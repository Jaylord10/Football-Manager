# ===========================================================================
# gameplay/shooting.py
# How a shot is STRUCK (the decision to shoot lives in ai/shooting.py).
#
# A shot now works like this:
#   1. Pick a shot type from the situation: placed, driven, chip or penalty.
#   2. Pick a target: the side of the goal with more room away from the keeper,
#      a little inside the post (better finishers aim tighter to the post).
#   3. Pick a height at the goal line for that shot type, then work out the
#      launch angle that actually gets the ball there (using the same ball
#      physics as Ball.update), so shots no longer fly over by accident.
#   4. Add a realistic miss: a bell-curve error around the target whose size
#      comes from the player's skill (Finishing / Long Shots / Penalties),
#      Composure under pressure, and how fast they're running.
#
# All the tuning numbers are in the TUNING block below.
# ===========================================================================

import math
import random
from pygame.math import Vector2
from core.utils import distance, clamp
from config.constants import *


# ---------------------------------------------------------------------------
# TUNING  (metres, m/s and degrees unless stated)
# ---------------------------------------------------------------------------
# Shot speed by type: base + per-skill-point (skill on the 1-20 scale)
SPEED_PLACED   = (19.0, 0.35)    # skill 13 -> ~23.5 m/s
SPEED_DRIVEN   = (23.0, 0.40)    # skill 13 -> ~28 m/s
SPEED_PENALTY  = (21.0, 0.30)
SPEED_CHIP     = (12.0, 0.15)

# Target height at the goal line (min, max) by type
HEIGHT_PLACED  = (0.15, 1.20)
HEIGHT_DRIVEN  = (0.25, 1.90)
HEIGHT_PENALTY = (0.15, 1.60)
HEIGHT_CHIP    = (1.40, 2.10)

# How far inside the post the player aims: worst skill -> best skill
AIM_INSIDE_POST = (1.10, 0.40)

# Sideways error (degrees, standard deviation) = BASE + PER_POINT * (20 - skill)
ANGLE_ERROR_BASE      = 3.9
ANGLE_ERROR_PER_POINT = 0.30
ANGLE_ERROR_PER_M     = 0.10     # extra degrees per metre beyond 16 m (long shots are harder)

# Height error (metres, standard deviation) = BASE + PER_M * distance * (1.6 - skill/20)
HEIGHT_ERROR_BASE  = 0.25
HEIGHT_ERROR_PER_M = 0.035

# Chance of completely skying / shanking it (before pressure)
SHANK_CHANCE = 0.05

PENALTY_ERROR_FACTOR = 0.45      # penalties: no pressure, ball still - far more accurate
PENALTY_AIM_INSIDE   = (0.90, 0.55)

PRESSURE_RADIUS = 2.5            # a defender this close counts as pressure
PLACED_MAX_DIST = 16.0           # beyond this, shots are driven
CHIP_KEEPER_OFF_LINE = 6.0       # keeper this far off his line can be chipped


def _stat(player, name, default=10):
    value = player.attributes.get(name, default)
    if value > 25:               # safety: a raw 0-100 value slipped through
        value /= 5.0
    return clamp(value, 1, 20)


def _find_keeper(opponents):
    if not opponents:
        return None
    return next((o for o in opponents if o.role == "GK" and getattr(o, "is_active", True)), None)


# ---------------------------------------------------------------------------
# Ball-flight helper: replicates Ball.update() so the launch angle is exact
# ---------------------------------------------------------------------------
def _height_at_goal(dist_px, speed_px, vz_px):
    """Height (px) of the ball when it has travelled dist_px, using Ball.update physics."""
    dt = 1.0 / 60.0
    travelled, v, z, vz = 0.0, speed_px, 0.0, vz_px
    for _ in range(240):                       # 4 s cap
        travelled += v * dt
        friction = 0.995 if z > 0.1 else 0.992
        v *= friction                          # (friction ** (dt*60)) with dt = 1/60
        z += vz * dt
        vz -= GRAVITY * dt
        if z < 0:
            z = 0.0
            vz = -vz * BOUNCE_FACTOR if abs(vz) > 20 else 0.0
        if travelled >= dist_px:
            return z
        if v < 1.0:
            break
    return z


