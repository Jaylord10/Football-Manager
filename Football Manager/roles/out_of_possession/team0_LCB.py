# roles/out_of_possession/team0_LCB.py
import pygame
from pygame.math import Vector2
import random

def out_of_possession(ball_cell_x, ball_cell_y, team, cell_size, current_pos):
    """
    Defensive decision tree for Left Center Back
    """
    cell_w, cell_h = cell_size
    
    # Base defensive position
    base_col = 5
    base_row = 6
    
    # Convert ball position to meaningful zones
    ball_x_ratio = ball_cell_x / 24
    ball_y_ratio = ball_cell_y / 16
    
    # --- DECISION TREE: DEFENSIVE PHASE ---
    
    # BALL IN OUR DEFENSIVE THIRD (HIGH DANGER)
    if ball_x_ratio < 0.33:
        if ball_y_ratio < 0.4:  # Ball in left channel (OUR ZONE)
            # DIRECT ENGAGEMENT - close down threat
            target_col = min(8, int(ball_cell_x) + 1)
            target_row = int(ball_cell_y)
        elif ball_y_ratio < 0.6:  # Ball central in our third
            # MARK CENTRAL THREAT - engage striker
            target_col = base_col + 1
            target_row = base_row
        else:  # Ball on right side
            # COVER SPACE - protect far post
            target_col = base_col - 1
            target_row = base_row + 1
            
    # BALL IN MIDFIELD (MEDIUM DANGER)
    elif ball_x_ratio < 0.66:
        if ball_y_ratio < 0.4:  # Ball in left midfield
            # SHIFT AND COMPRESS - limit central options
            target_col = min(10, base_col + 2)
            target_row = base_row
        elif ball_y_ratio > 0.6:  # Ball in right midfield
            # BALANCE DEFENSE - cover central space
            target_col = base_col
            target_row = base_row
        else:  # Ball central midfield
            # READY TO ENGAGE - step to intercept
            target_col = base_col + 1
            target_row = base_row
            
    # BALL IN THEIR HALF (LOW DANGER)
    else:
        if ball_x_ratio > 0.8:  # High press situation
            # PUSH UP - aggressive defensive line
            target_col = min(12, base_col + 4)
            target_row = base_row
        else:
            # BALANCED POSITION - ready for transitions
            target_col = base_col + 2
            target_row = base_row
    
    # Ensure defensive discipline
    target_col = max(3, min(14, target_col))  # Conservative positioning
    target_row = max(4, min(10, target_row))  # Stay central
    
    return Vector2(
        (target_col + 0.5) * cell_w,
        (target_row + 0.5) * cell_h
    )