"""
career/europe.py
================
The continental competitions and the World Club Trophy (the shared cup machinery is in career/cups.py).

THE CONTINENTAL CHAMPIONS' CUP (the Champions League): 16 clubs - the Premier Division's top four, Spain's top
four and eight of the continent's best (from the other leagues).  Four groups of four, home and away (six
Tuesday nights, September to December); the top two go through to two-legged quarter-finals (a group winner
against another group's runners-up) and semi-finals; the final at a neutral ground the Saturday a fortnight
after the league ends.

THE CONTINENTAL SHIELD (the Europa League): the same shape on Thursday nights - the Premier Division's 5th and
6th, the Association Cup and League Cup winners (if they're not in already: the next league place instead),
Spain's 5th-8th and eight more from the continent.

THE WORLD CLUB TROPHY: the Champions' Cup winners against South America's champions, one match on neutral
ground in December.

Groups are drawn from four pots (by strength), keeping clubs from the same country apart where it can.
Prize money: UEFA's 2024/25 figures (Champions League: €18.62m for taking part, €2.1m a win and €0.7m a draw
in the league phase, ~£15.6m for reaching the final and £5.5m more for winning it; Europa League about a
quarter of that), converted at ~0.84.

The continent's clubs live in career["europe"]["clubs"] (ids 300+, the same clubs every season - their squads
are made afresh each summer); South America's champions are 400+.
"""

import datetime as dt
import random

from career import calendar as cal
from career import clubs as clubs_mod

CC, SHIELD, WORLD = "champions_cup", "shield", "world_club"
NAMES = {CC: "The Crown of Europe", SHIELD: "The Europa Trophy", WORLD: "The Intercontinental Cup"}
SHORTS = {CC: "Crown of Europe", SHIELD: "Europa Trophy", WORLD: "Intercontinental Cup"}
BASE, SA_BASE = 300, 400
# The continent's clubs: (name, country, level).  The roll of honour's foreign winners are among them.
# (Germany's and Italy's clubs play in their own leagues now - career/foreign.py)
CONTINENT = [
    ("Sporting Esteira", "Portugal", 77), ("Olympique Varennes", "France", 75), ("Ajaxia Noord", "Netherlands", 72),
    ("Celtic Harbour", "Scotland", 68), ("Dinamo Kravetz", "Ukraine", 67), ("Galatur SK", "Turkey", 69),
    ("FC Lindholm", "Sweden", 63), ("Union Saint-Lys", "Belgium", 67), ("Hellas Korinna", "Greece", 66),
    ("Steaua Ravna", "Romania", 64), ("Racing Clairmont", "France", 69), ("SC Veldhoven", "Netherlands", 68), ("Dinamo Zarkov", "Croatia", 65),
    ("Slavia Brezno", "Czechia", 64), ("Rapid Donaustadt", "Austria", 63), ("FC Basellen", "Switzerland", 63),
    ("Legia Ostrowa", "Poland", 62), ("Red Star Kragova", "Serbia", 64), ("Sport Ribeira", "Portugal", 73),
    ("Olympique Calanques", "France", 71), ("Kempen Vooruit", "Netherlands", 70)]
SOUTH = [("Boca del Plata", "Argentina", 72), ("Estrela da Serra", "Brazil", 73), ("Club Atletico Montevista", "Uruguay", 68),
         ("Nacional de Sierra Alta", "Colombia", 67), ("Gremio Litoral", "Brazil", 71), ("Universitario del Sur", "Peru", 66),
         ("Deportivo Cumbre", "Ecuador", 67), ("Santa Fe del Rio", "Argentina", 69)]
