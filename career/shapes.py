"""
career/shapes.py
================
Formations in the career: each club plays its own shape.

YOU pick yours on the Tactics screen - a ready-made formation, or move your
players to any spot on the grid (config/slots.py) - and it's what you play
until you change it.

AI CLUBS choose theirs like a real manager: the shape that gets the most out
of the squad, with a lean towards what's in fashion in that league.  They
think again in pre-season, when the summer window shuts (2 September) and when
the January one does (3 February), and keep what they have unless something
else is clearly better.

Real usage (the lean):
  Premier League 2024/25, 760 team-matches: 4-2-3-1 408 (13 of the 20 clubs'
  main shape), 3-4-2-1 117, 4-3-3 114, 4-1-4-1 27, 4-4-2 20
  (premierleague.com, "Season trends: What were the most-popular formations
  in 2024/25?").
  LaLiga: 4-4-2 the most used shape from 2017/18 to 2020/21, 4-2-3-1 before
  that, 4-3-3 steady (Journal of Human Kinetics, "Evolution of Tactics in
  Professional Soccer ... LaLiga 2012-2021").
"""

import random

from career import clubs as clubs_mod
from config import slots as slots_mod

# Rating points added to a shape's XI average when a manager weighs it up
LEAN = {
    "pl": {"4-2-3-1": 0.75, "4-3-3": 0.45, "3-4-2-1": 1.0, "4-1-4-1": 0.0, "4-4-2": -0.35,
           "3-5-2": -0.3, "5-3-2": -0.4, "4-3-1-2": -0.6},
    "d1": {"4-2-3-1": 0.55, "4-3-3": 0.3, "3-4-2-1": 0.6, "4-1-4-1": 0.0, "4-4-2": 0.25,
           "3-5-2": 0.0, "5-3-2": -0.2, "4-3-1-2": -0.5},
    "es": {"4-4-2": 0.65, "4-2-3-1": 0.5, "4-3-3": 0.45, "3-4-2-1": 0.3, "4-1-4-1": 0.1,
           "3-5-2": -0.3, "5-3-2": -0.3, "4-3-1-2": -0.4},
}
MANAGER_TASTE = 0.45       # each manager's own preferences (sd, rating points per shape)
STICK = 0.4                # a new shape has to be this much better to change


def xi_average(club, form, exclude=()):
    spots = slots_mod.FORMATIONS[form]
    xi = clubs_mod.best_lineup(club, exclude=exclude, slots=spots)
    rs = [clubs_mod.overall(clubs_mod.player_by_id(club, pid), s) for s, pid in xi.items()]
    return sum(rs) / max(1, len(rs))


def _taste(club, form):
    """A manager's own leaning towards a shape (the same for him all career)."""
    seed = f"{club.get('manager_seed', club['id'])}:{club['name']}:{form}"
    return random.Random(seed).gauss(0.0, MANAGER_TASTE)


def choose(club, league="pl", exclude=()):
    """The formation (name) a manager would pick for this squad."""
    lean = LEAN[league]
    score = {f: xi_average(club, f, exclude) + lean[f] + _taste(club, f) for f in lean}
    now = clubs_mod.formation_name(club) if "formation" in club else None      # (None: never chosen)
    best = max(score, key=score.get)
    if now in score and score[best] - score[now] < STICK:
        return now
    return best


def set_formation(club, spots, refill=True):
    """Change a club's shape.  refill: AI - pick the best XI for it."""
    spots = [s for s in spots if s != "GK"]
    club["formation"] = None if slots_mod.is_legacy(spots) else list(spots)
    if refill:
        club["lineup"] = clubs_mod.best_lineup(club)


def ai_review(career, rng=None):
    """Every AI club (and every Spanish one) has a think about its shape."""
    from career import spain
    role_baseline([p for c in career["clubs"] + spain.clubs(career) for p in c["players"]])
    for c in career["clubs"]:
        if c["id"] == career.get("my_club"):
            continue
        _review(c, c.get("league", "pl"))
    for c in spain.clubs(career):
        _review(c, "es")


def _review(club, league):
    form = choose(club, league)
    if "formation" not in club or form != clubs_mod.formation_name(club):
        set_formation(club, slots_mod.FORMATIONS[form])
    ai_roles(club)
    from career import captains
    captains.ai_pick(club)


