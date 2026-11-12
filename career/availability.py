"""
career/availability.py
======================
Who can play: injuries and suspensions.

SUSPENSIONS (Premier League / FA rules)
  - sent off for two yellows ................ 1 match (those two yellows don't
                                               count towards the totals below)
  - straight red (serious foul play) ........ 3 matches
  - 5 yellows by the club's 19th game ....... 1 match
  - 10 yellows by the 32nd game ............. 2 matches
  - 15 yellows .............................. 3 matches
  Yellow counts start again each season; a ban not yet served carries over.

INJURIES (UEFA Elite Club Injury Study, Ekstrand et al.)
  - a club has ~55 injuries a season that keep a player out of training or
    a match: about half in matches (29 per 1000 match hours - the match
    engine decides those, gameplay/substitutions.py) and half in training
    (7.9 per 1000 hours - decided here, day by day between matches)
  - how long: slight (<3 days) 35%, minor (3-7 days) 27%, moderate (8-28
    days) 25%, major (more than 4 weeks) 13%
  - muscle strains (mostly thigh) are the most common, ~19 days on average;
    ankle sprains about two weeks
  Older players get injured a little more often.

Everything happens when a matchday is finished (finish_matchday): that
matchday's cards and injuries are dealt with, served bans come off, and the
training injuries up to the next match are decided - so the other clubs'
teams for the next round are known straight away (they start playing in the
background) and you see the news.
"""

import datetime as dt
import random

from career import calendar as cal
from career import clubs as clubs_mod

# --- Suspensions ---------------------------------------------------------------------
RED_BAN = {"second_yellow": 1, "red": 3}
YELLOW_BANS = ((5, 19, 1), (10, 32, 2), (15, 99, 3))      # (yellows, by game no., matches)

# --- Injuries -----------------------------------------------------------------------------
TRAINING_PER_DAY = 0.0045    # chance per player per day between matches (~26 a club a season)
AGE_RISK = {30: 1.15, 33: 1.3}
# (share, name, days min, days max)
SEVERITY = [
    (0.35, [("Knock", 1, 2), ("Bruised foot", 1, 3), ("Dead leg", 1, 3), ("Tight calf", 2, 3)]),
    (0.27, [("Tight hamstring", 3, 7), ("Twisted ankle", 4, 7), ("Groin strain", 4, 7),
            ("Back spasm", 3, 6), ("Calf tightness", 3, 7)]),
    (0.25, [("Hamstring strain", 10, 28), ("Ankle sprain", 10, 21), ("Calf strain", 10, 24),
            ("Thigh strain", 10, 25), ("Groin strain", 10, 21), ("Knee ligament sprain", 14, 28)]),
    (0.13, [("Torn hamstring", 35, 70), ("Knee ligament damage", 35, 60), ("Broken foot", 50, 85),
            ("Fractured ankle", 60, 100), ("Ruptured ACL", 200, 280)]),
]
NEWS_KEEP = 40


def _age_factor(p):
    return max([f for a, f in AGE_RISK.items() if p.get("Age", 26) >= a], default=1.0)


def roll_injury(rng):
    """(name, days out) for a new injury."""
    x = rng.random()
    for share, kinds in SEVERITY:
        x -= share
        if x <= 0:
            break
    name, lo, hi = rng.choice(kinds)
    # Long injuries: most at the shorter end
    days = round(lo + (hi - lo) * rng.random() ** 1.5)
    return name, days


def injured(p, date):
    inj = p.get("injury")
    return bool(inj) and cal.parse(inj["until"]) > cal.parse(date)


def banned(p):
    return p.get("ban", 0) > 0


def available(p, date):
    return not injured(p, date) and not banned(p)


def unavailable_ids(club, date):
    """Injured, suspended - or not registered (career/registration.py)."""
    from career import registration
    reg = "registered" in club
    vs = club.get("_vs")                     # (today's opponents: a loanee can't play against his parent club)
    return {p["id"] for p in club["players"]
            if not available(p, date) or (reg and not registration.can_play(club, p))
            or p.get("rest_for") == date                       # (you're resting him: career/chats.py)
            or (vs is not None and p.get("loan") and p["loan"]["from"] == vs)}


