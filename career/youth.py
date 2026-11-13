"""
career/youth.py
===============
The U21s and the U18s - every club's academy, its two youth sides, and their leagues.

  - THE ACADEMY (club["academy"]): every club has its own named youngsters - about 9 U18s (scholars, 16-18)
    and 8 U21s (19-21) - outside the first-team squad.  They don't count against the squad or the
    registration list, and their pay is part of the academy budget (career/finance.py academy_cost).
  - Your first-team youngsters can go down too (p["squad"] = "u21" / "u18"), and senior players back from
    injury can have a run-out with the U21s (games bring their sharpness back; three over-age players a game,
    like the real Premier League 2).  You can call any academy player up to the first team (he signs his
    first professional contract).
  - EACH SUMMER: the academy players are a year older; at 19 the U18s are offered a professional contract
    (the better prospects) or released; at 22 the U21s either join the first team (if they're good enough
    and there's room) or leave; a new intake of 16-year-olds joins the U18s.  (The few youngsters who come
    straight into the first-team squad each summer - career/ageing.py youth_intake - still do.)
  - Two leagues in each division, like the real Premier League 2 (U21) and U18 Premier League: every club in
    the division plays the others once (19 games), the U21s on Mondays, the U18s on Saturday mornings.
    Results are worked out quickly from the two sides' players.
  - GAMES MAKE PLAYERS (career/training.py develop): development speeds up with recent minutes, and
    first-team minutes count most - an U21 game counts a bit over half as much as a first-team game, an U18
    game about a third.  A youngster who never plays develops slowest of all.  Academy players develop once
    a week (Mondays), a week's worth at a time; your academy coach helps yours (career/staff.py).

Real-world: Premier League clubs have ~20 U18 scholars (two-year scholarships from 16) and ~20 in the U21
squad; at 18 most clubs offer a professional contract to only about a third to a half of their scholars,
and only around 1 in 10 of those still at the club at 21 make a real first-team career (EPPP / Premier
League youth development reviews; e.g. BBC Sport, "What happens to academy footballers?").  Premier League 2
allows three over-age outfield players and a keeper; first-team minutes, then loans and senior football,
do more for a young player than youth-team games - why clubs loan their best 19-21-year-olds out.

Kept in career["youth"] = {"year", "u21": {div: league}, "u18": {div: league}}, a league being
{"clubs", "fixtures", "dates", "results"}; squads in p["squad"] ("u21" / "u18" / none = the first team);
recent youth minutes in p["y_u21"] / p["y_u18"] (like mins_avg); this season's youth games and goals in
p["ystats"] = {"u21": [games, goals], "u18": [...]}.  Academy players carry p["academy"] = True and ids from
ACADEMY_ID up (a new id when they join the first team).
"""

import datetime as dt
import random

from career import clubs as clubs_mod

TEAMS = ("u21", "u18")
NAME = {"u21": "U21s", "u18": "U18s"}
LEAGUE = {"u21": "U21 League", "u18": "U18 League"}
AGE_MAX = {"u21": 21, "u18": 18}
WEEKDAY = {"u21": 0, "u18": 5}               # Monday / Saturday
START = {"u21": (8, 17), "u18": (8, 15)}
WEEKS = 34                                   # the rounds are spread over this many weeks (mid-August to April)
WEIGHT = {"u21": 0.55, "u18": 0.35}          # a youth game's minutes, against a first-team game's (1.0)
MINUTES_MEMORY = 0.25                        # (as career/training.py)
FIRST_TEAM_SQUAD = 22                        # setting the squads: your best this many stay in the first team
AI_REGULAR = 40                              # AI clubs: a youngster averaging more first-team minutes stays up
PAD = 25                                     # a side short of players: the gaps play like club strength - this
TIRED = 0.8                                  # condition after a youth game (it comes back in training)
OVER_AGE = 3                                 # over-21s a U21 side may play (real PL2: three outfield + a keeper)
# The academy
U18_SIZE = 9                                 # named U18s at each club (topped up by each summer's intake)
U21_SIZE = (6, 10)                           # named U21s: at least / at most
INTAKE_AGES = (16, 16, 16, 17)
KID_BELOW = 20                               # how good an academy player could become: club strength - this...
KID_SPREAD = 6.0                             # ...+- this (sd)
KID_GEM = 0.015                              # ...and now and then a real gem (+8..15)
PRO_OFFER = 0.4                              # at 19: a scholar below the club's usual prospect still gets a contract
RELEASED_TO_MARKET = 55                      # a released youngster this good (overall) looks for a new club
ACADEMY_ID = 100000
POSITIONS = {"GK": 1, "CB": 2, "LB": 1, "RB": 1, "CM": 2, "LM": 0.5, "RM": 0.5, "ST": 1}    # the shape of a youth squad


