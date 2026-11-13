"""
career/foreign.py
=================
More leagues in the background, like Spain's (career/spain.py): GERMANY's and ITALY's top flights.

  - their clubs and players are made like everyone else's (career/clubs.py), the same in every career, kept
    in data/world/<key>_clubs.csv and <key>_players.csv (edit them like the others)
  - quick results on our league's match days (the Spanish league's model, career/spain.py); the season runs
    to their own number of rounds (the Bundesliga's 18 clubs: 34)
  - their own money (career/finance.py LEAGUE["de" / "it"]), contracts, youth, ageing and retirements -
    through a "view" of the career, like Spain's; they keep their own pool of free agents
  - their best go into the continental cups (career/europe.py)
  - (not yet: transfers between them and us)

Ids: Germany 120-137, Italy 140-159.
"""

import datetime as dt
import os
import random

from career import calendar as cal
from career import clubs as clubs_mod
from career import world as world_mod


class Config:
    def __init__(self, key, name, country, id_base, seed, clubs, strengths, first, last):
        self.key, self.name, self.country, self.id_base, self.seed = key, name, country, id_base, seed
        self.clubs, self.strengths, self.first, self.last = clubs, strengths, first, last
        self.clubs_file = os.path.join(world_mod.WORLD_DIR, f"{key}_clubs.csv")
        self.players_file = os.path.join(world_mod.WORLD_DIR, f"{key}_players.csv")


GERMANY = Config(
    "de", "Bundesliga", "Germany", 120, 4048,
    [("FC Rheinfeld", "Rheinfeld", (210, 20, 40)), ("Borussia Kaltenbach", "Kaltenbach", (245, 205, 30)),
     ("SV Edelstein", "Edelstein", (230, 30, 30)), ("Eintracht Lindenau", "Lindenau", (20, 20, 20)),
     ("VfB Hohenwald", "Hohenwald", (240, 240, 240)), ("SC Altmark", "Altmark", (200, 20, 20)),
     ("TSG Weidenbach", "Weidenbach", (30, 90, 180)), ("SC Grunfeld", "Grunfeld", (30, 140, 60)),
     ("Fortuna Elbstadt", "Elbstadt", (210, 30, 40)), ("FC Seeburg", "Seeburg", (30, 70, 160)),
     ("1. FC Bergheim", "Bergheim", (230, 40, 40)), ("SV Moorstadt", "Moorstadt", (30, 130, 70)),
     ("VfL Ostwald", "Ostwald", (40, 140, 60)), ("Union Spreewald", "Spreewald", (200, 30, 30)),
     ("FSV Mainau", "Mainau", (210, 30, 40)), ("SpVgg Talheim", "Talheim", (20, 110, 60)),
     ("TuS Kohlberg", "Kohlberg", (30, 50, 120)), ("SV Nordhafen", "Nordhafen", (30, 60, 140))],
    (80, 76, 73, 70, 68, 66, 65, 64, 63, 62, 61, 60, 59, 58, 57, 56, 55, 54),
    ["Lukas", "Jonas", "Leon", "Felix", "Paul", "Maximilian", "Niklas", "Julian", "Tim", "Jan", "Florian",
     "Kai", "Timo", "Marco", "Mats", "Thomas", "Joshua", "Niclas", "Robin", "Benjamin",
     "Kevin", "Dennis", "Marvin", "Moritz", "Tobias", "Sebastian", "Pascal", "Lars", "Jamal", "Karim", "Emre"],
    ["Muller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann",
     "Koch", "Richter", "Klein", "Wolf", "Neumann", "Schwarz", "Zimmermann", "Braun", "Kruger", "Hartmann",
     "Lange", "Werner", "Krause", "Lehmann", "Kohler", "Kaiser", "Fuchs", "Brandt", "Vogt", "Arnold",
     "Yildiz", "Demir", "Kowalski", "Nowak"])

