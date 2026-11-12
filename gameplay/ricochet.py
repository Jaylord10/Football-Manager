"""
gameplay/ricochet.py
====================
Blocks and deflections: the ball coming off a body.

Before this a shot that hit a defender was simply CONTROLLED by him, like a
pass - nothing ever ricocheted.  So blocked shots never went out for a corner,
deflected shots never wrong-footed a keeper, and a defender closing down a
cross from two yards never blocked it behind.

Now a ball struck too hard to cushion (a shot, a ricochet, or a hard pass /
cross struck from right next to him) that hits a player comes off him:

  - Whether he gets in the way: he has to be close to its path - his body,
    or a leg stuck out (reach from Agility).  Right at him he nearly always
    blocks it; at the edge of his reach it often gets past him.
  - How it comes off:
      a GLANCE (about a third): it keeps going, a little off its line, at
        most of its pace - the deflected shot that wrong-foots the keeper or
        flies just wide for a corner;
      a BLOCK: it comes back off him - back towards the shooter or off to
        the side, at a fraction of its pace, sometimes looping up off a leg.
  - Nobody controls it: it's a loose ball, so the second ball is a scramble,
    and plenty go out for corners and throw-ins.

Throw-ins / corners go against whoever it came off (gameplay/set_pieces.py),
and a keeper has to save a ricochet off his own defender like any shot
(gameplay/goalkeeping.py).

All tuning numbers are in the TUNING block.
"""

import random
from pygame.math import Vector2
from config.constants import M_TO_PX

# ---------------------------------------------------------------------------
# TUNING  (metres, m/s, degrees)
# ---------------------------------------------------------------------------
BLOCK_MIN_SPEED   = 11.0          # m/s: struck harder than this he can't cushion it - it comes off him
BLOCK_REACH       = (0.70, 1.10)  # m from his centre: body, a leg stuck out, a slide (worst, best Agility)...
PASS_REACH_SHARE  = 0.65          # ...less for a pass or cross (he's closing the man down, not throwing himself in front of it)
BLOCK_MAX_HEIGHT  = 1.9           # m: above this it's over him
BLOCK_CHANCE      = (0.95, 0.30)  # chance it hits him: right at him ... at the edge of his reach
PASS_BLOCK_RANGE  = 4.0           # m: a hard pass / cross is blocked only by a man this close to the passer...
PASS_BLOCK_SPEED  = 14.0          # m/s: ...and only if it's struck this hard
JUST_STRUCK       = 0.15          # s: the man who struck it can't block his own shot
RICOCHET_LIVE     = 1.0           # s: a ricochet can come off the next man too...
RICOCHET_MIN_SPEED = 15.0         # m/s: ...if it's still this fast (slower, he can control it)

GLANCE_SHARE      = (0.15, 0.75)  # chance it's a glancing deflection: hit at his body ... off a leg at full stretch
GLANCE_TURN       = (6.0, 50.0)   # degrees off its line
GLANCE_SPEED      = (0.55, 0.85)  # share of its pace it keeps
BLOCK_SPREAD      = 85.0          # a full block comes back within this many degrees of straight back
BLOCK_SPEED       = (0.20, 0.55)  # share of its pace it keeps
LOOP_CHANCE       = 0.35          # chance a full block loops up off a leg / body...
LOOP_LIFT         = (0.25, 0.7)   # ...with this much lift (Ball.kick elevation)


def _stat(p, name):
    v = p.attributes.get(name, 10)
    if v > 25:
        v /= 5.0
    return max(1.0, min(20.0, v))


def _lerp(lo_hi, q):
    lo, hi = lo_hi
    return lo + (hi - lo) * q


def is_live_shot(ball):
    shot = getattr(ball, "shot_info", None)
    return bool(shot) and shot.get("time") == getattr(ball, "last_kick_time", None)


