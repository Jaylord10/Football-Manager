"""
career/clubs.py
===============
The clubs in the league and how their players are made.  (The 20-club
world itself is built once and kept in data/world - see career/world.py.)

Each club has a STRENGTH (its players' general level, on the 0-100 scale the
squad files use), and its players are built from it:
  - each player has his own level around the club's (some better, some
    worse), an age, and a hidden potential,
  - technical and mental attributes come from his level, what his position
    needs (a centre-back is good in the air and at marking, a winger crosses
    well, a keeper can stop shots...) and a bit of randomness,
  - physical attributes (pace, acceleration, agility, stamina, strength,
    jumping) come from real-world numbers for his position, his own build
    and his age - hardly at all from the club's level (see PHYS_MEAN).
Clubs also get a style: how they defend (ai/tactics.py), how they build up
(play out or clear it) and which role set they use (roles/library.py) -
the better sides tend to press and play out, the weaker ones sit deep and
clear their lines.

Squads are written as CSV files exactly like data/teams/*.csv, so the match
engine loads them the normal way.

All tuning numbers are in the TUNING block.
"""

import csv
import os
import random

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
# The 20 clubs' levels, best to worst (technical / mental quality, 0-100 -
# divided by 5 for the engine's 1-20).  Premier League-like: a top few, a
# big middle, a weak bottom.  (The first ten are the old 10-club league.)
STRENGTHS     = (77, 75, 73, 71, 69, 67, 66, 65, 64, 63, 62, 61, 60, 59, 58, 57, 56, 55, 54, 52)
STRENGTHS_10  = (74, 71, 68, 66, 64, 62, 60, 58, 56, 53)      # old 10-club saves
PLAYER_SPREAD = 5.0      # sd of a player's level around his club's
ATTR_SPREAD   = 7.0      # sd of each technical / mental attribute around what his level + position give
ATTR_MIN, ATTR_MAX = 15, 97
AGE_RANGE     = (18, 34)  # (old saves' reserves)

# --- Age ---------------------------------------------------------------------
# Premier League squads: average age ~26-27, a few teenagers, a few over 32.
AGE_WEIGHTS = {17: 0.5, 18: 1, 19: 2, 20: 4, 21: 5, 22: 6, 23: 7, 24: 8, 25: 8, 26: 8, 27: 8,
               28: 7, 29: 6, 30: 5, 31: 4, 32: 3, 33: 2, 34: 1, 35: 0.5}
# How far below his peak level a player is at each age (technical / mental):
# youngsters are still learning, players in their thirties start to lose it.
AGE_LEVEL = {16: -12, 17: -10, 18: -8, 19: -6, 20: -4.5, 21: -3, 22: -2, 23: -1, 24: 0, 25: 0, 26: 0,
             27: 0, 28: 0, 29: 0, 30: -0.5, 31: -1, 32: -2, 33: -3, 34: -4.5, 35: -6}

