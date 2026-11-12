"""
career/teamtalk.py
==================
Team talks: before kick-off and at full time.

You pick what to say to the whole squad; every man takes it his own way -
his character (professionalism, temperament: hidden), his nerve (Composure),
his age - and it depends on the situation: are we favourites or underdogs,
and (at full time) how did it go against what we expected?

  - "I expect a win" lifts professionals when we're favourites - and puts
    nervous lads under pressure when we're not.
  - "Nobody gives us a chance" fires up underdogs - favourites don't buy it.
  - "Go out and enjoy it" settles the nervous - and makes the lazy complacent
    when we should win.
  - "Not good enough!" after a bad defeat stings a professional into action
    and makes a hot-head sulk; after a win it baffles everyone.
  - and the same speech every week wears thin.

Effects are small (a couple of points of morale for most, a few at most - a
team talk can tip a man, not transform him): morale feeds into how hard he
works and how calm he is in the match (career/morale.py).

    context(career, club, phase, result=None) -> situation
    options(ctx)                                -> [(key, what you say)]
    give(career, club, ctx, key)                -> [(player, change, reaction)]
"""

import random

from career import morale, clubs as clubs_mod

PRE = [
    ("focus", "Stay focused - do your jobs and we'll be fine."),
    ("expect", "I expect a win today. Nothing less."),
    ("enjoy", "No pressure. Go out there and enjoy it."),
    ("prove", "Nobody gives us a chance. Prove them wrong."),
    ("passion", "I want passion! Win every tackle, every header."),
    ("captain", "Say nothing - let the captain do the talking."),
]
HALF = [
    ("keep", "Keep doing what you're doing."),
    ("tight", "Keep it tight - no silly mistakes."),
    ("believe", "We can turn this round. I believe in you."),
    ("demand", "That's not good enough. I want more!"),
    ("complacent", "Don't you dare get complacent - it's not over."),
    ("nothing", "Say nothing. Let them get a drink."),
]
STATES = {"up2": 2, "up1": 1, "level": 0, "down1": -1, "down2": -2}   # the score at half-time, for us
POST = [
    ("proud", "Brilliant. I'm proud of every one of you."),
    ("more", "Well done - but there's more in this team."),
    ("unlucky", "Unlucky, lads. Heads up - we go again."),
    ("notgood", "That was not good enough. Not good enough!"),
    ("nothing", "Say nothing. Let them get changed."),
]
MAX_CHANGE = 4.0             # morale, either way, for one talk
UNUSED = 0.5                 # men who didn't get on the pitch: half the effect (full time)
WEARS_THIN = 0.5             # the same pre-match talk as either of the last two: x this
NOISE = 0.4


def _expected(career, club, opp_id, home):
    """Points a team like ours would expect from this game (0-3)."""
    opp = career["clubs"][opp_id]
    diff = morale._strength(club) - morale._strength(opp) + (1.0 if home else -1.0)
    return max(0.3, min(2.6, 1.35 + 0.12 * diff))


def context(career, club, phase, result=None):
    """phase "pre" (next fixture) or "post" (result: your match's result)."""
    from career import league
    if phase == "pre":
        md, h, a = league.next_fixture(career)
    else:
        md, h, a = career["matchday"], result["home"], result["away"]
    home = h == club["id"]
    opp = a if home else h
    exp = _expected(career, club, opp, home)
    ctx = {"phase": phase, "md": md, "home": home, "opp": opp, "opp_name": career["clubs"][opp]["name"],
           "expected": exp, "fav": exp >= 1.75, "under": exp <= 1.0}
    played = len(career.get("results", {})) > 0
    pos_me, pos_opp = (league.position_of(career, club["id"]), league.position_of(career, opp)) if played else (None, None)
    ctx["pos"] = (pos_me, pos_opp)
    if phase == "post":
        gf, ga = (result["hg"], result["ag"]) if home else (result["ag"], result["hg"])
        res = "W" if gf > ga else "D" if gf == ga else "L"
        ctx.update(gf=gf, ga=ga, res=res, margin=gf - ga, surprise={"W": 3, "D": 1, "L": 0}[res] - exp,
                   played={x["id"] for x in result.get("players", []) if x.get("minutes", 0) > 0
                           and (x["team"] == 0) == home})
    ctx["last_res"] = _last_result(career, club)
    return ctx


def _last_result(career, club):
    for day in reversed(list(career.get("results", {}).values())):
        for m in day:
            if club["id"] in (m["home"], m["away"]):
                gf, ga = (m["hg"], m["ag"]) if m["home"] == club["id"] else (m["ag"], m["hg"])
                return "W" if gf > ga else "D" if gf == ga else "L"
    return None


