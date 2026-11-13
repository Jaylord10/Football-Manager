"""
career/owners.py
================
Takeovers: now and then a club gets new owners (each summer, before the budgets are set).

Real football: a Premier League or Championship club changes hands every year or two (Newcastle 2021, Chelsea
2022, Everton 2024...) - about 1-2 a season among 40 clubs here.  Three kinds of owner:

  - RICH INVESTORS (a consortium, a fund): £100-300m into the bank (Division 1: £25-60m), sponsors that
    grow over the next few seasons (+50%), and a board that expects more (aims as if the club were four
    places bigger).  The squad cost rules (career/ffp.py) still limit what they can spend on players, as
    Newcastle found.
  - A LOCAL BUSINESSMAN: a modest £15-40m (Division 1: £5-15m), sponsors +10%, the same ambitions.
  - COST-CUTTERS: a takeover paid for with borrowed money that the club then owes (as at Manchester United in
    2005): £80-200m of debt (Division 1: £15-40m) with 6% interest a year, transfer budgets halved, and a
    board that expects a little less.

Kept on the club: club["owner"] = {"kind", "name", "since", "debt"}; every takeover in career["takeovers"].
"""

import random

M = 1_000_000
CHANCE = 0.035                   # per club per summer (about 1.4 of the 40)
SETTLE = 5                       # no new takeover within this many seasons of the last
KINDS = (("rich", 0.35), ("local", 0.40), ("cutters", 0.25))
CASH = {"rich": {"pl": (100 * M, 300 * M), "d1": (25 * M, 60 * M)},
        "local": {"pl": (15 * M, 40 * M), "d1": (5 * M, 15 * M)}}
DEBT = {"pl": (80 * M, 200 * M), "d1": (15 * M, 40 * M)}
INTEREST = 0.06
COMMERCIAL = {"rich": 1.5, "local": 1.1}
AMBITION = {"rich": -4, "local": 0, "cutters": 2}       # (size rank the board aims as: - is bigger)
NAMES = {"rich": ["the Meridian Capital consortium", "Harbourline Investments", "the Aldgate Group",
                  "Sterling Crown Holdings", "the Pacifica Sports Fund", "Northstar Partners"],
         "local": ["local businessman Tom Hadley", "local haulage boss Brian Kettering",
                   "builder-turned-chairman Ray Cotton", "local entrepreneur Sue Whitlock",
                   "lifelong fan and tech founder Priya Bains", "the Ashworth family"],
         "cutters": ["Blackwater Leveraged Partners", "the Crane Equity Group", "Vexley Holdings",
                     "the Morrow Capital consortium"]}
LABEL = {"rich": "rich new owners", "local": "a local businessman", "cutters": "cost-cutting owners"}


def ambition(club):
    """Places bigger (-) or smaller (+) the board aims as, with the current owners (for 5 seasons)."""
    o = club.get("owner")
    return AMBITION.get(o["kind"], 0) if o else 0


def summer(career, rng):
    """Before the budgets: any takeovers this summer?  (career/league.py new_season)"""
    from career import finance as fin, transfers as trf, media
    year = career.get("year", 2026)
    out = []
    for c in career["clubs"]:
        f = c.get("finance")
        if not f:
            continue
        o = c.get("owner")
        if o and year - o.get("since", 0) < SETTLE:
            continue
        if o and year - o.get("since", 0) >= SETTLE and o["kind"] != "cutters":
            c.pop("owner")                       # (the new owners' honeymoon's over: back to normal ambitions)
        if rng.random() >= CHANCE:
            continue
        lg = fin.league_of(c)
        kind = rng.choices([k for k, _ in KINDS], [w for _, w in KINDS])[0]
        recent = {t["name"] for t in career.get("takeovers", []) if t["year"] > year - 10}
        name = rng.choice([x for x in NAMES[kind] if x not in recent] or NAMES[kind])
        o = {"kind": kind, "name": name, "since": year, "debt": 0}
        if kind in CASH:
            lo, hi = CASH[kind].get(lg, CASH[kind]["d1"])
            cash = round(rng.uniform(lo, hi) / M) * M
            fin._book(c, "investment", cash)
            o["cash"] = cash
            f["commercial_target"] = round(f["commercial"] * COMMERCIAL[kind])
            what = f"{fin.money(cash)} into the club"
        else:
            lo, hi = DEBT.get(lg, DEBT["d1"])
            debt = round(rng.uniform(lo, hi) / M) * M
            o["debt"] = debt
            what = f"{fin.money(debt)} of debt loaded onto the club"
        c["owner"] = o
        rec = {"year": year, "club": c["id"], "kind": kind, "name": name, "what": what}
        career.setdefault("takeovers", []).append(rec)
        out.append(rec)
        media.takeover_story(career, c, rec)
        if c["id"] == career["my_club"]:
            trf._message(career, "board", f"Takeover! The club has been bought by {name} - {what}. "
                                          + {"rich": "They want to be challenging much higher up the table.",
                                             "local": "They want steady progress.",
                                             "cutters": "Budgets will be tight - they expect you to cope."}[kind])
    return out


def interest(career):
    """Cost-cutting owners' borrowing: the club pays the interest each summer (career/finance.py)."""
    from career import finance as fin
    for c in career["clubs"]:
        o = c.get("owner")
        if o and o.get("debt") and c.get("finance"):
            fin._book(c, "other", -INTEREST * o["debt"])


def budget_factor(club):
    o = club.get("owner")
    return 0.5 if o and o["kind"] == "cutters" else 1.0
