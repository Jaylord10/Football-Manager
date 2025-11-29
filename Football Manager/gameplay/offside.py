import pygame
from pygame.math import Vector2
from core.utils import segment_point_distance
from config.constants import OFFSIDE_MARGIN, WIDTH, HEIGHT, FIELD_MARGIN, M_TO_PX

class OffsideSystem:
    def __init__(self):
        self.offside_detected = False
        self.offside_team = None
        self.offside_reset_time = 0
        self.offside_line_x = 0

    def check_offside(self, passing_team, receiving_team, ball, current_time):
        """Check if an offside offense occurs when a pass is made."""
        # Only check within a short time after a pass
        if current_time - ball.last_pass_time > 0.5:
            return None
        
        # Only check in attacking half (more precise)
        if ball.pass_start_pos and ball.pass_start_pos.x < WIDTH * 0.6:  # Only in final 40% of pitch
            return None
        
        # Get all defenders (including GK for the second-last defender calculation)
        defenders = [p for p in receiving_team]
        if len(defenders) < 2:
            return None
        
        # CORRECT: Find second-last defender (can be GK or outfield player)
        # Sort defenders by distance to their own goal line
        if passing_team[0].team == 0:  # Blue team attacking right
            # For blue attacking right, sort by x position (closest to right goal = defender's goal)
            defenders.sort(key=lambda p: p.pos.x, reverse=True)
        else:  # Red team attacking left  
            # For red attacking left, sort by x position (closest to left goal = defender's goal)
            defenders.sort(key=lambda p: p.pos.x)
        
        # The second-last defender is the one creating the offside line
        # This can be any player including the goalkeeper
        second_last_defender = defenders[1] if len(defenders) >= 2 else defenders[0]
        offside_line_x = second_last_defender.pos.x
        
        # Check all attacking players for offside position
        attackers = [p for p in passing_team if p.role != "GK"]  # Only outfield attackers
        offside_players = []
        
        for attacker in attackers:
            # Is this attacker ahead of the offside line?
            if passing_team[0].team == 0:  # Blue team attacking right
                is_offside_position = attacker.pos.x > offside_line_x + OFFSIDE_MARGIN
            else:  # Red team attacking left
                is_offside_position = attacker.pos.x < offside_line_x - OFFSIDE_MARGIN
            
            if is_offside_position:
                # Only flag as offside if actively involved in play
                if self._is_involved_in_play(attacker, ball, passing_team[0].team):
                    offside_players.append(attacker)
                    print(f"OFFSIDE: {attacker.role} at ({attacker.pos.x:.1f}, {attacker.pos.y:.1f}) - offside line at {offside_line_x:.1f}")
        
        return offside_players if offside_players else None

    def _is_involved_in_play(self, attacker, ball, attacking_team):
        """Determine if an attacker in offside position is actively involved in play."""
        # If attacker has the ball, definitely involved
        if attacker.has_ball:
            return True
        
        # If ball is very close to attacker, involved
        if (attacker.pos - ball.pos).length() < 8 * M_TO_PX:  # 8 meters
            return True
        
        # Check if moving toward ball with clear intent
        if attacker.vel.length_squared() > 0:
            to_ball = (ball.pos - attacker.pos)
            if to_ball.length_squared() > 0:  # Avoid division by zero
                to_ball = to_ball.normalize()
                facing = attacker.vel.normalize()
                # Only involved if clearly moving toward ball
                if to_ball.dot(facing) > 0.8:  # Very high threshold
                    return True
        
        # Check if in the path of the pass
        if ball.pass_start_pos:
            ball_trajectory = ball.pos - ball.pass_start_pos
            if ball_trajectory.length_squared() > 0:
                # Only consider if ball is moving toward attacker's general area
                to_attacker = (attacker.pos - ball.pass_start_pos)
                if to_attacker.length_squared() > 0:
                    to_attacker = to_attacker.normalize()
                    ball_dir = ball_trajectory.normalize()
                    
                    # If ball is generally moving toward attacker
                    if to_attacker.dot(ball_dir) > 0.7:
                        distance_to_trajectory = segment_point_distance(ball.pass_start_pos, ball.pos, attacker.pos)
                        if distance_to_trajectory < 5 * M_TO_PX:  # 5 meters from trajectory
                            return True
        
        # Check if obstructing goalkeeper's view or challenging for ball
        if attacking_team == 0:  # Blue attacking right
            goal_pos = Vector2(WIDTH, HEIGHT / 2)
        else:  # Red attacking left
            goal_pos = Vector2(0, HEIGHT / 2)
            
        # If attacker is between ball and goal, might be interfering
        ball_to_goal = goal_pos - ball.pos
        if ball_to_goal.length_squared() > 0:
            ball_to_goal = ball_to_goal.normalize()
            attacker_to_goal = goal_pos - attacker.pos
            if attacker_to_goal.length_squared() > 0:
                attacker_to_goal = attacker_to_goal.normalize()
                # If attacker is in the line from ball to goal
                if ball_to_goal.dot(attacker_to_goal) > 0.9 and (attacker.pos - ball.pos).length() < 15 * M_TO_PX:
                    return True
        
        return False

    def handle_offside_reset(self, offside_team, offside_line_x, team0, team1, ball, current_time):
        """Reset game state after offside call."""
        if offside_team == 0:
            # Free kick for team1 from offside position
            free_kick_pos = Vector2(offside_line_x - 8 * M_TO_PX, HEIGHT / 2)  # 8 meters back
            # Ensure free kick is in reasonable position
            free_kick_pos.x = max(free_kick_pos.x, WIDTH * 0.3)  # Not too deep in own half
            ball.pos = free_kick_pos
            ball.vel = Vector2(0, 0)
            ball.owner = None
            # Find nearest defender to take free kick
            defender = min([p for p in team1 if p.role != "GK"], key=lambda p: (p.pos - free_kick_pos).length())
            ball.owner = defender
            defender.has_ball = True
            print(f"Offside! Free kick for team1 at {free_kick_pos}")
        else:
            # Free kick for team0
            free_kick_pos = Vector2(offside_line_x + 8 * M_TO_PX, HEIGHT / 2)  # 8 meters back
            # Ensure free kick is in reasonable position
            free_kick_pos.x = min(free_kick_pos.x, WIDTH * 0.7)  # Not too deep in own half
            ball.pos = free_kick_pos
            ball.vel = Vector2(0, 0)
            ball.owner = None
            defender = min([p for p in team0 if p.role != "GK"], key=lambda p: (p.pos - free_kick_pos).length())
            ball.owner = defender
            defender.has_ball = True
            print(f"Offside! Free kick for team0 at {free_kick_pos}")
        
        self.offside_detected = False
        self.offside_team = None

    def draw_offside_line(self, surface, offside_line_x, team_attacking):
        """Draw the offside line for visualization."""
        if team_attacking == 0:  # Blue attacking right
            x_pos = FIELD_MARGIN + offside_line_x
        else:  # Red attacking left
            x_pos = FIELD_MARGIN + offside_line_x
        
        # Draw dashed yellow line
        dash_length = 10
        for y in range(FIELD_MARGIN, FIELD_MARGIN + HEIGHT, dash_length * 2):
            pygame.draw.line(surface, (255, 255, 0), 
                            (x_pos, y), 
                            (x_pos, y + dash_length), 
                            2)