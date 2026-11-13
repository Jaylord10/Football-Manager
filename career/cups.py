"""
career/cups.py
==============
The cup competitions.  This file has the machinery every knockout uses (draws, one-off ties and two-legged
ones, extra time and penalties, quick results, prize money) and the two English cups; the continental ones
are in career/europe.py and use the same pieces.

THE ASSOCIATION CUP (the FA Cup): the oldest cup in the world, the romance of the giant-killing.
  - the third round in early January: the 40 clubs of both divisions + 24 sides from the lower leagues
    (made up for each season - they only exist for the cup), drawn at random, one-off ties, the first club
    drawn at home
  - fourth round, fifth round and quarter-finals midweek; the semi-finals and the final at the national
    stadium; the final the Saturday after the league ends
  - level after 90 minutes: extra time, then penalties - no replays (the FA scrapped them from the first
    round proper in 2024-25)
  - prize money: the FA's own figures for 2026-27 (thefa.com prize fund) - third round winners £121,500
    (losers £26,500), fourth £127,000, fifth £238,500, quarter-final £477,000, semi-final £1,060,000
    (losers £530,000), the final £2,120,000 (runners-up £1,060,000); the home side keeps the gate

THE LEAGUE CUP: midweek, from August.
  - first round: Division 1's clubs below the top four (16); second round: the eight winners + Division 1's
    top four + the Premier Division's 20 (32); third round, quarter-finals one-off; the semi-finals over two
    legs (as the EFL Cup's are); the final at the national stadium on the Sunday of the March international
    break
  - small prize money, as in real life (the EFL Cup pays its winners about £100,000) - it's about the trophy
    and a place in Europe (the Continental Shield)

Your matches: watch them or take a quick result (the cup screen).  Watched, a match that decides a tie goes to
extra time and a penalty shoot-out in the match engine itself (gameplay/shootout.py) if it's level; a quick
result works them out like the play-offs' (career/playoffs.py).
Everyone else's: quick results on the day.

career["cups"]: {year, comps: {key: competition}, guests: {id: club}}
  competition: {key, name, rounds: [{name, dates, neutral, draw_on, size, entrants, ties: [...]}], matches,
                winner, runner_up}
  tie: {a, b, matches: [match ids], winner, how}
  match: {id, comp, round, tie, leg, date, home, away, neutral, result}
"""

import datetime as dt
import math
import random

from career import calendar as cal
from career import clubs as clubs_mod

ASSOC, LEAGUE_CUP = "association_cup", "league_cup"
NAMES = {ASSOC: "The Founders' Cup", LEAGUE_CUP: "The Charter Cup"}
SHORT = {ASSOC: "Founders' Cup", LEAGUE_CUP: "Charter Cup"}
# The Charter Cup has a sponsor - a new one every few years, as the real League Cup has had (the Milk
# Cup, Littlewoods, Rumbelows, Coca-Cola, Carling, Carabao): all made-up companies here
SPONSORS = ("Brightwater Dairies", "Halcyon Building Society", "Vantor Motors", "Orbix Mobile", "Pellmann Lager",
            "Thornbury Cider", "Redfern Tyres", "Sunburst Energy", "Mariner Insurance", "Castellan Bank",
            "Northlight Broadband", "Zephyr Airways", "Copperfield Crisps", "Ashdown Ales", "Lumen Electric")
SPONSOR_YEARS = (3, 5)
GUEST_BASE = 500                  # ids of the lower-league sides in the Association Cup
GUESTS = 24
GUEST_LEVEL = (36.0, 47.0)        # (Division 1's clubs ~41-58, the Premier Division's 52-77)
GUEST_TOWNS = ["Accrington Vale", "Barnsworth Town", "Chorley Albion", "Dagenby United", "Eastholme Town",
               "Fleetmouth", "Gainsby Trinity", "Harlow Athletic", "Ilkeston Rovers", "Kettlewell Town",
               "Leyton Orient Park", "Mansfield Wanderers", "Newport County Borough", "Oldmoor Athletic",
               "Port Vale Road", "Rochdale Moor", "Scunthorpe Steel", "Tranmere Rovers Park", "Walsall Wood",
               "Yeovil Glovers", "Altrincham Heath", "Boston Borough", "Crawley Green", "Dartford Bridge",
               "Ebbsfleet Town", "Forest Green Vale", "Grimsby Docks", "Hartlepool Bay", "Lincoln Imps United",
               "Morecambe Bay", "Notts Meadow", "Salford Quays", "Stevenage Old Town", "Wrexham Road"]