def state(career):
    return career.get("youth")


def _div(career, club):
    from career import divisions
    return divisions.div_of(club) if divisions.exists(career) else "all"


def _div_clubs(career):
    from career import divisions
    if not divisions.exists(career):
        return {"all": [c["id"] for c in career["clubs"]]}
    out = {}
    for c in career["clubs"]:
        out.setdefault(divisions.div_of(c), []).append(c["id"])
    return out


def _round_robin(ids, rng):
    ids = list(ids)
    rng.shuffle(ids)
    if len(ids) % 2:
        ids.append(None)
    n = len(ids)
    rounds = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = ids[i], ids[n - 1 - i]
            if a is not None and b is not None:
                pairs.append([a, b] if (r + i) % 2 == 0 else [b, a])
        rounds.append(pairs)
        ids = [ids[0]] + [ids[-1]] + ids[1:-1]
    return rounds


def create(career, first=True):
    """This season's youth leagues; your squads set (first=True: everyone placed afresh)."""
    y = career.get("year", 2026)
    rng = random.Random(f"youth:{y}")
    out = {"year": y}
    for t in TEAMS:
        m, d = START[t]
        start = dt.date(y, m, d)
        start += dt.timedelta(days=(WEEKDAY[t] - start.weekday()) % 7)
        out[t] = {}
        for div, ids in _div_clubs(career).items():
            rounds = _round_robin(ids, rng)
            n = len(rounds)
            dates = [(start + dt.timedelta(weeks=round(k * WEEKS / max(1, n - 1)))).isoformat() for k in range(n)]
            out[t][div] = {"clubs": ids, "fixtures": rounds, "dates": dates, "results": {}}
    career["youth"] = out
    rng = random.Random(f"academy:{y}")
    for c in career["clubs"]:
        if "academy" not in c:
            start_academy(career, c, rng)
    set_squads(career, keep=not first)
    return out


def ensure(career):
    """(Older saves, a new career: the youth leagues start.)"""
    ys = state(career)
    if ys is None or ys.get("year") != career.get("year"):
        create(career, first=ys is None)


def set_squads(career, keep=True):
    """Your players' squads.  Youngsters outside your best FIRST_TEAM_SQUAD go to the U18s / U21s by age;
    the over-age move up (an U18 at 19 to the U21s, an U21 at 22 to the first team).  keep: players you've
    already placed stay where you put them (seniors sent down for a run-out come back up each summer)."""
    club = career["clubs"][career["my_club"]]
    ranked = sorted(club["players"], key=lambda p: -clubs_mod.overall(p))
    top = {p["id"] for p in ranked[:FIRST_TEAM_SQUAD]}
    for p in club["players"]:
        age = p.get("Age", 26)
        sq = p.get("squad")
        if p.pop("squad_down", None):
            sq = None
        elif sq == "u18" and age > AGE_MAX["u18"]:
            sq = "u21" if age <= AGE_MAX["u21"] else None
        elif sq == "u21" and age > AGE_MAX["u21"]:
            sq = None
        if not (keep and p.get("squad_set")) and sq is None and p["id"] not in top and not p.get("loan"):
            sq = "u18" if age <= AGE_MAX["u18"] else "u21" if age <= AGE_MAX["u21"] else None
        if not keep and p["id"] in top:
            sq = None
        if sq:
            p["squad"] = sq
        else:
            p.pop("squad", None)
        p["squad_set"] = True


def move(career, p, squad):
    """You move a player: squad = "u21" / "u18" / None (the first team - an academy player signs a contract)."""
    club = career["clubs"][career["my_club"]]
    if p.get("academy"):
        if squad is None:
            call_up(career, club, p)
        else:
            p["squad"] = squad
        return
    if squad is None:
        p.pop("squad", None)
        p.pop("squad_down", None)
    else:
        p["squad"] = squad
        if p.get("Age", 26) > AGE_MAX[squad]:
            p["squad_down"] = True                 # (an over-age player: a run-out - back up next summer)
        else:
            p.pop("squad_down", None)
    p["squad_set"] = True


def can_drop(p, squad):
    """Can he go down to this side?  U18s: only the young enough.  U21s: anyone (over-age run-outs)."""
    return squad == "u21" or p.get("Age", 26) <= AGE_MAX["u18"]


