"""
career/spain.py
===============
A second league, in Spain, that plays in the background: the PRIMERA LIGA.

  - 20 fictional clubs, their players made exactly like ours (career/clubs.py:
    the same attribute scales, real-world pace by position...) - the same in
    every career, kept in data/world/es_clubs.csv and es_players.csv (edit
    them like the Premier League files)
  - it plays on the same weekends as our league.  Matches are QUICK RESULTS,
    not the match engine: each side's goals come from the two XIs' ratings
    (a Poisson model tuned to LaLiga: ~2.6 goals a game, home sides win ~45%,
    the champions take ~85-90 points); scorers are picked by position and
    finishing.  Players get injured (matches and training), develop with
    minutes, age, retire; clubs bring in youth, renew contracts, release
    players, buy and sell - from Spain, from the Premier League (including
    from you), from the rest of the world.
  - money on LaLiga's scale (career/finance.py LEAGUE["es"]): two giants,
    then a steep drop
  - SQUAD RULES (LaLiga): 25 registered, at most FIVE non-EU players (British
    players are non-EU since Brexit) - and only THREE of them in a matchday
    squad; players aged 22 or under can play from the B team without a
    place on the list

HOW IT FITS IN: the Spanish clubs live in career["spain"]["clubs"] with ids
100-119 (ours are 0-19), so transfers can tell them apart.  The rest of the
career code (contracts, ageing, money...) runs on Spain through a VIEW - the
career seen from Spain - which shares the free-agent pool, the date and the
transfer records with the real career.
"""

import datetime as dt
import math
import os
import random

from career import calendar as cal
from career import clubs as clubs_mod
from career import world as world_mod

NAME = "Primera Liga"
ID_BASE = 100
WORLD_SEED = 3034
CLUBS_FILE = os.path.join(world_mod.WORLD_DIR, "es_clubs.csv")
PLAYERS_FILE = os.path.join(world_mod.WORLD_DIR, "es_players.csv")

# The clubs' levels, best first - LaLiga-like: two giants (as good as our best),
# a strong third, then a long, even middle
STRENGTHS = (78, 76, 71, 68, 66, 65, 64, 63, 62, 61, 60, 59, 58, 58, 57, 56, 55, 54, 53, 52)
CLUBS = [
    ("Real Castellar", "Castellar", (235, 235, 235)),
    ("CE Vallbona", "Vallbona", (150, 30, 70)),
    ("Atletico Almenara", "Almenara", (200, 40, 50)),
    ("Real Torrevega", "Torrevega", (40, 150, 80)),
    ("Valdeluz CF", "Valdeluz", (240, 140, 30)),
    ("Deportivo Penaclara", "Penaclara", (60, 110, 200)),
    ("CD Lizarra", "Lizarra", (170, 20, 30)),
    ("Villarrubia CF", "Villarrubia", (245, 215, 40)),
    ("Union Monteverde", "Monteverde", (30, 120, 60)),
    ("Racing Calahonda", "Calahonda", (120, 190, 230)),
    ("SD Altamira", "Altamira", (120, 60, 160)),
    ("UD Valdesierra", "Valdesierra", (30, 40, 110)),
    ("CF Rio Seco", "Rio Seco", (170, 120, 40)),
    ("Real Cabo Fresno", "Cabo Fresno", (40, 80, 170)),
    ("CD Aldeavieja", "Aldeavieja", (60, 60, 60)),
    ("Atletico Benarraba", "Benarraba", (150, 25, 25)),
    ("UD Ribera", "Ribera", (30, 150, 150)),
    ("CF Montoro", "Montoro", (110, 30, 50)),
    ("SD Villanegra", "Villanegra", (25, 25, 25)),
    ("Maritimo Puerto Lindo", "Puerto Lindo", (90, 170, 220)),
]
# Names without accents (the match engine's files are read as plain text on Windows)
FIRST = ["Alvaro", "Pablo", "Sergio", "Javier", "Iker", "Hugo", "Mario", "Diego", "Adrian", "Raul", "Ruben",
         "Marcos", "Daniel", "Alejandro", "David", "Carlos", "Jorge", "Ivan", "Oscar", "Unai", "Aitor", "Gorka",
         "Pau", "Marc", "Jordi", "Nico", "Dani", "Fran", "Rodrigo", "Gonzalo", "Hector", "Victor", "Samuel",
         "Lucas", "Mateo", "Alex", "Borja", "Isco", "Koke", "Jon", "Ander", "Eneko", "Xabi", "Miguel", "Ismael",
         "Joan", "Gerard", "Oriol", "Ramon", "Manu", "Juanma", "Antonio", "Luis", "Enrique", "Ignacio", "Bruno"]