PRIZE = {ASSOC: {"Third round": (121_500, 26_500), "Fourth round": (127_000, 0), "Fifth round": (238_500, 0),
                 "Quarter-final": (477_000, 0), "Semi-final": (1_060_000, 530_000), "Final": (2_120_000, 1_060_000)},
         LEAGUE_CUP: {"Final": (100_000, 50_000)}}
CUP_CROWD = 0.85                  # a cup tie's crowd: this share of the ground (cup crowds are often a bit down)


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
def _nth(year, month, weekday, n):
    return cal._nth_weekday(year, month, weekday, n)


def _y(month, start):
    return start if month >= 7 else start + 1


def _free_saturday(career, start, after, before):
    """The first Saturday in [after, before] without a league round (the FA Cup's third-round weekend)."""
    league_days = set(career.get("calendar") or [])
    d = after + dt.timedelta(days=(5 - after.weekday()) % 7)
    while d <= before:
        if d.isoformat() not in league_days and all(abs((d - cal.parse(x)).days) >= 2 for x in league_days):
            return d
        d += dt.timedelta(weeks=1)
    return _nth(after.year, after.month, 2, 2)                       # (no free Saturday: a Wednesday)


def _after_league(career, days):
    last = cal.parse((career.get("calendar") or [career["date"]])[-1])
    return last + dt.timedelta(days=days)


def assoc_rounds(career, y):
    """[(name, [dates], neutral, draw_on)] for the season starting in July of y."""
    r3 = _free_saturday(career, y, dt.date(y + 1, 1, 3), dt.date(y + 1, 1, 20))
    return [("Third round", [r3], False, dt.date(y, 12, 1)),
            ("Fourth round", [_nth(y + 1, 1, 2, 4)], False, None),
            ("Fifth round", [_nth(y + 1, 2, 2, 3)], False, None),
            ("Quarter-final", [_nth(y + 1, 3, 2, 2)], False, None),
            ("Semi-final", [_nth(y + 1, 4, 2, 3)], True, None),
            ("Final", [_after_league(career, 7)], True, None)]


def league_cup_rounds(career, y):
    first = cal.parse((career.get("calendar") or [f"{y}-08-15"])[0])
    r1 = first + dt.timedelta(days=(2 - first.weekday()) % 7 + 7)          # the second Wednesday of the season
    brk = [cal.parse(b) for b in career.get("breaks") or [] if b[5:7] == "03"]
    final = (brk[0] + dt.timedelta(days=1)) if brk else _nth(y + 1, 3, 6, 4)
    return [("First round", [r1], False, None),
            ("Second round", [_nth(y, 9, 2, 4)], False, None),
            ("Third round", [_nth(y, 10, 2, 4)], False, None),
            ("Quarter-final", [_nth(y, 12, 2, 3)], False, None),
            ("Semi-final", [_nth(y + 1, 1, 2, 2), _nth(y + 1, 2, 2, 1)], False, None),
            ("Final", [final], True, None)]


# ---------------------------------------------------------------------------
# Clubs (any club that can play a cup match: ours, Spain's, the lower-league sides, the continent's)
# ---------------------------------------------------------------------------
def club(career, cid):
    if cid is None:
        return None
    if 0 <= cid < len(career["clubs"]):
        return career["clubs"][cid]
    g = (career.get("cups") or {}).get("guests", {}).get(str(cid))
    if g is not None:
        return g
    from career import europe, foreign
    c = europe.club(career, cid) or foreign.club(career, cid)
    if c is not None:
        return c
    from career import spain
    if spain.exists(career) and spain.ID_BASE <= cid < spain.ID_BASE + len(career["spain"]["clubs"]):
        return spain.club(career, cid)
    return None


def name(career, cid, short=False):
    c = club(career, cid)
    if c is None:
        return "?"
    return (c.get("short") or c["name"]) if short else c["name"]


def _make_side(rng, cid, nm, level, used):
    """A made-up club for a cup run (or a continental tie): a squad of 25 at this level."""
    c = {"id": cid, "name": nm, "short": nm.split(" ")[0] if len(nm.split(" ")[0]) > 3 else nm,
         "colour": [rng.randint(40, 230), rng.randint(40, 230), rng.randint(40, 230)], "strength": round(level),
         "roles": {"base": rng.choice(["blue", "red"])}, "league": "guest",
         "tactics": {"defence": rng.choice(["low_block", "mid_block"]), "build_up": rng.choice(["clear", "mixed"])},
         "instructions": {}, "players": clubs_mod._squad_25(rng, level, used)}
    for p in c["players"]:
        p["condition"] = 1.0
        p["homegrown"] = True
    c["registered"] = [p["id"] for p in c["players"]]
    c["lineup"] = clubs_mod.best_lineup(c)
    return c


