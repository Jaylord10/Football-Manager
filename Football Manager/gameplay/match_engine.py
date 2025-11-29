import pygame
import random
from pygame.math import Vector2
from config.constants import *
from core.game_objects import Ball
from config.formations import spawn_team
from ai.decision_maker import AIDecisionMaker
from rendering.pitch_renderer import PitchRenderer
from rendering.object_renderer import ObjectRenderer
from rendering.ui_renderer import UIRenderer
from gameplay.mechanics import GameMechanics
from gameplay.offside import OffsideSystem

class MatchEngine:
    def __init__(self):
        # Initialize pygame
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH + FIELD_MARGIN*2, HEIGHT + FIELD_MARGIN*2))
        pygame.display.set_caption("11v11 Football Simulation - Professional Version")
        self.clock = pygame.time.Clock()
        
        # Initialize systems
        self.ai = AIDecisionMaker()
        self.pitch_renderer = PitchRenderer()
        self.object_renderer = ObjectRenderer()
        self.ui_renderer = UIRenderer()
        self.mechanics = GameMechanics()
        self.offside_system = OffsideSystem()
        
        # Initialize game state
        self.team0 = spawn_team(0)
        self.team1 = spawn_team(1)
        self.ball = Ball(Vector2(WIDTH/2, HEIGHT/2))
        
        self.score = [0, 0]
        self.running = True
        self.paused = False
        self.time_elapsed = 0.0
        
        self._initialize_game()

    def _initialize_game(self):
        """Initialize the game with a kickoff."""
        all_field_players = [p for p in self.team0 + self.team1 if p.role != "GK"]
        kick_off_player = random.choice(all_field_players)
        self.ball.owner = kick_off_player
        kick_off_player.has_ball = True
        self.ai.last_possession_team = kick_off_player.team

    def run(self):
        """Main game loop."""
        while self.running:
            delta_time = self.clock.tick(FPS) / 1000.0
            self.time_elapsed += delta_time
            
            self._handle_events()
            if self.paused:
                self._render_paused()
                continue
            
            self._update_game(delta_time)
            self._render()
            
        pygame.quit()

    def _handle_events(self):
        """Handle pygame events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    self.paused = not self.paused
                if event.key == pygame.K_r:
                    self._reset_match()

    def _update_game(self, delta_time):
        """Update all game systems."""
        # AI decisions
        self.ai.make_team_decisions(self.team0, self.team1, self.ball, self.time_elapsed)
        self.ai.make_team_decisions(self.team1, self.team0, self.ball, self.time_elapsed)
        
        # Game mechanics
        self.mechanics.handle_tackles(self.team0, self.team1, self.ball, self.time_elapsed)
        self.mechanics.handle_loose_balls(self.team0 + self.team1, self.ball)
        self.mechanics.update_goalkeeper_dive_states(self.team0, self.team1, self.time_elapsed)
        
        # Offside check
        self._check_offside()
        
        # Update objects
        for player in self.team0 + self.team1:
            player.update(delta_time)
        self.ball.update(delta_time, self.time_elapsed)
        
        # More mechanics
        self.mechanics.handle_goalkeeper_interactions(self.team0, self.team1, self.ball, self.time_elapsed, self.ai)
        self.mechanics.handle_possession_pickup(self.team0, self.team1, self.ball, self.time_elapsed, self.ai)
        
        # Goal check
        goal_scorer = self.mechanics.check_goal(self.ball)
        if goal_scorer is not None:
            self.score[goal_scorer] += 1
            self._reset_after_goal(goal_scorer)

    def _check_offside(self):
        """Check for offside violations."""
        # Handle offside reset
        if (self.offside_system.offside_detected and 
            self.time_elapsed - self.offside_system.offside_reset_time > 2.0):
            self.offside_system.handle_offside_reset(
                self.offside_system.offside_team, 
                self.offside_system.offside_line_x, 
                self.team0, self.team1, self.ball, self.time_elapsed
            )
        
        # Check for new offside violations - only on forward passes
        if (not self.offside_system.offside_detected and 
            self.ball.vel.length() > 10 and 
            self.ball.last_pass_time + 0.1 > self.time_elapsed and
            self.ball.pass_start_pos):
            
            # Only check for forward passes
            if self.ai.last_possession_team == 0:  # Blue team
                is_forward_pass = self.ball.vel.x > 0  # Moving right
            else:  # Red team
                is_forward_pass = self.ball.vel.x < 0  # Moving left
                
            if is_forward_pass:
                if self.ai.last_possession_team == 0:
                    offside_players = self.offside_system.check_offside(
                        self.team0, self.team1, self.ball, self.time_elapsed
                    )
                    if offside_players:
                        self.offside_system.offside_detected = True
                        self.offside_system.offside_team = 0
                        self.offside_system.offside_reset_time = self.time_elapsed
                        # Find offside line for visualization
                        defenders = [p for p in self.team1]  # Include GK
                        defenders.sort(key=lambda p: p.pos.x, reverse=True)
                        if len(defenders) >= 2:
                            self.offside_system.offside_line_x = defenders[1].pos.x
                else:
                    offside_players = self.offside_system.check_offside(
                        self.team1, self.team0, self.ball, self.time_elapsed
                    )
                    if offside_players:
                        self.offside_system.offside_detected = True
                        self.offside_system.offside_team = 1
                        self.offside_system.offside_reset_time = self.time_elapsed
                        defenders = [p for p in self.team0]  # Include GK
                        defenders.sort(key=lambda p: p.pos.x)
                        if len(defenders) >= 2:
                            self.offside_system.offside_line_x = defenders[1].pos.x

    def _render(self):
        """Render the complete game state."""
        # Draw pitch
        self.pitch_renderer.draw_pitch(self.screen)
        
        # Draw offside line if detected
        if self.offside_system.offside_detected:
            self.offside_system.draw_offside_line(
                self.screen, 
                self.offside_system.offside_line_x, 
                self.offside_system.offside_team
            )
        
        # Draw objects
        self.object_renderer.draw_players(self.screen, self.team0 + self.team1, self.ui_renderer.normal_font)
        self.object_renderer.draw_ball(self.screen, self.ball)
        
        # Draw UI
        self.ui_renderer.draw_ui(self.screen, self.score, self.time_elapsed, self.ball)
        
        # Draw offside message
        if self.offside_system.offside_detected:
            self.ui_renderer.draw_offside_message(self.screen)
        
        # Draw winner message
        if self.score[0] >= FIRST_TO or self.score[1] >= FIRST_TO:
            self.ui_renderer.draw_winner_message(self.screen, self.score, FIRST_TO)
        
        pygame.display.flip()

    def _render_paused(self):
        """Render paused game state."""
        self.pitch_renderer.draw_pitch(self.screen)
        self.object_renderer.draw_players(self.screen, self.team0 + self.team1, self.ui_renderer.normal_font)
        self.object_renderer.draw_ball(self.screen, self.ball)
        self.ui_renderer.draw_paused_message(self.screen)
        pygame.display.flip()

    def _reset_after_goal(self, goal_scorer):
        """Reset game after a goal is scored."""
        self.mechanics.reset_game(self.team0, self.team1, self.ball, self.ai)
        # Give ball to conceding team
        conceding_team = self.team1 if goal_scorer == 0 else self.team0
        field_players = [p for p in conceding_team if p.role != "GK"]
        if field_players:
            kicker = random.choice(field_players)
            self.ball.owner = kicker
            kicker.has_ball = True
            self.ai.last_possession_team = kicker.team

    def _reset_match(self):
        """Reset the entire match."""
        self.score = [0, 0]
        self.mechanics.reset_game(self.team0, self.team1, self.ball, self.ai)
        self.offside_system.offside_detected = False