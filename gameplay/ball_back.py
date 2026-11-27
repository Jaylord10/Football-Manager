"""
gameplay/ball_back.py
=====================
(27 Nov, Jay: "the ball misses the goal then insta-jumps to the six-yard box... it should fly into the stands, get
thrown back, the keeper goes and picks it up and puts it on the spot")

A goal kick, between the ball going out and the keeper putting it down.  The engine's ball is placed on the
goal-kick spot straight away as before (so nothing else in the match changes - everyone takes up their goal-kick
positions round it), but what you SEE is this ball (ball._back):

  1. "out":   it carries on where it was going - over the line, past the boards, into the stands behind the goal
              (it stops STANDS_M behind the line);
  2. "throw": a moment later a ball boy behind the goal throws one back (Premier League grounds keep balls round the
              pitch so play isn't held up - the multi-ball system), in an arc to the keeper, who's gone to the
              corner of his six-yard box for it;
  3. "carry": he's caught it and walks it to the spot (held in his hands), and puts it down.

Then the goal kick goes on as before: he places it, steps back and takes it (broadcast3d draws the placing).
The 2D view and the 3D recording show ball._back's ball while it's on; the match itself never touches it.
"""
import math
from pygame.math import Vector2
from config.constants import M_TO_PX, WIDTH, HEIGHT, GRAVITY

STANDS_M = 9.0         # m behind the goal line: the front rows (the ball stops there)
OUT_FOR = 2.2          # s it's out of sight in the stands before the ball boy throws one back...
WAIT_KEEPER = 5.0      # ...once the keeper's near where he'll take it (or this long, whatever)
BOY_BACK = 6.0         # m behind the line the ball boy throws from...
BOY_WIDE = 14.0        # ...this far from the middle of the goal, on the side it went out
THROW_FROM_Z = 1.7     # m: from his hands, over his head
CATCH_Z = 1.1          # m: the keeper takes it at chest height
THROW_T = 1.05         # s in the air (an 11 m throw)
PICK_IN = 1.5          # m inside the goal line the keeper takes it...
PICK_WIDE = 6.0        # ...this far from the middle (the corner of the six-yard box)
HANDS_Z = 1.0          # m: carried in his hands
DONE_M = 0.4           # m: at the spot - he puts it down


def start(ball, spot, keeper, now):
    """The ball has just gone out for a goal kick at (ball.pos, ball.z, moving ball.vel): from here on it's shown,
    not played.  spot = the goal-kick spot (the engine's ball goes there)."""
    side = -1.0 if ball.pos.x < WIDTH / 2 else 1.0            # (the goal it went behind: left -1 / right +1)
    wide = 1.0 if ball.pos.y >= HEIGHT / 2 else -1.0
    ball._back = {"phase": "out", "t": 0.0, "since": now, "side": side, "wide": wide,
                  "pos": [ball.pos.x, ball.pos.y, float(getattr(ball, "z", 0.0))],
                  "vel": [ball.vel.x, ball.vel.y, float(getattr(ball, "vz", 0.0))],
                  "spot": Vector2(spot), "keeper": keeper}


def active(ball):
    return getattr(ball, "_back", None) is not None


def shown(ball):
    """(x, y, z) px where the ball's shown, or None (it's the engine's ball)."""
    s = getattr(ball, "_back", None)
    if s is None:
        return None
    if s["phase"] == "carry":
        k = s["keeper"]
        return (k.pos.x, k.pos.y, HANDS_Z * M_TO_PX)
    return tuple(s["pos"])


def holder(ball):
    """The keeper carrying it in his hands (or None)."""
    s = getattr(ball, "_back", None)
    return s["keeper"] if s is not None and s["phase"] == "carry" else None


def keeper_target(ball):
    """Where the keeper's going: for the ball (the corner of his six-yard box) - then, with it, to the spot."""
    s = ball._back
    if s["phase"] == "carry":
        return Vector2(s["spot"])
    return _pick(s)


def _pick(s):
    line = 0.0 if s["side"] < 0 else WIDTH
    return Vector2(line - s["side"] * PICK_IN * M_TO_PX, HEIGHT / 2 + s["wide"] * PICK_WIDE * M_TO_PX)


def update(ball, dt, now):
    s = getattr(ball, "_back", None)
    if s is None:
        return
    s["t"] += dt
    k = s["keeper"]
    if s["phase"] == "out":
        p, v = s["pos"], s["vel"]
        line = 0.0 if s["side"] < 0 else WIDTH
        stop = line + s["side"] * STANDS_M * M_TO_PX
        if v[0] or v[1] or v[2] or p[2] > 0:
            p[0] += v[0] * dt; p[1] += v[1] * dt; p[2] += v[2] * dt
            f = (0.995 if p[2] > 1.0 else 0.992) ** (dt * 60)
            v[0] *= f; v[1] *= f
            v[2] -= GRAVITY * dt
            if p[2] < 0:
                p[2] = 0.0
                v[2] = -v[2] * 0.6 if abs(v[2]) > 20 else 0.0
            if (p[0] - stop) * s["side"] > 0:                   # (into the seats: it stops there)
                p[0] = stop
                v[0] = v[1] = v[2] = 0.0
                p[2] = max(p[2], 0.0)
            if math.hypot(v[0], v[1]) < 2 and p[2] == 0.0 and v[2] == 0.0:
                v[0] = v[1] = 0.0
        near = k is None or (k.pos - _pick(s)).length() < 4.0 * M_TO_PX
        if s["t"] >= OUT_FOR and (near or s["t"] >= OUT_FOR + WAIT_KEEPER):
            _throw(s)
    elif s["phase"] == "throw":
        p, v = s["pos"], s["vel"]
        p[0] += v[0] * dt; p[1] += v[1] * dt; p[2] += v[2] * dt
        v[2] -= GRAVITY * dt
        s["tt"] += dt
        if s["tt"] >= THROW_T:
            if k is None:
                ball._back = None
                return
            s["phase"] = "carry"                                  # (he's got it)
    elif s["phase"] == "carry":
        if k is None or (k.pos - s["spot"]).length() <= DONE_M * M_TO_PX:
            ball._back = None                                     # (he puts it down: the engine's ball, on the spot)


def _throw(s):
    """The ball boy's throw: from behind the goal, to where the keeper is (or is getting to)."""
    line = 0.0 if s["side"] < 0 else WIDTH
    x0 = line + s["side"] * BOY_BACK * M_TO_PX
    y0 = HEIGHT / 2 + s["wide"] * BOY_WIDE * M_TO_PX
    k = s["keeper"]
    tgt = _pick(s) if k is None else Vector2(k.pos)
    if k is not None and (k.pos - _pick(s)).length() > 1.0 * M_TO_PX:
        tgt = Vector2(k.pos) + (_pick(s) - k.pos).normalize() * min((_pick(s) - k.pos).length(), 3.0 * M_TO_PX)
    T = THROW_T
    vz = ((CATCH_Z - THROW_FROM_Z) * M_TO_PX + 0.5 * GRAVITY * T * T) / T
    s["phase"], s["tt"] = "throw", 0.0
    s["pos"] = [x0, y0, THROW_FROM_Z * M_TO_PX]
    s["vel"] = [(tgt.x - x0) / T, (tgt.y - y0) / T, vz]
