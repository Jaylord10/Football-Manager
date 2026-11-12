"""
ai/run_planner.py
=================
Off-the-ball runs for the team in possession.

Your role files decide where each player normally stands.  This planner sits
on top: a few times a second it looks for a chance to make a RUN - mainly
in behind the defence - and gives one or two players a run to make.

When does a run happen?
  * Only when the ball carrier can actually play it: he has the ball, he's
    not under pressure and he's facing roughly forward.
  * Only for players whose role likes making that kind of run
    (roles/library.py -> Role.runs), weighted by Off The Ball and
    Anticipation.

Where to?
  * In behind: the gaps between (and outside) the opposition back line,
    a few metres beyond the offside line.  Scored on:
        - space at the target (distance to the nearest defender)
        - the race: can he get there before any defender?  Runs that start
          on a defender's blind side (behind his back) get a head start.
        - danger: how close the target is to goal
        - whether the carrier could reach it with a pass
  * Into the box: near post / far post / penalty spot when the ball is out
    wide in the final third (for crosses).

How?
  * If he's offside, he first drifts back onside.
  * If the gap is well across from him, he bends his run along the offside
    line first, then turns in behind - the classic diagonal run.  Because
    players can't turn sharply at speed (core/locomotion.py) this produces a
    natural curved run.
  * The through-ball planner (gameplay/through_pass.py) then decides whether
    to find him.

At most MAX_RUNS players run at once, and runs aim for different spaces.
All tuning numbers are in the TUNING block.
"""

import core.fatigue as fatigue
import random
from collections import Counter
from pygame.math import Vector2
from config.constants import WIDTH, HEIGHT, M_TO_PX
from core.utils import distance, clamp
import core.locomotion as locomotion
import roles.library as role_library

# ---------------------------------------------------------------------------
# TUNING (metres, seconds)
# ---------------------------------------------------------------------------
PLAN_INTERVAL      = 0.25    # s between planning passes (per team)
MAX_RUNS           = 2       # runners at the same time
NEW_RUN_GAP        = 1.2     # s between starting runs (per team)
PLAYER_COOLDOWN    = 3.0     # s rest for a player after a run
RUN_TIMEOUT        = 4.0     # s a run lasts at most
MIN_STAMINA        = 0.30    # too gassed / worn out to make a run below this

CARRIER_PRESSURE   = 2.5     # m: an opponent this close = carrier can't look up
CARRIER_MIN_FACING = -0.2    # carrier facing . attacking direction (> -0.2 = not facing own goal)
MAX_PASS_RANGE     = 40.0    # m: target must be within this of the carrier

BEHIND_DEPTH       = (7.0, 13.0)   # m beyond the offside line
GOAL_LINE_ROOM     = 7.0     # m: targets stay this far from the goal line
TOUCHLINE_ROOM     = 4.0     # m
MIN_GAP            = 6.0     # m: narrower gaps aren't worth attacking
BACK_LINE_DEPTH    = 12.0    # m: defenders within this of the deepest one form the line
ONSIDE_BUFFER      = 1.2     # m: hold position this far onside
BEND_LATERAL       = 8.0     # m: if the gap is further across than this, bend along the line first
DEF_SPEED          = 6.5     # m/s
DEF_REACTION       = 0.30    # s
BLIND_SIDE_BONUS   = 0.35    # s extra reaction for a defender the run starts behind
SEPARATION         = 12.0    # m: two runs shouldn't target spaces closer than this

THRESHOLD          = 0.62    # score needed to start a run
DECISION_NOISE     = 0.12    # random noise on scores for a Decisions-1 player (none at 20)

# Default run preferences by position (0 = never, 1 = loves it).
# Roles can override these in roles/library.py (Role.runs).
DEFAULT_RUNS = {
    "ST1": {"in_behind": 1.0, "box": 1.0},
    "ST2": {"in_behind": 1.0, "box": 1.0},
    "LM":  {"in_behind": 0.7, "box": 0.6},
    "RM":  {"in_behind": 0.7, "box": 0.6},
    "LCM": {"in_behind": 0.25, "box": 0.45},
    "RCM": {"in_behind": 0.25, "box": 0.45},
    "LB":  {"in_behind": 0.2, "box": 0.0},
    "RB":  {"in_behind": 0.2, "box": 0.0},
}


RUN_LABELS = {"in_behind": "run in behind", "box": "run into box",
              "overlap": "overlap", "underlap": "underlap",
              "beyond": "run beyond the striker", "third_man": "third-man run"}

