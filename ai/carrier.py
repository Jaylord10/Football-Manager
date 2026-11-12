import random
from pygame.math import Vector2
from core.utils import distance, clamp
from config.constants import *
from ai.sanity import is_action_nonsense

# Import your NEW decision layers
import ai.shooting as shooting
import ai.decisive as decisive
import ai.progression as progression
import ai.recycle as recycle

import ai.actions as actions
import ai.goalkeeper as gk_logic

def _looks_offside(carrier, mate, opponents):
    from gameplay.through_pass import is_offside_now
    if not is_offside_now(mate, carrier, opponents):
        return False
    # How far offside is he?  Clear offsides are always spotted.
    sign = 1.0 if carrier.team == 0 else -1.0
    xs = sorted((o.pos.x for o in opponents), reverse=(sign > 0))
    line_x = xs[1] if len(xs) >= 2 else xs[0]
    beyond_m = (mate.pos.x - line_x) * sign / M_TO_PX
    if beyond_m > 1.0:
        return True
    decisions = carrier.attributes.get("Decisions", 10)
    return random.random() > 0.5 * (1.0 - decisions / 20.0)


_SET_PIECE_FLAGS = ("must_take_penalty", "must_take_freekick", "must_cross_corner", "must_pass_restart")
_TIMING_PRESSURE = 3.5      # m: an opponent this close when he receives it = he's under pressure
_SETUP_SPEED     = 0.3      # dribble pace while he sets a pass / shot
_TOUCH_CLEAN_BASE        = 0.45   # chance his first touch is clean: this...
_TOUCH_CLEAN_PER_CONTROL = 0.03   # ...plus this per Control point (13 -> 0.84)...
_TOUCH_CLEAN_PRESSURE    = 0.10   # ...less this with a man on him


def make_ball_carrier_decision(carrier, team, opponents, ball, current_time, mechanics):
    """
    The man on the ball, with human timing (ai/decision_timing.py): control
    it, look up, decide, set the pass or shot - and only then strike it.
    """
    import ai.decision_timing as timing
    if carrier.role == "GK" or any(getattr(carrier, f, False) for f in _SET_PIECE_FLAGS):
        return _decide(carrier, team, opponents, ball, current_time, mechanics)

    spell = getattr(carrier, "last_received_time", None)
    st = getattr(carrier, "_timing", None)
    if st is None or st["spell"] != spell:
        # A loose ball / their cross / a rebound in his own box with a man on
        # him: he doesn't control it - he hits it away first time (ai/clearance.py)
        import ai.clearance as clearance
        if clearance.wants_first_time(carrier, ball, opponents):
            carrier._timing = {"spell": spell, "pending": None, "next": current_time + 1.0}
            kind, aim = clearance.plan(carrier, team, opponents, True)
            return mechanics.execute_clearance(carrier, ball, current_time, kind, aim,
                                               pressured=True, first_time=True)
        # Just received it: first touch, and (unless he'd already seen his
        # options) a look up before he can decide anything
        near = min((distance(carrier.pos, o.pos) for o in opponents
                    if o.role != "GK" and getattr(o, "is_active", True)), default=9e9)
        pressured = near < _TIMING_PRESSURE * M_TO_PX
        picture = timing.has_picture(carrier, ball)
        st = {"spell": spell, "pending": None,
              "next": current_time + timing.first_decision(carrier, pressured, picture)}
        carrier._timing = st
        carrier._busy_until = st["next"]       # controlling it: not a take-on (gameplay/duels.py)
        # How good is his first touch?  A clean one protects the ball; a heavy
        # one leaves it there to be nicked (gameplay/duels.py)
        p_clean = _TOUCH_CLEAN_BASE + _TOUCH_CLEAN_PER_CONTROL * _stat20(carrier, "Control") \
            - (_TOUCH_CLEAN_PRESSURE if pressured else 0.0)
        carrier._touch_clean = random.random() < p_clean
        carrier._go_at_him = False
        _control_touch(carrier, opponents, ball, current_time, mechanics, pressured)
        ball.intended_target = None
        return carrier.team

    pending = st["pending"]
    if pending is not None:
        if current_time >= pending["at"]:
            st["pending"] = None
            st["next"] = current_time + timing.redecide_gap(carrier)
            if pending["kind"] == "pass":
                mechanics.execute_pass(*pending["args"])
            elif pending["kind"] == "cross":
                ps_, rc_, b_, op_, kind_ = pending["args"]
                mechanics.execute_cross(ps_, rc_, b_, current_time, op_, kind_)
            elif pending["kind"] == "clear":
                p_, b_, kind_, aim_, pr_ = pending["args"]
                mechanics.execute_clearance(p_, b_, current_time, kind_, aim_, pr_)
            else:
                mechanics.execute_shot(*pending["args"], **pending.get("kw", {}))
            return carrier.team
        return carrier.team                    # still setting it (moving slowly - see below)

    if current_time < st["next"]:
        ball.intended_target = None
        return carrier.team                    # carrying on with what he's doing

    deferred = timing.Deferred(mechanics, carrier, current_time)
    result = _decide(carrier, team, opponents, ball, current_time, deferred)
    st["next"] = current_time + timing.redecide_gap(carrier)
    if deferred.queued is not None:
        st["pending"] = deferred.queued
        carrier._busy_until = deferred.queued["at"]
        # Setting the pass / shot: he slows right down
        ahead = carrier.pos + (carrier.facing * (1.0 * M_TO_PX) if carrier.facing.length_squared() > 0 else Vector2())
        mechanics.execute_dribble(carrier, ahead, ball, current_time, speed_mult=_SETUP_SPEED)
    return result