# --- Physical attributes ---------------------------------------------------------
# These are NOT tied to how good the club is: players in the lower divisions
# are as fit and as quick as Premier League players - the difference is
# technical (Bradley et al. 2013: Premier League, Championship and League One
# players had similar physical capacity; the Premier League players were
# 4-39% better on the ball).  They depend on position, the player himself,
# and age.
#
# Top Speed is calibrated to real sprint speeds.  The engine turns Top Speed
# 1-20 into 7.5-10.5 m/s (core/locomotion.py), i.e. 27-37.8 km/h.  Premier
# League 2025/26: the fastest players hit 36-37.3 km/h, the slowest regular
# outfielders 29.5-31 km/h; wide players and full-backs are the quickest,
# central midfielders the slowest (match-play study: WM 32.0, FB 30.7,
# CB 30.6, FW 29.9, CM 28.5 km/h, sd 1.4-2.0).  Season-best speeds by
# position used here (km/h, mean / sd):
#   WM 34.6, FB 34.2, ST 33.8, CB 33.3, CM 32.3, GK 30.0  -  sd 1.3
# which on the 0-100 squad scale (x5 of the engine's 1-20, which rounds down,
# so these are ~2.5 above speed x 5) is:
PHYS_MEAN = {    # position: {attribute: mean on 0-100}
    "WM": {"Top Speed": 74, "Acceleration": 72, "Agility": 70, "Stamina": 68, "Strength": 54, "Jumping": 52},
    "FB": {"Top Speed": 70, "Acceleration": 68, "Agility": 64, "Stamina": 72, "Strength": 60, "Jumping": 58},
    "ST": {"Top Speed": 68, "Acceleration": 67, "Agility": 64, "Stamina": 62, "Strength": 66, "Jumping": 64},
    "CB": {"Top Speed": 63, "Acceleration": 56, "Agility": 52, "Stamina": 62, "Strength": 72, "Jumping": 70},
    "CM": {"Top Speed": 55, "Acceleration": 58, "Agility": 62, "Stamina": 74, "Strength": 62, "Jumping": 58},
    "GK": {"Top Speed": 33, "Acceleration": 45, "Agility": 66, "Stamina": 45, "Strength": 64, "Jumping": 64},
    # (the modern positions - see NEW POSITIONS below)
    "DM": {"Top Speed": 55, "Acceleration": 57, "Agility": 60, "Stamina": 74, "Strength": 66, "Jumping": 62},
    "AM": {"Top Speed": 66, "Acceleration": 68, "Agility": 70, "Stamina": 68, "Strength": 56, "Jumping": 54},
    "W":  {"Top Speed": 78, "Acceleration": 76, "Agility": 72, "Stamina": 66, "Strength": 52, "Jumping": 50},
    "WB": {"Top Speed": 72, "Acceleration": 70, "Agility": 66, "Stamina": 76, "Strength": 58, "Jumping": 56},
}
PHYS_SD = {"Top Speed": 11.0, "Acceleration": 10.0, "Agility": 9.0, "Stamina": 9.0, "Strength": 9.0, "Jumping": 9.0}
PACE_ACCEL_LINK = 0.7      # quick players are usually quick off the mark too (correlation)
PHYS_PER_LEVEL = 0.10      # a slight link to quality: +0.1 per level point above 65 (top v bottom club ~ +-1.2)
# Age: pace and acceleration peak in the mid-twenties and fall ~1% a year in
# the thirties (about 2.5 on this scale); stamina a little slower; strength
# keeps growing into the late twenties.
PACE_AGE = {16: -5, 17: -4, 18: -3, 19: -2, 20: -1, 30: -2, 31: -4.5, 32: -7, 33: -9.5, 34: -12, 35: -14.5}
STAMINA_AGE = {16: -8, 17: -6, 18: -4, 19: -3, 20: -2, 21: -1, 32: -2, 33: -4, 34: -6, 35: -8}
STRENGTH_AGE = {16: -12, 17: -10, 18: -8, 19: -6, 20: -4, 21: -3, 22: -2, 23: -1}

# --- Potential (hidden) ------------------------------------------------------------
# The level a player could grow to (used by development later).  Young
# players have room to grow; a few are real prospects.
WONDERKID = 0.04           # chance a player of 21 or under has a lot more in him

CLUB_NAMES = [
    ("Ashvale Rovers", "Ashvale", (200, 60, 60)),
    ("Kingsmere City", "Kingsmere", (70, 130, 210)),
    ("Millbrook United", "Millbrook", (230, 180, 40)),
    ("Harrowby Athletic", "Harrowby", (60, 160, 90)),
    ("Eastvale Wanderers", "Eastvale", (150, 80, 180)),
    ("Northwick FC", "Northwick", (40, 40, 40)),
    ("Stonecross Albion", "Stonecross", (230, 120, 40)),
    ("Westmoor County", "Westmoor", (120, 190, 220)),
    ("Riverton Dynamo", "Riverton", (180, 30, 90)),
    ("Brackenfield Town", "Brackenfield", (110, 110, 60)),
    ("Fernley Park", "Fernley", (30, 120, 70)),
    ("Castleford Rangers", "Castleford", (20, 60, 140)),
    ("Oakhurst United", "Oakhurst", (200, 200, 200)),
    ("Bramhall Borough", "Bramhall", (160, 40, 40)),
    ("Lydmouth Town", "Lydmouth", (240, 220, 60)),
    ("Sandmere Athletic", "Sandmere", (240, 150, 170)),
    ("Holloway Vale", "Holloway", (90, 60, 140)),
    ("Penrith Forge", "Penrith", (100, 100, 100)),
    ("Whitcombe City", "Whitcombe", (90, 200, 200)),
    ("Darnford Albion", "Darnford", (180, 110, 50)),
]

FIRST = ["Adam", "Alfie", "Ben", "Callum", "Charlie", "Connor", "Dan", "Dylan", "Ethan", "Finn",
         "George", "Harry", "Jack", "Jake", "James", "Joe", "Jordan", "Josh", "Kai", "Kieran",
         "Leo", "Lewis", "Liam", "Luke", "Mason", "Matt", "Max", "Nathan", "Noah", "Oliver",
         "Owen", "Reece", "Rhys", "Ryan", "Sam", "Scott", "Theo", "Tom", "Tyler", "Zach",
         "Mateo", "Luca", "Tomas", "Andrei", "Kofi", "Yusuf", "Pablo", "Jonas", "Emil", "Sami"]
