"""
career/morale.py
================
How each player feels.

MORALE runs from 0 to 100 (p["morale"]); you see it as a word, like the
coaching staff's read of the dressing room:
    Superb 80+   Good 65+   OK 45+   Low 30+   Very low

WHAT MOVES IT (after every matchday, for every club in the league):
  - RESULTS: winning lifts everybody, losing drags everybody down - most of
    all the men who played.
  - GOALS: a scorer's day.
  - PLAYING TIME against what he expects (his squad status - promised in his
    contract, or where he'd fit in the squad): a key player on the bench gets
    frustrated, a squad man getting games is delighted.
  - and it drifts back towards his normal level - a little higher for a
    professional.

PERSONALITY (hidden - p["traits"]): professionalism (1-20: steadier, takes
setbacks better) and temperament (1-20: high = volatile, feels everything
more).  Set once per player from a few of his attributes plus chance.

Why he feels as he does is kept (p["morale_why"]): your assistant mentions
it when it's strong, otherwise you find out by talking to him (later step).

IN MATCHES (step 2): his mood shows in how hard he works and how calm he
is on the ball - not in his pace (morale doesn't make anyone quicker; it
makes him more or less willing to go flat out, which is Work Rate):
    Work Rate  up to +/-12  (1-100 scale; = +/-2.4 on the 1-20 you see)
    Composure  up to +/-9
    Decisions  up to +/-6
Full effect at Superb (95) / very low (25); none at a normal 60.
"""

import random

LABELS = ((80, "Superb"), (65, "Good"), (45, "OK"), (30, "Low"), (0, "Very low"))
START = 60.0
NORMAL = 58.0              # where it drifts back to (+ professionalism)
PRO_NORMAL = 0.6           # normal level: + this per point of professionalism above 10
DRIFT = 0.06               # each matchday: this share of the way back to normal
WIN, DRAW, LOSS = 1.9, -0.3, -2.3
SURPRISE = 1.2             # + per point more than the match was expected to bring (a draw away at the champions...)
DIDNT_PLAY = 0.5           # result effect on men who didn't play
GOAL = 2.0                 # per goal (up to 2 counted)
# share of minutes he expects, by squad status (career/contracts.py)
EXPECT = {"Key player": 0.85, "First team": 0.65, "Rotation": 0.40, "Backup": 0.18, "Prospect": 0.08}
MINUTES_SLACK = 0.12       # within this of what he expects: no complaint
MINUTES_HURT = 7.0         # morale per matchday for each full 100% short of expectation
MINUTES_JOY = 3.0          # ...and for playing more than he expected
WHY_MEMORY = 0.25          # the reasons: how fast they move (share of the newest matchday)


MATCH_EFFECT = {"Work Rate": 12.0, "Composure": 9.0, "Decisions": 6.0}
MATCH_NORMAL = 60.0
MATCH_FULL = 35.0          # this far from normal: the full effect


def match_adjust(p):
    """{attribute: points to add} for a match (career/clubs.py writes them into the team sheet)."""
    m = max(-1.0, min(1.0, (level(p) - MATCH_NORMAL) / MATCH_FULL))
    return {k: round(v * m, 1) for k, v in MATCH_EFFECT.items()}


def traits(p):
    """His hidden personality (made the first time it's needed)."""
    t = p.get("traits")
    if t:
        return t
    rng = random.Random(f"traits:{p['id']}:{p['Name']}")
    wr, tw, comp = (float(p.get(k, 50)) / 5.0 for k in ("Work Rate", "Teamwork", "Composure"))   # (1-100 -> 1-20)
    prof = 0.35 * (wr + tw) / 2 + 0.65 * rng.gauss(10.5, 3.5)
    temp = 0.3 * (20 - comp) + 0.7 * rng.gauss(10, 4)
    p["traits"] = t = {"prof": int(max(1, min(20, round(prof)))), "temp": int(max(1, min(20, round(temp))))}
    return t


def level(p):
    return p.get("morale", START)


def label(p):
    m = level(p)
    return next(name for cut, name in LABELS if m >= cut)


def colour_key(p):
    """good / ok / bad - for the screens."""
    m = level(p)
    return "good" if m >= 65 else "ok" if m >= 45 else "bad"


def _feel(p):
    """How strongly he feels things: temperament up, professionalism down."""
    t = traits(p)
    return 1.0 + 0.04 * (t["temp"] - 10) - 0.02 * (t["prof"] - 10)


def expected_share(club, p):
    from career import contracts
    status = p.get("status") or contracts.expected_status(club, p)
    return EXPECT.get(status, 0.4), status


