"""
career/divisions.py
===================
Two English divisions: the PREMIER DIVISION (20 clubs) and DIVISION 1 below it (20 clubs).

  - Division 1's clubs are made exactly like the Premier Division's (career/clubs.py), the
    same in every career, kept in data/world/d1_clubs.csv and d1_players.csv (edit them like
    the Premier Division's files).  Their ids are 20-39.
  - EVERY English club lives in career["clubs"] (index = id, never changes), tagged with its
    division: club["league"] = "pl" (Premier Division) or "d1" (Division 1).  The money code
    (career/finance.py) already reads that tag.
  - YOUR division plays as before: career["fixtures"] / ["results"] / ["matchday"], the real
    match engine.  THE OTHER division plays on the same days with quick results (the Spanish
    league's model, career/spain.py), in career["other"]: {div, fixtures, results, matchday}.
  - Both divisions have 20 clubs and 38 matchdays on the same calendar.

Promotion, relegation and the play-offs come next (stage 2).
"""

import os
import random

from career import clubs as clubs_mod
from career import world as world_mod

NAMES = {"pl": "Premier Division", "d1": "Division 1"}
SHORT = {"pl": "Premier", "d1": "Div 1"}
ORDER = ("pl", "d1")                      # top first
ID_BASE = 20
WORLD_SEED = 1888
CLUBS_FILE = os.path.join(world_mod.WORLD_DIR, "d1_clubs.csv")
PLAYERS_FILE = os.path.join(world_mod.WORLD_DIR, "d1_players.csv")

# Division 1's levels, best first: a couple of big clubs fallen on hard times about as good as
# the Premier Division's bottom four, then a long, even middle (the Championship is famously close)
STRENGTHS = (58, 56, 55, 54, 53, 52, 51, 50, 50, 49, 48, 47, 47, 46, 45, 45, 44, 43, 42, 41)
CLUBS = [
    ("Hexley Town", "Hexley", (30, 90, 170)),
    ("Wrexford City", "Wrexford", (200, 30, 40)),
    ("Saltmarsh Athletic", "Saltmarsh", (235, 235, 235)),
    ("Kelbridge Albion", "Kelbridge", (0, 110, 70)),
    ("Dunholme Wanderers", "Dunholme", (230, 120, 20)),
    ("Ravensworth United", "Ravensworth", (120, 20, 30)),
    ("Pitchford Forest", "Pitchford", (20, 100, 40)),
    ("Coldharbour Town", "Coldharbour", (60, 60, 140)),
    ("Ellesmoor County", "Ellesmoor", (170, 200, 230)),
    ("Grimsdale Rovers", "Grimsdale", (40, 40, 80)),
    ("Burnleigh Athletic", "Burnleigh", (230, 200, 20)),
    ("Stockbury City", "Stockbury", (140, 30, 100)),
    ("Morwick United", "Morwick", (220, 60, 30)),
    ("Ottercliffe Town", "Ottercliffe", (0, 140, 160)),
    ("Quarrington Albion", "Quarrington", (100, 160, 60)),
    ("Bexford City", "Bexford", (25, 50, 120)),
    ("Lanfield United", "Lanfield", (245, 245, 245)),
    ("Ironmoor Athletic", "Ironmoor", (160, 60, 40)),
    ("Kestwick Harriers", "Kestwick", (70, 170, 120)),
    ("Daleford Town", "Daleford", (200, 160, 60)),
]


# ---------------------------------------------------------------------------
# The world: built once, kept in the files
# ---------------------------------------------------------------------------
def build_world(seed=WORLD_SEED):
    rng = random.Random(seed)
    used = set()
    if os.path.exists(world_mod.PLAYERS_FILE):            # (no name already in the Premier Division)
        used = {p["Name"] for c in world_mod.load() for p in c["players"]}
    names = list(CLUBS)
    rng.shuffle(names)
    out = []
    for i, ((name, short, colour), strength) in enumerate(zip(names, STRENGTHS)):
        defence, build_up = clubs_mod.style_for_rank(i, len(STRENGTHS))
        c = {"id": ID_BASE + i, "name": name, "short": short, "colour": list(colour), "strength": strength,
             "roles": {"base": rng.choice(["blue", "red"])}, "tactics": {"defence": defence, "build_up": build_up},
             "instructions": {}, "players": clubs_mod._squad_25(rng, strength, used)}
        out.append(c)
    world_mod.save(out, CLUBS_FILE, PLAYERS_FILE)
    return out


def load_world():
    return world_mod.load(CLUBS_FILE, PLAYERS_FILE, build_fn=build_world)


# ---------------------------------------------------------------------------
# Who's where
# ---------------------------------------------------------------------------
def div_of(club):
    return club.get("league", "pl")


def name(div):
    return NAMES.get(div, div)


def my_div(career):
    return div_of(career["clubs"][career["my_club"]]) if career.get("my_club") is not None else "pl"