EUR = 0.84
PRIZE = {CC: {"enter": 18.62e6 * EUR, "win": 2.1e6 * EUR, "draw": 0.7e6 * EUR, "Quarter-final": 12.5e6 * EUR,
              "Semi-final": 15e6 * EUR, "Final": 18.5e6 * EUR, "winner": 6.5e6 * EUR},
         SHIELD: {"enter": 4.31e6 * EUR, "win": 0.45e6 * EUR, "draw": 0.15e6 * EUR, "Quarter-final": 3e6 * EUR,
                  "Semi-final": 5e6 * EUR, "Final": 7e6 * EUR, "winner": 6e6 * EUR},
         WORLD: {"winner": 4e6, "loser": 2e6}}
CROWD = 0.95                       # a European night: nearly full


def _nth(y, m, wd, n):
    return cal._nth_weekday(y, m, wd, n)


def _after_league(career, days):
    last = cal.parse((career.get("calendar") or [career["date"]])[-1])
    return (last + dt.timedelta(days=days)).isoformat()


def _dates(career, key, y):
    """(group matchdays, [(round, [dates], neutral)])"""
    if key == CC:
        groups = [_nth(y, 9, 1, 3), _nth(y, 10, 1, 1), _nth(y, 10, 1, 3), _nth(y, 11, 1, 1), _nth(y, 11, 1, 4),
                  _nth(y, 12, 1, 2)]
        ko = [("Quarter-final", [_nth(y + 1, 3, 1, 1), _nth(y + 1, 3, 1, 3)], False),
              ("Semi-final", [_nth(y + 1, 4, 1, 1), _nth(y + 1, 4, 1, 4)], False),
              ("Final", [cal.parse(_after_league(career, 14))], True)]
    else:
        groups = [_nth(y, 9, 3, 3), _nth(y, 10, 3, 2), _nth(y, 10, 3, 4), _nth(y, 11, 3, 1), _nth(y, 11, 3, 4),
                  _nth(y, 12, 3, 2)]
        ko = [("Quarter-final", [_nth(y + 1, 3, 3, 1), _nth(y + 1, 3, 3, 3)], False),
              ("Semi-final", [_nth(y + 1, 4, 3, 2), _nth(y + 1, 4, 3, 5) if _nth(y + 1, 4, 3, 5).month == 4
                              else _nth(y + 1, 4, 3, 4)], False),
              ("Final", [cal.parse(_after_league(career, 11))], True)]
    return [d.isoformat() for d in groups], ko


# ---------------------------------------------------------------------------
# The continent's clubs
# ---------------------------------------------------------------------------
def _eu(career):
    return career.setdefault("europe", {"clubs": {}, "south": {}})


def short_name(nm):
    """'Sporting Esteira' -> 'Esteira', 'Galatur SK' -> 'Galatur', 'Boca del Plata' -> 'Boca'."""
    for sep in (" del ", " de ", " da "):
        if sep in nm:
            return nm.split(sep)[0]
    words = nm.split(" ")
    if words[-1] in ("SK", "FC", "CF"):
        return words[0]
    return words[-1]


def club(career, cid):
    if cid is None or "europe" not in career:
        return None
    e = career["europe"]
    return e["clubs"].get(str(cid)) or e["south"].get(str(cid))


def _squads(career, y):
    """The continent's (and South America's) clubs, their squads made afresh for the season."""
    from career import cups
    e = _eu(career)
    rng = random.Random(f"europe:{y}")
    used = {p["Name"] for c in career["clubs"] for p in c["players"]}
    for i, (nm, country, level) in enumerate(CONTINENT):
        lv = level + rng.uniform(-2.5, 2.5)
        c = cups._make_side(rng, BASE + i, nm, lv, used)
        old = e["clubs"].get(str(BASE + i))
        if old:
            c["colour"] = old["colour"]
        c["country"], c["league"], c["short"] = country, "continent", short_name(nm)
        e["clubs"][str(BASE + i)] = c
    for i, (nm, country, level) in enumerate(SOUTH):
        c = cups._make_side(rng, SA_BASE + i, nm, level + rng.uniform(-2, 2), used)
        c["country"], c["league"], c["short"] = country, "south", short_name(nm)
        e["south"][str(SA_BASE + i)] = c


