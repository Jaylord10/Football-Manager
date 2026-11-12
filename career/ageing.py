"""
career/ageing.py
================
The summer between seasons: everyone gets a year older, older players lose
a bit, some retire, clubs release a few and bring in their youth intake.

AGE CURVES (research: Kalen et al. 2019; age-curve analysis of top-league
players)
  - players peak around 25-28
  - wide players decline first (few play on past 30); centre-backs hold on
    until 31-32; goalkeepers are the least affected by age
  - pace goes first: about 1% of top speed a year from 30, faster after 33;
    stamina and agility follow; strength holds until the early thirties
  - experience: decisions, anticipation, composure and positioning don't
    decline - they still edge up into the early thirties
  - technique (passing, control, dribbling, finishing, crossing) fades
    slowly, from the early thirties

RETIREMENT: usually in the mid-thirties (later for keepers); more likely if
he's no longer getting games, less if he's still one of the club's best.

YOUTH INTAKE: every club brings 3-5 youngsters (16-17) up from its academy;
how good they could become depends on the club (better clubs, better
academies) - and now and then there's a real gem.  Squads are kept at
MAX_SQUAD: the clubs release their weakest older players to make room.

Everything that happens shows in the news.
"""

import random

from career import clubs as clubs_mod

PEAK_END = {"WM": 29, "ST": 30, "FB": 30, "CM": 30, "CB": 31, "GK": 33, "DM": 31, "AM": 30, "W": 29, "WB": 29}   # decline starts after this age
# Yearly change once past it (0-100 scale), by years past the peak end: 1, 2, 3, 4+
TECH_DECLINE = (-0.5, -1.0, -1.5, -2.5)
PACE_DECLINE_FROM = 30
PACE_DECLINE = {30: -2.0, 31: -2.5, 32: -3.0, 33: -3.5, 34: -4.0}          # Top Speed / Acceleration per year
OTHER_PHYS = {"Agility": (30, -1.5), "Stamina": (31, -2.0), "Jumping": (31, -1.5), "Strength": (33, -1.0)}
EXPERIENCE = ["Decisions", "Anticipation", "Composure", "Defensive Positioning", "Teamwork"]
EXPERIENCE_GAIN = (28, 32, 0.6)    # from / until age, points a year
TECHNIQUE = ["Passing", "Control", "Dribbling", "Crossing", "Finishing", "Long Shots", "Tackling", "Marking",
             "Heading", "Off The Ball", "Work Rate", "Shot Stopping", "Handling"]

RETIRE = {32: 0.06, 33: 0.20, 34: 0.40, 35: 0.60, 36: 0.80, 37: 0.90}       # chance at this age (or more)
RETIRE_GK_LATER = 2                # keepers: as if this many years younger
RETIRE_NO_GAMES = 1.6              # x this if he hardly played
RETIRE_STILL_GOOD = 0.5            # x this if he's still among the club's best

INTAKE = (2, 3)                    # youngsters up from the academy each summer
INTAKE_AGES = (16, 17)
ACADEMY_BELOW = 10                 # how good they could become: club strength - this...
ACADEMY_SPREAD = 7.0               # ...+- this (sd)
GEM = 0.06                         # chance a youngster is a real gem (+8..15 potential)
MAX_SQUAD = 28
SIGNINGS = (0, 0)                  # each summer a club signs this many... (off: the transfer market will do this)
SIGNING_AGES = (23, 29)            # ...experienced players...
SIGNING_LEVEL = (-5, 4)            # ...around the club's level (mean offset, sd)
YOUTH_CUT = (19, 21, 4, 4)         # academy players of 19-21 whose potential is this far below the
                                   # club's level aren't kept on (at most this many a summer)
# (Until there's a transfer market, the signings stand in for it: they keep
# squads' ages and quality steady over the seasons.)
MIN_BY_POS = {"GK": 3, "LB": 2, "RB": 2, "CB": 4, "CM": 4, "LM": 2, "RM": 2, "ST": 3}


def _clamp(v):
    return int(max(clubs_mod.ATTR_MIN, min(clubs_mod.ATTR_MAX, round(v))))


def _news(career, date, cid, text, kind="squad"):
    from career import availability
    availability._news(career, date, cid, text, kind)


