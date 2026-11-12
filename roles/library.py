"""
roles/library.py
================
The role library: every way of playing a position that the engine knows.

A role is now a handful of SETTINGS, not a block of positioning code.  The
team decides its shape together (ai/team_shape.py) and each player's role
says how he plays his part in it - how high a full-back pushes on, whether
a winger hugs the touchline or comes inside, whether a striker pins the
last line or drops to link play.  Because the shape works in each team's
own attacking direction, every role works for either team automatically.

Choosing roles
--------------
In match_config.json, each team has a "roles" entry.  Either a role set name:
    "roles": "blue"
or a set plus per-position changes:
    "roles": {"base": "blue", "LM": "LM_red", "ST1": "ST1_red"}

Team tactics (optional) go next to it:
    "tactics": {"line": "high"}          # "deep", "mid" (default) or "high"

Adding a new role
-----------------
Add an entry to ROLES below with the settings you want - anything you leave
out uses the position's default (ai/team_shape.py DEFAULTS).  That's it.

Settings
--------
  Full-backs    fb_height   m he pushes on beyond the centre-backs (6 = cautious, 18 = flies forward)
                width       0-1: 1 = on the touchline, 0.5 = inside channel
  Centre-mids   cm_forward  0-1: 0 = sits and screens, 1 = joins every attack (box-to-box)
  Wide mids     wm_height   m ahead of the ball he likes to be in possession
                width       0-1 (an inverted winger / inside forward ~0.5)
                track_back  0-1: 1 = drops fully into the midfield line, 0 = stays ~6 m higher
  Strikers      st_style    "pin" = on the last line, threatening in behind
                            "link" = drops between the lines to link play
                stay_up     True = stays high when defending (outlet for the counter)
  Anyone        roam        0-1: wanders from his spot unpredictably
  Runs          runs        preferences for ai/run_planner.py, e.g. {"in_behind": 1.0, "box": 0.5}

Player instructions (like Football Manager's) - a role carries sensible
defaults, and you can override them for a match in match_config.json:
    "instructions": {"RM": {"crossing": "more", "cross_from": "byline"}}
  crossing      "more" / "normal" / "less"  - how readily he puts a cross in
  cross_from    "byline" - gets to the line before he crosses (or cuts it back)
                "early"  - whips it in from deep, 25-35 m out
                "mixed"  - whichever is on (the default)
(ai/decisive.py uses these.)
"""

from dataclasses import dataclass, field


@dataclass
class Role:
    position: str            # LB, LCB, RCB, RB, LM, LCM, RCM, RM, ST1, ST2
    name: str                # shown to you; describes how the role plays
    shape: dict = field(default_factory=dict)   # settings for ai/team_shape.py
    runs: dict = None        # run preferences for ai/run_planner.py (None = position defaults)
    instructions: dict = None   # default player instructions, e.g. {"crossing": "more"}