ITALY = Config(
    "it", "Serie Italia", "Italy", 140, 5059,
    [("Inter Valmora", "Valmora", (20, 60, 160)), ("AC Montevera", "Montevera", (200, 20, 30)),
     ("Virtus Calderano", "Calderano", (20, 20, 20)), ("SS Aurelia", "Aurelia", (120, 200, 230)),
     ("SSC Vesuvia", "Vesuvia", (40, 140, 220)), ("US Orobica", "Orobica", (20, 40, 100)),
     ("ACF Arnaldi", "Arnaldi", (110, 50, 150)), ("AC Collina", "Collina", (130, 20, 30)),
     ("US Felsina", "Felsina", (160, 20, 40)), ("Pro Lanterna", "Lanterna", (150, 20, 40)),
     ("US Carnia", "Carnia", (240, 240, 240)), ("Unione Marina", "Marina", (30, 70, 160)),
     ("Calcio Isola", "Isola", (160, 20, 40)), ("Virtus Scaligera", "Scaligera", (240, 210, 30)),
     ("US Salento", "Salento", (240, 200, 30)), ("AC Valdarno", "Valdarno", (30, 90, 170)),
     ("Calcio Crociata", "Crociata", (245, 245, 245)), ("FC Lariana", "Lariana", (30, 90, 180)),
     ("AC Laguna", "Laguna", (240, 120, 30)), ("US Brianza", "Brianza", (200, 30, 40))],
    (79, 77, 76, 73, 72, 70, 68, 66, 64, 63, 62, 61, 60, 59, 58, 57, 56, 55, 54, 53),
    ["Marco", "Luca", "Alessandro", "Lorenzo", "Matteo", "Andrea", "Federico", "Gianluca", "Nicolo", "Davide",
     "Simone", "Giacomo", "Riccardo", "Stefano", "Francesco", "Gianluigi", "Ciro", "Domenico", "Leonardo",
     "Manuel", "Sandro", "Giorgio", "Mattia", "Pietro", "Filippo", "Tommaso", "Rafael", "Theo", "Victor"],
    ["Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo", "Ricci", "Marino", "Greco",
     "Bruno", "Gallo", "Conti", "De Luca", "Mancini", "Costa", "Giordano", "Rizzo", "Lombardi", "Moretti",
     "Barbieri", "Fontana", "Santoro", "Mariani", "Rinaldi", "Caruso", "Ferrara", "Galli", "Martini",
     "Leone", "Longo", "Gentile", "Martinelli", "Vitale"])

LEAGUES = (GERMANY, ITALY)


def by_key(key):
    return next(c for c in LEAGUES if c.key == key)


# ---------------------------------------------------------------------------
# The world: built once, kept in the files
# ---------------------------------------------------------------------------
def build_world(cfg):
    rng = random.Random(cfg.seed)
    used = set()
    out = []
    for i, ((nm, short, colour), strength) in enumerate(zip(cfg.clubs, cfg.strengths)):
        defence, build_up = clubs_mod.style_for_rank(i, len(cfg.strengths))
        c = {"id": cfg.id_base + i, "name": nm, "short": short, "colour": list(colour), "strength": strength,
             "roles": {"base": rng.choice(["blue", "red"])}, "tactics": {"defence": defence, "build_up": build_up},
             "instructions": {}, "players": []}
        pid = 0
        for pos, n in clubs_mod.SQUAD_25:
            for k in range(n):
                age = clubs_mod._age(rng, young=k >= 2)
                peak = strength - clubs_mod.DEPTH_DROP[min(k, len(clubs_mod.DEPTH_DROP) - 1)] \
                    + rng.gauss(0.0, clubs_mod.PLAYER_SPREAD)
                c["players"].append(clubs_mod._player(rng, pos, peak, used, pid, age=age, names=(cfg.first, cfg.last)))
                pid += 1
        out.append(c)
    world_mod.save(out, cfg.clubs_file, cfg.players_file)
    return out


def load_world(cfg):
    return world_mod.load(cfg.clubs_file, cfg.players_file, build_fn=lambda: build_world(cfg))


# ---------------------------------------------------------------------------
# The career seen from a league (career/* functions run on it as if it were a career)
# ---------------------------------------------------------------------------
SHARED = ("date", "year", "_today", "transfer_log", "payables", "abroad", "abroad_next_id", "bids", "talks",
          "inbox", "calendar", "breaks")


class View:
    def __init__(self, career, cfg):
        self.parent, self.cfg = career, cfg
        self.data = career["leagues"][cfg.key]

    def _fixed(self, k):
        return {"pl_clubs": [c for c in self.parent["clubs"] if c.get("league", "pl") == "pl"], "my_club": -99,
                "league": self.cfg.key, "name_pool": (self.cfg.first, self.cfg.last)}.get(k, KeyError)

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


