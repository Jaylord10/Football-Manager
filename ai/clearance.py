"""
ai/clearance.py
===============
Clearing it: getting rid of the ball when it isn't safe to keep it.

Before this an outfield player never cleared the ball.  In his own six-yard
box with two strikers on him he still looked for a pass, and only the keeper
ever kicked it long.

WHEN he clears
--------------
  - Where he is: in his own defensive third - most of all in or around his
    own box.
  - How much danger he's in: someone on him (or about to be), facing his own
    goal, or the last man with nobody covering.
  - Whether he has a safe pass: if a team-mate (or the keeper) is free he's
    more likely to keep it.
  - Who he is: low Composure / Decisions clear earlier, a calm technical
    defender plays out; centre-backs clear most, strikers least.
  - The team instruction (match_config.json "tactics": {"build_up": ...}):
        "play_out"  - Play Out Of Defence: keep it unless it's really on fire
        "mixed"     - the default
        "clear"     - Clear Ball To Flanks: get it away early, out wide
  - FIRST TIME: a loose ball, rebound or low cross reaching a defender in his
    own box with attackers around isn't controlled first - it's hit away.

WHERE it goes (he picks one)
----------------------------
  - UP AND AWAY: high and long (~35-55 m), into the wide channels or towards
    a forward, never back across his own goal.  Then it's a fight for it.
  - INTO TOUCH: under pressure near the touchline - out for a throw.
  - BEHIND: last resort on his own byline, facing his own goal with a man on
    him - out for a corner.

HOW WELL it's hit
-----------------
A clearance is not a pass: the direction can be well off (more so with poor
Passing, under pressure or first time), and some are SLICED - off the side
of the foot, flying off at an angle at less pace (more with poor Control).
Plenty of those end up out of play on their own.  Distance comes from
Strength.  An attacker right on him can charge it down (gameplay/ricochet.py).

All tuning numbers are in the TUNING block.
"""

import math
import random
from pygame.math import Vector2
from config.constants import M_TO_PX, WIDTH, HEIGHT, GOAL_WIDTH

# ---------------------------------------------------------------------------
# TUNING  (metres, m/s, degrees, seconds)
# ---------------------------------------------------------------------------
PITCH_L, HALF_W = 110.0, 35.0
BOX_DEPTH, BOX_HALF = 16.5, 20.16

# When: chance per decision he clears it rather than playing
ZONE = ((BOX_DEPTH, 0.50), (25.0, 0.25), (36.0, 0.10))   # (m from own goal line, base chance)
PRESSURE_MULT = (1.0, 0.45, 0.10)   # x: someone on him / an opponent within NEAR / within FAR
NEAR          = 6.0                 # m
FAR           = 12.0                # m: nobody this close - no reason to clear it at all
FACING_OWN_GOAL = 0.15              # + if he's facing his own goal
LAST_MAN      = 0.10                # + if nobody (but the keeper) is behind him
CALM_PER_POINT = 0.025              # - per point of (Composure + Decisions)/2 over 10
SAFE_PASS_MULT = 0.45               # x if he has a safe pass on
SAFE_SPACE    = 6.0                 # m: a team-mate with this much room is a safe pass
BUILD_UP_MULT = {"play_out": 0.5, "mixed": 1.0, "clear": 1.6}
ROLE_MULT     = {"LCB": 1.2, "RCB": 1.2, "CB": 1.2, "LB": 1.0, "RB": 1.0,
                 "LCM": 0.7, "RCM": 0.7, "CM": 0.7, "DM": 0.8, "LM": 0.55, "RM": 0.55,
                 "ST1": 0.4, "ST2": 0.4, "ST": 0.4}
P_MAX         = 0.9

# First time: a loose ball / rebound / their cross arriving in his zone
FIRST_TIME_ZONE = ((BOX_DEPTH, 0.55), (25.0, 0.25))
FIRST_TIME_NEAR = 4.0               # m: needs an attacker this close (or closing)
FIRST_TIME_FAST = 1.3               # x if it's arriving fast (> 12 m/s) or in the air

# Which kind
BEHIND_LINE   = 8.0                 # m from his own byline...
BEHIND_WIDE   = 6.0                 # ...and at least this far off centre: he can put it behind
BEHIND_CHANCE = 0.55                # chance he does, if facing his own goal with a man on him
TOUCH_LINE    = 18.0                # m from the touchline: he can put it out for a throw...
TOUCH_CHANCE  = 0.40                # ...this often under pressure (+ TOUCH_FACING if facing it)
TOUCH_FACING  = 0.20
PRESSED       = 4.5                 # m: an opponent this close and he'll happily put it out
FLANK_SHARE   = {"play_out": 0.5, "mixed": 0.6, "clear": 0.85}  # up-and-away: to a flank, else to a forward