def country(career, cid):
    if cid is not None and 0 <= cid < len(career["clubs"]):
        return "England"
    from career import spain, foreign
    if spain.exists(career) and spain.ID_BASE <= cid < spain.ID_BASE + 20:
        return "Spain"
    cfg = foreign.league_of_id(cid)
    if cfg is not None:
        return cfg.country
    c = club(career, cid)
    return c.get("country", "?") if c else "?"


def find(career, nm):
    """A club id by name (the roll of honour's names: ours, Spain's, the continent's)."""
    from career import spain, foreign
    others = [c for cfg in foreign.LEAGUES for c in foreign.clubs(career, cfg)]
    for c in career["clubs"] + spain.clubs(career) + others + list(_eu(career)["clubs"].values()) + list(_eu(career)["south"].values()):
        if c["name"] == nm:
            return c["id"]
    return None


# ---------------------------------------------------------------------------
# Who's in
# ---------------------------------------------------------------------------
def _english(career, y):
    """(Champions' Cup four, Shield four) - from last season's table and cups (or, the first season, the
    roll of honour and the clubs' size)."""
    from career import divisions, cups
    hist = (career.get("history") or [])
    if hist and hist[-1].get("tables", {}).get("pl"):
        table = [cid for cid in hist[-1]["tables"]["pl"]]
        # (promoted / relegated since: only clubs now in the Premier Division... real rules keep the places
        # earned - the relegated keep theirs; we keep it simple and use last season's order)
    else:
        from career import clubinfo
        r = clubinfo.roll()["roll"].get("league", {}).get(str(y), [])
        top = [find(career, n) for n in r if find(career, n) is not None]
        rest = [c["id"] for c in sorted(divisions.clubs_in(career, "pl"), key=lambda c: -c.get("strength", 0))
                if c["id"] not in top]
        table = top + rest
    cc = table[:4]
    shield = table[4:6]
    ch = (career.get("cup_history") or [])
    winners = []
    if ch:
        winners = [ch[-1].get(cups.ASSOC, [None])[0], ch[-1].get(cups.LEAGUE_CUP, [None])[0]]
    else:
        from career import clubinfo
        for key in (cups.ASSOC, cups.LEAGUE_CUP):
            w = clubinfo.roll()["roll"].get(key, {}).get(str(y), [None])[0]
            winners.append(find(career, w) if w else None)
    k = 6
    for w in winners:
        if w is not None and w not in cc and w not in shield and 0 <= w < len(career["clubs"]):
            shield.append(w)
        else:
            while k < len(table) and (table[k] in cc or table[k] in shield):
                k += 1
            if k < len(table):
                shield.append(table[k])
                k += 1
    return cc, shield[:4]


def _spanish(career):
    from career import spain
    if not spain.exists(career):
        return [], []
    h = career["spain"].get("history") or []
    if h and h[-1].get("table"):
        t = h[-1]["table"]
    else:
        t = [c["id"] for c in sorted(spain.clubs(career), key=lambda c: -c.get("strength", 0))]
    return t[:4], t[4:8]


def _foreign_leagues(career):
    """(Champions' Cup places, Shield places) from Germany and Italy: their top three, then 4th-6th."""
    from career import foreign
    cc, sh = [], []
    for cfg in foreign.LEAGUES:
        if not foreign.exists(career, cfg):
            continue
        h = career["leagues"][cfg.key].get("history") or []
        t = h[-1]["table"] if h and h[-1].get("table") else \
            [c["id"] for c in sorted(foreign.clubs(career, cfg), key=lambda c: -c.get("strength", 0))]
        cc += t[:3]
        sh += t[3:6]
    return cc, sh


def _continent(career, rng, n_cc, n_sh):
    """The rest of the continent: the strongest (with a little luck) to the Champions' Cup, the next to the Shield."""
    e = _eu(career)
    ranked = sorted(e["clubs"].values(), key=lambda c: -(c["strength"] + rng.uniform(-4, 4)))
    return [c["id"] for c in ranked[:n_cc]], [c["id"] for c in ranked[n_cc:n_cc + n_sh]]


