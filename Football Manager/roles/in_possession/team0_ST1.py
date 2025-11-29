# roles/in_possession/team0_ST1.py
import pygame
from pygame.math import Vector2
import random

def in_possession(ball_cell_x, ball_cell_y, team, cell_size):
    """
    Dynamic line-breaking movement for Striker 1
    """
    cell_w, cell_h = cell_size
    
    # Base position - but we'll be very dynamic
    base_col = 13
    base_row = 7
    
    ball_x_ratio = ball_cell_x / 24
    ball_y_ratio = ball_cell_y / 16
    
    # --- AGGRESSIVE LINE-BREAKING MOVEMENT ---
    
    # BALL IN DEFENSIVE THIRD - make runs in behind immediately
    if ball_x_ratio < 0.33:
        # ATTEMPT EARLY THROUGH BALL RUNS - stretch defense
        if random.random() < 0.7:  # 70% chance to make aggressive run
            # RUN IN BEHIND - different channels
            run_type = random.choice(['left_channel', 'right_channel', 'central'])
            if run_type == 'left_channel':
                target_col = min(20, base_col + 7)
                target_row = max(4, base_row - 3)
            elif run_type == 'right_channel':
                target_col = min(20, base_col + 7)
                target_row = min(11, base_row + 3)
            else:  # central
                target_col = min(20, base_col + 7)
                target_row = base_row
        else:
            # SHOW FOR FEET - but still advanced
            target_col = min(16, base_col + 3)
            target_row = base_row + random.randint(-1, 1)
            
    # BALL IN MIDFIELD - constant movement to break lines
    elif ball_x_ratio < 0.66:
        # ALWAYS TRYING TO BREAK OFFSIDE TRAP
        if random.random() < 0.8:  # 80% chance of aggressive movement
            # TIMED RUNS BEHIND DEFENSE
            target_col = min(22, base_col + random.randint(4, 8))
            # Vary the channel - don't run straight lines
            channel_variation = random.randint(-3, 3)
            target_row = base_row + channel_variation
        else:
            # CHECK TO SHOULDER - create angle for through ball
            target_col = min(18, base_col + 5)
            target_row = base_row + random.randint(-2, 2)
            
    # BALL IN ATTACKING THIRD - pure penetration
    else:
        # GET INTO GOALSCORING POSITIONS
        if ball_y_ratio < 0.4:  # Ball wide left
            # FAR POST RUN for cross
            target_col = 20  # Near goal
            target_row = 9   # Far post area
        elif ball_y_ratio > 0.6:  # Ball wide right
            # NEAR POST RUN for cross
            target_col = 20  # Near goal
            target_row = 5   # Near post area
        else:  # Ball central
            # PENETRATE CENTRAL AREAS - between CBs
            target_col = 21  # Very advanced
            target_row = 7   # Central goal threat
    
    # Ensure aggressive positioning - always looking to break lines
    target_col = max(10, min(22, target_col))   # Stay in advanced areas
    target_row = max(3, min(12, target_row))    # Use full width of penalty area
    
    return Vector2(
        (target_col + 0.5) * cell_w,
        (target_row + 0.5) * cell_h
    )