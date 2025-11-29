from .constants import GRID_COLS, GRID_ROWS
from core.utils import cell_center

def formation_4_4_2_positions(team):
    mid_row = GRID_ROWS // 2
    
    if team == 0:  # Blue team (left to right)
        return [
            ("GK", 1, mid_row),
            ("RB", 3, GRID_ROWS - 3),
            ("LCB", 5, mid_row - 2),
            ("RCB", 5, mid_row + 2),
            ("LB", 3, 2),
            ("LM", 7, 2),
            ("LCM", 9, mid_row - 2),
            ("RCM", 9, mid_row + 2),
            ("RM", 7, GRID_ROWS - 3),
            ("ST1", 13, mid_row - 1),
            ("ST2", 13, mid_row + 1),
        ]
    else:  # Red team (right to left)
        return [
            ("GK", GRID_COLS - 2, mid_row),
            ("RB", GRID_COLS - 4, 2),
            ("RCB", GRID_COLS - 6, mid_row - 2),
            ("LCB", GRID_COLS - 6, mid_row + 2),
            ("LB", GRID_COLS - 4, GRID_ROWS - 3),
            ("RM", GRID_COLS - 8, GRID_ROWS - 3),
            ("RCM", GRID_COLS - 10, mid_row + 2),
            ("LCM", GRID_COLS - 10, mid_row - 2),
            ("LM", GRID_COLS - 8, 2),
            ("ST1", GRID_COLS - 14, mid_row - 1),
            ("ST2", GRID_COLS - 14, mid_row + 1),
        ]

def spawn_team(team_id):
    from core.game_objects import Player
    
    formation = formation_4_4_2_positions(team_id)
    players = []
    
    for index, (role, col, row) in enumerate(formation):
        position = cell_center(col, row)
        players.append(Player(team=team_id, role=role, pos=position, idx=index))
    
    return players