LAST = ["Garcia", "Martinez", "Lopez", "Sanchez", "Perez", "Gomez", "Fernandez", "Ruiz", "Diaz", "Moreno",
        "Munoz", "Alvarez", "Romero", "Navarro", "Torres", "Dominguez", "Vazquez", "Ramos", "Gil", "Serrano",
        "Blanco", "Molina", "Ortega", "Delgado", "Castro", "Ortiz", "Rubio", "Marin", "Sanz", "Iglesias",
        "Medina", "Garrido", "Cortes", "Castillo", "Santos", "Lozano", "Guerrero", "Cano", "Prieto", "Mendez",
        "Cruz", "Calvo", "Gallego", "Vidal", "Leon", "Herrera", "Marquez", "Pena", "Flores", "Cabrera",
        "Campos", "Vega", "Fuentes", "Carrasco", "Caballero", "Reyes", "Nieto", "Aguilar", "Pascual",
        "Herrero", "Lorenzo", "Hidalgo", "Montero", "Ibanez", "Gimenez", "Ferrer", "Duran", "Etxeberria",
        "Aranburu", "Puig", "Soler", "Busquets", "Llorente", "Zubieta", "Arrieta", "Olmo", "Bravo"]
# EU players from elsewhere, and non-EU (South America, Africa...)
FIRST_EU = ["Joao", "Tiago", "Rui", "Andre", "Luca", "Matteo", "Theo", "Hugo", "Lukas", "Jan", "Milan", "Ivan"]
LAST_EU = ["Silva", "Costa", "Pereira", "Rossi", "Ricci", "Moreau", "Laurent", "Novak", "Horvat", "Kovac",
           "Muller", "Jansen", "De Vries", "Nilsson", "Popescu", "Ferreira", "Mendes"]
FIRST_NON_EU = ["Thiago", "Matias", "Santiago", "Joaquin", "Facundo", "Emiliano", "Kevin", "Brayan", "Yeferson",
                "Wilmer", "Moussa", "Ibrahima", "Cheikh", "Gabriel", "Rafael", "Vinicius", "Julian", "Enzo",
                "Lautaro", "Federico", "Jhon", "Darwin", "Youssef", "Achraf", "Takumi"]
LAST_NON_EU = ["Rodriguez", "Gonzalez", "Benitez", "Cabral", "Acosta", "Ramirez", "Cordoba", "Mina", "Valencia",
               "Diallo", "Ndiaye", "Traore", "Camara", "Oliveira", "Souza", "Almeida", "Fernandes", "Paredes",
               "Alvarado", "Quintero", "Medina", "El Idrissi", "Bennani", "Watanabe", "Nunez"]
NON_EU_SHARE = 0.17          # of a squad (LaLiga squads carry 3-5 non-EU players)
OTHER_EU_SHARE = 0.15        # EU players from outside Spain
MAX_NON_EU = 5               # registered (LaLiga)
MAX_NON_EU_MATCHDAY = 3      # in a matchday squad
B_TEAM_AGE = 22              # 22 or under: can play from the B team, no place on the list needed
BRITISH_NON_EU = True        # since Brexit

# --- Quick results (tuned: see career/spain.py notes and calibrate()) ---------------
HOME_GOALS = 1.40            # a match between equal sides: home / away goals
AWAY_GOALS = 1.08
GOALS_PER_POINT = 0.040      # each rating point between the XIs: x e^(this) goals for the better side
# (200 simulated seasons: 2.64 goals a game, home 45% / draw 23% / away 31%,
#  champions ~89 points, 10th ~51, bottom ~26 - LaLiga 2024/25: 2.62 goals, 88 / 48 / 16)
SCORER_WEIGHT = {"ST": 3.5, "WM": 2.4, "CM": 1.5, "FB": 0.45, "CB": 0.6, "GK": 0.0,
                 "DM": 0.8, "AM": 2.6, "W": 2.8, "WB": 0.6}
