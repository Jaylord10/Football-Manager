"""
career/playerhist.py
====================
Every player's career record, season by season - like the "career" table on a real player's page:

    2026-27  Northwick (loan)   24 games  7 goals  (cups: 2)   League champions
    2027-28  Ashvale            31 games 12 goals  (cups: 4)   Association Cup

The record starts with the first season of the career (the world has no stats from before).  A line is
written:
  - at the end of the season, for the club he's at (career/league.py new_season - after the last games
    in every league, before the loans end and the summer resets the counts);
  - when he leaves a club in mid-season (a transfer or a loan, either way) - his games for them so far.

Games and goals are league games (both English divisions, from the results; Spain / Germany / Italy from
their quick-result counts); cup goals are every cup and continental cup.  Lines are kept on the player
(p["hist"]) in a compact form:
    {"y": "2026-27", "c": "Northwick", "cid": 0, "a": 24, "g": 7, "cg": 2, "h": ["League champions"], "loan": 1}
"""

MAX_LINES = 25


def _label(career):
    y = career.get("year", 2026)
    return f"{y}-{str(y + 1)[-2:]}"


def _short(career, cid):
    from career import cups
    c = cups.club(career, cid)
    return (c.get("short") or c["name"]) if c else "?"


def _english(career, cid):
    return 0 <= cid < len(career.get("clubs", []))


def _league_rows(career, cid):
    """[(date, pid played, {pid: goals})] for the club's league games this season (English clubs)."""
    from career import league
    res = league.results_of(career, cid)
    out = []
    for md, day in res.items():
        d = league.match_date(career, int(md))
        for r in day:
            if cid not in (r["home"], r["away"]):
                continue
            side = 0 if r["home"] == cid else 1
            played = {a["id"] for a in r.get("players", []) if a["team"] == side and a.get("minutes", 0) > 0}
            goals = {}
            for g in r.get("goals", []):
                if g.get("team", 0) == side and not g.get("own_goal") and g.get("pid") is not None:
                    goals[g["pid"]] = goals.get(g["pid"], 0) + 1
            out.append((d or "", played, goals))
    return out


def _cup_goals(career):
    """{(club id, pid): [(date, goals)]} for every cup and continental cup match this season."""
    from career import cups
    out = {}
    for m in cups.all_matches(career):
        res = m.get("result")
        if not res:
            continue
        for g in res.get("goals", []):
            if g.get("pid") is None:
                continue
            cid = m["home"] if g.get("team", 0) == 0 else m["away"]
            out.setdefault((cid, g["pid"]), []).append(m["date"])
    return out


def _count(career, cid, p, rows, cupg, until=None):
    """(games, goals, cup goals) for this player at this club since he joined (until: up to that date)."""
    since = p.get("hist_since") or ""
    ok = lambda d: d >= since and (until is None or d <= until)
    if _english(career, cid):
        a = g = 0
        for d, played, goals in rows:
            if not ok(d):
                continue
            a += p["id"] in played
            g += goals.get(p["id"], 0)
    else:
        took = p.get("hist_taken") or [0, 0]
        a, g = max(0, p.get("lg_apps", 0) - took[0]), max(0, p.get("lg_goals", 0) - took[1])
    cg = sum(1 for d in cupg.get((cid, p["id"]), []) if ok(d))
    return a, g, cg


def _add(career, p, cid, a, g, cg, honours=()):
    if not (a or g or cg or honours):
        return
    line = {"y": _label(career), "c": _short(career, cid), "cid": cid, "a": a, "g": g, "cg": cg}
    if honours:
        line["h"] = list(honours)
    if p.get("loan"):
        line["loan"] = 1
    hist = p.setdefault("hist", [])
    hist.append(line)
    del hist[:-MAX_LINES]