def _control_touch(carrier, opponents, ball, now, mechanics, pressured):
    """His first touch: take it forward into space, or away from the man on him."""
    goal = Vector2(WIDTH, HEIGHT / 2) if carrier.team == 0 else Vector2(0, HEIGHT / 2)
    direction = goal - carrier.pos
    if pressured:
        opp = min((o for o in opponents if o.role != "GK" and getattr(o, "is_active", True)),
                  key=lambda o: distance(carrier.pos, o.pos), default=None)
        if opp is not None and (carrier.pos - opp.pos).length_squared() > 0:
            direction = carrier.pos - opp.pos
    if direction.length_squared() == 0:
        direction = Vector2(1, 0)
    target = carrier.pos + direction.normalize() * ((1.5 if pressured else 3.0) * M_TO_PX)
    target.x = clamp(target.x, 0, WIDTH)
    target.y = clamp(target.y, 0, HEIGHT)
    mechanics.execute_dribble(carrier, target, ball, now, speed_mult=0.5 if pressured else 0.7)


def _decide(carrier, team, opponents, ball, current_time, mechanics):
    """The decision itself (shoot / play it / carry it / keep it)."""
    ball.intended_target = None
    
    # Don't pass to teammates standing offside (a tight call - within a
    # metre - may be misjudged, less often by players with good Decisions)
    onside = [p for p in team if p is carrier or not _looks_offside(carrier, p, opponents)]
    teammates = [p for p in onside if p is not carrier and p.role != "GK"]
    # GK included only for the recycle (backpass) layer so CBs can play it back
    teammates_with_gk = [p for p in onside if p is not carrier]
    opponent_field_players = [o for o in opponents if o.role != "GK"]
    
    # --- PRESSURE ANALYSIS ---
    nearest_opp_dist = 9999
    nearest_opp = None
    if opponent_field_players:
        nearest_opp = min(opponent_field_players, key=lambda d: distance(carrier.pos, d.pos))
        nearest_opp_dist = distance(carrier.pos, nearest_opp.pos)
    
    is_under_pressure = nearest_opp_dist < 2.5 * M_TO_PX
    is_panic = nearest_opp_dist < 1.0 * M_TO_PX
    # REAL pressure (someone on him, or about to be) - not just someone nearby
    real_pressure = _real_pressure(carrier, opponent_field_players)

    # --- GK LOGIC ---
    if carrier.role == "GK":
        return gk_logic.handle_goalkeeper_with_ball(carrier, teammates, opponent_field_players, ball, current_time, mechanics)

    # ========================================================================
    # PENALTY — step up and shoot, no hesitation
    # ========================================================================
    if getattr(carrier, 'must_take_penalty', False):
        carrier.must_take_penalty = False
        mechanics.execute_shot(carrier, ball, current_time, opponents, shot_type="penalty")
        return carrier.team

    # ========================================================================
    # FREE KICK — shoot if within range, otherwise play to a teammate
    # ========================================================================
    if getattr(carrier, 'must_take_freekick', False):
        carrier.must_take_freekick = False
        goal_pos = Vector2(WIDTH, HEIGHT / 2) if carrier.team == 0 else Vector2(0.0, HEIGHT / 2)
        dist_m   = (goal_pos - carrier.pos).length() / M_TO_PX
        if dist_m <= 30.0:
            # In shooting range — strike at goal
            mechanics.execute_shot(carrier, ball, current_time, opponents)
        else:
            # Too far out — find the best pass
            rc_action, rc_target, _ = recycle.evaluate_recycle_layer(
                carrier, teammates_with_gk, opponent_field_players
            )
            if rc_action == "pass" and rc_target is not None:
                mechanics.execute_pass(carrier, rc_target, ball, current_time)
            elif teammates:
                best = max(teammates, key=lambda t: distance(carrier.pos, t.pos))
                mechanics.execute_pass(carrier, best, ball, current_time)
        return carrier.team

    # ========================================================================
    # CORNER KICK — cross into the danger area (6-yard box ↔ penalty spot)
    # ========================================================================
    # Corner takers skip the recycle layer entirely and whip the ball into
    # the corridor between the 6-yard box (5.5 m) and the penalty spot (11 m).
    # We target the teammate standing closest to that zone's centre — typically
    # a near-post or penalty-spot runner placed there by _setup_corner_kick.
    if getattr(carrier, 'must_cross_corner', False):
        carrier.must_cross_corner = False
        # Danger-zone centre: 8.25 m from the goal line, middle of the pitch.
        if carrier.team == 0:
            danger_x = WIDTH - 8.25 * M_TO_PX
        else:
            danger_x = 8.25 * M_TO_PX
        from pygame.math import Vector2 as _V2
        danger_centre = _V2(danger_x, HEIGHT / 2)
        # Pick the teammate closest to the danger zone (excludes carrier & GK)
        cross_candidates = [p for p in teammates if p.role != "GK"]
        if cross_candidates:
            best = min(cross_candidates, key=lambda t: distance(t.pos, danger_centre))
            # Swung in, in the air (gameplay/crossing.py)
            mechanics.execute_cross(carrier, best, ball, current_time, opponents, kind="set_piece")
            return carrier.team
        # Fallback: nearest outfield teammate
        if teammates:
            best = min(teammates, key=lambda t: distance(carrier.pos, t.pos))
            mechanics.execute_pass(carrier, best, ball, current_time)
            return carrier.team

    # ========================================================================
    # SET-PIECE RESTART — always pass, never dribble into play
    # ========================================================================
    # The flag is set by the dead-ball handover in decision_maker so that
    # throw-ins and goal kicks are always played to a teammate rather than
    # dribbled.  Bypasses shooting, the settle window, and all dribble layers.
    if getattr(carrier, 'must_pass_restart', False):
        carrier.must_pass_restart = False
        # Try the recycle layer first — it knows how to find open teammates
        rc_action, rc_target, _ = recycle.evaluate_recycle_layer(
            carrier, teammates_with_gk, opponent_field_players
        )
        if rc_action == "pass" and rc_target is not None:
            mechanics.execute_pass(carrier, rc_target, ball, current_time)
            return carrier.team
        # Fallback: nearest teammate who isn't too close
        if teammates:
            best = max(teammates, key=lambda t: distance(carrier.pos, t.pos))
            mechanics.execute_pass(carrier, best, ball, current_time)
            return carrier.team

    # ========================================================================
    # DECISION HIERARCHY (4-Layer System)
    # ========================================================================

    # LAYER 0: CLEAR IT
    # In his own defensive third and it isn't safe to keep it: get rid of it
    # (ai/clearance.py) - up the pitch, into touch, or behind.
    import ai.clearance as clearance
    if clearance.wants_to_clear(carrier, teammates_with_gk, opponent_field_players, real_pressure):
        kind, aim = clearance.plan(carrier, teammates, opponent_field_players, real_pressure)
        mechanics.execute_clearance(carrier, ball, current_time, kind, aim, real_pressure)
        return carrier.team

    # LAYER 1: SHOOTING
    should_shoot, shoot_score = shooting.evaluate_shoot_decision(carrier, opponent_field_players, teammates)
    if should_shoot:
        # Pass opponents so pressure, Composure and the keeper's position count
        mechanics.execute_shot(carrier, ball, current_time, opponents)
        return carrier.team
    
    # LAYER 2: DECISIVE (Through balls, counter attacks, crosses)
    decisive_action, decisive_target = decisive.evaluate_decisive_layer(carrier, opponent_field_players, teammates)
    if decisive_action:
        if decisive_action == "pass":
            mechanics.execute_pass(carrier, decisive_target, ball, current_time)
            return carrier.team
        elif decisive_action == "through_ball":
            # Pass into space ahead of the runner (see gameplay/through_pass.py)
            mechanics.execute_pass(carrier, decisive_target, ball, current_time,
                                   through_plan=decisive.last_through_plan)
            return carrier.team
        elif decisive_action == "dribble":
            mechanics.execute_dribble(carrier, decisive_target, ball, current_time, speed_mult=1.0)
            carrier._go_at_him = _fancies_it(carrier, opponent_field_players, current_time)
            return carrier.team
        elif decisive_action == "cross":
            # A lofted ball into the box (gameplay/crossing.py)
            mechanics.execute_cross(carrier, decisive_target, ball, current_time, opponents)
            return carrier.team
    
    # ========================================================================
    # LAYER 2a: PLAY THE COMBINATION
    # ========================================================================
    # A teammate is overlapping / running beyond / making a third-man run
    # off this player (ai/combos.py).  Once he's level or ahead with an open
    # lane, play him in - if the carrier has spotted it (Passing + Decisions).
    combo_target, combo_plan = _combination_pass(carrier, teammates, opponents)
    if combo_target is not None:
        mechanics.execute_pass(carrier, combo_target, ball, current_time, through_plan=combo_plan)
        return carrier.team
    # An overlap is coming round him: hold it up until the full-back is level
    if nearest_opp_dist > _HOLD_UP_PRESSURE * M_TO_PX:
        hold_target = _hold_up_for_overlap(carrier, teammates, current_time)
        if hold_target is not None:
            mechanics.execute_dribble(carrier, hold_target, ball, current_time, speed_mult=_HOLD_UP_SPEED)
            carrier.last_decision_time = current_time
            return carrier.team

    # ========================================================================
    # LAYER 2c: CARRY IT INTO SPACE
    # ========================================================================
    # Open grass in front of him and nobody engaging him: a real player runs
    # with it - the defence has to come to him, and that opens the passes.
    # (Before, he compared "am I more dangerous than my teammate?" and the
    # man further forward always won, so 60% of players with 15 m+ of space
    # ahead passed it on without carrying it 5 m.)
    carry = _carry_target(carrier, opponent_field_players)
    if carry is not None:
        target, speed = carry
        mechanics.execute_dribble(carrier, target, ball, current_time, speed_mult=speed)
        carrier._go_at_him = False             # running into space, not at a man
        carrier.last_decision_time = current_time
        return carrier.team

    # ========================================================================
    # LAYER 2b: RELEASE UNDER PRESSURE
    # ========================================================================
    # Being closed down, a real player who has scanned knows where his
    # support is - even beside or behind him, outside the narrow "vision
    # cone" the other layers use - and plays it before he's caught.
    # Good dribblers sometimes take the man on instead (decided once per
    # spell of pressure, so he doesn't dither).  See ai/patterns.py for the
    # teammates who come to help.
    if real_pressure and not getattr(carrier, "must_cross_corner", False):
        choice = _pressure_choice(carrier, current_time)
        carrier._go_at_him = choice == "take_on"
        if choice == "release":
            target = _best_release(carrier, teammates_with_gk, opponents)
            if target is not None:
                mechanics.execute_pass(carrier, target, ball, current_time)
                return carrier.team

    # ========================================================================
    # COMMITMENT GUARDS — prevent frame-by-frame flip-flopping
    # ========================================================================
    # Shield commitment: shielding is slow and deliberate — hold for 0.6 s.
    # Layers 1-2 (shooting / decisive) still interrupt immediately.
    SHIELD_COMMIT_TIME = 0.6
    if (carrier.state == "shield" and
            current_time - carrier.last_decision_time < SHIELD_COMMIT_TIME):
        return carrier.team  # Keep shielding — don't break out early

    # Dribble commitment: shorter window (0.25 s) to stop oscillating between
    # pass and dribble every frame.
    DRIBBLE_COMMIT_TIME = 0.25  # seconds
    if (carrier.state == "dribble" and
            current_time - carrier.last_decision_time < DRIBBLE_COMMIT_TIME):
        return carrier.team  # Keep current dribble going — don't switch yet

    # ========================================================================
    # LAYER 3: PROGRESSION (with smart dribbling)
    # ========================================================================
    prog_result = progression.evaluate_progression_layer(carrier, teammates, opponent_field_players)

    # Check if we got a dribble action (returns 4 values including speed!)
    if len(prog_result) == 4:
        prog_action, prog_target, prog_score, prog_speed = prog_result
    else:
        prog_action, prog_target, prog_score = prog_result
        prog_speed = 1.0  # Default speed if not dribbling

    # ------------------------------------------------------------------
    # WAITING FOR THE RIGHT MOMENT: when he's just got it, only a clearly
    # good pass is worth playing; the bar comes down the longer he has it
    # (and straight away if he's under real pressure).  Not good enough yet:
    # he keeps it - carries, shifts it, shields - and looks again.
    # ------------------------------------------------------------------
    if prog_action == "pass" and not real_pressure \
            and prog_score < _PASS_BAR + _PASS_BAR_EARLY * _bar_left(carrier, current_time):
        prog_action = None

    # ------------------------------------------------------------------
    # PRE-COMPUTE RECYCLE — used for patience check AND Layer 4.
    # Evaluated once here so Layer 4 doesn't duplicate the work.
    # ------------------------------------------------------------------
    recycle_action, recycle_target, recycle_score = recycle.evaluate_recycle_layer(
        carrier, teammates_with_gk, opponent_field_players
    )

    # ------------------------------------------------------------------
    # PATIENCE CHECK: prefer a safe recycle over a marginal forward move.
    # Real players rarely force a fifty-fifty forward pass when a simple
    # sideways or backward option is much safer.
    # The recycle score is metres of space around the receiver (often
    # 15-35), the progression score is ~10 x threat (0-10ish).  Comparing
    # them directly meant ANY forward option short of excellent got swapped
    # for a safe pass back - often to the keeper.  Convert the recycle score
    # to the same scale first: a wide-open safe pass is worth at most 7.5.
    # ------------------------------------------------------------------
    PATIENCE_GAP = 0.5
    MARGINAL_FORWARD = 7.0
    recycle_value = min(7.5, 2.0 + recycle_score / 4.0) if recycle_score else 0.0
    if (prog_action and prog_action != "recycle"
            and prog_score < MARGINAL_FORWARD    # forward option is only marginal
            and recycle_action == "pass"
            and recycle_target is not None
            and recycle_value > prog_score + PATIENCE_GAP):
        if _keep_it(carrier, opponent_field_players, ball, current_time, mechanics, real_pressure):
            return carrier.team
        mechanics.execute_pass(carrier, recycle_target, ball, current_time)
        return carrier.team

    # Execute the best forward/lateral option from the progression layer
    if prog_action and prog_action != "recycle":
        if prog_action == "pass":
            mechanics.execute_pass(carrier, prog_target, ball, current_time)
            return carrier.team

        elif prog_action == "dribble":
            # prog_speed tells us how fast to dribble based on nearby defenders
            mechanics.execute_dribble(carrier, prog_target, ball, current_time, speed_mult=prog_speed)
            # Running at a defender: does he actually want to take him on?
            carrier._go_at_him = _fancies_it(carrier, opponent_field_players, current_time)
            carrier.last_decision_time = current_time  # start commitment window
            return carrier.team

        elif prog_action == "sidestep":
            mechanics.execute_dribble(carrier, prog_target, ball, current_time, speed_mult=1.1)
            carrier._go_at_him = _fancies_it(carrier, opponent_field_players, current_time)
            carrier.last_decision_time = current_time
            return carrier.team

        elif prog_action == "turn":
            mechanics.execute_dribble(carrier, prog_target, ball, current_time, speed_mult=0.9)
            carrier.last_decision_time = current_time
            return carrier.team

    # LAYER 4: RECYCLE (Safety pass — includes GK so CBs can play it back)
    # Reuses the recycle already computed above — no duplicate evaluation.
    if recycle_action == "pass" and recycle_target:
        if _keep_it(carrier, opponent_field_players, ball, current_time, mechanics, real_pressure):
            return carrier.team
        mechanics.execute_pass(carrier, recycle_target, ball, current_time)
        return carrier.team
    
    # ========================================================================
    # LAYER 5: EMERGENCY FALLBACK
    # ========================================================================
    # If NO layer found a good option, do emergency action
    
    if is_panic:
        # PANIC: Just boot it away from danger
        if nearest_opp:
            flee_dir = (carrier.pos - nearest_opp.pos).normalize()
        else:
            flee_dir = Vector2(0, 1)

        target = carrier.pos + flee_dir * (3.0 * M_TO_PX)
        target.x = clamp(target.x, 0, WIDTH)
        target.y = clamp(target.y, 0, HEIGHT)

        mechanics.execute_dribble(carrier, target, ball, current_time, speed_mult=0.9)
        carrier.last_decision_time = current_time
        return carrier.team

    elif is_under_pressure and current_time - getattr(carrier, "_shield_since", current_time) > _SHIELD_MAX:
        # He's been shielding too long with nothing on: play anything that's
        # open (backwards included), or turn out of trouble into space
        carrier._shield_since = current_time
        out = _escape_pass(carrier, teammates_with_gk, opponents)
        if out is not None:
            mechanics.execute_pass(carrier, out, ball, current_time)
            return carrier.team
        target = _escape_space(carrier, opponent_field_players)
        mechanics.execute_dribble(carrier, target, ball, current_time, speed_mult=0.9)
        carrier.last_decision_time = current_time
        return carrier.team

    elif is_under_pressure:
        # SHIELD: Slow, deliberate back-into-defender movement.
        # 0.25× speed (barely creeping) + very short target (1.5 m) means the
        # player plants themselves and uses their body to protect the ball
        # rather than sprinting away.  The commitment guard at the top of this
        # function ensures this state is held for 0.6 s so the player doesn't
        # instantly flip to dribbling if a pass doesn't immediately appear.
        if nearest_opp:
            flee_dir = (carrier.pos - nearest_opp.pos).normalize()
        else:
            flee_dir = Vector2(0, 1)

        target = carrier.pos + flee_dir * (1.5 * M_TO_PX)
        target.x = clamp(target.x, 0, WIDTH)
        target.y = clamp(target.y, 0, HEIGHT)

        mechanics.execute_dribble(carrier, target, ball, current_time, speed_mult=0.25)
        if carrier.state != "shield":
            carrier._shield_since = current_time
        carrier.state = "shield"
        carrier.last_decision_time = current_time
        return carrier.team

    else:
        # NO PRESSURE: Player is completely free — make a committed run.
        # Old code only looked 2 m ahead, producing hesitant creeping movement.
        # Now we stride 10 m toward goal, which looks purposeful and realistic.
        goal_pos = Vector2(WIDTH, HEIGHT/2) if carrier.team == 0 else Vector2(0, HEIGHT/2)
        direction = (goal_pos - carrier.pos).normalize()
        target = carrier.pos + direction * (10.0 * M_TO_PX)
        target.x = clamp(target.x, 0, WIDTH)
        target.y = clamp(target.y, 0, HEIGHT)

        mechanics.execute_dribble(carrier, target, ball, current_time, speed_mult=0.9)
        carrier.last_decision_time = current_time
        return carrier.team