def view(career, cfg):
    return View(career, cfg)


def exists(career, cfg):
    return cfg.key in career.get("leagues", {})


def clubs(career, cfg):
    return career["leagues"][cfg.key]["clubs"] if exists(career, cfg) else []


def club(career, cid):
    """A club in any of these leagues by id (or None)."""
    for cfg in LEAGUES:
        if exists(career, cfg) and cfg.id_base <= (cid or -1) < cfg.id_base + len(clubs(career, cfg)):
            return clubs(career, cfg)[cid - cfg.id_base]
    return None


def league_of_id(cid):
    for cfg in LEAGUES:
        if cfg.id_base <= (cid or -1) < cfg.id_base + 20:
            return cfg
    return None


# ---------------------------------------------------------------------------
# Setting up
# ---------------------------------------------------------------------------
def create(career, cfg):
    from career import finance, league, registration
    year = career.get("year", 2026)
    w = load_world(cfg)
    for c in w:
        c["league"] = cfg.key
        for p in c["players"]:
            p["homegrown"] = True
            p["condition"] = 1.0
    career.setdefault("leagues", {})[cfg.key] = {
        "name": cfg.name, "clubs": w, "results": {}, "matchday": 1, "history": [], "season": 1,
        "start_year": year, "free_agents": {"id": -1, "name": "Free agent", "short": "Free agent",
                                             "colour": [120, 120, 120], "players": [], "lineup": {}, "strength": 55},
        "done_to": (cal.parse(f"{year}-07-01") - dt.timedelta(days=1)).isoformat()}
    d = career["leagues"][cfg.key]
    d["fixtures"] = league.make_fixtures([c["id"] for c in w], random.Random(cfg.seed + year))
    v = view(career, cfg)
    finance.init(v, seed=cfg.seed)
    for c in w:
        registration.auto_register(c)
        c["lineup"] = clubs_mod.best_lineup(c)
    rng = random.Random(cfg.seed + 1)
    dd = cal.parse(d["done_to"]) + dt.timedelta(days=1)
    while dd < cal.parse(career["date"]):                 # (an older save part-way through a season)
        day(career, dd.isoformat(), rng)
        dd += dt.timedelta(days=1)


def ensure(career):
    for cfg in LEAGUES:
        if not exists(career, cfg):
            create(career, cfg)


# ---------------------------------------------------------------------------
# Every day (career/transfers.py on_day)
# ---------------------------------------------------------------------------
def day(career, iso, rng):
    for cfg in LEAGUES:
        if exists(career, cfg):
            _day(career, cfg, iso, rng)


def _day(career, cfg, iso, rng):
    d = career["leagues"][cfg.key]
    if cal.parse(iso) <= cal.parse(d["done_to"]):
        return
    from career import finance, contracts, registration, spain
    v = view(career, cfg)
    dd = cal.parse(iso)
    for c in d["clubs"]:
        finance.daily(v, c, iso)
        contracts.on_day(v, c, iso, rng)
    if (dd.month, dd.day) in registration.DEADLINES:
        for c in d["clubs"]:
            registration.auto_register(c)
    if dd.weekday() == 0:
        _week(career, cfg, iso, rng)
    cal_ = career.get("calendar") or []
    while d["matchday"] <= len(d["fixtures"]) and d["matchday"] <= len(cal_) \
            and cal.parse(cal_[d["matchday"] - 1]) <= dd:
        play_matchday(career, cfg, cal_[d["matchday"] - 1], rng)
    d["done_to"] = iso


def _week(career, cfg, iso, rng):
    from career import training, availability as av, spain
    for c in clubs(career, cfg):
        for p in c["players"]:
            if av.injured(p, iso):
                continue
            if rng.random() < spain.TRAINING_INJURY * 7 * av._age_factor(p):
                nm, days = av.roll_injury(rng)
                p["injury"] = {"name": nm, "since": iso, "cause": "training",
                               "until": (cal.parse(iso) + dt.timedelta(days=days)).isoformat()}
                continue
            training.develop(p, 7.0, [], rng)


