"""
career/training.py
==================
Training, fitness and development - day by day between matches.

Every club has a weekly TRAINING setting (you choose yours on the Training
screen; AI clubs train normally, and lightly in a busy week):
  - FOCUS: balanced, attacking, defending, technical, tactical, physical -
    which attributes improve most
  - INTENSITY: light, normal, hard -
      light:  quicker recovery, fewer injuries, slower development
      hard:   faster development, slower recovery, more injuries
    (sports science: players need ~72 hours to recover from a match, and
    sudden jumps in training load raise injury risk - Gabbett 2016)

CONDITION (fitness, 0-1): a player starts each match at his condition -
that's where his stamina starts in the match engine.  After a match his
condition is what his stamina was at the final whistle (~0.7-0.85 for 90
minutes), and it comes back day by day: full after about four days of
normal training.  Two games in three or four days means tired legs -
rotate.  AI clubs leave out players who aren't fit enough.

DEVELOPMENT: every player has a hidden potential (career/clubs.py).  Young
players close the gap to it - quickly at 17-20, slower into their mid
twenties, hardly at all after 25 - and faster when they play regularly
and train hard.  The focus decides which attributes the improvement goes
to.  (Ageing, decline and retirement come with the next step.)

Each day is done once per club ("trained_to" in the save): the other clubs'
days up to the next match are done as soon as a matchday is finished (so
their teams for the next round are known), yours when you press Continue -
so changing your training during the week counts.
"""

import datetime as dt
import random

from career import calendar as cal
from career import clubs as clubs_mod

FOCUS = {
    "balanced":  ("Balanced", "A bit of everything - development follows each player's position.", []),
    "attacking": ("Attacking", "Finishing, movement and composure in front of goal.",
                  ["Finishing", "Off The Ball", "Composure", "Dribbling", "Long Shots", "Crossing"]),
    "defending": ("Defending", "Tackling, marking, positioning and heading.",
                  ["Tackling", "Marking", "Defensive Positioning", "Heading", "Anticipation"]),
    "technical": ("Technical", "Passing, first touch, dribbling and crossing.",
                  ["Passing", "Control", "Dribbling", "Crossing"]),
    "tactical":  ("Tactical", "Decisions, teamwork, reading the game, work rate.",
                  ["Decisions", "Teamwork", "Anticipation", "Work Rate", "Defensive Positioning"]),
    "physical":  ("Physical", "Strength, stamina and agility (young players' pace too).",
                  ["Stamina", "Strength", "Agility", "Jumping"]),
}
INTENSITY = {
    #           label      recovery/day  development  injuries
    "light":  ("Light",    0.090,        0.75,        0.6),
    "normal": ("Normal",   0.075,        1.00,        1.0),
    "hard":   ("Hard",     0.060,        1.25,        1.5),
}
DEFAULT = {"focus": "balanced", "intensity": "normal"}

# Development: share of the gap to his potential a player closes in a year, by age
GROWTH_PER_YEAR = {16: 0.55, 17: 0.55, 18: 0.55, 19: 0.52, 20: 0.48, 21: 0.42, 22: 0.33, 23: 0.25, 24: 0.17,
                   25: 0.10, 26: 0.06, 27: 0.03}
PLAYING_TIME = (0.7, 1.2)      # development x this with no minutes .. a regular starter
MINUTES_MEMORY = 0.25          # each match counts this much in his recent-minutes average
FOCUS_WEIGHT = 3.0             # attributes in the focus get this weight (others 1, position keys 2)
PHYS_GROWTH_AGE = 23           # strength / stamina / jumping still grow until this age
TIRED_INJURY = 2.0             # training injuries x (1 + this x (1 - condition))
TRAINING_PER_DAY = 0.0045      # base chance of a training injury per player per day (~26 a club a season)
FIT_TO_PLAY = 0.88             # AI clubs rest a player below this condition if they can