# ---------------------------------------------------------------------------
# Release under pressure (layer 2b)
# ---------------------------------------------------------------------------
_RELEASE_PRESSURE = 3.5     # m: an opponent this close = time to get rid of it
_RELEASE_RANGE    = 25.0    # m: teammates within this are options
_RELEASE_MIN_LANE = 0.6     # lane must be at least this open (ai/spot_value.py)
_RELEASE_MIN      = 2.0     # score needed to play it
_EPISODE_GAP      = 1.0     # s without pressure ends a "spell" of pressure


def _stat20(p, name):
    v = p.attributes.get(name, 10)
    if v > 25:
        v /= 5.0
    return max(1.0, min(20.0, v))


_TAKE_ON_PATIENCE = 1.5     # s: if the take-on / protecting hasn't got him out by then, he looks to release it
_PROTECT_BASE  = 0.15       # chance he protects it first under pressure: this...
_PROTECT_RANGE = 0.35       # ...plus up to this (Composure + Strength)


def _pressure_choice(carrier, now):
    """'release' or 'take_on', decided once per spell of pressure.
    A 'take_on' only lasts _TAKE_ON_PATIENCE s: if the defender won't let him
    go at him (he's beside or behind him), he gives up on it and looks for a
    pass - before, he could shield in the corner until half-time."""
    import random
    if now - getattr(carrier, "_press_last", -99.0) > _EPISODE_GAP or \
            getattr(carrier, "_press_choice", None) is None:
        p_take_on = 0.05 * (_stat20(carrier, "Dribbling") - 10) + 0.03 * (_stat20(carrier, "Agility") - 10) + 0.1
        p_take_on = max(0.05, min(0.6, p_take_on))
        # Composed, strong players often protect it first and pass a moment later
        calm = 0.5 * (_stat20(carrier, "Composure") + _stat20(carrier, "Strength"))
        p_protect = _PROTECT_BASE + _PROTECT_RANGE * (calm - 1) / 19
        r = random.random()
        carrier._press_choice = "take_on" if r < p_take_on else \
            "protect" if r < p_take_on + p_protect * (1.0 - p_take_on) else "release"
        carrier._press_since = now
    elif carrier._press_choice in ("take_on", "protect") \
            and now - getattr(carrier, "_press_since", now) > _TAKE_ON_PATIENCE:
        carrier._press_choice = "release"
    carrier._press_last = now
    return carrier._press_choice


