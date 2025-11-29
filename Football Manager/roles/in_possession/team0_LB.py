# roles/in_possession/team0_LB.py
import pygame
from pygame.math import Vector2
import random

def in_possession(ball_cell_x, ball_cell_y, team, cell_size):
    """
    Attacking decision tree for Left Back (attacking profile)
    """
    cell_w, cell_h = cell_size
    
    # Base formation position (CORRECTED - LB is row 2, not 13)
    base_col = 3
    base_row = 2  # LB position in 4-4-2 (left side, higher up)
    
    # Convert ball position to meaningful zones
    ball_x_ratio = ball_cell_x / 24
    ball_y_ratio = ball_cell_y / 16
    
    # --- DECISION TREE: ATTACKING PHASE ---
    
    # BALL IN DEFENSIVE THIRD (build-up)
    if ball_x_ratio < 0.33:
        # Support build-up decisions
        if ball_y_ratio < 0.4:  # Ball on left side (now top of screen)
            # Show for pass, provide width
            target_col = min(5, base_col + 2)
            target_row = base_row
        else:  # Ball on right side
            # Stay wide but be ready for switch
            target_col = base_col
            target_row = base_row
            
    # BALL IN MIDFIELD
    elif ball_x_ratio < 0.66:
        # Overlap opportunities
        if ball_y_ratio < 0.3:  # Ball on left side near LM
            # AUTOMATIC OVERLAP - get ahead of play
            target_col = min(15, int(ball_cell_x) + 4)
            target_row = max(1, int(ball_cell_y) - 1)  # Stay high
        else:
            # Maintain width, support midfield
            target_col = min(10, base_col + 7)
            target_row = base_row
            
    # BALL IN ATTACKING THIRD
    else:
        # Attacking contribution
        if ball_y_ratio < 0.3:  # Ball on left side in attack
            # OVERLAP TO BYLINE - aggressive forward run
            target_col = min(20, int(ball_cell_x) + 2)
            target_row = max(1, int(ball_cell_y) - 1)
        elif ball_y_ratio > 0.7:  # Ball on right side
            # Tuck in for central support/crosses
            target_col = min(18, int(ball_cell_x) - 2)
            target_row = 4  # Central attacking position (higher up)
        else:
            # Edge of box for rebounds/crosses
            target_col = 16
            target_row = 3  # Higher attacking position
    
    # Ensure we stay in bounds
    target_col = max(1, min(22, target_col))
    target_row = max(1, min(14, target_row))
    
    # Return target position
    return Vector2(
        (target_col + 0.5) * cell_w,
        (target_row + 0.5) * cell_h
    )