FINISHING_DOUBLES = 25       # x2 the chance of scoring for every 25 points of Finishing (0-100)
MATCH_INJURY = 0.045         # per starter per match (as our engine: 0.0005 a minute)
TRAINING_INJURY = 0.0045     # per player per day (career/training.py)

# Shared with the real career (the rest of a view is Spain's own)
SHARED = ("free_agents", "fa_next_id", "date", "year", "_today", "transfer_log", "payables", "abroad",
          "abroad_next_id", "bids", "talks", "inbox", "calendar", "breaks")


class View:
    """The career seen from Spain: career/* functions run on it as if it were a career."""

    def __init__(self, career):
        self.parent = career
        self.data = career["spain"]

    def _fixed(self, k):
        return {"pl_clubs": self.parent["clubs"], "my_club": -99, "league": "es",
                "name_pool": (FIRST, LAST)}.get(k, KeyError)

    def _where(self, k):
        return self.parent if k in SHARED else self.data

    def __getitem__(self, k):
        f = self._fixed(k)
        if f is not KeyError:
            return f
        return self._where(k)[k]

    def __setitem__(self, k, v):
        self._where(k)[k] = v

    def get(self, k, default=None):
        try:
            return self[k]
        except KeyError:
            return default

    def setdefault(self, k, default=None):
        if self._fixed(k) is not KeyError:
            return self._fixed(k)
        return self._where(k).setdefault(k, default)

    def pop(self, k, *default):
        return self._where(k).pop(k, *default)

    def __contains__(self, k):
        return self._fixed(k) is not KeyError or k in self._where(k)


def view(career):
    return View(career)


def exists(career):
    return "spain" in career


def clubs(career):
    return career["spain"]["clubs"] if exists(career) else []


def club(career, cid):
    return career["spain"]["clubs"][cid - ID_BASE]


def is_spanish(cid):
    return cid is not None and cid >= ID_BASE


# ---------------------------------------------------------------------------
# The world: built once, kept in the files
# ---------------------------------------------------------------------------
def _nationality(rng, p):
    x = rng.random()
    if x < NON_EU_SHARE:
        p["non_eu"] = True
        return FIRST_NON_EU, LAST_NON_EU
    p["non_eu"] = False
    if x < NON_EU_SHARE + OTHER_EU_SHARE:
        return FIRST_EU, LAST_EU
    return FIRST, LAST


def build_world(seed=WORLD_SEED):
    rng = random.Random(seed)
    used = set()
    out = []
    for i, ((name, short, colour), strength) in enumerate(zip(CLUBS, STRENGTHS)):
        defence, build_up = clubs_mod.style_for_rank(i, len(STRENGTHS))
        c = {"id": ID_BASE + i, "name": name, "short": short, "colour": list(colour), "strength": strength,
             "roles": {"base": rng.choice(["blue", "red"])}, "tactics": {"defence": defence, "build_up": build_up},
             "instructions": {}, "players": []}
        pid = 0
        for pos, n in clubs_mod.SQUAD_25:
            for k in range(n):
                age = clubs_mod._age(rng, young=k >= 2)
                peak = strength - clubs_mod.DEPTH_DROP[min(k, len(clubs_mod.DEPTH_DROP) - 1)] \
                    + rng.gauss(0.0, clubs_mod.PLAYER_SPREAD)
                tmp = {}
                names = _nationality(rng, tmp)
                p = clubs_mod._player(rng, pos, peak, used, pid, age=age, names=names)
                p["non_eu"] = tmp["non_eu"]
                c["players"].append(p)
                pid += 1
        _cap_non_eu(c)
        out.append(c)
    world_mod.save(out, CLUBS_FILE, PLAYERS_FILE, extra=("non_eu",))
    return out


