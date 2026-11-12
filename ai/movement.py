import ai.team_shape as team_shape
import math
import random
from pygame.math import Vector2
from core.utils import grid_cell_from_position, cell_center, distance, clamp
from config.constants import *
from config.formations import formation_4_4_2_positions

# ---------------------------------------------------------------------------
# Friction constants for ball intercept prediction
# ---------------------------------------------------------------------------
# Matches the values in passing.py so intercept targets are consistent.
_BALL_K_PER_SEC  = 0.992 ** 60          # ground friction: speed retained per second ≈ 0.617
_BALL_NEG_LOG_K  = -math.log(_BALL_K_PER_SEC)   # ≈ 0.481
_INTERCEPT_T_CAP = 1.5                   # seconds: max lookahead for through-ball prediction

# ---------------------------------------------------------------------------
# Stable ball position for role targeting
# ---------------------------------------------------------------------------
# The ball can cross a grid-cell boundary (≈46 px) in a single frame when
# travelling at pass speed.  Using the raw ball position means ALL 11 role
# targets update simultaneously on every cell crossing, producing a
# one-frame jump of up to 46 px in every player's target → visible teleport.
#
# _smooth_ball is a running-average that lags the real ball by ~0.12 s.
# Role targets change smoothly, while the ball itself still moves at full speed.
# ---------------------------------------------------------------------------
_smooth_ball = None          # Vector2, initialised on first call

def _stable_ball_cell(ball):
    """Return a grid cell computed from a low-pass-filtered ball position."""
    global _smooth_ball
    if _smooth_ball is None:
        _smooth_ball = Vector2(ball.pos)
    else:
        # lerp ≈ 0.10  →  time-constant ≈ 9 frames (0.15 s at 60 fps)
        _smooth_ball = _smooth_ball.lerp(ball.pos, 0.10)
    return grid_cell_from_position(_smooth_ball)


def reset_stable_ball():
    """
    Call after any match reset / kickoff so _smooth_ball starts fresh.

    Without this, _smooth_ball holds the old position (e.g. near a goal line)
    after reset_game() snaps the ball to centre, causing role targets to be
    computed from the wrong cell for ~1 s until the filter catches up.
    """
    global _smooth_ball
    _smooth_ball = None


# ---------------------------------------------------------------------------
# Target smoothing — prevents 46 px cell-jump jolts
# ---------------------------------------------------------------------------
# Even with _stable_ball_cell, a grid cell crossing is still a discrete step,
# so a formation target can jump a full cell width (~46 px) in one frame.
# _clamp_target() limits how far player.target moves each frame for formation-
# following states (support / defend).  Chase / press targets are excluded
# because those need immediate responsiveness.
# ---------------------------------------------------------------------------
_MAX_TARGET_SHIFT = 10.0          # px per frame ≈ 1.1 m at 60 fps


def _clamp_target(player, new_target, max_shift=_MAX_TARGET_SHIFT):
    """
    Move player.target toward new_target by at most max_shift pixels this frame.

    Returns the (possibly clamped) target Vector2.  Does NOT modify player.target
    directly — callers decide whether to assign.
    """
    delta = new_target - player.target
    delta_len = delta.length()
    if delta_len <= max_shift:
        return Vector2(new_target)
    return player.target + delta.normalize() * max_shift


