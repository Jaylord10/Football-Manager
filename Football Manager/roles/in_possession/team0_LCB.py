# roles/in_possession/team0_LCB.py
import pygame
from pygame.math import Vector2
import random

def in_possession(ball_cell_x, ball_cell_y, team, cell_size):
    """
    Build-up decision tree for Left Center Back
    """
    cell_w, cell_h = cell_size
    
    # Base formation position (LCB: col=5, row=6 in 24x16 grid)
    base_col = 5
    base_row = 6
    
    # Convert ball position to meaningful zones
    ball_x_ratio = ball_cell_x / 24
    ball_y_ratio = ball_cell_y / 16
    
    # --- DECISION TREE: BUILD-UP PHASE ---
    
    # BALL IN DEFENSIVE THIRD (build-up phase)
    if ball_x_ratio < 0.33:
        if ball_x_ratio < 0.15:  # Ball very deep (with GK)
            # SPLIT WIDE - create passing lane
            target_col = base_col
            target_row = base_row - 1  # Slightly wider
        elif ball_y_ratio < 0.4:  # Ball on left side
            # PROVIDE SUPPORT - angle for pass
            target_col = base_col + 1
            target_row = base_row
        elif ball_y_ratio > 0.6:  # Ball on right side
            # COVER POSITION - balance defense
            target_col = base_col - 1
            target_row = base_row
        else:  # Ball central
            # BUILD-UP READY - standard position
            target_col = base_col
            target_row = base_row
            
    # BALL IN MIDFIELD
    elif ball_x_ratio < 0.66:
        if ball_y_ratio < 0.5:  # Ball on left side
            # STEP UP - support midfield, ready to progress
            target_col = min(10, base_col + 3)
            target_row = base_row
        else:
            # BALANCE POSITION - cover counter-attacks
            target_col = base_col + 1
            target_row = base_row
            
    # BALL IN ATTACKING THIRD
    else:
        if ball_x_ratio > 0.8 and ball_y_ratio < 0.4:  # Sustained left-side pressure
            # PUSH UP - support offside trap
            target_col = min(12, base_col + 5)
            target_row = base_row
        else:
            # DEFENSIVE COVER - protect against counters
            target_col = base_col + 2
            target_row = base_row
    
    # Ensure we stay in reasonable positions
    target_col = max(3, min(16, target_col))  # Don't push too high
    target_row = max(4, min(10, target_row))  # Stay in central channels
    
    return Vector2(
        (target_col + 0.5) * cell_w,
        (target_row + 0.5) * cell_h
    )