"""
career/crowds.py
================
Who comes to the games.  Every league club has a FAN BASE - how many would
come if they could (a club's profile can set it; otherwise it's worked out from
its size: the biggest clubs could fill their grounds ~1.2 times over, the
smallest not quite).  Each home game's crowd is that fan base, up or down with:

  - where the club is in the table (top three a bit up, the bottom down)
  - its form (the last five games)
  - the fans' mood (yours: the mood the papers and social media track)
  - the visitors (a big club or a derby brings more)

...never more than the seats that are open (career/stadium.py).  The crowd x
the ticket price is the gate money (career/finance.py).  The fan base grows
after good seasons and shrinks after bad ones.

Premier League grounds average ~97% full; most top clubs sell out every week
with waiting lists - which is what the board look for before they'll build.

career["crowds"][club id] = {"support": n, "games": [{date, opp, att, cap}] (this season),
                             "last": {avg, pct, sellouts, games} (last season)}
"""

import random

from career import clubinfo

SUPPORT_RANGE = (0.96, 1.20)   # fan base / capacity: the smallest club ... the biggest
POSITION = ((3, 1.06), (6, 1.02), (14, 0.97), (17, 0.92), (99, 0.88))
FORM = (0.94, 0.04)            # x (0.94 + 0.04 x points a game over the last five)
MOOD_PER_POINT = 1 / 300.0     # fans' mood away from 50
BIG_VISITORS = 1.06            # one of the four biggest clubs
DERBY = 1.12
NOISE = (0.97, 1.03)
SOLD_OUT = 0.985               # at or over this share of the seats open: a sell-out
# The fan base after a season - judged against EXPECTATIONS (where the club's size says it should
# finish - the predicted finish), not the table: a small club in mid-table is doing well, a big one
# isn't.  Fans are loyal: it moves a little each year, and drifts back towards the club's natural
# level (its size and history) so it never runs away in either direction.
PER_PLACE = 0.006              # each place better (worse) than expected: +0.6% (-0.6%)
CHAMPIONS = 0.03               # winning the league: +3% on top
PULL_BACK = 0.15               # each year, 15% of the gap back towards the natural level
GROWTH = 0.005                 # crowds across the league slowly grow (+0.5% a year)
WAITING_LIST = 1.05            # the board: demand at least this x the seats = "there's a waiting list"
SELLOUTS_NEEDED = 0.75         # ...or this share of last season's (or this season's) games sold out


def _c(career, club):
    cr = career.setdefault("crowds", {}).setdefault(str(club["id"]), {})
    if "support" in cr and not cr.get("profiled") and "last" not in cr:
        pr = clubinfo.profile(club)
        if pr and pr.get("support"):                # (a profile written since: its fan base, once)
            cr["support"] = cr["base"] = pr["support"]
            cr["profiled"] = True
    if "support" not in cr:
        pr = clubinfo.profile(club)
        if pr and pr.get("support"):
            cr["support"] = pr["support"]
            cr["profiled"] = True
        else:
            from career import finance as fin
            n = fin.league_size(career, club)
            rank = fin.size_rank(career, club)
            big = 1 - rank / max(1, n - 1)
            cr["support"] = int(club["finance"]["capacity"] * (SUPPORT_RANGE[0] + (SUPPORT_RANGE[1] - SUPPORT_RANGE[0]) * big))
    cr.setdefault("base", cr["support"])        # (the club's natural level)
    cr.setdefault("games", [])
    return cr


def support(career, club):
    return _c(career, club)["support"]


def _position(career, club):
    from career import league
    if career.get("matchday", 1) <= 3:
        return None
    return league.position_of(career, club["id"])


def _form(career, club):
    """Points a game over the last five league games (1.4 if none yet)."""
    from career import league
    pts = []
    res = league.results_of(career, club["id"]) if 0 <= club["id"] < len(career["clubs"]) else {}
    for md in sorted(res, key=int, reverse=True):
        for r in res[md]:
            if club["id"] in (r["home"], r["away"]):
                gf, ga = (r["hg"], r["ag"]) if r["home"] == club["id"] else (r["ag"], r["hg"])
                pts.append(3 if gf > ga else 1 if gf == ga else 0)
        if len(pts) >= 5:
            break
    return sum(pts) / len(pts) if pts else 1.4