def _guests(career, rng):
    used = {p["Name"] for c in career["clubs"] for p in c["players"]}
    towns = rng.sample(GUEST_TOWNS, GUESTS)
    out = {}
    for i, nm in enumerate(towns):
        lv = rng.uniform(*GUEST_LEVEL)
        out[str(GUEST_BASE + i)] = _make_side(rng, GUEST_BASE + i, nm, lv, used)
    return out


# ---------------------------------------------------------------------------
# Setting up a season's cups
# ---------------------------------------------------------------------------
def state(career):
    cu = career.get("cups")
    return cu if cu and cu.get("year") == career.get("year") else None


def _comp(key, nm, rounds):
    return {"key": key, "name": nm, "matches": [], "winner": None, "runner_up": None, "next_id": 0,
            "rounds": [{"name": n, "dates": [d.isoformat() for d in ds], "neutral": neu,
                        "draw_on": dw.isoformat() if dw else None, "entrants": [], "ties": [], "drawn": False}
                       for n, ds, neu, dw in rounds]}


def _rank_order(career, div):
    """A division's clubs, best first: last season's table if there is one, else by size."""
    from career import divisions
    clubs = divisions.clubs_in(career, div)
    last = (career.get("history") or [{}])[-1].get("tables", {})
    prev = []
    for d in ("pl", "d1"):
        prev += last.get(d, [])
    pos = {cid: i for i, cid in enumerate(prev)}
    return sorted(clubs, key=lambda c: (pos.get(c["id"], 999), -c.get("strength", 0)))


def create(career):
    """The season's English cups (called at the start of a season, and for older saves)."""
    from career import divisions
    y = career.get("year", 2026)
    rng = random.Random(f"cups:{y}")
    cu = career["cups"] = {"year": y, "comps": {}, "guests": _guests(career, rng)}
    ac = cu["comps"][ASSOC] = _comp(ASSOC, NAMES[ASSOC], assoc_rounds(career, y))
    ac["rounds"][0]["entrants"] = [c["id"] for c in career["clubs"]] + [int(k) for k in cu["guests"]]
    lc = cu["comps"][LEAGUE_CUP] = _comp(LEAGUE_CUP, charter_name(career), league_cup_rounds(career, y))
    if divisions.exists(career):
        d1 = [c["id"] for c in _rank_order(career, "d1")]
        lc["rounds"][0]["entrants"] = d1[4:]
        lc["rounds"][1]["entrants"] = d1[:4] + [c["id"] for c in divisions.clubs_in(career, "pl")]
    else:                                             # (one division: everyone from the second round)
        lc["rounds"] = lc["rounds"][1:]
        lc["rounds"][0]["entrants"] = [c["id"] for c in career["clubs"]][:32]
    from career import europe
    europe.create(career)                             # (the continental cups: career/europe.py)
    _draws_due(career, career.get("date"))


def sponsor(career):
    """The Charter Cup's sponsor this season: a deal runs 3-5 seasons, then someone new."""
    y = career.get("year", 2026)
    s = career.get("charter_sponsor")
    if s and s.get("from", 0) <= y < s.get("until", 0):
        return s["name"]
    rng = random.Random(f"sponsor:{y}")
    old = (s or {}).get("name")
    name = rng.choice([x for x in SPONSORS if x != old])
    career["charter_sponsor"] = {"name": name, "from": y, "until": y + rng.randint(*SPONSOR_YEARS)}
    career.setdefault("charter_sponsors", []).append({"name": name, "from": y})
    if old:
        from career import transfers as trf
        trf._message(career, "news", f"The Charter Cup has a new sponsor: from this season it's the {name} "
                                     f"Charter Cup (after {old}).")
    return name


def charter_name(career):
    return f"The {sponsor(career)} Charter Cup"


def ensure(career):
    """Older saves / a new season: this season's cups exist; anything already due is played (quick).
    (And the names are this season's - older saves had the old ones.)"""
    if state(career) is None:
        create(career)
        catch_up(career)
    from career import europe
    for comp in comps(career):
        k = comp["key"]
        comp["name"] = charter_name(career) if k == LEAGUE_CUP else NAMES.get(k) or europe.NAMES.get(k, comp["name"])
        if k in europe.SHORTS:
            comp["short"] = europe.SHORTS[k]


def comps(career):
    """Every competition this season (English cups first, then the continental ones)."""
    cu = state(career)
    if not cu:
        return []
    from career import europe
    return list(cu["comps"].values()) + europe.comps(career)


# ---------------------------------------------------------------------------
# Draws
# ---------------------------------------------------------------------------
def _round_done(rd):
    return rd["drawn"] and all(t["winner"] is not None for t in rd["ties"])