def clubs_in(career, div=None):
    """The clubs in a division (yours if div is None)."""
    div = my_div(career) if div is None else div
    return [c for c in career["clubs"] if div_of(c) == div]


def other_div(career):
    return "d1" if my_div(career) == "pl" else "pl"


def exists(career):
    return len(career.get("clubs", [])) > ID_BASE and "other" in career


# ---------------------------------------------------------------------------
# Setting up (a new career, or an older save)
# ---------------------------------------------------------------------------
def add_world(clubs):
    """A new career: the Premier Division's clubs (tagged) followed by Division 1's (ids 20-39)."""
    for c in clubs:
        c.setdefault("league", "pl")
    if len(clubs) != ID_BASE:
        return clubs
    d1 = load_world()
    for c in d1:
        c["league"] = "d1"
        for p in c["players"]:
            p["condition"] = 1.0
    return clubs + d1


def start(career):
    """A new career: the other division's fixtures (both divisions start on the same day)."""
    from career import league
    rng = random.Random(WORLD_SEED + career.get("year", 2026))
    other = other_div(career)
    career["other"] = {"div": other, "matchday": 1, "results": {},
                       "fixtures": league.make_fixtures([c["id"] for c in clubs_in(career, other)], rng)}


def create(career):
    """Division 1 joins the career: its 20 clubs (ids 20-39) and the other division's fixtures.
    A new career starts in July; an older save part-way through a season catches up (quick results)."""
    from career import finance, registration, shapes, captains, fitness, league, stadium
    for c in career["clubs"]:
        c.setdefault("league", "pl")
    if len(career["clubs"]) != ID_BASE:
        return                                            # (already there)
    world = load_world()
    for c in world:
        c["league"] = "d1"
        for p in c["players"]:
            p["condition"] = 1.0
        career["clubs"].append(c)
    finance.init(career, seed=WORLD_SEED, only=world)
    registration.setup(career, random.Random(WORLD_SEED))
    stadium.sync(career)
    rng = random.Random(WORLD_SEED + career.get("year", 2026))
    other = other_div(career)
    career["other"] = {"div": other, "matchday": 1, "results": {},
                       "fixtures": league.make_fixtures([c["id"] for c in clubs_in(career, other)], rng)}
    pre = not career.get("results") and career.get("date", "") < (career.get("calendar") or ["9999"])[0]
    for c in world:
        shapes._review(c, "d1")
        c["lineup"] = clubs_mod.best_lineup(c)
        shapes.ai_roles(c)
        captains.ai_pick(c)
        if pre:
            fr = random.Random(f"holiday:{career.get('year')}:{c['id']}")
            for p in c["players"]:
                p["fitness"] = round(max(0.62, min(0.92, fr.gauss(*fitness.HOLIDAY))), 3)
                p["sharp"] = round(max(0.25, min(0.65, fr.gauss(*fitness.HOLIDAY_SHARP))), 3)
    catch_up(career)


def ensure(career):
    """Older saves (one division): Division 1 arrives."""
    if "other" not in career or len(career["clubs"]) == ID_BASE:
        create(career)
    for c in career["clubs"]:
        c.setdefault("league", "pl" if c["id"] < ID_BASE else "d1")


def catch_up(career):
    """The other division plays every matchday ours already has."""
    o = career.get("other")
    if not o:
        return
    cal_ = career.get("calendar") or []
    rng = random.Random(f"{career.get('year')}:{o['matchday']}:other")
    from career import training
    while o["matchday"] < career.get("matchday", 1) and o["matchday"] <= min(len(o["fixtures"]), len(cal_)):
        training.after_match(career, play_matchday(career, cal_[o["matchday"] - 1], rng))


# ---------------------------------------------------------------------------
# The other division's matches: quick results (career/spain.py's model - it fits the
# Championship too: 200 seasons, 2.56 goals a game, home 45% / draw 25%, champions ~79 points,
# 10th ~53, bottom ~27 - the Championship 2023/24 scaled to 38 games: 80 / 53 / 22)
# ---------------------------------------------------------------------------
def play_matchday(career, date, rng):
    """The other division's next matchday: quick results.  Returns the results (each with a "players"
    list like the match engine's, so fitness, loans and the rest treat them the same)."""
    from career import spain, finance, crowds, availability as av
    import datetime as dt
    from career import calendar as cal
    o = career["other"]
    md = o["matchday"]
    results = []
    for h, a in o["fixtures"][md - 1]:
        H, A = career["clubs"][h], career["clubs"][a]
        hxi, axi = spain.pick_xi(H, date, a), spain.pick_xi(A, date, h)
        H["lineup"], A["lineup"] = hxi, axi
        hg, ag = spain.quick_result(rng, H, A, hxi, axi)
        goals, players = [], []
        for side, c, xi, n in ((0, H, hxi, hg), (1, A, axi, ag)):
            for _ in range(n):
                p = spain._scorer(rng, c, xi)
                goals.append({"team": side, "name": p["Name"], "pid": p["id"], "minute": rng.randint(1, 90)})
            for pid in xi.values():
                p = clubs_mod.player_by_id(c, pid)
                players.append({"team": side, "id": pid, "minutes": 90, "start": 1, "yellow": 0, "red": None,
                                "stamina": round(rng.uniform(0.62, 0.8), 3)})
                if rng.random() < spain.MATCH_INJURY * av._age_factor(p):
                    name, days = av.roll_injury(rng)
                    p["injury"] = {"name": name, "since": date, "cause": "match",
                                   "until": (cal.parse(date) + dt.timedelta(days=days)).isoformat()}
        goals.sort(key=lambda g: g["minute"])
        r = {"home": h, "away": a, "hg": hg, "ag": ag, "goals": goals, "players": players, "quick": True}
        r["att"] = crowds.home_game(career, H, A, date)
        finance.home_game(career, H, r["att"])
        results.append(r)
    o["results"][str(md)] = results
    o["matchday"] = md + 1
    return results