def _best_release(carrier, mates, opponents):
    import ai.spot_value as spot_value
    from ai.team_shape import to_frame
    tid = carrier.team
    ca, cl = to_frame(tid, carrier.pos)
    opps = [to_frame(tid, o.pos) for o in opponents if getattr(o, "is_active", True)]
    best = None
    for m in mates:
        ma, ml = to_frame(tid, m.pos)
        if m.role == "GK" and ca > 35.0:
            continue                     # back to the keeper only from our own third
        d = ((ma - ca) ** 2 + (ml - cl) ** 2) ** 0.5
        if d < 4.0 or d > _RELEASE_RANGE:
            continue
        lane, t = spot_value.lane_and_time(ma, ml, ca, cl, opps)
        if lane < _RELEASE_MIN_LANE:
            continue
        score = (2.0 * lane + max(0.0, min(1.0, (t + 0.5) / 2.5))
                 + 0.3 * (ma - ca) / 10.0 + (0.5 if getattr(m, "_support_job", False) else 0.0))
        if best is None or score > best[0]:
            best = (score, m)
    if best is None or best[0] < _RELEASE_MIN:
        return None
    return best[1]


# ---------------------------------------------------------------------------
# Play the combination (layer 2a)
# ---------------------------------------------------------------------------
_COMBO_KINDS      = ("overlap", "underlap", "beyond", "third_man")
_COMBO_MIN_LANE   = 0.7
_COMBO_MIN_TIME   = 0.3      # s on the ball when it arrives
_ARRIVING         = 2.0      # m: a runner this close behind, at speed, can be played in