# Counters for sim.py: ("started", kind), ("targeted", kind), ("received", kind)
STATS = Counter()


def _stat(p, name, default=10):
    v = p.attributes.get(name, default)
    if v > 25:
        v /= 5.0
    return clamp(v, 1, 20)


def _attack_sign(team_id):
    return 1.0 if team_id == 0 else -1.0


def _offside_line_x(attack_sign, opponents):
    """x of the second-last opponent (keeper included) - the offside line."""
    xs = sorted((o.pos.x for o in opponents), reverse=(attack_sign > 0))
    if len(xs) >= 2:
        return xs[1]
    return xs[0] if xs else (WIDTH / 2)


# Spots outside the 4-4-2 (config/slots.py): a number 10 and a winger in the
# attacking-midfield row are a lone striker's support - they get forward
# whatever their role (the role can only add to it)
SLOT_RUNS = {"AM": {"in_behind": 0.6, "box": 1.0}, "W": {"in_behind": 1.0, "box": 0.9}}
GENERIC_MAX_RUNS = 3     # one up front: more men break from deeper


def _run_prefs(player):
    role = role_library.role_for(player)
    prefs = dict(DEFAULT_RUNS.get(player.role, {}))
    if getattr(role, "runs", None):
        prefs.update(role.runs)
    extra = SLOT_RUNS.get(_slot_kind(player))
    if extra:
        for k, v in extra.items():
            prefs[k] = max(prefs.get(k, 0.0), v)
    return prefs


def _slot_kind(player):
    slot = getattr(player, "slot", None)
    if slot is None or slot == player.role:
        return None
    from config import slots as slots_mod
    return slots_mod.kind(slot)


def _max_runs(team):
    try:
        import config.formations as formations
        return GENERIC_MAX_RUNS if formations.formation_slots(team[0].team) else MAX_RUNS
    except Exception:
        return MAX_RUNS


# ---------------------------------------------------------------------------
# Entry point (called every frame for the team in possession)
# ---------------------------------------------------------------------------
def update(state, team, opponents, ball, current_time):
    """
    state: a dict kept per team by the decision maker.
    """
    carrier = ball.owner if (ball.owner is not None and ball.owner in team) else None
    runs = state.setdefault("runs", {})

    _execute_runs(runs, team, opponents, ball, carrier, current_time)
    _stay_onside(team, opponents, ball, carrier, runs)

    if carrier is None or carrier.role == "GK":
        return
    if current_time < state.get("next_plan", 0.0):
        return
    state["next_plan"] = current_time + PLAN_INTERVAL
    if len(runs) >= _max_runs(team) or current_time < state.get("next_new_run", 0.0):
        return
    if not _carrier_can_play(carrier, opponents):
        return

    best = _best_new_run(team, opponents, carrier, runs, current_time)
    if best is not None:
        player, run = best
        runs[id(player)] = run
        player._planned_run = run
        STATS[("started", run["kind"])] += 1
        state["next_new_run"] = current_time + NEW_RUN_GAP
        state["started"] = state.get("started", 0) + 1


def _stay_onside(team, opponents, ball, carrier, runs):
    """Attackers not on a run drift back onside instead of loitering offside."""
    if not team or not opponents:
        return
    sign = _attack_sign(team[0].team)
    onside_x = _offside_line_x(sign, opponents) - sign * ONSIDE_BUFFER * M_TO_PX
    ball_x = ball.pos.x
    for p in team:
        if p is carrier or p.role == "GK" or id(p) in runs:
            continue
        if getattr(ball, "intended_target", None) is p:
            continue
        # The ball itself is an onside reference: being behind the ball is fine
        limit = onside_x if (onside_x - ball_x) * sign > 0 else ball_x
        if (p.target.x - limit) * sign > 0:
            p.target = Vector2(limit, p.target.y)
            p.pos_reason = getattr(p, "pos_reason", "") .split(" +")[0] + " + stay onside"


def _carrier_can_play(carrier, opponents):
    sign = _attack_sign(carrier.team)
    if carrier.facing.x * sign < CARRIER_MIN_FACING:
        return False
    nearest = min((distance(carrier.pos, o.pos) for o in opponents if o.role != "GK"),
                  default=999.0) / M_TO_PX
    return nearest > CARRIER_PRESSURE