LAST = ["Archer", "Bailey", "Barnes", "Bennett", "Bradley", "Brooks", "Carter", "Clarke", "Cole",
        "Collins", "Cooper", "Davies", "Dawson", "Doyle", "Edwards", "Ellis", "Fisher", "Fletcher",
        "Foster", "Gibson", "Graham", "Grant", "Hale", "Harding", "Hayes", "Holt", "Hughes", "Hunt",
        "Jennings", "Kane", "Kelly", "Lane", "Lawson", "Lowe", "Marsh", "Mason", "Morris", "Murphy",
        "Nash", "Owens", "Parker", "Pearce", "Price", "Quinn", "Reid", "Rhodes", "Shaw", "Stone",
        "Turner", "Walsh", "Ward", "Webb", "West", "Whitaker", "Wood", "Wright", "Young",
        "Novak", "Silva", "Mensah", "Costa", "Varga", "Lindqvist", "Okafor", "Moreau", "Rossi", "Kowal"]

COLUMNS = ["Crossing", "Dribbling", "Finishing", "Control", "Heading", "Long Shots", "Marking",
           "Passing", "Penalties", "Tackling", "Acceleration", "Agility", "Jumping", "Top Speed",
           "Stamina", "Strength", "Aggression", "Anticipation", "Composure", "Decisions",
           "Off The Ball", "Defensive Positioning", "Teamwork", "Work Rate", "Shot Stopping", "Handling"]

POSITIONS = ["GK", "LB", "LCB", "RCB", "RB", "LM", "LCM", "RCM", "RM", "ST1", "ST2"]

# What each position needs: offset from his level, per attribute
_OUTFIELD_GK = {"Shot Stopping": None, "Handling": None}          # None = 5 (outfielders)
PROFILES = {
    "GK": {"Shot Stopping": 12, "Handling": 10, "Anticipation": 5, "Jumping": 2, "Agility": 4,
           "Crossing": -30, "Dribbling": -30, "Finishing": -40, "Long Shots": -30, "Tackling": -30,
           "Marking": -30, "Off The Ball": -35, "Passing": -10, "Control": -12, "Heading": -25,
           "Penalties": -15, "Top Speed": -12, "Acceleration": -8, "Defensive Positioning": -10},
    "CB": {"Heading": 10, "Marking": 12, "Tackling": 12, "Defensive Positioning": 12, "Strength": 10,
           "Jumping": 8, "Aggression": 5, "Crossing": -20, "Dribbling": -15, "Finishing": -25,
           "Long Shots": -15, "Off The Ball": -22, "Agility": -6, "Acceleration": -5},
    "FB": {"Tackling": 6, "Marking": 5, "Defensive Positioning": 4, "Crossing": 5, "Stamina": 8,
           "Acceleration": 6, "Top Speed": 6, "Work Rate": 6, "Finishing": -20, "Heading": -6,
           "Long Shots": -10, "Off The Ball": -6},
    "CM": {"Passing": 10, "Decisions": 6, "Teamwork": 6, "Stamina": 8, "Work Rate": 6, "Control": 5,
           "Anticipation": 4, "Finishing": -8, "Crossing": -5, "Heading": -5},
    "WM": {"Crossing": 10, "Dribbling": 10, "Acceleration": 10, "Top Speed": 10, "Agility": 6,
           "Off The Ball": 5, "Tackling": -10, "Marking": -12, "Defensive Positioning": -10,
           "Heading": -10, "Strength": -8},
    "ST": {"Finishing": 14, "Off The Ball": 12, "Composure": 6, "Heading": 6, "Anticipation": 6,
           "Tackling": -25, "Marking": -25, "Defensive Positioning": -25, "Crossing": -10, "Work Rate": -5},
    # NEW POSITIONS (Nov 2026): defensive and attacking midfielders, wingers, wing-backs
    "DM": {"Tackling": 8, "Defensive Positioning": 8, "Anticipation": 6, "Marking": 5, "Passing": 5, "Decisions": 5,
           "Teamwork": 6, "Finishing": -15, "Dribbling": -5, "Off The Ball": -10, "Crossing": -10},
    "AM": {"Passing": 8, "Control": 8, "Dribbling": 6, "Off The Ball": 6, "Composure": 6, "Long Shots": 6,
           "Decisions": 5, "Tackling": -15, "Marking": -15, "Defensive Positioning": -15, "Heading": -8},
    "W":  {"Dribbling": 12, "Off The Ball": 8, "Finishing": 4, "Crossing": 6, "Control": 6, "Tackling": -14,
           "Marking": -15, "Defensive Positioning": -14, "Heading": -10},
    "WB": {"Crossing": 8, "Work Rate": 8, "Tackling": 4, "Marking": 2, "Dribbling": 4, "Finishing": -18, "Heading": -8},
}
GROUP = {"GK": "GK", "LCB": "CB", "RCB": "CB", "LB": "FB", "RB": "FB", "LCM": "CM", "RCM": "CM",
         "LM": "WM", "RM": "WM", "ST1": "ST", "ST2": "ST"}