def _here(p, club):
    lo = p.get("loan")
    return not lo or lo.get("to") in (None, club["id"])


def pool(career, club, team):
    """The players who'd play for this club's youth side (injured or not): its academy players, and first-team
    players sent down (yours) / young first-team players who aren't regulars (the AI's)."""
    kids = [p for p in club.get("academy", []) if p.get("squad") == team]
    if club["id"] == career["my_club"]:
        return kids + [p for p in club["players"] if p.get("squad") == team and _here(p, club)]
    lo = AGE_MAX["u18"] + 1 if team == "u21" else 0
    return kids + [p for p in club["players"] if lo <= p.get("Age", 26) <= AGE_MAX[team]
                   and p.get("mins_avg", 45) < AI_REGULAR and _here(p, club)]


def everyone(club):
    return club["players"] + club.get("academy", [])


def _xi(career, club, team, iso):
    from career import availability as av
    ps = sorted((p for p in pool(career, club, team) if not av.injured(p, iso)),
                key=lambda p: -clubs_mod.overall(p))
    gk = [p for p in ps if p["Pos"] == "GK"][:1]
    rest, over = [], 0
    for p in ps:
        if p in gk or len(rest) >= 11 - len(gk):
            continue
        if p.get("Age", 26) > AGE_MAX[team]:
            if over >= OVER_AGE:
                continue
            over += 1
        rest.append(p)
    return gk + rest


def _strength(club, xi):
    vals = [clubs_mod.overall(p) for p in xi]
    vals += [club.get("strength", 60) - PAD] * (11 - len(vals))
    return sum(vals) / 11.0


def _poisson(rng, lam):
    k, p, L = 0, 1.0, 2.718281828 ** -lam
    while True:
        p *= rng.random()
        if p < L:
            return k
        k += 1


def play_round(career, team, div, k, iso, rng):
    from career import fitness, training
    lg = state(career)[team][div]
    if str(k) in lg["results"]:
        return
    out = []
    key = "y_" + team
    for h, a in lg["fixtures"][k]:
        ch, ca = career["clubs"][h], career["clubs"][a]
        xh, xa = _xi(career, ch, team, iso), _xi(career, ca, team, iso)
        sh, sa = _strength(ch, xh), _strength(ca, xa)
        hg = _poisson(rng, 1.6 * 1.035 ** (sh - sa))
        ag = _poisson(rng, 1.35 * 1.035 ** (sa - sh))
        goals = []
        for side, club, xi, n in ((0, ch, xh, hg), (1, ca, xa, ag)):
            shooters = [p for p in xi if p["Pos"] != "GK"]
            for _ in range(n):
                if shooters and rng.random() < len(xi) / 11.0:
                    w = [3 if p["Pos"] in ("ST", "LW", "RW", "AM") else 1 for p in shooters]
                    s = rng.choices(shooters, w)[0]
                    goals.append({"team": side, "name": s["Name"], "pid": s["id"]})
                    s.setdefault("ystats", {}).setdefault(team, [0, 0])[1] += 1
                else:
                    goals.append({"team": side, "name": "", "pid": None})
            played = {p["id"] for p in xi}
            for p in everyone(club):                      # (everyone's recent youth minutes)
                mins = 90 if p["id"] in played else 0
                if mins or p.get(key):
                    p[key] = round((1 - MINUTES_MEMORY) * p.get(key, 0) + MINUTES_MEMORY * mins, 1)
                if mins:
                    p.setdefault("ystats", {}).setdefault(team, [0, 0])[0] += 1
                    fitness.played(p, mins)               # (match sharpness - a run-out)
                    p["condition"] = round(min(training.condition(p), TIRED), 3)
        out.append({"home": h, "away": a, "hg": hg, "ag": ag, "goals": goals})
    lg["results"][str(k)] = out
    me = career["my_club"]
    for r in out:
        if me in (r["home"], r["away"]):
            from career import availability as av
            mine = r["home"] == me
            f, a_ = (r["hg"], r["ag"]) if mine else (r["ag"], r["hg"])
            opp = career["clubs"][r["away"] if mine else r["home"]]["name"]
            sc = [g["name"].split(" ")[-1] for g in r["goals"] if g["team"] == (0 if mine else 1) and g["name"]]
            av._news(career, iso, me, f"{NAME[team]}: {f}-{a_} v {opp} ({'home' if mine else 'away'})"
                     + (f" - {', '.join(sc)}" if sc else "") + ".", "youth")


