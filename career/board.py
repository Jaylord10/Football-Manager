"""
career/board.py
===============
The board: what they expect, how happy they are, and the sack.

OBJECTIVES (each summer, from the club's size - its place in the pecking
order - not its squad on the day):
  biggest club ............ win the league
  next three .............. finish in the top four
  next three .............. finish in the top seven
  the middle .............. finish in the top half
  the rest ................ stay out of the bottom three
plus the money: don't go into debt, keep within the wage budget.

CONFIDENCE (0-100, starting at 65 at a new job):
  - every match: points won against what a club of yours should take off
    that opponent (home or away)
  - the first of every month: where you are in the table against the target
    (from October - early tables mean little), and the money
  - end of the season: the big review - target met, missed narrowly, missed badly
Warnings come by inbox ("the board are concerned", then an ultimatum).

THE SACK: confidence below SACK_AT after the first ten games of a season, or
below SACK_AT_SEASON_END at the end of one.  You can then take a job at one
of the clubs that want you (smaller ones, usually) - or start again.
"""

import random

from career import calendar as cal
from career import finance as fin

START = 65
SACK_AT = 12
SACK_AT_SEASON_END = 25
PATIENCE_GAMES = 10
WARN_AT = 35
ULTIMATUM_AT = 22
MATCH_WEIGHT = 2.5            # confidence per point above / below what was expected
TABLE_WEIGHT = 0.9            # per place away from the target, each month (from October)
DEBT_HIT = 6                  # each month in the red
WAGES_HIT = 2                 # each month over the wage budget
REVIEW = {"met": 15, "near": -6, "missed": -22, "smashed": 25}
EXPECTED_PPG = (2.35, 0.85)   # what the biggest / smallest club should average (points per game)


def objective(career, club):
    """(text, target place: finish this or higher; 'avoid' targets stored as 17 = stay above 18th)"""
    n = fin.league_size(career, club)
    if fin.league_of(club) == "d1":                # Division 1 (career/divisions.py): promotion's the thing
        from career import owners
        r = max(0, fin.size_rank(career, club) + owners.ambition(club))
        if r <= 1:
            return "Win promotion", 2
        if r <= 5:
            return "Reach the play-offs", 6
        if r <= 11:
            return "Finish in the top half", n // 2
        return "Finish in the top fifteen", 15
    r = fin.size_rank(career, club)               # 0 = biggest
    from career import owners
    r = max(0, min(n - 1, r + owners.ambition(club)))   # (new owners aim higher - or lower)
    scale = n / 20.0
    if r == 0:
        return "Win the league", 1
    if r <= round(3 * scale):
        return "Finish in the top four", round(4 * scale)
    if r <= round(6 * scale):
        return "Finish in the top seven", round(7 * scale)
    if r <= round(12 * scale):
        return "Finish in the top half", n // 2
    return "Stay out of the bottom three", n - 3


def _expected_ppg(career, club):
    n = fin.league_size(career, club)
    r = fin.size_rank(career, club)
    top, bottom = EXPECTED_PPG
    return top - (top - bottom) * r / max(1, n - 1)


def state(career):
    b = career.get("board")
    if b is None:
        b = career["board"] = {"confidence": START, "games": 0, "warned": None, "sacked": False,
                               "history": [], "messages": []}
    return b


def new_season(career):
    """Summer: this season's objective."""
    from career import transfers as trf
    b = state(career)
    me = career["clubs"][career["my_club"]]
    text, target = objective(career, me)
    b["objective"] = text
    b["target"] = target
    b["games"] = 0
    b["warned"] = None
    trf._message(career, "board", f"The board's objective for {cal.season_label(career.get('year', 2026))}: "
                                  f"{text.lower()}. Keep the club out of debt and within the wage budget.")


def ensure(career):
    b = state(career)
    if "objective" not in b:
        me = career["clubs"][career["my_club"]]
        b["objective"], b["target"] = objective(career, me)


def _bump(career, delta, why=None):
    b = state(career)
    b["confidence"] = round(max(0.0, min(100.0, b["confidence"] + delta)), 1)
    if why:
        b["messages"].append({"date": career.get("date"), "text": why, "delta": round(delta, 1)})
        b["messages"] = b["messages"][-30:]


def after_match(career, results):
    """A matchday: points against expectation, then warnings / the sack."""
    me = career["my_club"]
    b = state(career)
    for r in results:
        if me not in (r["home"], r["away"]):
            continue
        home = r["home"] == me
        gf, ga = (r["hg"], r["ag"]) if home else (r["ag"], r["hg"])
        pts = 3 if gf > ga else 1 if gf == ga else 0
        opp = career["clubs"][r["away"] if home else r["home"]]
        mine = _expected_ppg(career, career["clubs"][me])
        theirs = _expected_ppg(career, opp)
        exp = max(0.2, min(2.8, 1.35 + (mine - theirs) * 0.9 + (0.3 if home else -0.3)))
        _bump(career, MATCH_WEIGHT * (pts - exp))
        b["games"] += 1
    _check(career)


