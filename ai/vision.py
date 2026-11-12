# ===========================================================================
# ai/vision.py
# Realistic player vision system - players can only pass to what they can see!
# ===========================================================================

import math
from pygame.math import Vector2
from core.utils import distance, segment_point_distance
from config.constants import WIDTH, HEIGHT, M_TO_PX

# =============================================================================
# VISION CONSTANTS
# =============================================================================

# Vision cone angles (in degrees)
COMPOSED_CONE_ANGLE = 160  # Full vision when under no pressure
PRESSURED_CONE_ANGLE = 120  # Tunnel vision when being closed down

# Vision distances
COMPOSED_VISION_RANGE = 45 * M_TO_PX  # Can see 45m ahead when composed
PRESSURED_VISION_RANGE = 20 * M_TO_PX  # Only 20m when panicking

# Peripheral awareness (360° "feel")
PERIPHERAL_RADIUS = 5 * M_TO_PX  # Can "sense" teammates within 5m

# Pressure detection
PRESSURE_DISTANCE = 3.0 * M_TO_PX  # Defender within 3m = under pressure

# Line of sight blocking
MIN_BLOCKERS_TO_OBSCURE = 2  # Need 2+ defenders to block vision
BLOCKING_CORRIDOR_WIDTH = 3.0 * M_TO_PX  # How wide the "blocking zone" is

# Memory/scanning (for future implementation)
SCAN_MEMORY_DURATION = 2.0  # Seconds before you "forget" where someone was


# =============================================================================
# MAIN VISION CHECK
# =============================================================================

def can_see_teammate(passer, target_teammate, opponents):
    """
    Can the passer see the target teammate well enough to attempt a pass?
    
    Returns: (can_see: bool, reason: str)
    
    Reasons:
    - "peripheral" - Very close, can sense them
    - "clear_view" - In vision cone, no blockers
    - "blocked" - Too many defenders in the way
    - "out_of_cone" - Behind you / not looking that way
    - "too_far" - Beyond vision range
    """
    
    # STEP 1: Peripheral Awareness (Always works for close teammates)
    dist_to_target = distance(passer.pos, target_teammate.pos)
    
    if dist_to_target < PERIPHERAL_RADIUS:
        return True, "peripheral"
    
    # STEP 2: Check if under pressure
    under_pressure = is_under_pressure(passer, opponents)
    
    # STEP 3: Get vision parameters based on pressure state
    if under_pressure:
        cone_angle = PRESSURED_CONE_ANGLE
        vision_range = PRESSURED_VISION_RANGE
    else:
        cone_angle = COMPOSED_CONE_ANGLE
        vision_range = COMPOSED_VISION_RANGE
    
    # STEP 4: Distance check
    if dist_to_target > vision_range:
        return False, "too_far"
    
    # STEP 5: Vision cone check (Are they in front of me?)
    if not is_in_vision_cone(passer, target_teammate.pos, cone_angle):
        return False, "out_of_cone"
    
    # STEP 6: Line of sight check (Are defenders blocking my view?)
    num_blockers = count_blockers_in_sight_line(
        passer.pos, 
        target_teammate.pos, 
        opponents
    )
    
    if num_blockers >= MIN_BLOCKERS_TO_OBSCURE:
        return False, "blocked"
    
    # All checks passed!
    return True, "clear_view"


# =============================================================================
# VISION CONE GEOMETRY
# =============================================================================

def is_in_vision_cone(passer, target_pos, cone_angle_degrees):
    """
    Check if target position is within player's vision cone.
    
    The cone is centered on the player's facing direction.
    """
    
    # Get direction from passer to target
    to_target = target_pos - passer.pos
    
    if to_target.length_squared() < 0.1:
        return True  # Target is basically on top of us
    
    to_target_normalized = to_target.normalize()
    
    # Get passer's facing direction
    facing = passer.facing
    if facing.length_squared() < 0.1:
        # Player has no facing direction, use team attack direction
        facing = Vector2(1, 0) if passer.team == 0 else Vector2(-1, 0)
    else:
        facing = facing.normalize()
    
    # Calculate angle between facing and target
    # Using dot product: cos(angle) = A·B
    dot = facing.dot(to_target_normalized)
    angle_between = math.degrees(math.acos(max(-1, min(1, dot))))
    
    # Check if within cone (half-angle on each side)
    half_cone = cone_angle_degrees / 2
    
    return angle_between <= half_cone


# =============================================================================
# LINE OF SIGHT BLOCKING
# =============================================================================