def _draws_due(career, iso):
    for comp in comps(career):
        if comp.get("kind") == "groups":
            continue
        draw_rounds(career, comp, iso)


def draw_rounds(career, comp, iso):
    """Make any draw that's due: the previous round's done and (if it has one) the draw date's come."""
    rng = random.Random(f"draw:{comp['key']}:{career.get('year')}:{iso}")
    for i, rd in enumerate(comp["rounds"]):
        if rd["drawn"]:
            continue
        if i > 0 and not _round_done(comp["rounds"][i - 1]):
            return
        if rd.get("draw_on") and iso and iso < rd["draw_on"]:
            return
        prev_winners = [t["winner"] for t in comp["rounds"][i - 1]["ties"]] if i > 0 else []
        pool = list(rd["entrants"]) + prev_winners
        if len(pool) < 2:
            if pool:
                _won(career, comp, pool[0], None, None)
            return
        _draw(career, comp, i, pool, rng)


def _draw(career, comp, i, pool, rng):
    rd = comp["rounds"][i]
    pool = list(pool)
    rng.shuffle(pool)
    if len(pool) % 2:
        pool.append(None)                              # (an odd number: a bye)
    for k in range(0, len(pool), 2):
        a, b = pool[k], pool[k + 1]
        tie = {"a": a, "b": b, "matches": [], "winner": None, "how": None}
        t_i = len(rd["ties"])
        rd["ties"].append(tie)
        if b is None:
            tie["winner"], tie["how"] = a, "bye"
            continue
        legs = rd["dates"]
        for leg, d in enumerate(legs, start=1):
            home, away = (a, b) if leg % 2 else (b, a)
            m = {"id": f"{comp['key']}:{comp['next_id']}", "comp": comp["key"], "round": i, "tie": t_i,
                 "leg": leg if len(legs) > 1 else None, "date": d, "home": home, "away": away,
                 "neutral": rd["neutral"], "result": None}
            comp["next_id"] += 1
            comp["matches"].append(m)
            tie["matches"].append(m["id"])
            if rd["name"] != "Final":
                space(career, m)
    rd["drawn"] = True
    _draw_news(career, comp, i)


MIN_GAP = 2                       # days between two matches for a club (real fixtures: never less than ~48 hours)
SHIFTS = (0, 1, -1, 2, -2, 3, -3, 6, -6, 7, -7)


def _busy(career, cid, skip):
    """The dates a club is already playing (league days for English clubs; every cup match)."""
    out = set()
    if cid is not None and 0 <= cid < len(career["clubs"]):
        from career import league
        out |= {league.match_date(career, md, cid) for md in range(1, len(career.get("calendar") or []) + 1)}
        out.discard(None)
    for comp in comps(career):
        for x in comp["matches"]:
            if x["id"] != skip and cid in (x["home"], x["away"]) and x.get("result") is None:
                out.add(x["date"])
    return out


def space(career, m):
    """A tie that lands on (or next to) another match for either club is moved a day or two - as real
    cup ties are rearranged when a club's in Europe or has a league game."""
    busy = [cal.parse(d) for d in _busy(career, m["home"], m["id"]) | _busy(career, m["away"], m["id"])]
    d0 = cal.parse(m["date"])
    today = cal.parse(career.get("date") or m["date"])
    for s in SHIFTS:
        d = d0 + dt.timedelta(days=s)
        if d <= today:
            continue
        if all(abs((d - b).days) >= MIN_GAP for b in busy):
            m["date"] = d.isoformat()
            return


def _draw_news(career, comp, i):
    rd = comp["rounds"][i]
    me = career["my_club"]
    for t in rd["ties"]:
        if me in (t["a"], t["b"]) and t["b"] is not None:
            opp = t["b"] if t["a"] == me else t["a"]
            m = match(career, t["matches"][0])
            where = f"at {VENUE}" if m["neutral"] else ("at home" if m["home"] == me else "away")
            from career import transfers as trf
            legs = " (two legs)" if len(t["matches"]) > 1 else ""
            trf._message(career, "news", f"{comp['name']}, {rd['name'].lower()}: {name(career, opp)}{legs}, "
                                         f"{where} - {cal.fmt(m['date'], False)}.")


# ---------------------------------------------------------------------------
# Matches
# ---------------------------------------------------------------------------
def match(career, mid):
    for comp in comps(career):
        for m in comp["matches"]:
            if m["id"] == mid:
                return m
    return None


def comp_of(career, m):
    return next(c for c in comps(career) if c["key"] == m["comp"])


