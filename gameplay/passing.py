# ===========================================================================
# gameplay/passing.py
# ===========================================================================

import random
import math
from pygame.math import Vector2
from core.utils import distance, clamp, segment_point_distance
from config.constants import *
import core.world as world

# ---------------------------------------------------------------------------
# PASS ACCURACY TUNING (degrees / fractions; stats on the 1-20 scale)
# ---------------------------------------------------------------------------
# Every pass now has a small error in direction and in weight (speed), so
# passes can be misplaced, under/over-hit, and intercepted - previously every
# pass went exactly to the receiver's feet whatever the Passing stat.
PASS_ANGLE_BASE      = 1.0    # degrees (standard deviation) for a perfect passer...
PASS_ANGLE_PER_POINT = 0.30   # ...plus this per Passing point below 20 (13 -> 3.1 deg)
PASS_ANGLE_PER_M     = 0.06   # extra degrees per metre beyond 20 m (long passes)
PASS_WEIGHT_SD       = 0.08   # speed error (fraction) for an average passer
PASS_PRESSURE_RADIUS = 2.5    # m: an opponent this close puts the passer under pressure
PASS_PRESSURE_EXTRA  = 0.8    # error multiplier added under pressure (reduced by Composure)
PASS_MOVING_EXTRA    = 0.15   # extra error when passing at a sprint
THROUGH_ERROR_MULT   = 1.25   # through balls into space are harder to weight and place

# ---------------------------------------------------------------------------
# Friction correction constants
# ---------------------------------------------------------------------------
# Ball friction: 0.992 multiplied per frame at 60fps.
# Speed remaining after 1 real second = 0.992^60 ≈ 0.617.
# A pass kicked at speed V travels  d = V * (1 - k^t) / (-ln k)  pixels in t s.
# Solving for V: V = d * (-ln k) / (1 - k^t)
# Without this correction, base_speed = dist/time assumes constant speed and
# consistently underestimates the required kick velocity → ball dies short.
_FRICTION_PER_SEC = 0.992 ** 60          # ≈ 0.617  (ground)
_NEG_LOG_FRICTION = -math.log(_FRICTION_PER_SEC)   # ≈ 0.481

_FRICTION_AIR     = 0.995 ** 60          # ≈ 0.741  (aerial — ball.update uses 0.995 when z > 0.1)
_NEG_LOG_AIR      = -math.log(_FRICTION_AIR)       # ≈ 0.300


def _stat(player, name):
    v = player.attributes.get(name, 10)
    if v > 25:
        v /= 5.0
    return clamp(v, 1, 20)


def _apply_pass_error(passer, pass_target, speed, dist_m, difficulty=1.0):
    """Return (speed, target) with a realistic execution error applied."""
    passing = _stat(passer, "Passing")
    composure = _stat(passer, "Composure")

    error = 1.0
    if getattr(passer, "_hurried", False):          # rushed it (ai/decision_timing.py)
        import ai.decision_timing as timing
        error *= timing.HURRY_ERROR
        passer._hurried = False
    opps = world.opponents_of(passer) if world.players else []
    if opps:
        nearest = min(distance(passer.pos, o.pos) for o in opps) / M_TO_PX
        if nearest < PASS_PRESSURE_RADIUS:
            error += PASS_PRESSURE_EXTRA * (1.0 - composure / 20.0) * (1.0 - nearest / PASS_PRESSURE_RADIUS + 0.3)
    if passer.vel.length() > MAX_SPEED * 0.7:
        error += PASS_MOVING_EXTRA

    angle_sd = (PASS_ANGLE_BASE + PASS_ANGLE_PER_POINT * (20 - passing)
                + PASS_ANGLE_PER_M * max(0.0, dist_m - 20.0)) * error * difficulty
    weight_sd = PASS_WEIGHT_SD * (1.6 - passing / 20.0) * error * difficulty

    to_target = pass_target - passer.pos
    if to_target.length_squared() > 0:
        pass_target = passer.pos + to_target.rotate(random.gauss(0.0, angle_sd))
    speed *= max(0.6, random.gauss(1.0, weight_sd))
    return speed, pass_target


