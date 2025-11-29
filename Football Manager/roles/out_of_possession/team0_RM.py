# roles/out_of_possession/team0_RM.py
from pygame.math import Vector2

# Defensive positioning for Team 0 Right Midfielder (attacking left→right)
# Grid size: 24 cols × 16 rows

# Defensive column based on ball column
BALL_COL_TO_DEF_COL = {
    20: 18, 19: 17, 18: 16, 17: 15, 16: 14, 15: 13, 14: 12, 13: 11, 12: 10, 11: 9,
    10: 8,  9: 7,   8: 6,    7: 5,   6: 4,   5: 3,   4: 3,   3: 2,   2: 2,   1: 2,   0: 1.5
}

# Defensive row based on ball row
BALL_ROW_TO_DEF_ROW = {
    15: 13, 14: 13, 13: 13, 12: 12, 11: 12, 10: 11.5, 9: 11, 8: 10,
    7: 10, 6: 10, 5: 10, 4: 10, 3: 10, 2: 10, 1: 10, 0: 10
}

def lerp(v1, v2, t):
    return v1 + (v2 - v1) * max(0, min(t, 1))

def out_of_possession(ball_col, ball_row, team, cell_size, current_pos):
    """Return target position for RM when defending."""
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
        lerp(current_pos.x, target.x, 0.08),  # Slightly faster for midfielders
        lerp(current_pos.y, target.y, 0.08)
    )
    return new_pos