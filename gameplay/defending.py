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

LOOSE_CONTEST_WITHIN = 1.5   # s: a team whose quickest man would get there within this of the first one goes
                             #    for it too - a second ball is a race, not handed to whoever's nearest
LOOSE_LOOK = 30.0            # m: (only men within this of the ball are considered)


def handle_loose_balls(all_players, ball):
    """A loose ball on the ground: each team sends its man who'll get there first (to where he can meet it,
    not where it is now) - both teams race for it if they're close to it in time."""
    if ball.is_dead: return
    if ball.owner is not None or ball.z > 20: return

    active = [p for p in all_players if getattr(p, 'is_active', True)]
    if not active: return
    from ai.movement import predict_intercept
    import core.locomotion as locomotion
    best = {}
    for p in active:
        d = distance(p.pos, ball.pos)
        if d > LOOSE_LOOK * M_TO_PX and p.team in best:
            continue
        if p.role == "GK":
            box_l, box_r = (0, KEEPER_BOX_DEPTH + 20) if p.team == 0 else (WIDTH - KEEPER_BOX_DEPTH - 20, WIDTH)
            if not (box_l <= ball.pos.x <= box_r):
                continue
        spot = predict_intercept(p, ball) if d < LOOSE_LOOK * M_TO_PX else Vector2(ball.pos)
        t = distance(p.pos, spot) / max(1.0, locomotion.top_speed_ms(p) * M_TO_PX)
        if p.team not in best or t < best[p.team][0]:
            best[p.team] = (t, p, spot)
    if not best:
        return
    first = min(v[0] for v in best.values())
    for t, p, spot in best.values():
        if t > first + LOOSE_CONTEST_WITHIN:
            continue
        p.target = Vector2(spot)
        p.state = "chase"
        p.pos_reason = "chase loose ball" if t <= first else "race for the second ball"

