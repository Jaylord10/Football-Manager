"""
gameplay/through_pass.py
========================
Plans a through ball: a pass into SPACE for a teammate who is running.

A real through ball isn't aimed at the runner - it's aimed at where he is
going to be, weighted so that he and the ball arrive together.  This module
finds that meeting point and checks it's worth playing:

  1. The runner must be ONSIDE right now (when the pass is played).
  2. For a range of lead times (0.8 - 3 s) it works out where the runner
     will be, and how hard the ball must be hit to arrive there at the same
     moment (using the real ball friction).
  3. It rejects meeting points that are off the pitch, need an impossible
     pass, or leave the ball too fast/slow to control.
  4. It races every defender (and the keeper) against the ball along its path
     and to the meeting point.  If someone gets there first, it's no good.
  5. Of the safe options it picks the one that gets the runner closest to a
     scoring position.

All tuning numbers are in the TUNING block (metres, seconds).
"""

import math
from pygame.math import Vector2
from config.constants import WIDTH, HEIGHT, M_TO_PX, OFFSIDE_MARGIN
from core.utils import distance

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
LEAD_TIMES          = [0.8 + 0.1 * i for i in range(23)]   # 0.8 .. 3.0 s
MIN_PASS_DIST       = 8.0     # m: shorter than this is just a normal pass
MIN_RUNNER_SPEED    = 2.5     # m/s: the runner must already be on the move
MIN_FORWARD         = 0.3     # run direction . attacking direction (0 = sideways)
RUNNER_ACCEL        = 4.0     # m/s^2 the runner keeps accelerating at
MAX_PASS_SPEED      = 30.0    # m/s
ARRIVAL_SPEED       = (3.0, 10.0)   # m/s: ball speed at the meeting point he can control
TOUCHLINE_MARGIN    = 2.0     # m: meeting point must be this far inside the touchlines
GOALLINE_MARGIN     = 6.0     # m: ...and this far from the goal line
DEF_REACTION        = 0.30    # s before a defender reacts to the pass
DEF_SPEED           = 6.5     # m/s average defender speed over a short burst
DEF_REACH           = 1.2     # m: a defender within this of the ball's path can stop it
GK_SPEED            = 7.0
GK_REACH            = 2.0     # keepers can use their hands / dive
RUNNER_HEAD_START   = 0.15    # s: runner must beat any defender to the point by this much

_K_GROUND = 0.992 ** 60                 # ball speed kept per second on the ground
_NEG_LN_K = -math.log(_K_GROUND)


def _ball_time_to(dist_m, speed_ms):
    """Seconds for a ground pass hit at speed_ms to travel dist_m (None if it never gets there)."""
    frac = dist_m * _NEG_LN_K / speed_ms
    if frac >= 1.0:
        return None
    return math.log(1.0 - frac) / math.log(_K_GROUND)


def _runner_distance(v0, v_top, t):
    """Distance covered in t seconds starting at v0, accelerating to v_top."""
    if v0 >= v_top:
        return v_top * t
    t_acc = (v_top - v0) / RUNNER_ACCEL
    if t <= t_acc:
        return v0 * t + 0.5 * RUNNER_ACCEL * t * t
    return v0 * t_acc + 0.5 * RUNNER_ACCEL * t_acc * t_acc + v_top * (t - t_acc)


def is_offside_now(runner, passer, opponents):
    """Would the runner be offside if the ball were played right now?"""
    attack_right = runner.team == 0
    ahead_of_ball = (runner.pos.x > passer.pos.x + OFFSIDE_MARGIN) if attack_right \
        else (runner.pos.x < passer.pos.x - OFFSIDE_MARGIN)
    if not ahead_of_ball:
        return False
    if attack_right:
        between = sum(1 for o in opponents if o.pos.x > runner.pos.x)
    else:
        between = sum(1 for o in opponents if o.pos.x < runner.pos.x)
    return between < 2


def plan(passer, runner, opponents):
    """
    Returns a plan dict {point, speed_px, lead_time, safety, value} or None.
    opponents should include the keeper.
    """
    import core.locomotion as locomotion

    attack_dir = Vector2(1, 0) if passer.team == 0 else Vector2(-1, 0)
    goal = Vector2(WIDTH if passer.team == 0 else 0.0, HEIGHT / 2)

    speed = runner.vel.length() / M_TO_PX
    if speed < MIN_RUNNER_SPEED:
        return None
    run_dir = runner.vel.normalize()
    if run_dir.dot(attack_dir) < MIN_FORWARD:
        return None
    if is_offside_now(runner, passer, opponents):
        return None

    v_top = locomotion.top_speed_ms(runner) * 0.95
    best = None
    for t in LEAD_TIMES:
        point = runner.pos + run_dir * (_runner_distance(speed, v_top, t) * M_TO_PX)

        # On the pitch, away from the lines
        if not (TOUCHLINE_MARGIN * M_TO_PX <= point.y <= HEIGHT - TOUCHLINE_MARGIN * M_TO_PX):
            break
        if not (GOALLINE_MARGIN * M_TO_PX <= point.x <= WIDTH - GOALLINE_MARGIN * M_TO_PX):
            break

        d_m = distance(passer.pos, point) / M_TO_PX
        if d_m < MIN_PASS_DIST:
            continue

        # Pass speed so the ball arrives exactly when he does
        k_t = _K_GROUND ** t
        v_pass = d_m * _NEG_LN_K / (1.0 - k_t)
        v_arrive = v_pass * k_t
        if v_pass > MAX_PASS_SPEED or not (ARRIVAL_SPEED[0] <= v_arrive <= ARRIVAL_SPEED[1]):
            continue

        safety = _race(passer.pos, point, v_pass, t, opponents)
        if safety is None:
            continue

        # Value: closer to goal and more central is better
        to_goal_m = distance(point, goal) / M_TO_PX
        value = max(0.0, 1.0 - to_goal_m / 45.0)
        value *= 0.75 + 0.25 * max(0.0, 1.0 - abs(point.y - HEIGHT / 2) / (HEIGHT / 2))
        score = value + 0.15 * min(safety, 1.5)
        if best is None or score > best["score"]:
            best = {"point": point, "speed_px": v_pass * M_TO_PX, "lead_time": t,
                    "safety": safety, "value": value, "score": score, "runner": runner}
    return best


def _race(start, point, v_pass, t_arrive, opponents):
    """
    Smallest time margin (s) by which the ball/runner beat every defender.
    None if any defender wins.
    """
    path = point - start
    length_m = path.length() / M_TO_PX
    direction = path / path.length()
    margin = 9.9
    for opp in opponents:
        is_gk = opp.role == "GK"
        reach = GK_REACH if is_gk else DEF_REACH
        spd = GK_SPEED if is_gk else DEF_SPEED

        # 1. Can he cut the pass out on its way?
        rel = opp.pos - start
        along_m = rel.dot(direction) / M_TO_PX
        if 0.0 < along_m < length_m:
            side_m = abs(rel.x * direction.y - rel.y * direction.x) / M_TO_PX
            t_ball = _ball_time_to(along_m, v_pass)
            if t_ball is not None:
                t_def = DEF_REACTION + max(0.0, side_m - reach) / spd
                margin = min(margin, t_def - t_ball)
                if t_def <= t_ball:
                    return None

        # 2. Can he get to the meeting point before the runner?
        to_point_m = distance(opp.pos, point) / M_TO_PX
        t_def_point = DEF_REACTION + max(0.0, to_point_m - reach) / spd
        m2 = t_def_point - (t_arrive + RUNNER_HEAD_START)
        margin = min(margin, m2)
        if m2 <= 0:
            return None
    return margin
