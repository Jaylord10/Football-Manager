"""
config/slots.py
===============
The positions a player can be put in - a grid like Football Manager's - and
the ready-made formations.

THE GRID (in each team's own frame: rows from our goal up, lanes from our
left to our right):

  row 4  strikers            ST1 . ST . ST2                (lanes -1, 0, 1)
  row 3  attacking midfield  LW  LAM  AM  RAM  RW
  row 2  midfield            LM  LCM  CM  RCM  RM
  row 1  defensive mid / WB  LWB LDM  DM  RDM  RWB
  row 0  defence             LB  LCB  CB  RCB  RB
                                    GK

A formation is a goalkeeper + any 10 of these, one player per spot.
(The 4-4-2 names - LB, LCB, RCB, RB, LM, LCM, RCM, RM, ST1, ST2 - are the
ones the engine was built with; they're spots on the grid like any other.)

THE ENGINE: each spot has a BEHAVIOUR KIND it borrows its decisions from
(proxy - how keen he is to dribble, whether he presses, where he makes runs...),
and its own place in the team's shape (ai/team_shape.py) from its row and
lane.  A 4-4-2 plays exactly as it always has.
"""

# spot: (row, lane)
GRID = {
    "LB": (0, -2), "LCB": (0, -1), "CB": (0, 0), "RCB": (0, 1), "RB": (0, 2),
    "LWB": (1, -2), "LDM": (1, -1), "DM": (1, 0), "RDM": (1, 1), "RWB": (1, 2),
    "LM": (2, -2), "LCM": (2, -1), "CM": (2, 0), "RCM": (2, 1), "RM": (2, 2),
    "LW": (3, -2), "LAM": (3, -1), "AM": (3, 0), "RAM": (3, 1), "RW": (3, 2),
    "ST1": (4, -1), "ST": (4, 0), "ST2": (4, 1),
}
ROWS = {0: "Defence", 1: "Defensive midfield", 2: "Midfield", 3: "Attacking midfield", 4: "Attack"}

LEGACY_442 = ("GK", "LB", "LCB", "RCB", "RB", "LM", "LCM", "RCM", "RM", "ST1", "ST2")

# The engine's behaviour kind for each spot (the 4-4-2 names it was built with)
PROXY = {
    "GK": "GK",
    "LB": "LB", "LCB": "LCB", "CB": "LCB", "RCB": "RCB", "RB": "RB",
    "LWB": "LB", "LDM": "LCM", "DM": "LCM", "RDM": "RCM", "RWB": "RB",
    "LM": "LM", "LCM": "LCM", "CM": "LCM", "RCM": "RCM", "RM": "RM",
    "LW": "LM", "LAM": "LCM", "AM": "LCM", "RAM": "RCM", "RW": "RM",
    "ST1": "ST1", "ST": "ST1", "ST2": "ST2",
}

# What each spot does (for the screens and the role lists)
KIND = {
    "LB": "FB", "RB": "FB", "LCB": "CB", "CB": "CB", "RCB": "CB",
    "LWB": "WB", "RWB": "WB", "LDM": "DM", "DM": "DM", "RDM": "DM",
    "LM": "WM", "RM": "WM", "LCM": "CM", "CM": "CM", "RCM": "CM",
    "LW": "W", "RW": "W", "LAM": "AM", "AM": "AM", "RAM": "AM",
    "ST1": "ST", "ST": "ST", "ST2": "ST", "GK": "GK",
}
LABEL = {"LB": "LB", "RB": "RB", "LCB": "CB", "CB": "CB", "RCB": "CB", "LWB": "LWB", "RWB": "RWB",
         "LDM": "DM", "DM": "DM", "RDM": "DM", "LM": "LM", "RM": "RM", "LCM": "CM", "CM": "CM", "RCM": "CM",
         "LW": "LW", "RW": "RW", "LAM": "AM", "AM": "AM", "RAM": "AM", "ST1": "ST", "ST": "ST", "ST2": "ST",
         "GK": "GK"}