# Club styles by strength (best first): defensive style and build-up
STYLE_BY_RANK = [("press", "play_out"), ("high_press", "play_out"), ("press", "mixed"),
                 ("mid_block", "play_out"), ("mid_block", "mixed"), ("mid_block", "mixed"),
                 ("mid_block", "clear"), ("low_block", "mixed"), ("low_block", "clear"),
                 ("low_block", "clear")]


def style_for_rank(i, n):
    """(defence, build_up) for the club ranked i of n (the 10 styles spread over the league)."""
    return STYLE_BY_RANK[min(len(STYLE_BY_RANK) - 1, int(i * len(STYLE_BY_RANK) / n))]


def _clamp(v):
    return int(max(ATTR_MIN, min(ATTR_MAX, round(v))))


# ---------------------------------------------------------------------------
# Squads of 20, natural positions and the starting XI
# ---------------------------------------------------------------------------
# A player has a NATURAL position; the team plays a 4-4-2 with 11 SLOTS.
SQUAD = (("GK", 2), ("LB", 2), ("RB", 2), ("CB", 4), ("CM", 3), ("LM", 2), ("RM", 2), ("ST", 3))   # 20 (old saves)
SQUAD_25 = (("GK", 3), ("LB", 2), ("RB", 2), ("CB", 5), ("CM", 5), ("LM", 2), ("RM", 2), ("ST", 4))  # 25 (Premier League squad size)
DEPTH_DROP = (0.0, 3.0, 6.0, 8.0, 9.0)   # first choice, second, third... this much below the club's level
RESERVE_DROP = 4.0       # backups are this much below the club's level, on average
SLOT_POS = {"GK": "GK", "LB": "LB", "LCB": "CB", "RCB": "CB", "RB": "RB",
            "LM": "LM", "LCM": "CM", "RCM": "CM", "RM": "RM", "ST1": "ST", "ST2": "ST",
            # the rest of the formation grid (config/slots.py)
            "CB": "CB", "LWB": "LWB", "RWB": "RWB", "LDM": "DM", "DM": "DM", "RDM": "DM", "CM": "CM",
            "LW": "LW", "RW": "RW", "LAM": "AM", "AM": "AM", "RAM": "AM", "ST": "ST"}
NATURAL_GROUP = {"GK": "GK", "LB": "FB", "RB": "FB", "CB": "CB", "CM": "CM", "LM": "WM", "RM": "WM", "ST": "ST",
                 "DM": "DM", "AM": "AM", "LW": "W", "RW": "W", "LWB": "WB", "RWB": "WB"}
# The family a position belongs to - squad planning counts these (a DM covers a CM's place in the squad...)
FAMILY = {"DM": "CM", "AM": "CM", "LW": "LM", "RW": "RM", "LWB": "LB", "RWB": "RB"}
GROUP_FAMILY = {"DM": "CM", "AM": "CM", "W": "WM", "WB": "FB"}
# Playing somewhere else: next door (almost natural), positions he can cover (a small drop), everything else
RELATED = {"DM": {"CM"}, "CM": {"DM", "AM"}, "AM": {"CM"}, "LW": {"LM"}, "LM": {"LW"}, "RW": {"RM"}, "RM": {"RW"},
           "LWB": {"LB"}, "LB": {"LWB"}, "RWB": {"RB"}, "RB": {"RWB"}}
CAN_PLAY = {
    "LB": {"RB", "CB", "LM", "RWB"}, "RB": {"LB", "CB", "RM", "LWB"}, "CB": {"LB", "RB", "CM", "DM"},
    "CM": {"LM", "RM", "CB"}, "LM": {"RM", "CM", "LB", "ST", "LWB", "RW", "AM"},
    "RM": {"LM", "CM", "RB", "ST", "RWB", "LW", "AM"},
    "ST": {"LM", "RM", "AM", "LW", "RW"}, "GK": set(),
    "DM": {"CB", "AM"}, "AM": {"ST", "LW", "RW", "LM", "RM", "DM"},
    "LW": {"RW", "ST", "AM", "RM"}, "RW": {"LW", "ST", "AM", "LM"},
    "LWB": {"LM", "RWB", "RB", "CB"}, "RWB": {"RM", "LWB", "LB", "CB"},
}
FIT_LABEL = {0: "Natural", 1: "Can play there", 2: "Out of position", 3: "Not a keeper / keeper", 4: "Very good there"}
FIT_DROP = {0: 0, 1: 4, 2: 10, 3: 30, 4: 1}  # taken off his technical / mental attributes there
PHYSICAL = {"Acceleration", "Top Speed", "Agility", "Jumping", "Stamina", "Strength"}


