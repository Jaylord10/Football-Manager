"""
gameplay/crossing.py
====================
How a cross is STRUCK (the decision to cross lives in ai/decisive.py).

Before this a cross was just a pass along the ground to a team-mate's feet -
lifted only if a defender happened to be in the passing lane, and a corner
never.  So nothing was ever won in the air.

Now a cross (open play, a corner, a free kick swung into the box) is a lofted
ball aimed to come down at head height (~2 m) where the man it's meant for
is going to be:
  - Its pace comes from the distance - whipped, not floated.
  - The Crossing attribute decides how accurate it is: direction, distance
    and height all have an error (bigger under pressure).  A poor crosser
    hits the first man, overhits it or puts it straight to the keeper more.
  - From near the byline, close in, he sometimes pulls it back along the
    ground instead (a cut-back) - that's an ordinary pass.

All tuning numbers are in the TUNING block.
"""

import math
import random
from collections import Counter
from pygame.math import Vector2
from config.constants import M_TO_PX, WIDTH, HEIGHT

# ---------------------------------------------------------------------------
# TUNING  (metres, m/s, degrees)
# ---------------------------------------------------------------------------
SPEED          = (17.0, 0.25)      # m/s along the ground: base + per metre of distance (30 m -> 24.5)
SPEED_MAX      = 28.0
ARRIVE_Z       = (1.6, 2.5)        # m: the height it's meant to come down through at the target
LEAD           = 1.0               # he crosses to where the man's run will take him...
BEHIND_LINE    = (1.5, 4.0)        # ...or, for a man on their line, this far behind it, into the space...
SPACE_MAX_A    = 104.0             # ...but no closer to goal than 6 m (the keeper's)...
REACT          = 0.45              # ...and never further than he can get to in the flight time, less this (s)
ANGLE_SD       = (3.5, 0.45)       # degrees: base + per Crossing point below 20 (13 -> 6.7 deg)
DIST_SD        = (0.05, 0.006)     # share of distance: base + per Crossing point below 20 (13 -> 9%)
HEIGHT_SD      = 0.4               # m
PRESSURE_R     = 2.5               # m: an opponent this close puts him under pressure...
PRESSURE_ERROR = 1.4               # ...this much less accurate
CUT_BACK_LINE  = 8.0               # m from the byline...
CUT_BACK_RANGE = 14.0              # ...to a team-mate this close: he may pull it back along the ground...
CUT_BACK_CHANCE = 0.4              # ...this often

STATS = Counter()                  # read by sim.py

_NLK_AIR = -math.log(0.995 ** 60)  # air friction per second (Ball.update)


def _stat(p, name):
    v = p.attributes.get(name, 10)
    if v > 25:
        v /= 5.0
    return max(1.0, min(20.0, v))


def _flight_time(passer, point):
    d = max(1.0, (point - passer.pos).length() / M_TO_PX)
    v = min(SPEED_MAX, SPEED[0] + SPEED[1] * d)
    v = max(v, d * _NLK_AIR / 0.85)
    return -math.log(1.0 - d * _NLK_AIR / v) / _NLK_AIR


def _aim(passer, receiver, opponents, kind):
    """The spot he crosses to (before his execution error)."""
    import ai.intercepts as intercepts
    t = _flight_time(passer, receiver.pos)
    want = receiver.pos + receiver.vel * (t * LEAD)                 # where his run takes him
    if kind == "cross" and opponents:
        # A man on their line: into the space behind it, for him to attack
        from ai.team_shape import to_frame as _tf, to_world as _tw
        line = max((_tf(passer.team, o.pos)[0] for o in opponents
                    if o.role != "GK" and getattr(o, "is_active", True)), default=0.0)
        wa, wl = _tf(passer.team, want)
        if wa < line + BEHIND_LINE[0]:
            want = _tw(passer.team, min(SPACE_MAX_A, max(wa, line + random.uniform(*BEHIND_LINE))), wl)
    # Can he get there?  If not, bring it back towards him until he can.
    for _ in range(10):
        t = _flight_time(passer, want)
        if intercepts._time_to(receiver, want) <= max(0.3, t - REACT):
            break
        want = receiver.pos + (want - receiver.pos) * 0.8
    return want


def execute_cross(passer, receiver, ball, now, opponents=None, kind="cross"):
    from ai.team_shape import to_frame
    a, _ = to_frame(passer.team, passer.pos)
    to_recv = (receiver.pos - passer.pos).length() / M_TO_PX
    if kind == "cross":
        STATS["open%d" % passer.team] += 1
    if kind == "cross" and 110.0 - a < CUT_BACK_LINE and to_recv < CUT_BACK_RANGE \
            and random.random() < CUT_BACK_CHANCE:
        STATS["cut_back"] += 1
        import gameplay.passing as passing
        return passing.execute_pass(passer, receiver, ball, now, opponents)

    crossing = _stat(passer, "Crossing")
    near = min(((o.pos - passer.pos).length() / M_TO_PX for o in (opponents or [])
                if o.role != "GK" and getattr(o, "is_active", True)), default=99.0)
    err = PRESSURE_ERROR if near < PRESSURE_R else 1.0

    # Where he's putting it: where the man will be - but only as far ahead as
    # he can actually get to by the time it arrives
    target = _aim(passer, receiver, opponents, kind)
    to_t = target - passer.pos
    if to_t.length_squared() < 1.0:
        to_t = Vector2(1.0 if passer.team == 0 else -1.0, 0.0)
    d = to_t.length() / M_TO_PX

    # Execution error
    direction = to_t.normalize().rotate(random.gauss(0.0, (ANGLE_SD[0] + ANGLE_SD[1] * (20 - crossing)) * err))
    d *= max(0.6, random.gauss(1.0, (DIST_SD[0] + DIST_SD[1] * (20 - crossing)) * err))
    z_arrive = max(0.8, random.uniform(*ARRIVE_Z) + random.gauss(0.0, HEIGHT_SD * err))

    v = min(SPEED_MAX, SPEED[0] + SPEED[1] * d)
    v = max(v, d * _NLK_AIR / 0.85)                    # fast enough to get there in the air
    t = -math.log(1.0 - d * _NLK_AIR / v) / _NLK_AIR   # s in the air to the target
    vz = (z_arrive + 0.5 * 9.8 * t * t) / t            # m/s up (from the ground)

    passer.state = "pass"
    ball.kick(direction * v * M_TO_PX, kicker=passer)
    ball.z = 0.0
    ball.vz = vz * M_TO_PX
    ball.last_kick_time = now
    ball.intended_target = receiver
    ball.through_plan = None
    ball.last_owner = passer
    passer.last_pass_time = now
    ball.last_cross = {"team": passer.team, "time": now, "kind": kind, "passer": passer, "receiver": receiver}
    passer.has_ball = False
    STATS[kind] += 1
    return passer.team
