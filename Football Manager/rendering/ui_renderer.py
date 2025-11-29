import pygame
from config.constants import *
from core.utils import grid_cell_from_position

class UIRenderer:
    def __init__(self):
        self.normal_font = pygame.font.SysFont("Arial", FONT_SIZE_NORMAL)
        self.large_font = pygame.font.SysFont("Arial", FONT_SIZE_LARGE)

    def draw_ui(self, surface, score, current_time, ball):
        """Draw all UI elements."""
        self._draw_score(surface, score)
        self._draw_game_info(surface, current_time, ball)
        self._draw_legend(surface)

    def _draw_score(self, surface, score):
        """Draw the score display."""
        score_text = self.large_font.render(f"{score[0]}  -  {score[1]}", True, BLACK)
        surface.blit(score_text, (WIDTH // 2 - 30 + FIELD_MARGIN, 8))

    def _draw_game_info(self, surface, current_time, ball):
        """Draw game information."""
        info_text = self.normal_font.render(
            "11v11 4-4-2. Grid 24x16 shown. Roles labeled. SPACE pause  R reset", 
            True, BLACK
        )
        surface.blit(info_text, (12, 36))
        
        # Draw ball cell and time
        ball_cell = grid_cell_from_position(ball.pos)
        cell_text = self.normal_font.render(f"Ball cell: {ball_cell[0]},{ball_cell[1]}  Time: {int(current_time)}s", True, BLACK)
        surface.blit(cell_text, (12, 56))

    def _draw_legend(self, surface):
        """Draw the game legend."""
        legend_y = HEIGHT + FIELD_MARGIN - 30
        legend_text = self.normal_font.render("State: press/dribble/pass/drive/support/chase/guard/tackle", True, BLACK)
        surface.blit(legend_text, (12, legend_y))

    def draw_paused_message(self, surface):
        """Draw paused message."""
        paused_text = self.large_font.render("PAUSED - SPACE to resume", True, BLACK)
        surface.blit(paused_text, (20, 10))

    def draw_winner_message(self, surface, score, first_to):
        """Draw winner message when game is over."""
        if score[0] >= first_to or score[1] >= first_to:
            winner = "Blue" if score[0] >= first_to else "Red"
            winner_text = self.large_font.render(f"{winner} wins! Press R to restart", True, BLACK)
            surface.blit(winner_text, (WIDTH // 2 - 160 + FIELD_MARGIN, HEIGHT // 2 - 10 + FIELD_MARGIN))

    def draw_offside_message(self, surface):
        """Draw offside message."""
        offside_text = self.large_font.render("OFFSIDE!", True, (255, 0, 0))
        surface.blit(offside_text, (WIDTH // 2 - 40 + FIELD_MARGIN, HEIGHT // 2 - 50 + FIELD_MARGIN))