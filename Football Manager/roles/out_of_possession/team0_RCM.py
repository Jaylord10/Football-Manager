# roles/out_of_possession/team0_RCM.py
from pygame.math import Vector2

# Defensive positioning for Team 0 Right Centre Midfielder (attacking left→right)
# Grid size: 24 cols × 16 rows

# Defensive column based on ball column
BALL_COL_TO_DEF_COL = {
    20: 15.5, 19: 15, 18: 14, 17: 13.5, 16: 13.5, 15: 13, 14: 12, 13: 11, 12: 10, 11: 9,
    10: 8,  9: 7,   8: 6,    7: 5,   6: 4,   5: 3,   4: 3,   3: 2,   2: 2,   1: 2,   0: 1.5
}

# Defensive row based on ball row
BALL_ROW_TO_DEF_ROW = {
    15: 10, 14: 10, 13: 10, 12: 10, 11: 10, 10: 10, 9: 9, 8: 8.5,
    7: 8, 6: 8, 5: 7.5, 4: 7, 3: 6, 2: 5, 1: 5, 0: 5
}

def lerp(v1, v2, t):
    return v1 + (v2 - v1) * max(0, min(t, 1))

def out_of_possession(ball_col, ball_row, team, cell_size, current_pos):
    """Return target position for RCM when defending."""
    # Handle column positioning
    ball_col_key = min(max(int(ball_col), 0), 20)
    
    if ball_col_key in BALL_COL_TO_DEF_COL:
        target_col = BALL_COL_TO_DEF_COL[ball_col_key]
    else:
        # Fallback to nearest defined column
        defined_cols = sorted(BALL_COL_TO_DEF_COL.keys())
        nearest_col = min(defined_cols, key=lambda x: abs(x - ball_col_key))
        target_col = BALL_COL_TO_DEF_COL[nearest_col]
    
    # Handle row positioning
    ball_row_key = min(max(int(ball_row), 0), 15)
    
    if ball_row_key in BALL_ROW_TO_DEF_ROW:
        target_row = BALL_ROW_TO_DEF_ROW[ball_row_key]
    else:
        # Fallback to nearest defined row
        defined_rows = sorted(BALL_ROW_TO_DEF_ROW.keys())
        nearest_row = min(defined_rows, key=lambda x: abs(x - ball_row_key))
        target_row = BALL_ROW_TO_DEF_ROW[nearest_row]

    target_x = (target_col + 0.5) * cell_size[0]
    target_y = (target_row + 0.5) * cell_size[1]
    target = Vector2(target_x, target_y)

    # Smooth movement toward target
    new_pos = Vector2(
        lerp(current_pos.x, target.x, 0.07),  # Moderate speed for central midfielders
        lerp(current_pos.y, target.y, 0.07)
    )
    return new_pos