def _combination_pass(carrier, mates, opponents):
    """(runner, through_plan or None) if a combination run is on, else (None, None)."""
    import random
    import ai.spot_value as spot_value
    import gameplay.through_pass as through_pass
    from ai.team_shape import to_frame
    tid = carrier.team
    ca, cl = to_frame(tid, carrier.pos)
    opps = [to_frame(tid, o.pos) for o in opponents if getattr(o, "is_active", True)]
    for m in mates:
        run = getattr(m, "_planned_run", None)
        if not run or run.get("kind") not in _COMBO_KINDS or carrier not in (run.get("partners") or ()):
            continue
        ma, ml = to_frame(tid, m.pos)
        if ma < ca - _ARRIVING:
            continue                         # not with him yet
        plan = through_pass.plan(carrier, m, opponents)
        if plan is None:
            lane, t = spot_value.lane_and_time(ma, ml, ca, cl, opps)
            if lane < _COMBO_MIN_LANE or t < _COMBO_MIN_TIME:
                continue
        # Has he seen it?  Decided once per run.
        if "_seen" not in run:
            skill = _stat20(carrier, "Passing") + _stat20(carrier, "Decisions")
            run["_seen"] = random.random() < max(0.3, min(0.9, 0.55 + 0.03 * (skill - 20)))
        if run["_seen"]:
            return m, plan
    return None, None


