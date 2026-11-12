import math
from pygame.math import Vector2
from config.constants import WIDTH, HEIGHT, M_TO_PX

def distance(p1, p2):
    """Calculates Euclidean distance between two Vector2 points or tuples."""
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def clamp(value, min_val, max_val):
    """Clamps a value between a minimum and maximum."""
    return max(min_val, min(value, max_val))

def cell_center(col, row):
    """Returns the pixel center Vector2 of a grid cell."""
    CELL_W = WIDTH / 24
    CELL_H = HEIGHT / 16
    x = (col + 0.5) * CELL_W
    y = (row + 0.5) * CELL_H
    return Vector2(x, y)

def grid_cell_from_position(pos):
    """
    Converts a pixel position (Vector2) into grid coordinates (col, row).
    Returns integer tuple (col, row).
    """
    CELL_W = WIDTH / 24
    CELL_H = HEIGHT / 16
    
    col = int(pos.x / CELL_W)
    row = int(pos.y / CELL_H)
    
    # Clamp to grid bounds (0-23, 0-15)
    col = clamp(col, 0, 23)
    row = clamp(row, 0, 15)
    
    return col, row

def segment_point_distance(seg_a, seg_b, point):
    """
    Calculates the perpendicular distance from a point to a line segment.
    Used for checking if a defender is blocking a passing lane.
    """
    seg_v = seg_b - seg_a
    if seg_v.length_squared() == 0:
        return distance(seg_a, point)
    
    pt_v = point - seg_a
    t = pt_v.dot(seg_v) / seg_v.length_squared()
    t = clamp(t, 0.0, 1.0)
    
    projection = seg_a + seg_v * t
    return distance(point, projection)

def predict_pass_point(passer_pos, receiver, pass_speed):
    """
    Predicts where a moving receiver will be when the ball arrives.
    """
    dist = distance(passer_pos, receiver.pos)
    safe_speed = max(pass_speed, 1.0)
    pass_time = dist / safe_speed
    
    # Cap prediction time
    prediction_time = min(pass_time, 1.5)
    
    # Calculate future position
    predicted_pos = receiver.pos + (receiver.vel * prediction_time)
    
    # Clamp to pitch boundaries
    predicted_pos.x = clamp(predicted_pos.x, 2.0, WIDTH - 2.0)
    predicted_pos.y = clamp(predicted_pos.y, 2.0, HEIGHT - 2.0)
    
    return predicted_pos

def opponent_will_intercept(start_pos, end_pos, opponents, ball_speed):
    """
    Checks if any opponent can intercept the ball before it reaches the target.
    """
    ball_dist = distance(start_pos, end_pos)
    if ball_dist < 1: return False
    
    safe_speed = max(ball_speed, 1.0)
    
    pass_dir = (end_pos - start_pos).normalize()
    
    for opp in opponents:
        # 1. Geometry Check
        dist_to_lane = segment_point_distance(start_pos, end_pos, opp.pos)
        if dist_to_lane > 3.0 * M_TO_PX: continue
            
        # 2. Timing Check
        to_opp = opp.pos - start_pos
        projection_dist = to_opp.dot(pass_dir)
        
        if projection_dist < 0 or projection_dist > ball_dist: continue
            
        # Time for ball to reach intercept point
        ball_time_to_intercept = projection_dist / safe_speed
        
        # Time for opponent to get there
        intercept_point = start_pos + pass_dir * projection_dist
        dist_opp_to_intercept = distance(opp.pos, intercept_point)
        opp_speed = 6.0 * M_TO_PX 
        opp_time = dist_opp_to_intercept / opp_speed
        
        if opp_time < ball_time_to_intercept - 0.1:
            return True
            
    return False

def any_defender_between(start_pos, end_pos, opponents, width_radius):
    """
    Simple geometric check: Is there a defender in this corridor?
    """
    for opp in opponents:
        dist = segment_point_distance(start_pos, end_pos, opp.pos)
        if dist < width_radius:
            d_total = distance(start_pos, end_pos)
            d1 = distance(start_pos, opp.pos)
            d2 = distance(end_pos, opp.pos)
            
            if d1 < d_total and d2 < d_total:
                return True
    return False

def angle_between(a, b):
    """
    Unsigned angle between two vectors, always 0-180 degrees.

    Use this instead of abs(a.angle_to(b)): pygame's angle_to can return
    e.g. 350 instead of -10 when the vectors point roughly LEFT (either side
    of 180 degrees), which made right-to-left situations look like huge
    angles - the team attacking right-to-left was refusing sensible shots,
    passes and dribbles because of it.
    """
    ang = abs(a.angle_to(b)) % 360.0
    return 360.0 - ang if ang > 180.0 else ang