# ---------------------------------------------------------------------------
# Choosing a run
# ---------------------------------------------------------------------------
def _best_new_run(team, opponents, carrier, runs, now):
    sign = _attack_sign(carrier.team)
    line_x = _offside_line_x(sign, opponents)
    targets_taken = [r["target"] for r in runs.values()]
    candidates = []

    for p in team:
        if p is carrier or p.role == "GK" or id(p) in runs:
            continue
        if now < getattr(p, "_run_cooldown_until", 0.0) or fatigue.condition(p) < MIN_STAMINA:
            continue
        prefs = _run_prefs(p)
        if not any(prefs.values()):
            continue
        for kind, target, extra in _candidate_targets(p, carrier, opponents, line_x, sign, prefs):
            if any(distance(target, t) < SEPARATION * M_TO_PX for t in targets_taken):
                continue
            score = _score(p, carrier, target, opponents, sign, prefs[kind], extra)
            if score is not None:
                candidates.append((score, p, kind, target))

    if not candidates:
        return None
    score, p, kind, target = max(candidates, key=lambda c: c[0])
    if score < THRESHOLD:
        return None
    return p, _make_run(p, kind, target, line_x, sign, now)


def _candidate_targets(p, carrier, opponents, line_x, sign, prefs):
    goal_x = WIDTH if sign > 0 else 0.0
    out = []

    # --- In behind: gaps in the back line ---
    if prefs.get("in_behind", 0) > 0:
        field = [o for o in opponents if o.role != "GK"]
        if field:
            deepest = max(field, key=lambda o: o.pos.x * sign)
            line = [o for o in field
                    if (deepest.pos.x - o.pos.x) * sign < BACK_LINE_DEPTH * M_TO_PX]
            ys = sorted(o.pos.y for o in line)
            edges = [TOUCHLINE_ROOM * M_TO_PX] + ys + [HEIGHT - TOUCHLINE_ROOM * M_TO_PX]
            room_to_goal = abs(goal_x - line_x) / M_TO_PX - GOAL_LINE_ROOM
            if room_to_goal > BEHIND_DEPTH[0]:
                depth = min(BEHIND_DEPTH[1], room_to_goal)
                for a, b in zip(edges, edges[1:]):
                    if (b - a) / M_TO_PX < MIN_GAP:
                        continue
                    gy = (a + b) / 2
                    target = Vector2(line_x + sign * depth * M_TO_PX, gy)
                    out.append(("in_behind", target, {"gap_m": (b - a) / M_TO_PX}))

    # --- Into the box: ball out wide in the final third ---
    if prefs.get("box", 0) > 0:
        wide = abs(carrier.pos.y - HEIGHT / 2) > 15 * M_TO_PX
        final_third = abs(goal_x - carrier.pos.x) < 35 * M_TO_PX
        if wide and final_third:
            ball_side = 1.0 if carrier.pos.y > HEIGHT / 2 else -1.0
            spots = [
                Vector2(goal_x - sign * 6 * M_TO_PX, HEIGHT / 2 + ball_side * 4 * M_TO_PX),   # near post
                Vector2(goal_x - sign * 7 * M_TO_PX, HEIGHT / 2 - ball_side * 5 * M_TO_PX),   # far post
                Vector2(goal_x - sign * 11 * M_TO_PX, HEIGHT / 2),                             # penalty spot
            ]
            for s in spots:
                out.append(("box", s, {}))
    return out


def _score(p, carrier, target, opponents, sign, preference, extra):
    # Pass must be possible
    pass_m = distance(carrier.pos, target) / M_TO_PX
    if pass_m > MAX_PASS_RANGE:
        return None

    # Race: runner vs every defender
    run_speed = locomotion.top_speed_ms(p) * 0.9
    t_runner = 0.3 + distance(p.pos, target) / M_TO_PX / run_speed
    t_def = 99.0
    space = 99.0
    blind = 0.0
    for o in opponents:
        d_m = distance(o.pos, target) / M_TO_PX
        space = min(space, d_m)
        reaction = DEF_REACTION
        # Blind side: the runner starts behind the defender's back
        to_runner = p.pos - o.pos
        if to_runner.length() < 15 * M_TO_PX and o.facing.dot(to_runner) < 0:
            reaction += BLIND_SIDE_BONUS
            blind = 1.0
        t_def = min(t_def, reaction + d_m / (7.0 if o.role == "GK" else DEF_SPEED))
    margin = t_def - t_runner
    if margin < -0.2:
        return None

    goal = Vector2(WIDTH if sign > 0 else 0.0, HEIGHT / 2)
    danger = max(0.0, 1.0 - distance(target, goal) / M_TO_PX / 40.0)

    otb = _stat(p, "Off The Ball")
    anticip = _stat(p, "Anticipation")
    decisions = _stat(p, "Decisions")

    score = (0.40 * danger
             + 0.25 * clamp(margin + 0.2, 0.0, 1.5) / 1.5
             + 0.15 * min(space, 10.0) / 10.0
             + 0.10 * blind
             + 0.20 * (otb + anticip) / 40.0)
    score *= 0.4 + 0.6 * preference
    score *= 0.85 + 0.15 * fatigue.condition(p)     # tired legs make slightly fewer runs
    score += random.gauss(0.0, DECISION_NOISE * (1.0 - decisions / 20.0))
    return score


