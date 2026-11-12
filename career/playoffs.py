"""
career/playoffs.py
==================
The DIVISION 1 PLAY-OFFS: the third promotion place (career/divisions.py).

  - 3rd v 6th and 4th v 5th, over two legs: the lower-placed club at home first, the higher-placed
    club at home in the second leg (as the EFL does).  Level on aggregate after the second leg:
    extra time, then penalties - no away goals (gone from the EFL play-offs since 2021).
  - THE FINAL: one match at the national stadium (neutral - no home advantage); level after 90
    minutes: extra time, then penalties.  The winner goes up with the top two.
  - Dates: the first legs four days after the last league games, the second legs three days
    later, the final a week after that (the EFL: mid-May semis, the final at the end of May).
  - Your matches: watch them or take a quick result, like a league match.  The match engine
    plays 90 minutes, so if a tie is still level the extra time and the shoot-out are quick
    results (the engine has no extra time or shoot-outs yet).  Everyone else's: quick results.

career["playoffs"]: {year, seeds [3rd, 4th, 5th, 6th], matches: [{id, round, tie, leg, date, home,
away, neutral, result}], ties: [{a, b, winner, how}], final: {winner, how}, winner}
"""

import datetime as dt
import math
import random

from career import calendar as cal
from career import clubs as clubs_mod

DIV = "d1"
SEEDS = (3, 4, 5, 6)
FIRST_LEG_DAYS = 4                 # after the last league game
SECOND_LEG_DAYS = 7
FINAL_DAYS = 14
VENUE = "the National Stadium"
ET_SHARE = 1 / 3                   # extra time: a third of a match's goals
PEN_SCORE = (0.62, 0.86)           # a penalty taker's chance, worst to best (Penalties 0-100) - ~76% on average


def state(career):
    return career.get("playoffs") if (career.get("playoffs") or {}).get("year") == career.get("year") else None


def ready(career):
    """Division 1's league season is over (both divisions play the same rounds)."""
    from career import divisions, league
    if not divisions.exists(career):
        return False
    if divisions.my_div(career) == DIV:
        return league.season_over(career)
    o = career["other"]
    return o["matchday"] > len(o["fixtures"])


def ensure(career):
    """Set the play-offs up once Division 1's season is over.  Returns the state (or None)."""
    st = state(career)
    if st or not ready(career):
        return st
    from career import league
    t = league.table(career, DIV)
    seeds = [t[i - 1]["club"] for i in SEEDS]
    last = cal.parse((career.get("calendar") or [career["date"]])[-1])
    d1 = (last + dt.timedelta(days=FIRST_LEG_DAYS)).isoformat()
    d2 = (last + dt.timedelta(days=SECOND_LEG_DAYS)).isoformat()
    df = (last + dt.timedelta(days=FINAL_DAYS)).isoformat()
    ties = [{"a": seeds[0], "b": seeds[3], "winner": None, "how": None},     # 3rd v 6th
            {"a": seeds[1], "b": seeds[2], "winner": None, "how": None}]     # 4th v 5th
    ms = []
    for k, tie in enumerate(ties):
        ms.append({"id": f"sf{k + 1}a", "round": "semi", "tie": k, "leg": 1, "date": d1,
                   "home": tie["b"], "away": tie["a"], "neutral": False, "result": None})
        ms.append({"id": f"sf{k + 1}b", "round": "semi", "tie": k, "leg": 2, "date": d2,
                   "home": tie["a"], "away": tie["b"], "neutral": False, "result": None})
    ms.append({"id": "final", "round": "final", "tie": None, "leg": None, "date": df,
               "home": None, "away": None, "neutral": True, "result": None})
    career["playoffs"] = {"year": career.get("year"), "seeds": seeds, "ties": ties, "matches": ms,
                          "final": {"winner": None, "how": None}, "winner": None}
    from career import transfers as trf
    me = career["my_club"]
    if me in seeds:
        opp = next(t["a"] if t["b"] == me else t["b"] for t in ties if me in (t["a"], t["b"]))
        trf._message(career, "news", f"The play-offs: you finished {_ord(seeds.index(me) + 3)} and meet "
                                     f"{career['clubs'][opp]['name']} in the semi-final - first leg "
                                     f"{cal.fmt(d1, False)}, second leg {cal.fmt(d2, False)}. "
                                     f"The final is at {VENUE} on {cal.fmt(df, False)}.")
    return career["playoffs"]