def fit(player, slot):
    """0 natural, 1 can play there, 2 out of position, 3 keeper <-> outfield."""
    pos, want = player["Pos"], SLOT_POS[slot]
    if pos == want:
        return 0
    if (pos == "GK") != (want == "GK"):
        return 3
    if want in RELATED.get(pos, set()):
        return 4
    return 1 if want in CAN_PLAY.get(pos, set()) else 2


def family(pos):
    return FAMILY.get(pos, pos)


def fam_group(pos):
    """The position group, with the new positions folded into the old ones (DM/AM -> CM, W -> WM, WB -> FB)."""
    g = NATURAL_GROUP[pos]
    return GROUP_FAMILY.get(g, g)


def _player(rng, pos, level, used_names, pid, age=None, names=None):
    """
    A player for this position.  level: his technical / mental quality at his
    peak (0-100).  Technical and mental attributes come from that level and
    what the position needs; physical ones from the position's real-world
    numbers (PHYS_MEAN), his own build and his age - only slightly from level.
    """
    group = NATURAL_GROUP[pos]
    profile = PROFILES[group]
    if age is None:
        age = rng.randint(*AGE_RANGE)
    now = level + AGE_LEVEL.get(age, 0)          # not at his peak yet / past it
    attrs = {}
    for col in COLUMNS:
        if col in PHYSICAL:
            continue
        if col in ("Shot Stopping", "Handling") and pos != "GK":
            attrs[col] = 5
            continue
        attrs[col] = _clamp(now + profile.get(col, 0) + rng.gauss(0.0, ATTR_SPREAD))
    # Physical: his own athletic make-up
    pm = PHYS_MEAN[group]
    link = PHYS_PER_LEVEL * (level - 65)
    z_pace = rng.gauss(0.0, 1.0)
    z_acc = PACE_ACCEL_LINK * z_pace + (1 - PACE_ACCEL_LINK ** 2) ** 0.5 * rng.gauss(0.0, 1.0)
    z = {"Top Speed": z_pace, "Acceleration": z_acc}
    age_adj = {"Top Speed": PACE_AGE.get(age, 0), "Acceleration": PACE_AGE.get(age, 0),
               "Agility": PACE_AGE.get(age, 0) * 0.6, "Stamina": STAMINA_AGE.get(age, 0),
               "Strength": STRENGTH_AGE.get(age, 0), "Jumping": PACE_AGE.get(age, 0) * 0.5}
    for col in sorted(PHYSICAL):                 # (sorted: the same order every run)
        zz = z.get(col, rng.gauss(0.0, 1.0))
        attrs[col] = _clamp(pm[col] + PHYS_SD[col] * zz + link + age_adj[col])
    first, last = names or (FIRST, LAST)
    for _ in range(50):
        name = f"{rng.choice(first)} {rng.choice(last)}"
        if name not in used_names:
            break
    used_names.add(name)
    # Hidden potential: the level he could reach
    # (young: around the peak level he's heading for; older: about where he is now)
    pot = level + rng.gauss(0.0, 3.0) if age <= 23 else now + max(0.0, rng.gauss(0.5, 1.0))
    if age <= 21 and rng.random() < WONDERKID:
        pot += rng.uniform(6, 14)
    pot = round(min(95.0, max(pot, now)), 1)
    p = {"id": pid, "Pos": pos, "Name": name, "Age": age, "Potential": pot, **attrs}
    p["Pos"] = modern_position(p)            # (a new CM may well be a natural DM...)
    return p


RATING_KEYS = {
    "GK": ("Shot Stopping", "Handling", "Anticipation", "Decisions", "Agility"),
    "CB": ("Marking", "Tackling", "Heading", "Defensive Positioning", "Strength", "Anticipation"),
    "FB": ("Tackling", "Marking", "Crossing", "Acceleration", "Stamina", "Defensive Positioning"),
    "CM": ("Passing", "Decisions", "Control", "Teamwork", "Stamina", "Anticipation"),
    "WM": ("Crossing", "Dribbling", "Acceleration", "Top Speed", "Control", "Passing"),
    "ST": ("Finishing", "Off The Ball", "Composure", "Control", "Heading", "Acceleration"),
}