_HOLD_UP_PRESSURE = 3.0      # m: hold it up only while nobody is right on him
_HOLD_UP_SPEED    = 0.35     # dribble pace while waiting
_HOLD_UP_MAX      = 3.0      # s at most


def _hold_up_for_overlap(carrier, mates, now):
    """A slow touch inside while an overlap/underlap gets level. None if not needed."""
    from ai.team_shape import to_frame, to_world
    tid = carrier.team
    ca, cl = to_frame(tid, carrier.pos)
    for m in mates:
        run = getattr(m, "_planned_run", None)
        if not run or run.get("kind") not in ("overlap", "underlap") or carrier not in (run.get("partners") or ()):
            continue
        if now - run["start"] > _HOLD_UP_MAX:
            continue
        ma, _ = to_frame(tid, m.pos)
        if ma >= ca - _ARRIVING:
            continue                          # he's arriving: layer 2a plays him in
        # Check inside (towards the middle) and slightly forward, drawing the marker
        inside = -1.0 if cl > 0 else 1.0
        return to_world(tid, ca + 1.5, cl + inside * 3.0)
    return None



# ---------------------------------------------------------------------------
# Carrying it into space (layer 2c) and patience
# ---------------------------------------------------------------------------
_CARRY_APPETITE = {"LCB": 0.45, "RCB": 0.45, "LB": 0.6, "RB": 0.6, "LCM": 0.7, "RCM": 0.7,
                   "LM": 0.85, "RM": 0.85, "ST1": 0.75, "ST2": 0.75}