def _cap_non_eu(c):
    """A club starts with a legal list: at most MAX_NON_EU non-EU seniors (the rest have EU passports)."""
    ne = sorted((p for p in c["players"] if p.get("non_eu") and p["Age"] > B_TEAM_AGE),
                key=lambda p: -clubs_mod.overall(p))
    for p in ne[MAX_NON_EU:]:
        p["non_eu"] = False


def load_world():
    return world_mod.load(CLUBS_FILE, PLAYERS_FILE, extra=("non_eu",), build_fn=build_world)


# ---------------------------------------------------------------------------
# Setting up (a new career, or an older save)
# ---------------------------------------------------------------------------
def create(career, catch_up=True):
    from career import finance, league, registration
    year = career.get("year", 2026)
    world = load_world()
    for c in world:
        c["league"] = "es"
        for p in c["players"]:
            p["homegrown"] = False
            p["condition"] = 1.0
            p.setdefault("non_eu", False)
    career["spain"] = {"name": NAME, "clubs": world, "results": {}, "matchday": 1, "history": [],
                       "news": [], "season": 1, "start_year": year,
                       "done_to": (cal.parse(f"{year}-07-01") - dt.timedelta(days=1)).isoformat()}
    s = career["spain"]
    s["fixtures"] = league.make_fixtures([c["id"] for c in world], random.Random(WORLD_SEED + year))
    v = view(career)
    finance.init(v, seed=WORLD_SEED)
    for c in world:
        registration.auto_register(c)
        c["lineup"] = clubs_mod.best_lineup(c)
    if catch_up:
        # An older save part-way through a season: Spain has played up to today
        rng = random.Random(WORLD_SEED + 1)
        d = cal.parse(s["done_to"]) + dt.timedelta(days=1)
        while d < cal.parse(career["date"]):
            day(career, d.isoformat(), rng)
            d += dt.timedelta(days=1)
        cal_ = career.get("calendar") or []
        while s["matchday"] < career.get("matchday", 1) and s["matchday"] <= len(cal_):
            play_matchday(career, cal_[s["matchday"] - 1], rng)      # (today's games, if ours are played)


def ensure(career):
    if not exists(career):
        create(career)
    for c in career["spain"]["clubs"]:
        c.setdefault("league", "es")


# ---------------------------------------------------------------------------
# Every day (called from career/transfers.py on_day, for every day of the season)
# ---------------------------------------------------------------------------
def day(career, iso, rng):
    if not exists(career):
        return
    s = career["spain"]
    if cal.parse(iso) <= cal.parse(s["done_to"]):
        return
    from career import finance, contracts, registration
    v = view(career)
    d = cal.parse(iso)
    for c in s["clubs"]:
        finance.daily(v, c, iso)                      # the month's money on the 1st
        contracts.on_day(v, c, iso, rng)              # 1 January: renewals
    if (d.month, d.day) in registration.DEADLINES:
        for c in s["clubs"]:
            registration.auto_register(c)
    if d.weekday() == 0:
        _week(career, iso, rng)                       # development and training knocks, once a week
    cal_ = career.get("calendar") or []
    while s["matchday"] <= len(s["fixtures"]) and s["matchday"] <= len(cal_) \
            and cal.parse(cal_[s["matchday"] - 1]) <= d:
        play_matchday(career, cal_[s["matchday"] - 1], rng)
    s["done_to"] = iso


def _week(career, iso, rng):
    from career import training, availability as av
    for c in clubs(career):
        for p in c["players"]:
            if av.injured(p, iso):
                continue
            if rng.random() < TRAINING_INJURY * 7 * av._age_factor(p):
                name, days = av.roll_injury(rng)
                p["injury"] = {"name": name, "since": iso,
                               "until": (cal.parse(iso) + dt.timedelta(days=days)).isoformat(), "cause": "training"}
                continue
            training.develop(p, 7.0, [], rng)