def play_matchday(career, cfg, date, rng):
    from career import spain, finance, availability as av
    d = career["leagues"][cfg.key]
    v = view(career, cfg)
    md = d["matchday"]
    results = []
    by = {c["id"]: c for c in d["clubs"]}
    for h, a in d["fixtures"][md - 1]:
        H, A = by[h], by[a]
        hxi, axi = spain.pick_xi(H, date, a), spain.pick_xi(A, date, h)
        H["lineup"], A["lineup"] = hxi, axi
        hg, ag = spain.quick_result(rng, H, A, hxi, axi)
        goals = []
        for side, c, xi, n in ((0, H, hxi, hg), (1, A, axi, ag)):
            for _ in range(n):
                p = spain._scorer(rng, c, xi)
                p["lg_goals"] = p.get("lg_goals", 0) + 1
                goals.append({"team": side, "name": p["Name"], "minute": rng.randint(1, 90)})
            started = set(xi.values())
            for p in c["players"]:
                mins = 90 if p["id"] in started else 0
                p["mins_avg"] = round(0.75 * p.get("mins_avg", 45) + 0.25 * mins, 1)
                if mins:
                    p["lg_apps"] = p.get("lg_apps", 0) + 1
                    if rng.random() < spain.MATCH_INJURY * av._age_factor(p):
                        nm, days = av.roll_injury(rng)
                        p["injury"] = {"name": nm, "since": date, "cause": "match",
                                       "until": (cal.parse(date) + dt.timedelta(days=days)).isoformat()}
        goals.sort(key=lambda g: g["minute"])
        results.append({"home": h, "away": a, "hg": hg, "ag": ag, "goals": goals})
        finance.home_game(v, H)
    d["results"][str(md)] = results
    d["matchday"] = md + 1


def table(career, cfg):
    from career import league
    return league.table(view(career, cfg))


def top_scorers(career, cfg, n=10):
    rows = [(p.get("lg_goals", 0), p, c) for c in clubs(career, cfg) for p in c["players"] if p.get("lg_goals")]
    rows.sort(key=lambda t: -t[0])
    return rows[:n]


def season_over(career, cfg):
    d = career["leagues"][cfg.key]
    return d["matchday"] > len(d["fixtures"])


# ---------------------------------------------------------------------------
# The end of a season and the summer (career/league.py new_season)
# ---------------------------------------------------------------------------
def season_end(career, rng):
    from career import finance
    for cfg in LEAGUES:
        if not exists(career, cfg):
            continue
        d = career["leagues"][cfg.key]
        cal_ = career.get("calendar") or []
        while not season_over(career, cfg):
            play_matchday(career, cfg, cal_[min(d["matchday"], len(cal_)) - 1], rng)
        t = table(career, cfg)
        finance.season_end(view(career, cfg), t)
        best = max(((p.get("lg_goals", 0), p["Name"], c["name"]) for c in clubs(career, cfg) for p in c["players"]),
                   default=(0, "", ""))
        d["history"].append({"season": d["season"], "year": career.get("year"), "champion": t[0]["club"],
                             "table": [r["club"] for r in t], "top_scorer": list(best)})
        d["history"] = d["history"][-30:]


def summer(career, rng):
    from career import contracts, ageing, finance, registration, league
    for cfg in LEAGUES:
        if not exists(career, cfg):
            continue
        d = career["leagues"][cfg.key]
        v = view(career, cfg)
        d["season"] += 1
        d["results"] = {}
        d["matchday"] = 1
        d["fixtures"] = league.make_fixtures([c["id"] for c in d["clubs"]], random.Random(rng.random()))
        contracts.summer_departures(v, rng)
        ageing.summer(v, rng)
        contracts.new_outside_players(v, rng)
        contracts.ai_sign_free_agents(v, rng)
        contracts.trim_free_agents(v)
        finance.new_season(v, rng)
        for c in d["clubs"]:
            for p in c["players"]:
                p["lg_goals"] = 0
                p["lg_apps"] = 0
                p["season_gain"] = 0
                p["season_start_rating"] = clubs_mod.overall(p)
                p.setdefault("homegrown", True)
            registration.auto_register(c)
            c["lineup"] = clubs_mod.best_lineup(c)
        d["done_to"] = (cal.parse(career["date"]) - dt.timedelta(days=1)).isoformat()