_CARRY_NEED = ((25.0, 0.25), (15.0, 0.35), (10.0, 0.50), (7.0, 0.65))  # (m of space ahead, appetite needed)
_CARRY_CB_SPACE = 12.0     # m: centre-backs only step in with this much room
_CARRY_CONE     = 0.6      # an opponent is "ahead" if within this x distance sideways of his line (+2 m)
_CARRY_ENGAGED  = 5.0      # m: an opponent this close in front = he's being engaged: stop and decide
_CARRY_CLOSE    = 3.0      # m: anyone this close, any side
_PATIENCE       = (1.5, 3.0)   # s he'll wait for a better option (Composure + Decisions 1 / 20)
_PASS_BAR       = 5.0      # progression pass score that's always good enough...
_PASS_BAR_EARLY = 3.0      # ...plus this much more when he's only just got it (falls to 0 over _PATIENCE)
_REAL_PRESSURE  = (2.5, 1.7)   # m: someone this close is "on him" (Composure 1 / 20)...
_CLOSING_TIME   = 0.35     # ...or will be within this many seconds
_CLOSING_RANGE  = 6.0      # m: (only counting opponents this close)


def _bar_left(carrier, now):
    """1 when he's just got it, falling to 0 when his patience runs out."""
    held = now - getattr(carrier, "last_received_time", now)
    lo, hi = _PATIENCE
    calm = 0.5 * (_stat20(carrier, "Composure") + _stat20(carrier, "Decisions"))
    patience = lo + (hi - lo) * (calm - 1) / 19
    return max(0.0, 1.0 - held / patience)


def _real_pressure(carrier, opponents):
    """Someone on him, or about to be - a composed player feels it later."""
    lo, hi = _REAL_PRESSURE
    r = (lo + (hi - lo) * (_stat20(carrier, "Composure") - 1) / 19) * M_TO_PX
    for o in opponents:
        if not getattr(o, "is_active", True):
            continue
        rel = carrier.pos - o.pos
        d = rel.length()
        if d < r:
            return True
        if 0 < d < _CLOSING_RANGE * M_TO_PX:
            closing = o.vel.dot(rel / d)
            if closing > 0 and (d - r) / closing < _CLOSING_TIME:
                return True
    return False


def _space_ahead(carrier, opponents):
    goal = Vector2(WIDTH, HEIGHT / 2) if carrier.team == 0 else Vector2(0, HEIGHT / 2)
    to_goal = goal - carrier.pos
    if to_goal.length_squared() == 0:
        return 0.0, 0.0, to_goal
    dirg = to_goal.normalize()
    ahead_m, close_m = 99.0, 99.0
    for o in opponents:
        if not getattr(o, "is_active", True):
            continue
        rel = o.pos - carrier.pos
        d = rel.length() / M_TO_PX
        close_m = min(close_m, d)
        along = rel.dot(dirg) / M_TO_PX
        side = abs(rel.cross(dirg)) / M_TO_PX
        if along > 0 and side < _CARRY_CONE * along + 2.0:
            ahead_m = min(ahead_m, d)
    return ahead_m, close_m, dirg