# For ratings: what's normal for the position (physical attributes don't
# follow the level, so their "normal" is the position average, scored around 65)
RATING_KEYS.update({
    "DM": ("Tackling", "Defensive Positioning", "Anticipation", "Decisions", "Passing", "Teamwork"),
    "AM": ("Passing", "Control", "Dribbling", "Off The Ball", "Composure", "Decisions"),
    "W":  ("Dribbling", "Acceleration", "Top Speed", "Control", "Off The Ball", "Crossing"),
    "WB": ("Crossing", "Stamina", "Acceleration", "Tackling", "Work Rate", "Dribbling"),
})
# The new positions' profiles are set so a player's rating means the same in either position: a typical
# central midfielder rates the same as a DM as he does as a CM (measured on the world's players, 2026)
_SAME_SCALE = {"DM": 3.3, "AM": 4.0, "W": 2.35, "WB": 2.4}
for _g, _shift in _SAME_SCALE.items():
    _tech = [k for k in RATING_KEYS[_g] if k not in PHYSICAL]
    for _k in _tech:
        PROFILES[_g][_k] = PROFILES[_g].get(_k, 0) - _shift * len(RATING_KEYS[_g]) / len(_tech)
RATING_PROFILE = {g: dict(PROFILES[g], **{k: v - 65 for k, v in PHYS_MEAN[g].items()}) for g in PROFILES}

# Which old-style players are really one of the new positions: if his rating there beats his rating in his
# old position by this much (set so squads look like today's Premier League: ~2 DMs, ~1 AM, mostly wingers
# rather than wide midfielders, the odd wing-back)
RELABEL = {"CM": (("DM", 1.1), ("AM", 3.0)), "LM": (("LW", -1.1),), "RM": (("RW", -1.1),),
           "LB": (("LWB", 1.8),), "RB": (("RWB", 1.8),), "ST": (("AM", 4.2),)}


def _rating_as(player, group):
    keys, prof = RATING_KEYS[group], RATING_PROFILE[group]
    return sum(player[k] - prof.get(k, 0) for k in keys) / len(keys)


def modern_position(player):
    """His natural position in the modern set (DM, AM, LW/RW, LWB/RWB) - from his attributes."""
    pos = player["Pos"]
    if pos not in RELABEL:
        return pos
    here = _rating_as(player, NATURAL_GROUP[pos])
    best, out = 0.0, pos
    for new, margin in RELABEL[pos]:
        gain = _rating_as(player, NATURAL_GROUP[new]) - here - margin
        if gain > best:
            best, out = gain, new
    return out


def overall(player, slot=None):
    """
    A 0-100 rating: in his natural position, or (with slot) playing there.
    It's relative to what the position needs (a centre-back's marking is
    naturally high), so ratings compare across positions.
    """
    group = NATURAL_GROUP[player["Pos"]] if slot is None else NATURAL_GROUP[SLOT_POS[slot]]
    keys, prof = RATING_KEYS[group], RATING_PROFILE[group]
    r = sum(player[k] - prof.get(k, 0) for k in keys) / len(keys)
    if slot is not None:
        r -= FIT_DROP[fit(player, slot)]
    return round(r)


# ---------------------------------------------------------------------------
# The club's formation (config/slots.py): club["formation"] = its ten outfield
# spots (a list), or nothing = the 4-4-2.
# ---------------------------------------------------------------------------
def formation_of(club):
    """The ten outfield spots the club plays."""
    from config import slots as slots_mod
    f = club.get("formation")
    if isinstance(f, str):
        f = slots_mod.FORMATIONS.get(f)
    if not f or slots_mod.check(f):
        return list(slots_mod.FORMATIONS["4-4-2"])
    return [s for s in f if s != "GK"]


def xi_slots(club):
    """The eleven spots: keeper first, then the formation's."""
    return ["GK"] + formation_of(club)


def formation_name(club):
    """Its name if it's a ready-made formation (else "Custom")."""
    from config import slots as slots_mod
    mine = sorted(formation_of(club))
    for name, spots in slots_mod.FORMATIONS.items():
        if sorted(spots) == mine:
            return name
    return "Custom"


_PICK_FIRST = {"GK": 0, "CB": 1, "FB": 2, "WB": 3, "DM": 4, "CM": 5, "WM": 6, "W": 7, "AM": 8, "ST": 9}


def pick_order(slots):
    """The order a manager fills the spots in: keeper, the spine at the back, then forward
    (for the 4-4-2: GK, LCB, RCB, LB, RB, LCM, RCM, LM, RM, ST1, ST2 - as it always was)."""
    from config import slots as slots_mod
    return sorted(slots, key=lambda s: (_PICK_FIRST[slots_mod.kind(s)], slots_mod.lane(s)))