def _make_run(p, kind, target, line_x, sign, now):
    waypoints = []
    if kind == "in_behind":
        onside_x = line_x - sign * ONSIDE_BUFFER * M_TO_PX
        lateral_m = abs(target.y - p.pos.y) / M_TO_PX
        # Bend along the line first when the gap is well across (diagonal run)
        if lateral_m > BEND_LATERAL:
            bend_y = p.pos.y + (target.y - p.pos.y) * 0.6
            waypoints.append(Vector2(onside_x, bend_y))
        elif (p.pos.x - onside_x) * sign > 0:
            # Currently offside: drift back onside first
            waypoints.append(Vector2(onside_x, p.pos.y))
    waypoints.append(Vector2(target))
    return {"kind": kind, "target": Vector2(target), "waypoints": waypoints,
            "start": now, "player": p, "received": False}


# ---------------------------------------------------------------------------
# Carrying out runs
# ---------------------------------------------------------------------------
def _execute_runs(runs, team, opponents, ball, carrier, now):
    sign = _attack_sign(team[0].team) if team else 1.0
    line_x = _offside_line_x(sign, opponents) if opponents else WIDTH / 2
    for key in list(runs.keys()):
        run = runs[key]
        p = run["player"]

        # End the run?
        finished = (
            p not in team
            or now - run["start"] > RUN_TIMEOUT
            or p.has_ball
            or ball.owner is not None and ball.owner not in team      # lost the ball
        )
        # Combination runs (ai/combos.py) only make sense while their partner
        # still has the ball, or it's on its way to this runner
        partners = run.get("partners")
        if partners and not finished:
            aimed = getattr(ball, "intended_target", None)
            if ball.owner is not None and ball.owner not in partners and not p.has_ball:
                finished = True
            elif (ball.owner is None and aimed is not p and aimed not in partners
                  and run.get("partners_must_hold", True)):
                finished = True
        if p.has_ball:
            run["received"] = True
        if finished:
            _end(runs, key, p, now)
            continue

        # A pass is on its way to him: let the receiving logic take over
        if getattr(ball, "intended_target", None) is p and ball.owner is None:
            run["targeted"] = True
            continue

        # Next waypoint
        while len(run["waypoints"]) > 1 and distance(p.pos, run["waypoints"][0]) < 2.0 * M_TO_PX:
            run["waypoints"].pop(0)
        wp = run["waypoints"][0]
        if len(run["waypoints"]) == 1 and distance(p.pos, wp) < 1.5 * M_TO_PX:
            _end(runs, key, p, now)
            continue

        # While bending along the line, don't drift offside: keep the
        # waypoint's x tracking the (moving) offside line.
        if len(run["waypoints"]) > 1 and run["kind"] == "in_behind":
            wp = Vector2(line_x - sign * ONSIDE_BUFFER * M_TO_PX, wp.y)
        elif run["kind"] not in ("in_behind",):
            # Combination runs stay onside until the ball is played
            onside_x = line_x - sign * ONSIDE_BUFFER * M_TO_PX
            if (wp.x - onside_x) * sign > 0 and (ball.pos.x - onside_x) * sign < 0:
                wp = Vector2(onside_x, wp.y)

        p.target = Vector2(wp)
        p.pos_reason = RUN_LABELS.get(run["kind"], run["kind"])
        p.state = "run"
        p.current_run_type = "planned_" + run["kind"]
        p.run_committed_until = now + 0.3     # keep role code from cancelling it


def _end(runs, key, p, now):
    run = runs.pop(key, None)
    if run is not None:
        if run.get("targeted"):
            STATS[("targeted", run["kind"])] += 1
        if run.get("received"):
            STATS[("received", run["kind"])] += 1
    p._run_cooldown_until = now + PLAYER_COOLDOWN
    p._planned_run = None