# ---------------------------------------------------------------------------
# AI managers' roles: each spot gets the role that suits the man playing there,
# with the manager's own leanings (some like attacking full-backs, some a
# deep-lying forward...).  Centre-backs and keepers have one role.
# ---------------------------------------------------------------------------
PACE = ("Acceleration", "Top Speed")
ROLE_FIT = {          # role: (attributes that suit it, weight), averaged
    "LB_red":   [("Tackling", 1), ("Defensive Positioning", 1.2), ("Marking", 1), ("Crossing", -0.4)],
    "LB_blue":  [("Tackling", 0.8), ("Stamina", 1), ("Crossing", 0.8), ("Top Speed", 0.6), ("Defensive Positioning", 0.6)],
    "RB_blue":  [("Crossing", 1.2), ("Stamina", 1), ("Top Speed", 1), ("Dribbling", 0.6), ("Defensive Positioning", -0.3)],
    "RCM_blue": [("Tackling", 1.2), ("Defensive Positioning", 1.2), ("Anticipation", 1), ("Passing", 0.6)],
    "RCM_red":  [("Passing", 1.2), ("Decisions", 1), ("Teamwork", 0.8), ("Control", 0.6)],
    "LCM_blue": [("Stamina", 1), ("Work Rate", 1), ("Off The Ball", 1), ("Finishing", 0.6), ("Long Shots", 0.4)],
    "LM_red":   [("Work Rate", 1.2), ("Stamina", 1), ("Crossing", 0.8), ("Tackling", 0.6)],
    "RM_blue":  [("Top Speed", 1), ("Acceleration", 0.8), ("Crossing", 1.2), ("Dribbling", 1)],
    "RM_red":   [("Top Speed", 1), ("Off The Ball", 1), ("Finishing", 1), ("Dribbling", 0.8)],
    "LM_blue":  [("Finishing", 1), ("Dribbling", 1), ("Long Shots", 0.8), ("Passing", 0.6), ("Crossing", -0.4)],
    "ST1_blue": [("Top Speed", 1), ("Acceleration", 1), ("Off The Ball", 1), ("Work Rate", 0.8)],
    "ST2_blue": [("Finishing", 1.3), ("Off The Ball", 1.1), ("Composure", 1)],
    "ST1_red":  [("Passing", 1.1), ("Control", 1), ("Decisions", 1), ("Strength", 0.6)],
}
TASTE_SD = 2.5           # a manager's leaning towards a role (rating points)


def _role_score(p, rid):
    parts = ROLE_FIT[rid]
    pos = sum(w for _, w in parts if w > 0)
    return sum(float(p.get(a, 50)) * w for a, w in parts) / pos


_BASELINE = {}


def role_baseline(players):
    """How each role's suitability is spread among the players who play that sort of position:
    {role: (mean, sd)} - a man suits a role if he's better at it than most in his position."""
    import statistics as st
    import roles.library as rl
    by_group = {}
    for p in players:
        g = rl.POSITION_GROUP.get(slots_mod.proxy(_spot_of(p["Pos"])))
        by_group.setdefault(g, []).append(p)
    out = {}
    for g, ps in by_group.items():
        for rid, _, _ in rl.MANAGER_ROLES.get(g, []):
            if rid in ROLE_FIT and len(ps) >= 5:
                xs = [_role_score(p, rid) for p in ps]
                out[rid] = (st.mean(xs), st.pstdev(xs) or 1.0)
    _BASELINE.clear()
    _BASELINE.update(out)
    return out


def _spot_of(pos):
    return {"CB": "LCB", "ST": "ST1", "CM": "LCM", "DM": "DM", "AM": "AM", "GK": "GK"}.get(pos, pos)


def ai_roles(club):
    """Pick the role for each of the club's outfield spots (club["roles"][spot])."""
    import roles.library as rl
    roles = club.get("roles")
    if not isinstance(roles, dict):
        roles = club["roles"] = {"base": roles or "blue"}
    lineup = club.get("lineup") or {}
    for slot in clubs_mod.formation_of(club):
        group = rl.POSITION_GROUP.get(slots_mod.proxy(slot))
        options = [rid for rid, _, _ in rl.MANAGER_ROLES.get(group, []) if rid in ROLE_FIT]
        p = clubs_mod.player_by_id(club, lineup.get(slot))
        if len(options) < 2 or p is None:
            continue
        if slots_mod.kind(slot) == "DM":
            options = [r for r in options if r != "LCM_blue"] if slot != "LDM" else options   # (a DM mostly sits)
        if slots_mod.kind(slot) == "AM":
            options = [r for r in options if r != "RCM_blue"]                             # (a No. 10 doesn't hold)
        def score(rid):
            taste = random.Random(f"roletaste:{club['id']}:{club['name']}:{rid}").gauss(0, TASTE_SD)
            mean, sd = _BASELINE.get(rid, (0.0, 1.0))
            return 5.0 * (_role_score(p, rid) - mean) / sd + taste
        roles[slot] = max(options, key=score)
    # a double pivot: not both sitting - the one better suited to getting forward does
    if roles.get("LDM") == "RCM_blue" and roles.get("RDM") == "RCM_blue":
        a, b = (clubs_mod.player_by_id(club, lineup.get(s_)) for s_ in ("LDM", "RDM"))
        if a and b:
            go = "LDM" if _role_score(a, "LCM_blue") - _role_score(a, "RCM_blue") >= \
                _role_score(b, "LCM_blue") - _role_score(b, "RCM_blue") else "RDM"
            roles[go] = "LCM_blue"
    return roles


