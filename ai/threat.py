# ai/threat.py
"""
THREAT ASSESSMENT SYSTEM

Measures how dangerous a player/position is to the opponent's goal.

Threat Score: 0.0 to 1.0
- 1.0 = Immediate goal danger (e.g., striker 1v1 with keeper)
- 0.5 = Medium threat (e.g., winger in space)
- 0.0 = No threat (e.g., defender in own half)

This helps the AI prioritize ATTACKING VALUE over just "safety"
"""

from pygame.math import Vector2
from core.utils import distance, clamp, angle_between
from config.constants import WIDTH, HEIGHT, M_TO_PX
import math


# ===========================================================================
# BALL CARRIER THREAT (Dribbling Danger)
# ===========================================================================

def calculate_carrier_threat(player, opponents):
    """
    How dangerous is the player WITH the ball when DRIBBLING?
    
    This measures threat for moving FORWARD with the ball.
    
    Factors (NEW WEIGHTS):
    30% defenders in dribble path - Can I run forward without hitting someone?
    25% space ahead - How much room to run into?
    20% distance to goal - How close am I?
    17% facing direction - Am I facing the right way?
    5% angle to goal - Am I central or wide?
    3% behind defensive line - Am I already in behind?
    
    Returns: 0.0 to 1.0
    """
    
    # Determine which goal we're attacking
    goal_pos = Vector2(WIDTH, HEIGHT/2) if player.team == 0 else Vector2(0, HEIGHT/2)
    
    # ==================================================================
    # FACTOR 1: DEFENDERS IN DRIBBLE PATH (30% importance)
    # ==================================================================
    # Count defenders in the corridor I'd dribble through (narrower than "between me and goal")
    defenders_in_path = count_defenders_in_dribble_path(player.pos, goal_pos, opponents, player.team)
    
    # HARSH scoring for dribbling (can't beat multiple defenders)
    # 0 defenders = 1.0 (clear run!)
    # 1 defender = 0.4 (can maybe beat one)
    # 2+ defenders = 0.0 (impossible)
    
    if defenders_in_path == 0:
        defender_score = 1.0
    elif defenders_in_path == 1:
        defender_score = 0.4
    else:
        defender_score = 0.0
    
    # ==================================================================
    # FACTOR 2: SPACE AHEAD (25% importance)
    # ==================================================================
    # How much clear space to run into?
    space_score = check_space_ahead(player.pos, goal_pos, opponents)
    
    # ==================================================================
    # FACTOR 3: DISTANCE TO GOAL (20% importance)
    # ==================================================================
    dist_to_goal = distance(player.pos, goal_pos)
    dist_meters = dist_to_goal / M_TO_PX
    
    if dist_meters < 6:
        distance_score = 0.9 + (6 - dist_meters) / 60
    elif dist_meters < 16:
        distance_score = 0.7 + (16 - dist_meters) / 50
    elif dist_meters < 30:
        distance_score = 0.4 + (30 - dist_meters) / 47
    elif dist_meters < 50:
        distance_score = 0.1 + (50 - dist_meters) / 67
    else:
        distance_score = max(0.0, 0.1 - (dist_meters - 50) / 200)
    
    distance_score = clamp(distance_score, 0.0, 1.0)
    
    # ==================================================================
    # FACTOR 4: FACING DIRECTION (17% importance)
    # ==================================================================
    # Are you facing toward goal or away?
    facing_score = calculate_facing_score(player, goal_pos)
    
    # ==================================================================
    # FACTOR 5: ANGLE TO GOAL (5% importance)
    # ==================================================================
    to_goal = goal_pos - player.pos
    ideal_direction = Vector2(1, 0) if player.team == 0 else Vector2(-1, 0)
    
    if to_goal.length_squared() > 0:
        angle_deg = angle_between(to_goal.normalize(), ideal_direction)
        
        if angle_deg < 15:
            angle_score = 1.0
        elif angle_deg < 30:
            angle_score = 0.8
        elif angle_deg < 45:
            angle_score = 0.5
        elif angle_deg < 60:
            angle_score = 0.2
        else:
            angle_score = 0.0
    else:
        angle_score = 1.0
    
    # ==================================================================
    # FACTOR 6: BEHIND DEFENSIVE LINE (3% importance)
    # ==================================================================
    is_behind = check_behind_defensive_line(player, opponents)
    behind_score = 1.0 if is_behind else 0.0
    
    # ==================================================================
    # WEIGHTED CALCULATION (NEW WEIGHTS!)
    # ==================================================================
    threat = (
        0.30 * defender_score +    # Defenders in path
        0.25 * space_score +        # Space ahead
        0.20 * distance_score +     # Distance to goal
        0.17 * facing_score +       # Facing direction
        0.05 * angle_score +        # Angle to goal
        0.03 * behind_score         # Behind line
    )
    
    return clamp(threat, 0.0, 1.0)