def execute_pass(passer, receiver, ball, current_time, opponents=None, through_plan=None):
    """
    Execute a pass from passer to receiver.

    Pass speed is friction-corrected so the ball actually reaches the receiver
    in the intended time regardless of deceleration.  Aerial passes use the
    air-friction constant (0.995/frame) rather than the ground constant (0.992)
    because the ball decelerates less while in flight.
    """

    dist_to_receiver = distance(passer.pos, receiver.pos)
    dist_meters = dist_to_receiver / M_TO_PX

    # =========================================================================
    # STEP 1: Ideal travel time (distance-based)
    # =========================================================================
    if dist_meters < 10:
        ideal_time = 0.8
    elif dist_meters < 20:
        ideal_time = 0.8 + (dist_meters - 10) * 0.05
    elif dist_meters < 35:
        ideal_time = 1.3 + (dist_meters - 20) * 0.04
    else:
        ideal_time = 1.9 + (dist_meters - 35) * 0.03

    # =========================================================================
    # STEP 2: Elevation — calculated BEFORE speed so we know which friction
    #         constant to use.  Lofted passes travel in air (friction=0.995/frame)
    #         which decelerates the ball far less than ground (0.992/frame).
    #         Using the wrong constant makes aerial passes overpowered.
    # =========================================================================
    elevation = calculate_pass_elevation(
        passer.pos, receiver.pos, dist_meters, opponents
    )

    # =========================================================================
    # STEP 3: Friction-corrected speed
    #         V = d · (-ln k) / (1 - k^t)
    #         k = per-second speed retention (ground ≈ 0.617, air ≈ 0.741)
    # =========================================================================
    MIN_SPEED = 4.0 * M_TO_PX
    MAX_SPEED = 32.0 * M_TO_PX

    # Ground: 0.992^60 ≈ 0.617  Air: 0.995^60 ≈ 0.741  (module-level constants)
    if elevation > 0:
        k          = _FRICTION_AIR
        neg_log_k  = _NEG_LOG_AIR
    else:
        k          = _FRICTION_PER_SEC
        neg_log_k  = _NEG_LOG_FRICTION

    k_t = k ** ideal_time
    if k_t < 0.9999:
        base_speed = dist_to_receiver * neg_log_k / (1.0 - k_t)
    else:
        base_speed = dist_to_receiver / max(ideal_time, 0.01)

    # Global trim: friction-corrected speed is correct in theory but passes
    # look slightly too crisp; shave 8% off universally.
    base_speed *= 0.92

    # Lofted correction: we assumed 100% air friction, but the ball spends
    # some time rolling after landing.  Scale back lofted passes further so
    # they don't fly through the target.
    if elevation > 0:
        base_speed *= 0.78

    final_speed = clamp(base_speed, MIN_SPEED, MAX_SPEED)

    # =========================================================================
    # STEP 4: Through ball or normal pass?
    #         Normal passes aim at the receiver's current position (feet).
    #         The receiver's intended_target / intercept_pos logic in
    #         handle_possession_movement already moves them toward the ball —
    #         adding a positional lead on top causes double-correction overshoot.
    # =========================================================================
    # Normal passes go to the receiver's feet; a THROUGH BALL goes into the
    # space where the runner will be (planned in gameplay/through_pass.py),
    # hit along the ground at the speed that makes them arrive together.
    if through_plan is not None:
        pass_target = Vector2(through_plan["point"])
        final_speed = through_plan["speed_px"]
        elevation = 0.0
        dist_meters = distance(passer.pos, pass_target) / M_TO_PX
        difficulty = THROUGH_ERROR_MULT
    else:
        pass_target = Vector2(receiver.pos)
        difficulty = 1.0

    # =========================================================================
    # STEP 4b: Execution error - direction and weight
    # =========================================================================
    final_speed, pass_target = _apply_pass_error(passer, pass_target, final_speed, dist_meters, difficulty)

    passer.state = "pass"

    # =========================================================================
    # STEP 5: Execute the kick!
    # =========================================================================
    kick_vec = pass_target - passer.pos
    if kick_vec.length_squared() > 0:
        ball.kick(kick_vec.normalize() * final_speed, kicker=passer, elevation=elevation)
    else:
        # Fallback if math breaks
        ball.kick(Vector2(1, 0) * final_speed, kicker=passer, elevation=elevation)
    
    ball.intended_target = receiver
    ball.through_plan = through_plan
    ball.last_kick_time = current_time
    ball.last_owner = passer
    passer.has_ball = False
    
    # 🔧 FIX #3: Give passer a cooldown so they don't chase their own pass!
    # This makes them hold position for 0.6 seconds
    passer.last_pass_time = current_time