def status(p, date):
    """Short text for the squad screens, or ''."""
    if banned(p):
        return f"BAN {p['ban']}"
    if injured(p, date):
        days = cal.days_between(date, p["injury"]["until"])
        return f"INJ {days}d" if days < 14 else f"INJ {round(days / 7)}w"
    return ""


def _news(career, date, club_id, text, kind):
    if club_id is not None and club_id >= 100 and "spain" in career:
        career = career["spain"]                         # Spanish clubs' news stays with the Spanish league
    career.setdefault("news", []).append({"date": date, "club": club_id, "text": text, "kind": kind})
    career["news"] = career["news"][-NEWS_KEEP * 5:]


def _injure(career, club, p, date, cause, rng, minute=None):
    name, days = roll_injury(rng)
    until = (cal.parse(date) + dt.timedelta(days=days)).isoformat()
    if p.get("injury") and injured(p, date):
        # Already injured: keep the longer one
        if cal.parse(p["injury"]["until"]) >= cal.parse(until):
            return
    p["injury"] = {"name": name, "since": date, "until": until, "cause": cause}
    length = ("1 day" if days == 1 else f"{days} days") if days < 14 else f"about {round(days / 7)} weeks" if days < 60 else \
        f"about {round(days / 30)} months"
    where = f"in the match ({minute}')" if cause == "match" else "in training"
    _news(career, date, club["id"], f"{p['Name']} ({p['Pos']}) injured {where}: {name.lower()}, out {length}.",
          "injury")


def after_matchday(career, md, results, rng=None):
    """Deal with a finished matchday: bans served, new cards, match injuries,
    then training injuries up to the next match, then fix the teams."""
    rng = rng or random.Random()
    date = career.get("calendar", [None] * md)[md - 1] or career.get("date")
    clubs = career["clubs"]
    # 1. Bans served: everyone banned missed this round
    for c in clubs:
        for p in c["players"]:
            if banned(p):
                p["ban"] -= 1
                if p["ban"] == 0:
                    _news(career, date, c["id"], f"{p['Name']} has served his suspension.", "ban")
    # 2. This round's cards and injuries
    games = md   # every club plays every round: this was their md-th game
    for r in results:
        for a in r.get("players", []):
            cid = r["home"] if a["team"] == 0 else r["away"]
            club = clubs[cid]
            p = clubs_mod.player_by_id(club, a["id"])
            if p is None:
                continue
            red = a.get("red")
            if red:
                kind = red if red in RED_BAN else "red"
                ban = RED_BAN[kind]
                p["ban"] = p.get("ban", 0) + ban
                why = "two yellow cards" if kind == "second_yellow" else "a straight red card"
                _news(career, date, cid, f"{p['Name']} is suspended for {ban} match{'es' if ban > 1 else ''} "
                                         f"after {why}.", "ban")
                yellows = 0 if kind == "second_yellow" else a.get("yellow", 0)
            else:
                yellows = a.get("yellow", 0)
            for _ in range(yellows):
                p["yellows"] = p.get("yellows", 0) + 1
                for n, by, ban in YELLOW_BANS:
                    if p["yellows"] == n and games <= by:
                        p["ban"] = p.get("ban", 0) + ban
                        _news(career, date, cid, f"{p['Name']} has {n} yellow cards: suspended for {ban} "
                                                 f"match{'es' if ban > 1 else ''}.", "ban")
            if a.get("injury"):
                inj = a["injury"]
                if inj.get("knock"):
                    days = rng.randint(1, 3)
                    until = (cal.parse(date) + dt.timedelta(days=days)).isoformat()
                    if not injured(p, date):
                        p["injury"] = {"name": "Knock", "since": date, "until": until, "cause": "match"}
                else:
                    _injure(career, club, p, date, "match", rng, inj.get("minute"))
    # 3. Fitness after the match; then the other clubs train up to their next
    #    match (yours does when you press Continue - career/training.py)
    from career import training, finance, transfers, board, divisions
    other = divisions.after_matchday(career, md, date, rng)    # the other division's round (quick results)
    training.after_match(career, results + other)
    from career import morale, chats
    morale.after_matchday(career, results + other)      # how everyone feels (career/morale.py)
    _after_chats(career)
    board.after_match(career, results)                  # the board's view of your result
    transfers.count_appearances(career, results)         # add-ons
    from career import contracts
    contracts.pay_bonuses(career, results)               # appearance fees, goal / clean-sheet bonuses
    from career import loans
    loans.count_games(career, results + other)           # loanees' games
    from career import crowds
    for r in results:
        home, away = clubs[r["home"]], clubs[r["away"]]
        r["att"] = crowds.home_game(career, home, away, date)      # who came (career/crowds.py)
        finance.home_game(career, home, r["att"])          # gate money
    for c in clubs:
        if career.get("trained_to", {}).get(str(c["id"])) != date:
            finance.daily(career, c, date)                  # (a match on the 1st: the month's money too)
            from career import contracts
            contracts.on_day(career, c, date, rng)
        career.setdefault("trained_to", {})[str(c["id"])] = date
    from career import transfers
    transfers.on_day(career, date, rng)                  # the match day's market, deadlines - and Spain's games
    nxt = career["calendar"][md] if md < len(career.get("calendar", [])) else None
    from career import transfers
    if nxt and not transfers.window_between(date, nxt):
        # Outside a transfer window nothing the other clubs do depends on you:
        # do their days now, so the next round can start in the background
        for c in clubs:
            if c["id"] != career["my_club"]:
                training.run_days(career, c, nxt, rng)
    # 4. Teams for the next match
    if nxt:
        fix_lineups(career, nxt)