# ===========================================================================
# RECEIVER THREAT (Passing Danger)
# ===========================================================================

def calculate_receiver_threat(receiver, opponents, passer_pos):
    """
    How dangerous would this teammate be if they RECEIVED the ball?
    
    This measures threat for a STATIONARY player who would receive a pass.
    
    Factors (NEW WEIGHTS):
    30% defenders between receiver and goal - Clear path to score?
    25% space around receiver - Room to turn and operate?
    20% distance to goal - How close are they?
    17% facing direction - Facing the right way?
    5% angle to goal - Central or wide?
    3% behind defensive line - Already in behind?
    
    Returns: 0.0 to 1.0
    """
    
    # Determine which goal we're attacking
    goal_pos = Vector2(WIDTH, HEIGHT/2) if receiver.team == 0 else Vector2(0, HEIGHT/2)
    
    # ==================================================================
    # FACTOR 1: DEFENDERS BETWEEN RECEIVER AND GOAL (30% importance)
    # ==================================================================
    defenders_between = count_defenders_between(receiver.pos, goal_pos, opponents)
    
    # More lenient for receiving (can pass around defenders)
    # 0-1 defenders = 1.0 (clear path!)
    # 2 defenders = 0.6
    # 3 defenders = 0.3
    # 4+ defenders = 0.1
    
    if defenders_between <= 1:
        defender_score = 1.0
    elif defenders_between == 2:
        defender_score = 0.6
    elif defenders_between == 3:
        defender_score = 0.3
    else:
        defender_score = 0.1
    
    # ==================================================================
    # FACTOR 2: SPACE AROUND RECEIVER (25% importance)
    # ==================================================================
    # Can they receive and turn, or will they be immediately pressed?
    
    nearest_def_dist = 999
    if opponents:
        nearest_def_dist = min(distance(receiver.pos, d.pos) for d in opponents)
    
    nearest_meters = nearest_def_dist / M_TO_PX
    
    # 5m+ space = 1.0 (plenty of room)
    # 3-5m space = 0.7 (some room)
    # 1-3m space = 0.3 (tight)
    # <1m space = 0.0 (crowded)
    
    if nearest_meters > 5:
        space_score = 1.0
    elif nearest_meters > 3:
        space_score = 0.7
    elif nearest_meters > 1:
        space_score = 0.3
    else:
        space_score = 0.0
    
    # ==================================================================
    # FACTOR 3: DISTANCE TO GOAL (20% importance)
    # ==================================================================
    dist_to_goal = distance(receiver.pos, goal_pos)
    dist_meters = dist_to_goal / M_TO_PX
    
    # Same zones as carrier threat
    if dist_meters < 6:
        distance_score = 0.9 + (6 - dist_meters) / 60
    elif dist_meters < 16:
        distance_score = 0.7 + (16 - dist_meters) / 50
    elif dist_meters < 30:
        distance_score = 0.4 + (30 - dist_meters) / 47
    elif dist_meters < 50:
        distance_score = 0.1 + (50 - dist_meters) / 67
    else:
        distance_score = max(0.0, 0.1 - (dist_meters - 50) / 200)
    
    distance_score = clamp(distance_score, 0.0, 1.0)
    
    # ==================================================================
    # FACTOR 4: FACING DIRECTION (17% importance)
    # ==================================================================
    # Are they facing toward goal or away?
    facing_score = calculate_facing_score(receiver, goal_pos)
    
    # ==================================================================
    # FACTOR 5: ANGLE TO GOAL (5% importance)
    # ==================================================================
    to_goal = goal_pos - receiver.pos
    ideal_direction = Vector2(1, 0) if receiver.team == 0 else Vector2(-1, 0)
    
    if to_goal.length_squared() > 0:
        angle_deg = angle_between(to_goal.normalize(), ideal_direction)
        
        if angle_deg < 15:
            angle_score = 1.0
        elif angle_deg < 30:
            angle_score = 0.8
        elif angle_deg < 45:
            angle_score = 0.5
        elif angle_deg < 60:
            angle_score = 0.2
        else:
            angle_score = 0.0
    else:
        angle_score = 1.0
    
    # ==================================================================
    # FACTOR 6: BEHIND DEFENSIVE LINE (3% importance)
    # ==================================================================
    # This is HUGE - being in behind is super dangerous!
    
    is_behind_line = check_behind_defensive_line(receiver, opponents)
    behind_score = 1.0 if is_behind_line else 0.0
    
    # ==================================================================
    # WEIGHTED CALCULATION (NEW WEIGHTS!)
    # ==================================================================
    threat = (
        0.30 * defender_score +     # Defenders between
        0.25 * space_score +         # Space around
        0.20 * distance_score +      # Distance to goal
        0.17 * facing_score +        # Facing direction
        0.05 * angle_score +         # Angle to goal
        0.03 * behind_score          # Behind line
    )
    
    return clamp(threat, 0.0, 1.0)


# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================

def check_space_ahead(player_pos, goal_pos, opponents):
    """
    How much clear space is there in front of the player?
    
    Returns: 0.0 to 1.0
    """
    
    if not opponents:
        return 1.0
    
    # Check points along the path to goal
    direction = (goal_pos - player_pos)
    total_dist = direction.length()
    
    if total_dist < 1:
        return 1.0
    
    direction = direction.normalize()
    
    # Check every 5 meters up to 20 meters ahead
    clear_distance = 0
    max_check = min(20 * M_TO_PX, total_dist)
    
    for check_dist in range(int(5 * M_TO_PX), int(max_check), int(5 * M_TO_PX)):
        check_point = player_pos + direction * check_dist
        
        # Is any defender close to this point?
        closest_def = min(distance(check_point, d.pos) for d in opponents)
        
        if closest_def > 3 * M_TO_PX:
            clear_distance += 5
        else:
            break  # Hit a defender, stop checking
    
    # Score based on how far we could check
    space_score = clamp(clear_distance / 20, 0.0, 1.0)
    return space_score


def count_defenders_in_dribble_path(player_pos, goal_pos, opponents, player_team):
    """
    Count defenders in the NARROW CORRIDOR the player would dribble through.
    
    This is stricter than "defenders between player and goal" because
    we're checking if you can physically run forward without hitting someone.
    
    Returns: Integer count
    """
    
    if not opponents:
        return 0
    
    # Direction we'd dribble
    to_goal = goal_pos - player_pos
    if to_goal.length_squared() < 1:
        return 0
    
    direction = to_goal.normalize()
    
    # Only check next 10 meters ahead (realistic dribble distance)
    check_distance = min(10 * M_TO_PX, to_goal.length())
    
    count = 0
    CORRIDOR_WIDTH = 5 * M_TO_PX  # Narrow corridor (5m wide)
    
    for defender in opponents:
        # Skip goalkeepers
        if hasattr(defender, 'role') and defender.role == "GK":
            continue
        
        # Vector to defender
        to_defender = defender.pos - player_pos
        
        # How far along the dribble path?
        projection = to_defender.dot(direction)
        
        # Only count defenders ahead of us (within dribble distance)
        if 0 < projection < check_distance:
            # How far from the center line?
            perpendicular_dist = (to_defender - direction * projection).length()
            
            # Is defender in our corridor?
            if perpendicular_dist < CORRIDOR_WIDTH:
                count += 1
    
    return count


def calculate_facing_score(player, goal_pos):
    """
    Calculate how well the player is facing toward the goal.
    
    Scoring:
    - 0-45° from goal = 1.0 (facing forward)
    - 45-90° = 0.5 (side-on)
    - 90-180° = 0.0 (back to goal)
    
    Returns: 0.0 to 1.0
    """
    
    # Player's facing direction
    if player.facing.length_squared() < 0.1:
        # No facing direction set, assume facing team's attack direction
        facing = Vector2(1, 0) if player.team == 0 else Vector2(-1, 0)
    else:
        facing = player.facing.normalize()
    
    # Direction to goal
    to_goal = goal_pos - player.pos
    if to_goal.length_squared() < 1:
        return 1.0  # At the goal!
    
    to_goal_norm = to_goal.normalize()
    
    # Calculate angle between facing and goal direction
    angle_deg = angle_between(facing, to_goal_norm)
    
    # Score based on angle
    if angle_deg < 45:
        return 1.0  # Facing forward
    elif angle_deg < 90:
        return 0.5  # Side-on
    else:
        return 0.0  # Back to goal


