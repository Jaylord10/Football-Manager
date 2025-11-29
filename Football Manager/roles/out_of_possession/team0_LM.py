# roles/out_of_possession/team0_LM.py
import pygame
from pygame.math import Vector2
import random

def out_of_possession(ball_cell_x, ball_cell_y, team, cell_size, current_pos):
    """
    Defensive decision tree for Left Midfielder (team0 - HIGH PRESSING)
    """
    cell_w, cell_h = cell_size
    
    # Base defensive position - MUCH HIGHER
    base_col = 7
    base_row = 2
    
    # Convert ball position to meaningful zones
    ball_x_ratio = ball_cell_x / 24
    ball_y_ratio = ball_cell_y / 16
    
    # --- DECISION TREE: DEFENSIVE PHASE - HIGH BLOCK ---
    
    # BALL IN OUR DEFENSIVE THIRD (HIGH DANGER)
    if ball_x_ratio < 0.33:
        if ball_y_ratio < 0.4:  # Ball on left side (OUR ZONE)
            # HIGH BLOCK POSITION - don't drop too deep
            target_col = max(8, base_col + 1)  # Much higher than before
            target_row = base_row
        elif ball_y_ratio < 0.6:  # Ball central
            # CENTRAL HIGH BLOCK - ready for counter
            target_col = max(10, base_col + 3)
            target_row = 4
        else:  # Ball on right side
            # BALANCE HIGH BLOCK - maintain shape
            target_col = max(9, base_col + 2)
            target_row = base_row + 1
            
    # BALL IN MIDFIELD (MEDIUM DANGER)
    elif ball_x_ratio < 0.66:
        if ball_y_ratio < 0.4:  # Ball on left midfield
            # AGGRESSIVE HIGH PRESS - win ball back immediately
            target_col = min(14, int(ball_cell_x) + 3)  # Much more aggressive
            target_row = max(1, int(ball_cell_y))
        elif ball_y_ratio < 0.6:  # Ball central midfield
            # CUT PASSING LANES FROM HIGH POSITION
            target_col = min(12, base_col + 5)  # Higher central position
            target_row = 4
        else:  # Ball on right midfield
            # HIGH DEFENSIVE SHAPE - ready to counter
            target_col = min(11, base_col + 4)  # Stay advanced
            target_row = base_row
            
    # BALL IN THEIR HALF (LOW DANGER)
    else:
        if ball_x_ratio < 0.2:  # Very advanced opponent possession
            # ULTRA HIGH PRESS - force errors in their final third
            target_col = max(12, int(ball_cell_x) - 1)  # Really close pressure
            target_row = int(ball_cell_y)
        else:
            # COUNTER-ATTACK POSITION - stay very high for transitions
            target_col = min(16, base_col + 8)  # Extremely advanced
            target_row = base_row
    
    # Ensure HIGH defensive line - LM should rarely drop deep
    target_col = max(6, min(18, target_col))   # Stay in advanced areas
    target_row = max(1, min(6, target_row))    # Left flank but higher
    
    return Vector2(
        (target_col + 0.5) * cell_w,
        (target_row + 0.5) * cell_h
    )