def fix_lineups(career, date):
    """Nobody injured or suspended in a starting XI: AI clubs pick their best
    available team; for you, your assistant puts the best available man in
    each gap (and tells you)."""
    opp = {}
    if date in (career.get("calendar") or []):
        md = career["calendar"].index(date)
        if md < len(career.get("fixtures", [])):
            for h, a in career["fixtures"][md]:
                opp[h], opp[a] = a, h
    for c in career["clubs"]:
        c["_vs"] = opp.get(c["id"])
        out = unavailable_ids(c, date)
        if c["id"] != career["my_club"]:
            from career import training
            c["lineup"] = training.best_lineup_fit(c, date, exclude=out)
            continue
        if not clubs_mod.lineup_ok(c):                  # (someone's left: fill the gap)
            from career import shapes
            shapes.remap(c, clubs_mod.formation_of(c))
        lineup = c["lineup"]
        for slot, pid in list(lineup.items()):
            if pid in out:
                used = set(lineup.values())
                cands = [p for p in c["players"] if p["id"] not in used and p["id"] not in out]
                if not cands:
                    continue
                best = max(cands, key=lambda p: clubs_mod.overall(p, slot))
                gone = clubs_mod.player_by_id(c, pid)
                lineup[slot] = best["id"]
                _news(career, date, c["id"], f"Assistant: {best['Name']} comes in at {slot} for "
                                             f"{gone['Name']} ({status(gone, date)}). Change it on Tactics.",
                      "team")


def new_season(career):
    """Yellow card counts start again (bans carry over)."""
    for c in career["clubs"]:
        for p in c["players"]:
            p["yellows"] = 0


def club_news(career, club_id, n=6):
    return [x for x in career.get("news", []) if x["club"] == club_id][-n:][::-1]


def _after_chats(career):
    """Rests done with; promises falling due (career/chats.py) - news in your inbox."""
    from career import chats, transfers
    me = career["clubs"][career["my_club"]]
    from career import captains
    captains.tidy(me)
    for p in me["players"]:
        if p.get("rest_for") and p["rest_for"] <= career["date"]:
            p.pop("rest_for", None)
    import random
    chats.unhappy_requests(career, random.Random(f"{career['date']}:{career['my_club']}"))
    from career import assistant
    assistant.weekly(career)                                  # your assistant's weekly report
    for p, word in chats.after_matchday(career):
        if word == "kept":
            text = f"{p['Name']} is pleased: you promised him more games and kept your word."
        else:
            text = (f"{p['Name']} is angry: you promised him more games five weeks ago and he hasn't had them. "
                    f"His morale has taken a big hit.")
        mid = transfers._message(career, "news", text)
        for m in transfers.inbox(career):
            if m["id"] == mid:
                m["state"] = "info"
