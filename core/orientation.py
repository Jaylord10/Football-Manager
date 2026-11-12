"""
core/orientation.py
===================
Which way a player's BODY faces - separately from which way he's moving.

Before: a player always faced exactly where he was running.  So a defender
dropping off a winger turned his back on him, a full-back shuffling across
faced the touchline, and a midfielder waiting for a pass faced wherever he
had last jogged.

Now each frame a player without the ball:
  1. Decides what he wants to LOOK at:
       - defending / pressing / waiting: the ball
       - supporting the man on the ball: half-turned - the ball AND the
         goal he's attacking ("open body"), so he can play forward
       - expecting a pass: the ball, slightly opened up
  2. Moves relative to that.  He can go forwards at full speed, but only
     shuffle sideways (~4 m/s) or backpedal (~3 m/s) while watching.
  3. If he needs to go faster than that, he TURNS AND RUNS: his body swings
     round to face where he's going (taking a moment - a defender who has
     to turn to chase a ball over the top loses a few yards), then he's
     back to full speed.
  4. Running in behind, chasing a loose ball, recovering flat out: he just
     faces where he's going.

The man on the ball faces where he's carrying it (that's handled by the ball
control code as before).

All tuning numbers are in the TUNING block.  Speeds m/s, angles degrees.
"""

import math
from pygame.math import Vector2
from config.constants import M_TO_PX

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
FORWARD_ARC      = 50.0    # deg either side of facing: full speed
SIDE_SPEED       = 4.0     # m/s max shuffling sideways (90 deg)...
BACK_SPEED       = 3.0     # m/s max backpedalling (180 deg)...
SPEED_PER_AGILITY = 0.04   # ...each +/- this per Agility point from 10
TURN_AND_RUN     = 0.3     # m/s: turn and run once he wants this much more than he can shuffle
STAY_RUNNING     = 0.75    # ...and go back to watching below this share of the shuffle speed
TURN_RATE_STILL  = 480.0   # deg/s body turn when (nearly) standing...
TURN_RATE_FAST   = 220.0   # ...and at top speed
TURN_PER_AGILITY = 12.0    # deg/s per Agility point from 10
OPEN_BODY        = 0.7     # supporting: weight of "facing the goal" against "facing the ball"
OPEN_BODY_RECEIVE = 0.35   # about to receive: open up a little
FACE_TRAVEL_STATES = ("run", "intercept", "tackle", "tackled")   # always face where he's going


from core.stats import stat20 as _stat    # (cached: attributes never change during a match)


def _angle(a, b):
    """Angle in degrees between two unit vectors."""
    d = max(-1.0, min(1.0, a.dot(b)))
    return math.degrees(math.acos(d))


def speed_cap(player, angle_deg, top):
    """Fastest he can move at this angle to the way he's facing (m/s)."""
    if angle_deg <= FORWARD_ARC:
        return top
    agi = (_stat(player, "Agility") - 10.0) * SPEED_PER_AGILITY
    side = min(top, SIDE_SPEED + agi)
    back = min(side, BACK_SPEED + agi)
    if angle_deg <= 90.0:
        f = (angle_deg - FORWARD_ARC) / (90.0 - FORWARD_ARC)
        return top + (side - top) * f
    f = (angle_deg - 90.0) / 90.0
    return side + (back - side) * f


_ATTACK_RIGHT = Vector2(1, 0)
_ATTACK_LEFT = Vector2(-1, 0)


def watch_direction(player, ball):
    """Unit vector he wants to face while not running flat out (None = no preference)."""
    if ball is None:
        return None
    to_ball = ball.pos - player.pos
    if to_ball.length_squared() < (0.3 * M_TO_PX) ** 2:
        return None
    to_ball = to_ball.normalize()
    attack = _ATTACK_RIGHT if player.team == 0 else _ATTACK_LEFT   # (never changed in place)
    state = player.state
    if state == "support":
        v = to_ball + attack * OPEN_BODY
    elif state == "chase" and getattr(ball, "intended_target", None) is player:
        v = to_ball + attack * OPEN_BODY_RECEIVE
    else:
        v = to_ball
    return v.normalize() if v.length_squared() > 1e-6 else to_ball


def plan(player, desired, top_ms, ball):
    """
    Adjust the desired velocity for which way he's facing and decide which
    way his body should turn.  Returns (desired, face_target or None).
    """
    speed = desired.length()
    speed_m = speed / M_TO_PX
    watch = watch_direction(player, ball)
    loose_chase = player.state == "chase" and getattr(ball, "intended_target", None) is not player
    if speed_m < 0.05:
        player._turn_and_run = False
        return desired, watch
    move_dir = desired / speed

    if player.state in FACE_TRAVEL_STATES or loose_chase or watch is None:
        running = True
    else:
        cap_watch = speed_cap(player, _angle(watch, move_dir), top_ms)
        running = getattr(player, "_turn_and_run", False)
        if running and speed_m < STAY_RUNNING * cap_watch:
            running = False
        elif not running and speed_m > cap_watch + TURN_AND_RUN:
            running = True
    player._turn_and_run = running
    face_target = move_dir if running else watch

    # Whatever he's doing, he can't go faster than his body allows right now
    facing = player.facing.normalize() if player.facing.length_squared() > 0 else move_dir
    cap = speed_cap(player, _angle(facing, move_dir), top_ms)
    if speed_m > cap:
        desired = move_dir * (cap * M_TO_PX)
    return desired, face_target


def turn(player, face_target, dt, top_ms):
    """Swing the body towards face_target at a limited rate."""
    if face_target is None:
        return
    cur = player.facing
    if cur.length_squared() < 1e-6:
        player.facing = Vector2(face_target)
        return
    cur = cur.normalize()
    speed_frac = min(1.0, (player.vel.length() / M_TO_PX) / max(top_ms, 1.0))
    rate = TURN_RATE_STILL + (TURN_RATE_FAST - TURN_RATE_STILL) * speed_frac
    rate += TURN_PER_AGILITY * (_stat(player, "Agility") - 10.0)
    max_step = rate * dt
    ang = cur.angle_to(face_target)            # signed degrees
    if ang > 180.0:
        ang -= 360.0
    elif ang < -180.0:
        ang += 360.0
    if abs(ang) <= max_step:
        player.facing = Vector2(face_target)
    else:
        player.facing = cur.rotate(max_step if ang > 0 else -max_step)