# How it's hit
SPEED         = (17.0, 0.5)         # m/s along the ground: base + per Strength point (13 -> 23.5)
SPEED_SPREAD  = 0.10
FLIGHT        = (2.0, 2.8)          # s in the air for an up-and-away clearance
ANGLE_SD      = (6.0, 0.6)          # degrees: base + per Passing point below 20 (13 -> 10 deg)
PRESSURE_ERROR = 1.5                # x under pressure
FIRST_TIME_ERROR = 1.3              # x first time
SLICE         = (0.05, 0.015)       # chance he slices it: base + per Control point below 20 (13 -> 15%)
SLICE_TURN    = (25.0, 70.0)        # degrees off
SLICE_SPEED   = 0.70                # x pace
SETUP         = (0.30, 0.15)        # s to set himself (worst, best Passing); first time: none


def _stat(p, name):
    v = p.attributes.get(name, 10)
    if v > 25:
        v /= 5.0
    return max(1.0, min(20.0, v))


def _frame(p, v):
    from ai.team_shape import to_frame
    return to_frame(p.team, v)


def build_up(team_id):
    import ai.tactics as tactics
    return tactics.build_up(team_id)


def _zone_chance(a, l, table):
    in_box = a < BOX_DEPTH and abs(l) < BOX_HALF
    for depth, chance in table:
        if depth == BOX_DEPTH:
            if in_box:
                return chance
            continue
        if a < depth:
            return chance
    return 0.0


def _own_goal(p):
    return Vector2(0.0, HEIGHT / 2) if p.team == 0 else Vector2(float(WIDTH), HEIGHT / 2)


def _facing_own_goal(p):
    if p.facing.length_squared() == 0:
        return False
    to_goal = _own_goal(p) - p.pos
    return to_goal.length_squared() > 0 and p.facing.normalize().dot(to_goal.normalize()) > 0.5


def _calm(p):
    return 0.5 * (_stat(p, "Composure") + _stat(p, "Decisions")) - 10.0


def _nearest(p, opponents):
    return min(((o.pos - p.pos).length() / M_TO_PX for o in opponents
                if o.role != "GK" and getattr(o, "is_active", True)), default=99.0)


def _last_man(p, teammates):
    a, _ = _frame(p, p.pos)
    return not any(_frame(m, m.pos)[0] < a - 2.0 for m in teammates
                   if m is not p and m.role != "GK" and getattr(m, "is_active", True))


def _safe_pass(p, teammates, opponents):
    try:
        import ai.recycle as recycle
        action, target, score = recycle.evaluate_recycle_layer(p, teammates, opponents)
    except Exception:
        return False
    return action == "pass" and target is not None and score >= SAFE_SPACE


def wants_to_clear(p, teammates, opponents, real_pressure):
    """Rolled once per decision: does he get rid of it?"""
    a, l = _frame(p, p.pos)
    base = _zone_chance(a, l, ZONE)
    if base <= 0.0:
        return False
    near = _nearest(p, opponents)
    if near > FAR and not real_pressure:
        return False
    mult = PRESSURE_MULT[0] if real_pressure else PRESSURE_MULT[1] if near < NEAR else PRESSURE_MULT[2]
    chance = base * mult
    if _facing_own_goal(p):
        chance += FACING_OWN_GOAL * mult
    if _last_man(p, teammates):
        chance += LAST_MAN * mult
    chance -= CALM_PER_POINT * _calm(p)
    chance *= BUILD_UP_MULT.get(build_up(p.team), 1.0) * ROLE_MULT.get(p.role, 0.8)
    if chance <= 0.0:
        return False
    if _safe_pass(p, teammates, opponents):
        chance *= SAFE_PASS_MULT
    return random.random() < min(P_MAX, chance)


def wants_first_time(p, ball, opponents):
    """He's just got to a ball that came from them (or off someone): hit it first time?"""
    from gameplay.ricochet import is_ricochet
    from_them = getattr(ball, "last_kick_team", p.team) != p.team
    if not (from_them or is_ricochet(ball)):
        return False
    a, l = _frame(p, p.pos)
    base = _zone_chance(a, l, FIRST_TIME_ZONE)
    if base <= 0.0 or _nearest(p, opponents) > FIRST_TIME_NEAR:
        return False
    chance = base - CALM_PER_POINT * _calm(p)
    if getattr(ball, "_arrival_speed", 0.0) > 12.0 or getattr(ball, "_arrival_z", 0.0) > 0.5:
        chance *= FIRST_TIME_FAST
    chance *= BUILD_UP_MULT.get(build_up(p.team), 1.0) * ROLE_MULT.get(p.role, 0.8)
    return random.random() < min(P_MAX, max(0.0, chance))


