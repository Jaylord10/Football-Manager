# roles/in_possession/team1_RB.py
import pygame
from pygame.math import Vector2
import random

def in_possession(ball_cell_x, ball_cell_y, team, cell_size):
    """
    Attacking decision tree for Right Back (team1 - attacking left)
    """
    cell_w, cell_h = cell_size
    
    # Base formation position (RB: col=GRID_COLS-4, row=2 in 24x16 grid)
    base_col = 20  # GRID_COLS-4 = 24-4 = 20
    base_row = 2
    
    # Convert ball position to meaningful zones
    ball_x_ratio = ball_cell_x / 24
    ball_y_ratio = ball_cell_y / 16
    
    # --- DECISION TREE: ATTACKING PHASE ---
    
    # BALL IN DEFENSIVE THIRD (build-up)
    if ball_x_ratio > 0.66:  # Ball in our defensive third (team1 perspective)
        if ball_y_ratio < 0.4:  # Ball on right side (our RB's side)
            # PROVIDE WIDTH - support build-up on right
            target_col = max(16, base_col - 2)  # Slightly more advanced
            target_row = base_row
        else:  # Ball on left side
            # STAY WIDE - ready for switch
            target_col = base_col
            target_row = base_row
            
    # BALL IN MIDFIELD
    elif ball_x_ratio > 0.33:
        # Overlap opportunities - team1 attacks left, so RB provides width on right
        if ball_y_ratio > 0.6:  # Ball on left side near LM
            # HOLD POSITION - maintain width for switch
            target_col = max(14, base_col - 4)
            target_row = base_row
        elif ball_y_ratio < 0.4:  # Ball on right side near RM
            # OVERLAP OPPORTUNITY - support RM
            target_col = max(12, int(ball_cell_x) - 4)
            target_row = max(1, int(ball_cell_y) - 1)
        else:  # Ball central
            # BALANCED POSITION - support midfield
            target_col = max(16, base_col - 2)
            target_row = base_row
            
    # BALL IN ATTACKING THIRD
    else:
        # Attacking contribution - team1 attacking left
        if ball_y_ratio < 0.4:  # Ball on right side in attack
            # SUPPORT RUN - get forward for crosses/cutbacks
            target_col = max(8, int(ball_cell_x) - 6)
            target_row = max(1, int(ball_cell_y) - 1)
        elif ball_y_ratio > 0.6:  # Ball on left side
            # DEFENSIVE COVER - tuck in for balance
            target_col = max(14, base_col - 4)
            target_row = 4  # More central
        else:
            # EDGE OF ATTACK - support from deep
            target_col = max(12, base_col - 6)
            target_row = base_row
    
    # Ensure we stay in reasonable positions
    target_col = max(8, min(22, target_col))   # Don't push too high as fullback
    target_row = max(1, min(6, target_row))    # Stay on right flank
    
    return Vector2(
        (target_col + 0.5) * cell_w,
        (target_row + 0.5) * cell_h
    )