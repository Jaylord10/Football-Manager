import random
from pygame.math import Vector2
from core.utils import distance, clamp
from config.constants import *

def execute_through_ball(passer, receiver, ball, current_time, opponents=None):
    """
    A through ball is a pass into space ahead of a runner.
    """
    if opponents is None:
        opponents = []

    dist_to_receiver = distance(passer.pos, receiver.pos)
    dist_m = dist_to_receiver / M_TO_PX

    if dist_m < 8.0:
        from gameplay.mechanics import GameMechanics
        mechanics = GameMechanics()
        mechanics.execute_pass(passer, receiver, ball, current_time)
        return

    passing_stat = passer.attributes.get("Passing", 10)
    vision_stat = passer.attributes.get("Vision", 10)

    if passing_stat > 25:
        passing_stat /= 5.0
    if vision_stat > 25:
        vision_stat /= 5.0

    attack_dir = Vector2(1, 0) if passer.team == 0 else Vector2(-1, 0)

    if receiver.vel.length_squared() > 1.0:
        run_dir = receiver.vel.normalize()
        if run_dir.dot(attack_dir) < 0.2:
            run_dir = attack_dir
    else:
        run_dir = attack_dir

    # REDUCED LEAD DISTANCE (was 12m max, now 8m max)
    lead_m = 4.0  # Base reduced from 6m to 4m

    speed_ratio = clamp(receiver.vel.length() / MAX_SPEED, 0.0, 1.0)
    lead_m += speed_ratio * 2.5  # Reduced from 4m to 2.5m

    iq = (passing_stat + vision_stat) / 40.0
    lead_m += iq * 1.5  # Reduced from 2m to 1.5m

    if dist_m > 25.0:
        lead_m += 1.0  # Reduced from 1.5m to 1m

    # NEW MAXIMUM: 8 meters (was 12)
    lead_m = min(lead_m, 8.0)
    
    # SAFETY CHECK: Don't lead the ball out of play
    goal_x = WIDTH if passer.team == 0 else 0
    if passer.team == 0:
        distance_to_line = WIDTH - receiver.pos.x
    else:
        distance_to_line = receiver.pos.x
    
    available_space_m = distance_to_line / M_TO_PX
    
    # Never lead more than 70% of available space
    max_safe_lead = available_space_m * 0.7
    lead_m = min(lead_m, max_safe_lead)
    
    lead_px = lead_m * M_TO_PX

    target = Vector2(receiver.pos) + run_dir * lead_px
    target += attack_dir * (1.5 * M_TO_PX)  # Reduced from 2m to 1.5m
    target.x = clamp(target.x, 2.0, WIDTH - 2.0)
    target.y = clamp(target.y, 2.0, HEIGHT - 2.0)

    dist_to_target = distance(passer.pos, target)
    dist_target_m = dist_to_target / M_TO_PX

    if dist_target_m < 15:
        ideal_time = 0.70  # Slightly faster
    elif dist_target_m < 30:
        ideal_time = 0.90 + (dist_target_m - 15) * 0.03
    else:
        ideal_time = 1.35 + (dist_target_m - 30) * 0.02

    base_speed = dist_to_target / ideal_time
    MIN_SPEED = 6.0 * M_TO_PX
    MAX_SPEED_PASS = 30.0 * M_TO_PX  # Reduced from 32 to 30
    base_speed = clamp(base_speed, MIN_SPEED, MAX_SPEED_PASS)

    max_error_pct = 0.16 - (passing_stat / 20.0) * 0.08  # Slightly more accurate
    speed_variance = random.uniform(1.0 - max_error_pct, 1.0 + max_error_pct)
    final_speed = clamp(base_speed * speed_variance, MIN_SPEED, MAX_SPEED_PASS)

    accuracy_factor = 1.6 - (passing_stat / 20.0) * 0.9 - (vision_stat / 20.0) * 0.5
    accuracy_factor = max(0.3, accuracy_factor)

    base_error = 0.05 * dist_to_target  # Reduced from 0.06
    final_error = base_error * accuracy_factor

    error_vec = Vector2(random.uniform(-1, 1), random.uniform(-1, 1)) * final_error
    actual_target = target + error_vec

    elevation = calculate_pass_elevation(passer.pos, target, dist_target_m, opponents)

    passer.state = "pass"

    kick_vec = actual_target - passer.pos
    if kick_vec.length_squared() > 0:
        ball.kick(kick_vec.normalize() * final_speed, kicker=passer, elevation=elevation)
    else:
        ball.kick(Vector2(1, 0) * final_speed, kicker=passer, elevation=elevation)

    ball.intended_target = receiver
    ball.last_kick_time = current_time
    ball.last_owner = passer
    passer.has_ball = False


def calculate_pass_elevation(start_pos, end_pos, dist_meters, opponents):
    """Calculate elevation for the through ball."""
    
    elevation = 0.0
    
    if dist_meters > 35:
        elevation = 0.55
    elif dist_meters > 22:
        elevation = 0.3
    
    if opponents and elevation < 0.3:
        lane_blocked = False
        for opp in opponents:
            to_opp = opp.pos - start_pos
            to_end = end_pos - start_pos
            
            if to_end.length_squared() > 0:
                projection = to_opp.dot(to_end.normalize())
                
                if 0 < projection < to_end.length():
                    perp_dist = (to_opp - to_end.normalize() * projection).length()
                    
                    if perp_dist < 3.0 * M_TO_PX:
                        lane_blocked = True
                        break
        
        if lane_blocked:
            elevation = 0.4
    
    return elevation