# ---------------------------------------------------------------------------
# All roles.  Ids end in _blue / _red: the roles each team was given originally.
# ---------------------------------------------------------------------------
ROLES = {
    # Full-backs
    "LB_blue":  Role("LB", "Overlapping Full-Back (goal-side recovery)",
                     {"fb_height": 16.0, "width": 0.95}, runs={"in_behind": 0.35},
                     instructions={"crossing": "normal", "cross_from": "mixed"}),
    "LB_red":   Role("LB", "Overlapping Full-Back",
                     {"fb_height": 14.0, "width": 0.95}, runs={"in_behind": 0.35},
                     instructions={"crossing": "normal", "cross_from": "mixed"}),
    "RB_blue":  Role("RB", "Attacking Full-Back",
                     {"fb_height": 18.0, "width": 1.0}, runs={"in_behind": 0.35},
                     instructions={"crossing": "more", "cross_from": "early"}),
    "RB_red":   Role("RB", "Attacking Full-Back",
                     {"fb_height": 16.0, "width": 0.95}, runs={"in_behind": 0.35},
                     instructions={"crossing": "more", "cross_from": "early"}),
    # Centre-backs
    "LCB_blue": Role("LCB", "Ball-Playing Centre-Back (splits wide in build-up)"),
    "LCB_red":  Role("LCB", "Centre-Back"),
    "RCB_blue": Role("RCB", "Centre-Back (covers the right-back)"),
    "RCB_red":  Role("RCB", "Centre-Back"),
    # Central midfield
    "LCM_blue": Role("LCM", "Box-to-Box Midfielder",
                     {"cm_forward": 0.75}, runs={"in_behind": 0.3, "box": 0.7}),
    "LCM_red":  Role("LCM", "Complete Box-to-Box Midfielder",
                     {"cm_forward": 0.85}, runs={"in_behind": 0.3, "box": 0.7}),
    "RCM_blue": Role("RCM", "Holding Midfielder (screens the back four)",
                     {"cm_forward": 0.15}, runs={"in_behind": 0.1, "box": 0.3}),
    "RCM_red":  Role("RCM", "Central Midfielder",
                     {"cm_forward": 0.4}),
    # Wide midfield
    "LM_blue":  Role("LM", "Inside Forward (inverted left midfielder)",
                     {"wm_height": 8.0, "width": 0.5, "track_back": 0.7},
                     runs={"in_behind": 1.0, "box": 0.8},
                     instructions={"crossing": "less", "cross_from": "mixed"}),
    "LM_red":   Role("LM", "Wide Midfielder (hard-working, presses)",
                     {"wm_height": 3.0, "width": 0.95, "track_back": 1.0},
                     instructions={"crossing": "normal", "cross_from": "mixed"}),
    "RM_blue":  Role("RM", "Unpredictable Winger (Dembele role)",
                     {"wm_height": 7.0, "width": 0.95, "track_back": 0.6, "roam": 1.0},
                     runs={"in_behind": 0.9, "box": 0.6},
                     instructions={"crossing": "normal", "cross_from": "byline"}),
    "RM_red":   Role("RM", "Inside Forward (Salah role: like Dembele's freedom, but cuts inside)",
                     {"wm_height": 7.0, "width": 0.75, "track_back": 0.6},
                     runs={"in_behind": 0.9, "box": 0.8},
                     instructions={"crossing": "less", "cross_from": "mixed"}),
    "RM_red_old": Role("RM", "Wide Midfielder (heavy pressing) - red's original right midfielder",
                     {"wm_height": 3.0, "width": 0.95, "track_back": 1.0},
                     instructions={"crossing": "normal", "cross_from": "mixed"}),
    # Strikers
    "ST1_blue": Role("ST1", "Advanced Forward (runs in behind, presses high)",
                     {"st_style": "pin", "stay_up": True}),
    "ST1_red":  Role("ST1", "Deep-Lying Forward (drops off to link play)",
                     {"st_style": "link", "stay_up": True}),
    "ST2_blue": Role("ST2", "Poacher (pure goal threat, in-behind runs)",
                     {"st_style": "pin", "stay_up": True}, runs={"in_behind": 1.2, "box": 1.0}),
    "ST2_red":  Role("ST2", "Poacher (pure goal threat)",
                     {"st_style": "pin", "stay_up": True}),
}

POSITIONS = ("LB", "LCB", "RCB", "RB", "LM", "LCM", "RCM", "RM", "ST1", "ST2")

# A role's settings don't depend on the side of the pitch, so a role works in
# either position of its pair (a left midfielder can play the winger role).
POSITION_GROUP = {"LB": "FB", "RB": "FB", "LCB": "CB", "RCB": "CB", "LCM": "CM", "RCM": "CM",
                  "LM": "WM", "RM": "WM", "ST1": "ST", "ST2": "ST"}

# The roles offered in the manager game's Tactics screen, by position group:
# (role id, name, what he does).  Near-duplicates are left out, and so are the
# centre-back variants - they don't differ in the engine yet, so there's
# nothing to choose between.
MANAGER_ROLES = {
    "FB": [("LB_red", "Cautious full-back", "Gets forward now and then; stays close to the centre-backs."),
           ("LB_blue", "Full-back", "Overlaps on the outside, gets back goal-side."),
           ("RB_blue", "Attacking full-back", "Pushes high and wide, crosses early and often.")],
    "CB": [("LCB_red", "Centre-back", "Defends the box, wins headers, keeps it simple.")],
    "CM": [("RCM_blue", "Holding midfielder", "Sits in front of the back four and screens it."),
           ("RCM_red", "Central midfielder", "Links defence and attack, gets forward sometimes."),
           ("LCM_blue", "Box-to-box midfielder", "Gets up and down - arrives in the box late.")],
    "WM": [("LM_red", "Wide midfielder", "Hugs the touchline, works hard, tracks back fully."),
           ("RM_blue", "Winger", "High and wide, roams, goes to the byline to cross."),
           ("RM_red", "Wide forward", "Starts wide, cuts inside, runs in behind and into the box."),
           ("LM_blue", "Inside forward", "Narrow - comes inside to shoot and combine, crosses little.")],
    "ST": [("ST1_blue", "Advanced forward", "Plays on the last defender, runs in behind, presses."),
           ("ST2_blue", "Poacher", "Lives in the box - always looking to run in behind and score."),
           ("ST1_red", "Deep-lying forward", "Drops off between the lines to link the play.")],
}

