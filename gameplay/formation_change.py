"""
gameplay/formation_change.py
============================
Changing shape during a match.

YOU: the Formation button in the substitutions panel (S) - drag your
players to new spots on the grid, or pick a ready-made formation, then
Confirm.  It takes effect straight away (a shout from the touchline; no
substitution needed), like a role change.

AI MANAGERS (career matches): they react to the score late on, as real
managers do -
  - one goal down from the 70th minute: go 4-2-4 (an extra striker for a
    midfielder); still behind at 85: everybody forward (2-3-5)
  - two or more down at 75: 4-2-4 (and no more - the game's usually gone)
  - one goal up from the 80th minute: shut up shop - five at the back
They decide at a stoppage, like substitutions.

Each player keeps his role if his new spot is the same sort of position;
otherwise he takes the spot's usual role.
"""

from config import slots as slots_mod

CHASE = "4-2-4"
ALL_OUT = "2-3-5"
PARK = "5-4-1"
CHASE_FROM = 70          # one down: go for it from here
ALL_OUT_FROM = 85
CHASE_TWO_FROM = 75
PARK_FROM = 80

if "4-2-4" not in slots_mod.FORMATIONS:
    slots_mod.FORMATIONS["4-2-4"] = ["LB", "LCB", "RCB", "RB", "LCM", "RCM", "LW", "ST1", "ST2", "RW"]


def current(team):
    """{player: slot} for the active outfield players."""
    return {p: p.slot for p in team if p.role != "GK" and getattr(p, "is_active", True)}


def fit(team, formation):
    """Put the active players into a formation's spots, moving each as little as possible.
    (Down to ten men: the spare spot - the furthest forward that's left - stays empty.)"""
    spots = list(slots_mod.FORMATIONS.get(formation, formation))
    players = list(current(team))

    def cost(p, s):
        r0, l0 = slots_mod.GRID.get(p.slot, (2, 0))
        r1, l1 = slots_mod.GRID[s]
        same = slots_mod.kind(p.slot) == slots_mod.kind(s)
        return abs(r0 - r1) * 1.5 + abs(l0 - l1) + (0 if same else 0.75)

    pairs = sorted(((cost(p, s), i, j) for i, p in enumerate(players) for j, s in enumerate(spots)))
    out, used_p, used_s = {}, set(), set()
    for c, i, j in pairs:
        if i in used_p or j in used_s:
            continue
        out[players[i]] = spots[j]
        used_p.add(i)
        used_s.add(j)
    return out


def apply(engine, tid, plan):
    """plan: {player: new spot}.  Returns a problem (str) or None."""
    import config.formations as formations
    from roles import library as lib
    team = engine.team0 if tid == 0 else engine.team1
    act = current(team)
    new = {p: plan.get(p, s) for p, s in act.items()}
    field = list(new.values())
    if len(set(field)) != len(field):
        return "Two players in the same spot."
    if not any(slots_mod.row(s) == 0 for s in field):
        return "Nobody in defence - keep at least one player at the back."
    for p, s in new.items():
        if s == p.slot:
            continue
        old_group = lib.POSITION_GROUP.get(p.role)
        p.slot = s
        p.role = slots_mod.proxy(s)
        if lib.POSITION_GROUP.get(p.role) != old_group or slots_mod.kind(s) in ("DM", "AM", "W", "WB"):
            p.role_style = _role_for(tid, s)
    all_slots = list(dict.fromkeys(p.slot for p in team if p.role != "GK"))
    formations.db.formation[tid] = None if slots_mod.is_legacy(all_slots) else all_slots
    return None


def _role_for(tid, slot):
    """The spot's role: the team's choice for it if it has one, else the spot's usual role."""
    from roles import library as lib
    try:
        import config.formations as formations
        chosen = formations.db.team_roles.get(tid) or {}
    except Exception:
        chosen = {}
    if isinstance(chosen, dict) and slot in chosen:
        return chosen[slot]
    if slot in slots_mod.DEFAULT_ROLE:
        return slots_mod.DEFAULT_ROLE[slot]
    return lib.default_role_id(slots_mod.proxy(slot), tid)


def name_of(team):
    """The formation's name, if it's a ready-made one."""
    field = sorted(p.slot for p in team if p.role != "GK")
    for name, spots in slots_mod.FORMATIONS.items():
        if sorted(spots) == field:
            return name
    return "custom"


# ---------------------------------------------------------------------------
# AI managers
# ---------------------------------------------------------------------------
def ai_manage(engine, tid, minute, done):
    """At a stoppage: change shape to chase a game or protect a lead.  done: set of stages already used."""
    team = engine.team0 if tid == 0 else engine.team1
    diff = engine.score[tid] - engine.score[1 - tid]
    stage = None
    if diff == -1 and minute >= ALL_OUT_FROM and "all_out" not in done:
        stage, form = "all_out", ALL_OUT
    elif diff == -1 and minute >= CHASE_FROM and "chase" not in done:
        stage, form = "chase", CHASE
    elif diff <= -2 and minute >= CHASE_TWO_FROM and "chase" not in done:
        stage, form = "chase", CHASE
    elif diff == 1 and minute >= PARK_FROM and "park" not in done:
        stage, form = "park", PARK
    if stage is None:
        return None
    done.add(stage)
    if stage == "chase":
        done.add("park")
    if name_of(team) == form:
        return None
    if stage == "park" and sum(1 for p in team if slots_mod.row(p.slot) == 0 or slots_mod.kind(p.slot) == "WB") >= 5:
        return None                                   # (already five at the back)
    problem = apply(engine, tid, fit(team, form))
    return None if problem else form