# The week around the matches (Jay, 21 Nov).  Recovery is quick at first and slower at the end: each day a player
# gets back this share of what he's missing (his condition - his tiredness - is 1.0 when fully fresh).  Real
# players are still 2-4% down on sprint and jump 72 hours after a match (Silva et al. 2018, Sports Med 48(3),
# doi 10.1007/s40279-017-0798-8), so a man who played 90 on Saturday is nearly - not quite - fresh on Wednesday,
# and one who pressed flat out all game is a bit further off.  The days are planned like a real club's:
#   the day after he played   recovery session          (only the men who played - the rest train normally)
#   two days after            a day off                 (if the next match isn't tomorrow)
#   the day before a match    light session
#   otherwise                 your Light / Normal / Hard training
# Saturday-Wednesday: recovery, off, light - a man finishing on 60% is ~95% on Wednesday, one on 45% ~92%.
# Saturday-Saturday: three proper training days in the middle, and everyone's fresh.
DAY_RECOVERY = {"recovery": 0.45, "off": 0.55, "pre-match": 0.45, "light": 0.40, "normal": 0.33, "hard": 0.25}
DAY_INJURY = {"recovery": 0.4, "off": 0.0, "pre-match": 0.6}     # training-injury risk x this on those days
DAY_LOAD = {"recovery": "light", "off": "light", "pre-match": "light"}   # what it counts as for fitness

NON_PHYSICAL = [c for c in clubs_mod.COLUMNS if c not in clubs_mod.PHYSICAL
                and c not in ("Shot Stopping", "Handling", "Penalties")]


def settings(club):
    return dict(DEFAULT, **club.get("training", {}))


def ai_settings(career, club, date):
    """AI clubs: normal, balanced - light in a week with two games."""
    nxt = _next_match_after(career, date)
    if nxt and cal.days_between(date, nxt) <= 3:
        return {"focus": "balanced", "intensity": "light"}
    return dict(DEFAULT)


def _next_match_after(career, date):
    for d in career.get("calendar", []):
        if cal.parse(d) > cal.parse(date):
            return d
    return None


def condition(p):
    return p.get("condition", 1.0)


def after_match(career, results):
    """Condition after the match = stamina at the final whistle; recent minutes."""
    played = {}
    for r in results:
        for a in r.get("players", []):
            cid = r["home"] if a["team"] == 0 else r["away"]
            played[(cid, a["id"])] = a
    sides = {r["home"] for r in results} | {r["away"] for r in results}
    for c in career["clubs"]:
        if c["id"] not in sides:
            continue                                     # (not their round - the other division's catch-up)
        for p in c["players"]:
            p.setdefault("season_start_rating", clubs_mod.overall(p))     # (older saves)
            a = played.get((c["id"], p["id"]))
            mins = a["minutes"] if a else 0
            p["mins_avg"] = round((1 - MINUTES_MEMORY) * p.get("mins_avg", 45) + MINUTES_MEMORY * mins, 1)
            if mins:
                from career import fitness as fit
                fit.played(p, mins)                      # sharpness and fitness from minutes
            if a and a.get("stamina") is not None and mins > 0:
                p["condition"] = round(min(condition(p), a["stamina"]), 3)
            if mins:
                p["played_on"] = career.get("date")         # (tomorrow is his recovery day)


def run_days(career, club, until, rng=None, news=None):
    """Train this club day by day up to (not including) `until`."""
    rng = rng or random.Random()
    trained = career.setdefault("trained_to", {})
    start = trained.get(str(club["id"])) or career.get("date")
    day = cal.parse(start) + dt.timedelta(days=1)
    end = cal.parse(until)
    while day < end:
        train_day(career, club, day.isoformat(), rng)
        day += dt.timedelta(days=1)
    if str(club["id"]) not in trained:
        trained[str(club["id"])] = start