# ---------------------------------------------------------------------------
# Matches: quick results
# ---------------------------------------------------------------------------
def pick_xi(c, date, vs=None):
    """The best fit XI - nobody injured, at most three non-EU players, no loanee against his parent club."""
    from career import availability as av, registration
    out = {p["id"] for p in c["players"] if av.injured(p, date) or not registration.can_play(c, p)
           or (vs is not None and p.get("loan") and p["loan"]["from"] == vs)}
    while True:
        xi = clubs_mod.best_lineup(c, exclude=out)
        ne = [clubs_mod.player_by_id(c, pid) for pid in xi.values()]
        ne = [p for p in ne if p.get("non_eu")]
        if len(ne) <= MAX_NON_EU_MATCHDAY:
            return xi
        out.add(min(ne, key=clubs_mod.overall)["id"])


def xi_rating(c, xi):
    rs = [clubs_mod.overall(clubs_mod.player_by_id(c, pid), slot) for slot, pid in xi.items()]
    return sum(rs) / max(1, len(rs)) if rs else 40.0


def _poisson(rng, lam):
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p < L:
            return k
        k += 1


def _scorer(rng, c, xi):
    ps = [clubs_mod.player_by_id(c, pid) for pid in xi.values()]
    w = [SCORER_WEIGHT[clubs_mod.NATURAL_GROUP[p["Pos"]]] * 2 ** ((p["Finishing"] - 60) / FINISHING_DOUBLES)
         for p in ps]
    return rng.choices(ps, weights=w)[0]


def quick_result(rng, home, away, hxi, axi):
    """(home goals, away goals) from the two XIs."""
    d = xi_rating(home, hxi) - xi_rating(away, axi)
    hg = _poisson(rng, HOME_GOALS * math.exp(GOALS_PER_POINT * d))
    ag = _poisson(rng, AWAY_GOALS * math.exp(-GOALS_PER_POINT * d))
    return hg, ag


def play_matchday(career, date, rng):
    from career import finance, availability as av
    s = career["spain"]
    v = view(career)
    md = s["matchday"]
    results = []
    for h, a in s["fixtures"][md - 1]:
        H, A = club(career, h), club(career, a)
        hxi, axi = pick_xi(H, date, a), pick_xi(A, date, h)
        H["lineup"], A["lineup"] = hxi, axi
        hg, ag = quick_result(rng, H, A, hxi, axi)
        goals = []
        for side, c, xi, n in ((0, H, hxi, hg), (1, A, axi, ag)):
            for _ in range(n):
                p = _scorer(rng, c, xi)
                p["lg_goals"] = p.get("lg_goals", 0) + 1
                goals.append({"team": side, "name": p["Name"], "minute": rng.randint(1, 90)})
            started = set(xi.values())
            for p in c["players"]:
                mins = 90 if p["id"] in started else 0
                p["mins_avg"] = round(0.75 * p.get("mins_avg", 45) + 0.25 * mins, 1)
                if mins:
                    p["lg_apps"] = p.get("lg_apps", 0) + 1
                    if p.get("loan"):
                        p["loan"]["apps"] = p["loan"].get("apps", 0) + 1
                    if rng.random() < MATCH_INJURY * av._age_factor(p):
                        name, days = av.roll_injury(rng)
                        p["injury"] = {"name": name, "since": date, "cause": "match",
                                       "until": (cal.parse(date) + dt.timedelta(days=days)).isoformat()}
        goals.sort(key=lambda g: g["minute"])
        results.append({"home": h, "away": a, "hg": hg, "ag": ag, "goals": goals})
        finance.home_game(v, H)
    s["results"][str(md)] = results
    s["matchday"] = md + 1


def table(career):
    from career import league
    return league.table(view(career))


def position_of(career, cid):
    for i, r in enumerate(table(career), start=1):
        if r["club"] == cid:
            return i
    return None


def top_scorers(career, n=10):
    rows = [(p.get("lg_goals", 0), p, c) for c in clubs(career) for p in c["players"] if p.get("lg_goals")]
    rows.sort(key=lambda t: -t[0])
    return rows[:n]


def season_over(career):
    s = career["spain"]
    return s["matchday"] > len(s["fixtures"])