def all_matches(career):
    out = []
    for comp in comps(career):
        out += comp["matches"]
    return sorted(out, key=lambda m: (m["date"], m["id"]))


def involved(career, m):
    return career["my_club"] in (m["home"], m["away"])


def my_next(career, before=None):
    """Your next unplayed cup match (on or after today; before `before` if given) - or None."""
    if state(career) is None:
        return None
    today = career.get("date", "")
    for m in all_matches(career):
        if m["result"] is None and involved(career, m) and m["date"] >= today and (before is None or m["date"] < before):
            return m
    return None


ROTATE = {LEAGUE_CUP: ("First round", "Second round", "Third round"), ASSOC: ("Third round", "Fourth round")}
ROTATE_REST = 5                    # a big club's early cup ties: its best five rested (the kids and the squad get a game)


def _rotating(career, c, m):
    """Does an AI manager rest his best players for this tie?  Premier Division clubs do in the League Cup's early
    rounds and the Association Cup's third and fourth rounds - unless the other side's from their own level."""
    if m is None or c.get("league") != "pl":
        return False
    if comp_of(career, m)["rounds"][m["round"]]["name"] not in ROTATE.get(m["comp"], ()):
        return False
    other = club(career, m["away"] if m["home"] == c["id"] else m["home"])
    return other is None or other.get("league") != "pl"


def _xi(career, c, date, vs, m=None):
    from career import spain, availability as av
    if c["id"] == career["my_club"] and c.get("lineup"):
        return c["lineup"]
    if m is not None and m.get("round") is not None and _rotating(career, c, m):
        rest = sorted((p for p in c["players"] if not av.injured(p, date)), key=lambda p: -clubs_mod.overall(p))[:ROTATE_REST]
        keep = c.get("lineup")
        xi = clubs_mod.best_lineup(c, exclude={p["id"] for p in rest} | {p["id"] for p in c["players"] if av.injured(p, date)})
        if len(xi) >= 11:
            c["lineup"] = keep                 # (the league side's untouched)
            return xi
    xi = spain.pick_xi(c, date, vs)
    c["lineup"] = xi
    return xi


def quick(career, m, rng=None):
    """A quick result for a cup match (90 minutes)."""
    from career import spain
    rng = rng or random.Random(f"cup:{career.get('year')}:{m['id']}:{m['home']}:{m['away']}:"
                               f"{len(career.get('transfer_log') or [])}")
    H, A = club(career, m["home"]), club(career, m["away"])
    hxi, axi = _xi(career, H, m["date"], A["id"], m), _xi(career, A, m["date"], H["id"], m)
    d = spain.xi_rating(H, hxi) - spain.xi_rating(A, axi)
    hl, al = spain.HOME_GOALS, spain.AWAY_GOALS
    if m["neutral"]:
        hl = al = (spain.HOME_GOALS + spain.AWAY_GOALS) / 2
    hg = spain._poisson(rng, hl * math.exp(spain.GOALS_PER_POINT * d))
    ag = spain._poisson(rng, al * math.exp(-spain.GOALS_PER_POINT * d))
    goals, players = [], []
    for side, c, xi, n in ((0, H, hxi, hg), (1, A, axi, ag)):
        for _ in range(n):
            p = spain._scorer(rng, c, xi)
            goals.append({"team": side, "name": p["Name"], "pid": p["id"], "minute": rng.randint(1, 90)})
        for pid in xi.values():
            a = {"team": side, "id": pid, "minutes": 90, "start": 1, "yellow": 0, "red": None,
                 "stamina": round(rng.uniform(0.62, 0.8), 3)}
            if rng.random() < spain.MATCH_INJURY:
                a["injury"] = {"minute": rng.randint(1, 90), "knock": rng.random() < 0.4}
            players.append(a)
    goals.sort(key=lambda g: g["minute"])
    return {"home": H["id"], "away": A["id"], "hg": hg, "ag": ag, "goals": goals, "players": players, "quick": True}


def _shootout(rng, H, A):
    from career import playoffs
    return playoffs._shootout(rng, H, A)


def _extra_time(career, m, rng):
    from career import spain, playoffs
    H, A = club(career, m["home"]), club(career, m["away"])
    d = spain.xi_rating(H, H.get("lineup") or {}) - spain.xi_rating(A, A.get("lineup") or {})
    base = (spain.HOME_GOALS + spain.AWAY_GOALS) / 2 * playoffs.ET_SHARE
    return (spain._poisson(rng, base * math.exp(spain.GOALS_PER_POINT * d)),
            spain._poisson(rng, base * math.exp(-spain.GOALS_PER_POINT * d)))