# Role sets: a full outfield line-up of roles
ROLE_SETS = {
    "blue": {pos: f"{pos}_blue" for pos in POSITIONS},   # Blue's roles
    "red":  {pos: f"{pos}_red" for pos in POSITIONS},    # Red's roles
}


def get_role(role_id):
    if role_id not in ROLES:
        raise KeyError(f"Unknown role '{role_id}'. Known roles: {', '.join(sorted(ROLES))}")
    return ROLES[role_id]


def default_role_id(position, team_id):
    return f"{position}_{'blue' if team_id == 0 else 'red'}"


CROSSING = ("more", "normal", "less")
CROSS_FROM = ("byline", "early", "mixed")
OVERRIDE_INSTRUCTIONS = {}    # team id -> {position: {...}} (sim.py --home-crossing etc.)
_warned_instr = set()


def instructions_for(player):
    """His player instructions: the role's defaults, then this match's settings."""
    out = {"crossing": "normal", "cross_from": "mixed"}
    try:
        out.update(role_for(player).instructions or {})
    except Exception:
        pass
    try:
        import core.database as database
        out.update((database.INSTRUCTIONS.get(player.team, {}) or {}).get(getattr(player, "slot", player.role), {}) or {})
    except Exception:
        pass
    out.update((OVERRIDE_INSTRUCTIONS.get(player.team, {}) or {}).get(getattr(player, "slot", player.role), {}) or {})
    for key, allowed, default in (("crossing", CROSSING, "normal"), ("cross_from", CROSS_FROM, "mixed")):
        if out.get(key) not in allowed:
            if (key, out.get(key)) not in _warned_instr:
                _warned_instr.add((key, out.get(key)))
                print(f"[Roles] Unknown {key} '{out.get(key)}' - using {default}. Choose from: {', '.join(allowed)}")
            out[key] = default
    return out


def role_for(player):
    """The Role a player is using (falls back to his team's original role)."""
    role_id = getattr(player, "role_style", None) or default_role_id(player.role, player.team)
    return get_role(role_id)


def apply_role_set(team, spec):
    """
    Give a team its roles.  spec is a role set name ("blue"/"red"), or a dict
    like {"base": "blue", "LM": "LM_red"}.  Unknown names are reported and
    the player keeps his team's original role.
    """
    if not team:
        return
    team_id = team[0].team
    if isinstance(spec, str):
        spec = {"base": spec}
    spec = dict(spec or {})
    base = spec.pop("base", "blue" if team_id == 0 else "red")
    if base not in ROLE_SETS:
        print(f"[Roles] Unknown role set '{base}' - using defaults")
        base = "blue" if team_id == 0 else "red"
    chosen = dict(ROLE_SETS[base])
    chosen.update(spec)

    from config import slots
    for player in team:
        if player.role not in POSITIONS:
            continue                                   # GK has its own logic
        slot = getattr(player, "slot", player.role)
        if slot in chosen:
            role_id = chosen[slot]
        elif slot in slots.DEFAULT_ROLE:               # a spot outside the 4-4-2: its own sort of role
            role_id = slots.DEFAULT_ROLE[slot]
        else:
            role_id = chosen.get(player.role, default_role_id(player.role, team_id))
        role = ROLES.get(role_id)
        if role is None or POSITION_GROUP.get(role.position) != POSITION_GROUP.get(player.role):
            print(f"[Roles] '{role_id}' is not a {player.role} role - "
                  f"keeping {default_role_id(player.role, team_id)}")
            role_id = default_role_id(player.role, team_id)
        player.role_style = role_id
