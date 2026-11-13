"""Builds data/world/honours.json: every season's winners, consistent with the club profiles."""
import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
GAME = _os.environ.get("FM_GAME", _os.path.dirname(DEV))   # the game folder (default: this repo)
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")

import json, random, csv
W = _os.path.join(GAME, "data", "world")
clubs = [r for r in csv.DictReader(open(f"{W}/clubs.csv"))]
strength = {c["name"]: int(c["strength"]) for c in clubs}
names = [c["name"] for c in clubs]
es = [r["name"] for r in csv.DictReader(open(f"{W}/es_clubs.csv"))]
es_str = {r["name"]: int(r.get("strength") or 70) for r in csv.DictReader(open(f"{W}/es_clubs.csv"))}
abroad_eu = ["FC Rheinfeld", "Olympique Varennes", "Ajaxia Noord", "Dinamo Kravetz", "AC Montevera", "Sporting Esteira",
             "Galatur SK", "FC Lindholm", "Union Saint-Lys", "Celtic Harbour", "Hellas Korinna", "Inter Valmora", "Steaua Ravna"]
south = ["Boca del Plata", "Estrela da Serra", "Club Atletico Montevista", "Nacional de Sierra Alta", "Gremio Litoral",
         "Universitario del Sur", "Deportivo Cumbre", "Santa Fe del Rio"]