def day(career, iso, rng=None):
    """Each day (career/transfers.py on_day): any youth games today."""
    ys = state(career)
    if not ys:
        return
    if dt.date.fromisoformat(iso).weekday() == 0 and ys.get("grown") != iso:
        ys["grown"] = iso
        grow(career)                                       # (the academies' week of development)
    for team in TEAMS:
        for div, lg in (ys.get(team) or {}).items():
            for k, d in enumerate(lg["dates"]):
                if d == iso:
                    play_round(career, team, div, k, iso, random.Random(f"{team}:{div}:{iso}"))


def league_of(career, team, club=None):
    ys = state(career) or {}
    club = club or career["clubs"][career["my_club"]]
    lgs = ys.get(team) or {}
    lg = lgs.get(_div(career, club))
    if lg is None or club["id"] not in lg.get("clubs", []):
        lg = next((x for x in lgs.values() if club["id"] in x.get("clubs", [])), None)
    return lg


def table(career, team, club=None):
    lg = league_of(career, team, club) or {}
    rows = {c: {"club": c, "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0} for c in lg.get("clubs", [])}
    for res in (lg.get("results") or {}).values():
        for r in res:
            for c, f, a in ((r["home"], r["hg"], r["ag"]), (r["away"], r["ag"], r["hg"])):
                row = rows[c]
                row["p"] += 1
                row["gf"] += f
                row["ga"] += a
                if f > a:
                    row["w"] += 1
                    row["pts"] += 3
                elif f == a:
                    row["d"] += 1
                    row["pts"] += 1
                else:
                    row["l"] += 1
    out = list(rows.values())
    for r in out:
        r["gd"] = r["gf"] - r["ga"]
    out.sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["club"]))
    return out


def results(career, team, n=3):
    """Your side's latest results, newest first: [(date, "W 2-1 v Opp (h)")]."""
    lg = league_of(career, team) or {}
    me = career["my_club"]
    out = []
    for k in sorted((int(x) for x in lg.get("results", {})), reverse=True):
        for r in lg["results"][str(k)]:
            if me in (r["home"], r["away"]):
                mine = r["home"] == me
                f, a = (r["hg"], r["ag"]) if mine else (r["ag"], r["hg"])
                opp = career["clubs"][r["away"] if mine else r["home"]]["short"]
                out.append((lg["dates"][k], f"{'W' if f > a else 'D' if f == a else 'L'} {f}-{a} v {opp}"
                                            f" ({'h' if mine else 'a'})"))
        if len(out) >= n:
            break
    return out


def next_game(career, team):
    lg = league_of(career, team) or {}
    today = career.get("date") or ""
    me = career["my_club"]
    for k, d in enumerate(lg.get("dates", [])):
        if d >= today and str(k) not in lg["results"]:
            for h, a in lg["fixtures"][k]:
                if me in (h, a):
                    opp = career["clubs"][a if h == me else h]["short"]
                    return d, f"v {opp} ({'h' if h == me else 'a'})"
    return None


def champions(career, team):
    """{div: club id} - the season's youth champions (once every game's played)."""
    out = {}
    for div, lg in ((state(career) or {}).get(team) or {}).items():
        if len(lg["results"]) >= len(lg["fixtures"]):
            t = table(career, team, career["clubs"][lg["clubs"][0]])
            if t:
                out[div] = t[0]["club"]
    return out


def season_end(career):
    """(Before the summer: the youth champions into the history.)"""
    ys = state(career)
    if not ys:
        return
    rec = {"year": ys["year"]}
    for team in TEAMS:
        rec[team] = champions(career, team)
    career.setdefault("youth_history", []).append(rec)


def new_season(career):
    """Summer (after career/ageing.py's summer): last season's youth stats go; the academies' year (a year
    older, contracts or released, graduates, the new intake); the age groups move up; the new leagues."""
    rng = random.Random(f"academy-summer:{career.get('year')}")
    for c in career["clubs"]:
        for p in c["players"]:
            p.pop("ystats", None)
        academy_summer(career, c, rng)
    create(career, first=False)


# --- The academies -------------------------------------------------------------------------------------
def _next_kid_id(club):
    n = max([ACADEMY_ID - 1] + [p["id"] for p in club.get("academy", [])]) + 1
    return n


