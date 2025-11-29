# roles/out_of_possession/team1_RB.py
import pygame
from pygame.math import Vector2
import random

def out_of_possession(ball_cell_x, ball_cell_y, team, cell_size, current_pos):
    """
    Defensive decision tree for Right Back (team1 - defending right side)
    """
    cell_w, cell_h = cell_size
    
    # Base defensive position
    base_col = 20
    base_row = 2
    
    # Convert ball position to meaningful zones
    ball_x_ratio = ball_cell_x / 24
    ball_y_ratio = ball_cell_y / 16
    
    # --- DECISION TREE: DEFENSIVE PHASE ---
    
    # BALL IN OUR DEFENSIVE THIRD (HIGH DANGER)
    if ball_x_ratio > 0.66:  # Ball in our defensive third
        if ball_y_ratio < 0.4:  # Ball on our right side (OUR ZONE)
            # DIRECT DEFENSIVE ACTION - close down immediately
            target_col = max(16, int(ball_cell_x) - 1)
            target_row = int(ball_cell_y)
        elif ball_y_ratio < 0.6:  # Ball central in our third
            # TUCK IN - help central defense
            target_col = base_col - 1
            target_row = 4  # More central
        else:  # Ball on left side
            # COVER FAR POST - defensive shape
            target_col = base_col
            target_row = 4
            
    # BALL IN MIDFIELD (MEDIUM DANGER)
    elif ball_x_ratio > 0.33:
        if ball_y_ratio < 0.5:  # Ball on right midfield
            # TRACK WINGER - stay goal-side of threat
            target_col = max(14, int(ball_cell_x) - 2)
            target_row = max(1, int(ball_cell_y) - 1)
        else:  # Ball on left/central midfield
            # MAINTAIN DEFENSIVE SHAPE
            target_col = base_col - 2
            target_row = base_row + 1
            
    # BALL IN THEIR HALF (LOW DANGER)
    else:
        if ball_x_ratio < 0.2:  # Very advanced opponent possession
            # PUSH UP - high defensive line
            target_col = max(10, base_col - 8)
            target_row = base_row
        else:
            # BALANCED POSITION - ready for transitions
            target_col = base_col - 4
            target_row = base_row
    
    # Ensure defensive discipline
    target_col = max(10, min(22, target_col))   # Conservative positioning
    target_row = max(1, min(8, target_row))     # Stay on right flank
    
    return Vector2(
        (target_col + 0.5) * cell_w,
        (target_row + 0.5) * cell_h
    )