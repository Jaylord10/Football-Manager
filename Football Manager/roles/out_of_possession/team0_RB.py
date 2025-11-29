# roles/out_of_possession/team0_RB.py
import pygame
from pygame.math import Vector2
import random

def out_of_possession(ball_cell_x, ball_cell_y, team, cell_size, current_pos):
    """
    Defensive decision tree for Right Back
    """
    cell_w, cell_h = cell_size
    
    # Base defensive position
    base_col = 3
    base_row = 13
    
    # Convert ball position to meaningful zones
    ball_x_ratio = ball_cell_x / 24
    ball_y_ratio = ball_cell_y / 16
    
    # --- DECISION TREE: DEFENSIVE PHASE ---
    
    # BALL IN OUR DEFENSIVE THIRD (HIGH DANGER)
    if ball_x_ratio < 0.33:
        if ball_y_ratio > 0.6:  # Ball on our left side (HIGH THREAT)
            # DIRECT DEFENSIVE ACTION - press immediately
            target_col = min(8, int(ball_cell_x) + 2)
            target_row = int(ball_cell_y)
        elif ball_y_ratio > 0.4:  # Ball in central defensive area
            # TUCK IN NARROW - help central defense
            target_col = base_col + 1
            target_row = 10  # More central position
        else:
            # Ball on opposite flank - cover far post
            target_col = base_col
            target_row = 8
            
    # BALL IN MIDFIELD (MEDIUM DANGER)
    elif ball_x_ratio < 0.66:
        if ball_y_ratio > 0.5:  # Ball on our left flank
            # TRACK POTENTIAL THREATS - stay goal-side
            target_col = min(12, int(ball_cell_x) + 1)
            target_row = max(10, int(ball_cell_y) - 1)
        else:
            # MAINTAIN DEFENSIVE SHAPE - balanced position
            target_col = base_col + 2
            target_row = base_row - 1
            
    # BALL IN THEIR HALF (LOW DANGER)
    else:
        # PUSH UP - support midfield, ready for transition
        target_col = min(15, base_col + 8)
        target_row = base_row - 2
    
    # Ensure we stay in reasonable defensive positions
    target_col = max(1, min(18, target_col))  # Don't push too high defensively
    target_row = max(5, min(14, target_row))  # Stay in defensive half
    
    return Vector2(
        (target_col + 0.5) * cell_w,
        (target_row + 0.5) * cell_h
    )