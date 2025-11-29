import pygame
from config.constants import *

class ObjectRenderer:
    def __init__(self):
        pass

    def draw_players(self, surface, players, font):
        """Draw all players on the surface."""
        for player in players:
            self._draw_player(surface, player, font)

    def _draw_player(self, surface, player, font):
        """Draw a single player."""
        color = BLUE if player.team == 0 else RED
        screen_pos = (int(player.pos.x) + FIELD_MARGIN, int(player.pos.y) + FIELD_MARGIN)
        
        # Draw player circle
        pygame.draw.circle(surface, color, screen_pos, PLAYER_RADIUS)
        pygame.draw.circle(surface, BLACK, screen_pos, PLAYER_RADIUS, 2)
        
        # Draw role label
        label = font.render(player.role, True, BLACK)
        surface.blit(label, (player.pos.x - 20 + FIELD_MARGIN, player.pos.y - 28 + FIELD_MARGIN))
        
        # Draw ball indicator if player has ball
        if player.has_ball:
            pygame.draw.circle(surface, YELLOW, screen_pos, PLAYER_RADIUS // 2)
        
        # Draw stamina bar
        self._draw_stamina_bar(surface, player, screen_pos)

    def _draw_stamina_bar(self, surface, player, screen_pos):
        """Draw player stamina bar."""
        bar_width = 28
        x = int(player.pos.x - bar_width / 2) + FIELD_MARGIN
        y = int(player.pos.y + PLAYER_RADIUS + 6) + FIELD_MARGIN
        
        pygame.draw.rect(surface, (50, 50, 50), (x, y, bar_width, 6))
        pygame.draw.rect(surface, (60, 200, 80), (x, y, int(bar_width * player.stamina), 6))

    def draw_ball(self, surface, ball):
        """Draw the ball on the surface."""
        ball_pos = (int(ball.pos.x) + FIELD_MARGIN, int(ball.pos.y) + FIELD_MARGIN)
        pygame.draw.circle(surface, WHITE, ball_pos, BALL_RADIUS)
        pygame.draw.circle(surface, BLACK, ball_pos, BALL_RADIUS, 1)