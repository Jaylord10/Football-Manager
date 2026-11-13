"""
career/manager.py
=================
You, the manager: your record and your reputation.

  - YOUR RECORD, season by season and club by club: where you finished, games won / drawn / lost (league and
    cups), trophies, promotions and relegations, Manager of the Season - and the times you were sacked.
  - YOUR REPUTATION (0-100), which decides who wants you:
      * it starts from the size of your first club (managing a big club means the game already rates you);
      * each season it moves with how you did against the club's size (finishing above where the money says
        you should), with trophies and promotion, Manager of the Season; relegation and the sack cost you;
      * it drifts a little towards the level of the club you're at (a big job keeps you in the papers).
    Real football works like this: the managers who get the big jobs are the ones who did better than their
    budgets (Eddie Howe at Bournemouth, Graham Potter at Brighton, Unai Emery at Villarreal), or who won.
  - WHO WANTS YOU: when you're sacked, the clubs that call are the ones your reputation reaches; and in the
    summer a bigger club may ask you to be its manager (the summer screen) - take it or stay.

Kept in career["manager"] = {"rep": 47.5, "since": "2026-07-01", "club": 2, "seasons": [...], "offer": {...}}.
"""

import random

from career import calendar as cal
from career import finance as fin

TITLES = {"association_cup": ("the Association Cup", 6), "league_cup": ("the League Cup", 4),
          "champions_cup": ("the Champions' Cup", 14), "shield": ("the Continental Shield", 7),
          "world_club": ("the World Club Trophy", 3)}
LEAGUE_TITLE, D1_TITLE, PROMOTED = 12, 6, 6
RELEGATED, SACKED = -7, -8
PER_PLACE = {"pl": 1.1, "d1": 0.7}          # reputation per place above (or below) where the club "should" finish
DRIFT = 0.12                                  # each season, this share of the gap to the club's own level
OFFER_CHANCE = 0.55                           # a bigger club asks, if your reputation reaches one


def level(career, club):
    """What managing this club says about you, 0-100 (the biggest club ~85, the smallest Division 1 club ~25)."""
    n = len(career["clubs"]) or 40
    return 85 - 60 * fin.stature(career, club) / max(1, n - 1)


def state(career):
    m = career.get("manager")
    if m is None:
        me = career["clubs"][career["my_club"]]
        m = career["manager"] = {"rep": round(level(career, me) * 0.85, 1), "since": None,
                                 "club": career["my_club"], "seasons": [], "offer": None}
    return m


def label(rep):
    return ("World class" if rep >= 85 else "Top manager" if rep >= 72 else "Highly rated" if rep >= 60
            else "Respected" if rep >= 47 else "Promising" if rep >= 34 else "Up and coming")


def _matches(career, since):
    """[(competition, goals for, goals against)] for your matches since `since` this season."""
    from career import league, cups
    me = career["my_club"]
    out = []
    for md, day in (career.get("results") or {}).items():
        d = league.match_date(career, int(md)) or ""
        if d < (since or ""):
            continue
        for r in day:
            if me in (r["home"], r["away"]):
                f, a = (r["hg"], r["ag"]) if r["home"] == me else (r["ag"], r["hg"])
                out.append(("league", f, a))
    for m in cups.all_matches(career):
        res = m.get("result")
        if res and me in (m["home"], m["away"]) and m["date"] >= (since or ""):
            f, a = (res["hg"], res["ag"]) if m["home"] == me else (res["ag"], res["hg"])
            out.append((m["comp"], f, a))
    return out


def _wdl(ms):
    w = sum(1 for _, f, a in ms if f > a)
    d = sum(1 for _, f, a in ms if f == a)
    return [len(ms), w, d, len(ms) - w - d]


def _line(career, extra=None):
    m = state(career)
    me = career["clubs"][career["my_club"]]
    from career import divisions, league
    ms = _matches(career, m.get("since"))
    line = {"year": career.get("year"), "club": me["id"], "name": me["name"], "short": me.get("short", me["name"]),
            "div": divisions.div_of(me) if divisions.exists(career) else "pl", "all": _wdl(ms),
            "league": _wdl([x for x in ms if x[0] == "league"]), "pos": league.position_of(career, me["id"]),
            "won": [], "notes": [], "rep_before": m["rep"]}
    line.update(extra or {})
    return line


def _add_rep(m, delta, cap=99):
    m["rep"] = round(max(5.0, min(cap, m["rep"] + delta)), 1)


def season_end(career, tables, up, down):
    """After the board's verdict (career/league.py new_season): the season's line and your reputation."""
    from career import divisions, awards
    m = state(career)
    me = career["clubs"][career["my_club"]]
    if (career.get("board") or {}).get("sacked"):           # (sacked on the last day: that line stands)
        last = m["seasons"][-1] if m["seasons"] else None
        if last and last.get("year") == career.get("year") and last.get("club") == me["id"]:
            t = tables.get(last.get("div")) or []
            last["pos"] = next((i for i, r in enumerate(t, start=1) if r["club"] == me["id"]), last.get("pos"))
        m["closed"] = [career.get("year"), me["id"]]
        return
    line = _line(career)
    div = line["div"]
    t = tables.get(div) or []
    pos = next((i for i, r in enumerate(t, start=1) if r["club"] == me["id"]), None)
    line["pos"] = pos
    delta = 0.0
    if pos:
        expected = fin.size_rank(career, me) + 1
        delta += PER_PLACE.get(div, 0.8) * (expected - pos)
        if pos == 1:
            line["won"].append("the League" if div == "pl" else "Division 1")
            delta += LEAGUE_TITLE if div == "pl" else D1_TITLE
    if me["id"] in up:
        line["notes"].append("promoted")
        delta += PROMOTED
    if me["id"] in down:
        line["notes"].append("relegated")
        delta += RELEGATED
    h = (career.get("cup_history") or [{}])[-1]
    if h.get("year_end") == career.get("year", 0) + 1:
        for key, (nm, worth) in TITLES.items():
            if (h.get(key) or [None])[0] == me["id"]:
                line["won"].append(nm)
                delta += worth
    aw = awards.latest(career) or {}
    if (aw.get(div) or {}).get("manager") == me["id"] and aw.get("year_end") == career.get("year", 0) + 1:
        line["notes"].append("Manager of the Season")
        delta += 4
    _add_rep(m, delta)
    _add_rep(m, DRIFT * (level(career, me) - m["rep"]))
    line["rep"] = m["rep"]
    m["seasons"].append(line)
    m["seasons"] = m["seasons"][-60:]
    m["since"] = None                          # (the next season counts from its start)
    m["closed"] = [career.get("year"), me["id"]]