def _carry_target(carrier, opponents):
    """(target, speed) if he should run with it, else None."""
    ahead_m, close_m, dirg = _space_ahead(carrier, opponents)
    if close_m < _CARRY_CLOSE or ahead_m < _CARRY_ENGAGED:
        return None
    if carrier.role in ("LCB", "RCB") and ahead_m < _CARRY_CB_SPACE:
        return None
    need = next((n for space, n in _CARRY_NEED if ahead_m >= space), None)
    if need is None:
        return None
    want = _CARRY_APPETITE.get(carrier.role, 0.7) \
        * (0.6 + 0.4 * (_stat20(carrier, "Dribbling") - 1) / 19) \
        * (0.85 + 0.15 * (_stat20(carrier, "Composure") - 1) / 19)
    if want < need:
        return None
    from ai.smart_dribbling import calculate_smart_dribble_target, calculate_dribble_speed
    goal = Vector2(WIDTH, HEIGHT / 2) if carrier.team == 0 else Vector2(0, HEIGHT / 2)
    target = calculate_smart_dribble_target(carrier, opponents, goal)
    return target, calculate_dribble_speed(carrier, target, opponents)


def _keep_it(carrier, opponents, ball, now, mechanics, real_pressure):
    """
    Patience: nothing better than a safe pass sideways or back, and nobody on
    him - keep it a moment (shift it, look for movement) instead of giving
    it straight away.  Composed players wait longer.
    """
    if real_pressure or _bar_left(carrier, now) <= 0.0:
        return False
    goal = Vector2(WIDTH, HEIGHT / 2) if carrier.team == 0 else Vector2(0, HEIGHT / 2)
    dirg = goal - carrier.pos
    if dirg.length_squared() == 0:
        return False
    side = Vector2(-dirg.y, dirg.x).normalize()
    if (side.y > 0) == (carrier.pos.y > HEIGHT / 2):
        side = -side                                    # shift it towards the middle
    target = carrier.pos + (side * 1.5 + dirg.normalize() * 0.5) * M_TO_PX
    mechanics.execute_dribble(carrier, target, ball, now, speed_mult=0.4)
    carrier.last_decision_time = now
    carrier._go_at_him = False
    return True


_SHIELD_MAX = 2.5          # s of shielding before he forces something


def _escape_pass(carrier, mates, opponents):
    """Any teammate with a reasonably open lane, nearest first (backwards is fine)."""
    import ai.spot_value as spot_value
    from ai.team_shape import to_frame
    tid = carrier.team
    ca, cl = to_frame(tid, carrier.pos)
    opps = [to_frame(tid, o.pos) for o in opponents if getattr(o, "is_active", True)]
    for m in sorted(mates, key=lambda m: distance(m.pos, carrier.pos)):
        d = distance(m.pos, carrier.pos) / M_TO_PX
        if d < 3.0 or d > 35.0:
            continue
        ma, ml = to_frame(tid, m.pos)
        lane, _ = spot_value.lane_and_time(ma, ml, ca, cl, opps)
        if lane >= 0.3:
            return m
    return None


def _escape_space(carrier, opponents):
    """Turn away from the men on him, towards the middle of the pitch."""
    away = Vector2()
    for o in opponents:
        rel = carrier.pos - o.pos
        d = rel.length()
        if 0 < d < 6.0 * M_TO_PX:
            away += rel / d * (6.0 * M_TO_PX - d)
    centre = Vector2(WIDTH / 2, HEIGHT / 2) - carrier.pos
    if centre.length_squared() > 0:
        away += centre.normalize() * (2.0 * M_TO_PX)
    if away.length_squared() == 0:
        away = Vector2(1, 0)
    target = carrier.pos + away.normalize() * (4.0 * M_TO_PX)
    target.x = clamp(target.x, 0, WIDTH)
    target.y = clamp(target.y, 0, HEIGHT)
    return target


def _fancies_it(carrier, opponents, now):
    """The defender in front of him (if any): does he want to take him on? (gameplay/duels.py)"""
    import gameplay.duels as duels
    ahead_m, close_m, dirg = _space_ahead(carrier, opponents)
    front = [o for o in opponents if getattr(o, "is_active", True)
             and (o.pos - carrier.pos).dot(dirg) > 0 and distance(o.pos, carrier.pos) < 6.0 * M_TO_PX]
    if not front:
        return True
    d = min(front, key=lambda o: distance(o.pos, carrier.pos))
    return duels.wants_take_on(carrier, d, opponents, now)
