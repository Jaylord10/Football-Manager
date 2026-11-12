import pygame
import math
from pygame.math import Vector2
from config.constants import *

class ObjectRenderer:
    def __init__(self):
        pass

    def draw_players(self, surface, players, font):
        # Draw players sorted by Y position so lower players overlap higher ones
        sorted_players = sorted((p for p in players if getattr(p, "is_active", True)),
                                key=lambda p: p.pos.y)          # sent-off players aren't drawn
        for player in sorted_players:
            self._draw_player_complex(surface, player, font)

    def _draw_player_complex(self, surface, player, font):
        # (Paste your existing _draw_player_complex code here)
        # It doesn't change, just using the one we built previously
        x = int(player.pos.x) + FIELD_MARGIN
        y = int(player.pos.y) + FIELD_MARGIN
        if player.team == 0: jersey_color = (30, 144, 255) 
        else: jersey_color = (220, 20, 60)  
        skin_color = (255, 220, 177); hair_color = (60, 40, 30); outline_color = (20, 20, 20)
        angle = math.degrees(math.atan2(player.facing.y, player.facing.x))
        rotation = -angle 
        size = int(PLAYER_RADIUS * 4.0); player_surf = pygame.Surface((size, size), pygame.SRCALPHA)
        c_x, c_y = size // 2, size // 2; r = PLAYER_RADIUS
        arm_dist_y = r * 0.8; arm_dist_x = r * 0.2; arm_r = r * 0.4
        pygame.draw.circle(player_surf, skin_color, (c_x + arm_dist_x, c_y - arm_dist_y), arm_r)
        pygame.draw.circle(player_surf, outline_color, (c_x + arm_dist_x, c_y - arm_dist_y), arm_r, 1)
        pygame.draw.circle(player_surf, skin_color, (c_x + arm_dist_x, c_y + arm_dist_y), arm_r)
        pygame.draw.circle(player_surf, outline_color, (c_x + arm_dist_x, c_y + arm_dist_y), arm_r, 1)
        shldr_w = int(r * 2.1); shldr_h = int(r * 2.3)
        shldr_rect = pygame.Rect(c_x - shldr_w//2, c_y - shldr_h//2, shldr_w, shldr_h)
        pygame.draw.rect(player_surf, jersey_color, shldr_rect, border_radius=int(r*0.7))
        pygame.draw.rect(player_surf, outline_color, shldr_rect, width=2, border_radius=int(r*0.7))
        head_r = int(r * 0.6)
        pygame.draw.circle(player_surf, hair_color, (c_x, c_y), head_r)
        pygame.draw.circle(player_surf, outline_color, (c_x, c_y), head_r, 1)
        rotated_surf = pygame.transform.rotate(player_surf, rotation)
        new_rect = rotated_surf.get_rect(center=(x, y))
        surface.blit(rotated_surf, new_rect)
        if player.has_ball:
            label_text = getattr(player, "name", player.role)
            label = font.render(label_text, True, WHITE)
            shadow = font.render(label_text, True, BLACK)
            text_rect = label.get_rect(center=(x, y - 30)) 
            surface.blit(shadow, (text_rect.x + 1, text_rect.y + 1)); surface.blit(label, text_rect)
        self._draw_stamina_bar(surface, player, (x, y))

    def _draw_stamina_bar(self, surface, player, screen_pos):
        bar_width = 28; x = int(screen_pos[0] - bar_width / 2); y = int(screen_pos[1] + PLAYER_RADIUS + 10)
        pygame.draw.rect(surface, (50, 50, 50), (x, y, bar_width, 4))
        if player.stamina > 0.6: col = (60, 200, 80)
        elif player.stamina > 0.3: col = (220, 200, 60)
        else: col = (200, 60, 60)
        pygame.draw.rect(surface, col, (x, y, int(bar_width * player.stamina), 4))

    # --- NEW: 3D BALL RENDERING ---
    def draw_ball(self, surface, ball):
        """Draws ball with 3D illusion (Shadow + Height offset)."""
        # 1. Shadow (Always on the ground)
        shadow_pos = (int(ball.pos.x) + FIELD_MARGIN, int(ball.pos.y) + FIELD_MARGIN)
        
        # Shadow grows smaller/fainter as ball gets higher
        shadow_scale = max(0.4, 1.0 - (ball.z / 150.0))
        shadow_radius = int(BALL_RADIUS * shadow_scale)
        pygame.draw.circle(surface, (0, 0, 0, 100), shadow_pos, shadow_radius)
        
        # 2. Ball Body (Shifted UP by Z)
        # We subtract Z from Y because screen Y goes down
        ball_visual_y = ball.pos.y - ball.z 
        ball_pos_visual = (int(ball.pos.x) + FIELD_MARGIN, int(ball_visual_y) + FIELD_MARGIN)
        
        # Ball grows slightly larger when high (perspective)
        scale_factor = 1.0 + (ball.z / 300.0)
        visual_radius = int(BALL_RADIUS * scale_factor)
        
        pygame.draw.circle(surface, WHITE, ball_pos_visual, visual_radius)
        pygame.draw.circle(surface, BLACK, ball_pos_visual, visual_radius, 1)