def count_blockers_in_sight_line(passer_pos, target_pos, opponents):
    """
    Count how many defenders are blocking the line of sight.
    
    A defender blocks if they're:
    1. In the corridor between passer and target
    2. Close enough to the line to obscure vision
    """
    
    if not opponents:
        return 0
    
    blocker_count = 0
    
    for defender in opponents:
        # Skip goalkeepers (they don't block vision from outfield)
        if hasattr(defender, 'role') and defender.role == "GK":
            continue
        
        # Calculate perpendicular distance from defender to passing line
        perp_dist = segment_point_distance(passer_pos, target_pos, defender.pos)
        
        if perp_dist < BLOCKING_CORRIDOR_WIDTH:
            # Defender is close to the line, check if they're actually between passer and target
            pass_vector = target_pos - passer_pos
            to_defender = defender.pos - passer_pos
            
            # Project defender onto pass vector
            pass_length = pass_vector.length()
            if pass_length < 1:
                continue
            
            projection = to_defender.dot(pass_vector) / pass_length
            
            # Defender must be between 10% and 90% of the way to the target to block
            if 0.1 < projection < 0.9 * pass_length:
                blocker_count += 1
    
    return blocker_count


# =============================================================================
# PRESSURE DETECTION
# =============================================================================

def is_under_pressure(player, opponents):
    """
    Determine if player is under defensive pressure.
    
    Under pressure means:
    - At least one opponent within 3 meters
    """
    
    if not opponents:
        return False
    
    for opponent in opponents:
        if distance(player.pos, opponent.pos) < PRESSURE_DISTANCE:
            return True
    
    return False


# =============================================================================
# SPECIAL CASE CHECKS
# =============================================================================

def is_cross_situation(passer, target_pos):
    """
    Check if this is a crossing situation (special rules apply).
    
    Crosses don't need vision checks because you're just whipping it into a zone.
    
    A cross is:
    - Wide position (near touchline)
    - Target is in the box area
    - Distance > 15m
    """
    
    # Check if passer is wide
    is_wide = (passer.pos.y < 20 * M_TO_PX) or (passer.pos.y > HEIGHT - 20 * M_TO_PX)
    
    if not is_wide:
        return False
    
    # Check if target is in box area
    goal_x = WIDTH if passer.team == 0 else 0
    box_center = Vector2(goal_x, HEIGHT / 2)
    dist_to_box_center = distance(target_pos, box_center)
    
    in_box_area = dist_to_box_center < 25 * M_TO_PX
    
    # Check distance
    pass_distance = distance(passer.pos, target_pos)
    is_long_enough = pass_distance > 15 * M_TO_PX
    
    return is_wide and in_box_area and is_long_enough


def is_clearance_situation(passer, opponents):
    """
    Check if player should just clear it (panic situation).
    
    Clearances ignore vision because you're just booting it away.
    """
    
    # Deep in own half
    if passer.team == 0:
        in_danger_zone = passer.pos.x < 25 * M_TO_PX
    else:
        in_danger_zone = passer.pos.x > WIDTH - 25 * M_TO_PX
    
    if not in_danger_zone:
        return False
    
    # Multiple opponents very close
    close_opponents = [
        o for o in opponents 
        if distance(passer.pos, o.pos) < 2.5 * M_TO_PX
    ]
    
    return len(close_opponents) >= 2


# =============================================================================
# DEBUG / VISUALIZATION HELPERS
# =============================================================================

def get_vision_cone_points(player, num_points=20):
    """
    Get list of points defining the player's vision cone.
    Useful for debugging/visualization.
    
    Returns list of Vector2 points.
    """
    
    # Determine cone parameters
    opponents = []  # Would need to pass this in for real use
    under_pressure = False  # Simplified for visualization
    
    cone_angle = PRESSURED_CONE_ANGLE if under_pressure else COMPOSED_CONE_ANGLE
    vision_range = PRESSURED_VISION_RANGE if under_pressure else COMPOSED_VISION_RANGE
    
    facing = player.facing
    if facing.length_squared() < 0.1:
        facing = Vector2(1, 0) if player.team == 0 else Vector2(-1, 0)
    else:
        facing = facing.normalize()
    
    # Calculate cone edges
    half_angle = math.radians(cone_angle / 2)
    facing_angle = math.atan2(facing.y, facing.x)
    
    points = [player.pos]  # Start at player
    
    # Left edge of cone
    for i in range(num_points + 1):
        t = i / num_points
        angle = facing_angle - half_angle + (2 * half_angle * t)
        point = player.pos + Vector2(
            math.cos(angle) * vision_range,
            math.sin(angle) * vision_range
        )
        points.append(point)
    
    points.append(player.pos)  # Close the shape
    
    return points


def get_vision_debug_info(passer, target, opponents):
    """
    Get detailed debug information about a vision check.
    Returns a dictionary with all the details.
    """
    
    can_see, reason = can_see_teammate(passer, target, opponents)
    
    dist = distance(passer.pos, target.pos)
    under_pressure = is_under_pressure(passer, opponents)
    blockers = count_blockers_in_sight_line(passer.pos, target.pos, opponents)
    
    cone_angle = PRESSURED_CONE_ANGLE if under_pressure else COMPOSED_CONE_ANGLE
    in_cone = is_in_vision_cone(passer, target.pos, cone_angle)
    
    return {
        "can_see": can_see,
        "reason": reason,
        "distance_m": dist / M_TO_PX,
        "under_pressure": under_pressure,
        "in_cone": in_cone,
        "num_blockers": blockers,
        "cone_angle": cone_angle
    }