def _kid(career, club, team, age, rng, used, pos=None):
    from career import ageing, staff
    have = {}
    for p in club.get("academy", []):
        if p.get("squad") == team:
            fam = clubs_mod.family(p["Pos"])
            have[fam] = have.get(fam, 0) + 1
    pos = pos or max(POSITIONS, key=lambda f: (POSITIONS[f] - have.get(f, 0), rng.random()))
    plus, gem = staff.academy(career, club)               # (your academy coach)
    level = club.get("strength", 60) - KID_BELOW + rng.gauss(0.0, KID_SPREAD) + plus
    p = clubs_mod._player(rng, pos, level, used, _next_kid_id(club), age=age, names=career.get("name_pool"))
    now = clubs_mod.overall(p)
    pot = level + rng.gauss(0.0, 3.0)                     # (no wonderkid lottery for the whole academy...)
    if rng.random() < KID_GEM * gem:
        pot += rng.uniform(8, 15)                         # (...just the odd gem)
    p["Potential"] = round(min(95.0, max(pot, now)), 1)
    if career.get("name_pool"):
        p["homegrown"] = False
        p["non_eu"] = rng.random() < 0.08
    p["academy"] = True
    p["squad"] = team
    p["mins_avg"] = 0.0
    p["condition"] = 1.0
    p["fitness"] = 0.9
    p["sharp"] = 0.5
    club.setdefault("academy", []).append(p)
    return p


def _used_names(career):
    return {p["Name"] for c in career["clubs"] for p in everyone(c)}


