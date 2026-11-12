from core.utils import grid_cell_from_position
import ai.carrier as carrier_logic
import ai.movement as movement_logic
import ai.goalkeeper as gk_logic
import ai.run_planner as run_planner
import ai.combos as combos
import ai.pressing as pressing
import ai.urgency as urgency
import ai.intercepts as intercepts
from ai.rl_actions import execute_rl_action

# Restarts take as long as they do in real football - but the time is spent
# walking into position, not standing still waiting for a timer.  Each restart
# is taken once (a) at least its MINIMUM time has passed (fetching the ball,
# placing it), (b) the taker is on the ball and (c) his team is set - or when
# its MAXIMUM is reached, whoever isn't set.
# Tuned so the AVERAGE times match the Premier League (Opta, 2025-27):
# throw-in ~16 s, goal kick ~29 s, corner ~35 s, free kick ~33 s overall -
# a quick one in midfield ~25 s, one swung into the box ~40 s, a direct
# free kick in shooting range (wall, ceremony) over a minute.
_RESTART_TIMING = {        # (minimum, maximum) seconds from the ball going dead
    "throw_in":    (12.0, 30.0),
    "goal_kick":   (24.0, 45.0),
    "corner_kick": (32.0, 55.0),
    "free_kick":   (20.0, 45.0),          # fallback - free kicks are timed by zone below
    "free_kick_long":     (20.0, 45.0),   # gameplay/set_pieces.py _fk_zone
    "free_kick_delivery": (33.0, 60.0),
    "free_kick_shoot":    (54.0, 90.0),
    "offside":     (12.0, 25.0),
    "penalty":     (45.0, 80.0),
    "kick_off":    (3.0, 90.0),     # after a goal: celebrate, walk back (see _kickoff_positions)
}
_DEFAULT_TIMING = (9.0, 25.0)
_MIN_SPREAD     = 1.4      # the minimum is a random time between min and this x min
QUICK_THROW     = 0.20     # chance a throw-in is taken quickly, without waiting for the team...
QUICK_THROW_MIN = 4.0      # ...as soon as this many seconds
SET_DIST        = 3.0      # m: a player this close to his restart spot is "set"...
SET_SHARE       = 0.85     # ...and a team is set when this share of its outfielders are
WALK_UNTIL      = 25.0     # m: further than this from his spot he jogs instead of walking
CELEBRATE_JOIN  = 45.0     # m: teammates this close to the scorer run over to celebrate
KICKOFF_SET     = 2.5      # m: everyone this close to his kick-off spot before kick-off


def _restart_timing(ball):
    """(minimum, maximum, quick) for this restart - picked once per restart."""
    key = (ball.restart_type, ball.restart_time)
    if getattr(ball, "_timing_for", None) != key:
        import random
        kind = ball.restart_type
        if kind == "free_kick":
            kind = "free_kick_" + str(getattr(ball, "_fk_zone", "long"))
        lo, hi = _RESTART_TIMING.get(kind, _RESTART_TIMING.get(ball.restart_type, _DEFAULT_TIMING))
        quick = ball.restart_type == "throw_in" and random.random() < QUICK_THROW
        ball._timing_for = key
        ball._timing = (QUICK_THROW_MIN if quick else random.uniform(lo, lo * _MIN_SPREAD), hi, quick)
    return ball._timing


def _walk_state(p):
    from config.constants import M_TO_PX
    return "walk" if (p.target - p.pos).length() < WALK_UNTIL * M_TO_PX else "idle"