def _launch_vz_for_height(dist_px, speed_px, target_z_px):
    """Bisection: vertical launch speed that puts the ball at target_z_px at the goal line."""
    lo, hi = 0.0, 25.0 * M_TO_PX
    if _height_at_goal(dist_px, speed_px, lo) >= target_z_px:
        return lo
    for _ in range(14):
        mid = (lo + hi) / 2
        if _height_at_goal(dist_px, speed_px, mid) < target_z_px:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def execute_shot(player, ball, current_time, opponents=None, shot_type=None):
    """
    Strike a shot at goal.

    shot_type: None (choose automatically), "placed", "driven", "chip" or "penalty".
    opponents: pass the opposing team so pressure and the keeper's position count.
    """
    goal_x = float(WIDTH) if player.team == 0 else 0.0
    goal_centre = Vector2(goal_x, HEIGHT / 2)
    post_top = HEIGHT / 2 - GOAL_WIDTH / 2
    post_bottom = HEIGHT / 2 + GOAL_WIDTH / 2
    dist_m = distance(player.pos, goal_centre) / M_TO_PX

    keeper = _find_keeper(opponents)
    field_opps = [o for o in (opponents or []) if o.role != "GK" and getattr(o, "is_active", True)]
    nearest_def = min((distance(player.pos, o.pos) for o in field_opps), default=9999.0) / M_TO_PX

    finishing   = _stat(player, "Finishing")
    long_shots  = _stat(player, "Long Shots", finishing)
    composure   = _stat(player, "Composure")
    strength    = _stat(player, "Strength", _stat(player, "Physical"))
    penalties   = _stat(player, "Penalties", finishing)

    # ---------------------------------------------------------------- type
    if shot_type is None:
        keeper_off_line = abs(keeper.pos.x - goal_x) / M_TO_PX if keeper else 0.0
        if (keeper and keeper_off_line > CHIP_KEEPER_OFF_LINE and 10.0 < dist_m < 25.0
                and random.random() < 0.6):
            shot_type = "chip"
        elif dist_m <= PLACED_MAX_DIST:
            shot_type = "placed"
        else:
            shot_type = "driven"

    if shot_type == "penalty":
        skill = (penalties * 2 + composure) / 3
        speed_cfg, height_cfg = SPEED_PENALTY, HEIGHT_PENALTY
    elif shot_type == "driven":
        skill = (finishing + long_shots * 2) / 3
        speed_cfg, height_cfg = SPEED_DRIVEN, HEIGHT_DRIVEN
    elif shot_type == "chip":
        skill = (finishing + composure) / 2
        speed_cfg, height_cfg = SPEED_CHIP, HEIGHT_CHIP
    else:
        shot_type = "placed"
        skill = finishing
        speed_cfg, height_cfg = SPEED_PLACED, HEIGHT_PLACED

    skill01 = (skill - 1) / 19.0

    # ---------------------------------------------------------------- target
    # Aim for the side with more room between keeper and post.
    if keeper is not None:
        gap_top = keeper.pos.y - post_top
        gap_bottom = post_bottom - keeper.pos.y
        better_side = -1 if gap_top > gap_bottom else 1
        # Better players read it right more often
        side = better_side if random.random() < 0.65 + 0.25 * skill01 else -better_side
    else:
        side = random.choice((-1, 1))

    aim_cfg = PENALTY_AIM_INSIDE if shot_type == "penalty" else AIM_INSIDE_POST
    inside = aim_cfg[0] + (aim_cfg[1] - aim_cfg[0]) * skill01
    aim_y = (post_bottom - inside * M_TO_PX) if side > 0 else (post_top + inside * M_TO_PX)
    if shot_type == "chip":
        aim_y = HEIGHT / 2 + side * random.uniform(0.0, 1.5) * M_TO_PX   # chips go more central
    aim = Vector2(goal_x, aim_y)

    target_height_m = random.uniform(*height_cfg)

    # ---------------------------------------------------------------- error
    pressure = 1.0
    if nearest_def < PRESSURE_RADIUS:
        pressure += 0.6 * (1.0 - composure / 20.0)
        if nearest_def < 1.2:
            pressure += 0.25
    if player.vel.length() > MAX_SPEED * 0.7:
        pressure += 0.15

    angle_sd = (ANGLE_ERROR_BASE + ANGLE_ERROR_PER_POINT * (20 - skill)
                + ANGLE_ERROR_PER_M * max(0.0, dist_m - 16.0)) * pressure
    if shot_type == "penalty":
        angle_sd *= PENALTY_ERROR_FACTOR
    height_sd = (HEIGHT_ERROR_BASE + HEIGHT_ERROR_PER_M * dist_m * (1.6 - skill / 20.0)) * pressure

    angle_err = random.gauss(0.0, angle_sd)
    height_err = random.gauss(0.0, height_sd)
    if random.random() < SHANK_CHANCE * pressure * (1.3 - skill01):
        # Scuffed it: way off target
        angle_err += random.choice((-1, 1)) * random.uniform(6.0, 14.0)
        height_err += random.uniform(1.0, 3.0)

    target_height_m = max(0.0, target_height_m + height_err)

    # ---------------------------------------------------------------- power
    speed_ms = speed_cfg[0] + speed_cfg[1] * skill
    if shot_type == "driven":
        speed_ms += (strength - 10) * 0.25
    speed_ms *= random.uniform(0.94, 1.06)
    speed_px = speed_ms * M_TO_PX

    # ---------------------------------------------------------------- strike
    to_aim = aim - player.pos
    if to_aim.length_squared() == 0:
        to_aim = Vector2(1, 0) if player.team == 0 else Vector2(-1, 0)
    direction = to_aim.normalize().rotate(angle_err)
    dist_to_line_px = max(1.0, to_aim.length())

    vz = _launch_vz_for_height(dist_to_line_px, speed_px, target_height_m * M_TO_PX)
    elevation = vz / (speed_px * 0.8)     # Ball.kick sets vz = speed * elevation * 0.8

    player.state = "shoot"
    ball.kick(direction * speed_px, kicker=player, elevation=elevation)
    ball.last_kick_time = current_time
    ball.last_owner = player
    ball.shot_info = {
        "time": current_time,
        "type": shot_type,
        "shooter": player,
        "speed_ms": speed_ms,
    }
    player.has_ball = False
