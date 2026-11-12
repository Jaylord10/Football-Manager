import random
from pygame.math import Vector2
from core.utils import distance, clamp
from config.constants import *

# ===========================================================================
# TACKLING
# ===========================================================================

def handle_tackles(mechanics, team0, team1, ball, current_time):
    """
    One-v-one duels: take-ons and tackles.  See gameplay/duels.py.

    Returns: (successful_tackle: bool, foul_info: dict | None)
      foul_info keys: fouler, fouled, pos, card_type, attacking_team
    """
    from gameplay import duels
    return duels.handle(team0, team1, ball, current_time)

# ===========================================================================
# INTERCEPTIONS (RESTORED TO FIX IMPORT ERROR)
# ===========================================================================

def check_interceptions(team0, team1, ball, current_time):
    """
    Check if any player can intercept a loose ball.
    """
    if ball.owner is not None: return False
    
    ball_speed = ball.vel.length()
    if ball_speed < 8 * M_TO_PX or ball.z > 15: return False
    
    all_players = team0 + team1
    candidates = sorted(all_players, key=lambda p: distance(p.pos, ball.pos))
    
    for player in candidates:
        if player.role == "GK": continue
        
        dist_to_ball = distance(player.pos, ball.pos)
        if dist_to_ball > 15 * M_TO_PX: continue
        
        # Predict ball position
        future_ball_pos = ball.pos + ball.vel * 0.2
        if distance(player.pos, future_ball_pos) < 3.5 * M_TO_PX:
            # Stat based success
            int_stat = player.attributes.get("Interceptions", 10)
            anti_stat = player.attributes.get("Anticipation", 10)
            
            success_chance = 0.20 + (int_stat / 20.0) * 0.35 + (anti_stat / 20.0) * 0.15
            
            if random.random() < success_chance:
                ball.owner = player
                player.has_ball = True
                player.last_received_time = current_time
                ball.last_toucher = player
                ball.last_toucher_team = player.team
                ball.vel = player.vel * 0.8
                player.state = "intercept"
                return True
    return False

# ===========================================================================
# LOOSE BALLS & PICKUP (RESTORED)
# ===========================================================================

def handle_loose_balls(all_players, ball):
    """Assign nearest player to chase loose balls."""
    if ball.is_dead: return
    if ball.owner is not None or ball.z > 20: return
    
    active = [p for p in all_players if getattr(p, 'is_active', True)]
    if not active: return
    nearest_player = min(active, key=lambda p: distance(p.pos, ball.pos))
    
    # GK Box restrictions
    if nearest_player.role == "GK":
        box_l, box_r = (0, KEEPER_BOX_DEPTH + 20) if nearest_player.team == 0 else (WIDTH - KEEPER_BOX_DEPTH - 20, WIDTH)
        if not (box_l <= ball.pos.x <= box_r): return
        
    nearest_player.target = Vector2(ball.pos)
    nearest_player.state = "chase"
    nearest_player.pos_reason = "chase loose ball"