# ---------------------------------------------------------------------------
# Your formation (the Tactics screen)
# ---------------------------------------------------------------------------
MOVE_COST = 0.3          # rating points: how much a manager minds moving a man a step on the grid
SWAP_IN = 3              # a squad man this much better in a spot than an out-of-position XI man comes in


def remap(club, spots, exclude=()):
    """Your XI put into a new formation: the same men, each in the spot that suits him best
    (moving as few steps as he can).  Where that leaves a man out of position and there's
    someone better for the spot in the squad, he comes in (exclude: injured, suspended).
    Returns the changes: [(spot, in id, out id)]."""
    spots = [s for s in spots if s != "GK"]
    lineup = club.get("lineup") or {}
    field = [(s, pid) for s, pid in lineup.items() if s != "GK" and clubs_mod.player_by_id(club, pid)]

    def cost(old, new, pid):
        r0, l0 = slots_mod.GRID.get(old, (2, 0))
        r1, l1 = slots_mod.GRID[new]
        p = clubs_mod.player_by_id(club, pid)
        return -clubs_mod.overall(p, new) + MOVE_COST * (abs(r0 - r1) + abs(l0 - l1))

    n = len(spots)
    matrix = [[cost(o, sp, pid) for sp in spots] for o, pid in field[:n]]
    matrix += [[0.0] * n for _ in range(n - len(matrix))]          # (a short XI: empty rows)
    new = {}
    for i, j in _assign(matrix).items():
        if i < len(field):
            new[spots[j]] = field[i][1]
    if "GK" in lineup and clubs_mod.player_by_id(club, lineup["GK"]):
        new["GK"] = lineup["GK"]
    taken = set(new.values()) | set(exclude)
    for s in clubs_mod.pick_order(["GK"] + spots):              # anything left empty: the best man for it
        if s not in new:
            cands = [p for p in club["players"] if p["id"] not in taken]
            if cands:
                pick = max(cands, key=lambda p: clubs_mod.overall(p, s))
                new[s] = pick["id"]
                taken.add(pick["id"])
    changes = []
    for s in clubs_mod.pick_order(spots):                        # a man out of position: anyone better?
        here = clubs_mod.player_by_id(club, new[s])
        if clubs_mod.fit(here, s) not in (2, 3):
            continue
        cands = [p for p in club["players"] if p["id"] not in taken]
        if cands:
            pick = max(cands, key=lambda p: clubs_mod.overall(p, s))
            if clubs_mod.overall(pick, s) >= clubs_mod.overall(here, s) + SWAP_IN:
                changes.append((s, pick["id"], here["id"]))
                new[s] = pick["id"]
                taken.add(pick["id"])
    club["formation"] = None if slots_mod.is_legacy(spots) else list(spots)
    club["lineup"] = new
    return changes


def _assign(cost):
    """The cheapest way to give each row its own column (square matrix): {row: column}.
    (The Hungarian method.)"""
    n = len(cost)
    INF = float("inf")
    u, v, p, way = [0.0] * (n + 1), [0.0] * (n + 1), [0] * (n + 1), [0] * (n + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, used = [INF] * (n + 1), [False] * (n + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], INF, 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    return {p[j] - 1: j - 1 for j in range(1, n + 1) if p[j]}


def move(club, old, new):
    """Move the man at spot `old` to the empty spot `new`.  Returns a problem or None."""
    spots = clubs_mod.formation_of(club)
    if old not in spots or new in spots or new not in slots_mod.GRID:
        return "Pick one of your players, then an empty spot."
    after = [new if s == old else s for s in spots]
    problems = slots_mod.check(after)
    if problems:
        return "Keep at least one player in the back row." if "nobody in defence" in problems else problems[0]
    lineup = club["lineup"]
    lineup[new] = lineup.pop(old)
    club["formation"] = None if slots_mod.is_legacy(after) else after
    roles = club.get("roles")
    if isinstance(roles, dict) and old in roles and new not in roles and _same_group(old, new):
        roles[new] = roles[old]                    # (same sort of spot: he keeps his role)
    instr = club.get("instructions") or {}
    if old in instr and new not in instr and _same_group(old, new):
        instr[new] = instr[old]
    return None


def _same_group(a, b):
    import roles.library as rl
    return rl.POSITION_GROUP.get(slots_mod.proxy(a)) == rl.POSITION_GROUP.get(slots_mod.proxy(b))
