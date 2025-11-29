import random
from pygame.math import Vector2
from core.utils import distance, segment_point_distance, clamp, cell_center
from config.constants import *
from config.formations import formation_4_4_2_positions

class GameMechanics:
    def __init__(self):
        pass

    def handle_tackles(self, attacking_team, defending_team, ball, current_time):
        """Attempt tackles on ball carrier."""
        if ball.owner is None:
            return False
            
        carrier = ball.owner
        successful_tackle = False
        
        for defender in defending_team:
            if (distance(defender.pos, carrier.pos) > TACKLE_DISTANCE or 
                current_time - defender.last_tackle_time < TACKLE_COOLDOWN):
                continue
            
            tackle_chance = self._calculate_tackle_chance(defender, carrier)
            
            if random.random() < tackle_chance:
                # Execute successful tackle directly here with ball access
                carrier.has_ball = False
                carrier.state = "tackled"
                
                ball.owner = defender
                defender.has_ball = True
                defender.last_tackle_time = current_time
                defender.state = "tackle"
                
                successful_tackle = True
                break
                
        return successful_tackle

    def _calculate_tackle_chance(self, defender, carrier):
        """Calculate chance of successful tackle."""
        base_chance = TACKLE_CHANCE
        
        # Defensive role bonus
        if defender.role in ("LB", "LCB", "RCB", "RB"):
            base_chance += 0.2
        
        # Stamina modifier
        stamina_mod = defender.stamina * 0.3
        base_chance += stamina_mod
        
        # Facing bonus - only if defender is moving and has non-zero velocity
        if defender.vel.length_squared() > 0:
            to_carrier = (carrier.pos - defender.pos)
            # Check if vectors have non-zero length before normalizing
            if to_carrier.length_squared() > 0:
                to_carrier = to_carrier.normalize()
                facing = defender.vel.normalize()
                facing_bonus = max(0, to_carrier.dot(facing)) * 0.2
                base_chance += facing_bonus
            
        return base_chance


    def _execute_successful_tackle(self, carrier, defender, current_time):
        """Execute a successful tackle, transferring ball possession."""
        carrier.has_ball = False
        carrier.state = "tackled"
        
        ball.owner = defender
        defender.has_ball = True
        defender.last_tackle_time = current_time
        defender.state = "tackle"

    def handle_loose_balls(self, all_players, ball):
        """Assign closest player to chase loose ball."""
        if ball.owner is not None:
            return
            
        nearest_player = min(all_players, key=lambda p: distance(p.pos, ball.pos))
        
        if nearest_player.role == "GK":
            # Only chase if ball is in keeper's area
            if nearest_player.team == 0:
                keeper_box_left, keeper_box_right = 0, KEEPER_BOX_DEPTH + 20
            else:
                keeper_box_left, keeper_box_right = WIDTH - KEEPER_BOX_DEPTH - 20, WIDTH
            
            if keeper_box_left <= ball.pos.x <= keeper_box_right:
                nearest_player.target = Vector2(ball.pos)
                nearest_player.state = "chase"
        else:
            nearest_player.target = Vector2(ball.pos)
            nearest_player.state = "chase"

    def update_goalkeeper_dive_states(self, team0, team1, current_time):
        """Update goalkeeper dive state machine."""
        for keeper_team, _ in ((team0, team1), (team1, team0)):
            keeper = next((p for p in keeper_team if p.role == "GK"), None)
            if not keeper:
                continue
            
            # Preparing -> diving after reaction delay
            if keeper.dive_state == "preparing":
                if (current_time - keeper.dive_start_time) >= keeper.dive_reaction:
                    keeper.dive_state = "diving"
                    keeper.last_dive_time = current_time
            
            # Diving -> recover when close to target
            if keeper.dive_state == "diving":
                if (keeper.pos - keeper.dive_target).length() < 3:
                    keeper.dive_state = "recover"
                    keeper.last_dive_time = current_time

    def handle_goalkeeper_interactions(self, team0, team1, ball, current_time, ai_system):
        """Handle goalkeeper interactions with the ball."""
        for keeper_team, _ in ((team0, team1), (team1, team0)):
            keeper = next((p for p in keeper_team if p.role == "GK"), None)
            if not keeper:
                continue
            
            if keeper.dive_state == "diving":
                # Check for catch/parry during dive
                ball_distance = distance(keeper.pos, ball.pos)
                
                # Catch if within small radius and ball not too fast
                if ball_distance <= keeper.catch_radius and ball.vel.length() < SHOT_SPEED * 1.2:
                    ball.owner = keeper
                    keeper.has_ball = True
                    ball.vel = Vector2(0, 0)
                    keeper.dive_state = "recover"
                    keeper.last_dive_time = current_time
                    ai_system.last_possession_team = keeper.team
                # Parry if slightly further but inside parry radius
                elif ball_distance <= keeper.parry_radius and ball.vel.length() > 10:
                    # Redirect ball away from goal
                    away_direction = Vector2(1, random.uniform(-0.6, 0.6)) if keeper.team == 0 else Vector2(-1, random.uniform(-0.6, 0.6))
                    ball.vel = away_direction.normalize() * (ball.vel.length() * 0.45)
                    ball.pos = Vector2(keeper.pos) + away_direction.normalize() * (keeper.parry_radius + 2)
                    keeper.dive_state = "recover"
                    keeper.last_dive_time = current_time
            else:
                # Normal keeper ball collection
                if keeper.team == 0:
                    box_left, box_right = 0, KEEPER_BOX_DEPTH
                else:
                    box_left, box_right = WIDTH - KEEPER_BOX_DEPTH, WIDTH
                    
                box_top = HEIGHT/2 - GOAL_WIDTH/2 - (KEEPER_BOX_DEPTH / 4)
                box_bottom = HEIGHT/2 + GOAL_WIDTH/2 + (KEEPER_BOX_DEPTH / 4)
                
                if (box_left <= ball.pos.x <= box_right and 
                    box_top <= ball.pos.y <= box_bottom):
                    ball_distance = distance(keeper.pos, ball.pos)
                    if (ball_distance < keeper.catch_radius + 2 and 
                        ball.vel.length() < 40 and 
                        (current_time - ball.last_kick_time) > 0.12):
                        ball.owner = keeper
                        keeper.has_ball = True
                        ball.vel = Vector2(0, 0)
                        keeper.dive_state = "idle"
                        keeper.last_dive_time = current_time
                        ai_system.last_possession_team = keeper.team

    def handle_possession_pickup(self, team0, team1, ball, current_time, ai_system):
        """Handle field players picking up loose balls."""
        if ball.owner is None and ball.vel.length() < 30 * M_TO_PX:
            candidates = [p for p in team0 + team1 if distance(p.pos, ball.pos) <= POSSESSION_DIST]
            if candidates and (current_time - ball.last_kick_time) > 0.12:
                closest_player = min(candidates, key=lambda x: distance(x.pos, ball.pos))
                ball.owner = closest_player
                closest_player.has_ball = True
                ball.vel = Vector2(0, 0)
                ai_system.last_possession_team = closest_player.team

    def check_goal(self, ball):
        """Check if ball is in goal and return scoring team."""
        goal_top = (HEIGHT / 2) - GOAL_WIDTH / 2
        goal_bottom = (HEIGHT / 2) + GOAL_WIDTH / 2
        goal_line_deep = int(0.5 * M_TO_PX)
        
        # Left goal (team 1 scores)
        if ball.pos.x < -goal_line_deep and goal_top < ball.pos.y < goal_bottom:
            return 1
        # Right goal (team 0 scores)
        if ball.pos.x > WIDTH + goal_line_deep and goal_top < ball.pos.y < goal_bottom:
            return 0
            
        return None

    def reset_game(self, team0, team1, ball, ai_system):
        """Reset game to initial state."""
        for team in (team0, team1):
            formation = formation_4_4_2_positions(team[0].team)
            for role, col, row in formation:
                player = next((p for p in team if p.role == role), None)
                if player:
                    player.pos = cell_center(col, row)
                    player.target = Vector2(player.pos)
                    player.has_ball = False
                    player.state = "idle"
                    player.stamina = 1.0
                    if player.role == "GK":
                        player.dive_state = "idle"
                        player.last_dive_time = -10.0
        
        ball.pos = Vector2(WIDTH / 2, HEIGHT / 2)
        ball.vel = Vector2(0, 0)
        ball.owner = None
        ball.last_kick_time = -10.0
        ball.last_pass_time = -10.0
        ball.pass_start_pos = None
        
        ai_system.last_possession_team = random.choice([0, 1])