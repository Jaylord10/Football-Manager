"""
career/league.py
================
The league: fixtures, results and the table - and saving / loading a career.

  - FIXTURES: every club plays every other club home and away - 38
    matchdays for 20 clubs (18 in the old 10-club league) (the "circle" method, so nobody plays the same
    team twice in a row and home / away alternate fairly).
  - TABLE: 3 points for a win, 1 for a draw; ties are split by goal
    difference, then goals scored, then name.
  - SAVE: the whole career (clubs, squads, fixtures, results) is one JSON
    file in saves/, written after every matchday.
"""

import json
import os
import random

from career import calendar as cal

FIRST_SEASON = 2026       # the first season is 2026/27

SAVE_DIR = "saves"
SAVE_FILE = os.path.join(SAVE_DIR, "career.json")
SAVE_VERSION = 3          # 3: the 20-club world (career/world.py); 2 still loads


def make_fixtures(club_ids, rng=None):
    """Double round-robin: a list of matchdays, each a list of (home, away)."""
    rng = rng or random.Random()
    ids = list(club_ids)
    rng.shuffle(ids)
    if len(ids) % 2:
        ids.append(None)
    n = len(ids)
    first_half = []
    rot = ids[:]
    last = {}                      # club -> "H" / "A" in its previous match
    homes = {c: 0 for c in ids}
    for r in range(n - 1):
        day = []
        for i in range(n // 2):
            a, b = rot[i], rot[n - 1 - i]
            if a is None or b is None:
                continue
            # Whoever was away last time is at home now (so nobody has a long run
            # of home or away games); if they were both, the one with fewer homes
            la, lb = last.get(a), last.get(b)
            if la == "A" and lb != "A":
                home, away = a, b
            elif lb == "A" and la != "A":
                home, away = b, a
            else:
                home, away = (a, b) if homes[a] <= homes[b] else (b, a)
            homes[home] += 1
            last[home], last[away] = "H", "A"
            day.append((home, away))
        first_half.append(day)
        rot = [rot[0]] + [rot[-1]] + rot[1:-1]
    second_half = [[(away, home) for home, away in day] for day in first_half]
    return first_half + second_half


def _div_data(career, div):
    """(clubs, results) of a division (career/divisions.py) - yours if div is None."""
    from career import divisions
    if not divisions.exists(career):
        return career["clubs"], career["results"]
    mine = divisions.my_div(career)
    div = mine if div is None else div
    res = career["results"] if div == mine else career["other"]["results"]
    return divisions.clubs_in(career, div), res


def table(career, div=None):
    """Rows sorted by position: dicts with club, p, w, d, l, gf, ga, gd, pts, form.
    div: "pl" / "d1" (career/divisions.py) - your division if None."""
    clubs, results = _div_data(career, div)
    rows = {c["id"]: {"club": c["id"], "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0, "form": []}
            for c in clubs}
    for md in sorted(results, key=int):
        for r in results[md]:
            h, a, hg, ag = r["home"], r["away"], r["hg"], r["ag"]
            for cid, gf, ga in ((h, hg, ag), (a, ag, hg)):
                row = rows[cid]
                row["p"] += 1
                row["gf"] += gf
                row["ga"] += ga
                if gf > ga:
                    row["w"] += 1; row["pts"] += 3; row["form"].append("W")
                elif gf == ga:
                    row["d"] += 1; row["pts"] += 1; row["form"].append("D")
                else:
                    row["l"] += 1; row["form"].append("L")
    names = {c["id"]: c["name"] for c in clubs}
    out = list(rows.values())
    for r in out:
        r["gd"] = r["gf"] - r["ga"]
        r["form"] = r["form"][-5:]
    out.sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"], names[r["club"]]))
    return out


def top_scorers(career, div=None, n=20):
    """[(goals, apps, player, club)] in a division this season, from the match records."""
    clubs, results = _div_data(career, div)
    ids = {c["id"] for c in clubs}
    goals, apps = {}, {}
    for md in results.values():
        for r in md:
            for g in r.get("goals", []):
                if g.get("own_goal") or g.get("pid") is None:
                    continue
                cid = r["home"] if g.get("team", 0) == 0 else r["away"]
                goals[(cid, g["pid"])] = goals.get((cid, g["pid"]), 0) + 1
            for a in r.get("players", []):
                if a.get("minutes", 0) > 0:
                    cid = r["home"] if a["team"] == 0 else r["away"]
                    apps[(cid, a["id"])] = apps.get((cid, a["id"]), 0) + 1
    from career import clubs as clubs_mod
    out = []
    for (cid, pid), n_ in goals.items():
        if cid not in ids:
            continue
        club = career["clubs"][cid]
        p = clubs_mod.player_by_id(club, pid)
        if p is not None:
            out.append((n_, apps.get((cid, pid), 0), p, club))
    out.sort(key=lambda t: (-t[0], t[1], t[2]["Name"]))
    return out[:n]


def results_of(career, club_id):
    """The results dict ("matchday" -> [...]) of the division this club plays in."""
    from career import divisions
    if divisions.exists(career) and divisions.div_of(career["clubs"][club_id]) != divisions.my_div(career):
        return career["other"]["results"]
    return career.get("results", {})


def position_of(career, club_id):
    """Where a club is in its own division's table."""
    from career import divisions
    div = divisions.div_of(career["clubs"][club_id]) if divisions.exists(career) and 0 <= club_id < len(career["clubs"]) else None
    for i, r in enumerate(table(career, div)):
        if r["club"] == club_id:
            return i + 1
    return None


def club(career, club_id):
    return career["clubs"][club_id]


def new_career(clubs, my_club, seed=None):
    rng = random.Random(seed)
    from career import divisions
    clubs = divisions.add_world(clubs)   # both divisions (career/divisions.py): you can start in either
    mine = divisions.div_of(clubs[my_club])
    career = {
        "version": SAVE_VERSION,
        "season": 1,
        "my_club": my_club,
        "clubs": clubs,
        "fixtures": make_fixtures([c["id"] for c in clubs if divisions.div_of(c) == mine], rng),
        "results": {},          # "matchday number" -> [{home, away, hg, ag, goals: [...]}]
        "matchday": 1,          # the next matchday to play (1-based)
        "history": [],          # past seasons: {season, champion, my_position}
        "pending_results": {},  # "matchday" -> results of other matches already played in the background
    }
    set_calendar(career, FIRST_SEASON)
    from career import training, finance
    training.mark_season_start(career)
    training.reset_days(career)
    finance.init(career)                 # club finances, wages, contracts (career/finance.py)
    from career import contracts, registration, transfers
    contracts.ensure(career)             # free agents to start with
    registration.setup(career, random.Random(2026))     # homegrown players, squad lists
    transfers.ensure_abroad(career)      # players at clubs outside the league
    from career import board, spain
    spain.create(career)                 # the Spanish league, in the background (career/spain.py)
    board.new_season(career)             # the board's objective
    career["positions_v2"] = True        # (the world file has the modern positions)
    from career import shapes
    shapes.ai_review(career)             # every club's formation (career/shapes.py)
    me = clubs[my_club]                  # yours: what the squad's set up for - change it on Tactics
    shapes.set_formation(me, shapes.slots_mod.FORMATIONS[shapes.choose(me, "pl")])
    career["formations_v1"] = True
    career["ai_roles_v1"] = True
    from career import captains
    cap, vice = captains.recommend(me)
    me["captain"], me["vice"] = (cap["id"] if cap else None), (vice["id"] if vice else None)
    career["captains_v1"] = True
    from career import fitness
    fitness.holiday(career)              # back from the summer short of fitness and sharpness
    career["fitness_v1"] = True
    from career import stadium
    stadium.sync(career)                 # (each ground's real capacity - career/stadium.py)
    divisions.start(career)              # the other division's fixtures (career/divisions.py)
    from career import foreign
    foreign.ensure(career)               # Germany's and Italy's leagues (career/foreign.py)
    from career import cups
    cups.create(career)                  # the season's cups (career/cups.py, career/europe.py)
    return career


def set_calendar(career, year):
    """The season's dates (career/calendar.py); today = 1 July: pre-season, the
    summer transfer window open."""
    career["year"] = year
    career["calendar"], career["breaks"] = cal.season(year, len(career["fixtures"]))
    career["date"] = f"{year}-07-01"


def match_date(career, md=None):
    md = career["matchday"] if md is None else md
    cal_ = career.get("calendar") or []
    return cal_[md - 1] if 0 < md <= len(cal_) else None


def advance_to_match(career, stop=False):
    """Continue: every club trains up to the next match day (career/training.py)
    and the clock moves on to it.  stop: halt early on a day something needs you
    (an offer for one of your players) - returns False if it did."""
    d = match_date(career)
    if d and cal.parse(d) > cal.parse(career["date"]):
        from career import training, availability
        halted = training.run_all(career, d, stop=stop)     # every club, in date order
        if halted:
            career["date"] = halted
            return False
        availability.fix_lineups(career, d)
        career["date"] = d
    return True


def next_fixture(career, club_id=None):
    """(matchday, home, away) of the club's next match, or None if the season's over."""
    club_id = career["my_club"] if club_id is None else club_id
    md = career["matchday"]
    if md > len(career["fixtures"]):
        return None
    for home, away in career["fixtures"][md - 1]:
        if club_id in (home, away):
            return md, home, away
    return None


def season_over(career):
    return career["matchday"] > len(career["fixtures"])


def record_matchday(career, results):
    """results: list of {home, away, hg, ag, goals} for the current matchday."""
    career["results"][str(career["matchday"])] = results
    career.get("pending_results", {}).pop(str(career["matchday"]), None)
    career["matchday"] += 1


def new_season(career, seed=None):
    from career import divisions, cups
    divisions.season_end(career)         # the other division's last games (career/divisions.py)
    cups.season_end(career)              # the cups finished, their winners recorded (career/cups.py)
    from career import awards
    awards.season(career)                # the season's awards (career/awards.py)
    t = table(career)
    tables = divisions.tables(career)    # {"pl": [...], "d1": [...]} (just yours in an older one-division world)
    up, down = divisions.movers(career, tables)     # promotion and relegation (play-offs: career/playoffs.py)
    from career import finance, board
    board.season_review(career, t, up, down)        # the board's verdict (and maybe the sack)
    for tt in tables.values():
        finance.season_end(career, tt)   # merit payments, the season's accounts
    from career import crowds
    for tt in tables.values():
        crowds.season_end(career, tt)    # fan bases grow or shrink; this season's crowds filed
    from career import spain
    spain.season_end(career, random.Random(seed))       # Spain's last games, money, champions
    from career import foreign
    foreign.season_end(career, random.Random(seed))     # ...and Germany's and Italy's
    from career import playerhist
    playerhist.season_end(career)                        # every player's season in his career record
    from career import loans
    loans.season_end(career)                             # loans end: back to their clubs (or bought)
    from career import contracts
    contracts.yearly_rises(career)                       # pay rises written into contracts
    career["history"].append({
        "season": career["season"],
        "champion": tables.get("pl", t)[0]["club"],
        "my_position": position_of(career, career["my_club"]),
        "division": divisions.my_div(career),
        "year_end": career.get("year", FIRST_SEASON + career["season"] - 1) + 1,
        "tables": {d: [r["club"] for r in tt] for d, tt in tables.items()},
        "up": up, "down": down,
    })
    if up:
        divisions.promote(career, up, down)          # everyone changes division before the new fixtures
    career["season"] += 1
    career["fixtures"] = make_fixtures([c["id"] for c in divisions.clubs_in(career)], random.Random(seed))
    divisions.new_season(career, seed)   # the other division's fixtures
    career["results"] = {}
    career["matchday"] = 1
    career["pending_results"] = {}
    set_calendar(career, career.get("year", FIRST_SEASON + career["season"] - 2) + 1)
    from career import availability, training, ageing, contracts
    rng = random.Random(seed)
    left = contracts.summer_departures(career, rng)  # out of contract: gone on a free
    ageing.summer(career, rng)                       # older, retirements, youth intake, releases
    career["summer"]["free"] = [{"name": p["Name"], "pos": p["Pos"], "age": p["Age"] + 1,
                                 "rating": clubs_mod_overall(p)} for p in left]
    contracts.new_outside_players(career, rng)       # new free agents from outside the league
    contracts.ai_sign_free_agents(career, rng)       # AI clubs short of players sign some
    spain.summer(career, rng)                        # ...and the same summer in Spain
    from career import foreign
    foreign.summer(career, rng)                      # ...Germany and Italy
    contracts.trim_free_agents(career)
    finance.new_season(career, rng)                  # contracts for the youngsters, budgets
    from career import registration, transfers
    transfers.refresh_abroad(career, rng)            # clubs outside the league
    registration.new_season(career)                  # homegrown status, squad lists
    board.new_season(career)                         # this season's objective
    availability.new_season(career)
    training.new_season(career)
    from career import shapes
    shapes.ai_review(career)                         # pre-season: AI managers settle on a shape
    availability.fix_lineups(career, career["calendar"][0])
    cups.create(career)                              # this season's cups (career/cups.py)


def clubs_mod_overall(p):
    from career import clubs
    return clubs.overall(p)


def save(career, path=SAVE_FILE):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(career, f, indent=1)
    os.replace(tmp, path)          # never leaves a half-written save


def load(path=SAVE_FILE):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        career = json.load(f)
    career["fixtures"] = [[tuple(m) for m in day] for day in career["fixtures"]]
    if career.get("version", 1) < 2:
        # Squads of 11 -> 20 (reserves added), positions and a starting XI
        from career import clubs as clubs_mod
        for c in career["clubs"]:
            clubs_mod.upgrade_club(c)
        career["version"] = 2
    if "calendar" not in career:
        # An older save: give it this season's dates, today = its last match day
        set_calendar(career, FIRST_SEASON + career["season"] - 1)
        if career["matchday"] > 1:
            career["date"] = career["calendar"][min(career["matchday"], len(career["calendar"])) - 2]
    career.setdefault("pending_results", {})
    from career import finance, contracts, registration, transfers
    finance.ensure(career)
    contracts.ensure(career)
    registration.setup(career, random.Random(2026))
    transfers.ensure_abroad(career)
    from career import board, spain
    board.ensure(career)
    spain.ensure(career)                 # (older saves: the Spanish league starts now, caught up to today)
    if not career.get("positions_v2"):   # (older saves: the modern positions - DM, AM, wingers, wing-backs)
        from career import transfers as trf, contracts as con, clubs
        everyone = [c["players"] for c in career["clubs"] + spain.clubs(career)]
        everyone += [con.free_agents(career)["players"], trf.abroad(career)["players"]]
        for ps in everyone:
            for p in ps:
                p["Pos"] = clubs.modern_position(p)
        career["positions_v2"] = True
    if not career.get("formations_v1"):  # (older saves: the AI clubs pick formations; yours stays as it is)
        from career import shapes
        shapes.ai_review(career)
        career["formations_v1"] = True
    if not career.get("ai_roles_v1"):    # (older saves: AI managers pick roles for their players)
        from career import shapes
        shapes.role_baseline([p for c in career["clubs"] + spain.clubs(career) for p in c["players"]])
        for c in career["clubs"] + spain.clubs(career):
            if c["id"] != career.get("my_club"):
                shapes.ai_roles(c)
        career["ai_roles_v1"] = True
    if not career.get("captains_v1"):    # (older saves: every club's armband - yours to the assistant's pick; change it on Tactics)
        from career import captains
        for c in career["clubs"] + spain.clubs(career):
            if c["id"] == career.get("my_club"):
                cap, vice = captains.recommend(c)
                c["captain"], c["vice"] = (cap["id"] if cap else None), (vice["id"] if vice else None)
            else:
                captains.ai_pick(c)
        career["captains_v1"] = True
    if not career.get("fitness_v1"):     # (older saves: fitness and sharpness - career/fitness.py)
        from career import fitness
        first = (career.get("calendar") or [None])[0]
        if not career.get("results") and first and career.get("date", "") < first:
            fitness.holiday(career)      # still pre-season: back from the summer short of it
        career["fitness_v1"] = True
    from career import stadium
    stadium.sync(career)                 # (each ground's real capacity - career/stadium.py)
    from career import divisions
    divisions.ensure(career)             # (older saves: Division 1 arrives - career/divisions.py)
    from career import foreign
    foreign.ensure(career)               # (older saves: Germany and Italy - career/foreign.py)
    from career import cups
    cups.ensure(career)                  # (older saves: the cups start - career/cups.py)
    return career


def has_save(path=SAVE_FILE):
    return os.path.exists(path)