def leaving(career, cid, p):
    """He's leaving this club in mid-season (call before his id changes): his games for them so far."""
    if career.get("hist_closed") == career.get("year") or cid is None or cid < 0:
        return
    try:
        rows = _league_rows(career, cid) if _english(career, cid) else []
        a, g, cg = _count(career, cid, p, rows, _cup_goals(career), until=career.get("date"))
        _add(career, p, cid, a, g, cg)
    except Exception:                                   # (a record is never worth a crash)
        pass
    if not _english(career, cid):
        p["hist_taken"] = [p.get("lg_apps", 0), p.get("lg_goals", 0)]
    p["hist_since"] = career.get("date")


def _honours(career):
    """{club id: [what they won this season]}."""
    from career import divisions, spain, foreign
    out = {}
    tabs = divisions.tables(career) if divisions.exists(career) else {}
    if tabs.get("pl"):
        out.setdefault(tabs["pl"][0]["club"], []).append("League champions")
    if tabs.get("d1"):
        out.setdefault(tabs["d1"][0]["club"], []).append("Division 1 champions")
    try:
        t = spain.table(career)
        if t:
            out.setdefault(t[0]["club"], []).append(f"{spain.NAME} champions")
        for cfg in foreign.LEAGUES:
            if foreign.exists(career, cfg):
                t = foreign.table(career, cfg)
                if t:
                    out.setdefault(t[0]["club"], []).append(f"{cfg.name} champions")
    except Exception:
        pass
    from career import cups
    for comp in cups.comps(career):
        if comp.get("winner") is not None:
            out.setdefault(comp["winner"], []).append(SHORT_NAMES.get(comp["key"], comp["name"]))
    return out


SHORT_NAMES = {"association_cup": "Association Cup", "league_cup": "League Cup", "champions_cup": "Champions' Cup",
               "shield": "Continental Shield", "world_club": "World Club Trophy"}


SHORT_WON = {"League champions": "Champions", "Division 1 champions": "D1 champions",
             "Association Cup": "Assoc. Cup", "Champions' Cup": "Champions' Cup", "Continental Shield": "Shield",
             "World Club Trophy": "World Club"}


def season_end(career):
    """The season's line for every player at every club (England, Spain, Germany, Italy)."""
    if career.get("hist_closed") == career.get("year"):
        return
    from career import spain, foreign
    cupg = _cup_goals(career)
    won = _honours(career)
    groups = [(c["id"], c) for c in career.get("clubs", [])]
    groups += [(c["id"], c) for c in spain.clubs(career)]
    for cfg in foreign.LEAGUES:
        groups += [(c["id"], c) for c in foreign.clubs(career, cfg)]
    for cid, c in groups:
        rows = _league_rows(career, cid) if _english(career, cid) else []
        for p in c["players"]:
            a, g, cg = _count(career, cid, p, rows, cupg)
            # (a trophy counts if he was there for it - a few games, or he joined before the spring)
            h = won.get(cid, []) if (a >= 3 or not p.get("hist_since")) else []
            _add(career, p, cid, a, g, cg, h)
    for _, c in groups:
        for p in c["players"]:
            p.pop("hist_since", None)
            p.pop("hist_taken", None)
    career["hist_closed"] = career.get("year")
    from career import legends
    legends.season_records(career)                      # (a club's goals record beaten?)


def lines(p):
    return list(p.get("hist") or [])


def totals(p):
    h = lines(p)
    return sum(x["a"] for x in h), sum(x["g"] for x in h), sum(x.get("cg", 0) for x in h)


def trophies(p):
    """[(trophy, [season labels])], most won first."""
    out = {}
    for x in lines(p):
        for t in x.get("h", []):
            out.setdefault(t, []).append(x["y"])
    return sorted(out.items(), key=lambda kv: -len(kv[1]))


def current(career, cid, p):
    """This season so far, at his club now (for the player page) - or None."""
    if cid is None or cid < 0 or career.get("hist_closed") == career.get("year"):
        return None
    try:
        rows = _league_rows(career, cid) if _english(career, cid) else []
        a, g, cg = _count(career, cid, p, rows, _cup_goals(career))
    except Exception:
        return None
    if not (a or g or cg):
        return None
    line = {"y": _label(career), "c": _short(career, cid), "cid": cid, "a": a, "g": g, "cg": cg, "now": 1}
    if p.get("loan"):
        line["loan"] = 1
    return line