# ---------------------------------------------------------------------------
# Setting up (called from career/cups.py create)
# ---------------------------------------------------------------------------
def create(career):
    from career import cups
    y = career.get("year", 2026)
    rng = random.Random(f"europe-draw:{y}")
    _squads(career, y)
    cu = cups.state(career)
    eng_cc, eng_sh = _english(career, y)
    es_cc, es_sh = _spanish(career)
    fl_cc, fl_sh = _foreign_leagues(career)
    es_cc, es_sh = es_cc + fl_cc, es_sh + fl_sh
    for_cc, for_sh = _continent(career, rng, 16 - len(eng_cc) - len(es_cc), 16 - len(eng_sh) - len(es_sh))
    for key, entrants in ((CC, eng_cc + es_cc + for_cc), (SHIELD, eng_sh + es_sh + for_sh)):
        groups_d, ko = _dates(career, key, y)
        comp = cups._comp(key, NAMES[key], [(n, [cal.parse(d) if isinstance(d, str) else d for d in ds], neu, None)
                                            for n, ds, neu in ko])
        comp["kind"], comp["short"] = "groups", SHORTS[key]
        comp["group_dates"] = groups_d
        comp["groups"] = _draw_groups(career, entrants, rng)
        _group_fixtures(comp)
        cu["comps"][key] = comp
        for cid in entrants:
            _pay(career, cid, PRIZE[key]["enter"])
            if cid == career["my_club"]:
                from career import transfers as trf
                g = next(k for k, v in comp["groups"].items() if cid in v)
                others = ", ".join(cups.name(career, x) for x in comp["groups"][g] if x != cid)
                trf._message(career, "news", f"{NAMES[key]}: you're in Group {g} with {others}. "
                                             f"First game {cal.fmt(groups_d[0], False)}.")
    _world_club(career, y)


def _draw_groups(career, entrants, rng):
    """Four pots by strength; one from each pot per group, same countries apart where possible."""
    from career import cups, spain
    def strength(cid):
        c = cups.club(career, cid)
        xi = clubs_mod.best_lineup(c)
        return spain.xi_rating(c, xi)
    ranked = sorted(entrants, key=lambda cid: -strength(cid))
    pots = [ranked[i * 4:(i + 1) * 4] for i in range(4)]
    for attempt in range(200):
        groups = {g: [] for g in "ABCD"}
        ok = True
        for pot in pots:
            pot = pot[:]
            rng.shuffle(pot)
            for g in "ABCD":
                pick = next((x for x in pot if all(country(career, x) != country(career, y) for y in groups[g])), None)
                if pick is None:
                    if attempt < 199:
                        ok = False
                        break
                    pick = pot[0]
                groups[g].append(pick)
                pot.remove(pick)
            if not ok:
                break
        if ok:
            return groups
    return groups


def _group_fixtures(comp):
    """Each group: home and away, six matchdays (the circle method: 1v4 2v3, 1v3 4v2, 1v2 3v4, then reversed)."""
    pattern = [((0, 3), (1, 2)), ((2, 0), (3, 1)), ((0, 1), (2, 3)), ((3, 0), (2, 1)), ((0, 2), (1, 3)), ((1, 0), (3, 2))]
    for g, ids in comp["groups"].items():
        for md, pairs in enumerate(pattern):
            for h, a in pairs:
                m = {"id": f"{comp['key']}:{comp['next_id']}", "comp": comp["key"], "round": None, "tie": None,
                     "leg": None, "group": g, "gmd": md + 1, "date": comp["group_dates"][md],
                     "home": ids[h], "away": ids[a], "neutral": False, "result": None}
                comp["next_id"] += 1
                comp["matches"].append(m)