def plan(p, teammates, opponents, real_pressure):
    """(kind, aim point in world px)."""
    a, l = _frame(p, p.pos)
    side = 1.0 if l >= 0 else -1.0                         # his side of the pitch (frame)
    near = _nearest(p, opponents)
    pressured = real_pressure or near < PRESSED
    # Behind for a corner: on his own byline, facing his goal, a man on him
    if a < BEHIND_LINE and abs(l) > BEHIND_WIDE and pressured and _facing_own_goal(p) \
            and random.random() < BEHIND_CHANCE:
        y_l = side * random.uniform(abs(l), HALF_W)
        return "behind", _world(p, -3.0, y_l)
    # Into touch for a throw
    to_touch = HALF_W - abs(l)
    if to_touch < TOUCH_LINE and pressured:
        f = p.facing.normalize() if p.facing.length_squared() > 0 else Vector2()
        facing_touch = _frame_dir(p, f)[1] * side > 0.6
        if random.random() < TOUCH_CHANCE + (TOUCH_FACING if facing_touch else 0.0):
            return "touch", _world(p, a + random.uniform(5.0, 20.0), side * (HALF_W + 4.0))
    # Up and away
    dist = random.uniform(35.0, 55.0)
    if random.random() < FLANK_SHARE.get(build_up(p.team), 0.6):
        tl = side * random.uniform(18.0, 30.0)
        ta = a + math.sqrt(max(dist * dist - (tl - l) ** 2, 400.0))
        return "away", _world(p, ta, tl)
    fwd = [m for m in teammates if m.role != "GK" and getattr(m, "is_active", True)]
    if fwd:
        best = max(fwd, key=lambda m: _frame(m, m.pos)[0])
        ba, bl = _frame(best, best.pos)
        if ba > a + 25.0:
            return "away", _world(p, min(ba + 5.0, a + 60.0), bl)
    return "away", _world(p, a + dist, l * 0.5 + side * 8.0)


def _world(p, a, l):
    """Frame (m) -> world (px), NOT clamped to the pitch (a clearance can go out)."""
    if p.team == 0:
        return Vector2(a * M_TO_PX, (l + HALF_W) * M_TO_PX)
    return Vector2((PITCH_L - a) * M_TO_PX, (HALF_W - l) * M_TO_PX)


def _frame_dir(p, v):
    return (v.x, v.y) if p.team == 0 else (-v.x, -v.y)


def setup_time(p):
    lo, hi = SETUP
    return lo + (hi - lo) * (_stat(p, "Passing") - 1.0) / 19.0


def execute(p, ball, now, kind, aim, pressured=False, first_time=False):
    """Strike the clearance."""
    to_aim = aim - p.pos
    if to_aim.length_squared() < 1.0:
        to_aim = _world(p, 60.0, 0.0) - p.pos
    sd = (ANGLE_SD[0] + ANGLE_SD[1] * (20.0 - _stat(p, "Passing")))
    sd *= (PRESSURE_ERROR if pressured else 1.0) * (FIRST_TIME_ERROR if first_time else 1.0)
    direction = to_aim.normalize().rotate(random.gauss(0.0, sd))
    speed = (SPEED[0] + SPEED[1] * _stat(p, "Strength")) * random.uniform(1 - SPEED_SPREAD, 1 + SPEED_SPREAD)
    p_slice = (SLICE[0] + SLICE[1] * (20.0 - _stat(p, "Control"))) * (PRESSURE_ERROR if pressured else 1.0)
    sliced = random.random() < p_slice
    if sliced:
        direction = direction.rotate(random.uniform(*SLICE_TURN) * random.choice((-1.0, 1.0)))
        speed *= SLICE_SPEED
    if kind == "away":
        flight = random.uniform(*FLIGHT) * (0.7 if sliced else 1.0)
        vz = 0.5 * 9.8 * flight                               # m/s up: lands after `flight` s
    else:
        speed = min(speed, 20.0)                              # into touch / behind: no need to welly it
        vz = random.uniform(1.0, 5.0)
    elevation = vz / (speed * 0.8)                            # Ball.kick sets vz = speed * elevation * 0.8
    p.state = "clear"
    ball.kick(direction * speed * M_TO_PX, kicker=p, elevation=elevation)
    ball.last_kick_time = now
    ball.intended_target = None
    ball.last_clearance = {"team": p.team, "time": now, "kind": kind, "player": p, "sliced": sliced,
                           "first_time": first_time}
    p.has_ball = False
    STATS[kind] += 1
    STATS["team%d" % p.team] += 1
    STATS["first_time" if first_time else "decided"] += 1
    if sliced:
        STATS["sliced"] += 1
    return p.team


from collections import Counter as _Counter
STATS = _Counter()      # read by sim.py