def is_ricochet(ball):
    """Did the ball last come off someone (rather than being kicked by him)?"""
    return getattr(ball, "ricochet_time", None) is not None \
        and ball.ricochet_time == getattr(ball, "last_kick_time", None)


def blockable(player, ball, now):
    """Is this ball coming at him too hard to control?"""
    speed = ball.vel.length() / M_TO_PX
    if speed < BLOCK_MIN_SPEED or ball.z > BLOCK_MAX_HEIGHT * M_TO_PX:
        return False
    since = now - getattr(ball, "last_kick_time", -99.0)
    if ball.last_toucher is player and since < JUST_STRUCK:
        return False
    if is_live_shot(ball):
        return True
    if is_ricochet(ball):
        return since < RICOCHET_LIVE and speed >= RICOCHET_MIN_SPEED
    # A pass / cross: only blocked by an opponent closing down the passer
    if getattr(ball, "last_toucher_team", None) in (None, player.team):
        return False
    if speed < PASS_BLOCK_SPEED:
        return False
    start = getattr(ball, "pass_start_pos", None)
    return start is not None and (start - player.pos).length() < PASS_BLOCK_RANGE * M_TO_PX


def _miss_distance(player, ball, dt):
    """m: how close the ball's path this frame came to him."""
    end = ball.pos
    start = ball.pos - ball.vel * dt
    seg = end - start
    rel = player.pos - start
    L2 = seg.length_squared()
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, rel.dot(seg) / L2))
    return (start + seg * t - player.pos).length() / M_TO_PX


def try_block(player, ball, now, dt=1.0 / 60.0):
    """
    Called for each outfield player near a moving ball, before he tries to
    take it.  Returns True if it came off him (the ball is now loose).
    """
    if ball.owner is not None or ball.is_dead or player.role == "GK":
        return False
    if not blockable(player, ball, now):
        return False
    reach = _lerp(BLOCK_REACH, (_stat(player, "Agility") - 1.0) / 19.0)
    if not is_live_shot(ball):
        reach *= PASS_REACH_SHARE
    miss = _miss_distance(player, ball, dt)
    if miss > reach:
        return False
    key = (getattr(ball, "last_kick_time", None), id(player))
    if getattr(player, "_block_roll", None) == key:
        return False                                   # one roll per ball
    player._block_roll = key
    if random.random() >= _lerp(BLOCK_CHANCE, miss / reach):
        return False                                   # it gets past him
    STATS["off_" + ("shot" if is_live_shot(ball) else "ricochet" if is_ricochet(ball) else "pass")] += 1
    _come_off(player, ball, now, miss / reach)
    return True


def _come_off(player, ball, now, edge=0.5):
    """edge: 0 = it hit him square on, 1 = off a leg at full stretch."""
    v = ball.vel.length()
    direction = ball.vel / v
    lift = 0.0
    if random.random() < _lerp(GLANCE_SHARE, edge):
        out = direction.rotate(random.uniform(*GLANCE_TURN) * random.choice((-1.0, 1.0)))
        speed = v * random.uniform(*GLANCE_SPEED)
        kind = "glance"
    else:
        out = (-direction).rotate(random.uniform(-BLOCK_SPREAD, BLOCK_SPREAD))
        speed = v * random.uniform(*BLOCK_SPEED)
        if random.random() < LOOP_CHANCE:
            lift = random.uniform(*LOOP_LIFT)
        kind = "block"
    z = ball.z
    ball.kick(out * speed, kicker=player, elevation=lift)
    ball.z = z                                          # it comes off him where it hit him
    ball.intended_target = None
    ball.last_kick_time = now
    ball.ricochet_time = now
    ball.last_ricochet = {"kind": kind, "player": player, "time": now}
    player._next_run_touch = now + 0.3                  # he can't immediately control his own block
    player._no_touch_until = now + 0.2
    STATS[kind] += 1


from collections import Counter as _Counter
STATS = _Counter()      # read by sim.py