def after_matchday(career, md, date, rng):
    """Called with our matchday: the other division plays its games of the same round."""
    o = career.get("other")
    if not o or o["matchday"] != md or md > len(o["fixtures"]):
        return []
    return play_matchday(career, date, rng)


def table(career, div=None):
    from career import league
    return league.table(career, div)


# ---------------------------------------------------------------------------
# The end of a season
# ---------------------------------------------------------------------------
def season_end(career):
    """The other division's games still to play (if any)."""
    from career import training
    o = career.get("other")
    if not o:
        return
    cal_ = career.get("calendar") or []
    rng = random.Random(f"{career.get('year')}:end:other")
    while o["matchday"] <= len(o["fixtures"]):
        training.after_match(career, play_matchday(career, cal_[min(o["matchday"], len(cal_)) - 1], rng))


def tables(career):
    """Every division's final table, top division first."""
    from career import league
    if not exists(career):
        return {my_div(career): league.table(career)}
    return {d: league.table(career, d) for d in ORDER}


def new_season(career, seed=None):
    from career import league
    if not exists(career):
        return
    o = career["other"]
    o["div"] = other_div(career)
    o["fixtures"] = league.make_fixtures([c["id"] for c in clubs_in(career, o["div"])],
                                         random.Random(f"{seed}:{career.get('season')}:other"))
    o["results"] = {}
    o["matchday"] = 1


def follow(career):
    """Your club is now in the other division (a new job; promotion / relegation swap the divisions
    in the summer instead): its fixtures and results become career["fixtures"] / ["results"], played
    with the match engine; yours become the other division's (quick results from now on)."""
    o = career.get("other")
    if not o or o["div"] != my_div(career):
        return False
    mine = {"div": other_div(career), "fixtures": career["fixtures"], "results": career["results"],
            "matchday": career["matchday"]}
    career["fixtures"], career["results"], career["matchday"] = o["fixtures"], o["results"], o["matchday"]
    career["other"] = mine
    career["pending_results"] = {}               # (background matches of the old division: not needed)
    return True


# ---------------------------------------------------------------------------
# Promotion and relegation (in the summer - career/league.py new_season)
# ---------------------------------------------------------------------------
DOWN = 3                     # the Premier Division's bottom three go down
UP = 2                       # Division 1's top two go up automatically...
                             # ...and the play-off winners (3rd-6th - career/playoffs.py) make three


def movers(career, tables):
    """(up, down): the club ids changing division this summer."""
    if "pl" not in tables or "d1" not in tables:
        return [], []
    from career import playoffs
    playoffs.finish_all(career)                       # (anything still to play: quick results)
    down = [r["club"] for r in tables["pl"][-DOWN:]]
    up = [r["club"] for r in tables["d1"][:UP]]
    w = playoffs.promoted_via_playoffs(career)
    if w is None:                                     # (no play-offs: an older save mid-way) 3rd goes up
        w = tables["d1"][UP]["club"]
    up.append(w)
    return up, down


def promote(career, up, down):
    """Swap the clubs over; the news; your fixtures follow you."""
    from career import transfers as trf
    for cid in up:
        career["clubs"][cid]["league"] = "pl"
    for cid in down:
        career["clubs"][cid]["league"] = "d1"
    nm = lambda cid: career["clubs"][cid]["name"]
    career["movements"] = career.get("movements", [])[-30:] + [{"year": career.get("year"), "up": up, "down": down}]
    trf._message(career, "news", f"Promoted to the Premier Division: {', '.join(nm(c) for c in up[:2])} "
                                 f"and play-off winners {nm(up[2])}.  Relegated to Division 1: "
                                 f"{', '.join(nm(c) for c in down)}.")
    me = career["my_club"]
    if me in up:
        trf._message(career, "board", "Promotion! The board are delighted - welcome to the Premier Division. "
                                      "The money's bigger, and so is everyone else.")
    elif me in down:
        trf._message(career, "board", "Relegation. The board are bitterly disappointed - Division 1 next season, "
                                      "and the money that goes with it. They want us back up as soon as we can.")