def predict_intercept(player, ball):
    """
    Earliest point on the ball's (friction-slowed) path that this player can
    reach in time, at a height he can control.  Falls back to where the ball
    will stop, kept inside the pitch.
    """
    import core.locomotion as locomotion
    v = ball.vel.length()
    if v < 0.5:
        return Vector2(ball.pos)
    direction = ball.vel / v
    run_speed = locomotion.top_speed_ms(player) * M_TO_PX * 0.9
    # He has to get up to speed first (it used to assume he was already
    # flying, so he picked spots on the ball's path he couldn't reach in time
    # and arrived just after it had gone past)
    accel = (locomotion.ACCEL_BASE + locomotion.ACCEL_PER_POINT * locomotion._stat(player, "Acceleration")) \
        * M_TO_PX * 0.75                        # average, allowing for it fading near top speed
    reaction = 0.15

    def time_to(point):
        to_p = point - player.pos
        d = to_p.length()
        if d < 1e-6:
            return reaction
        v0 = max(0.0, min(run_speed, player.vel.dot(to_p / d)))
        t_acc = (run_speed - v0) / accel
        d_acc = (v0 + run_speed) * 0.5 * t_acc
        if d <= d_acc:
            return reaction + (-v0 + math.sqrt(v0 * v0 + 2.0 * accel * d)) / accel
        return reaction + t_acc + (d - d_acc) / run_speed

    point = Vector2(ball.pos)
    for i in range(1, 41):                       # look up to 4 s ahead
        t = i * 0.1
        travelled = v * (1.0 - _BALL_K_PER_SEC ** t) / _BALL_NEG_LOG_K
        point = ball.pos + direction * travelled
        if not (0 <= point.x <= WIDTH and 0 <= point.y <= HEIGHT):
            # Ball will go out before he gets there: aim for where it leaves
            point.x = clamp(point.x, 0, WIDTH)
            point.y = clamp(point.y, 0, HEIGHT)
            return point
        z = ball.z + ball.vz * t - 0.5 * GRAVITY * t * t
        if z > 2.0 * M_TO_PX:
            continue                             # still too high to control
        if time_to(point) <= t:
            return point
    return point


def handle_possession_movement(team, opponents, ball, ball_owner, current_time=None):
    """
    Updated: run-commitment system for strikers + shorter post-pass hold for STs.
    Also adds:
      - Anticipatory ball position: support targets are computed from where the
        ball WILL be in ~0.5 s, not where it is now.  Players create angles
        before they're needed rather than reacting after the fact.
      - Per-player update interval: support targets are recalculated every 0.2 s
        instead of every frame.  Between updates players keep walking to the same
        spot, which looks deliberate rather than frantically re-targeting.
    """
    ball_cell = _stable_ball_cell(ball)

    # ------------------------------------------------------------------
    # ANTICIPATORY BALL POSITION
    # Project the ball 0.5 s forward (friction-corrected) so that support
    # positions are computed for where the ball is likely to end up.
    # Players will already be in position when the ball arrives.
    # ------------------------------------------------------------------
    _ANTICIPATE_T = 0.5          # seconds to look ahead
    _v = ball.vel.length()
    if _v > 0.5:
        _k_t = _BALL_K_PER_SEC ** _ANTICIPATE_T
        _ahead = _v * (1.0 - _k_t) / _BALL_NEG_LOG_K
        _pred_pos = ball.pos + ball.vel.normalize() * _ahead
    else:
        _pred_pos = Vector2(ball.pos)
    predicted_ball_cell = grid_cell_from_position(_pred_pos)

    # How often support players recompute their role target.
    # 0.2 s gives smooth, committed movement without constant micro-adjustment.
    _SUPPORT_UPDATE_INTERVAL = 0.2

    shape = None          # the team's shape, worked out once when someone needs it

    for player in team:
        if player == ball_owner or player.role == "GK":
            continue

        # Post-pass hold: shorter for strikers so they can make give-and-go runs
        if current_time and hasattr(player, 'last_pass_time'):
            time_since_pass = current_time - player.last_pass_time
            hold_duration = 0.15 if player.role in ("ST1", "ST2") else 0.6
            if time_since_pass < hold_duration:
                player.target = Vector2(player.pos)
                player.state = "hold"
                player.pos_reason = "just passed"
                continue

        # (Strikers used to be planted at the end of a run until a timer ran
        # out - even with play elsewhere.  Runs now come from ai/run_planner.py,
        # which overrides this positioning while a run is on.)

        # Check if this player is the intended pass receiver
        is_receiving = False
        if getattr(ball, 'intended_target', None) == player:
            is_receiving = True
        elif ball.owner is None and (ball.pos - player.pos).length() < 15 * M_TO_PX:
            to_me = player.pos - ball.pos
            if ball.vel.length_squared() > 0.1 and to_me.length_squared() > 0:
                angle = ball.vel.normalize().dot(to_me.normalize())
                if angle > 0.8:
                    is_receiving = True
            elif ball.vel.length_squared() <= 0.1:
                is_receiving = True

        if is_receiving:
            # Run to the earliest point on the ball's path he can actually
            # reach (players now accelerate realistically, so aiming at where
            # the ball will be in 0.2 s left receivers trailing behind passes).
            intercept_pos = predict_intercept(player, ball)

            player.target = intercept_pos
            player.state = "chase"
            player.pos_reason = "receive pass"
            import core.clock as clock
            player._receiving_at = clock.now()          # core/locomotion.py: meet it, don't park
        else:
            # Support positioning — rate-limited and anticipatory.
            #
            # Only recompute the role target every _SUPPORT_UPDATE_INTERVAL
            # seconds.  In between, the player keeps walking to the same spot.
            # This stops the constant per-frame micro-adjustments that make
            # off-ball movement look frantic.
            #
            # Role targets are computed from predicted_ball_cell (0.5 s ahead)
            # rather than the current ball cell, so players are creating angles
            # BEFORE the ball arrives rather than reacting after.
            _next_update = getattr(player, '_next_pos_update', 0.0)
            _should_update = (current_time is None or current_time >= _next_update)

            if _should_update:
                # His place in the team's shape (ai/team_shape.py)
                if shape is None:
                    shape = team_shape.compute(team, opponents, ball, True, current_time or 0.0)
                spot, why = shape.get(id(player), (Vector2(player.pos), "hold"))
                # (no target smoothing needed: the shape moves continuously with the
                # ball now - the old grid-square roles needed it, and it made targets
                # crawl at 5 m/s when the whole shape changed after a turnover)
                player.target = Vector2(spot)
                player._shape_reason = why
                if current_time is not None:
                    player._next_pos_update = current_time + _SUPPORT_UPDATE_INTERVAL
            # else: player keeps walking toward existing target — no update needed

            player.state = "support"
            player.pos_reason = getattr(player, "_shape_reason", "support")



