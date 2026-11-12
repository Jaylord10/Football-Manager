from core.utils import distance, angle_between
from config.constants import *

def is_action_nonsense(player, action_type, target_pos, opponents):
    """
    Returns TRUE if the action violates basic body mechanics or physics.
    """
    dist = distance(player.pos, target_pos)
    
    # 1. Boundary Rule
    if not (0 <= target_pos.x <= WIDTH and 0 <= target_pos.y <= HEIGHT):
        return True 

    # 2. Physical Range Limit
    MAX_KICK_DIST = 65.0 * M_TO_PX
    if dist > MAX_KICK_DIST:
        return True

    # 3. Angle & Momentum (The "Usain Bolt" Rule)
    # Only enforce on longer actions (> 5m)
    if dist > 5.0 * M_TO_PX:
        to_target = target_pos - player.pos
        if to_target.length_squared() == 0: return False
        target_dir = to_target.normalize()
        
        current_speed = player.vel.length()
        
        # A. Sprinting (> 80%) -> Momentum dominates
        if current_speed > (MAX_SPEED * 0.8):
            if player.vel.length_squared() > 0:
                angle_momentum = angle_between(player.vel.normalize(), target_dir)
                if angle_momentum > 110:
                    return True 
        
        # B. Stationary -> Facing dominates
        elif player.facing.length_squared() > 0:
            angle_diff = angle_between(player.facing, target_dir)
            if angle_diff > 110: 
                return True 

    return False