def start_academy(career, club, rng, used=None):
    """A club's academy, the first time: U18s of 16-18 and U21s of 19-21."""
    used = used if used is not None else _used_names(career)
    club.setdefault("academy", [])
    for k in range(U18_SIZE):
        _kid(career, club, "u18", (16, 17, 18)[k % 3], rng, used)
    for k in range(sum(U21_SIZE) // 2):
        _kid(career, club, "u21", (19, 20, 21)[k % 3], rng, used)


def in_academy(p):
    return bool(p.get("academy"))


def _sign(career, club, p):
    """An academy player signs his first professional contract and joins the first-team squad."""
    from career import finance as fin
    club["academy"].remove(p)
    for k in ("academy", "y_u18"):
        p.pop(k, None)
    p["id"] = max((q["id"] for q in club["players"]), default=-1) + 1
    p["youth"] = True
    rng = random.Random(f"pro:{p['Name']}:{career.get('date')}")
    fin.give_contract(p, career.get("year", 2026), rng)
    if "finance" in club:
        p["wage"] = fin.fair_wage(p, fin.size_rank(career, club), fin.league_size(career, club), fin.league_of(club))
    else:
        p["wage"] = 1000
    p["mins_avg"] = p.get("mins_avg", 0.0)
    club["players"].append(p)
    return p


def call_up(career, club, p):
    """You call an academy player up: a professional contract, into the first-team squad."""
    from career import availability as av
    _sign(career, club, p)
    p.pop("squad", None)
    p["squad_set"] = True
    av._news(career, career.get("date"), club["id"], f"{p['Name']} ({p['Pos']}, {p['Age']}) signs his first "
             f"professional contract and joins the first-team squad.", "youth")


def _release(career, club, p, out):
    from career import contracts
    club["academy"].remove(p)
    out.append(p)
    if clubs_mod.overall(p) >= RELEASED_TO_MARKET:
        for k in ("academy", "squad", "squad_set", "y_u18", "y_u21", "ystats"):
            p.pop(k, None)
        contracts._to_free_agent(career, club, p)


def academy_summer(career, club, rng):
    """The academy's summer (the players have had their birthdays - see career/ageing.py age_player)."""
    from career import ageing, availability as av
    if "academy" not in club:
        return
    date = career.get("date")
    is_me = club["id"] == career["my_club"]
    for p in club["academy"]:
        ageing.age_player(p, rng)
        p.pop("ystats", None)
    prospect = club.get("strength", 60) - KID_BELOW         # (what the club's usual academy player could become)
    ranked = sorted((clubs_mod.overall(q) for q in club["players"]), reverse=True)
    bar = ranked[min(19, len(ranked) - 1)] - 3 if ranked else 0
    mid = ranked[len(ranked) // 2] if ranked else 0
    released, pros, signed = [], [], []
    for p in sorted(club["academy"], key=lambda q: -q.get("Potential", 0)):
        age = p["Age"]
        if p["squad"] == "u18" and age > AGE_MAX["u18"]:
            if p.get("Potential", 0) >= prospect or rng.random() < PRO_OFFER:
                p["squad"] = "u21"
                pros.append(p)
            else:
                _release(career, club, p, released)
        elif p["squad"] == "u21" and age > AGE_MAX["u21"]:
            good = clubs_mod.overall(p) >= bar or p.get("Potential", 0) >= mid
            if good and len(club["players"]) < ageing.MAX_SQUAD:
                _sign(career, club, p)
                p.pop("squad", None)
                signed.append(p)
            else:
                _release(career, club, p, released)
    u21 = sorted((p for p in club["academy"] if p["squad"] == "u21"), key=lambda q: -q.get("Potential", 0))
    for p in u21[U21_SIZE[1]:]:
        _release(career, club, p, released)
    used = _used_names(career)
    new = []
    while sum(1 for p in club["academy"] if p["squad"] == "u18") < U18_SIZE:
        new.append(_kid(career, club, "u18", rng.choice(INTAKE_AGES), rng, used))
    while sum(1 for p in club["academy"] if p["squad"] == "u21") < U21_SIZE[0]:
        _kid(career, club, "u21", 19, rng, used)              # (a trialist or two from elsewhere)
    for team, age in (("u21", 19), ("u18", 16)):
        if not any(p["Pos"] == "GK" for p in club["academy"] if p["squad"] == team):
            new.append(_kid(career, club, team, age, rng, used, pos="GK"))     # (every side needs a keeper)
    if is_me:
        if signed:
            av._news(career, date, club["id"], "Academy graduates: " + ", ".join(
                f"{p['Name']} ({p['Pos']}, {p['Age']})" for p in signed) + " sign professional contracts and join "
                "the first-team squad.", "youth")
        if pros:
            av._news(career, date, club["id"], "U18 scholars offered professional contracts (now U21s): " + ", ".join(
                f"{p['Name']} ({p['Pos']})" for p in pros) + ".", "youth")
        if released:
            av._news(career, date, club["id"], "Released by the academy: " + ", ".join(
                f"{p['Name']} ({p['Pos']}, {p['Age']})" for p in released) + ".", "youth")
        if new:
            av._news(career, date, club["id"], "New U18 scholars: " + ", ".join(
                f"{p['Name']} ({p['Pos']}, {p['Age']})" for p in new) + ".", "youth")
        career.setdefault("summer", {})["academy"] = {"signed": [p["Name"] for p in signed],
                                                      "released": [p["Name"] for p in released]}


def grow(career):
    """Monday: every academy player's week of development (career/training.py develop, x 7 days)."""
    from career import training, staff
    rng = random.Random(f"grow:{career.get('date')}")
    for c in career["clubs"]:
        kids = c.get("academy")
        if not kids:
            continue
        mult = 7.0 * (staff.academy_development(career, c) if c["id"] == career["my_club"] else 1.0)
        for p in kids:
            training.develop(p, mult, (), rng)


def report(career, p):
    """(low, high) - your academy coach's guess at how good one of your youngsters could become."""
    from career import staff
    coaches = staff.of_role(career, "academy")
    ability = coaches[0]["ability"] if coaches else 6
    spread = max(1, round((21 - ability) / 2.5))
    true = max(clubs_mod.overall(p), round(p.get("Potential") or clubs_mod.overall(p)))
    rng = random.Random(f"acad:{p['Name']}:{coaches[0]['name'] if coaches else ''}")
    guess = true + rng.randint(-spread, spread)
    return guess - spread, guess + spread


def effective_minutes(p):
    """For development (career/training.py): first-team minutes, plus youth games at their weight."""
    return p.get("mins_avg", 45) + WEIGHT["u21"] * p.get("y_u21", 0) + WEIGHT["u18"] * p.get("y_u18", 0)


def stats(p, team):
    g = (p.get("ystats") or {}).get(team) or [0, 0]
    return g[0], g[1]


def first_team(career):
    """{player id: [league games, goals]} for your club this season (from the match records)."""
    me = career["my_club"]
    out = {}
    for md in (career.get("results") or {}).values():
        for r in md:
            if me not in (r["home"], r["away"]):
                continue
            side = 0 if r["home"] == me else 1
            for a in r.get("players", []):
                if a["team"] == side and a.get("minutes", 0) > 0:
                    out.setdefault(a["id"], [0, 0])[0] += 1
            for g in r.get("goals", []):
                if g.get("team") == side and not g.get("own_goal") and g.get("pid") is not None:
                    out.setdefault(g["pid"], [0, 0])[1] += 1
    return out