# =============================================================================
# THROUGH BALL DETECTION (UNCHANGED - already good!)
# =============================================================================

def check_through_ball_conditions(passer, receiver, attack_dir, opponents):
    """
    STEP 1: Is this even a through ball situation?
    
    A through ball needs:
    1. Receiver running fast (not standing still)
    2. Receiver running FORWARD (toward goal)
    3. Space ahead to run into
    4. Distance between 8-35 meters
    """
    
    # Check 1: Is receiver moving fast enough?
    receiver_speed = receiver.vel.length()
    if receiver_speed < 5.0 * M_TO_PX:
        return False  # Walking pace = not a through ball
    
    # Check 2: Is receiver running FORWARD?
    move_direction = receiver.vel.normalize()
    forward_component = move_direction.dot(attack_dir)
    
    if forward_component < 0.5:
        return False  # Not running toward goal
    
    # Check 3: Distance check
    dist = distance(passer.pos, receiver.pos) / M_TO_PX
    if dist < 8 or dist > 35:
        return False  # Too close or too far
    
    # Check 4: Is there space ahead?
    space_ahead = check_space_ahead(receiver, attack_dir, opponents)
    if space_ahead < 5.0:
        return False  # No room to run
    
    return True  # All conditions met!


def check_space_ahead(receiver, attack_dir, opponents):
    """
    How much clear space does the receiver have in front of them?
    Like asking: "How far can they run before hitting a defender?"
    """
    
    if not opponents:
        return 999.0  # No opponents = infinite space!
    
    check_distance = 0.0
    max_check = 30.0
    
    while check_distance < max_check:
        check_distance += 5.0
        
        # Where will receiver be if they keep running?
        future_pos = receiver.pos + attack_dir * (check_distance * M_TO_PX)
        
        # Any defender close to this spot?
        for defender in opponents:
            dist_to_defender = distance(future_pos, defender.pos) / M_TO_PX
            
            if dist_to_defender < 3.0:
                return check_distance - 5.0  # Found a blocker
    
    return max_check  # Made it all the way!


def calculate_through_ball(passer, receiver, attack_dir, opponents, base_speed):
    """
    STEP 2: Calculate the perfect through ball.
    
    Like a quarterback throwing to a running receiver!
    """
    
    receiver_speed = receiver.vel.length()
    run_direction = receiver.vel.normalize()
    
    # 🔧 FIX #4: Pull the run direction toward goal (stop sideways drift!)
    # If receiver is drifting wide, we correct it toward goal
    goal_bias = 0.7  # 70% toward goal, 30% follow their run
    run_direction = (run_direction * (1 - goal_bias) + attack_dir * goal_bias).normalize()
    
    # =========================================================================
    # Calculate how far ahead to put the ball
    # =========================================================================
    
    # Base lead: 2m for slow runs, up to 5m for sprints
    speed_ratio = receiver_speed / (MAX_SPEED_M * M_TO_PX)
    base_lead = 2.0 + (speed_ratio * 3.0)
    
    # Don't lead into a defender
    space_ahead = check_space_ahead(receiver, attack_dir, opponents)
    if space_ahead < base_lead:
        base_lead = space_ahead * 0.7
    
    # Calculate target position
    lead_distance_meters = base_lead
    target_position = receiver.pos + run_direction * (lead_distance_meters * M_TO_PX)
    
    # =========================================================================
    # Safety checks
    # =========================================================================
    
    # Out of bounds?
    if target_position.x < 0 or target_position.x > WIDTH:
        return {'execute': False, 'target': receiver.pos, 'speed': base_speed, 'lead_distance': 0}
    
    if target_position.y < 0 or target_position.y > HEIGHT:
        return {'execute': False, 'target': receiver.pos, 'speed': base_speed, 'lead_distance': 0}
    
    # Will defenders intercept?
    will_intercept = check_through_ball_interception(
        passer.pos,
        target_position,
        opponents,
        base_speed
    )
    
    if will_intercept:
        return {'execute': False, 'target': receiver.pos, 'speed': base_speed, 'lead_distance': 0}
    
    # Base speed is already friction-corrected; no multiplier needed.
    # Through ball target placement provides the lead — speed stays accurate.
    return {
        'execute': True,
        'target': target_position,
        'speed': base_speed,
        'lead_distance': lead_distance_meters
    }