def run_all(career, until, rng=None, stop=False):
    """Every club, day by day together, up to (not including) `until` - so
    whatever happens between clubs (transfers) happens in date order.
    stop: halt after a day on which something needs you (an offer) - returns that day."""
    rng = rng or random.Random()
    career.pop("stop", None)
    trained = career.setdefault("trained_to", {})
    starts = [cal.parse(trained.get(str(c["id"])) or career.get("date")) for c in career["clubs"]]
    day = min(starts) + dt.timedelta(days=1)
    end = cal.parse(until)
    while day < end:
        iso = day.isoformat()
        for c in career["clubs"]:
            if cal.parse(trained.get(str(c["id"])) or career.get("date")) < day:
                train_day(career, c, iso, rng)
        from career import transfers
        transfers.on_day(career, iso, rng)              # the transfer market (AI clubs, offers...)
        if iso[5:] in ("09-02", "02-03"):               # a window's just shut: AI managers rethink the shape
            from career import shapes
            shapes.ai_review(career)
        if stop and career.pop("stop", None):
            return iso
        day += dt.timedelta(days=1)
    career.pop("stop", None)
    return None


def trained_up_to(career, date, exclude=None):
    """Has every club (but `exclude`) been processed up to the day before `date`?"""
    trained = career.get("trained_to", {})
    limit = cal.parse(date) - dt.timedelta(days=1)
    return all(cal.parse(trained.get(str(c["id"])) or career.get("date")) >= limit for c in career["clubs"]
               if c["id"] != exclude)


def reset_days(career):
    """A new season: nothing done yet - the first day to do is today."""
    before = (cal.parse(career["date"]) - dt.timedelta(days=1)).isoformat()
    career["trained_to"] = {str(c["id"]): before for c in career["clubs"]}


def train_day(career, club, iso, rng):
    """One day for one club: recovery, training injuries, development, money, contracts."""
    from career import availability as av
    trained = career.setdefault("trained_to", {})
    mine = club["id"] == career["my_club"]
    if True:
        s = settings(club) if mine else ai_settings(career, club, iso)
        _, recover, dev_mult, inj_mult = INTENSITY[s["intensity"]]
        focus = FOCUS[s["focus"]][2]
        from career import fitness as fit, staff
        st_rec, st_inj = staff.recovery(career, club), staff.training_injuries(career, club)   # (your staff)
        if not mine:
            fit.ai_preseason(career, club, iso)          # (AI clubs' pre-season friendlies, off-screen)
        for p in club["players"]:
            if av.injured(p, iso):
                p["condition"] = min(1.0, round(condition(p) + recover * 0.5, 3))
                fit.train_day(p, s["intensity"], True)
                continue
            # Recovery (no fresher than his fitness allows - career/fitness.py); your fitness coach helps
            kind = day_kind(career, club, p, iso, s["intensity"])
            share = min(0.9, DAY_RECOVERY[kind] * st_rec)
            p["condition"] = min(1.0, round(condition(p) + (1.0 - condition(p)) * share, 3))
            fit.train_day(p, DAY_LOAD.get(kind, s["intensity"]), False)
            # Injury
            risk = TRAINING_PER_DAY * av._age_factor(p) * inj_mult * (1 + TIRED_INJURY * (1 - condition(p))) \
                * fit.injury_factor(p) * st_inj * DAY_INJURY.get(kind, 1.0)
            if rng.random() < risk:
                av._injure(career, club, p, iso, "training", rng)
                continue
            # Development
            develop(p, dev_mult * staff.development(career, club, p), focus, rng)
        from career import finance, contracts
        finance.daily(career, club, iso)                 # wages, TV money... on the 1st of the month
        if mine and iso.endswith("-01"):
            from career import board
            board.monthly(career, iso)                   # the board looks at the table and the money
            from career import stadium
            stadium.monthly(career, iso)                 # stand rebuilds: pay the builders, open the stand
        contracts.on_day(career, club, iso, rng)         # 1 January: contract talks / AI renewals
        trained[str(club["id"])] = iso


def day_kind(career, club, p, iso, intensity):
    """What today is for him: "recovery", "off", "pre-match" or the club's training intensity (see DAY_RECOVERY)."""
    nxt = days_to_next_match(career, club, iso)
    since = None
    if p.get("played_on"):
        try:
            since = cal.days_between(p["played_on"], iso)
        except Exception:
            since = None
    if since == 1:
        return "recovery"
    if nxt == 1:
        return "pre-match"
    if since == 2 and nxt >= 2:
        return "off"
    return intensity


