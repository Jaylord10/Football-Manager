"""
career/awards.py
================
The end-of-season awards, for both divisions (made in the summer, career/league.py new_season):

  - the GOLDEN BOOT: the division's top scorer (league goals; fewer games breaks a tie)
  - PLAYER OF THE SEASON and YOUNG PLAYER OF THE SEASON (21 or under): who was best and played a full part -
    his quality, his goals (and a little for where his club finished); 20 league games at least (young: 12)
  - the TEAM OF THE SEASON: a 4-3-3 of the best in each position
  - MANAGER OF THE SEASON: the champions' manager - unless a club did far better than its size said
    (as the Premier League's award often goes to the over-achiever)

There are no match ratings in the records yet, so "best" is worked out from what is recorded: a player's
overall rating, goals, games and his club's finish.  The winners are kept in career["awards"] and on the
players themselves (p["awards"]) for their profiles.
"""

from career import clubs as clubs_mod

MIN_APPS, MIN_APPS_YOUNG = 20, 12
GOAL_WORTH = {"ST": 0.35, "W": 0.4, "AM": 0.45, "WM": 0.45, "CM": 0.6, "DM": 0.7, "FB": 0.8, "WB": 0.8,
              "CB": 0.8, "GK": 0.0}
TEAM = (("GK", 1), ("FB", 2), ("CB", 2), ("MID", 3), ("FWD", 3))
SLOT = {"GK": "GK", "FB": "FB", "WB": "FB", "CB": "CB", "DM": "MID", "CM": "MID", "AM": "MID", "WM": "MID",
        "W": "FWD", "ST": "FWD"}


def _stats(career, div):
    """{(club id, player id): [apps, goals]} for a division's league season."""
    from career import league
    clubs, results = league._div_data(career, div)
    ids = {c["id"] for c in clubs}
    out = {}
    for md in results.values():
        for r in md:
            for a in r.get("players", []):
                if a.get("minutes", 0) > 0:
                    cid = r["home"] if a["team"] == 0 else r["away"]
                    if cid in ids:
                        out.setdefault((cid, a["id"]), [0, 0])[0] += 1
            for g in r.get("goals", []):
                if g.get("own_goal") or g.get("pid") is None:
                    continue
                cid = r["home"] if g.get("team", 0) == 0 else r["away"]
                if cid in ids:
                    out.setdefault((cid, g["pid"]), [0, 0])[1] += 1
    return out


def _score(p, apps, goals, pos, n):
    group = clubs_mod.NATURAL_GROUP.get(p["Pos"], "CM")
    return clubs_mod.overall(p) + min(12.0, goals * GOAL_WORTH.get(group, 0.5)) + 0.25 * (n + 1 - pos) \
        + 0.05 * apps


def season(career):
    """Work out and keep the awards for the season just finished (call before the results are cleared)."""
    from career import league, divisions, transfers as trf
    if not divisions.exists(career):
        return None
    year_end = career.get("year", 2026) + 1
    label = f"{year_end - 1}-{str(year_end)[-2:]}"
    out = {"year_end": year_end}
    me = career["my_club"]
    for div in divisions.ORDER:
        t = league.table(career, div)
        if not t:
            continue
        pos = {r["club"]: i for i, r in enumerate(t, start=1)}
        n = len(t)
        stats = _stats(career, div)
        rows = []
        for (cid, pid), (apps, goals) in stats.items():
            c = career["clubs"][cid]
            p = clubs_mod.player_by_id(c, pid)
            if p is None:
                continue
            rows.append({"cid": cid, "p": p, "apps": apps, "goals": goals,
                         "score": _score(p, apps, goals, pos.get(cid, n), n)})
        if not rows:
            continue
        aw = {}
        boot = max(rows, key=lambda r: (r["goals"], -r["apps"]))
        aw["golden_boot"] = _entry(career, boot, f"{boot['goals']} goals")
        full = [r for r in rows if r["apps"] >= MIN_APPS] or rows
        best = max(full, key=lambda r: r["score"])
        aw["player"] = _entry(career, best, f"{best['goals']} goals in {best['apps']} games")
        young = [r for r in rows if r["p"].get("Age", 30) <= 21 and r["apps"] >= MIN_APPS_YOUNG]
        if young:
            y = max(young, key=lambda r: r["score"])
            aw["young"] = _entry(career, y, f"{y['goals']} goals in {y['apps']} games")
        team = []
        used = set()
        for slot, k in TEAM:
            cands = sorted((r for r in full if SLOT.get(clubs_mod.NATURAL_GROUP.get(r["p"]["Pos"], "CM")) == slot
                            and id(r["p"]) not in used), key=lambda r: -r["score"])[:k]
            for r in cands:
                used.add(id(r["p"]))
                team.append(_entry(career, r, r["p"]["Pos"]))
        aw["team"] = team
        champ = t[0]["club"]
        from career import finance as fin
        over = max(t, key=lambda r: (fin.size_rank(career, career["clubs"][r["club"]]) + 1) - pos[r["club"]])
        gap = (fin.size_rank(career, career["clubs"][over["club"]]) + 1) - pos[over["club"]]
        aw["manager"] = over["club"] if gap >= 8 else champ
        out[div] = aw
        # On the players' records
        for key, title in (("golden_boot", "Golden Boot"), ("player", "Player of the Season"),
                           ("young", "Young Player of the Season")):
            e = aw.get(key)
            if e:
                p = clubs_mod.player_by_id(career["clubs"][e["club"]], e["pid"])
                if p is not None:
                    p.setdefault("awards", []).append(f"{divisions.name(div)} {title} {label}")
        for e in team:
            p = clubs_mod.player_by_id(career["clubs"][e["club"]], e["pid"])
            if p is not None:
                p.setdefault("awards", []).append(f"{divisions.name(div)} Team of the Season {label}")
        # The news for you
        for key, title in (("golden_boot", "the Golden Boot"), ("player", "Player of the Season"),
                           ("young", "Young Player of the Season")):
            e = aw.get(key)
            if e and e["club"] == me:
                trf._message(career, "news", f"{e['name']} wins {title} in the {divisions.name(div)} ({e['note']}).")
        if aw["manager"] == me:
            trf._message(career, "news", f"You've been named the {divisions.name(div)} Manager of the Season!")
            from career import board
            board._bump(career, 5, "Manager of the Season")
        n_team = sum(1 for e in team if e["club"] == me)
        if n_team:
            trf._message(career, "news", f"{n_team} of your players made the {divisions.name(div)} Team of the Season.")
    career.setdefault("awards", []).append(out)
    career["awards"] = career["awards"][-40:]
    from career import media
    media.awards_story(career, out)
    return out


def _entry(career, r, note):
    return {"name": r["p"]["Name"], "pid": r["p"]["id"], "club": r["cid"], "pos": r["p"]["Pos"],
            "age": r["p"].get("Age"), "note": note}


def latest(career):
    return (career.get("awards") or [None])[-1]