class AIDecisionMaker:
    def __init__(self):
        self.last_possession_team = None
        self.run_state = {0: {}, 1: {}}     # off-the-ball runs per team (ai/run_planner.py)
        self.press_state = {0: {}, 1: {}}   # who is closing down the ball (ai/pressing.py)
        self.poss_since = {0: 0.0, 1: 0.0}  # when each team last won / lost the ball
        self._had_poss = {0: None, 1: None}

    def make_team_decisions(self, team, opponents, ball, current_time, mechanics):
        # Filter out red-carded / inactive players before any decisions
        team      = [p for p in team      if getattr(p, 'is_active', True)]
        opponents = [p for p in opponents if getattr(p, 'is_active', True)]
        if not team:
            return

        ball_cell = grid_cell_from_position(ball.pos)
        team_id = team[0].team

        # ── DEAD BALL RESTART ───────────────────────────────────────────────
        # If a restart is pending AND it belongs to this team, wait briefly
        # then hand possession to the restart taker so carrier logic kicks in.
        if ball.is_dead and ball.restart_taker is not None:
            if ball.restart_taker.team == team_id:
                elapsed = current_time - ball.restart_time
                min_t, max_t, quick = _restart_timing(ball)
                from config.constants import M_TO_PX
                taker_dist = (ball.restart_taker.pos - ball.pos).length() / M_TO_PX
                if ball.restart_type == "kick_off":
                    ready = elapsed >= min_t and taker_dist <= 0.4 and \
                        self._kickoff_ready(team + opponents, ball, current_time, elapsed >= max_t)
                else:
                    on_ball = taker_dist <= 0.4
                    set_ = quick or self._team_set(team, ball) and \
                        (ball.restart_type != "free_kick" or self._team_set(opponents, ball))
                    ready = (elapsed >= min_t and on_ball and set_) or elapsed >= max_t
                if ready and current_time < getattr(ball, "sub_hold_until", 0.0):
                    ready = False          # a substitution is being made (gameplay/substitutions.py)
                if ready:
                    from pygame.math import Vector2
                    taker = ball.restart_taker
                    # Capture restart type BEFORE clearing — carrier.py needs
                    # it to decide whether to cross (corner) or recycle (other).
                    restart_type_captured = ball.restart_type
                    # Snap taker to the exact ball position so the kick always
                    # originates from the correct spot (corner flag, GK box, etc.)
                    taker.pos    = Vector2(ball.pos)
                    taker.target = Vector2(ball.pos)
                    taker.vel    = Vector2(0, 0)
                    # Face INTO the pitch: the ball is held just in front of
                    # the player, so facing outwards (he usually arrives
                    # running towards the line) put it straight back out of
                    # play - throw-ins could ping-pong between the teams.
                    from config.constants import WIDTH, HEIGHT
                    inward = Vector2(WIDTH / 2, HEIGHT / 2) - taker.pos
                    if inward.length_squared() > 0:
                        taker.facing = inward.normalize()
                    ball.is_dead = False
                    ball.restart_type = None
                    ball.restart_taker = None
                    ball.owner = taker
                    taker.has_ball = True
                    self.last_possession_team = team_id
                    # Corner kicks → cross into the danger area.
                    # Free kicks → shoot or cross depending on distance.
                    # Penalties → always shoot.
                    # All other set pieces → pass via recycle layer.
                    if restart_type_captured == "corner_kick":
                        taker.must_cross_corner = True
                    elif restart_type_captured == "free_kick":
                        # gameplay/set_pieces.py: shoot / deliver it into the box / play it
                        zone = getattr(ball, "_fk_zone", "shoot")
                        if zone == "shoot":
                            taker.must_take_freekick = True
                        elif zone == "delivery":
                            taker.must_cross_corner = True
                        else:
                            taker.must_pass_restart = True
                    elif restart_type_captured == "penalty":
                        taker.must_take_penalty = True
                    else:
                        taker.must_pass_restart = True
                else:
                    # Still waiting — taker goes to the ball (walks to a goal
                    # kick or kick-off, jogs to fetch a throw-in)
                    from pygame.math import Vector2
                    ball.restart_taker.target = Vector2(ball.pos)
                    ball.restart_taker.state = "walk" if ball.restart_type in ("goal_kick", "kick_off") \
                        else "idle"
                    ball.restart_taker.pos_reason = "take restart"
            # Everyone else takes up position for the restart (they used to
            # keep their old orders - so whoever had chased the ball out ran
            # over and stood on it until the other team's taker arrived)
            if ball.is_dead and ball.restart_taker is not None:
                self._restart_positions(team, opponents, ball, current_time)
            # Either waiting or just activated — skip normal decisions this tick
            return
        # ────────────────────────────────────────────────────────────────────

        team_has_possession = self._determine_possession_state(ball.owner, team_id)
        if team_has_possession != self._had_poss[team_id]:
            self._had_poss[team_id] = team_has_possession
            self.poss_since[team_id] = current_time

        # ── Find ALL RL-agent players on this team ───────────────────────────
        # Must collect ALL of them — using next() only found the first one,
        # which meant only Neo ever got _run_rl_agent() called; Messi's
        # trajectory stayed empty and his Q-table never updated.
        rl_players = [p for p in team if p.rl_agent is not None]

        # 1. Update GK
        keeper = next((p for p in team if p.role == "GK"), None)
        if keeper:
            gk_logic.update_goalkeeper(
                keeper, ball, current_time, team_has_possession,
                ball_cell, opponents, team, mechanics
            )

        # 2. Possession Logic
        if team_has_possession:
            ball_owner = ball.owner

            # A. Carrier Decision
            if ball_owner and ball_owner.team == team_id:
                if ball_owner in rl_players:
                    # RL agent handles its own ball-carrying decision
                    _run_rl_agent(ball_owner, ball, team, opponents,
                                  ball_cell, current_time, mechanics)
                    self.last_possession_team = team_id
                else:
                    result = carrier_logic.make_ball_carrier_decision(
                        ball_owner, team, opponents, ball, current_time, mechanics
                    )
                    if result is not None:
                        self.last_possession_team = result

            # B. Off-Ball Movement
            movement_logic.handle_possession_movement(
                team, opponents, ball, ball_owner, current_time
            )
            # D. Run planner — runs in behind / into the box (both teams).
            #    Last, so a planned run overrides normal positioning.
            run_planner.update(self.run_state[team_id], team, opponents, ball, current_time)
            # Combination runs: overlaps, runs beyond the striker, third man (ai/combos.py)
            combos.update(self.run_state[team_id], team, opponents, ball, current_time)
            # Ball out wide in the final third: get bodies in the box (ai/attack_box.py)
            import ai.attack_box as attack_box
            attack_box.update(self.run_state[team_id], team, opponents, ball)
            self.press_state[team_id]["presser"] = None

            # RL agent off-ball override for every RL player not carrying
            for rl_p in rl_players:
                if rl_p is not ball_owner:
                    _run_rl_agent(rl_p, ball, team, opponents,
                                  ball_cell, current_time, mechanics)

        else:
            # 3. Defensive Logic
            # Possession lost: any runs this team was making are over
            runs = self.run_state[team_id].get("runs")
            if runs:
                for key in list(runs):
                    run_planner._end(runs, key, runs[key]["player"], current_time)
            ball_owner = ball.owner
            movement_logic.handle_defensive_movement(
                team, opponents, ball, ball_owner, team_has_possession, current_time
            )
            # Closing down the man on the ball (overrides one player's role target)
            pressing.update(self.press_state[team_id], team, opponents, ball, current_time,
                            current_time - self.poss_since[team_id])
            # A cross is on: pick up the runners in our box (ai/box_marking.py)
            import ai.box_marking as box_marking
            box_marking.update(team, opponents, ball, self.press_state[team_id].get("presser"))
            # Reading a pass and going to cut it out (ai/intercepts.py)
            intercepts.update(team, opponents, ball, current_time)
            # RL agent defensive override for every RL player
            for rl_p in rl_players:
                _run_rl_agent(rl_p, ball, team, opponents,
                              ball_cell, current_time, mechanics)

        # 4. How urgently everyone moves to their spot (walk / jog / run / sprint)
        urgency.update_team(team, ball, team_has_possession,
                            current_time - self.poss_since[team_id], current_time)

    # Restarts where the set-piece code doesn't place the players itself
    _SHAPE_RESTARTS = {"throw_in": 2.0, "goal_kick": 9.15, "offside": 9.15}   # opponents' minimum distance (m)

    def _team_set(self, team, ball):
        """Are (most of) this team's outfielders on their restart spots?"""
        from config.constants import M_TO_PX
        ps = [p for p in team if p.role != "GK" and p is not ball.restart_taker
              and getattr(p, "is_active", True)]
        if not ps:
            return True
        set_n = sum(1 for p in ps if (p.target - p.pos).length() <= SET_DIST * M_TO_PX)
        return set_n >= SET_SHARE * len(ps)

    def _kickoff_ready(self, players, ball, now, overdue):
        """Kick-off: celebrations over and everyone on his kick-off spot."""
        from config.constants import M_TO_PX
        from pygame.math import Vector2
        import gameplay.set_pieces as set_pieces
        cel = getattr(ball, "_celebration", None)
        if cel is not None and now < cel["until"] and not overdue:
            return False
        taker = ball.restart_taker
        spots = {t: set_pieces.kickoff_spots(t, t == taker.team, taker.slot) for t in (0, 1)}
        bad = [p for p in players if p is not taker and getattr(p, "is_active", True)
               and p.slot in spots[p.team]
               and (p.pos - spots[p.team][p.slot]).length() > KICKOFF_SET * M_TO_PX]
        if not bad:
            return True
        if not overdue:
            return False
        for p in bad:                     # safety net: a stuck player is put on his spot
            p.pos = Vector2(spots[p.team][p.slot])
            p.vel = Vector2(0, 0)
        return True

    def _kickoff_positions(self, team, ball, now):
        """
        After a goal: the scorer wheels away to celebrate and the teammates
        near him run over to join in, while everyone else walks back; then
        both teams walk to their kick-off spots.
        """
        from config.constants import M_TO_PX
        from pygame.math import Vector2
        import math
        import gameplay.set_pieces as set_pieces
        taker = ball.restart_taker
        tid = team[0].team
        spots = set_pieces.kickoff_spots(tid, taker.team == tid, taker.slot)
        cel = getattr(ball, "_celebration", None)
        celebrating = cel is not None and now < cel["until"] and cel["team"] == tid
        scorer = cel["scorer"] if celebrating else None
        for i, p in enumerate(team):
            if p is taker or not getattr(p, "is_active", True):
                continue
            spot = spots.get(p.slot)
            if spot is None:
                continue
            if celebrating and p.role != "GK" and \
                    (p is scorer or (p.pos - scorer.pos).length() < CELEBRATE_JOIN * M_TO_PX):
                if p is scorer:
                    p.target = Vector2(cel["spot"])
                    p.pos_reason = "celebrate!"
                else:
                    ang = 2.0 * math.pi * i / max(1, len(team))
                    p.target = scorer.pos + Vector2(math.cos(ang), math.sin(ang)) * (1.2 * M_TO_PX)
                    p.pos_reason = "celebrate with " + getattr(scorer, "name", "the scorer")
                p.state = "celebrate"
                continue
            p.target = Vector2(spot)
            p.state = _walk_state(p)
            p.pos_reason = "back for the kick-off"

    def _restart_positions(self, team, opponents, ball, current_time):
        from config.constants import M_TO_PX
        from pygame.math import Vector2
        import ai.team_shape as team_shape
        if ball.restart_type == "kick_off":
            self._kickoff_positions(team, ball, current_time)
            return
        gap = self._SHAPE_RESTARTS.get(ball.restart_type)
        if ball.restart_type == "free_kick" and getattr(ball, "_fk_zone", None) == "long":
            gap = 9.15                           # long free kick: both teams just take up their shape
        if gap is None:
            # Corners, free kicks, penalties: set_pieces.py gave everyone his
            # spot - they walk there (the keeper too)
            for p in team:
                if p is not ball.restart_taker and getattr(p, "is_active", True):
                    p.state = _walk_state(p)
            return
        taker = ball.restart_taker
        ours = taker.team == team[0].team
        shape = team_shape.compute(team, opponents, ball, ours, current_time, restart=ball.restart_type)
        for p in team:
            if p is taker or p.role == "GK":
                continue
            spot, why = shape.get(id(p), (Vector2(p.pos), "hold"))
            spot = Vector2(spot)
            if not ours:
                # Give the taker room (laws of the game: 2 m at a throw-in)
                away = spot - ball.pos
                d = away.length()
                need = (gap + 0.5) * M_TO_PX
                if d < need:
                    spot = ball.pos + (away.normalize() if d > 1e-6 else Vector2(0, 1)) * need
            p.target = spot
            p.state = _walk_state(p)                 # walk (jog if he's a long way out)
            p.pos_reason = f"restart: {why}"
        # The keepers go back to their goal (the taking keeper is the restart taker)
        keeper = next((p for p in team if p.role == "GK"), None)
        if keeper is not None and keeper is not taker:
            from config.constants import WIDTH, HEIGHT
            keeper.target = Vector2(3.0 * M_TO_PX if keeper.team == 0 else WIDTH - 3.0 * M_TO_PX, HEIGHT / 2)
            keeper.state = "walk"

    def _determine_possession_state(self, ball_owner, team_id):
        if ball_owner: 
            return ball_owner.team == team_id
        else: 
            return self.last_possession_team == team_id

