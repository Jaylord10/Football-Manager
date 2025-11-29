import importlib
import random
from pygame.math import Vector2
from core.utils import grid_cell_from_position, predict_pass_point, cell_center, distance, segment_point_distance
from core.utils import opponent_will_intercept, any_defender_between
from config.constants import *
from config.formations import formation_4_4_2_positions

class AIDecisionMaker:
    def __init__(self):
        self.last_possession_team = None

    def make_team_decisions(self, team, opponents, ball, current_time):
        ball_cell = grid_cell_from_position(ball.pos)
        team_id = team[0].team
        team_has_possession = self._determine_possession_state(ball.owner, team_id)
        
        # Update goalkeeper
        keeper = next((p for p in team if p.role == "GK"), None)
        if keeper:
            self._update_goalkeeper(keeper, ball, current_time, team_has_possession, ball_cell)
        
        if team_has_possession:
            self._handle_possession_phase(team, opponents, ball, current_time, team_id)
        else:
            self._handle_defensive_phase(team, opponents, ball, team_has_possession, ball_cell)

    def _determine_possession_state(self, ball_owner, team_id):
        if ball_owner:
            return ball_owner.team == team_id
        else:
            return self.last_possession_team == team_id

    def _update_goalkeeper(self, keeper, ball, current_time, team_has_possession, ball_cell):
        # Reset dive when recovery time passed
        if keeper.dive_state == "recover" and (current_time - keeper.last_dive_time) > keeper.recover_time:
            keeper.dive_state = "idle"
        
        # Decide whether to prepare/dive for shots
        if ball.owner is None and ball.vel.length() > 10:
            self._evaluate_goalkeeper_dive(keeper, ball, current_time)
        
        # Set keeper target when not diving
        if keeper.dive_state not in ("preparing", "diving"):
            keeper.target = self.get_role_target(
                keeper.role,
                ball_cell,
                team_has_possession,
                keeper.team,
                keeper.pos
            )
            keeper.state = "guard"

    def _evaluate_goalkeeper_dive(self, keeper, ball, current_time):
        """Evaluate if goalkeeper should dive for the ball."""
        # Calculate keeper's box boundaries
        if keeper.team == 0:
            box_left, box_right = 0, KEEPER_BOX_DEPTH
        else:
            box_left, box_right = WIDTH - KEEPER_BOX_DEPTH, WIDTH
            
        box_top = HEIGHT/2 - GOAL_WIDTH/2 - (KEEPER_BOX_DEPTH / 4)
        box_bottom = HEIGHT/2 + GOAL_WIDTH/2 + (KEEPER_BOX_DEPTH / 4)
        
        # Predict ball trajectory
        if abs(ball.vel.x) > 1e-6:
            target_x = box_right - (PLAYER_RADIUS * 0.5) if keeper.team == 0 else box_left + (PLAYER_RADIUS * 0.5)
            time_to_intercept = (target_x - ball.pos.x) / ball.vel.x
            
            if 0 < time_to_intercept < 2.0:
                intercept_point = ball.pos + ball.vel * time_to_intercept
                
                if box_top - 10 <= intercept_point.y <= box_bottom + 10:
                    distance_to_intercept = (intercept_point - keeper.pos).length()
                    estimated_dive_time = distance_to_intercept / keeper.dive_speed
                    
                    if (time_to_intercept <= keeper.dive_reaction + estimated_dive_time + 0.12 and
                        (current_time - keeper.last_dive_time) >= keeper.dive_cooldown and
                        keeper.dive_state in ("idle", "preparing")):
                        
                        keeper.dive_state = "preparing"
                        keeper.dive_target = Vector2(intercept_point)
                        keeper.dive_start_time = current_time

    def get_role_target(self, role, ball_cell, team_has_possession, team, current_pos):
        try:
            role_module = f"team{team}_{role}"
            
            if team_has_possession:
                mod = importlib.import_module(f"roles.in_possession.{role_module}")
                if hasattr(mod, 'in_possession'):
                    return mod.in_possession(ball_cell[0], ball_cell[1], team, (CELL_W, CELL_H))
            else:
                mod = importlib.import_module(f"roles.out_of_possession.{role_module}")
                if hasattr(mod, 'out_of_possession'):
                    return mod.out_of_possession(ball_cell[0], ball_cell[1], team, (CELL_W, CELL_H), current_pos)
            return current_pos
        except ImportError:
            # Fallback to formation positions
            formation = formation_4_4_2_positions(team)
            for r, col, row in formation:
                if r == role:
                    return cell_center(col, row)
            return current_pos

    def _handle_possession_phase(self, team, opponents, ball, current_time, team_id):
        ball_owner = ball.owner
        
        if ball_owner and ball_owner.team == team_id:
            self._make_ball_carrier_decision(ball_owner, team, opponents, ball, current_time)
        else:
            # Support positioning for players without ball
            ball_cell = grid_cell_from_position(ball.pos)
            for player in team:
                if player.role == "GK":
                    continue
                    
                player.target = self.get_role_target(
                    player.role,
                    ball_cell,
                    True,
                    player.team,
                    player.pos
                )
                player.state = "support"

    def _handle_defensive_phase(self, team, opponents, ball, team_has_possession, ball_cell):
        ball_owner = ball.owner
        
        if ball_owner and ball_owner.role == "GK":
            # Opponent keeper has ball - maintain defensive shape
            for player in team:
                if player.role == "GK":
                    # Keeper stays in goal
                    formation = formation_4_4_2_positions(player.team)
                    gk_pos = next((cell_center(col, row) for r, col, row in formation if r == "GK"), player.pos)
                    player.target = gk_pos
                    player.state = "guard"
                    continue
                    
                player.target = self.get_role_target(
                    player.role,
                    ball_cell,
                    False,
                    player.team,
                    player.pos
                )
                player.state = "defend"
                
        elif ball_owner:
            # Opponent field player has ball - apply pressure
            self._apply_defensive_pressure(team, ball_owner, ball_cell)
        else:
            # Loose ball - maintain defensive shape
            for player in team:
                if player.role == "GK":
                    formation = formation_4_4_2_positions(player.team)
                    gk_pos = next((cell_center(col, row) for r, col, row in formation if r == "GK"), player.pos)
                    player.target = gk_pos
                    player.state = "guard"
                    continue
                    
                player.target = self.get_role_target(
                    player.role,
                    ball_cell,
                    team_has_possession,
                    player.team,
                    player.pos
                )
                player.state = "support" if team_has_possession else "defend"

    def _apply_defensive_pressure(self, team, ball_carrier, ball_cell):
        """Apply defensive pressure to ball carrier."""
        field_players = [p for p in team if p.role != "GK"]
        
        # Find closest defender to apply pressure
        closest_defender = min(field_players, key=lambda p: distance(p.pos, ball_carrier.pos))
        closest_defender.target = Vector2(ball_carrier.pos)
        closest_defender.state = "press"
        
        # Find second closest defender for double team if close enough
        other_players = [p for p in field_players if p is not closest_defender]
        if other_players:
            second_closest = min(other_players, key=lambda p: distance(p.pos, ball_carrier.pos))
            if distance(second_closest.pos, ball_carrier.pos) <= 5 * M_TO_PX:
                second_closest.target = Vector2(ball_carrier.pos)
                second_closest.state = "press"
            else:
                # Maintain defensive shape
                second_closest.target = self.get_role_target(
                    second_closest.role,
                    ball_cell,
                    False,
                    second_closest.team,
                    second_closest.pos
                )
                second_closest.state = "defend"
        
        # Other players maintain defensive positions
        for player in field_players:
            if player is closest_defender or (other_players and player is second_closest):
                continue
                
            player.target = self.get_role_target(
                player.role,
                ball_cell,
                False,
                player.team,
                player.pos
            )
            player.state = "defend"

    def _make_ball_carrier_decision(self, carrier, team, opponents, ball, current_time):
        """Make decision for player with the ball."""
        teammates = [p for p in team if p is not carrier and p.role != "GK"]
        opponent_field_players = [o for o in opponents if o.role != "GK"]
        
        # Handle goalkeeper with ball
        if carrier.role == "GK":
            self._handle_goalkeeper_with_ball(carrier, teammates, ball, current_time)
            return
        
        # Field player with ball - evaluate options
        nearest_opponent = min(opponent_field_players, key=lambda o: distance(o.pos, carrier.pos)) if opponent_field_players else None
        under_pressure = nearest_opponent and distance(nearest_opponent.pos, carrier.pos) < 5 * M_TO_PX

        # Check shooting opportunity
        if self._should_shoot(carrier, opponent_field_players):
            self._execute_shot(carrier, ball, current_time)
            return
        
        # Under pressure - look for safe pass
        if under_pressure:
            safe_pass_option = self._find_safe_pass_option(carrier, teammates, opponent_field_players)
            if safe_pass_option:
                self._execute_pass(carrier, safe_pass_option, ball, current_time)
                return
        
        # Look for forward passing options
        forward_pass_option = self._find_forward_pass_option(carrier, teammates, opponent_field_players)
        if forward_pass_option:
            self._execute_pass(carrier, forward_pass_option, ball, current_time)
            return
        
        # Consider dribbling forward
        if self._should_dribble_forward(carrier, opponent_field_players):
            self._execute_dribble(carrier, teammates, opponent_field_players, ball, current_time)
            return
        
        # Last resort - safe pass to any teammate
        safe_fallback = self._find_safe_fallback_pass(carrier, teammates, opponent_field_players)
        if safe_fallback:
            self._execute_pass(carrier, safe_fallback, ball, current_time)
            return
        
        # Default - dribble sideways
        carrier.target = carrier.pos + Vector2(0, random.uniform(-3, 3) * M_TO_PX)
        carrier.state = "dribble"

    def _handle_goalkeeper_with_ball(self, keeper, teammates, ball, current_time):
        """Handle goalkeeper decision when they have the ball."""
        if teammates:
            # Pass to nearest teammate
            nearest_teammate = min(teammates, key=lambda m: distance(m.pos, keeper.pos))
            pass_target = predict_pass_point(keeper.pos, nearest_teammate, PASS_SPEED)
            keeper.state = "pass"
            ball.kick((pass_target - keeper.pos).normalize() * PASS_SPEED, kicker=keeper)
        else:
            # Clear the ball upfield
            if keeper.team == 0:
                clear_target = Vector2(WIDTH * 0.7, HEIGHT / 2)
            else:
                clear_target = Vector2(WIDTH * 0.3, HEIGHT / 2)
            
            clear_direction = (clear_target - keeper.pos).normalize()
            keeper.state = "clear"
            ball.kick(clear_direction * PASS_SPEED * 1.2, kicker=keeper)
        
        ball.last_kick_time = current_time
        keeper.has_ball = False
        self.last_possession_team = keeper.team

    def _should_shoot(self, player, opponents):
        """Determine if player should shoot at goal."""
        goal_position = Vector2(WIDTH, HEIGHT / 2) if player.team == 0 else Vector2(0, HEIGHT / 2)
        distance_to_goal = distance(player.pos, goal_position)
        
        if distance_to_goal > 25 * M_TO_PX:
            return False
        
        to_goal = (goal_position - player.pos)
        if to_goal.length() == 0:
            return False
            
        to_goal = to_goal.normalize()
        ideal_direction = Vector2(1, 0) if player.team == 0 else Vector2(-1, 0)
        angle_to_goal = abs(to_goal.angle_to(ideal_direction))
        
        if angle_to_goal > 45:
            return False
        
        # Check if defenders are blocking the shot
        return not any_defender_between(player.pos, goal_position, opponents, 3 * M_TO_PX)

    def _execute_shot(self, player, ball, current_time):
        """Execute a shot at goal."""
        goal_position = Vector2(WIDTH, HEIGHT / 2) if player.team == 0 else Vector2(0, HEIGHT / 2)
        distance_to_goal = distance(player.pos, goal_position)
        
        # Add some error to the shot
        error = Vector2(random.uniform(-1, 1), random.uniform(-1, 1)) * SHOT_ERROR_RATIO * distance_to_goal
        shot_target = goal_position + error
        
        # Scale shot power based on distance
        shot_power = SHOT_SPEED * (0.7 + 0.3 * (distance_to_goal / (25 * M_TO_PX)))
        
        player.state = "shoot"
        ball.kick((shot_target - player.pos).normalize() * shot_power, kicker=player)
        ball.last_kick_time = current_time
        player.has_ball = False
        self.last_possession_team = player.team

    def _find_safe_pass_option(self, passer, teammates, opponents):
        """Find a safe passing option under pressure."""
        safe_options = []
        
        for teammate in teammates:
            nearest_defender = min(distance(teammate.pos, d.pos) for d in opponents) if opponents else 9999
            pass_blocked = opponent_will_intercept(passer.pos, teammate.pos, opponents, PASS_SPEED)
            
            if nearest_defender > 3 * M_TO_PX and not pass_blocked:
                safety_score = nearest_defender - (100 if pass_blocked else 0)
                safe_options.append((teammate, safety_score))
        
        if safe_options:
            safe_options.sort(key=lambda x: -x[1])  # Sort by safety score descending
            return safe_options[0][0]
        
        return None

    def _find_forward_pass_option(self, passer, teammates, opponents):
        """Find a forward passing option to advance the play."""
        forward_options = []
        
        for teammate in teammates:
            nearest_defender = min(distance(teammate.pos, d.pos) for d in opponents) if opponents else 9999
            in_clear_space = nearest_defender > 5 * M_TO_PX
            
            # Check if teammate is forward of passer
            is_forward = (teammate.pos.x > passer.pos.x) if passer.team == 0 else (teammate.pos.x < passer.pos.x)
            pass_blocked = opponent_will_intercept(passer.pos, teammate.pos, opponents, PASS_SPEED)
            
            if in_clear_space and is_forward and not pass_blocked:
                advance_distance = abs(teammate.pos.x - passer.pos.x)
                forward_options.append((teammate, advance_distance))
        
        if forward_options:
            forward_options.sort(key=lambda x: -x[1])  # Sort by advance distance descending
            return forward_options[0][0]
        
        return None

    def _should_dribble_forward(self, player, opponents):
        """Determine if player should dribble forward."""
        goal_position = Vector2(WIDTH, HEIGHT / 2) if player.team == 0 else Vector2(0, HEIGHT / 2)
        direction_to_goal = (goal_position - player.pos)
        
        if direction_to_goal.length() == 0:
            return False
            
        ahead_point = player.pos + direction_to_goal.normalize() * (6 * M_TO_PX)
        defenders_near_ahead = [d for d in opponents if distance(d.pos, ahead_point) < 4 * M_TO_PX]
        
        return len(defenders_near_ahead) == 0

    def _execute_dribble(self, dribbler, teammates, opponents, ball, current_time):
        """Execute a dribble forward and look for pass."""
        goal_position = Vector2(WIDTH, HEIGHT / 2) if dribbler.team == 0 else Vector2(0, HEIGHT / 2)
        direction_to_goal = (goal_position - dribbler.pos).normalize()
        
        dribbler.target = dribbler.pos + direction_to_goal * (4 * M_TO_PX)
        dribbler.state = "dribble"
        
        # Look for pass after dribble
        dribble_pass_options = []
        for teammate in teammates:
            nearest_defender = min(distance(teammate.pos, d.pos) for d in opponents) if opponents else 9999
            in_clear_space = nearest_defender > 4 * M_TO_PX
            is_forward = (teammate.pos.x > dribbler.pos.x) if dribbler.team == 0 else (teammate.pos.x < dribbler.pos.x)
            pass_blocked = opponent_will_intercept(dribbler.pos, teammate.pos, opponents, PASS_SPEED)
            
            if in_clear_space and is_forward and not pass_blocked:
                dribble_pass_options.append(teammate)
        
        if dribble_pass_options:
            best_pass_target = max(dribble_pass_options, key=lambda m: abs(m.pos.x - dribbler.pos.x))
            pass_target = predict_pass_point(dribbler.pos, best_pass_target, PASS_SPEED)
            dribbler.state = "pass"
            ball.kick((pass_target - dribbler.pos).normalize() * PASS_SPEED, kicker=dribbler)
            ball.last_kick_time = current_time
            dribbler.has_ball = False
            self.last_possession_team = dribbler.team

    def _find_safe_fallback_pass(self, passer, teammates, opponents):
        """Find any safe pass as last resort."""
        safe_options = []
        
        for teammate in teammates:
            nearest_defender = min(distance(teammate.pos, d.pos) for d in opponents) if opponents else 9999
            pass_blocked = opponent_will_intercept(passer.pos, teammate.pos, opponents, PASS_SPEED)
            
            if nearest_defender > 3 * M_TO_PX and not pass_blocked:
                safe_options.append((teammate, nearest_defender))
        
        if safe_options:
            safe_options.sort(key=lambda x: -x[1])  # Sort by distance to nearest defender
            return safe_options[0][0]
        
        return None

    def _execute_pass(self, passer, receiver, ball, current_time):
        """Execute a pass to a teammate."""
        pass_target = predict_pass_point(passer.pos, receiver, PASS_SPEED)
        passer.state = "pass"
        ball.kick((pass_target - passer.pos).normalize() * PASS_SPEED, kicker=passer)
        ball.last_kick_time = current_time
        passer.has_ball = False
        self.last_possession_team = passer.team