def monthly(career, date):
    """The first of the month: the table and the money."""
    from career import league
    b = state(career)
    me = career["clubs"][career["my_club"]]
    d = cal.parse(date)
    if b["games"] >= 6 and d.month not in (7, 8, 9):
        pos = league.position_of(career, me["id"])
        gap = b.get("target", 10) - pos             # + = above target
        _bump(career, TABLE_WEIGHT * max(-6, min(6, gap)))
    f = me.get("finance", {})
    if f.get("balance", 0) < 0:
        _bump(career, -DEBT_HIT, "The board are alarmed that the club is in debt.")
    if fin.wage_bill(me) > f.get("wage_budget", 1e18):
        _bump(career, -WAGES_HIT, "The board note the wage bill is over budget.")
    _check(career)


def _check(career):
    from career import transfers as trf
    b = state(career)
    c = b["confidence"]
    if b["games"] >= PATIENCE_GAMES and c < SACK_AT:
        sack(career, "results this season have not been good enough")
        return
    if c < ULTIMATUM_AT and b.get("warned") != "ultimatum":
        b["warned"] = "ultimatum"
        trf._message(career, "board", "The board have issued an ultimatum: results must improve immediately, "
                                      "or you will be dismissed.")
    elif c < WARN_AT and b.get("warned") is None:
        b["warned"] = "concern"
        trf._message(career, "board", "The board are concerned by recent results and expect a quick improvement.")
    elif c >= 50:
        b["warned"] = None


def season_review(career, table, up=(), down=()):
    """End of the season: the objective, and maybe the sack.  up / down: who's promoted and relegated
    (career/divisions.py) - going up always meets a Division 1 objective; going down misses any."""
    from career import transfers as trf
    b = state(career)
    me = career["my_club"]
    pos = next(i for i, r in enumerate(table, start=1) if r["club"] == me)
    target = b.get("target", 10)
    if me in up:
        verdict, delta = ("smashed", REVIEW["smashed"]) if target > 2 else ("met", REVIEW["met"])
    elif me in down:
        verdict, delta = "missed", REVIEW["missed"]
    elif pos <= max(1, target - 3) and target > 1:
        verdict, delta = "smashed", REVIEW["smashed"]
    elif pos <= target:
        verdict, delta = "met", REVIEW["met"]
    elif pos <= target + (1 if target >= len(table) - 3 else 2):      # (the bottom three is never "narrow")
        verdict, delta = "near", REVIEW["near"]
    else:
        verdict, delta = "missed", REVIEW["missed"]
    _bump(career, delta)
    words = {"smashed": "far exceeded", "met": "met", "near": "narrowly missed", "missed": "badly missed"}[verdict]
    b["history"].append({"year": career.get("year"), "objective": b.get("objective"), "position": pos,
                         "verdict": verdict, "confidence": b["confidence"]})
    trf._message(career, "board", f"Season review: you finished {pos}{_suffix(pos)} - the objective "
                                  f"({(b.get('objective') or '').lower()}) was {words}. Board confidence: "
                                  f"{round(b['confidence'])}/100.")
    if b["confidence"] < SACK_AT_SEASON_END:
        sack(career, f"the season's objective was {words}")


def _suffix(n):
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def sack(career, why):
    b = state(career)
    if b.get("sacked"):
        return
    b["sacked"] = True
    b["sacked_reason"] = why
    b["sacked_date"] = career.get("date")
    me = career["clubs"][career["my_club"]]
    b.setdefault("career_log", []).append({"club": me["name"], "until": career.get("date"), "why": why})
    career["stop"] = True                       # (Continue halts here)
    from career import manager, media
    manager.sacked(career, why)                 # your record and reputation (career/manager.py)
    media.sacked(career, me, why)


def job_offers(career, rng=None):
    """Clubs that would take you on: a few, usually smaller than the one that sacked you."""
    rng = rng or random.Random(career.get("date"))
    me = career["clubs"][career["my_club"]]
    from career import manager, divisions
    if divisions.exists(career):
        return manager.job_offers(career, rng)  # (the clubs your reputation reaches - career/manager.py)
    r = fin.size_rank(career, me)
    order = sorted(career["clubs"], key=lambda c: fin.size_rank(career, c))
    pool = [c for c in order if c["id"] != me["id"] and fin.size_rank(career, c) >= min(r + 2, len(order) - 4)]
    if len(pool) < 3:
        pool = [c for c in order if c["id"] != me["id"]][-6:]
    return [c["id"] for c in rng.sample(pool, min(3, len(pool)))]


def take_job(career, club_id):
    """A new club: your old one goes to the AI; a fresh start with the new board."""
    from career import availability as av, registration
    old = career["clubs"][career["my_club"]]
    career["my_club"] = club_id
    from career import manager, media
    manager.joined(career, club_id)
    media.appointed(career, career["clubs"][club_id])
    from career import staff
    staff.ensure(career)                        # (the new club's staff)
    from career import divisions
    divisions.follow(career)                    # (a job in the other division: its fixtures become yours)
    b = state(career)
    b.update({"confidence": START, "games": 0, "warned": None, "sacked": False})
    new = career["clubs"][club_id]
    b["objective"], b["target"] = objective(career, new)
    # the old club picks its own team again; the new one keeps its list
    from career import training
    old["lineup"] = training.best_lineup_fit(old, career.get("date"))
    registration.tidy(new)
    for k in ("bids", "talks"):
        career[k] = {}
    career["inbox"] = [m for m in career.get("inbox", []) if m["kind"] != "offer"]
    av._news(career, career["date"], club_id, f"You are the new manager of {new['name']}. The board's objective: "
                                              f"{b['objective'].lower()}.", "squad")