def age_player(p, rng):
    """One year older: decline past the peak, experience, pace."""
    p["Age"] = p.get("Age", 26) + 1
    age = p["Age"]
    group = clubs_mod.NATURAL_GROUP[p["Pos"]]
    past = age - PEAK_END[group]
    if past > 0:
        step = TECH_DECLINE[min(past, len(TECH_DECLINE)) - 1]
        for a in TECHNIQUE:
            if a in p and not (a in ("Shot Stopping", "Handling") and p["Pos"] != "GK"):
                p[a] = _clamp(p[a] + step + rng.gauss(0, 0.6))
    lo, hi, gain = EXPERIENCE_GAIN
    if lo <= age <= hi:
        for a in EXPERIENCE:
            p[a] = _clamp(p[a] + gain + rng.gauss(0, 0.4))
    if age >= PACE_DECLINE_FROM:
        d = PACE_DECLINE.get(age, PACE_DECLINE[max(PACE_DECLINE)])
        for a in ("Top Speed", "Acceleration"):
            p[a] = _clamp(p[a] + d + rng.gauss(0, 0.8))
    for a, (from_age, d) in OTHER_PHYS.items():
        if age >= from_age:
            p[a] = _clamp(p[a] + d + rng.gauss(0, 0.6))
    # Potential can't be above what he can still reach
    if age >= 25 and p.get("Potential") is not None:
        p["Potential"] = round(min(p["Potential"], max(clubs_mod.overall(p), p["Potential"] - 1.0)), 1)


def retire_chance(p, club):
    age = p.get("Age", 26) - (RETIRE_GK_LATER if p["Pos"] == "GK" else 0)
    ages = sorted(RETIRE)
    if age < ages[0]:
        return 0.0
    chance = RETIRE[min(age, ages[-1])]
    if p.get("mins_avg", 45) < 20:
        chance *= RETIRE_NO_GAMES
    better = sum(1 for q in club["players"] if clubs_mod.family(q["Pos"]) == clubs_mod.family(p["Pos"])
                 and clubs_mod.overall(q) > clubs_mod.overall(p))
    if better == 0:
        chance *= RETIRE_STILL_GOOD
    return min(0.95, chance)


def _next_id(club):
    return max((p["id"] for p in club["players"]), default=-1) + 1


def youth_intake(career, club, date, rng, used_names):
    """3-5 academy players: positions where the squad is shortest first."""
    n = rng.randint(*INTAKE)
    have = {}
    for p in club["players"]:
        have[clubs_mod.family(p["Pos"])] = have.get(clubs_mod.family(p["Pos"]), 0) + 1
    new = []
    for _ in range(n):
        need = sorted(MIN_BY_POS, key=lambda pos: (have.get(pos, 0) - MIN_BY_POS[pos], rng.random()))
        pos = need[0] if rng.random() < 0.6 else rng.choice(list(MIN_BY_POS))
        peak = club["strength"] - ACADEMY_BELOW + rng.gauss(0.0, ACADEMY_SPREAD)
        age = rng.choice(INTAKE_AGES)
        p = clubs_mod._player(rng, pos, peak, used_names, _next_id(club), age=age, names=career.get("name_pool"))
        if career.get("name_pool"):
            p["homegrown"] = False
            p["non_eu"] = rng.random() < 0.08                  # (a few academy players aren't EU citizens)
        p["Potential"] = round(min(95.0, max(p["Potential"], peak + rng.gauss(0, 2))), 1)
        if rng.random() < GEM:
            p["Potential"] = round(min(95.0, p["Potential"] + rng.uniform(8, 15)), 1)
        p["youth"] = True
        p["condition"] = 1.0
        club["players"].append(p)
        have[pos] = have.get(pos, 0) + 1
        new.append(p)
    names = ", ".join(f"{p['Name']} ({p['Pos']}, {p['Age']})" for p in new)
    _news(career, date, club["id"], f"Youth intake: {names} join the squad from the academy.", "youth")
    return new


def trim_squad(career, club, date, protect=()):
    """Over MAX_SQUAD: release the weakest older players (never below MIN_BY_POS at a position)."""
    released = []
    while len(club["players"]) > MAX_SQUAD:
        have = {}
        for p in club["players"]:
            have[clubs_mod.family(p["Pos"])] = have.get(clubs_mod.family(p["Pos"]), 0) + 1
        cands = [p for p in club["players"] if p["id"] not in protect and not p.get("loan")
                 and have[clubs_mod.family(p["Pos"])] > MIN_BY_POS.get(clubs_mod.family(p["Pos"]), 1)]
        if not cands:
            break
        worst = min(cands, key=lambda p: (_worth(p), -p["Age"]))
        club["players"].remove(worst)
        from career import contracts
        contracts._to_free_agent(career, club, worst)
        released.append(worst)
    if released:
        names = ", ".join(f"{p['Name']} ({p['Pos']}, {p['Age']})" for p in released)
        _news(career, date, club["id"], f"Released: {names}.", "squad")
    return released