def after_matchday(career, results):
    """Everyone's morale after a matchday (league clubs)."""
    played, goals, outcome = {}, {}, {}
    for r in results:
        h, a = r["home"], r["away"]
        outcome[h] = "W" if r["hg"] > r["ag"] else "D" if r["hg"] == r["ag"] else "L"
        outcome[a] = "W" if r["ag"] > r["hg"] else "D" if r["hg"] == r["ag"] else "L"
        for x in r.get("players", []):
            cid = h if x["team"] == 0 else a
            if x.get("minutes", 0) > 0:
                played[(cid, x["id"])] = x["minutes"]
        for g in r.get("goals", []):
            gid = g.get("pid")
            if gid is not None and not g.get("own_goal"):
                cid = h if g.get("team", 0) == 0 else a
                goals[(cid, gid)] = goals.get((cid, gid), 0) + 1
    opp = {}
    for r in results:
        opp[r["home"]], opp[r["away"]] = r["away"], r["home"]
    strength = {c["id"]: _strength(c) for c in career["clubs"] if c["id"] in outcome}
    for c in career["clubs"]:
        res = outcome.get(c["id"])
        if res is None:
            continue
        diff = strength[c["id"]] - strength.get(opp[c["id"]], strength[c["id"]])
        expected = max(0.3, min(2.6, 1.35 + 0.12 * diff))         # points a team like this would expect
        surprise = {"W": 3, "D": 1, "L": 0}[res] - expected
        from career import captains
        leader = captains.leader_on_pitch(c, {pid for (cid, pid) in played if cid == c["id"]})
        lead = captains.leadership(leader) if leader is not None else 10.0
        for p in c["players"]:
            if p.get("loan", {}).get("to") not in (None, c["id"]):
                continue
            _update(c, p, res, surprise, played.get((c["id"], p["id"]), 0), goals.get((c["id"], p["id"]), 0), lead)


def _strength(club):
    from career import clubs as clubs_mod
    rs = [clubs_mod.overall(q, s) for s, pid in (club.get("lineup") or {}).items()
          for q in [clubs_mod.player_by_id(club, pid)] if q]
    return sum(rs) / len(rs) if rs else 60.0


def _update(club, p, res, surprise, minutes, goals, lead=10.0):
    t = traits(p)
    feel = _feel(p)
    why = p.setdefault("morale_why", {})
    # results
    base = {"W": WIN, "D": DRAW, "L": LOSS}[res] + SURPRISE * surprise
    d_res = base * (1.0 if minutes else DIDNT_PLAY)
    if d_res < 0:                                     # a good captain out there softens a bad day (career/captains.py)
        from career import captains
        d_res *= max(0.6, 1 - captains.STEADY * (lead - 10))
    # goals
    d_goal = GOAL * min(2, goals)
    # playing time against what he expects (his recent minutes - career/training.py)
    want, status = expected_share(club, p)
    share = min(1.0, p.get("mins_avg", 45) / 90.0)
    gap = share - want
    if p.get("injury") or p.get("ban"):
        d_min = 0.0                                   # (he knows why he's not playing)
    elif p.get("listed"):
        d_min = 0.0                                   # (he's on his way: games here matter less to him)
    elif gap < -MINUTES_SLACK:
        d_min = MINUTES_HURT * (gap + MINUTES_SLACK)
    elif gap > MINUTES_SLACK:
        d_min = MINUTES_JOY * min(0.5, gap - MINUTES_SLACK)
    else:
        d_min = 0.0
    d = (d_res + d_goal + d_min) * feel
    m = level(p) + d
    from career import captains
    normal = NORMAL + PRO_NORMAL * (t["prof"] - 10) + captains.LIFT * (lead - 10)
    m += (normal - m) * DRIFT
    p["morale"] = round(max(3.0, min(98.0, m)), 1)
    for k, v in (("results", d_res), ("goals", d_goal), ("minutes", d_min)):
        why[k] = round((1 - WHY_MEMORY) * why.get(k, 0.0) + WHY_MEMORY * v * feel, 2)
    for k in ("talk", "promise", "captaincy"):        # (your chats with him fade too - career/chats.py)
        if k in why:
            why[k] = round(why[k] * (1 - WHY_MEMORY), 2)
    why["status"] = status


def reason(p):
    """(what's on his mind, how strongly: + good / - bad) - the biggest thing."""
    why = p.get("morale_why") or {}
    parts = {k: why.get(k, 0.0) for k in ("results", "goals", "minutes", "talk", "promise", "captaincy")}
    if not parts:
        return None, 0.0
    k = max(parts, key=lambda k: abs(parts[k]))
    v = parts[k]
    if abs(v) < 0.6:
        return None, 0.0
    status = why.get("status", "")
    text = {
        ("results", True): "enjoying the team's results",
        ("results", False): "down about the team's results",
        ("goals", True): "buzzing after his goals",
        ("minutes", True): "delighted to be getting games",
        ("minutes", False): f"frustrated at his lack of minutes - he sees himself as {_a(status)}",
        ("talk", True): "pleased with how you've handled him",
        ("talk", False): "unhappy about how you've spoken to him",
        ("promise", True): "pleased you kept your word",
        ("promise", False): "angry that you broke your promise",
        ("captaincy", True): "proud to wear the armband",
        ("captaincy", False): "hurt that you took the armband off him",
    }.get((k, v > 0))
    return text, v


def assistant_note(p):
    """What your assistant has picked up (only the strong feelings - the rest you'd have to ask him)."""
    text, v = reason(p)
    if text is None or abs(v) < 2.0:
        return None
    return f"{p['Name'].split(' ')[-1]} is {text}."


def _a(status):
    return {"Key player": "a key player", "First team": "a first-team player", "Rotation": "a regular squad player",
            "Backup": "a squad player", "Prospect": "a young player who should be getting chances"}.get(
        status, "a first-team player")
