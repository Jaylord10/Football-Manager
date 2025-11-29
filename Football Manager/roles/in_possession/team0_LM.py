# roles/in_possession/team0_LM.py
import pygame
from pygame.math import Vector2
import random

def in_possession(ball_cell_x, ball_cell_y, team, cell_size):
    """
    Attacking decision tree for Left Midfielder (team0 - attacking right)
    """
    cell_w, cell_h = cell_size
    
    # Base formation position (LM: col=7, row=2 in 24x16 grid)
    base_col = 7
    base_row = 2
    
    # Convert ball position to meaningful zones
    ball_x_ratio = ball_cell_x / 24
    ball_y_ratio = ball_cell_y / 16
    
    # --- DECISION TREE: ATTACKING PHASE ---
    
    # BALL IN DEFENSIVE THIRD (build-up)
    if ball_x_ratio < 0.33:
        if ball_y_ratio < 0.4:  # Ball on left side (OUR SIDE)
            # DROP DEEP - provide passing option, create triangles
            target_col = max(4, base_col - 3)
            target_row = base_row + random.randint(-1, 1)
        elif ball_y_ratio > 0.6:  # Ball on right side
            # STAY ADVANCED - ready for switch of play
            target_col = min(12, base_col + 5)
            target_row = base_row
        else:  # Ball central
            # SUPPORT CENTRALLY - between lines
            target_col = base_col
            target_row = base_row
            
    # BALL IN MIDFIELD
    elif ball_x_ratio < 0.66:
        # Multiple attacking options based on situation
        if ball_y_ratio < 0.4:  # Ball on left side
            # DRIVE FORWARD - progressive run, look for 1-2s
            target_col = min(16, base_col + 6)
            target_row = max(1, base_row - 1)
        elif ball_y_ratio < 0.6:  # Ball central
            # CUT INSIDE - create central overload
            target_col = min(14, base_col + 5)
            target_row = 5  # More central position
        else:  # Ball on right side
            # HOLD WIDTH - stretch defense for switch
            target_col = base_col + 2
            target_row = base_row
            
    # BALL IN ATTACKING THIRD
    else:
        # Pure attacking intent
        if ball_y_ratio < 0.4:  # Ball on left side in attack
            # ATTACK BYLINE - get to crossing positions
            target_col = min(20, base_col + 10)
            target_row = max(1, base_row - 2)
        elif ball_y_ratio > 0.6:  # Ball on right side
            # ATTACK FAR POST - for crosses/cutbacks
            target_col = min(18, base_col + 8)
            target_row = 4  # Central goal threat
        else:  # Ball central attacking
            # EDGE OF BOX - shooting/combination position
            target_col = min(17, base_col + 7)
            target_row = 3
    
    # Ensure we stay in attacking positions
    target_col = max(3, min(22, target_col))   # Use full attacking range
    target_row = max(1, min(8, target_row))    # Stay on left flank but can drift
    
    return Vector2(
        (target_col + 0.5) * cell_w,
        (target_row + 0.5) * cell_h
    )