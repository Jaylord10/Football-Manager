# ===========================================================================
# ai/smart_dribbling.py
# Makes players dribble intelligently - avoiding defenders while moving forward!
# ===========================================================================

import math
from pygame.math import Vector2
from core.utils import distance, clamp
from config.constants import WIDTH, HEIGHT, M_TO_PX


def calculate_smart_dribble_target(dribbler, opponents, goal_pos):
    """
    SMART DRIBBLING SYSTEM
    
    Instead of running straight at goal, we:
    1. Look at 5 different directions (angles)
    2. See which direction has the most space
    3. Pick the best one that still moves us toward goal
    
    Like a kid running through a playground - you go forward but dodge around people!
    
    Args:
        dribbler: The player with the ball
        opponents: List of enemy players
        goal_pos: Where the goal is
    
    Returns:
        Vector2: The smart place to dribble toward
    """
    
    # =========================================================================
    # STEP 1: What direction is "straight at goal"?
    # =========================================================================
    to_goal = goal_pos - dribbler.pos
    
    if to_goal.length_squared() < 1:
        # We're basically AT the goal already!
        return goal_pos
    
    ideal_direction = to_goal.normalize()
    ideal_angle = math.degrees(math.atan2(ideal_direction.y, ideal_direction.x))
    
    # =========================================================================
    # STEP 2: Create 5 different directions to check
    # =========================================================================
    # We'll check:
    # - Straight ahead (0 degrees from ideal)
    # - Slightly left (-30 degrees)
    # - More left (-60 degrees)  
    # - Slightly right (+30 degrees)
    # - More right (+60 degrees)
    
    angles_to_check = [
        0,      # Straight
        -30,    # Left a bit
        -60,    # Left more
        30,     # Right a bit
        60      # Right more
    ]
    
    # =========================================================================
    # STEP 3: Score each direction (which is safest + moves us forward?)
    # =========================================================================
    best_direction = ideal_direction
    best_score = -9999
    
    for angle_offset in angles_to_check:
        # Calculate this direction
        test_angle = ideal_angle + angle_offset
        test_rad = math.radians(test_angle)
        
        test_direction = Vector2(
            math.cos(test_rad),
            math.sin(test_rad)
        )
        
        # Where would we end up if we dribbled this way?
        dribble_distance = 8 * M_TO_PX  # Look 8 meters ahead
        test_position = dribbler.pos + test_direction * dribble_distance
        
        # Make sure it's on the pitch!
        if not (0 < test_position.x < WIDTH and 0 < test_position.y < HEIGHT):
            continue  # Skip this direction, it goes off the pitch
        
        # =====================================================================
        # SCORING: How good is this direction?
        # =====================================================================
        score = 0
        
        # A) SPACE SCORE (Most Important! - 60% of decision)
        # How far are defenders from this direction?
        space_score = calculate_space_score(test_position, opponents)
        score += space_score * 60
        
        # B) PROGRESS SCORE (Important - 30% of decision)  
        # Does this direction move us toward goal?
        progress_score = calculate_progress_score(
            dribbler.pos, 
            test_position, 
            goal_pos
        )
        score += progress_score * 30
        
        # C) ANGLE PENALTY (Small - 10% of decision)
        # Don't go too sideways/backwards
        angle_penalty = abs(angle_offset) / 60.0  # 0.0 to 1.0
        score -= angle_penalty * 10
        
        # =====================================================================
        # Is this the best direction so far?
        # =====================================================================
        if score > best_score:
            best_score = score
            best_direction = test_direction
    
    # =========================================================================
    # STEP 4: Return the target position
    # =========================================================================
    # 7 m committed run — enough to look purposeful without over-committing into
    # a defender.  The old 4 m target made players take tiny shuffling steps and
    # re-evaluate every fraction of a second, which looked robotic and hesitant.
    final_distance = 7 * M_TO_PX
    target = dribbler.pos + best_direction * final_distance
    
    # Make sure it's on the pitch
    target.x = clamp(target.x, 2 * M_TO_PX, WIDTH - 2 * M_TO_PX)
    target.y = clamp(target.y, 2 * M_TO_PX, HEIGHT - 2 * M_TO_PX)
    
    return target


# =============================================================================
# HELPER FUNCTIONS (The tools that make the magic work!)
# =============================================================================