# ---------------------------------------------------------------------------
# End of the season and the summer (called from career/league.py new_season)
# ---------------------------------------------------------------------------
def season_end(career, rng):
    """The last matches (if any are left), merit money, the record."""
    if not exists(career):
        return
    from career import finance
    s = career["spain"]
    cal_ = career.get("calendar") or []
    while not season_over(career):
        play_matchday(career, cal_[min(s["matchday"], len(cal_)) - 1], rng)
    t = table(career)
    finance.season_end(view(career), t)
    best = max(((p.get("lg_goals", 0), p["Name"], c["name"]) for c in clubs(career) for p in c["players"]),
               default=(0, "", ""))
    s["history"].append({"season": s["season"], "year": career.get("year"), "champion": t[0]["club"],
                         "table": [r["club"] for r in t], "top_scorer": list(best)})
    s["history"] = s["history"][-30:]


def summer(career, rng):
    """After our summer (career/league.py): the same yearly cycle for Spain."""
    if not exists(career):
        return
    from career import contracts, ageing, finance, registration, league, training
    s = career["spain"]
    v = view(career)
    s["season"] += 1
    s["results"] = {}
    s["matchday"] = 1
    s["fixtures"] = league.make_fixtures([c["id"] for c in s["clubs"]], random.Random(rng.random()))
    contracts.summer_departures(v, rng)
    ageing.summer(v, rng)
    contracts.ai_sign_free_agents(v, rng)
    finance.new_season(v, rng)
    for c in s["clubs"]:
        for p in c["players"]:
            p["lg_goals"] = 0
            p["lg_apps"] = 0
            p["season_gain"] = 0
            p["season_start_rating"] = clubs_mod.overall(p)
            arrives(p)                                   # (free agents just signed: EU or not)
            p.setdefault("homegrown", False)
        registration.auto_register(c)
        c["lineup"] = pick_xi(c, career["date"])
    s["done_to"] = (cal.parse(career["date"]) - dt.timedelta(days=1)).isoformat()
    s["news"] = s.get("news", [])[-200:]


# ---------------------------------------------------------------------------
# Players moving in and out of Spain
# ---------------------------------------------------------------------------
def arrives(p, rng=None):
    """A player joining a Spanish club from elsewhere: is he an EU citizen?"""
    if "non_eu" in p:
        return
    rng = rng or random.Random(p.get("Name"))
    if p.get("homegrown") and BRITISH_NON_EU:
        p["non_eu"] = True                     # an English-trained player: British, so non-EU since Brexit
    else:
        p["non_eu"] = rng.random() < 0.45


# ---------------------------------------------------------------------------
# Tuning check: python -m career.spain
# ---------------------------------------------------------------------------
def calibrate(seasons=200, seed=1):
    """Simulate seasons with the starting squads: goals, home / draw / away, points."""
    rng = random.Random(seed)
    w = build_world() if not os.path.exists(CLUBS_FILE) else load_world()
    from career import league
    xis = {c["id"]: clubs_mod.best_lineup(c) for c in w}
    by = {c["id"]: c for c in w}
    goals = games = hw = dr = 0
    first = []
    last = []
    tenth = []
    for _ in range(seasons):
        pts = {c["id"]: 0 for c in w}
        for dayf in league.make_fixtures(list(by), rng):
            for h, a in dayf:
                hg, ag = quick_result(rng, by[h], by[a], xis[h], xis[a])
                goals += hg + ag
                games += 1
                if hg > ag:
                    hw += 1; pts[h] += 3
                elif hg == ag:
                    dr += 1; pts[h] += 1; pts[a] += 1
                else:
                    pts[a] += 3
        s = sorted(pts.values(), reverse=True)
        first.append(s[0]); tenth.append(s[9]); last.append(s[-1])
    print(f"goals/game {goals / games:.2f}  home {hw / games:.0%}  draw {dr / games:.0%}  "
          f"away {1 - (hw + dr) / games:.0%}")
    print(f"points: 1st {sum(first) / seasons:.0f}  10th {sum(tenth) / seasons:.0f}  20th {sum(last) / seasons:.0f}")
    print("XI ratings:", [round(xi_rating(c, xis[c["id"]])) for c in w])


if __name__ == "__main__":
    calibrate()
