"""
career/fitness.py
=================
Fitness and match sharpness (hidden - your assistant tells you about them).

FITNESS (p["fitness"], 0-1): his base fitness - the engine.  Everybody comes
back from the summer holiday short of it (65-90%: professionals keep in
shape, older legs lose more).  Training builds it back - hard training
fastest - and so do minutes on the pitch.  A long injury knocks it down.
  -> it caps how fresh he can be: his match-day CONDITION never gets above
     CAP_BASE + (1 - CAP_BASE) x fitness, so an unfit man starts matches with
     less in the tank and tires early
  -> unfit men get injured more in training

SHARPNESS (p["sharp"], 0-1): match rhythm.  Only playing builds it
(friendlies count).  Training alone only keeps him half-sharp (TRAIN_SHARP):
above that it fades a little every day without a game; a man out injured
fades further.  Benchwarmers and men back from injury go rusty.
  -> in matches, low sharpness takes a little off his decisions, anticipation,
     composure and first touch (SHARP_EFFECT at none at all; nothing at
     SHARP_OK or better)

AI clubs play their pre-season friendlies off-screen (ai_preseason).

Real-world: a summer break of 3-6 weeks costs a good deal of aerobic fitness
(detraining - Mujika & Padilla 2000), and clubs use a 5-6 week pre-season
of training and friendlies to get it back.
"""

import random

from career import calendar as cal

CAP_BASE = 0.55                 # condition cap at zero fitness (1.0 at full fitness)
GAIN = {"light": 0.004, "normal": 0.007, "hard": 0.011}   # fitness per training day
MATCH_FITNESS = 0.03            # per 90 minutes played
INJURED_LOSS = 0.006            # per day out injured
FIT_FLOOR = 0.55
SHARP_PER_90 = 0.20             # sharpness per 90 minutes played (~5 full games: rusty -> sharp)
SHARP_DECAY = 0.008             # per day without a game, down to TRAIN_SHARP (...x2 injured, to the floor)
TRAIN_SHARP = 0.50              # training alone keeps (or brings) him this sharp - no further
TRAIN_SHARP_GAIN = 0.004        # per training day while below it
SHARP_FLOOR = 0.15
SHARP_OK = 0.85                 # this sharp or better: no effect in matches
SHARP_EFFECT = {"Decisions": -6.0, "Anticipation": -5.0, "Composure": -5.0, "Control": -4.0}   # (1-100 scale) at 0
UNFIT_INJURY = 1.5              # training injuries x (1 + this x how far below full fitness)
HOLIDAY = (0.80, 0.06)          # fitness back from holiday: mean, spread (then character / age)
HOLIDAY_SHARP = (0.45, 0.08)
AI_FRIENDLY_EVERY = 5           # AI clubs: a pre-season friendly every few days (off-screen)...
AI_FRIENDLY_FROM = "07-10"       # ...from about ten days into pre-season


def fitness(p):
    return p.get("fitness", 1.0)


def sharp(p):
    return p.get("sharp", 0.9)


def cap(p):
    """The highest his match-day condition can be."""
    return CAP_BASE + (1 - CAP_BASE) * fitness(p)


def match_adjust(p):
    """{attribute: points} for a match (career/clubs.py adds it to morale's)."""
    s = sharp(p)
    if s >= SHARP_OK:
        return {}
    k = (SHARP_OK - s) / SHARP_OK
    return {a: round(v * k, 1) for a, v in SHARP_EFFECT.items()}


def injury_factor(p):
    return 1.0 + UNFIT_INJURY * max(0.0, 1.0 - fitness(p))