def _worth(p):
    """What a player is worth to the club when deciding who to let go: the
    young on what they could become, the old on what they still are."""
    now = clubs_mod.overall(p)
    pot = p.get("Potential") or now
    age = p.get("Age", 26)
    if age <= 20:
        return 0.6 * now + 0.4 * pot
    if age <= 23:
        return 0.8 * now + 0.2 * pot
    return now - 3.0 * max(0, age - 30)


def youth_cut(career, club, date):
    lo, hi, below, most = YOUTH_CUT
    cands = [p for p in club["players"] if lo <= p.get("Age", 26) <= hi and not p.get("loan")
             and (p.get("Potential") or 0) < club["strength"] - below]
    cands.sort(key=lambda p: p.get("Potential") or 0)
    gone = cands[:most]
    from career import contracts
    for p in gone:
        club["players"].remove(p)
        contracts._to_free_agent(career, club, p)
    if gone:
        names = ", ".join(f"{p['Name']} ({p['Pos']}, {p['Age']})" for p in gone)
        _news(career, date, club["id"], f"Not offered a new contract: {names}.", "squad")
    return gone


def signings(career, club, date, rng, used_names):
    """Experienced players from outside the league, where the squad is short."""
    new = []
    for _ in range(rng.randint(*SIGNINGS)):
        have = {}
        for p in club["players"]:
            have[clubs_mod.family(p["Pos"])] = have.get(clubs_mod.family(p["Pos"]), 0) + 1
        pos = min(MIN_BY_POS, key=lambda q: (have.get(q, 0) - MIN_BY_POS[q], rng.random()))
        mean, sd = SIGNING_LEVEL
        level = club["strength"] + mean + rng.gauss(0.0, sd)
        p = clubs_mod._player(rng, pos, level, used_names, _next_id(club), age=rng.randint(*SIGNING_AGES))
        p["condition"] = 1.0
        club["players"].append(p)
        new.append(p)
    if new:
        names = ", ".join(f"{p['Name']} ({p['Pos']}, {p['Age']})" for p in new)
        _news(career, date, club["id"], f"Signed from outside the league: {names}.", "squad")
    return new


def summer(career, rng=None):
    """Between seasons: age, retire, youth intake, release.  Returns a summary for your club."""
    rng = rng or random.Random()
    date = career.get("date")
    used = {p["Name"] for c in career["clubs"] for p in c["players"]}
    mine = {"retired": [], "intake": [], "released": [], "declined": []}
    for c in career["clubs"]:
        is_me = c["id"] == career["my_club"]
        # 1. Retirements (decided on last season's age and form)
        for p in list(c["players"]):
            if rng.random() < retire_chance(p, c):
                c["players"].remove(p)
                _news(career, date, c["id"], f"{p['Name']} ({p['Pos']}) retires at {p['Age']}.", "squad")
                if is_me:
                    mine["retired"].append(p)
        # 2. A year older
        for p in c["players"]:
            before = clubs_mod.overall(p)
            pace0 = p["Top Speed"]
            age_player(p, rng)
            p.pop("youth", None)
            if is_me and (clubs_mod.overall(p) <= before - 2 or p["Top Speed"] <= pace0 - 4):
                mine["declined"].append(p)
        # 3. Academy players who won't make it; youth intake; signings; make room
        cut = youth_cut(career, c, date)
        new = youth_intake(career, c, date, rng, used)
        signed = signings(career, c, date, rng, used)
        gone = trim_squad(career, c, date, protect={p["id"] for p in new + signed})
        if is_me:
            mine["intake"] += new
            mine["released"] += cut + gone
            mine.setdefault("signed", []).extend(signed)
        # 4. The XI: anyone who's gone is replaced
        ids = {p["id"] for p in c["players"]}
        if any(pid not in ids for pid in c.get("lineup", {}).values()):
            if is_me:
                for slot, pid in list(c["lineup"].items()):
                    if pid not in ids:
                        used_ids = set(c["lineup"].values())
                        cands = [p for p in c["players"] if p["id"] not in used_ids]
                        if cands:
                            c["lineup"][slot] = max(cands, key=lambda p: clubs_mod.overall(p, slot))["id"]
            else:
                c["lineup"] = clubs_mod.best_lineup(c)
    if mine["declined"]:
        names = ", ".join(p["Name"] for p in mine["declined"][:5])
        _news(career, date, career["my_club"], f"Staff report: {names} {'has' if len(mine['declined']) == 1 else 'have'} "
                                               f"lost a step over the summer.", "squad")
    career["summer"] = {k: [{"name": p["Name"], "pos": p["Pos"], "age": p["Age"], "rating": clubs_mod.overall(p)}
                            for p in v] for k, v in mine.items()}
    return mine
