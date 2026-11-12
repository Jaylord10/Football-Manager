"""
ai/intercepts.py
================
Reading a pass and cutting it out.

Before this a defending team simply kept its shape while a pass was on its
way - nobody went for the ball - and a defender only won it if it happened
to roll within a metre of him.  (There was an interception routine in
gameplay/defending.py, but nothing ever called it.)

Now, while a pass is travelling, each defender near its path works out
whether he can get to a point on it before it reaches the man it's meant
for:
  - He has to READ it first: Anticipation decides how long after the pass
    is struck he reacts (~0.15 s for the best, ~0.4 s for the worst).
  - Then it's a race: his pace and acceleration against the ball, and he
    only has to get within his REACH of the ball's line - a stretch, a
    lunge or a slide, 1.0-1.8 m depending on his Agility.
  - The best placed one or two go for it flat out.

Whether he actually wins it once it's in reach is decided in
gameplay/mechanics.py (handle_possession_pickup): a clean interception, or
just a toe on it that knocks it loose.

All tuning numbers are in the TUNING block.
"""

import math
from pygame.math import Vector2
from config.constants import M_TO_PX, GRAVITY

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
READ_DELAY   = (0.40, 0.15)   # s after the pass before he reacts (worst, best Anticipation)
REACH        = (1.0, 1.8)     # m: how far he can stretch / lunge / slide (worst, best Agility)
CONSIDER     = 22.0           # m: defenders this far from the ball's line don't bother
MIN_SPEED    = 4.0            # m/s: slower than this it's a loose ball (gameplay/defending.py)
MAX_HEIGHT   = 1.0            # m: the ball has to be low enough to get a foot to
STEP         = 0.05           # s between the points he checks along the ball's path
LOOKAHEAD    = 2.5            # s
BEFORE_RECEIVER = 0.05        # s: he has to get there at least this much before the receiver
MAX_CHASERS  = 2

_BALL_K_PER_SEC = 0.992 ** 60                     # ground friction (as ai/movement.py)
_BALL_NEG_LOG_K = -math.log(_BALL_K_PER_SEC)


from core.stats import stat20 as _stat    # (cached: attributes never change during a match)


def _lerp(lo_hi, stat):
    lo, hi = lo_hi
    return lo + (hi - lo) * (stat - 1.0) / 19.0


def reach_m(p):
    return _lerp(REACH, _stat(p, "Agility"))


def _time_to(p, point):
    """Seconds for him to get to a point, allowing for getting up to speed."""
    import core.locomotion as locomotion
    to_p = point - p.pos
    d = to_p.length()
    if d < 1e-6:
        return 0.0
    top = locomotion.top_speed_ms(p) * M_TO_PX
    accel = (locomotion.ACCEL_BASE + locomotion.ACCEL_PER_POINT * _stat(p, "Acceleration")) * M_TO_PX * 0.75
    v0 = max(0.0, min(top, p.vel.dot(to_p / d)))
    t_acc = (top - v0) / accel
    d_acc = (v0 + top) * 0.5 * t_acc
    if d <= d_acc:
        return (-v0 + math.sqrt(v0 * v0 + 2.0 * accel * d)) / accel
    return t_acc + (d - d_acc) / top


def _ball_at(ball, t, direction, v):
    travelled = v * (1.0 - _BALL_K_PER_SEC ** t) / _BALL_NEG_LOG_K
    z = ball.z + ball.vz * t - 0.5 * GRAVITY * t * t
    return ball.pos + direction * travelled, max(0.0, z)


def update(team, opponents, ball, now):
    """Called every frame for the team WITHOUT the ball, after pressing."""
    if ball.owner is not None or ball.is_dead:
        return
    receiver = getattr(ball, "intended_target", None)
    if receiver is None or receiver not in opponents:
        return
    v = ball.vel.length()
    if v < MIN_SPEED * M_TO_PX:
        return
    direction = ball.vel / v
    since = now - getattr(ball, "last_kick_time", now)

    # When does the ball get to the receiver?  (where it passes closest to him)
    rel = receiver.pos - ball.pos
    along = max(0.0, rel.dot(direction))
    frac = min(0.999, along * _BALL_NEG_LOG_K / v)
    t_recv = -math.log(1.0 - frac) / _BALL_NEG_LOG_K if frac > 0 else 0.0
    t_recv = min(t_recv, LOOKAHEAD)

    cands = []
    for p in team:
        if p.role == "GK" or p.has_ball or not getattr(p, "is_active", True) \
                or now < getattr(p, "stagger_until", 0.0):
            continue
        if since < _lerp(READ_DELAY, _stat(p, "Anticipation")):
            continue                                   # hasn't read it yet
        rp = p.pos - ball.pos
        side = abs(rp.cross(direction)) / M_TO_PX
        if side > CONSIDER or rp.dot(direction) < -2.0 * M_TO_PX:
            continue                                   # nowhere near its line / already behind it
        reach = reach_m(p) * M_TO_PX
        t = STEP
        while t <= t_recv - BEFORE_RECEIVER:
            pt, z = _ball_at(ball, t, direction, v)
            if z <= MAX_HEIGHT * M_TO_PX:
                gap = (pt - p.pos).length() - reach
                if gap <= 0 or _time_to(p, p.pos + (pt - p.pos) * (gap / max(1e-6, (pt - p.pos).length()))) <= t:
                    cands.append((t, p, pt))
                    break
            t += STEP
    cands.sort(key=lambda c: c[0])
    for t, p, pt in cands[:MAX_CHASERS]:
        p.target = Vector2(pt)
        p.state = "intercept"
        p.pos_reason = "cut out the pass"