# A spot's role when nobody has chosen one (roles/library.py); 4-4-2 spots keep the team's set
DEFAULT_ROLE = {
    "CB": "LCB_red", "LWB": "LB_blue", "RWB": "RB_blue",
    "LDM": "LCM_blue", "DM": "RCM_blue", "RDM": "RCM_blue", "CM": "RCM_red",     # (a double pivot: one goes, one sits)
    "LW": "LM_blue", "RW": "RM_red", "LAM": "LCM_blue", "AM": "LCM_blue", "RAM": "LCM_blue",
    "ST": "ST1_blue",
}

FORMATIONS = {
    "4-4-2":   ["LB", "LCB", "RCB", "RB", "LM", "LCM", "RCM", "RM", "ST1", "ST2"],
    "4-2-3-1": ["LB", "LCB", "RCB", "RB", "LDM", "RDM", "LW", "AM", "RW", "ST"],
    "4-3-3":   ["LB", "LCB", "RCB", "RB", "DM", "LCM", "RCM", "LW", "RW", "ST"],
    "3-4-2-1": ["LCB", "CB", "RCB", "LWB", "RWB", "LCM", "RCM", "LAM", "RAM", "ST"],
    "4-1-4-1": ["LB", "LCB", "RCB", "RB", "DM", "LM", "LCM", "RCM", "RM", "ST"],
    "5-3-2":   ["LWB", "LCB", "CB", "RCB", "RWB", "LCM", "CM", "RCM", "ST1", "ST2"],
    "4-3-1-2": ["LB", "LCB", "RCB", "RB", "DM", "LCM", "RCM", "AM", "ST1", "ST2"],
    "3-5-2":   ["LCB", "CB", "RCB", "LWB", "RWB", "DM", "LCM", "RCM", "ST1", "ST2"],
    "5-4-1":   ["LWB", "LCB", "CB", "RCB", "RWB", "LM", "LCM", "RCM", "RM", "ST"],
    "2-3-5":   ["LCB", "RCB", "LWB", "DM", "RWB", "LW", "AM", "RW", "ST1", "ST2"],     # all out: chasing a game
}


def proxy(slot):
    return PROXY.get(slot, slot)


def row(slot):
    return GRID.get(slot, (-1, 0))[0]


def lane(slot):
    return GRID.get(slot, (-1, 0))[1]


def side(slot):
    """-1 our left, 0 the middle, 1 our right."""
    ln = lane(slot)
    return -1 if ln < 0 else 1 if ln > 0 else 0


def kind(slot):
    return KIND.get(slot, "CM")


def is_legacy(slots):
    """Is this the 4-4-2 the engine was built with?"""
    return set(s for s in slots if s != "GK") == set(LEGACY_442[1:])


def check(slots):
    """Problems with a formation (outfield spots), or []."""
    out = []
    field = [s for s in slots if s != "GK"]
    if len(field) != 10:
        out.append(f"{len(field)} outfield players - a team has 10")
    if len(set(field)) != len(field):
        out.append("two players in the same spot")
    bad = [s for s in field if s not in GRID]
    if bad:
        out.append("unknown spots: " + ", ".join(bad))
    if not any(row(s) == 0 for s in field):
        out.append("nobody in defence")
    return out


# ---------------------------------------------------------------------------
# Where they line up at kick-off (the 24 x 16 cell grid of config/constants.py)
# ---------------------------------------------------------------------------
_LANE_ROW = {-2: 2.0, -1: 5.5, 0: 7.5, 1: 9.5, 2: 13.0}       # (rows across: as the 4-4-2 always was)
_ST_ROW = {-1: 6.5, 0: 7.5, 1: 8.5}
_COL = {(0, True): 3.0, (0, False): 5.0, (1, True): 4.5, (1, False): 7.0, (2, True): 7.0, (2, False): 9.0,
        (3, True): 9.5, (3, False): 10.0, (4, True): 10.5, (4, False): 10.5}    # (row, wide) -> column


def kickoff_cells(slots):
    """[(slot, col, row)] for team 0 - the 4-4-2 numbers exactly as before."""
    out = [("GK", 0, 7.5)]
    for s in slots:
        if s == "GK":
            continue
        r, ln = GRID[s]
        col = _COL[(r, abs(ln) == 2)]
        cell_row = _ST_ROW[ln] if r == 4 else _LANE_ROW[ln]
        out.append((s, col, cell_row))
    return out
