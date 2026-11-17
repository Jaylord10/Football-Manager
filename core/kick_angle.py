"""
core/kick_angle.py
==================
Kicking the ball where you're not facing.

Before this, the man on the ball could pass or shoot in any direction the moment he'd decided - straight
behind him as easily as straight ahead, without turning.

Now:
  1. Within KICK_ARC either side of the way his body faces it's a normal kick (laces, or the inside of the
     foot across his body).
  2. Further round than that he has to TURN first, bringing the ball round with him (a drag-back, a
     half-turn).  That takes time on top of setting the pass / shot (ai/decision_timing.py) - and while he's
     turning, a defender can get to him.  He turns at his normal body-turn speed (core/orientation.py:
     quicker standing than running, quicker for agile players) times TURN_WITH_BALL, because he has the
     ball to bring round too: about 0.4 s for a full about-turn standing still, nearer 0.6 s on the run.
  3. If he still hasn't got round when he strikes it (a first-time ball, or he was hurried), it's an
     awkward one - a back-heel, a hooked flick - and much less accurate (error_mult).

Keepers and dead balls (set pieces, throw-ins, kick-offs - the taker has lined himself up) are left alone.

No published timing for a turn with the ball was found; the turn speeds are the game's own body-turn
speeds (core/orientation.py), with TURN_WITH_BALL set so a standing about-turn with the ball takes ~0.4 s.
"""

import math
from pygame.math import Vector2

from config.constants import M_TO_PX

# ---------------------------------------------------------------------------
# TUNING (degrees, seconds)
# ---------------------------------------------------------------------------
import os as _os0
KICK_ARC       = float(_os0.environ.get("FM_KA_ARC", 70.0))     # either side of where he faces: a normal kick
TURN_WITH_BALL = float(_os0.environ.get("FM_KA_TURNK", 0.6))   # share of his normal body-turn speed with the ball
AWKWARD_ERROR  = float(_os0.environ.get("FM_KA_ERR", 2.0))     # extra error at a kick 180 deg from his facing...
                         # ...scaled down to nothing at KICK_ARC
SET_PIECE_TIME = 3.0     # s after a restart: the taker lined himself up - no turning


def _exempt(player):
    if player.role == "GK":
        return True
    try:
        from core import clock
        return clock._now < getattr(player, "_set_piece_until", -1.0)
    except Exception:
        return False


def angle_off(player, direction):
    """Degrees between the way he faces and `direction` (a vector)."""
    f = player.facing
    if f.length_squared() < 1e-9 or direction.length_squared() < 1e-9:
        return 0.0
    d = max(-1.0, min(1.0, f.normalize().dot(direction.normalize())))
    return math.degrees(math.acos(d))


def turn_rate(player):
    """Degrees a second he can bring his body - and the ball - round."""
    import core.orientation as orient
    from core.locomotion import top_speed_ms
    from core.stats import stat20
    top = max(1.0, top_speed_ms(player))
    frac = min(1.0, (player.vel.length() / M_TO_PX) / top)
    rate = orient.TURN_RATE_STILL + (orient.TURN_RATE_FAST - orient.TURN_RATE_STILL) * frac
    rate += orient.TURN_PER_AGILITY * (stat20(player, "Agility") - 10.0)
    return max(60.0, rate * TURN_WITH_BALL)


import os as _os
_NO_TURN = _os.environ.get("FM_KA_NOTURN") == "1"     # (tests: switch either half off)
_NO_ERR = _os.environ.get("FM_KA_NOERR") == "1"


def turn_time(player, direction):
    """Extra seconds he needs to get round to kick it that way (0 if he's facing near enough)."""
    if _NO_TURN or _exempt(player):
        return 0.0
    extra = angle_off(player, direction) - KICK_ARC
    return extra / turn_rate(player) if extra > 0 else 0.0


def error_mult(player, direction):
    """How much less accurate the kick is for the angle he's kicking it at, as he stands now."""
    if _NO_ERR or _exempt(player):
        return 1.0
    extra = angle_off(player, direction) - KICK_ARC
    return 1.0 + AWKWARD_ERROR * extra / (180.0 - KICK_ARC) if extra > 0 else 1.0


def turn_towards(player, direction, dt):
    """Swing his body (and so the ball, which sits in front of him) towards `direction` this frame.
    Returns True once he's facing within KICK_ARC of it."""
    cur = player.facing
    if cur.length_squared() < 1e-9:
        player.facing = Vector2(direction).normalize()
        return True
    cur = cur.normalize()
    want = Vector2(direction).normalize()
    ang = cur.angle_to(want)
    if ang > 180.0:
        ang -= 360.0
    elif ang < -180.0:
        ang += 360.0
    step = turn_rate(player) * dt
    player.facing = want if abs(ang) <= step else cur.rotate(step if ang > 0 else -step)
    return abs(ang) - step <= KICK_ARC