def check_through_ball_interception(pass_start, pass_end, opponents, ball_speed):
    """
    Will any defender intercept this through ball?
    """
    
    if not opponents:
        return False
    
    pass_distance = distance(pass_start, pass_end)
    if pass_distance < 1:
        return False
    
    pass_direction = (pass_end - pass_start).normalize()
    ball_time = pass_distance / ball_speed
    
    for defender in opponents:
        # How far from the passing lane?
        dist_to_lane = segment_point_distance(pass_start, pass_end, defender.pos)
        
        if dist_to_lane > 4.0 * M_TO_PX:
            continue  # Too far away
        
        # Where would they intercept?
        to_defender = defender.pos - pass_start
        projection = to_defender.dot(pass_direction)
        
        if projection < 0 or projection > pass_distance:
            continue  # Behind or beyond the pass
        
        intercept_point = pass_start + pass_direction * projection
        
        # Can defender get there in time?
        defender_distance = distance(defender.pos, intercept_point)
        defender_speed = 8.0 * M_TO_PX
        defender_time = defender_distance / defender_speed
        
        ball_time_to_intercept = projection / ball_speed
        
        if defender_time < (ball_time_to_intercept - 0.2):
            return True  # Defender will intercept!
    
    return False


# =============================================================================
# ELEVATION LOGIC (UNCHANGED)
# =============================================================================

def calculate_pass_elevation(passer_pos, receiver_pos, dist_meters, opponents):
    """
    Should we loft this pass over defenders?
    """
    
    if opponents is None:
        opponents = []
    
    defenders_blocking = count_defenders_in_lane(passer_pos, receiver_pos, opponents)
    
    if defenders_blocking >= 2 and dist_meters > 12:
        elevation = 0.5 + (defenders_blocking * 0.1)
        elevation = min(elevation, 0.8)
    elif defenders_blocking == 1 and dist_meters > 15:
        elevation = 0.3
    elif dist_meters > 40:
        elevation = 0.6
    elif dist_meters > 25 and defenders_blocking > 0:
        elevation = 0.2
    else:
        elevation = 0.0
    
    return elevation


def count_defenders_in_lane(passer_pos, receiver_pos, opponents):
    """Count defenders blocking the passing lane."""
    
    if not opponents:
        return 0
    
    pass_vector = receiver_pos - passer_pos
    pass_length = pass_vector.length()
    
    if pass_length < 1:
        return 0
    
    pass_direction = pass_vector.normalize()
    blockers = 0
    
    BLOCKING_RADIUS = 3.0 * M_TO_PX
    
    for defender in opponents:
        to_defender = defender.pos - passer_pos
        progress = to_defender.dot(pass_direction) / pass_length
        
        if progress < 0.05 or progress > 0.95:
            continue
        
        closest_point = passer_pos + pass_direction * (progress * pass_length)
        perp_dist = distance(defender.pos, closest_point)
        
        if perp_dist < BLOCKING_RADIUS:
            blockers += 1
    
    return blockers