ash = json.load(open(f"{W}/clubs/ashvale.json"))
H = ash["honours"]
rng = random.Random(1878)
WAR = set(range(1916, 1920)) | set(range(1940, 1947))
# each club's fortunes by era (20-year blocks) - today's strength counts most lately
era = {n: {b: rng.uniform(0.3, 1.8) for b in range(1860, 2040, 20)} for n in names + es + abroad_eu}
EX = 1.3
def w(n, year, base, ex=None):
    ex = EX if ex is None else ex
    s = base.get(n, 66)
    recent = min(1.0, max(0.0, (year - 1950) / 70))
    return max(0.05, (max(1, s - 55) ** ex) * (0.35 + 0.65 * recent) * era[n][(year // 20) * 20] + 12 * (1 - recent))
def pick(pool, year, base, avoid=(), ex=None):
    pool = [n for n in pool if n not in avoid]
    return rng.choices(pool, [w(n, year, base, ex) for n in pool])[0]
roll = {"league": {}, "association_cup": {}, "league_cup": {}, "champions_cup": {}, "shield": {}, "world_club": {}}
not_top = {1939, 1992, 1993, 1994}         # Ashvale outside the top flight (Second Division 1939, 1992-94)
for y in range(1889, 2027):
    if y in WAR: continue
    avoid = {"Ashvale Rovers"}                 # (all Ashvale's top-two finishes are fixed by the profile)
    ch = "Ashvale Rovers" if y in H["League champions"] else pick(names, y, strength, avoid)
    ru = "Ashvale Rovers" if y in H["League runners-up"] else pick(names, y, strength, avoid | {ch})
    roll["league"][y] = [ch, ru]
for y in range(1872, 2027):
    if y in WAR: continue
    win = "Ashvale Rovers" if y in H["Founders' Cup"] else pick(names, y, strength, {"Ashvale Rovers"}, 1.0)
    roll["association_cup"][y] = [win, pick(names, y, strength, {win, "Ashvale Rovers"}, 1.0)]
for y in range(1961, 2027):
    win = "Ashvale Rovers" if y in H["Charter Cup"] else pick(names, y, strength, {"Ashvale Rovers"}, 1.0)
    roll["league_cup"][y] = [win, pick(names, y, strength, {win, "Ashvale Rovers"}, 1.0)]
def cont(y, ours_won, comp_share):
    if ours_won:
        return "Ashvale Rovers"
    if rng.random() < comp_share:
        return pick(names, y, strength, {"Ashvale Rovers"})
    if rng.random() < 0.3:
        return pick(es, y, es_str)
    return rng.choice(abroad_eu)
for y in range(1956, 2027):
    win = cont(y, y in H["Crown of Europe"], 0.18)
    ru = "FC Rheinfeld" if y == 1979 else cont(y, False, 0.12)
    while ru == win: ru = cont(y, False, 0.12)
    roll["champions_cup"][y] = [win, ru]
for y in range(1972, 2027):
    win = cont(y, y in H["Europa Trophy"], 0.22)
    ru = cont(y, False, 0.15)
    while ru == win: ru = cont(y, False, 0.15)
    roll["shield"][y] = [win, ru]
for y in range(1960, 2026):
    eu = roll["champions_cup"][y][0]
    sa = "Boca del Plata" if y == 1979 else rng.choice(south)
    if y == 1979:
        roll["world_club"][y] = [eu, sa]
    else:
        roll["world_club"][y] = [eu, sa] if rng.random() < 0.55 else [sa, eu]
roll["league"][1991] = ["Bramhall Borough", "Millbrook United"]   # (Bramhall's profile: champions 1991, so in the 1992 Crown of Europe)
# ---------------------------------------------------------------------------------------------------
# DIVISION 1 (Nov 2026): the second tier's clubs get a past too.  Everything above is unchanged (same
# random numbers); this part has its own.  Some old titles and cups go to clubs now in Division 1 (like
# Preston, Huddersfield or Sheffield Wednesday in real life) - never a year with Ashvale, Northwick or
# Bramhall in it (their profiles fix those) - and a second-tier roll: the Second Division until 1992,
# Division 1 since the Premier Division began in 1992-93; play-offs since 1987.
# ---------------------------------------------------------------------------------------------------
rng2 = random.Random(1888)
d1 = [r["name"] for r in csv.DictReader(open(f"{W}/d1_clubs.csv"))]
d1_str = {r["name"]: int(r["strength"]) for r in csv.DictReader(open(f"{W}/d1_clubs.csv"))}
era2 = {n: {b: rng2.uniform(0.2, 2.2) for b in range(1860, 2040, 20)} for n in d1}
PROTECTED = {"Ashvale Rovers", "Northwick FC", "Bramhall Borough"}
def w2(n, year):
    return max(0.05, (d1_str[n] - 38) * era2[n][(year // 20) * 20])
def pick2(year, avoid=()):
    pool = [n for n in d1 if n not in avoid]
    return rng2.choices(pool, [w2(n, year) for n in pool])[0]
def share(year, table):
    for until, sh in table:
        if year < until:
            return sh
    return 0.0
SHARES = {"league": ((1915, 0.30), (1960, 0.22), (1992, 0.10)),
          "association_cup": ((1915, 0.35), (1960, 0.25), (1992, 0.15), (2100, 0.07)),
          "league_cup": ((1992, 0.15), (2100, 0.06))}
FIXED = {("league", 1991)}
for comp, table in SHARES.items():
    for y in sorted(roll[comp]):
        ch, ru = roll[comp][y]
        if (comp, y) in FIXED or ch in PROTECTED or ru in PROTECTED:
            continue
        if rng2.random() < share(y, table):
            ch = pick2(y, {ru})
        if rng2.random() < share(y, table) * 1.2:
            ru = pick2(y, {ch})
        roll[comp][y] = [ch, ru]
# The second tier
ASH_DOWN = {1939: "champion", 1992: None, 1993: None, 1994: "champion"}      # (Ashvale's profile)
NEVER_DOWN = {"Northwick FC", "Bramhall Borough"}
pl_others = [n for n in names if n not in PROTECTED]
roll["second_tier"], roll["second_tier_playoffs"] = {}, {}
for y in range(1893, 2027):
    if y in WAR:
        continue
    top = set(roll["league"].get(y, [])) | set(roll["league"].get(y - 1, [])) | set(roll["league"].get(y + 1, []))
    up_last = set(roll["second_tier"].get(y - 1, [])) | set(roll["second_tier_playoffs"].get(y - 1, [])[:1])
    if y == 2025:
        up_last |= {"Holloway Vale", "Harrowby Athletic", "Fernley Park", "Saltmarsh Athletic"}   # (2026's, below)
    pool = [n for n in d1 + pl_others if n not in top and n not in up_last]
    wts = [w2(n, y) if n in d1 else 0.5 * max(1, 80 - strength[n]) * era[n][(y // 20) * 20] for n in pool]   # (smaller clubs go down more)
    def draw(avoid):
        pp = [(n, x) for n, x in zip(pool, wts) if n not in avoid]
        return rng2.choices([n for n, _ in pp], [x for _, x in pp])[0]
    if y == 2026:                       # (last season: the Premier Division's three newest clubs came up)
        ch, ru, po = "Holloway Vale", "Harrowby Athletic", "Fernley Park"
    else:
        ch = "Ashvale Rovers" if ASH_DOWN.get(y) == "champion" else draw(set())
        ru = draw({ch})
        po = draw({ch, ru}) if y >= 1987 else None
    roll["second_tier"][y] = [ch, ru]
    if po:
        roll["second_tier_playoffs"][y] = [po, draw({ch, ru, po}) if y != 2026 else "Saltmarsh Athletic"]
# A beaten play-off finalist stayed down - so it has to be a club that's in Division 1 now (a Premier Division
# club today would have needed promoting later, and the roll doesn't know that it was).  Own random numbers, so
# nothing above changes.
rng3 = random.Random(1987)
for y in sorted(roll["second_tier_playoffs"]):
    w, ru = roll["second_tier_playoffs"][y]
    if ru not in d1:
        busy = set(roll["second_tier"].get(y, [])) | {w}
        roll["second_tier_playoffs"][y] = [w, rng3.choice([n for n in d1 if n not in busy])]
# The Crown of Europe: an English club in it must have got there - league champions the
# season before, or the holders (and, from 1998 when the competition opened up, the runners-up too).
# Entries that can't have qualified go to the club that did (never one of the three with profiles);
# the Intercontinental Cup follows its winner.  (Ashvale's, Northwick's and Bramhall's entries are fixed.)
english = set(names) | set(d1)
CUP_FIXED = {2000, 2005}          # (Northwick's profile: those finals were lost to Stonecross Albion)
for y in sorted(roll["champions_cup"]):
    if y in CUP_FIXED:
        continue
    pair = list(roll["champions_cup"][y])
    for i, club in enumerate(pair):
        if club not in english or club in PROTECTED:
            continue
        prev = roll["league"].get(y - 1, [None, None])
        ok = {prev[0]} | ({prev[1]} if y >= 1998 else set()) | {roll["champions_cup"].get(y - 1, [None])[0]}
        if club in ok:
            continue
        cands = [n for n in ([prev[0]] + ([prev[1]] if y >= 1998 else [])) if n and n not in PROTECTED and n not in pair]
        new_club = cands[0] if cands else rng2.choice([n for n in abroad_eu if n not in pair])
        pair[i] = new_club
        if i == 0 and y in roll["world_club"]:
            roll["world_club"][y] = [new_club if n == club else n for n in roll["world_club"][y]]
    roll["champions_cup"][y] = pair
out = {"about": "Every season's winners and runners-up (year = the season's end; 1893 = 1892-93). Intercontinental Cup: "
                "the Crown of Europe winners v South America's champions.",
       "competitions": {"league": "The League", "association_cup": "The Founders' Cup", "league_cup": "The Charter Cup",
                        "champions_cup": "The Crown of Europe", "shield": "The Europa Trophy",
                        "world_club": "The Intercontinental Cup",
                        "second_tier": "Second Division / Division 1", "second_tier_playoffs": "Division 1 play-offs"},
       "roll": {k: {str(y): v for y, v in d.items()} for k, d in roll.items()}}
json.dump(out, open(f"{W}/honours.json", "w"), indent=0)
from collections import Counter
for k in ("league", "association_cup", "league_cup", "champions_cup", "second_tier"):
    print(k, Counter(v[0] for v in roll[k].values()).most_common(8))
# check Ashvale consistency
for comp, key in (("league", "League champions"), ("association_cup", "Founders' Cup"), ("league_cup", "Charter Cup"),
                  ("champions_cup", "Crown of Europe"), ("shield", "Europa Trophy"), ("world_club", "Intercontinental Cup")):
    got = sorted(int(y) for y, v in roll[comp].items() if v[0] == "Ashvale Rovers")
    assert got == sorted(H[key]), (comp, got, H[key])
assert sorted(y for y, v in roll["league"].items() if v[1] == "Ashvale Rovers") == sorted(H["League runners-up"])
print("consistent")