def _derby(home, away):
    pr = clubinfo.profile(home)
    return bool(pr and any(rv.get("club") == away["name"] and rv.get("derby") for rv in pr.get("rivals", [])))


def demand(career, home, away=None):
    """How many would come to this game (before the noise)."""
    d = support(career, home)
    pos = _position(career, home)
    if pos:
        d *= next(f for lim, f in POSITION if pos <= lim)
    d *= FORM[0] + FORM[1] * _form(career, home)
    if home["id"] == career.get("my_club"):
        from career import media
        d *= 1 + (media.mood(career) - 50) * MOOD_PER_POINT
    if away is not None:
        big = sorted(career["clubs"], key=lambda c: -c.get("strength", 0))[:4]
        if any(c["id"] == away["id"] for c in big):
            d *= BIG_VISITORS
        if _derby(home, away) or _derby(away, home):
            d *= DERBY
    return d


def home_game(career, home, away, date):
    """The crowd for a league game (recorded)."""
    cap = home["finance"]["capacity"]
    rng = random.Random(f"crowd:{home['id']}:{away['id']}:{date}")
    want = demand(career, home, away) * rng.uniform(*NOISE)
    att = int(cap * rng.uniform(SOLD_OUT, 1.0)) if want >= cap * SOLD_OUT else int(want)
    cr = _c(career, home)
    cr["games"].append({"date": date, "opp": away["id"], "att": att, "cap": cap})
    return att


def summary(games):
    if not games:
        return None
    n = len(games)
    avg = sum(g["att"] for g in games) / n
    pct = sum(g["att"] / g["cap"] for g in games) / n
    sold = sum(1 for g in games if g["att"] >= g["cap"] * SOLD_OUT)
    return {"avg": int(avg), "pct": pct, "sellouts": sold, "games": n,
            "best": max(games, key=lambda g: g["att"])["att"]}


def this_season(career, club):
    return summary(_c(career, club)["games"])


def last_season(career, club):
    return _c(career, club).get("last")


def demand_case(career, club, seats):
    """The board's question before building: is the demand there?  (yes, what they say)"""
    s = this_season(career, club)
    if not s or s["games"] < 8:
        s = last_season(career, club) or s
    if s and s["games"] >= 8:
        share = s["sellouts"] / s["games"]
        if share >= SELLOUTS_NEEDED:
            return True, f"{s['sellouts']} sell-outs in {s['games']} home games - the demand is there."
        return False, (f"The ground isn't full every week - {s['sellouts']} sell-outs in {s['games']} home games, "
                       f"{round(100 * s['pct'])}% full on average. The board won't spend that money on empty seats.")
    want = demand(career, club)
    if want >= seats * WAITING_LIST:
        return True, f"There's a waiting list - about {int(want - seats):,} more would come every week."
    return False, ("The board don't think there's the demand: the ground would hardly fill as it is. "
                   "Win more, and the crowds will follow.")


def expected_place(career, club):
    """Where the club's size says it should finish (as the papers predict)."""
    from career import finance as fin
    return fin.size_rank(career, club) + 1


def season_end(career, table):
    """The fan base after the season; this season's crowds become last season's."""
    for pos, row in enumerate(table, start=1):
        club = next((c for c in career["clubs"] if c["id"] == row["club"]), None)
        if club is None:
            continue
        cr = _c(career, club)
        change = PER_PLACE * (expected_place(career, club) - pos) + (CHAMPIONS if pos == 1 else 0) + GROWTH
        cr["base"] = cr["base"] * (1 + GROWTH)
        s = cr["support"] * (1 + change)
        s += (cr["base"] - s) * PULL_BACK
        cr["support"] = int(max(8000, s))
        cr["last"] = summary(cr["games"])
        cr["games"] = []
