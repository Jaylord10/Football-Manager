"""
ai/box_marking.py
=================
Picking up runners in the box.

Before this, when the other side had the ball out wide near our box, our
defenders simply held their places in the shape.  Strikers and midfielders
arriving in the box were nobody's job - so a cross usually found a free man
(about two thirds found a team-mate, against about a quarter in real
football).

Now, when they have it wide in our final third (a cross is on), the
defenders pick up the men in and arriving at our box:
  - the most dangerous first (closest to goal), each by the nearest
    defender who isn't the one closing down the ball;
  - he takes up a goal-side position on his man - between him and the goal,
    a little towards the ball - how tight from his Marking and Defensive
    Positioning (a good marker ~1 m off him, a poor one ~2 m and he loses
    him more);
  - up to four markers; the rest keep their shape.

(When the cross comes in, gameplay/aerial.py takes over: the men nearest
where it's coming down go for it.)

All tuning numbers are in the TUNING block.
"""

from pygame.math import Vector2
from config.constants import M_TO_PX, WIDTH, HEIGHT
import core.clock as clock

# ---------------------------------------------------------------------------
# TUNING  (metres)
# ---------------------------------------------------------------------------
BALL_A        = 72.0           # their man on the ball this far up (their frame)...
BALL_WIDE     = 12.0           # ...and out wide - or...
BALL_BYLINE   = 95.0           # ...this close to our byline: a cross is on
RUNNER_A      = 86.0           # their men this far up (their frame)...
RUNNER_L      = 20.0           # ...and inside this - in or arriving at the box - get marked
MAX_MARKERS   = 4
MARKER_RANGE  = 18.0           # m: a defender further than this from the man doesn't pick him up
TIGHT         = (1.5, 0.6)     # m off his man, goal-side (worst, best Marking + Def. Positioning)
BALL_SIDE     = 0.5            # m he shades towards the ball
SPRINT_FROM   = 3.0            # m from his spot: further than this he runs to get there...
RUNNER_RUNNING = 4.0           # m/s: ...and if his man is running, he runs with him
MARKING_MEMORY = 1.0           # s: he's still "on" his man this long after he last checked


def _stat(p, name):
    v = p.attributes.get(name, 10)
    if v > 25:
        v /= 5.0
    return max(1.0, min(20.0, v))


def update(team, opponents, ball, presser=None):
    """Called for the team WITHOUT the ball, after pressing."""
    owner = ball.owner
    if owner is None or owner.team == (team[0].team if team else -1) or ball.is_dead:
        return
    from ai.team_shape import to_frame
    a, l = to_frame(owner.team, owner.pos)
    if not ((a >= BALL_A and abs(l) >= BALL_WIDE) or a >= BALL_BYLINE):
        return
    my_team = team[0].team
    goal = Vector2(0.0, HEIGHT / 2) if my_team == 0 else Vector2(float(WIDTH), HEIGHT / 2)
    runners = []
    for o in opponents:
        if o is owner or o.role == "GK" or not getattr(o, "is_active", True):
            continue
        oa, ol = to_frame(o.team, o.pos)
        if oa >= RUNNER_A and abs(ol) <= RUNNER_L:
            runners.append(((o.pos - goal).length(), o))
    if not runners:
        return
    runners.sort(key=lambda r: r[0])
    free = [p for p in team if p.role != "GK" and p is not presser and getattr(p, "is_active", True)
            and p.state != "intercept" and not p.has_ball]
    for _, runner in runners[:MAX_MARKERS]:
        if not free:
            break
        marker = min(free, key=lambda p: (p.pos - runner.pos).length())
        if (marker.pos - runner.pos).length() > MARKER_RANGE * M_TO_PX:
            continue
        free.remove(marker)
        q = (0.5 * (_stat(marker, "Marking") + _stat(marker, "Defensive Positioning")) - 1.0) / 19.0
        tight = TIGHT[0] + (TIGHT[1] - TIGHT[0]) * q
        to_goal = goal - runner.pos
        if to_goal.length_squared() < 1.0:
            continue
        spot = runner.pos + to_goal.normalize() * (tight * M_TO_PX)
        to_ball = owner.pos - spot
        if to_ball.length_squared() > 1.0:
            spot += to_ball.normalize() * (BALL_SIDE * M_TO_PX)
        marker.target = spot
        far = (marker.pos - spot).length() > SPRINT_FROM * M_TO_PX
        running = runner.vel.length() > RUNNER_RUNNING * M_TO_PX
        marker.state = "run" if (far or running) else "defend"     # he goes with him when he runs
        marker.pos_reason = "mark his man in the box"
        marker._marking = runner
        marker._marking_t = clock.now()


def marker_of(player, team, now):
    """The defender in `team` who has been marking `player` (or None)."""
    for p in team:
        if getattr(p, "_marking", None) is player and now - getattr(p, "_marking_t", -99.0) < MARKING_MEMORY:
            return p
    return None