_NEXT = {}


def days_to_next_match(career, club, iso):
    """Days from `iso` to this club's next match (league, cups, Europe) - 99 if none is known."""
    key = (id(career), club["id"], iso)
    hit = _NEXT.get(key)
    if hit is not None:
        return hit
    if len(_NEXT) > 5000:
        _NEXT.clear()
    best = None
    try:
        from career import league
        for r in range(max(1, career.get("matchday", 1)), len(career.get("calendar") or []) + 1):
            d = league.match_date(career, r, club["id"])
            if d and d > iso:
                best = d
                break
    except Exception:
        best = None
    try:
        from career import cups
        for m in cups.all_matches(career):
            if m.get("result") is None and club["id"] in (m.get("home"), m.get("away")) and m["date"] > iso:
                if best is None or m["date"] < best:
                    best = m["date"]
                break
    except Exception:
        pass
    n = cal.days_between(iso, best) if best else 99
    _NEXT[key] = n
    return n


def develop(p, dev_mult, focus, rng):
    """One day's development."""
    age = p.get("Age", 26)
    rate = GROWTH_PER_YEAR.get(age, 0.0)
    pot = p.get("Potential")
    if rate <= 0 or pot is None:
        return
    level = clubs_mod.overall(p)
    gap = pot - level
    if gap <= 0:
        return
    lo, hi = PLAYING_TIME
    from career import youth                             # (first-team minutes, plus youth games at their weight)
    play = lo + (hi - lo) * min(1.0, youth.effective_minutes(p) / 75.0)
    gain = gap * rate / 365.0 * dev_mult * play          # level points today
    # Spread over the attributes: position keys and the focus get more
    keys = set(clubs_mod.RATING_KEYS[clubs_mod.NATURAL_GROUP[p["Pos"]]])
    attrs = list(NON_PHYSICAL)
    if p["Pos"] == "GK":
        attrs += ["Shot Stopping", "Handling"]
    if age < PHYS_GROWTH_AGE:
        attrs += ["Strength", "Stamina", "Jumping", "Agility"]
    w = {a: (FOCUS_WEIGHT if a in focus else 1.0) * (2.0 if a in keys else 1.0) for a in attrs}
    total = sum(w.values())
    points = gain * len(attrs)                            # level +1 = every attribute +1
    prog = p.setdefault("progress", {})
    for a in attrs:
        prog[a] = prog.get(a, 0.0) + points * w[a] / total
        if prog[a] >= 1.0:
            whole = int(prog[a])
            p[a] = min(clubs_mod.ATTR_MAX, p[a] + whole)
            prog[a] -= whole
            p["season_gain"] = p.get("season_gain", 0) + whole
    for a in list(prog):
        prog[a] = round(prog[a], 4)


TIRED_PENALTY = 80             # AI selection: rating points off per unit of condition below FIT_TO_PLAY + 0.07


def best_lineup_fit(club, date, exclude=()):
    """AI team selection: the best XI, but a tired man loses out to a fresh one who's nearly as good."""
    pen = {p["id"]: TIRED_PENALTY * max(0.0, (FIT_TO_PLAY + 0.07) - condition(p)) for p in club["players"]}
    return clubs_mod.best_lineup(club, exclude=exclude, penalty=pen)


def mark_season_start(career):
    """Remember everyone's rating now (the Training screen shows the change this season)."""
    for c in career["clubs"]:
        for p in c["players"]:
            p["season_start_rating"] = clubs_mod.overall(p)


def new_season(career):
    for c in career["clubs"]:
        for p in c["players"]:
            p["season_gain"] = 0
            p["condition"] = 1.0
    from career import fitness as fit
    fit.holiday(career)                                  # back from the summer short of fitness / sharpness
    reset_days(career)
    mark_season_start(career)