def _world_club(career, y):
    """December: last season's Champions' Cup winners v South America's champions."""
    from career import cups, clubinfo
    cu = cups.state(career)
    ch = career.get("cup_history") or []
    winner = None
    if ch and ch[-1].get(CC):
        winner = ch[-1][CC][0]
    if winner is None:
        nm = clubinfo.roll()["roll"].get(CC, {}).get(str(y), [None])[0]
        winner = find(career, nm) if nm else None
    if winner is None:
        return
    rng = random.Random(f"south:{y}")
    sa = rng.choice(list(_eu(career)["south"].values()))["id"]
    d = _nth(y, 12, 3, 3).isoformat()
    comp = cups._comp(WORLD, NAMES[WORLD], [("Final", [cal.parse(d)], True, None)])
    comp["short"] = SHORTS[WORLD]
    comp["year_label"] = y                        # (played in December: the roll counts it in that year)
    comp["rounds"][0]["entrants"] = [winner, sa]
    cu["comps"][WORLD] = comp
    cups.draw_rounds(career, comp, career.get("date"))
    if career["my_club"] == winner:
        from career import transfers as trf
        trf._message(career, "news", f"The Intercontinental Cup: as champions of Europe you'll play "
                                     f"{cups.name(career, sa)}, South America's champions, on {cal.fmt(d, False)}.")


def comps(career):
    return []           # (the continental cups live in career["cups"]["comps"] with the English ones)


def _pay(career, cid, amount):
    from career import cups, finance as fin
    c = cups.club(career, cid)
    if c is not None and "finance" in c and amount:
        fin._book(c, "prize", round(amount))