def count_defenders_ahead(player_pos, goal_pos, opponents):
    """
    How many defenders are between the player and the goal line?
    
    Returns: Integer count
    """
    
    if not opponents:
        return 0
    
    count = 0
    
    for defender in opponents:
        # Is defender ahead of player (toward goal)?
        # (Direction comes from which goal we're attacking - it used to be
        #  guessed from which half the player was in, which was wrong in the
        #  opponent's half.)
        if goal_pos.x > player_pos.x:  # Attacking right
            if defender.pos.x > player_pos.x:
                # Is defender in the path? (not too far to the side)
                if abs(defender.pos.y - player_pos.y) < 25 * M_TO_PX:
                    count += 1
        else:  # Attacking left
            if defender.pos.x < player_pos.x:
                if abs(defender.pos.y - player_pos.y) < 25 * M_TO_PX:
                    count += 1
    
    return count


def count_defenders_between(receiver_pos, goal_pos, opponents):
    """
    How many defenders are between the receiver and goal?
    
    Similar to count_defenders_ahead but from receiver's position.
    
    Returns: Integer count
    """
    
    if not opponents:
        return 0
    
    count = 0
    
    # Get direction to goal
    to_goal = goal_pos - receiver_pos
    if to_goal.length_squared() < 1:
        return 0
    
    direction = to_goal.normalize()
    goal_distance = to_goal.length()
    
    for defender in opponents:
        # Vector to defender
        to_defender = defender.pos - receiver_pos
        
        # Project defender onto goal line
        projection = to_defender.dot(direction)
        
        # Is defender between receiver and goal?
        if 0 < projection < goal_distance:
            # Is defender close enough to the line to matter?
            perpendicular_dist = (to_defender - direction * projection).length()
            
            if perpendicular_dist < 15 * M_TO_PX:  # Within 15m of the line
                count += 1
    
    return count


def check_behind_defensive_line(receiver, opponents):
    """
    Is the receiver behind the last defender (not including goalkeeper)?
    
    This is a HUGE threat indicator!
    
    Returns: True/False
    """
    
    if not opponents:
        return True
    
    # Find the last defender (deepest, closest to their own goal)
    # Sort defenders by X position
    
    if receiver.team == 0:  # Attacking right
        # Get all defenders' X positions
        defender_positions = [d.pos.x for d in opponents if d.role != "GK"]
        
        if not defender_positions:
            return True
        
        # Find the furthest right defender (closest to their goal)
        last_defender_x = max(defender_positions)
        
        # Is receiver beyond this line?
        return receiver.pos.x > last_defender_x
        
    else:  # Attacking left
        defender_positions = [d.pos.x for d in opponents if d.role != "GK"]
        
        if not defender_positions:
            return True
        
        # Find the furthest left defender
        last_defender_x = min(defender_positions)
        
        # Is receiver beyond this line?
        return receiver.pos.x < last_defender_x


# ===========================================================================
# DEBUG / UTILITY FUNCTIONS
# ===========================================================================

def get_threat_category(threat_value):
    """
    Convert threat number into easy words.
    
    Like danger levels:
    - High (>0.7) = Immediate danger
    - Medium (0.4-0.7) = Potential danger
    - Low (<0.4) = Limited danger
    """
    
    if threat_value > 0.7:
        return "High Threat"
    elif threat_value > 0.4:
        return "Medium Threat"
    else:
        return "Low Threat"


def compare_passing_options(passer, receivers, opponents):
    """
    Helper function to compare multiple passing options.
    
    Returns list of (receiver, threat_score) sorted by threat.
    """
    
    options = []
    
    for receiver in receivers:
        threat = calculate_receiver_threat(receiver, opponents, passer.pos)
        options.append((receiver, threat))
    
    # Sort by threat (highest first)
    options.sort(key=lambda x: x[1], reverse=True)
    
    return options