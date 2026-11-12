# ai/tpi.py
from pygame.math import Vector2
from core.utils import distance, clamp, angle_between
from config.constants import M_TO_PX


def compute_tpi(player, opponents, teammates=None):
    """
    Time & Pressure Index (TPI)
    Returns value in [0.0, 1.0]
    1.0 = calm, time & space
    0.0 = immediate danger
    """

    # --- 1) Nearest defender distance ---
    if opponents:
        nearest = min(distance(player.pos, d.pos) for d in opponents)
    else:
        nearest = 9999.0

    dist_score = clamp(nearest / (8.0 * M_TO_PX), 0.0, 1.0)

    # --- 2) Crowd pressure ---
    close_defs = 0
    for d in opponents:
        if distance(player.pos, d.pos) < 6.0 * M_TO_PX:
            close_defs += 1

    crowd_score = 1.0 - clamp(close_defs / 3.0, 0.0, 1.0)

    # --- 3) Angle of pressure ---
    front_pressure = False
    if player.facing.length_squared() > 0:
        for d in opponents:
            to_def = d.pos - player.pos
            if to_def.length_squared() == 0:
                continue
            ang = angle_between(player.facing.normalize(), to_def.normalize())
            if ang < 60:  # defender roughly in front
                front_pressure = True
                break

    angle_score = 0.5 if front_pressure else 1.0

    # --- 4) Facing direction (calm if facing attack) ---
    attack_dir = Vector2(1, 0) if player.team == 0 else Vector2(-1, 0)
    if player.facing.length_squared() > 0:
        facing_score = clamp(
            (player.facing.normalize().dot(attack_dir) + 1.0) / 2.0,
            0.0,
            1.0,
        )
    else:
        facing_score = 0.5

    # --- 5) Support (optional, light influence) ---
    support_score = 0.5
    if teammates:
        dists = [
            distance(player.pos, t.pos)
            for t in teammates
            if t is not player
        ]
        if dists:
            nearest_support = min(dists)
            support_score = clamp(nearest_support / (10.0 * M_TO_PX), 0.3, 1.0)

    # --- Final blend ---
    tpi = (
        0.35 * dist_score +
        0.20 * crowd_score +
        0.15 * angle_score +
        0.15 * facing_score +
        0.15 * support_score
    )

    return clamp(tpi, 0.0, 1.0)
