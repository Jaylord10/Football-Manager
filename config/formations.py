from .constants import GRID_COLS, GRID_ROWS, HEIGHT
from core.utils import cell_center
from core.database import PlayerDatabase
from pygame.math import Vector2

# Initialize database
db = PlayerDatabase()

def formation_4_4_2_positions(team):
    """
    Returns a list of (Role, GridCol, GridRow).

    Team 0 (Blue) defends the left goal.  Team 1 (Red) gets the exact mirror
    image (pitch rotated 180 degrees), so neither side starts with an
    advantage.  Rows are centred on the pitch's halfway line (row 7.5).
    """
    mid_row = GRID_ROWS // 2          # 8; the pitch centre is row 7.5
    home = [
        ("GK", 0, mid_row - 0.5),
        ("RB", 3, GRID_ROWS - 3), ("LCB", 5, mid_row - 2.5),
        ("RCB", 5, mid_row + 1.5), ("LB", 3, 2),
        ("LM", 7, 2), ("LCM", 9, mid_row - 2.5),
        ("RCM", 9, mid_row + 1.5), ("RM", 7, GRID_ROWS - 3),
        # (the strikers used to start on col 13 - 7 m inside the OPPONENTS' half)
        ("ST1", 10.5, mid_row - 1.5), ("ST2", 10.5, mid_row + 0.5),
    ]
    if team == 0:
        return home
    return [(role, GRID_COLS - 1 - col, GRID_ROWS - 1 - row) for role, col, row in home]

def formation_slots(team):
    """The team's spots (config/slots.py) - None for the 4-4-2."""
    return db.formation.get(team) if hasattr(db, "formation") else None


def formation_positions(team):
    """[(slot, col, row)] at kick-off: the 4-4-2 table, or the team's formation on the grid."""
    slots_ = formation_slots(team)
    if not slots_:
        return formation_4_4_2_positions(team)
    from config import slots
    home = slots.kickoff_cells(slots_)
    if team == 0:
        return home
    return [(s, GRID_COLS - 1 - col, GRID_ROWS - 1 - row) for s, col, row in home]


def spawn_team(team_id):
    from core.game_objects import Player
    from config import slots

    formation = formation_positions(team_id)
    players = []
    
    for index, (role, col, row) in enumerate(formation):
        slot = role
        role = slots.proxy(slot)
        position = cell_center(col, row)
        
        # --- FIX: FORCE GK TO CENTER ---
        # Grid rows are discrete (7.5 or 8.5), but we want exact center (8.0)
        if role == "GK":
            position.y = HEIGHT / 2
        
        # Get Attributes
        attributes = db.get_player_stats(team_id, slot)
        
        new_player = Player(team=team_id, role=role, pos=position, idx=index, attributes=attributes)
        new_player.slot = slot
        
        if attributes and "Name" in attributes:
            new_player.name = attributes["Name"]
        else:
            new_player.name = slot
        # Career id (None in friendlies) - for minutes, cards and the sub log
        new_player.pid = db.lineup_ids.get(team_id, {}).get(slot)
        # Fitness: he starts the match at his condition (career/training.py)
        if slot in db.lineup_condition.get(team_id, {}):
            new_player.stamina = float(db.lineup_condition[team_id][slot])

        players.append(new_player)

    # Give everyone their role from the library (match_config.json "roles")
    from roles.library import apply_role_set
    apply_role_set(players, db.team_roles.get(team_id))
    return players