def _run_rl_agent(player, ball, team, opponents, ball_cell, current_time, mechanics):
    """
    Execute one RL step for `player`.

    The agent only makes a NEW decision every RL_DECISION_INTERVAL seconds, or
    immediately when the player gains/loses the ball.  In between, the last
    chosen action keeps being executed so movement targets stay fresh.
    (Deciding every frame meant 25-80% random actions 60 times a second.)

    Uses agent.execute_fn if set (e.g. Messi's attacker actions),
    otherwise falls back to the default CB action executor.
    """
    from config.constants import RL_DECISION_INTERVAL
    agent    = player.rl_agent
    has_ball = (ball.owner is player)

    decision_due = (
        getattr(player, '_rl_action', None) is None
        or current_time >= getattr(player, '_rl_next_decision', 0.0)
        or has_ball != getattr(player, '_rl_had_ball', None)
    )
    if decision_due:
        state  = agent.get_state(player, ball, team, opponents)
        action = agent.choose_action(state, has_ball)
        agent.record(state, action, has_ball)
        player._rl_action        = action
        player._rl_had_ball      = has_ball
        player._rl_next_decision = current_time + RL_DECISION_INTERVAL
    action = player._rl_action

    # Agent-specific executor (set at init) or default CB executor
    exec_fn  = getattr(agent, 'execute_fn', None) or execute_rl_action
    exec_fn(action, player, ball, team, opponents,
            mechanics, current_time, ball_cell)
