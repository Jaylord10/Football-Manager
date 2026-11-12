import random
from pygame.math import Vector2
from core.utils import clamp
from config.constants import *

def perform_smart_clearance(carrier, teammates, ball, current_time, mechanics):
    """
    Clears the ball towards the furthest forward teammate (Target Man).
    """
    target_pos = None
    target_man = None
    
    # 1. Find Target
    if teammates:
        if carrier.team == 0: 
            # Look for max X (Strikers first)
            strikers = [p for p in teammates if "ST" in p.role or "FW" in p.role]
            if strikers: target_man = max(strikers, key=lambda p: p.pos.x)
            else: target_man = max(teammates, key=lambda p: p.pos.x)
        else: 
            # Look for min X
            strikers = [p for p in teammates if "ST" in p.role or "FW" in p.role]
            if strikers: target_man = min(strikers, key=lambda p: p.pos.x)
            else: target_man = min(teammates, key=lambda p: p.pos.x)
            
        if target_man:
            target_pos = Vector2(target_man.pos)
            # Lead target
            if carrier.team == 0: target_pos.x += 10 * M_TO_PX
            else: target_pos.x -= 10 * M_TO_PX
            
    # 2. Fallback (Center Field)
    if not target_pos:
        if carrier.team == 0: target_pos = Vector2(WIDTH * 0.75, HEIGHT / 2)
        else: target_pos = Vector2(WIDTH * 0.25, HEIGHT / 2)
        
    # 3. Variance (+/- 5m)
    variance = 5 * M_TO_PX
    target_pos.x += random.uniform(-variance, variance)
    target_pos.y += random.uniform(-variance, variance)
    target_pos.x = clamp(target_pos.x, 0, WIDTH)
    target_pos.y = clamp(target_pos.y, 10 * M_TO_PX, HEIGHT - 10 * M_TO_PX)
    
    # 4. Kick
    kick_vec = target_pos - carrier.pos
    if kick_vec.length_squared() == 0: kick_vec = Vector2(1, 0)
    
    ball.kick(kick_vec.normalize() * 30.0 * M_TO_PX, kicker=carrier, elevation=0.7)
    
    ball.last_kick_time = current_time
    carrier.has_ball = False
    return carrier.team # Return possession ID