def calculate_space_score(position, opponents):
    """
    HOW MUCH SPACE IS HERE?
    
    We check:
    - How far is the nearest defender?
    - Are there multiple defenders nearby?
    
    More space = Higher score!
    
    Returns: 0.0 to 100.0
    """
    
    if not opponents:
        return 100.0  # No opponents = infinite space!
    
    # Find nearest defender
    nearest_dist = min(distance(position, opp.pos) for opp in opponents)
    nearest_meters = nearest_dist / M_TO_PX
    
    # Count defenders within 5 meters
    close_defenders = sum(
        1 for opp in opponents 
        if distance(position, opp.pos) < 5 * M_TO_PX
    )
    
    # =========================================================================
    # SPACE SCORING
    # =========================================================================
    # Nearest defender distance:
    # - 8m+ away = 100 points (loads of space!)
    # - 5m away = 70 points (decent space)
    # - 3m away = 40 points (getting tight)
    # - 1m away = 0 points (very crowded!)
    
    if nearest_meters > 8:
        space_score = 100
    elif nearest_meters > 5:
        space_score = 70 + ((nearest_meters - 5) / 3) * 30
    elif nearest_meters > 3:
        space_score = 40 + ((nearest_meters - 3) / 2) * 30
    elif nearest_meters > 1:
        space_score = ((nearest_meters - 1) / 2) * 40
    else:
        space_score = 0
    
    # Penalty for multiple defenders nearby
    # Each extra defender = -15 points
    space_score -= (close_defenders - 1) * 15
    
    return clamp(space_score, 0, 100)


def calculate_progress_score(current_pos, new_pos, goal_pos):
    """
    DOES THIS MOVE US CLOSER TO GOAL?
    
    We check:
    - Are we getting closer to goal?
    - By how much?
    
    Better progress = Higher score!
    
    Returns: 0.0 to 100.0
    """
    
    # How far are we from goal right now?
    current_dist = distance(current_pos, goal_pos)
    
    # How far would we be after this dribble?
    new_dist = distance(new_pos, goal_pos)
    
    # Did we get closer or further?
    progress = current_dist - new_dist
    progress_meters = progress / M_TO_PX
    
    # =========================================================================
    # PROGRESS SCORING
    # =========================================================================
    # Moving forward:
    # - 5m+ closer = 100 points (great progress!)
    # - 3m closer = 70 points (good progress)
    # - 1m closer = 40 points (some progress)
    # - Same distance = 0 points (sideways)
    # - Moving away = negative points (bad!)
    
    if progress_meters > 5:
        return 100
    elif progress_meters > 3:
        return 70 + ((progress_meters - 3) / 2) * 30
    elif progress_meters > 1:
        return 40 + ((progress_meters - 1) / 2) * 30
    elif progress_meters > 0:
        return progress_meters * 40
    else:
        # Moving away from goal!
        return progress_meters * 50  # This will be negative


def check_path_is_clear(start_pos, end_pos, opponents, corridor_width=3*M_TO_PX):
    """
    IS THIS PATH BLOCKED BY DEFENDERS?
    
    Imagine drawing a line from start to end.
    We check if any defenders are standing on that line.
    
    Like checking if someone is blocking a hallway!
    
    Returns: True if clear, False if blocked
    """
    
    if not opponents:
        return True
    
    path_vector = end_pos - start_pos
    path_length = path_vector.length()
    
    if path_length < 1:
        return True
    
    path_direction = path_vector.normalize()
    
    for defender in opponents:
        # How far along the path is this defender?
        to_defender = defender.pos - start_pos
        projection = to_defender.dot(path_direction)
        
        # Is defender between start and end?
        if 0 < projection < path_length:
            # How far to the side of the path are they?
            closest_point = start_pos + path_direction * projection
            perpendicular_dist = distance(defender.pos, closest_point)
            
            # If they're close to the line, path is blocked!
            if perpendicular_dist < corridor_width:
                return False
    
    return True


# =============================================================================
# DRIBBLING SPEED CALCULATION
# =============================================================================

def calculate_dribble_speed(dribbler, target_pos, opponents):
    """
    HOW FAST SHOULD WE DRIBBLE?
    
    Rules:
    - Lots of space? → Dribble fast! (sprint)
    - Defenders nearby? → Dribble carefully (slow down)
    - Very tight? → Dribble very carefully (walk)
    
    Returns: Speed multiplier (0.6 to 1.2)
    """
    
    # Find nearest defender
    if opponents:
        nearest_dist = min(distance(dribbler.pos, opp.pos) for opp in opponents)
        nearest_meters = nearest_dist / M_TO_PX
    else:
        nearest_meters = 999
    
    # Get dribbling skill
    dribbling = dribbler.attributes.get("Dribbling", 10)
    if dribbling > 25:
        dribbling /= 5.0
    
    # =========================================================================
    # SPEED DECISIONS
    # =========================================================================
    
    if nearest_meters > 8:
        # Loads of space - SPRINT!
        base_speed = 1.2
        
    elif nearest_meters > 5:
        # Decent space - Run normally
        base_speed = 1.0
        
    elif nearest_meters > 3:
        # Getting tight - Careful dribbling
        base_speed = 0.85
        
    else:
        # Very tight - Very careful!
        base_speed = 0.65
    
    # =========================================================================
    # SKILL BONUS
    # =========================================================================
    # Better dribblers can go faster in tight spaces
    # (Think Messi vs a normal player!)
    
    if nearest_meters < 5:  # Only applies in tight spaces
        skill_bonus = (dribbling - 10) * 0.02  # Up to +0.2
        base_speed += skill_bonus
    
    return clamp(base_speed, 0.6, 1.2)