def record(career, m, r, rng=None):
    """A cup match is over: extra time / penalties if the tie needs them; fitness, knocks, the gate;
    who goes through (and the next draw, if it's due)."""
    comp = comp_of(career, m)
    rng = rng or random.Random(f"cup-after:{m['id']}:{r['hg']}:{r['ag']}:{career.get('year')}")
    res = {"hg": r["hg"], "ag": r["ag"], "quick": bool(r.get("quick")),
           "goals": [{"team": g["team"], "name": g["name"], "minute": g.get("minute"), "pid": g.get("pid")}
                     for g in r.get("goals", [])]}
    m["result"] = res
    if m.get("group") is not None:                     # (a continental group match - career/europe.py)
        _after(career, m, r, rng)
        from career import europe
        europe.record_group(career, comp, m, res)
        return res
    rd = comp["rounds"][m["round"]]
    tie = rd["ties"][m["tie"]] if m.get("tie") is not None else None
    if tie is not None:
        ms = [match(career, x) for x in tie["matches"]]
        last = all(x["result"] is not None for x in ms)
        if last:
            # aggregate from this match's home side's point of view
            agg_h = sum(x["result"]["hg"] if x["home"] == m["home"] else x["result"]["ag"] for x in ms)
            agg_a = sum(x["result"]["ag"] if x["home"] == m["home"] else x["result"]["hg"] for x in ms)
            if len(ms) > 1:
                res["agg"] = [agg_h, agg_a]
            how = None
            if agg_h == agg_a:
                eh, ea = r["et"] if r.get("et") is not None else _extra_time(career, m, rng)   # (engine: played)
                res["et"] = [eh, ea]
                agg_h, agg_a = agg_h + eh, agg_a + ea
                if len(ms) > 1:
                    res["agg"] = [agg_h, agg_a]
                if agg_h == agg_a:
                    ph, pa = (r["pens"] if r.get("pens") is not None else
                              _shootout(rng, club(career, m["home"]), club(career, m["away"])))
                    res["pens"] = [ph, pa]
                    how = "pens"
                    winner = m["home"] if ph > pa else m["away"]
                else:
                    how = "et"
                    winner = m["home"] if agg_h > agg_a else m["away"]
            else:
                winner = m["home"] if agg_h > agg_a else m["away"]
            tie["winner"], tie["how"] = winner, how or "90"
            loser = m["away"] if winner == m["home"] else m["home"]
            _prize(career, comp, rd, winner, loser)
            if rd["name"] == "Final":
                _won(career, comp, winner, loser, m)
    _after(career, m, r, rng)
    from career import media
    media.cup_story(career, comp, m)
    draw_rounds(career, comp, m["date"])
    return res


def knockout_info(career, m):
    """For the match engine: does this match decide its tie?  {"agg": [home, away]} - the goals from the
    earlier legs, from this match's home side's point of view - or None (a first leg, a group match)."""
    if m.get("group") is not None or m.get("tie") is None:
        return None
    comp = comp_of(career, m)
    tie = comp["rounds"][m["round"]]["ties"][m["tie"]]
    others = [match(career, x) for x in tie["matches"] if x != m["id"]]
    if any(x is None or x["result"] is None for x in others):
        return None
    h = sum(x["result"]["hg"] if x["home"] == m["home"] else x["result"]["ag"] for x in others)
    a = sum(x["result"]["ag"] if x["home"] == m["home"] else x["result"]["hg"] for x in others)
    return {"agg": [h, a]}


def _won(career, comp, winner, loser, m):
    comp["winner"], comp["runner_up"] = winner, loser
    from career import transfers as trf
    me = career["my_club"]
    if me == winner:
        trf._message(career, "news", f"CUP WINNERS! You've won {comp['name']}.")
        from career import board
        board._bump(career, 12, f"{comp['name']} won")
    elif me == loser:
        trf._message(career, "news", f"Beaten in the final of {comp['name']} - so close.")


def _prize(career, comp, rd, winner, loser):
    from career import finance as fin, europe
    if rd["name"] == "Final":                                   # (the players' bonus for a trophy)
        wc = club(career, winner)
        if wc is not None and "finance" in wc:
            fin.bonus(career, wc, fin.CUP_BONUS.get(comp["key"], 0.03))
    if comp["key"] in (europe.CC, europe.SHIELD, europe.WORLD):
        return europe.final_prizes(career, comp, rd, winner, loser)
    w, l = PRIZE.get(comp["key"], {}).get(rd["name"], (0, 0))
    for cid, amount in ((winner, w), (loser, l)):
        c = club(career, cid)
        if amount and c is not None and "finance" in c:
            fin._book(c, "prize", amount)