# ---------------------------------------------------------------------------
# Day by day (career/training.py) and after games
# ---------------------------------------------------------------------------
def train_day(p, intensity, injured):
    if injured:
        p["fitness"] = round(max(FIT_FLOOR, fitness(p) - INJURED_LOSS), 3)
        p["sharp"] = round(max(SHARP_FLOOR, sharp(p) - 2 * SHARP_DECAY), 3)
    else:
        p["fitness"] = round(min(1.0, fitness(p) + GAIN.get(intensity, GAIN["normal"])), 3)
        s = sharp(p)
        s = max(TRAIN_SHARP, s - SHARP_DECAY) if s > TRAIN_SHARP else min(TRAIN_SHARP, s + TRAIN_SHARP_GAIN)
        p["sharp"] = round(s, 3)
    p["condition"] = round(min(p.get("condition", 1.0), cap(p)), 3)


def played(p, minutes):
    """Minutes on the pitch (league or friendly)."""
    if minutes <= 0:
        return
    k = min(1.2, minutes / 90.0)
    p["sharp"] = round(min(1.0, sharp(p) + SHARP_PER_90 * k + SHARP_DECAY), 3)   # (+ the day's decay back)
    p["fitness"] = round(min(1.0, fitness(p) + MATCH_FITNESS * k), 3)


def holiday(career, rng=None):
    """The summer: everyone back short of fitness and sharpness."""
    from career import morale
    rng = rng or random.Random(f"holiday:{career.get('year')}")
    for c in career["clubs"]:
        for p in c["players"]:
            prof = morale.traits(p)["prof"]
            age = int(p.get("Age", 25))
            f = rng.gauss(*HOLIDAY) + 0.008 * (prof - 10) - 0.012 * max(0, age - 29)
            p["fitness"] = round(max(0.62, min(0.92, f)), 3)
            p["sharp"] = round(max(0.25, min(0.65, rng.gauss(*HOLIDAY_SHARP))), 3)
            p["condition"] = round(min(p.get("condition", 1.0), cap(p)), 3)


def ai_preseason(career, club, iso):
    """AI clubs in pre-season: friendlies off-screen every few days (minutes for the squad's best 20)."""
    first = (career.get("calendar") or [None])[0]
    if not first or iso >= first or iso < f"{iso[:4]}-{AI_FRIENDLY_FROM}":
        return
    if cal.parse(iso).toordinal() % AI_FRIENDLY_EVERY:
        return
    from career import clubs as clubs_mod
    best = sorted(club["players"], key=lambda q: -clubs_mod.overall(q))[:20]
    for i, p in enumerate(best):
        played(p, 60 if i < 11 else 45)


# ---------------------------------------------------------------------------
# What your assistant says (hidden numbers)
# ---------------------------------------------------------------------------
def fitness_word(p):
    f = fitness(p)
    return (None if f >= 0.95 else "nearly fully fit" if f >= 0.87 else "short of fitness" if f >= 0.77
            else "well short of fitness")


def sharp_word(p):
    s = sharp(p)
    return (None if s >= 0.8 else "lacking a bit of sharpness" if s >= 0.6 else "rusty - he needs minutes"
            if s >= 0.4 else "very rusty")


def assistant_view(p):
    """One line, or None if he's ready."""
    f, s = fitness_word(p), sharp_word(p)
    if not f and not s:
        return None
    bits = [b for b in (f, s) if b]
    line = " and ".join(bits)
    return line[0].upper() + line[1:] + "."


def squad_note(club, ids):
    """Your assistant on the men in `ids` (the XI): who isn't ready."""
    from career import clubs as clubs_mod
    unfit, rusty = [], []
    for pid in ids:
        p = clubs_mod.player_by_id(club, pid)
        if p is None:
            continue
        if fitness(p) < 0.87:
            unfit.append(p["Name"].split(" ")[-1])
        elif sharp(p) < 0.6:
            rusty.append(p["Name"].split(" ")[-1])
    out = []
    if unfit:
        out.append(f"{', '.join(unfit[:4])}{' and others' if len(unfit) > 4 else ''} still short of fitness")
    if rusty:
        out.append(f"{', '.join(rusty[:4])}{' and others' if len(rusty) > 4 else ''} lacking sharpness")
    return ("; ".join(out) + ".") if out else None
