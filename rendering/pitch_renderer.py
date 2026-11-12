import pygame
import math
from config.constants import *

# Pitch line thickness (pixels)
_LINE_W   = 2   # standard markings
_BOUND_W  = 3   # outer boundary (slightly bolder)

# Stripe width: 10 m → ~11 stripe-pairs across a 110 m pitch
_STRIPE_W = int(10 * M_TO_PX)

class PitchRenderer:
    def __init__(self):
        pass

    def draw_pitch(self, surface):
        # 1. Fill entire surface with outer-surround colour
        surface.fill(GRASS_OUT)
        # 2. Light-green base for the playing area
        pitch_rect = pygame.Rect(FIELD_MARGIN, FIELD_MARGIN, WIDTH, HEIGHT)
        pygame.draw.rect(surface, GRASS_A, pitch_rect)
        # 3. Dark stripe overlays — restricted to the pitch area
        self._draw_grass_stripes(surface)
        # 4. All pitch markings on top
        self._draw_boundaries(surface)
        self._draw_center(surface)
        self._draw_goals(surface)
        self._draw_penalty_areas(surface)
        self._draw_goal_areas(surface)
        self._draw_penalty_spots(surface)
        self._draw_corners(surface)
        self._draw_grid(surface)

    def _draw_grass_stripes(self, surface):
        """Alternating light / dark stripes clipped to the pitch rectangle."""
        pitch_rect = pygame.Rect(FIELD_MARGIN, FIELD_MARGIN, WIDTH, HEIGHT)
        # Every other stripe gets the dark colour; light is the GRASS_A base already drawn
        num_stripes = int(WIDTH / _STRIPE_W) + 2
        for i in range(num_stripes):
            if i % 2 == 0:
                continue   # skip — base GRASS_A already showing
            x = FIELD_MARGIN + i * _STRIPE_W
            stripe_rect = pygame.Rect(x, FIELD_MARGIN, _STRIPE_W, HEIGHT)
            # Clip to pitch boundary so stripes never bleed into the margin
            clipped = stripe_rect.clip(pitch_rect)
            if clipped.width > 0:
                pygame.draw.rect(surface, GRASS_B, clipped)

    def _draw_boundaries(self, surface):
        pygame.draw.rect(surface, WHITE, (FIELD_MARGIN, FIELD_MARGIN, WIDTH, HEIGHT), _BOUND_W)

    def _draw_center(self, surface):
        cx = FIELD_MARGIN + WIDTH  // 2
        cy = FIELD_MARGIN + HEIGHT // 2
        # Halfway line
        pygame.draw.line(surface, WHITE, (cx, FIELD_MARGIN), (cx, FIELD_MARGIN + HEIGHT), _LINE_W)
        # Centre circle
        pygame.draw.circle(surface, WHITE, (cx, cy), int(9.15 * M_TO_PX), _LINE_W)
        # Centre spot
        pygame.draw.circle(surface, WHITE, (cx, cy), int(0.25 * M_TO_PX))

    def _draw_goals(self, surface):
        """Goals drawn as white outline boxes (matching real top-down footage)."""
        left_goal = pygame.Rect(
            FIELD_MARGIN - int(2 * M_TO_PX),
            FIELD_MARGIN + int(HEIGHT / 2 - GOAL_WIDTH / 2),
            int(2 * M_TO_PX), int(GOAL_WIDTH)
        )
        right_goal = pygame.Rect(
            FIELD_MARGIN + WIDTH,
            FIELD_MARGIN + int(HEIGHT / 2 - GOAL_WIDTH / 2),
            int(2 * M_TO_PX), int(GOAL_WIDTH)
        )
        # Fill with a very slightly lighter grass shade so the nets read clearly
        pygame.draw.rect(surface, GRASS_A, left_goal)
        pygame.draw.rect(surface, GRASS_A, right_goal)
        # White outline
        pygame.draw.rect(surface, WHITE, left_goal,  _LINE_W)
        pygame.draw.rect(surface, WHITE, right_goal, _LINE_W)

    def _draw_penalty_areas(self, surface):
        left_penalty = pygame.Rect(
            FIELD_MARGIN,
            FIELD_MARGIN + HEIGHT // 2 - int(PENALTY_AREA_WIDTH / 2),
            int(PENALTY_AREA_DEPTH), int(PENALTY_AREA_WIDTH)
        )
        right_penalty = pygame.Rect(
            FIELD_MARGIN + WIDTH - int(PENALTY_AREA_DEPTH),
            FIELD_MARGIN + HEIGHT // 2 - int(PENALTY_AREA_WIDTH / 2),
            int(PENALTY_AREA_DEPTH), int(PENALTY_AREA_WIDTH)
        )
        pygame.draw.rect(surface, WHITE, left_penalty,  _LINE_W)
        pygame.draw.rect(surface, WHITE, right_penalty, _LINE_W)

    def _draw_goal_areas(self, surface):
        left_goal_area = pygame.Rect(
            FIELD_MARGIN,
            FIELD_MARGIN + HEIGHT // 2 - int(GOAL_AREA_WIDTH / 2),
            int(GOAL_AREA_DEPTH), int(GOAL_AREA_WIDTH)
        )
        right_goal_area = pygame.Rect(
            FIELD_MARGIN + WIDTH - int(GOAL_AREA_DEPTH),
            FIELD_MARGIN + HEIGHT // 2 - int(GOAL_AREA_WIDTH / 2),
            int(GOAL_AREA_DEPTH), int(GOAL_AREA_WIDTH)
        )
        pygame.draw.rect(surface, WHITE, left_goal_area,  _LINE_W)
        pygame.draw.rect(surface, WHITE, right_goal_area, _LINE_W)

    def _draw_penalty_spots(self, surface):
        left_spot  = (FIELD_MARGIN + int(PENALTY_SPOT_DISTANCE), FIELD_MARGIN + HEIGHT // 2)
        right_spot = (FIELD_MARGIN + WIDTH - int(PENALTY_SPOT_DISTANCE), FIELD_MARGIN + HEIGHT // 2)

        pygame.draw.circle(surface, WHITE, left_spot,  int(0.25 * M_TO_PX))
        pygame.draw.circle(surface, WHITE, right_spot, int(0.25 * M_TO_PX))

        # ── Penalty D arcs ────────────────────────────────────────────────
        # Only the arc segment that falls *outside* the penalty area is marked.
        # The penalty spot is 11 m from the goal line; the area edge is 16.5 m.
        # Horizontal distance from spot to area edge = 5.5 m.
        # Half-angle of the visible arc = arccos(5.5 / 9.15) ≈ 53°.
        # In pygame's arc convention (counterclockwise from east, y-axis flipped
        # so π/2 appears at screen-top), drawing from -θ to +θ produces the
        # right-facing D; mirroring around π gives the left-facing D.
        d_theta = math.acos(
            (PENALTY_AREA_DEPTH - PENALTY_SPOT_DISTANCE) / PENALTY_ARC_RADIUS
        )   # ≈ 0.925 rad  (M_TO_PX cancels in numerator/denominator)

        left_arc_rect = (
            left_spot[0]  - int(PENALTY_ARC_RADIUS),
            left_spot[1]  - int(PENALTY_ARC_RADIUS),
            int(PENALTY_ARC_RADIUS * 2), int(PENALTY_ARC_RADIUS * 2)
        )
        # Left D: arc from  -θ  counterclockwise to +θ  (rightward bulge)
        pygame.draw.arc(surface, WHITE, left_arc_rect,  -d_theta, d_theta, _LINE_W)

        right_arc_rect = (
            right_spot[0] - int(PENALTY_ARC_RADIUS),
            right_spot[1] - int(PENALTY_ARC_RADIUS),
            int(PENALTY_ARC_RADIUS * 2), int(PENALTY_ARC_RADIUS * 2)
        )
        # Right D: arc from  π-θ  counterclockwise to π+θ  (leftward bulge)
        pygame.draw.arc(surface, WHITE, right_arc_rect, math.pi - d_theta, math.pi + d_theta, _LINE_W)

    def _draw_corners(self, surface):
        r = int(1 * M_TO_PX)   # 1 m corner arc radius

        corners_and_arcs = [
            # pygame arc angles: 0 = right, pi/2 = UP the screen.  Each quarter
            # circle must curve INTO the pitch (it used to point outwards).
            ((FIELD_MARGIN,         FIELD_MARGIN),          3 * math.pi / 2, 2 * math.pi),     # top-left: right & down
            ((FIELD_MARGIN,         FIELD_MARGIN + HEIGHT), 0,              math.pi / 2),      # bottom-left: right & up
            ((FIELD_MARGIN + WIDTH, FIELD_MARGIN),          math.pi,        3 * math.pi / 2),  # top-right: left & down
            ((FIELD_MARGIN + WIDTH, FIELD_MARGIN + HEIGHT), math.pi / 2,    math.pi),          # bottom-right: left & up
        ]

        for (cx, cy), start, end in corners_and_arcs:
            arc_rect = (cx - r, cy - r, r * 2, r * 2)
            pygame.draw.arc(surface, WHITE, arc_rect, start, end, _LINE_W)

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