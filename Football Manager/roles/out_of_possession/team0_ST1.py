# roles/out_of_possession/team0_ST1.py
import pygame
from pygame.math import Vector2
import random

def out_of_possession(ball_cell_x, ball_cell_y, team, cell_size, current_pos):
    """
    Aggressive pressing of opposition back line for Striker 1
    """
    cell_w, cell_h = cell_size
    
    ball_x_ratio = ball_cell_x / 24
    ball_y_ratio = ball_cell_y / 16
    
    # --- AGGRESSIVE BACK LINE PRESSING ---
    
    # BALL IN THEIR DEFENSIVE THIRD - HARASS CONSTANTLY
    if ball_x_ratio > 0.66:  # Ball in their defensive third
        # DIRECT PRESSURE ON BALL-CARRYING DEFENDER
        target_col = max(16, int(ball_cell_x) - 1)  # Get close to defender
        target_row = int(ball_cell_y)
        
        # Add some intelligence - don't just chase mindlessly
        if ball_x_ratio > 0.9:  # Ball with GK or very deep
            # CUT PASSING LANES while pressuring
            if ball_y_ratio < 0.5:
                target_col = 20  # Pressure left side
                target_row = 6   # Block central passes
            else:
                target_col = 20  # Pressure right side  
                target_row = 8   # Block central passes
                
    # BALL IN MIDFIELD - READ INTERCEPTS AND BLOCK BACK PASSES
    elif ball_x_ratio > 0.33:
        # POSITION TO CUT PASSES BACK TO DEFENSE
        target_col = 16  # High block position
        target_row = 7   # Central to see both sides
        
        # If ball is on one side, shift to block that passing lane
        if ball_y_ratio < 0.4:  # Ball on their left
            target_row = 6  # Shift to block left CB pass
        elif ball_y_ratio > 0.6:  # Ball on their right
            target_row = 8  # Shift to block right CB pass
            
    # BALL IN OUR HALF - CONSERVE BUT READ COUNTER
    else:
        # STAY HIGH FOR COUNTER-ATTACK THREAT
        target_col = 15  # Just inside their half
        target_row = 7   # Central for quick breaks
    
    # Ensure we're always in pressing positions - never too deep
    target_col = max(14, min(22, target_col))   # Stay in their half
    target_row = max(4, min(11, target_row))    # Central pressing areas
    
    return Vector2(
        (target_col + 0.5) * cell_w,
        (target_row + 0.5) * cell_h
    )