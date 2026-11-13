"""
career/friendlies.py
====================
Friendlies: arrange them on any free date (Calendar screen) against a local
non-league side, a club from your league or a Spanish club, home or away.

  - a free date: from tomorrow on, at least GAP days away from a league match
    and from another friendly; before the season's last league game
  - on the day, Continue stops there: watch it, or take a quick result
  - it doesn't count in the table; lots of substitutes are allowed (everyone
    gets a run-out - the engine's friendly mode); men can still get injured
  - minutes build fitness and sharpness (career/fitness.py); a home friendly
    brings in a little gate money

career["friendlies"]: [{id, date, kind (local / league / spain), opp (club id or
None), name, home, club (a local side's squad), result}]
"""

import math
import random

from career import calendar as cal, clubs as clubs_mod

GAP = 2                         # days clear of a league match / another friendly
LOCAL_ID = 900                  # (ids for local sides - never a real club)
LOCAL_LEVEL = (46.0, 54.0)      # a non-league side's level (league clubs ~62-80)
GATE = {"local": 40_000, "league": 220_000, "spain": 450_000}    # home friendly gate money
QUICK_INJURY = 0.0003           # per minute played (friendlies: less intense than the league)
LOCAL_NAMES = ["Hartley Town", "Kirkby Lane", "Elmstead Rovers", "Fenwick Athletic", "Bramley Vale", "Coldham Town",
               "Willow Park", "Stanmoor United", "Greyfield Town", "Oxley Celtic", "Pennington Rangers",
               "Marsh Lane", "Holt Wanderers", "Ridgeway Town", "Calder Vale", "Thornbury Athletic"]


def all_(career):
    return career.setdefault("friendlies", [])


def upcoming(career):
    today = career.get("date", "")
    return sorted((f for f in all_(career) if not f.get("result") and f["date"] >= today), key=lambda f: f["date"])


def next_one(career):
    """The next unplayed friendly before your next league match (or None)."""
    from career import league
    nxt = league.match_date(career)
    for f in upcoming(career):
        if nxt is None or f["date"] < nxt:
            return f
    return None


def today(career):
    f = next_one(career)
    return f if f and f["date"] == career.get("date") else None


def date_ok(career, iso):
    """(ok, why not)"""
    t = career.get("date", "")
    if iso <= t:
        return False, "That's not in the future."
    days = career.get("calendar") or []
    if days and iso > days[-1]:
        return False, "The season's over by then."
    for d in days:
        if abs(cal.days_between(d, iso)) < GAP:
            return False, "Too close to a league match."
    for f in all_(career):
        if not f.get("result") and abs(cal.days_between(f["date"], iso)) < GAP:
            return False, "Too close to another friendly."
    from career import cups
    for m in cups.all_matches(career):
        if cups.involved(career, m) and abs(cal.days_between(m["date"], iso)) < GAP:
            return False, "Too close to a cup tie."
    return True, ""


def local_sides(career, iso):
    """Three non-league sides who'd play you that day (names fixed by the date)."""
    rng = random.Random(f"locals:{iso}")
    return rng.sample(LOCAL_NAMES, 3)


def options(career, kind, iso):
    """[(opp id or None, name)] you could play that day."""
    if kind == "local":
        return [(None, n) for n in local_sides(career, iso)]
    if kind == "league":
        return [(c["id"], c["name"]) for c in career["clubs"] if c["id"] != career["my_club"]]
    if kind == "spain" and "spain" in career:
        from career import spain
        return [(c["id"], c["name"]) for c in spain.clubs(career)]
    return []


def arrange(career, iso, kind, opp, name, home):
    ok, why = date_ok(career, iso)
    if not ok:
        return why
    f = {"id": max([x["id"] for x in all_(career)] + [0]) + 1, "date": iso, "kind": kind, "opp": opp,
         "name": name, "home": bool(home), "result": None}
    if kind == "local":
        f["club"] = _local_side(career, name, iso)
    all_(career).append(f)
    return None


def cancel(career, fid):
    career["friendlies"] = [f for f in all_(career) if f["id"] != fid or f.get("result")]


def _local_side(career, name, iso):
    """A non-league squad (18 men) - made once, kept with the friendly."""
    rng = random.Random(f"local:{name}:{iso}")
    level = rng.uniform(*LOCAL_LEVEL)
    used = set()
    players = []
    pid = 0
    for pos, n in (("GK", 2), ("LB", 1), ("RB", 1), ("CB", 3), ("CM", 4), ("LM", 1), ("RM", 1), ("ST", 3)):
        for _ in range(n):
            p = clubs_mod._player(rng, pos, level + rng.gauss(0, 3), used, pid, age=rng.randint(19, 33))
            p["condition"] = 1.0
            players.append(p)
            pid += 1
    club = {"id": LOCAL_ID + rng.randint(0, 99), "name": name, "short": name.split(" ")[0],
            "colour": [rng.randint(40, 230), rng.randint(40, 230), rng.randint(40, 230)], "strength": level,
            "players": players, "roles": {"base": rng.choice(["blue", "red"])},
            "tactics": {"defence": "mid_block", "build_up": "mixed"}, "instructions": {}}
    club["lineup"] = clubs_mod.best_lineup(club)
    return club