def summer(career):
    """After promotion and relegation (career/league.py new_season): does a bigger club want you?"""
    from career import divisions
    m = state(career)
    m["offer"] = None
    if not divisions.exists(career) or (career.get("board") or {}).get("sacked"):
        return
    _maybe_offer(career, random.Random(f"job:{career.get('year')}:{career['my_club']}:{m['rep']}"))


def sacked(career, why):
    """The board has sacked you (career/board.py): the season so far at this club, and a hit to your name."""
    m = state(career)
    m["offer"] = None
    if m.get("closed") == [career.get("year"), career["my_club"]] and m["seasons"]:
        m["seasons"][-1]["notes"].append("sacked")             # (at the season's end: that season's line)
        _add_rep(m, SACKED)
        m["seasons"][-1]["rep"] = m["rep"]
        return
    line = _line(career, {"notes": ["sacked"]})
    _add_rep(m, SACKED)
    line["rep"] = m["rep"]
    line["sacked"] = cal.fmt(career.get("date"), False) if career.get("date") else ""
    m["seasons"].append(line)
    m["offer"] = None


def joined(career, club_id):
    """A new job (career/board.py take_job)."""
    m = state(career)
    m["since"] = career.get("date")
    m["club"] = club_id
    m["offer"] = None


def pull(career, club):
    """The reputation a club wants in its manager."""
    return level(career, club) - 12


def job_offers(career, rng, n=3):
    """After the sack: clubs your reputation reaches (the biggest few of them), never the club that sacked you."""
    m = state(career)
    me = career["my_club"]
    y = (career.get("date") or "0000")[:4]
    burnt = {j["club"] for j in (career.get("board") or {}).get("career_log", [])
             if (j.get("until") or "0000")[:4] >= str(int(y) - 2)}          # (not the clubs that sacked you lately)
    clubs = [c for c in career["clubs"] if c["id"] != me and c["name"] not in burnt]
    cap = level(career, career["clubs"][me]) + 2       # (after the sack: not a bigger club than the last one)
    reach = [c for c in clubs if pull(career, c) <= m["rep"] + 4 and level(career, c) <= cap]
    reach.sort(key=lambda c: -level(career, c))
    pool = reach[:max(n + 3, 6)] or sorted(clubs, key=lambda c: level(career, c))[:6]
    return [c["id"] for c in rng.sample(pool, min(n, len(pool)))]


def _maybe_offer(career, rng):
    """The summer: a bigger club your reputation reaches may want you."""
    m = state(career)
    me = career["clubs"][career["my_club"]]
    mine = level(career, me)
    cands = [c for c in career["clubs"] if c["id"] != me["id"] and level(career, c) >= mine + 6
             and pull(career, c) <= m["rep"]]
    if not cands or rng.random() > OFFER_CHANCE:
        m["offer"] = None
        return
    cands.sort(key=lambda c: -level(career, c))
    pick = rng.choice(cands[:3])
    m["offer"] = {"club": pick["id"], "year": career.get("year", 0) + 1, "until": f"{career.get('year', 0) + 1}-07-31"}
    from career import transfers as trf
    trf._message(career, "board", f"{pick['name']} have asked for permission to speak to you about becoming "
                                  f"their manager. (See the summer screen.)")


def offer(career):
    """This summer's offer: the club id, or None."""
    o = state(career).get("offer")
    if o and o.get("year") == career.get("year"):
        return o["club"]
    return None


def take_offer(career):
    cid = offer(career)
    if cid is None:
        return False
    from career import board
    old = career["clubs"][career["my_club"]]["name"]
    board.take_job(career, cid)
    m = state(career)
    if m["seasons"]:
        m["seasons"][-1].setdefault("notes", []).append(f"left for {career['clubs'][cid]['name']}")
    from career import transfers as trf
    trf._message(career, "news", f"You've left {old} to become the manager of {career['clubs'][cid]['name']}.")
    return True


def turn_down(career):
    m = state(career)
    if m.get("offer"):
        nm = career["clubs"][m["offer"]["club"]]["name"]
        m["offer"] = None
        from career import transfers as trf
        trf._message(career, "board", f"You've turned down {nm}. The board are delighted you're staying.")
        from career import board
        board._bump(career, 4, "turned down " + nm)


def totals(career):
    """(games, won, drawn, lost, trophies, seasons) over your whole career."""
    m = state(career)
    g = w = d = l = 0
    tro = []
    for s in m["seasons"]:
        a = s.get("all") or [0, 0, 0, 0]
        g, w, d, l = g + a[0], w + a[1], d + a[2], l + a[3]
        tro += s.get("won", [])
    return g, w, d, l, tro, len({s["year"] for s in m["seasons"]})