def best_lineup(club, exclude=(), penalty=None, slots=None):
    """The strongest XI: each slot gets the best remaining player for it
    (exclude: ids of players who can't play - injured, suspended; penalty:
    {id: rating points off} - e.g. for tired legs; slots: a formation to try
    instead of the club's own)."""
    order = pick_order(["GK"] + [s for s in (slots or formation_of(club)) if s != "GK"])
    used, lineup = set(exclude), {}
    penalty = penalty or {}
    for slot in order:
        pick = max((p for p in club["players"] if p["id"] not in used),
                   key=lambda p: overall(p, slot) - penalty.get(p["id"], 0), default=None)
        if pick is not None:
            lineup[slot] = pick["id"]
            used.add(pick["id"])
    return lineup


def lineup_ok(club, lineup=None):
    """Is the XI complete for the club's formation (each spot filled, nobody twice, everyone still here)?"""
    lineup = club.get("lineup") if lineup is None else lineup
    lineup = lineup or {}
    ids = [lineup.get(s) for s in xi_slots(club)]
    return (None not in ids and len(set(ids)) == len(ids) and set(lineup) == set(xi_slots(club))
            and all(player_by_id(club, i) is not None for i in ids))


def player_by_id(club, pid):
    p = next((p for p in club["players"] if p["id"] == pid), None)
    if p is None and club.get("academy"):                      # (an academy player - career/youth.py)
        p = next((q for q in club["academy"] if q["id"] == pid), None)
    return p


def _squad(rng, strength, used):
    """20-man squad (the old 10-club league)."""
    players, pid = [], 0
    for pos, n in SQUAD:
        for k in range(n):
            drop = 0.0 if k == 0 else RESERVE_DROP
            players.append(_player(rng, pos, strength - drop + rng.gauss(0.0, PLAYER_SPREAD), used, pid))
            pid += 1
    return players


def _age(rng, young=False):
    ages = list(AGE_WEIGHTS)
    w = [AGE_WEIGHTS[a] * (1.4 if young and a <= 21 else 1.0) for a in ages]
    return rng.choices(ages, weights=w)[0]


def _squad_25(rng, strength, used):
    """25-man squad: first choices around the club's level, then backups and youngsters."""
    players, pid = [], 0
    for pos, n in SQUAD_25:
        for k in range(n):
            age = _age(rng, young=k >= 2)
            peak = strength - DEPTH_DROP[min(k, len(DEPTH_DROP) - 1)] + rng.gauss(0.0, PLAYER_SPREAD)
            players.append(_player(rng, pos, peak, used, pid, age=age))
            pid += 1
    return players


def generate(seed=None, n_clubs=20):
    """The clubs, strongest first: [{id, name, short, colour, strength, roles, tactics, players, lineup}]"""
    rng = random.Random(seed)
    names = list(CLUB_NAMES)[:n_clubs]
    rng.shuffle(names)
    strengths = STRENGTHS if n_clubs == 20 else STRENGTHS_10
    used = set()
    clubs = []
    for i, ((name, short, colour), strength) in enumerate(zip(names, strengths)):
        defence, build_up = style_for_rank(i, len(strengths))
        club = {
            "id": i, "name": name, "short": short, "colour": list(colour), "strength": strength,
            "roles": {"base": rng.choice(["blue", "red"])},
            "tactics": {"defence": defence, "build_up": build_up},
            "instructions": {},
            "players": _squad_25(rng, strength, used) if n_clubs == 20 else _squad(rng, strength, used),
        }
        club["lineup"] = best_lineup(club)
        clubs.append(club)
    return clubs


def upgrade_club(club, rng=None):
    """An 11-man squad from an older save: give everyone a natural position and add 9 reserves."""
    if "lineup" in club:
        return club
    rng = rng or random.Random(club["id"])
    to_pos = {"LCB": "CB", "RCB": "CB", "LCM": "CM", "RCM": "CM", "ST1": "ST", "ST2": "ST"}
    lineup = {}
    for pid, p in enumerate(club["players"]):
        slot = p.pop("Role")
        p["id"], p["Pos"] = pid, to_pos.get(slot, slot)
        lineup[slot] = pid
    have = {}
    for p in club["players"]:
        have[p["Pos"]] = have.get(p["Pos"], 0) + 1
    used = {p["Name"] for p in club["players"]}
    pid = len(club["players"])
    for pos, n in SQUAD:
        for _ in range(max(0, n - have.get(pos, 0))):
            club["players"].append(_player(rng, pos, club["strength"] - RESERVE_DROP + rng.gauss(0.0, PLAYER_SPREAD),
                                           used, pid))
            pid += 1
    club["lineup"] = lineup
    if isinstance(club.get("roles"), str):
        club["roles"] = {"base": club["roles"]}
    club.setdefault("instructions", {})
    return club