def _ord(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def involved(career, m):
    return career["my_club"] in (m["home"], m["away"])


def next_match(career):
    st = state(career)
    if not st:
        return None
    for m in st["matches"]:
        if m["result"] is None and m["home"] is not None:
            return m
    return None


def my_next(career):
    """Your next play-off match (or None)."""
    st = ensure(career)
    if not st:
        return None
    for m in st["matches"]:
        if m["result"] is None and m["home"] is not None and involved(career, m):
            return m
    return None


def still_in(career):
    """Are you in the play-offs and not yet out?"""
    st = ensure(career)
    if not st or career["my_club"] not in st["seeds"]:
        return False
    if st["winner"] is not None:
        return False
    for t in st["ties"]:
        if career["my_club"] in (t["a"], t["b"]) and t["winner"] is not None and t["winner"] != career["my_club"]:
            return False
    return True


def done(career):
    st = state(career)
    return bool(st and st["winner"] is not None)


# ---------------------------------------------------------------------------
# Playing them
# ---------------------------------------------------------------------------
def _xi(career, club, date, vs):
    from career import spain
    if club["id"] == career["my_club"] and club.get("lineup"):
        return club["lineup"]
    xi = spain.pick_xi(club, date, vs)
    club["lineup"] = xi
    return xi


def quick(career, m, rng=None):
    """A quick result for a play-off match (90 minutes)."""
    from career import spain
    rng = rng or random.Random(f"playoff:{career.get('year')}:{m['id']}:{m['home']}:{m['away']}:"
                               f"{len(career.get('transfer_log') or [])}:{career['clubs'][m['home']]['finance']['balance']}")
    H, A = career["clubs"][m["home"]], career["clubs"][m["away"]]
    hxi, axi = _xi(career, H, m["date"], A["id"]), _xi(career, A, m["date"], H["id"])
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
            players.append({"team": side, "id": pid, "minutes": 90, "start": 1, "yellow": 0, "red": None,
                            "stamina": round(rng.uniform(0.62, 0.8), 3),
                            **({"injury": {"minute": rng.randint(1, 90), "knock": rng.random() < 0.4}}
                               if rng.random() < spain.MATCH_INJURY else {})})
    goals.sort(key=lambda g: g["minute"])
    return {"home": H["id"], "away": A["id"], "hg": hg, "ag": ag, "goals": goals, "players": players, "quick": True}


def _penalty_takers(club):
    xi = [clubs_mod.player_by_id(club, pid) for pid in (club.get("lineup") or {}).values()]
    xi = [p for p in xi if p is not None] or club["players"][:11]
    return sorted(xi, key=lambda p: -p.get("Penalties", 50))


def _shootout(rng, H, A):
    """(home pens, away pens): five each, then sudden death."""
    takers = (_penalty_takers(H), _penalty_takers(A))
    lo, hi = PEN_SCORE
    score = [0, 0]
    kicks = [0, 0]

    def kick(side):
        p = takers[side][kicks[side] % len(takers[side])]
        kicks[side] += 1
        if rng.random() < lo + (hi - lo) * p.get("Penalties", 50) / 100:
            score[side] += 1

    for i in range(5):
        for side in (0, 1):
            kick(side)
            left = [5 - kicks[0], 5 - kicks[1]]
            if score[0] + left[0] < score[1] or score[1] + left[1] < score[0]:
                return tuple(score)
    while score[0] == score[1]:
        kick(0)
        kick(1)
    return tuple(score)


def _extra_time(career, m, rng):
    """Extra time (and penalties if needed) on top of a level match: (et_home, et_away, pens or None)."""
    from career import spain
    H, A = career["clubs"][m["home"]], career["clubs"][m["away"]]
    d = spain.xi_rating(H, H.get("lineup") or {}) - spain.xi_rating(A, A.get("lineup") or {})
    base = (spain.HOME_GOALS + spain.AWAY_GOALS) / 2 * ET_SHARE
    eh = spain._poisson(rng, base * math.exp(spain.GOALS_PER_POINT * d))
    ea = spain._poisson(rng, base * math.exp(-spain.GOALS_PER_POINT * d))
    return eh, ea


def record(career, m, r, rng=None):
    """A play-off match is over (engine or quick): extra time / penalties if a tie needs them,
    fitness and knocks, the gate - and who goes through."""
    rng = rng or random.Random(f"playoff-after:{career.get('year')}:{m['id']}:{r['hg']}:{r['ag']}:"
                               f"{career['clubs'][m['away']]['finance']['balance']}")
    st = state(career)
    res = {"hg": r["hg"], "ag": r["ag"], "quick": bool(r.get("quick")),
           "goals": [{"team": g["team"], "name": g["name"], "minute": g.get("minute")} for g in r.get("goals", [])]}
    # Who's through?
    if m["round"] == "semi" and m["leg"] == 2:
        first = next(x for x in st["matches"] if x["tie"] == m["tie"] and x["leg"] == 1)["result"]
        # aggregate from the second-leg home side's point of view (they were away in the first leg)
        agg_h = r["hg"] + first["ag"]
        agg_a = r["ag"] + first["hg"]
        level = agg_h == agg_a
    else:
        agg_h, agg_a = r["hg"], r["ag"]
        level = m["round"] == "final" and r["hg"] == r["ag"]
    how = None
    if level:
        eh, ea = _extra_time(career, m, rng)
        res["et"] = [eh, ea]
        agg_h += eh
        agg_a += ea
        if agg_h == agg_a:
            ph, pa = _shootout(rng, career["clubs"][m["home"]], career["clubs"][m["away"]])
            res["pens"] = [ph, pa]
            how = "pens"
            winner = m["home"] if ph > pa else m["away"]
        else:
            how = "et"
            winner = m["home"] if agg_h > agg_a else m["away"]
    else:
        winner = m["home"] if agg_h > agg_a else m["away"]
    if m["round"] == "semi" and m["leg"] == 2:
        res["agg"] = [agg_h, agg_a]
    m["result"] = res
    if m["round"] == "semi" and m["leg"] == 2:
        tie = st["ties"][m["tie"]]
        tie["winner"], tie["how"] = winner, how or "agg"
        fin_m = next(x for x in st["matches"] if x["round"] == "final")
        # the final: the higher seed's tie winner is the "home" side on the team sheet (it's neutral)
        if all(t["winner"] is not None for t in st["ties"]):
            a, b = st["ties"][0]["winner"], st["ties"][1]["winner"]
            fin_m["home"], fin_m["away"] = (a, b) if st["seeds"].index(a) < st["seeds"].index(b) else (b, a)
    elif m["round"] == "final":
        st["final"] = {"winner": winner, "how": how or "90"}
        st["winner"] = winner
    elif m["round"] == "semi" and m["leg"] == 1:
        pass
    _after(career, m, r, rng)
    _news(career, m)
    return res


def _after(career, m, r, rng):
    """Fitness and knocks for both sides; the gate for the home side (semi-finals: a full house)."""
    from career import training, finance, availability as av
    training.after_match(career, [r])
    for a in r.get("players", []):
        inj = a.get("injury")
        if not inj:
            continue
        cid = r["home"] if a["team"] == 0 else r["away"]
        club = career["clubs"][cid]
        p = clubs_mod.player_by_id(club, a["id"])
        if p is None:
            continue
        if inj.get("knock"):
            if not av.injured(p, m["date"]):
                until = (cal.parse(m["date"]) + dt.timedelta(days=rng.randint(1, 3))).isoformat()
                p["injury"] = {"name": "Knock", "since": m["date"], "until": until, "cause": "match"}
        else:
            av._injure(career, club, p, m["date"], "match", rng, inj.get("minute"))
    if not m["neutral"]:
        H = career["clubs"][m["home"]]
        if "finance" in H:
            finance.home_game(career, H, H["finance"]["capacity"])


def _news(career, m):
    from career import transfers as trf
    me = career["my_club"]
    st = state(career)
    nm = lambda cid: career["clubs"][cid]["name"]
    res = m["result"]
    if m["round"] == "semi" and m["leg"] == 2:
        tie = st["ties"][m["tie"]]
        w = tie["winner"]
        l = tie["a"] if w == tie["b"] else tie["b"]
        how = {"pens": " on penalties", "et": " after extra time"}.get(tie["how"], "")
        if me in (tie["a"], tie["b"]):
            txt = (f"Through to the play-off final! You beat {nm(l)}{how}, {res['agg'][0 if m['home'] == me else 1]}-"
                   f"{res['agg'][1 if m['home'] == me else 0]} on aggregate." if w == me else
                   f"Out of the play-offs: {nm(w)} beat you{how}, {res['agg'][0 if m['home'] == w else 1]}-"
                   f"{res['agg'][1 if m['home'] == w else 0]} on aggregate.")
            trf._message(career, "news", txt)
    elif m["round"] == "final":
        w = st["winner"]
        l = m["away"] if w == m["home"] else m["home"]
        how = (f" on penalties ({res['pens'][0]}-{res['pens'][1]})" if res.get("pens") else
               " after extra time" if res.get("et") else "")
        if me in (m["home"], m["away"]):
            trf._message(career, "news", (f"PROMOTED! You won the play-off final at {VENUE}{how} - "
                                          f"the Premier Division next season." if w == me else
                                          f"Heartbreak at {VENUE}: {nm(w)} won the final{how}. "
                                          f"Another season in Division 1."))


def play_others(career, until=None):
    """Quick results for every play-off match not involving you, up to and including `until` (a date;
    None: all of them).  Stops at your next match."""
    st = ensure(career)
    if not st:
        return
    while True:
        m = next_match(career)
        if m is None or involved(career, m) or (until is not None and m["date"] > until):
            return
        record(career, m, quick(career, m))


def promoted_via_playoffs(career):
    st = state(career)
    return st["winner"] if st else None


def lines(career):
    """For the screens: [(round label, text)] of every match so far."""
    st = state(career)
    if not st:
        return []
    nm = lambda cid: career["clubs"][cid]["name"] if cid is not None else "?"
    out = []
    for m in st["matches"]:
        if m["home"] is None:
            out.append(("Final", f"{VENUE}, {cal.fmt(m['date'], False)}: winners of the semi-finals"))
            continue
        label = "Final" if m["round"] == "final" else f"Semi-final, {'first' if m['leg'] == 1 else 'second'} leg"
        r = m["result"]
        if r is None:
            out.append((label, f"{nm(m['home'])} v {nm(m['away'])}  ·  {cal.fmt(m['date'], False)}"
                               + (f"  ·  {VENUE}" if m["neutral"] else "")))
            continue
        txt = f"{nm(m['home'])} {r['hg']} - {r['ag']} {nm(m['away'])}"
        if r.get("et"):
            txt += f"  (after extra time: {r['hg'] + r['et'][0]} - {r['ag'] + r['et'][1]})"
        if r.get("agg"):
            txt += f"  ·  {r['agg'][0]}-{r['agg'][1]} on aggregate"
        if r.get("pens"):
            txt += f"  ·  {r['pens'][0]}-{r['pens'][1]} on penalties"
        out.append((label, txt))
    return out


def finish_all(career):
    """Everything still to play, yours included (quick results) - the summer can't wait."""
    if not ensure(career):
        return
    while True:
        m = next_match(career)
        if m is None:
            return
        record(career, m, quick(career, m))