# ---------------------------------------------------------------------------
# Group stage
# ---------------------------------------------------------------------------
def standings(career, comp, g):
    """[{club, p, w, d, l, gf, ga, gd, pts}] for a group, best first."""
    from career import cups
    rows = {cid: {"club": cid, "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0} for cid in comp["groups"][g]}
    for m in comp["matches"]:
        if m.get("group") != g or m["result"] is None:
            continue
        r = m["result"]
        for cid, gf, ga in ((m["home"], r["hg"], r["ag"]), (m["away"], r["ag"], r["hg"])):
            row = rows[cid]
            row["p"] += 1; row["gf"] += gf; row["ga"] += ga
            if gf > ga:
                row["w"] += 1; row["pts"] += 3
            elif gf == ga:
                row["d"] += 1; row["pts"] += 1
            else:
                row["l"] += 1
    out = list(rows.values())
    for r in out:
        r["gd"] = r["gf"] - r["ga"]
    out.sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"], cups.name(career, r["club"])))
    return out


def record_group(career, comp, m, r):
    """A group match: the points' money; then, once every group's done, the quarter-final draw."""
    key = comp["key"]
    if r["hg"] > r["ag"]:
        _pay(career, m["home"], PRIZE[key]["win"])
    elif r["hg"] < r["ag"]:
        _pay(career, m["away"], PRIZE[key]["win"])
    else:
        _pay(career, m["home"], PRIZE[key]["draw"])
        _pay(career, m["away"], PRIZE[key]["draw"])
    groups_done(career, comp)


def groups_done(career, comp):
    if comp["rounds"][0]["drawn"]:
        return
    if any(m["result"] is None for m in comp["matches"] if m.get("group") is not None):
        return
    from career import cups, transfers as trf
    tables = {g: standings(career, comp, g) for g in comp["groups"]}
    pairs = [(tables["A"][0], tables["B"][1]), (tables["B"][0], tables["A"][1]),
             (tables["C"][0], tables["D"][1]), (tables["D"][0], tables["C"][1])]
    rd = comp["rounds"][0]
    for first, second in pairs:
        a, b = first["club"], second["club"]                      # (the group winners at home in the second leg)
        tie = {"a": a, "b": b, "matches": [], "winner": None, "how": None}
        rd["ties"].append(tie)
        for leg, d in enumerate(rd["dates"], start=1):
            home, away = (b, a) if leg == 1 else (a, b)
            mm = {"id": f"{comp['key']}:{comp['next_id']}", "comp": comp["key"], "round": 0,
                  "tie": len(rd["ties"]) - 1, "leg": leg, "date": d, "home": home, "away": away,
                  "neutral": False, "result": None}
            comp["next_id"] += 1
            comp["matches"].append(mm)
            tie["matches"].append(mm["id"])
            cups.space(career, mm)
    rd["drawn"] = True
    for first, second in pairs:
        for row in (first, second):
            _pay(career, row["club"], PRIZE[comp["key"]]["Quarter-final"])
    me = career["my_club"]
    for g, t in tables.items():
        ids = [r["club"] for r in t]
        if me in ids:
            pos = ids.index(me) + 1
            if pos <= 2:
                opp = next(x for p in pairs for x in (p[0]["club"], p[1]["club"]) if me in (p[0]["club"], p[1]["club"]) and x != me)
                trf._message(career, "news", f"{comp['name']}: through to the quarter-finals "
                                             f"({'group winners' if pos == 1 else 'second in the group'}) - "
                                             f"{cups.name(career, opp)} next, in March.")
            else:
                trf._message(career, "news", f"{comp['name']}: out at the group stage ({pos}{'rd' if pos == 3 else 'th'} in Group {g}).")


def my_status(career, comp):
    me = career["my_club"]
    for g, ids in comp.get("groups", {}).items():
        if me in ids:
            if comp["rounds"][0]["drawn"]:
                if not any(me in (t["a"], t["b"]) for t in comp["rounds"][0]["ties"]):
                    return "Out at the group stage"
            else:
                t = standings(career, comp, g)
                pos = [r["club"] for r in t].index(me) + 1
                return f"Group {g}: {pos}{['st', 'nd', 'rd', 'th'][pos - 1]}"
    return "Not in it"


def group_stages(career, comp):
    """For the cups screen: one page per group."""
    from career import cups
    out = []
    for g in comp.get("groups", {}):
        def lines(g=g):
            rows = []
            for i, r in enumerate(standings(career, comp, g), start=1):
                rows.append((f"{i}.  {cups.name(career, r['club'])} ({country(career, r['club'])})   "
                             f"P{r['p']}  W{r['w']}  D{r['d']}  L{r['l']}  {r['gf']}-{r['ga']}  {r['pts']} pts",
                             r["club"] == career["my_club"]))
            rows.append(("", False))
            for m in sorted((x for x in comp["matches"] if x.get("group") == g), key=lambda x: x["date"]):
                res = m["result"]
                txt = (f"{cal.fmt(m['date'], False)}   {cups.name(career, m['home'], True)} "
                       + (f"{res['hg']}-{res['ag']}" if res else "v") + f" {cups.name(career, m['away'], True)}")
                rows.append((txt, career["my_club"] in (m["home"], m["away"])))
            return rows
        out.append((f"Group {g}", lines))
    return out


def day(career, iso):
    """Every day: the knockout draws once the groups are done (career/cups.py plays the matches)."""
    from career import cups
    cu = cups.state(career)
    if not cu:
        return
    for key in (CC, SHIELD):
        comp = cu["comps"].get(key)
        if comp:
            groups_done(career, comp)
            if comp["rounds"][0]["drawn"]:
                cups.draw_rounds(career, comp, iso)


def final_prizes(career, comp, rd, winner, loser):
    """Prize money for reaching a knockout round (both sides) and winning the final."""
    key = comp["key"]
    if key == WORLD:
        _pay(career, winner, PRIZE[WORLD]["winner"])
        _pay(career, loser, PRIZE[WORLD]["loser"])
        return
    nxt = {"Quarter-final": "Semi-final", "Semi-final": "Final"}.get(rd["name"])
    if nxt:
        _pay(career, winner, PRIZE[key][nxt])
    if rd["name"] == "Final":
        _pay(career, winner, PRIZE[key]["winner"])