def _after(career, m, r, rng):
    """Fitness and knocks; the home side's gate (English clubs)."""
    from career import training, finance, availability as av
    training.after_match(career, [r])
    for a in r.get("players", []):
        inj = a.get("injury")
        if not inj:
            continue
        cid = r["home"] if a["team"] == 0 else r["away"]
        c = club(career, cid)
        p = clubs_mod.player_by_id(c, a["id"]) if c else None
        if p is None:
            continue
        if inj.get("knock"):
            if not av.injured(p, m["date"]):
                until = (cal.parse(m["date"]) + dt.timedelta(days=rng.randint(1, 3))).isoformat()
                p["injury"] = {"name": "Knock", "since": m["date"], "until": until, "cause": "match"}
        elif 0 <= cid < len(career["clubs"]):
            av._injure(career, c, p, m["date"], "match", rng, inj.get("minute"))
        else:
            name_, days = av.roll_injury(rng)
            p["injury"] = {"name": name_, "since": m["date"], "cause": "match",
                           "until": (cal.parse(m["date"]) + dt.timedelta(days=days)).isoformat()}
    H = club(career, m["home"])
    if not m["neutral"] and H is not None and "finance" in H and 0 <= H["id"] < len(career["clubs"]):
        finance.home_game(career, H, int(H["finance"]["capacity"] * CUP_CROWD))


# ---------------------------------------------------------------------------
# Every day (career/transfers.py on_day): draws, and everyone else's matches
# ---------------------------------------------------------------------------
def day(career, iso, rng=None):
    if state(career) is None:
        return
    _draws_due(career, iso)
    from career import europe
    europe.day(career, iso)
    for m in all_matches(career):
        if m["result"] is not None or m["date"] > iso or m["home"] is None:
            continue
        if involved(career, m) and m["date"] >= iso:
            continue                                   # (yours: you play it - unless it's been missed)
        record(career, m, quick(career, m))
    _draws_due(career, iso)


def catch_up(career):
    """Everything dated before today (an older save starting its cups mid-season)."""
    today = career.get("date", "")
    prev = (cal.parse(today) - dt.timedelta(days=1)).isoformat() if today else today
    for _ in range(60):
        before = sum(1 for m in all_matches(career) if m["result"] is None)
        day(career, prev)
        if sum(1 for m in all_matches(career) if m["result"] is None) == before:
            break


def finish_all(career):
    """The summer: anything still to play (yours too) - quick results."""
    if state(career) is None:
        return
    far = "9999-12-31"
    for _ in range(200):
        _draws_due(career, far)
        from career import europe
        europe.day(career, far)
        todo = [m for m in all_matches(career) if m["result"] is None and m["home"] is not None]
        if not todo:
            _draws_due(career, far)
            if not [m for m in all_matches(career) if m["result"] is None and m["home"] is not None]:
                break
            continue
        for m in todo:
            record(career, m, quick(career, m))


def season_end(career):
    """The cups' winners into the record (career["cup_history"]) - for the honours and next season's Europe."""
    finish_all(career)
    cu = state(career)
    if not cu:
        return {}
    out = {"year_end": career.get("year", 2026) + 1}
    for comp in comps(career):
        out[comp["key"]] = [comp.get("winner"), comp.get("runner_up")]
        out[comp["key"] + "_names"] = [name(career, comp.get("winner")), name(career, comp.get("runner_up"))]
        if comp.get("year_label"):
            out[comp["key"] + "_year"] = comp["year_label"]
    career.setdefault("cup_history", []).append(out)
    career["cup_history"] = career["cup_history"][-60:]
    return out


# ---------------------------------------------------------------------------
# For the screens
# ---------------------------------------------------------------------------
def round_lines(career, comp, i):
    """[(text, is_mine)] for a round's ties."""
    rd = comp["rounds"][i]
    out = []
    for t in rd["ties"]:
        if t["b"] is None:
            out.append((f"{name(career, t['a'])} - a bye", career["my_club"] == t["a"]))
            continue
        ms = [match(career, x) for x in t["matches"]]
        parts = []
        for m in ms:
            r = m["result"]
            if r is None:
                parts.append(f"{name(career, m['home'], True)} v {name(career, m['away'], True)}  ·  {cal.fmt(m['date'], False)}")
            else:
                s = f"{name(career, m['home'], True)} {r['hg']}-{r['ag']} {name(career, m['away'], True)}"
                if r.get("et"):
                    s += f" (aet {r['hg'] + r['et'][0]}-{r['ag'] + r['et'][1]})"
                if r.get("pens"):
                    s += f", {r['pens'][0]}-{r['pens'][1]} pens"
                if r.get("agg"):
                    s += f"  ·  agg {r['agg'][0]}-{r['agg'][1]}"
                parts.append(s)
        mine = career["my_club"] in (t["a"], t["b"])
        out.append(("   |   ".join(parts), mine))
        if rd["name"] == "Final" and len(ms) == 1:              # (the final: where, when, who scored)
            m = ms[0]
            out.append((f"{venue(career, comp)}  ·  {cal.fmt(m['date'], False)}", False))
            r = m["result"]
            if r and r.get("goals"):
                for side, cid in ((0, m["home"]), (1, m["away"])):
                    gs = [f"{g['name']} {g['minute']}'" if g.get("minute") else g["name"]
                          for g in r["goals"] if g.get("team") == side]
                    if gs:
                        out.append((f"{name(career, cid, True)}: " + ", ".join(gs), False))
    return out