def situation(ctx):
    """The assistant's one-line read of it (so you can choose)."""
    pos_me, pos_opp = ctx["pos"]
    where = "at home" if ctx["home"] else "away"
    table = f" ({_ord(pos_me)} v {_ord(pos_opp)})" if pos_me else ""
    if ctx["phase"] == "pre":
        lean = "We're favourites" if ctx["fav"] else "We're the underdogs" if ctx["under"] else "It's an even game"
        return f"{lean} today - {ctx['opp_name']} {where}{table}."
    word = {"W": "We won", "D": "We drew", "L": "We lost"}[ctx["res"]]
    s = ctx["surprise"]
    verdict = ("- better than anyone expected." if s >= 1.0 else
               "- about what we'd expect." if s > -0.8 else
               "- we should have done better.")
    return f"{word} {ctx['gf']}-{ctx['ga']} {where} against {ctx['opp_name']} {verdict}"


def _ord(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def options(career, club, ctx):
    """[(key, words, allowed, why not)]"""
    out = []
    for key, words in (PRE if ctx["phase"] == "pre" else POST):
        ok, why = True, ""
        if key == "captain":
            cap = _speaker(career, club)
            if cap is None:
                ok, why = False, "Neither your captain nor vice is in the squad."
        out.append((key, words, ok, why))
    return out


def squad(career, club, ctx):
    """Who's in the dressing room: the XI and the bench."""
    from career import league, availability as avail
    date = league.match_date(career) or career.get("date")
    out = avail.unavailable_ids(club, date) if (date and ctx["phase"] == "pre") else set()
    ids = [i for i in (club.get("lineup") or {}).values() if i not in out]
    for b in clubs_mod.bench(club, out):
        if b["id"] not in ids:
            ids.append(b["id"])
    if ctx["phase"] == "post":
        for pid in ctx.get("played", ()):
            if pid not in ids:
                ids.append(pid)
    return [p for p in (clubs_mod.player_by_id(club, i) for i in ids) if p is not None]


def _speaker(career, club):
    """The captain (or vice) if he's in the squad."""
    from career import captains
    ctx_ids = {p["id"] for p in club["players"]}
    xi = set((club.get("lineup") or {}).values())
    for p in captains.armband(club):
        if p is not None and p["id"] in xi and p["id"] in ctx_ids:
            return p
    return None


def _nerve(p):
    return float(p.get("Composure", 50)) / 5.0       # 1-20


def _react(career, club, ctx, key, p):
    """(change before scaling, word for a bad reaction or None)."""
    from career import captains
    t = morale.traits(p)
    prof, temp, nerve = t["prof"], t["temp"], _nerve(p)
    young = int(p.get("Age", 25)) <= 21
    nervous = nerve < 10 or young
    fav, under = ctx["fav"], ctx["under"]
    if ctx["phase"] == "pre":
        if key == "focus":
            return 0.7 + 0.05 * (prof - 10), None
        if key == "expect":
            if fav:
                return 1.4 + 0.08 * (prof - 10), None
            if nervous:
                return (-1.4 if under else -0.6), "Feels the pressure"
            return (0.2 if under else 0.9), None
        if key == "enjoy":
            if fav and prof <= 9:
                return -0.8, "Complacent"
            d = 1.6 if under else 0.8 if not fav else 0.3
            return d + (0.8 if nervous else 0.0), None
        if key == "prove":
            if fav:
                return -0.4, "Not convinced"
            return (2.0 if under else 0.6) + 0.06 * (temp - 10), None
        if key == "passion":
            bonus = 0.5 if ctx["last_res"] == "L" else 0.0
            if temp >= 13:
                return 1.9 + bonus, None
            if temp <= 7:
                return -0.3, "Unmoved"
            return 0.8 + bonus, None
        if key == "captain":
            cap = _speaker(career, club)
            if cap is None:
                return 0.0, None
            lead = captains.leadership(cap)
            d = 0.2 * (lead - 10) + 0.15
            if cap is p:
                return 0.6, None                     # (he likes being trusted with it)
            return d, ("Not listening" if d < -0.3 else None)
    # full time
    res, s, margin = ctx["res"], ctx["surprise"], ctx["margin"]
    if key == "proud":
        if res == "W":
            return 2.0, None
        if res == "D":
            if s < 0 and prof >= 13:
                return -0.5, "Not satisfied"
            return (1.5 if s > 0 else 0.4), None
        if s < -1.0 and prof >= 12:
            return -1.0, "Knows it wasn't good enough"
        return (0.9 if s > -1.0 else 0.3), None
    if key == "more":
        if res == "W":
            return (1.5 if prof >= 12 else -0.3 if prof <= 7 else 0.9), ("Wanted praise" if prof <= 7 else None)
        return (0.5 if res == "D" else -0.5), (None if res == "D" else "Confused")
    if key == "unlucky":
        if res == "L":
            if margin <= -3 and prof >= 12:
                return -1.0, "Knows that's not true"
            return (1.5 if margin >= -1 or s > -1.2 else 0.5), None
        return (0.8 if res == "D" else 0.3), None
    if key == "notgood":
        if res == "W":
            return -2.5, "Baffled"
        if s > 0.3:                                  # a decent result for us: harsh
            return -1.5, "Feels it's unfair"
        if prof >= 12 and temp < 13:
            return 1.6, None
        if temp >= 13:
            return -2.0, "Angry"
        return -0.5, "Hurt"
    if key == "nothing":
        if res == "W" and s > 0.5:
            return -0.5, "Expected a word"
        return 0.0, None
    return 0.0, None


def give(career, club, ctx, key):
    """The talk.  Returns [(player, morale change, reaction word)] and moves their morale."""
    rng = random.Random(f"talk:{career.get('date')}:{ctx['phase']}:{key}")
    talks = club.setdefault("talks", {})
    recent = talks.get(ctx["phase"] + "_recent", [])
    thin = key in recent[-2:] and key not in ("nothing", "focus")
    out = []
    for p in squad(career, club, ctx):
        d, bad = _react(career, club, ctx, key, p)
        if thin and d > 0:
            d *= WEARS_THIN
        if ctx["phase"] == "post" and p["id"] not in ctx.get("played", ()):
            d *= UNUSED
        d += rng.gauss(0, NOISE)
        if d < 0:
            d *= morale._feel(p)
        d = round(max(-MAX_CHANGE, min(MAX_CHANGE, d)), 1)
        p["morale"] = round(max(3.0, min(98.0, morale.level(p) + d)), 1)
        why = p.setdefault("morale_why", {})
        why["talk"] = round(why.get("talk", 0.0) + 0.5 * d, 2)
        word = (bad if (bad and d <= -0.6) else
                "Fired up" if d >= 2.0 else
                ("Pleased" if ctx["phase"] == "post" else "Motivated") if d >= 0.8 else
                "No change" if d > -0.6 else (bad or "Unhappy"))
        out.append((p, d, word))
    talks[ctx["phase"] + "_recent"] = (recent + [key])[-3:]
    talks[ctx["phase"]] = ctx["md"]
    talks["last"] = {"phase": ctx["phase"], "md": ctx["md"], "key": key, "thin": thin,
                     "reactions": [(p["id"], d, w) for p, d, w in out]}
    return out


def done(career, club, phase):
    """Already given this matchday's talk?"""
    md = career["matchday"]
    return (club.get("talks") or {}).get(phase) == md


def summary(out, thin=False):
    """The assistant's read of the room afterwards."""
    if not out:
        return "Nobody to talk to."
    good = [p for p, d, w in out if d >= 0.8]
    bad = sorted((x for x in out if x[1] <= -0.6), key=lambda x: x[1])
    share = len(good) / len(out)
    head = ("That went down well - the lads are up for it." if share >= 0.6 else
            "A mixed reaction." if share >= 0.3 else
            "That didn't really land.")
    if thin:
        head += " They've heard that one before, mind."
    if bad:
        sn = [q["Name"].split(" ")[-1] for q, _, _ in out]
        names = ", ".join((f"{p['Name'][0]}. " if sn.count(p["Name"].split(" ")[-1]) > 1 else "") + p["Name"].split(" ")[-1]
                          for p, d, w in bad[:3])
        head += f" {names} didn't take it well."
    return head



# ---------------------------------------------------------------------------
# HALF-TIME (the match engine plays it: rendering/ht_panel.py)
# ---------------------------------------------------------------------------
# The engine knows nothing about a player's character, so before kick-off we
# work out how each man would take each talk at each half-time score, and
# hand the table over with the team sheet (career/matches.py).  At the break
# you pick (or your assistant does, in a match you don't watch); in the
# second half a man's Work Rate / Composure / Decisions move with how he took
# it, and after the match his morale does too (after_match below).
HT_EFFECT = {"Work Rate": 0.30, "Composure": 0.20, "Decisions": 0.10}   # 1-20 scale, per point of reaction


def _react_half(ctx, key, p, margin):
    t = morale.traits(p)
    prof, temp, nerve = t["prof"], t["temp"], _nerve(p)
    young = int(p.get("Age", 25)) <= 21
    nervous = nerve < 10 or young
    ahead, behind = margin > 0, margin < 0
    if key == "keep":
        if ahead:
            return 1.2, None
        if behind:
            return (-0.6, "Knows we need more") if prof >= 12 else (0.2, None)
        return (0.6 if not ctx["fav"] else 0.2), None
    if key == "tight":
        if ahead:
            return 0.9 + (0.6 if nervous else 0.0), None
        if behind:
            return (-0.5, "Wants to go for it") if temp >= 12 else (0.0, None)
        return (0.7 if ctx["under"] else 0.4), None
    if key == "believe":
        if behind:
            return 1.4 + (0.4 if ctx["under"] else 0.0) + (0.3 if margin == -1 else 0.0), None
        return (0.8 if margin == 0 else 0.3), None
    if key == "demand":
        if ahead:
            return -1.6, "Baffled"
        if nervous and behind:
            return -1.0, "Rattled"
        if prof >= 12 and temp < 13:
            return (1.7 if behind else 1.1 if ctx["fav"] else 0.4), None
        if temp >= 13:
            return (0.9, None) if behind else (-0.8, "Annoyed")
        return (0.3 if behind else -0.3), None
    if key == "complacent":
        if ahead:
            return (1.3 if prof >= 11 else 0.7), None
        return -0.4, "Confused"
    return 0.0, None                                        # "nothing"


def half_table(career, club, home, opp_id):
    """For the team sheet: {"options": [[key, words]], "react": {state: {key: {pid: d}}},
    "pick": {state: key} (your assistant's choice)}."""
    exp = _expected(career, club, opp_id, home)
    ctx = {"phase": "half", "fav": exp >= 1.75, "under": exp <= 1.0}
    date = career.get("date", "")
    people = squad(career, club, {"phase": "pre"})
    talks = club.get("talks") or {}
    recent = talks.get("half_recent", [])
    react, pick = {}, {}
    rng = random.Random(f"ht:{date}:{club['id']}")
    for state, margin in STATES.items():
        react[state] = {}
        for key, _ in HALF:
            row = {}
            for p in people:
                d, _bad = _react_half(ctx, key, p, margin)
                if key in recent[-2:] and key != "nothing" and d > 0:
                    d *= WEARS_THIN
                d += rng.gauss(0, NOISE)
                if d < 0:
                    d *= morale._feel(p)
                row[str(p["id"])] = round(max(-MAX_CHANGE, min(MAX_CHANGE, d)), 1)
            react[state][key] = row
        xi = {str(i) for i in (club.get("lineup") or {}).values()}
        score = sorted(((sum(v for k, v in react[state][key].items() if k in xi), key) for key, _ in HALF), reverse=True)
        pick[state] = score[0][1] if rng.random() < 0.7 or len(score) < 2 else score[1][1]   # (he's good, not perfect)
    return {"options": [list(x) for x in HALF], "react": react, "pick": pick, "effect": HT_EFFECT,
            "bad": {state: {key: {pid: _react_half(ctx, key, p, m)[1] for p in people for pid in [str(p["id"])]}
                            for key, _ in HALF} for state, m in STATES.items()}}


def state_of(margin):
    return "up2" if margin >= 2 else "up1" if margin == 1 else "level" if margin == 0 else \
        "down1" if margin == -1 else "down2"


def word_for(d, bad=None):
    return (bad if (bad and d <= -0.6) else "Fired up" if d >= 2.0 else "Motivated" if d >= 0.8 else
            "No change" if d > -0.6 else (bad or "Unhappy"))


def after_match(career, results):
    """Half-time talks given in this matchday's matches: morale moves (your club, from the result)."""
    me = career["clubs"][career["my_club"]]
    for r in results:
        ht = r.get("ht_talk")
        if not ht or me["id"] not in (r["home"], r["away"]):
            continue
        for pid, d in ht.get("react", {}).items():
            p = clubs_mod.player_by_id(me, int(pid))
            if p is None:
                continue
            p["morale"] = round(max(3.0, min(98.0, morale.level(p) + d)), 1)
            why = p.setdefault("morale_why", {})
            why["talk"] = round(why.get("talk", 0.0) + 0.5 * d, 2)
        talks = me.setdefault("talks", {})
        talks["half_recent"] = (talks.get("half_recent", []) + [ht["key"]])[-3:]
        talks["half_last"] = {"md": career["matchday"], "key": ht["key"], "by": ht.get("by", "you"),
                              "reactions": [(int(pid), d, ht.get("words", {}).get(pid)) for pid, d in ht.get("react", {}).items()]}