def handle_defensive_movement(team, opponents, ball, ball_owner, team_has_possession, current_time=0.0):
    """All defending outfielders take their place in the team's defensive block."""
    shape = team_shape.compute(team, opponents, ball, False, current_time)
    for player in team:
        if player.role == "GK":
            continue
        spot, why = shape.get(id(player), (Vector2(player.pos), "hold"))
        player.target = Vector2(spot)
        player.state = "defend"
        player.pos_reason = why


def apply_dynamic_spacing(team, ball_owner):
    """
    Gently steers formation targets apart to prevent crowding.

    KEY FIX: now uses actual player POSITIONS (not formation targets) for all
    distance calculations.  The old code used target-to-target distances, which
    caused a hard-to-spot teleporting bug: when two players shared the same
    formation target (dist → 0) the code fell back to
        Vector2(random.uniform(-1,1), random.uniform(-1,1)).normalize()
    producing a completely different push direction every frame → target jumped
    randomly → players visibly teleported.

    Using player.pos gives a stable, non-oscillating direction because positions
    change smoothly.  Physical body separation (< 0.65 m) is already handled by
    the collision resolution inside Player._update_normal_movement; we only need
    a light steering nudge here to spread formation targets apart.
    """
    MIN_SEPARATION = 3.5 * M_TO_PX      # 3.5 m between any two outfielders
    CARRIER_SEPARATION = 6.0 * M_TO_PX  # 6 m clear space around the ball carrier

    for player in team:
        if player == ball_owner or player.role == "GK":
            continue

        avoidance = Vector2(0, 0)

        # 1. Carrier bubble — steer away from whoever has the ball
        if ball_owner:
            diff = player.pos - ball_owner.pos
            dist_to_carrier = diff.length()
            if 0 < dist_to_carrier < CARRIER_SEPARATION:
                push_strength = (CARRIER_SEPARATION - dist_to_carrier) * 0.35
                avoidance += diff.normalize() * push_strength

        # 2. Teammate separation — use actual positions so direction is always stable
        for other in team:
            if player == other or other.role == "GK":
                continue

            diff = player.pos - other.pos
            dist = diff.length()

            # Guard: only push if players are physically close AND diff is non-zero.
            # The dist > 0 guard prevents the random-direction fallback entirely.
            if 0 < dist < MIN_SEPARATION:
                push = (MIN_SEPARATION - dist) * 0.25
                avoidance += diff.normalize() * push

        # Apply steering force to the formation target (not position — no snapping)
        if avoidance.length_squared() > 0:
            player.target += avoidance
            player.target.x = clamp(player.target.x, 20, WIDTH - 20)
            player.target.y = clamp(player.target.y, 20, HEIGHT - 20)
