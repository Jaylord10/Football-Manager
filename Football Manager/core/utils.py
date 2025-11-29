from pygame.math import Vector2
from config.constants import CELL_W, CELL_H, GRID_COLS, GRID_ROWS

def clamp(value, min_val, max_val):
    """Clamp a value between min and max."""
    return max(min_val, min(max_val, value))

def distance(point_a, point_b):
    """Calculate distance between two points."""
    return (point_a - point_b).length()

def segment_point_distance(segment_start, segment_end, point):
    """Calculate shortest distance from point to line segment."""
    segment_vector = segment_end - segment_start
    if segment_vector.length_squared() == 0:
        return (point - segment_start).length()
    
    t = clamp((point - segment_start).dot(segment_vector) / segment_vector.length_squared(), 0.0, 1.0)
    projection = segment_start + segment_vector * t
    return (point - projection).length()

def grid_cell_from_position(position):
    """Convert position to grid cell coordinates."""
    col = int(clamp(position.x / CELL_W, 0, GRID_COLS - 1))
    row = int(clamp(position.y / CELL_H, 0, GRID_ROWS - 1))
    return col, row

def cell_center(col, row):
    """Get center position of a grid cell."""
    return Vector2((col + 0.5) * CELL_W, (row + 0.5) * CELL_H)

def predict_pass_point(pass_start, target_player, pass_speed):
    """Predict where to pass to account for target movement."""
    to_target = target_player.pos - pass_start
    distance_to_target = to_target.length()
    
    if pass_speed < 1:
        return Vector2(target_player.pos)
    
    time_to_reach = distance_to_target / pass_speed
    return target_player.pos + target_player.vel * (time_to_reach * 0.5)

def opponent_will_intercept(pass_start, pass_end, opponents, pass_speed):
    """Check if an opponent can intercept the pass."""
    segment_length = (pass_end - pass_start).length()
    if segment_length == 0:
        return False
        
    for opponent in opponents:
        for fraction in [0.2, 0.4, 0.6, 0.8]:
            point_on_pass = pass_start + (pass_end - pass_start) * fraction
            distance_to_opponent = (point_on_pass - opponent.pos).length()
            time_for_opponent = distance_to_opponent / (9.5 * 10 * 1.05)  # MAX_SPEED
            time_for_ball = (fraction * segment_length) / max(1.0, pass_speed)
            
            if time_for_opponent + 0.08 < time_for_ball:
                return True
    return False

def any_defender_between(player_pos, goal_pos, defenders, clearance_distance):
    """Check if any defender is between player and goal."""
    for defender in defenders:
        if segment_point_distance(player_pos, goal_pos, defender.pos) < clearance_distance:
            return True
    return False