def opponent(career, f):
    """The other club's dict."""
    if f["kind"] == "local":
        return f["club"]
    if f["kind"] == "spain":
        from career import spain
        c = spain.club(career, f["opp"])
        if not c.get("lineup"):
            c["lineup"] = spain.pick_xi(c, f["date"])
        return c
    return career["clubs"][f["opp"]]


def sides(career, f):
    """(home club, away club)"""
    me = career["clubs"][career["my_club"]]
    opp = opponent(career, f)
    return (me, opp) if f["home"] else (opp, me)


# ---------------------------------------------------------------------------
# Playing it
# ---------------------------------------------------------------------------
def quick(career, f, rng=None):
    """A quick result (no engine): goals from the two sides' strength; minutes for everyone."""
    rng = rng or random.Random(f"friendly:{f['id']}:{f['date']}")
    home, away = sides(career, f)
    sh, sa = _strength(home), _strength(away)
    hg = _poisson(rng, max(0.2, 1.45 * 1.08 ** (sh - sa)))
    ag = _poisson(rng, max(0.2, 1.15 * 1.08 ** (sa - sh)))
    players, goals = [], []
    for side, club, n in ((0, home, hg), (1, away, ag)):
        xi = list((club.get("lineup") or {}).values())
        from career import availability as av
        bench = [p for p in sorted(club["players"], key=lambda q: -clubs_mod.overall(q))
                 if p["id"] not in xi and not av.injured(p, f["date"])][:9]
        swap = max(0, min(len(bench), 8))
        for i, pid in enumerate(xi):
            mins = 90 if i >= swap else rng.choice([45, 60, 70])
            players.append({"team": side, "id": pid, "minutes": mins, "stamina": round(1 - 0.27 * mins / 90, 2)})
        for p in bench[:swap]:
            players.append({"team": side, "id": p["id"], "minutes": rng.choice([20, 30, 45]), "stamina": 0.9})
        att = [a["id"] for a in players if a["team"] == side]
        for _ in range(n):
            gp = rng.choice(att)
            gpl = clubs_mod.player_by_id(club, gp)
            goals.append({"team": side, "pid": gp, "own_goal": False, "name": gpl["Name"] if gpl else "?",
                          "minute": rng.randint(1, 90)})
    goals.sort(key=lambda g: g["minute"])
    for a in players:                                       # knocks and injuries
        if rng.random() < QUICK_INJURY * a["minutes"]:
            a["injury"] = {"minute": rng.randint(1, 90), "knock": rng.random() < 0.3}
    return {"home": home["id"], "away": away["id"], "hg": hg, "ag": ag, "goals": goals,
            "possession": 50, "subs": [], "players": players, "quick": True}


def _strength(club):
    from career import morale
    return morale._strength(club)


def _poisson(rng, lam):
    k, p, L = 0, 1.0, math.exp(-lam)
    while True:
        p *= rng.random()
        if p < L:
            return k
        k += 1


def finish(career, f, r, rng=None):
    """After the friendly: your men's minutes, fitness, sharpness, knocks; the gate; the papers."""
    from career import fitness, availability as av, finance, media
    rng = rng or random.Random(f"after:{f['id']}")
    me = career["clubs"][career["my_club"]]
    my_side = 0 if f["home"] else 1
    date = f["date"]
    for a in r.get("players", []):
        if a["team"] != my_side:
            continue
        p = clubs_mod.player_by_id(me, a["id"])
        if p is None or not a.get("minutes"):
            continue
        fitness.played(p, a["minutes"])
        if a.get("stamina") is not None:
            p["condition"] = round(min(p.get("condition", 1.0), a["stamina"]), 3)
        inj = a.get("injury")
        if inj:
            if inj.get("knock"):
                if not av.injured(p, date):
                    import datetime as dt
                    until = (cal.parse(date) + dt.timedelta(days=rng.randint(1, 3))).isoformat()
                    p["injury"] = {"name": "Knock", "since": date, "until": until, "cause": "match"}
            else:
                av._injure(career, me, p, date, "match", rng, inj.get("minute"))
    if f["home"]:
        finance._book(me, "matchday", GATE.get(f["kind"], 50_000))     # (the gate)
    gf, ga = (r["hg"], r["ag"]) if f["home"] else (r["ag"], r["hg"])
    f["result"] = {"hg": r["hg"], "ag": r["ag"], "gf": gf, "ga": ga,
                   "goals": [{"team": g["team"], "name": g["name"], "minute": g.get("minute")} for g in r.get("goals", [])],
                   "quick": bool(r.get("quick"))}
    media.friendly(career, f)
    return f["result"]