FINAL_CITIES = ("Lisbon", "Vienna", "Amsterdam", "Munich", "Madrid", "Milan", "Paris", "Istanbul", "Athens",
                "Budapest", "Glasgow", "Seville", "Prague", "Copenhagen")


def venue(career, comp):
    """Where a final is played: the national stadium for our cups; a different city each year for Europe's."""
    if comp["key"] in (ASSOC, LEAGUE_CUP):
        return VENUE[0].upper() + VENUE[1:]
    y = career.get("year", 2026)
    k = (y * 7 + (3 if comp["key"] == "shield" else 0) + (5 if comp["key"] == "world_club" else 0)) % len(FINAL_CITIES)
    return f"The final in {FINAL_CITIES[k]}"


def my_status(career, comp):
    """'Still in: fifth round' / 'Out: third round' / 'Winners' / 'Not entered'."""
    me = career["my_club"]
    if comp.get("winner") == me:
        return "Winners!"
    entered = False
    for rd in comp["rounds"]:
        for t in rd["ties"]:
            if me in (t["a"], t["b"]):
                entered = True
                if t["winner"] is not None and t["winner"] != me:
                    return f"Out in the {rd['name'].lower()}"
                if t["winner"] is None:
                    return f"In the {rd['name'].lower()}"
        if me in rd.get("entrants", []):
            entered = True
    if comp.get("kind") == "groups":
        from career import europe
        return europe.my_status(career, comp)
    return "Waiting for the draw" if entered else "Not in it"


VENUE = "the National Bowl"


def SHORT_ANY(comp):
    return comp.get("short") or SHORT.get(comp["key"], comp["name"])


def round_name(career, m):
    comp = comp_of(career, m)
    if m.get("group") is not None:
        return f"Group {m['group']}, matchday {m.get('gmd', '')}"
    rd = comp["rounds"][m["round"]]
    return rd["name"] + (f", {'first' if m['leg'] == 1 else 'second'} leg" if m.get("leg") else "")


def tie_note(career, m):
    """Under 'v' on the cup screen."""
    if m.get("group") is not None:
        return "Group stage: three points for a win - the top two go through"
    comp = comp_of(career, m)
    rd = comp["rounds"][m["round"]]
    t = rd["ties"][m["tie"]]
    if m.get("leg") == 2:
        first = match(career, t["matches"][0])["result"]
        if first:
            return (f"First leg: {name(career, m['away'], True)} {first['hg']}-{first['ag']} "
                    f"{name(career, m['home'], True)}  ·  level on aggregate: extra time, then penalties")
    if m.get("leg") == 1:
        return "First leg of two"
    return "One match: level after 90 minutes - extra time, then penalties"


def stages(career, comp):
    """[(label, lines function)] for the cups screen: the groups (if any), then each round."""
    out = []
    if comp.get("kind") == "groups":
        from career import europe
        out += europe.group_stages(career, comp)
    for i, rd in enumerate(comp["rounds"]):
        label = {"Third round": "Round 3", "Fourth round": "Round 4", "Fifth round": "Round 5",
                 "First round": "Round 1", "Second round": "Round 2", "Quarter-final": "Quarter-finals",
                 "Semi-final": "Semi-finals"}.get(rd["name"], rd["name"])
        out.append((label, lambda i=i: round_lines(career, comp, i)))
    return out


def current_stage(career, comp):
    """The stage to show first: the latest one that's been drawn."""
    st = stages(career, comp)
    n_groups = len(st) - len(comp["rounds"])
    cur = 0
    me = career["my_club"]
    for k, g in enumerate(comp.get("groups") or {}):            # (in the groups: yours, if you're in one)
        if any(me in (m["home"], m["away"]) for m in comp["matches"] if m.get("group") == g):
            cur = k
    for i, rd in enumerate(comp["rounds"]):
        if rd["drawn"]:
            cur = n_groups + i
    return cur
