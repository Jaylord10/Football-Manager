import pygame
import math
from config.constants import *

class PitchRenderer:
    def __init__(self):
        pass

    def draw_pitch(self, surface):
        surface.fill(GRASS_A)
        self._draw_grass_stripes(surface)
        self._draw_boundaries(surface)
        self._draw_center(surface)
        self._draw_goals(surface)
        self._draw_penalty_areas(surface)
        self._draw_goal_areas(surface)
        self._draw_penalty_spots(surface)
        self._draw_corners(surface)
        self._draw_grid(surface)

    def _draw_grass_stripes(self, surface):
        stripe_width = CELL_W * 2
        for i in range(int(WIDTH / stripe_width) + 3):
            rect = pygame.Rect(int(i * stripe_width), 0, int(stripe_width / 2), HEIGHT)
            pygame.draw.rect(surface, GRASS_B, rect)

    def _draw_boundaries(self, surface):
        pygame.draw.rect(surface, WHITE, (FIELD_MARGIN, FIELD_MARGIN, WIDTH, HEIGHT), 4)

    def _draw_center(self, surface):
        pygame.draw.line(surface, WHITE, (FIELD_MARGIN + WIDTH//2, FIELD_MARGIN), 
                        (FIELD_MARGIN + WIDTH//2, FIELD_MARGIN + HEIGHT), 2)
        pygame.draw.circle(surface, WHITE, (FIELD_MARGIN + WIDTH//2, FIELD_MARGIN + HEIGHT//2), 
                          int(9.15 * M_TO_PX), 2)

    def _draw_goals(self, surface):
        left_goal = pygame.Rect(FIELD_MARGIN - int(2 * M_TO_PX), 
                               FIELD_MARGIN + int(HEIGHT/2 - GOAL_WIDTH/2), 
                               int(2 * M_TO_PX), int(GOAL_WIDTH))
        right_goal = pygame.Rect(FIELD_MARGIN + WIDTH, 
                                FIELD_MARGIN + int(HEIGHT/2 - GOAL_WIDTH/2), 
                                int(2 * M_TO_PX), int(GOAL_WIDTH))
        pygame.draw.rect(surface, GOAL_COLOR, left_goal)
        pygame.draw.rect(surface, GOAL_COLOR, right_goal)

    def _draw_penalty_areas(self, surface):
        left_penalty = pygame.Rect(FIELD_MARGIN, 
                                  FIELD_MARGIN + HEIGHT//2 - int(PENALTY_AREA_WIDTH/2), 
                                  int(PENALTY_AREA_DEPTH), int(PENALTY_AREA_WIDTH))
        right_penalty = pygame.Rect(FIELD_MARGIN + WIDTH - int(PENALTY_AREA_DEPTH), 
                                   FIELD_MARGIN + HEIGHT//2 - int(PENALTY_AREA_WIDTH/2), 
                                   int(PENALTY_AREA_DEPTH), int(PENALTY_AREA_WIDTH))
        pygame.draw.rect(surface, WHITE, left_penalty, 2)
        pygame.draw.rect(surface, WHITE, right_penalty, 2)

    def _draw_goal_areas(self, surface):
        left_goal_area = pygame.Rect(FIELD_MARGIN, 
                                    FIELD_MARGIN + HEIGHT//2 - int(GOAL_AREA_WIDTH/2), 
                                    int(GOAL_AREA_DEPTH), int(GOAL_AREA_WIDTH))
        right_goal_area = pygame.Rect(FIELD_MARGIN + WIDTH - int(GOAL_AREA_DEPTH), 
                                     FIELD_MARGIN + HEIGHT//2 - int(GOAL_AREA_WIDTH/2), 
                                     int(GOAL_AREA_DEPTH), int(GOAL_AREA_WIDTH))
        pygame.draw.rect(surface, WHITE, left_goal_area, 2)
        pygame.draw.rect(surface, WHITE, right_goal_area, 2)

    def _draw_penalty_spots(self, surface):
        left_penalty_spot = (FIELD_MARGIN + int(PENALTY_SPOT_DISTANCE), 
                            FIELD_MARGIN + HEIGHT//2)
        right_penalty_spot = (FIELD_MARGIN + WIDTH - int(PENALTY_SPOT_DISTANCE), 
                             FIELD_MARGIN + HEIGHT//2)
        
        pygame.draw.circle(surface, WHITE, left_penalty_spot, int(0.2 * M_TO_PX))
        pygame.draw.circle(surface, WHITE, right_penalty_spot, int(0.2 * M_TO_PX))
        
        # Draw penalty arcs
        left_arc_rect = (left_penalty_spot[0] - int(PENALTY_ARC_RADIUS),
                         left_penalty_spot[1] - int(PENALTY_ARC_RADIUS),
                         int(PENALTY_ARC_RADIUS * 2), int(PENALTY_ARC_RADIUS * 2))
        pygame.draw.arc(surface, WHITE, left_arc_rect, -math.pi/2, math.pi/2, 2)
        
        right_arc_rect = (right_penalty_spot[0] - int(PENALTY_ARC_RADIUS),
                          right_penalty_spot[1] - int(PENALTY_ARC_RADIUS),
                          int(PENALTY_ARC_RADIUS * 2), int(PENALTY_ARC_RADIUS * 2))
        pygame.draw.arc(surface, WHITE, right_arc_rect, math.pi/2, 3*math.pi/2, 2)

    def _draw_corners(self, surface):
        corner_arc_radius = int(1 * M_TO_PX)
        
        # Four corners
        corners = [
            (FIELD_MARGIN, FIELD_MARGIN),  # Top-left
            (FIELD_MARGIN, FIELD_MARGIN + HEIGHT),  # Bottom-left
            (FIELD_MARGIN + WIDTH, FIELD_MARGIN),  # Top-right
            (FIELD_MARGIN + WIDTH, FIELD_MARGIN + HEIGHT)  # Bottom-right
        ]
        
        arc_params = [
            (0, math.pi/2),  # Top-left
            (3*math.pi/2, 2*math.pi),  # Bottom-left
            (math.pi/2, math.pi),  # Top-right
            (math.pi, 3*math.pi/2)  # Bottom-right
        ]
        
        for (corner_x, corner_y), (start_angle, end_angle) in zip(corners, arc_params):
            arc_rect = (corner_x - corner_arc_radius, corner_y - corner_arc_radius,
                        corner_arc_radius * 2, corner_arc_radius * 2)
            pygame.draw.arc(surface, WHITE, arc_rect, start_angle, end_angle, 2)

    def _draw_grid(self, surface):
        # Vertical grid lines
        for col in range(GRID_COLS + 1):
            x = FIELD_MARGIN + int(col * CELL_W)
            pygame.draw.line(surface, GRID_COLOR, (x, FIELD_MARGIN), (x, FIELD_MARGIN + HEIGHT), 1)
        
        # Horizontal grid lines
        for row in range(GRID_ROWS + 1):
            y = FIELD_MARGIN + int(row * CELL_H)
            pygame.draw.line(surface, GRID_COLOR, (FIELD_MARGIN, y), (FIELD_MARGIN + WIDTH, y), 1)
        
        # Cell coordinates
        for col in range(GRID_COLS):
            for row in range(GRID_ROWS):
                x = FIELD_MARGIN + int((col + 0.02) * CELL_W)
                y = FIELD_MARGIN + int((row + 0.02) * CELL_H)
                # Note: font will be passed from main renderer
                # Label rendering moved to UIRenderer to avoid font dependency