BENCH_SIZE = 9          # Premier League: nine named substitutes
BENCH_ORDER = ["GK", "CB", "LB", "LWB", "RB", "RWB", "DM", "CM", "AM", "LM", "LW", "RM", "RW", "ST"]


def bench(club, exclude=()):
    """
    The substitutes (up to 9): a keeper, then cover for each part of the
    team - the best centre-back, full-back, central midfielder, wide man and
    striker not starting - then the best of the rest.
    """
    starting = set((club.get("lineup") or {}).values())
    rest = [p for p in club["players"] if p["id"] not in starting and p["id"] not in exclude]
    if len(rest) <= BENCH_SIZE:
        picks = rest
    else:
        picks = []
        cover = (("GK",), ("CB",), ("LB", "RB"), ("CM",), ("LM", "RM"), ("ST",))
        for group in cover:
            cands = [p for p in rest if family(p["Pos"]) in group and p not in picks]
            if cands:
                picks.append(max(cands, key=overall))
        others = sorted([p for p in rest if p not in picks and p["Pos"] != "GK"], key=lambda p: -overall(p))
        picks += others[:BENCH_SIZE - len(picks)]
    picks.sort(key=lambda p: (BENCH_ORDER.index(p["Pos"]) if p["Pos"] in BENCH_ORDER else 99, -overall(p)))
    return picks


def match_squad(club, exclude=()):
    """What the match engine needs for substitutions: the bench (raw
    attributes, the drop and rating for each slot) and the XI's ids and ratings."""
    lineup = club["lineup"]
    out_bench = []
    for p in bench(club, exclude):
        out_bench.append({
            "id": p["id"], "name": p["Name"], "pos": p["Pos"], "age": p.get("Age", 26),
            "condition": p.get("condition", 1.0),
            "row": {c: _clamp(p[c] + _mood(p).get(c, 0)) if c in _mood(p) else p[c] for c in COLUMNS},
            "drop": {slot: FIT_DROP[fit(p, slot)] for slot in SLOT_POS},
            "rating": {slot: overall(p, slot) for slot in SLOT_POS},
        })
    ids = {slot: lineup[slot] for slot in xi_slots(club)}
    ratings = {slot: overall(player_by_id(club, pid), slot) for slot, pid in ids.items()}
    ages = {slot: player_by_id(club, pid).get("Age", 26) for slot, pid in ids.items()}
    cond = {slot: player_by_id(club, pid).get("condition", 1.0) for slot, pid in ids.items()}
    return {"bench": out_bench, "lineup_ids": ids, "lineup_ratings": ratings, "lineup_ages": ages,
            "lineup_condition": cond}


def _mood(p):
    """Match-day adjustments: morale (career/morale.py) + sharpness (career/fitness.py)."""
    from career import morale, fitness
    out = dict(morale.match_adjust(p))
    for k, v in fitness.match_adjust(p).items():
        out[k] = round(out.get(k, 0.0) + v, 1)
    return out


def write_squad_csv(club, folder, exclude=()):
    """
    Write the club's starting XI as a CSV the match engine loads (data/teams
    format).  A man playing out of position has his technical and mental
    attributes reduced there (his pace and strength don't change).
    """
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"club_{club['id']}.csv")
    if not lineup_ok(club):
        club["lineup"] = best_lineup(club, exclude)  # an incomplete XI: pick the best one
    for slot, pid in list(club["lineup"].items()):
        if pid in exclude:                           # can't play: the best available man for the slot
            used = set(club["lineup"].values()) | set(exclude)
            cands = [p for p in club["players"] if p["id"] not in used]
            if cands:
                club["lineup"][slot] = max(cands, key=lambda p: overall(p, slot))["id"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Role", "Name"] + COLUMNS)
        for slot in xi_slots(club):
            p = player_by_id(club, club["lineup"][slot])
            drop = FIT_DROP[fit(p, slot)]
            mood = _mood(p)
            vals = []
            for c in COLUMNS:
                v = p[c] + mood.get(c, 0)                  # (his morale: career/morale.py)
                if c in ("Shot Stopping", "Handling"):
                    if slot != "GK":
                        v = 5                      # only the man in goal can use his hands
                elif drop and c not in PHYSICAL:
                    v = _clamp(v - drop)
                elif c in mood:
                    v = _clamp(v)
                vals.append(v)
            w.writerow([slot, p["Name"]] + vals)
    return path
