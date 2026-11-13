"""
career/media.py
===============
The world talks about football: newspapers and social media.

PAPERS (the newspaper on your desk):
    The Daily Roar          - tabloid: puns, capitals, drama
    The National Chronicle  - broadsheet: measured, a bit dry
    <Your town> Evening Post - your local paper: all about your club
Stories come from what happens: match reports, upsets and thrashings,
hat-tricks, title races and relegation scraps, transfers (and rumours in
the window), long injuries, players who want out, pressure on the manager
(you), Spain, and a pre-season preview.

SOCIAL MEDIA (the laptop): your club's account, regular fans (each with a
personality), rival fans, journalists, and your players - happy ones after a
win, unhappy ones with something cryptic (a clue to their morale).

FAN MOOD (0-100): results against what was expected, big signings, selling
favourites; it drifts back towards normal.  A small real effect:
  - each matchday it nudges the board's confidence (BOARD_NUDGE)
  - at home the crowd lifts - or gets at - the players a little (CROWD)

    catch_up(career)            - stories for anything new (call any time)
    after_matchday(career, md, results)
    articles(career), posts(career), mood(career), mood_word(m)
"""

import random

from career import league, calendar as cal, morale

KEEP_ARTICLES = 160
KEEP_POSTS = 220
MOOD_START = 58.0
MOOD_NORMAL = 55.0
MOOD_DRIFT = 0.05            # each matchday: this share of the way back to normal
MOOD_RESULT = 5.0            # per point above / below what was expected
MOOD_SIGNING = 3.0           # a big signing (>= BIG_FEE)
MOOD_SALE = -4.0             # one of your three best sold
BIG_FEE = 15_000_000
BOARD_NUDGE = 0.015          # board confidence per matchday for each point of mood away from normal
CROWD = 1.0 / 25.0           # home game: players' morale per point of mood away from normal (max CROWD_MAX)
CROWD_MAX = 1.2

TABLOID, BROADSHEET, LOCAL = "The Daily Roar", "The National Chronicle", "local"


def _m(career):
    m = career.setdefault("media", {})
    m.setdefault("articles", [])
    m.setdefault("posts", [])
    m.setdefault("mood", MOOD_START)
    m.setdefault("mood_hist", [])
    m.setdefault("seen_log", 0)
    m.setdefault("seen_md", 0)
    m.setdefault("next_id", 1)
    return m


def local_paper(career):
    club = career["clubs"][career["my_club"]]
    return f"{club['name'].split(' ')[0]} Evening Post"


def articles(career):
    return list(reversed(_m(career)["articles"]))


def posts(career):
    return list(reversed(_m(career)["posts"]))


def mood(career):
    return _m(career)["mood"]


def mood_word(m):
    return ("Delighted" if m >= 78 else "Happy" if m >= 64 else "Content" if m >= 50 else
            "Restless" if m >= 38 else "Angry" if m >= 25 else "Mutinous")


def _name(career, cid, short=False):
    c = career["clubs"][cid] if 0 <= cid < len(career["clubs"]) else None
    if c is None:
        return "?"
    return (c.get("short") or c["name"]) if short else c["name"]


def _nick(career, cid):
    """What fans call the club: the second word if there is one (Rovers, Athletic...), else the first."""
    w = _name(career, cid).split(" ")
    return w[-1] if len(w) > 1 and w[-1] not in ("FC", "City", "Town", "United", "Park") else w[0]


def _add_article(career, paper, kind, head, body, club=None, date=None):
    m = _m(career)
    m["articles"].append({"id": m["next_id"], "date": date or career.get("date"), "paper": paper, "kind": kind,
                          "head": head, "body": body, "club": club})
    m["next_id"] += 1
    del m["articles"][:-KEEP_ARTICLES]


def _add_post(career, who, handle, kind, text, likes, club=None, pid=None, date=None):
    m = _m(career)
    m["posts"].append({"id": m["next_id"], "date": date or career.get("date"), "who": who, "handle": handle,
                       "kind": kind, "text": text, "likes": int(likes), "club": club, "pid": pid})
    m["next_id"] += 1
    del m["posts"][:-KEEP_POSTS]


def _rng(career, salt):
    return random.Random(f"media:{career.get('date')}:{career.get('matchday')}:{salt}")


def _ord(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _money(fee):
    from career import finance as fin
    return fin.money(fee)


# ---------------------------------------------------------------------------
# Expectations (as the board sees them)
# ---------------------------------------------------------------------------
def _expected(career, r, cid):
    from career import board as brd
    home = r["home"] == cid
    opp = career["clubs"][r["away"] if home else r["home"]]
    mine = brd._expected_ppg(career, career["clubs"][cid])
    theirs = brd._expected_ppg(career, opp)
    return max(0.2, min(2.8, 1.35 + (mine - theirs) * 0.9 + (0.3 if home else -0.3)))


def _for(r, cid):
    home = r["home"] == cid
    gf, ga = (r["hg"], r["ag"]) if home else (r["ag"], r["hg"])
    return home, gf, ga, (r["away"] if home else r["home"])


def _scorers(r, side):
    out = {}
    for g in r.get("goals", []):
        if g.get("team") == side and not g.get("own_goal"):
            nm = g["name"].split(" ")[-1]
            out[nm] = out.get(nm, 0) + 1
    return ", ".join(f"{n}{' (' + str(k) + ')' if k > 1 else ''}" for n, k in out.items())


# ---------------------------------------------------------------------------
# Catching up: pre-season preview, transfers since we last looked
# ---------------------------------------------------------------------------
def catch_up(career):
    m = _m(career)
    if not m["articles"]:
        _preview(career)
    log = career.get("transfer_log", [])
    start = min(m["seen_log"], len(log))
    if len(log) < m["seen_log"]:                 # (the log was trimmed)
        start = max(0, len(log) - 10)
    for e in log[start:]:
        _transfer_story(career, e)
    m["seen_log"] = len(log)


def _preview(career):
    from career import divisions
    t = sorted(divisions.clubs_in(career), key=lambda c: -morale._strength(c))
    if len(t) < 4:
        return
    rng = _rng(career, "preview")
    fav, second = t[0], t[1]
    me = career["clubs"][career["my_club"]]
    rank = [c["id"] for c in t].index(me["id"]) + 1
    _add_article(career, BROADSHEET, "preview", f"Season preview: {fav['name']} the team to beat",
                 f"Our panel expects {fav['name']} to lead the way, with {second['name']} their closest challengers. "
                 f"At the other end, {t[-1]['name']} and {t[-2]['name']} look most at risk.")
    _add_article(career, TABLOID, "preview", rng.choice([f"{fav['name'].split(' ')[0].upper()} TO WALK IT?",
                                                         f"TITLE IS {fav['name'].split(' ')[0].upper()}'S TO LOSE"]),
                 f"Bookies make {fav['name']} red-hot favourites. Can anyone stop them? Don't bet the house on it.")
    hope = ("a title challenge" if rank <= 2 else "a top-four finish" if rank <= 5 else
            "a solid mid-table season" if rank <= 13 else "survival")
    _add_article(career, local_paper(career), "preview", f"{me['name']}: fans dream of {hope}",
                 f"Supporters head into the new campaign with {hope} in mind. The experts rank the squad "
                 f"{_ord(rank)} in the league on paper - now it's down to the manager.", club=me["id"])


def _transfer_story(career, e):
    me = career["clubs"][career["my_club"]]
    rng = _rng(career, f"tr:{e['player']}:{e['date']}")
    mine_in, mine_out = e["to"] == me["name"], e["from"] == me["name"]
    fee = e.get("fee", 0) or 0
    big = fee >= BIG_FEE
    p_last = e["player"].split(" ")[-1]
    if mine_in or mine_out:
        if mine_in:
            head = rng.choice([f"{p_last} completes move to {me['name']}", f"{me['name']} land {e['player']}",
                               f"Done deal: {e['player']} signs"])
            body = (f"{e['player']} ({e['pos']}) has joined from {e['from']}"
                    + (f" for {_money(fee)}" if fee else " on a free") + ". "
                    + rng.choice(["Fans will hope he hits the ground running.", "The manager has his man.",
                                  "A statement of intent."]))
            _add_article(career, local_paper(career), "transfer", head, body, club=me["id"], date=e["date"])
            _fan_reaction(career, "signing", e)
            _player_post(career, None, "signed", e)
            _shift_mood(career, MOOD_SIGNING if big else 1.0)
        else:
            head = rng.choice([f"{p_last} leaves for {e['to']}", f"{e['player']} departs",
                               f"End of an era? {p_last} sold"])
            body = (f"{e['player']} has left for {e['to']}" + (f" in a {_money(fee)} deal" if fee else "") + ". "
                    + rng.choice(["Not every supporter is happy.", "A good bit of business, says the club.",
                                  "The fans will want that money spent."]))
            _add_article(career, local_paper(career), "transfer", head, body, club=me["id"], date=e["date"])
            star = _was_star(career, e)
            _fan_reaction(career, "sale_star" if star else "sale", e)
            _shift_mood(career, MOOD_SALE if star else 0.0)
        if big:
            _add_article(career, TABLOID, "transfer", _tabloid_transfer(rng, e), _tabloid_transfer_body(rng, e),
                         date=e["date"])
        return
    if big:
        if rng.random() < 0.6:
            _add_article(career, TABLOID, "transfer", _tabloid_transfer(rng, e), _tabloid_transfer_body(rng, e),
                         date=e["date"])
        else:
            _add_article(career, BROADSHEET, "transfer", f"{e['to']} sign {e['player']} for {_money(fee)}",
                         f"{e['to']} have completed the signing of {e['pos']} {e['player']} from {e['from']}, a fee "
                         f"of {_money(fee)}.", date=e["date"])
        if rng.random() < 0.5:
            _journo_post(career, f"{e['player']} to {e['to']} is done. {_money(fee)}. Medical passed. #transfers",
                         date=e["date"])


def _was_star(career, e):
    fee = e.get("fee", 0) or 0
    return fee >= 20_000_000


def _tabloid_transfer(rng, e):
    t = e["to"].split(" ")[0].upper()
    p = e["player"].split(" ")[-1].upper()
    return rng.choice([f"{t} SPLASH THE CASH ON {p}", f"{p} SEALS {_money(e.get('fee', 0)).upper()} MOVE",
                       f"KERCHING! {p} JOINS {t}", f"{t} BAG {p}"])


def _tabloid_transfer_body(rng, e):
    return (f"{e['to']} have splashed {_money(e.get('fee', 0))} on {e['from']}'s {e['player']}. "
            + rng.choice(["Big money, big pressure.", "Will he be worth it? Only time will tell.",
                          "Rivals have been warned."]))


# ---------------------------------------------------------------------------
# The matchday
# ---------------------------------------------------------------------------
def after_matchday(career, md, results):
    """Stories, posts and the fans' mood for a matchday just played (your league + Spain)."""
    catch_up(career)
    m = _m(career)
    if md <= m["seen_md"]:
        return
    m["seen_md"] = md
    me = career["my_club"]
    my = next((r for r in results if me in (r["home"], r["away"])), None)
    if my:
        _match_report(career, my)
        _match_social(career, my)
        _mood_after(career, my)
    _elsewhere(career, results, my)
    _hat_tricks(career, results)
    if md >= 5:
        _table_story(career, md)
    _pressure(career)
    _unhappy(career)
    _rumour(career)
    _spain(career)
    _other_division(career)
    m["mood_hist"] = (m["mood_hist"] + [round(m["mood"], 1)])[-12:]


def _crowd_line(career, r):
    from career import clubinfo, crowds
    host = career["clubs"][r["home"]]
    pr = clubinfo.profile(host)
    where = f" at {pr['ground']['name']}" if pr else ""
    cap = host["finance"]["capacity"]
    if r["att"] >= cap * crowds.SOLD_OUT:
        return f"A sell-out crowd of {r['att']:,}{where}."
    return f"The crowd{where}: {r['att']:,}."


def _match_report(career, r):
    me = career["my_club"]
    rng = _rng(career, "report")
    home, gf, ga, opp = _for(r, me)
    exp = _expected(career, r, me)
    pts = 3 if gf > ga else 1 if gf == ga else 0
    shock = pts - exp
    us, them = _name(career, me), _name(career, opp)
    U, T = us.split(" ")[0].upper(), them.split(" ")[0].upper()
    score = f"{r['hg']}-{r['ag']}"
    line = f"{_name(career, r['home'])} {r['hg']}-{r['ag']} {_name(career, r['away'])}"
    our_side = 0 if home else 1
    sc_us, sc_them = _scorers(r, our_side), _scorers(r, 1 - our_side)
    poss = r.get("possession")
    poss_us = (poss if home else 100 - poss) if isinstance(poss, (int, float)) else None
    goals_line = (f"Goals: {sc_us}" if sc_us else "") + ("; " if sc_us and sc_them else "") + \
        (f"{them.split(' ')[0]}: {sc_them}" if sc_them else "")
    # local paper - always
    if pts == 3:
        head = rng.choice([f"{us.split(' ')[-1]} see off {them}" if gf - ga >= 2 else f"{us} edge past {them}",
                           f"Three points for {us}", f"Delight as {us} beat {them}"])
        mood_line = rng.choice(["The supporters went home happy.", "A performance to build on.",
                                "The manager will be pleased with that."])
    elif pts == 1:
        head = rng.choice([f"Honours even against {them}", f"{us} held by {them}", f"Point apiece for {us}"])
        mood_line = ("A point gained on the road." if not home and shock > 0 else
                     "Two points dropped, some will say." if shock < -0.5 else "Fair result on the day.")
    else:
        head = rng.choice([f"{us} beaten by {them}", f"Frustration for {us}", f"No joy for {us} against {them}"])
        mood_line = rng.choice(["Plenty to work on.", "The boos at full time said it all." if shock < -1.2 else
                                "Not the day anyone wanted.", "Back to the training ground."])
    body = f"{line}. " + (f"{goals_line}. " if goals_line else "") + \
        (f"{us} had {round(poss_us)}% of the ball. " if poss_us is not None else "") + mood_line
    if r.get("att"):                                    # the crowd (career/crowds.py)
        body += " " + _crowd_line(career, r)
    body += " " + _table_line(career, me) + " " + _next_line(career, me)
    _add_article(career, local_paper(career), "report", head, body.strip(), club=me)
    # nationals - only if it's a story
    if shock >= 1.3:
        _add_article(career, TABLOID, "upset", rng.choice([f"{U} STUN {T}!", f"GIANT-KILLERS {U}!",
                                                          f"{T} RED-FACED"]),
                     f"Nobody saw this coming. {line}. " + (f"Hero{'es' if ',' in sc_us else ''}: {sc_us}." if sc_us else ""),
                     club=me)
    elif shock <= -1.6:
        _add_article(career, TABLOID, "upset", rng.choice([f"{U} FLOP!", f"{U} IN MELTDOWN", f"{T} SHOCK {U}"]),
                     f"{line}. Questions will be asked of the manager after that one.", club=me)


_PEOPLE = [  # (persona, display name style, handle style)
    ("moaner", "Grumpy {n}", "{N}Moans"),
    ("optimist", "{n} Believer", "{N}Believe"),
    ("stats", "{n} Numbers", "{N}xG"),
    ("sacker", "Proper {n}", "Real{N}Fan"),
    ("banter", "{n} Banter Bus", "{N}Banter"),
    ("oldtimer", "{n} Since '78", "{N}Since78"),
    ("kid", "{n} Wonderkid Watch", "{N}Academy"),
    ("local", "{n} Til I Die", "{N}TilIDie"),
]


def _fans(career):
    n = _nick(career, career["my_club"])
    return [(kind, disp.format(n=n), "@" + handle.format(N=n.replace(" ", ""))) for kind, disp, handle in _PEOPLE]


FAN_LINES = {
    "moaner": {"W": ["Won, but we were rubbish for an hour. Don't get carried away.", "Lucky. Very lucky.",
                     "Three points papering over the cracks.", "Still can't defend a set piece.",
                     "Fine. But {them} were awful, let's be honest.", "Happy with the points, not the performance."],
               "D": ["A draw against {them}. Embarrassing.", "Same old story. No cutting edge.",
                     "How do we not beat {them}?", "Passing it sideways for 90 minutes. Riveting.",
                     "Another two points thrown away.", "I want my afternoon back."],
               "L": ["Unacceptable. Again.", "I've seen better at the park on a Sunday.",
                     "Some of these players don't care. You can see it.", "Season's going nowhere.",
                     "Clueless from start to finish.", "Worst I've seen us play in years."]},
    "optimist": {"W": ["WHAT A WIN! We're going up the table!", "Get in!! This team is special.",
                       "Told you all. TOLD YOU.", "Can feel something building here.",
                       "Best we've looked all season!", "Dreaming big now."],
                 "D": ["A point is a point. Onwards!", "Good shift today lads, keep going.",
                       "Unbeaten is unbeaten!", "Building nicely. Patience.",
                       "Plenty of positives there.", "We'll turn these into wins soon."],
                 "L": ["Heads up, plenty of football left.", "Bad day at the office. We go again!",
                       "Still believe in this squad.", "One result doesn't change anything.",
                       "Learn from it and bounce back.", "Long season. Stay with them."]},
    "stats": {"W": ["Deserved that. Better chances, better shape.", "Win rate climbing. Trend is good.",
                    "Pressing numbers way up today. Shows.", "Dominated the middle third.",
                    "That's the clinical finishing we've been missing.", "Underlying numbers say it wasn't a fluke."],
              "D": ["Fair on the numbers. Neither side created much.", "We need more shots in the box.",
                    "Too many crosses, not enough cut-backs.", "Possession without penetration again.",
                    "Expected goals said draw. Draw it is.", "Midfield passing was too slow."],
              "L": ["Outplayed in midfield. The numbers don't lie.", "Their chances were far better than ours.",
                    "Lost the second balls all game.", "Our full-backs got overloaded every time.",
                    "Shots from distance won't win you anything.", "That's a structural problem, not bad luck."]},
    "sacker": {"W": ["Finally. Still not convinced by the manager.", "One swallow doesn't make a summer.",
                     "Win's a win. Doesn't change my mind.", "Took him long enough."],
               "D": ["Tactically clueless. Time for a change?", "Not good enough for a club this size.",
                     "Where's the plan? There isn't one.", "We're standing still under this manager."],
               "L": ["That's it. Manager out.", "How much longer do we put up with this?",
                     "Board need to act. Today.", "Can't see where the next win comes from.",
                     "Every week the same excuses."]},
    "banter": {"W": ["Bet the {them} lot are quiet now", "{them} fans, where are you?",
                     "Someone check on the {them} group chat", "Easy. Next.", "Absolute scenes."],
               "D": ["At least we're not {them}.", "Could've been worse. Could've been {them}.",
                     "Draw specialists, us.", "Meh. Pub?"],
               "L": ["Not even mad. Ok, a bit mad.", "I'm going to need a minute.",
                     "Deleting the app. Back next week.", "Who wants my season ticket? Joking. Mostly."]},
    "oldtimer": {"W": ["Reminds me of the old days. Proper football.", "That's how you do it.",
                       "Proper shift from the lads. Old school.", "My dad would've loved that one."],
                 "D": ["In my day we'd have won that.", "Steady. Nothing more.",
                       "Seen a thousand of these. Move on.", "Wouldn't have happened under the old gaffer."],
                 "L": ["Seen worse. Not much worse, mind.",
                       "Back in my day they'd run through walls for this shirt.",
                       "Forty years watching this club. Still hurts.", "Football's changed. Not for the better."]},
    "kid": {"W": ["Give the youngsters a chance and they'll take it!", "Future's bright.",
                  "Academy will be watching that and dreaming.", "Bring on the next generation."],
            "D": ["Bring the kids on, they're hungry.", "Why no minutes for the academy lads?",
                  "Time to trust the youth.", "One of the kids would've nicked that."],
            "L": ["Play the youngsters. Can't be worse.", "Academy lads would've run harder than that.",
                  "Blood the kids. Nothing to lose.", "Some of the youth team want it more."]},
    "local": {"W": ["{us} til I die!! Massive win.", "Proud of every one of them today.",
                    "Great day out with the lads. Up the {us}!", "Sang myself hoarse. Worth it."],
              "D": ["Point's a point. Up the {us}.", "Was in the rain for that. Worth it? Just about.",
                    "Away end was bouncing anyway.", "Long trip for a point. I'll take it."],
              "L": ["Gutted. Still behind them.", "Long drive home after that one.",
                    "Through thick and thin. This is the thin.", "Back next week. Always."]},
}


def _fresh(career, rng, options):
    """A line nobody's posted lately (keeps the feed from repeating)."""
    import zlib
    m = _m(career)
    said = m.setdefault("said", [])
    keys = [format(zlib.crc32(o.encode()) & 0xFFFFF, "x") for o in options]
    fresh = [o for o, k in zip(options, keys) if k not in said] or options
    line = rng.choice(fresh)
    said.append(format(zlib.crc32(line.encode()) & 0xFFFFF, "x"))
    del said[:-80]
    return line


def _fan_line(career, rng, kind, ctx):
    """One fan's take.  ctx: res W/D/L, shock, us, them, scorer, mood."""
    res, us, them, sc, mood = ctx["res"], ctx["us"], ctx["them"], ctx.get("scorer"), ctx["mood"]
    if sc and res == "W" and kind in ("optimist", "local", "kid") and rng.random() < 0.4:
        return _fresh(career, rng, [f"{sc}!!! What a player.", f"{sc} you beauty.", f"Give {sc} a new contract NOW.",
                                    f"{sc} is different class.", f"Sing his name: {sc}!"])
    if kind == "sacker" and mood >= 70 and res != "L":
        return _fresh(career, rng, ["Ok fine. The manager knows what he's doing. Maybe.",
                                    "Alright, I'll admit it. Good job.", "Starting to come round to this manager."])
    return _fresh(career, rng, FAN_LINES[kind][res]).format(us=us, them=them)


def _poss(name):
    return name + ("'" if name.endswith("s") else "'s")


def _table_line(career, cid):
    t = league.table(career)
    pos = league.position_of(career, cid)
    row = next((x for x in t if x["club"] == cid), None)
    if not row or not row["p"]:
        return ""
    gap = t[0]["pts"] - row["pts"]
    where = ("top of the table" if pos == 1 else f"{_ord(pos)}, {gap} point{'s' if gap != 1 else ''} off the top"
             if pos <= 6 else f"{_ord(pos)} in the table")
    return f"The result leaves {_name(career, cid)} {where}."


def _next_line(career, cid):
    nf = league.next_fixture(career)
    if not nf:
        return ""
    _, h, a = nf
    if cid not in (h, a):
        return ""
    opp = a if h == cid else h
    return f"Next up: {_name(career, opp)} {'at home' if h == cid else 'away'}."


def _season_goals(career, name):
    return sum(1 for day in career.get("results", {}).values() for r in day for g in r.get("goals", [])
               if g.get("name") == name and not g.get("own_goal"))


def _match_social(career, r):
    me = career["my_club"]
    rng = _rng(career, "social")
    home, gf, ga, opp = _for(r, me)
    exp = _expected(career, r, me)
    res = "W" if gf > ga else "D" if gf == ga else "L"
    pts = {"W": 3, "D": 1, "L": 0}[res]
    shock = pts - exp
    us_n, them_n = _nick(career, me), _nick(career, opp)
    our_side = 0 if home else 1
    scorer = next((g["name"].split(" ")[-1] for g in r.get("goals", []) if g.get("team") == our_side
                   and not g.get("own_goal")), None)
    m = _m(career)
    hype = 300 + 900 * max(0.0, min(1.0, abs(shock) / 2.0))
    _add_post(career, _name(career, me), "@" + _name(career, me).replace(" ", ""), "club",
              f"FT | {_name(career, r['home'], True)} {r['hg']}-{r['ag']} {_name(career, r['away'], True)}"
              + (f"  ({_scorers(r, our_side)})" if _scorers(r, our_side) else ""), hype * 2, club=me)
    ctx = {"res": res, "shock": shock, "us": us_n, "them": them_n, "scorer": scorer, "mood": m["mood"]}
    people = _fans(career)
    rng.shuffle(people)
    n = 4 + (1 if abs(shock) > 1 else 0) + (1 if res == "L" and m["mood"] < 45 else 0)
    for kind, disp, handle in people[:n]:
        if kind == "sacker" and res == "W" and rng.random() < 0.5:
            continue
        _add_post(career, disp, handle, "fan", _fan_line(career, rng, kind, ctx), rng.uniform(0.2, 1.0) * hype, club=me)
    if res == "L":
        rival = _fresh(career, rng, ["Ha. {us} were shocking.", "{us} fans gone very quiet tonight",
                                     "Easiest three points of the season", "Is that {usp} manager or a cardboard cutout?",
                                     "Thanks for the points, {us}.", "{us} = three points. Every time."])
        _add_post(career, f"{them_n} Away Days", f"@{them_n.replace(' ', '')}Away", "rival",
                  rival.format(us=us_n, usp=_poss(us_n)), rng.uniform(0.4, 1.2) * hype, club=opp)
    # your players
    if scorer and rng.random() < 0.75:
        _player_post(career, scorer, "scored", r)
    if res == "L" and rng.random() < 0.4:
        _player_post(career, None, "loss", r)
    for p in career["clubs"][me]["players"]:
        if morale.level(p) < 32 and (p.get("morale_why") or {}).get("minutes", 0) < -1.5 and rng.random() < 0.18:
            _player_post(career, p["Name"].split(" ")[-1], "cryptic", r, p=p)
            break


def _player_post(career, last_name, what, ref, p=None):
    me = career["clubs"][career["my_club"]]
    rng = _rng(career, f"pp:{what}:{last_name}")
    if p is None and last_name:
        p = next((q for q in me["players"] if q["Name"].split(" ")[-1] == last_name), None)
    if what == "signed":
        p = next((q for q in me["players"] if q["Name"] == ref["player"]), None)
        if p is None:
            return
        text = rng.choice([f"Delighted to join {me['name']}. Can't wait to meet the fans!",
                           f"Proud day. New chapter. Let's go {_nick(career, me['id'])}!",
                           "Dream come true. Thank you to everyone who made it happen."])
    elif what == "scored":
        if p is None:
            return
        text = _fresh(career, rng, ["Buzzing with that. Massive 3 points!", "Love scoring in front of these fans.",
                                    "Team performance. On to the next one.", "Get in!! Proud of the lads.",
                                    "That one's for the fans.", "Big win. Big performance. Recover and go again."])
    elif what == "loss":
        p = rng.choice([q for q in me["players"] if q["id"] in (me.get("lineup") or {}).values()] or me["players"])
        text = _fresh(career, rng, ["Not good enough today. We'll put it right.",
                                    "Sorry to the fans who travelled. We go again.", "Hurting. Heads up.",
                                    "We owe you one. Training tomorrow."])
    elif what == "cryptic":
        if p is None:
            return
        text = _fresh(career, rng, ["Some people just don't see it.", "Keep working. Keep quiet. Keep smiling.",
                                    "Patience has a limit.", "Ready when needed. If needed.", "...",
                                    "Every dog has its day."])
    else:
        return
    handle = "@" + p["Name"].replace(" ", "")
    _add_post(career, p["Name"], handle, "player", text, rng.uniform(400, 2500), club=me["id"], pid=p["id"],
              date=ref.get("date") if isinstance(ref, dict) and "player" in ref else None)


def _fan_reaction(career, what, e):
    me = career["my_club"]
    rng = _rng(career, f"fr:{what}:{e['player']}")
    people = _fans(career)
    rng.shuffle(people)
    p = e["player"].split(" ")[-1]
    lines = {"signing": [f"Get {p} in!! Big signing.", f"Not sure about {p} but let's see.", f"{p}! Didn't see that coming.",
                         f"{_money(e.get('fee', 0))} for {p}? Hope he's worth it." if e.get("fee") else f"Free transfer, no risk. Welcome {p}!"],
             "sale": [f"Good luck {p}. Thanks for everything.", f"Fair enough, {p} wasn't playing much.", f"Money better be spent."],
             "sale_star": [f"Selling {p}?! What is this club doing.", f"{p} gone. Gutted.", f"Board out if that money isn't spent.",
                           f"Can't believe we've let {p} go."]}[what]
    for kind, disp, handle in people[:3]:
        _add_post(career, disp, handle, "fan", rng.choice(lines), rng.uniform(200, 1500), club=me, date=e["date"])


def _journo_post(career, text, date=None):
    rng = _rng(career, "journo:" + text[:10])
    who = rng.choice([("Dan Clarke", "@DanClarkeFootball"), ("Sophie Hale", "@SophieHaleNews"),
                      ("Raj Mistry", "@RajMistryTransfers")])
    _add_post(career, who[0], who[1], "journo", text, rng.uniform(800, 4000), date=date)


def _mood_after(career, r):
    me = career["my_club"]
    m = _m(career)
    home, gf, ga, opp = _for(r, me)
    pts = 3 if gf > ga else 1 if gf == ga else 0
    _shift_mood(career, MOOD_RESULT * (pts - _expected(career, r, me)))
    m["mood"] += (MOOD_NORMAL - m["mood"]) * MOOD_DRIFT
    m["mood"] = round(max(3.0, min(98.0, m["mood"])), 1)
    from career import board as brd                       # the fans' voice reaches the boardroom
    brd._bump(career, BOARD_NUDGE * (m["mood"] - MOOD_NORMAL))
    if home:                                              # the crowd at the ground
        d = max(-CROWD_MAX, min(CROWD_MAX, CROWD * (m["mood"] - MOOD_NORMAL)))
        for p in career["clubs"][me]["players"]:
            p["morale"] = round(max(3.0, min(98.0, morale.level(p) + d)), 1)


def _shift_mood(career, d):
    m = _m(career)
    m["mood"] = round(max(3.0, min(98.0, m["mood"] + d)), 1)


# ---------------------------------------------------------------------------
# Around the league
# ---------------------------------------------------------------------------
def _elsewhere(career, results, mine):
    rng = _rng(career, "else")
    others = [r for r in results if r is not mine]
    if not others:
        return
    def shock(r):
        h, a = career["clubs"][r["home"]], career["clubs"][r["away"]]
        d = morale._strength(h) - morale._strength(a)
        res = (r["hg"] > r["ag"]) - (r["hg"] < r["ag"])
        return -d * res if res else 0.0
    up = max(others, key=shock)
    if shock(up) >= 3.0:
        win, lose = (up["home"], up["away"]) if up["hg"] > up["ag"] else (up["away"], up["home"])
        W, L = _name(career, win).split(" ")[0].upper(), _name(career, lose).split(" ")[0].upper()
        _add_article(career, TABLOID, "upset", rng.choice([f"{W} STUN {L}", f"{L} HUMBLED", f"SHOCK! {W} TOPPLE {L}"]),
                     f"{_name(career, up['home'])} {up['hg']}-{up['ag']} {_name(career, up['away'])}. "
                     f"The upset of the weekend: {_name(career, win)} ({_ord(league.position_of(career, win))}) "
                     f"got the better of {_name(career, lose)} ({_ord(league.position_of(career, lose))}). "
                     + rng.choice(["Nobody saw that coming.", "Football, eh?", "Questions for the losers this week."]))
    big = max(others, key=lambda r: abs(r["hg"] - r["ag"]))
    if abs(big["hg"] - big["ag"]) >= 4:
        win = big["home"] if big["hg"] > big["ag"] else big["away"]
        lose = big["away"] if win == big["home"] else big["home"]
        side = 0 if win == big["home"] else 1
        sc = _scorers(big, side)
        _add_article(career, BROADSHEET, "result", f"{_name(career, win)} run riot against {_name(career, lose)}",
                     f"{_name(career, big['home'])} {big['hg']}-{big['ag']} {_name(career, big['away'])}. "
                     + (f"The goals came from {sc}. " if sc else "")
                     + f"A chastening afternoon for {_name(career, lose)}. " + _table_line(career, win))


def _hat_tricks(career, results):
    for r in results:
        cnt = {}
        for g in r.get("goals", []):
            if not g.get("own_goal"):
                k = (g["name"], g.get("team"))
                cnt[k] = cnt.get(k, 0) + 1
        for (nm, side), n in cnt.items():
            if n >= 3:
                cid = r["home"] if side == 0 else r["away"]
                rng = _rng(career, "hat" + nm)
                last = nm.split(" ")[-1].upper()
                _add_article(career, TABLOID, "hattrick",
                             rng.choice([f"HAT-TRICK HERO {last}", f"{last} BAGS THE MATCH BALL", f"TREBLE TROUBLE: {last}"]),
                             f"{nm} scored {n} for {_name(career, cid)} "
                             f"({_name(career, r['home'])} {r['hg']}-{r['ag']} {_name(career, r['away'])}). "
                             f"That takes him to {_season_goals(career, nm) + n} league goals this season. "
                             + rng.choice(["Defenders beware.", "He'll be keeping the match ball.",
                                           "Scouts will have taken note."]),
                             club=cid)


def _table_story(career, md):
    rng = _rng(career, "table")
    t = league.table(career)
    if len(t) < 6:
        return
    m = _m(career)
    leader = t[0]["club"]
    if m.get("leader") != leader:
        if m.get("leader") is not None:
            _add_article(career, BROADSHEET, "table", f"{_name(career, leader)} go top",
                         f"After matchday {md}, {_name(career, leader)} lead the way on {t[0]['pts']} points, "
                         f"{t[0]['pts'] - t[1]['pts']} clear of {_name(career, t[1]['club'])}.")
        m["leader"] = leader
    me = career["my_club"]
    pos = league.position_of(career, me)
    if pos == 1 and m.get("me_top") != md - 1:
        _add_article(career, local_paper(career), "table", rng.choice(["Top of the league!", "Look at the table!"]),
                     f"{_name(career, me)} sit top of the league after matchday {md}. Enjoy it.", club=me)
    m["me_top"] = md if pos == 1 else m.get("me_top")
    from career import divisions
    if md % 6 == 0 and divisions.exists(career) and divisions.my_div(career) == "d1":
        # Division 1: the promotion race and the play-off places (nobody goes down from here)
        _add_article(career, BROADSHEET, "table", rng.choice(["Division 1: the promotion race", "Who's going up?"]),
                     f"{_name(career, t[0]['club'])} ({t[0]['pts']} pts) and {_name(career, t[1]['club'])} "
                     f"({t[1]['pts']}) hold the automatic places after matchday {md}; "
                     f"{', '.join(_name(career, x['club']) for x in t[2:6])} fill the play-off places, "
                     f"with {_name(career, t[6]['club'])} {t[5]['pts'] - t[6]['pts']} point"
                     f"{'s' if t[5]['pts'] - t[6]['pts'] != 1 else ''} off them.")
        return
    if md % 6 == 0:
        bottom = t[-3:]
        _add_article(career, BROADSHEET, "table", "Relegation battle heats up",
                     f"{', '.join(_name(career, x['club']) for x in bottom)} occupy the bottom three after matchday {md}. "
                     f"The gap to safety is {t[-4]['pts'] - t[-3]['pts']} point{'s' if t[-4]['pts'] - t[-3]['pts'] != 1 else ''}.")
        if t[0]["pts"] - t[1]["pts"] <= 3:
            _add_article(career, TABLOID, "table", "TITLE RACE IS ON!",
                         f"{_name(career, t[0]['club'])} and {_name(career, t[1]['club'])} are separated by "
                         f"{t[0]['pts'] - t[1]['pts']} point{'s' if t[0]['pts'] - t[1]['pts'] != 1 else ''}. Buckle up.")


def _pressure(career):
    from career import board as brd
    b = brd.state(career)
    m = _m(career)
    me = career["my_club"]
    conf = b["confidence"]
    rng = _rng(career, "pressure")
    if conf < brd.WARN_AT and m.get("pressure") != "warn":
        _add_article(career, TABLOID, "pressure", rng.choice(["BOSS ON THE BRINK", "AXE HANGS OVER BOSS",
                                                              f"{_name(career, me).split(' ')[0].upper()} BOSS FEELS THE HEAT"]),
                     f"Sources close to the {_name(career, me)} boardroom say patience is wearing thin.", club=me)
        _journo_post(career, f"Understand there is growing unease at {_name(career, me)}. Results need to improve quickly.")
        m["pressure"] = "warn"
    elif conf >= 70 and m.get("pressure") != "praise" and b.get("games", 0) >= 6:
        _add_article(career, local_paper(career), "pressure", "Board delighted with progress",
                     "The manager has won over the boardroom, insiders say.", club=me)
        m["pressure"] = "praise"
    elif brd.WARN_AT + 10 <= conf < 70:
        m["pressure"] = None


def _unhappy(career):
    me = career["clubs"][career["my_club"]]
    m = _m(career)
    told = m.setdefault("wants_out_told", [])
    for p in me["players"]:
        if p.get("wants_out") and p["id"] not in told:
            rng = _rng(career, "out" + p["Name"])
            last = p["Name"].split(" ")[-1].upper()
            _add_article(career, TABLOID, "unrest", rng.choice([f"{last} WANTS OUT!", f"{last}: GET ME OUT",
                                                                f"BUST-UP: {last} DEMANDS MOVE"]),
                         f"{p['Name']} has asked to leave {me['name']}, we can reveal.", club=me["id"])
            told.append(p["id"])
    m["wants_out_told"] = [i for i in told if any(q["id"] == i and q.get("wants_out") for q in me["players"])]


def _rumour(career):
    from career import transfers as trf
    if not trf.in_window(career.get("date", "")):
        return
    rng = _rng(career, "rumour")
    if rng.random() > 0.6:
        return
    clubs = career["clubs"]
    buyer = rng.choice(clubs)
    target_club = rng.choice([c for c in clubs if c is not buyer])
    pool = sorted(target_club["players"], key=lambda p: -float(p.get("Potential", 0) or 0))[:5]
    if not pool:
        return
    p = rng.choice(pool)
    me = career["my_club"]
    head = rng.choice([f"{buyer['name']} eye {p['Name']}", f"{buyer['name']} weigh up move for {target_club['name']}'s {p['Name'].split(' ')[-1]}"])
    _add_article(career, TABLOID if rng.random() < 0.5 else BROADSHEET, "rumour", head,
                 f"{buyer['name']} are said to be monitoring {target_club['name']} {p['Pos']} {p['Name']}. "
                 + rng.choice(["Nothing is close yet.", "A bid could follow.", "His club would demand a big fee."]),
                 club=target_club["id"] if target_club["id"] == me else None)
    _journo_post(career, rng.choice([f"Hearing {buyer['name']} keen on {p['Name']}. Early stages.",
                                     f"{p['Name']} on {buyer['name']}'s list. One to watch.",
                                     f"No truth in the {p['Name']} to {buyer['name']} talk, I'm told."]))


def _other_division(career):
    """Every few weeks: how the other English division's going (career/divisions.py)."""
    from career import divisions
    if not divisions.exists(career):
        return
    o = career["other"]
    md = o.get("matchday", 1) - 1
    m = _m(career)
    if md < 3 or m.get("other_md") == md or md % 4:
        return
    m["other_md"] = md
    t = league.table(career, o["div"])
    nm = divisions.name(o["div"])
    lead, second = t[0], t[1]
    if o["div"] == "d1":
        _add_article(career, BROADSHEET, "division", f"{nm}: {_name(career, lead['club'])} lead the way",
                     f"After {md} games {_name(career, lead['club'])} top {nm} on {lead['pts']} points, "
                     f"{lead['pts'] - second['pts']} ahead of {_name(career, second['club'])}. "
                     f"The play-off places: {', '.join(_name(career, x['club'], True) for x in t[2:6])}.")
    else:
        _add_article(career, BROADSHEET, "division", f"{nm}: {_name(career, lead['club'])} set the pace",
                     f"Up in the {nm}, {_name(career, lead['club'])} lead after {md} games with {lead['pts']} points. "
                     f"At the bottom: {', '.join(_name(career, x['club'], True) for x in t[-3:])}.")


def season_moves(career, up, down):
    """The summer's stories: who's gone up, who's gone down (career/divisions.py promote)."""
    rng = _rng(career, "moves")
    nm = lambda i: _name(career, i)
    _add_article(career, BROADSHEET, "division", f"Up go {_name(career, up[0], True)}, {_name(career, up[1], True)} "
                 f"and {_name(career, up[2], True)}",
                 f"{nm(up[0])} and {nm(up[1])} are promoted to the Premier Division, joined by play-off winners "
                 f"{nm(up[2])}. Going the other way: {', '.join(nm(i) for i in down)}.")
    _add_article(career, TABLOID, "division", rng.choice(["THE DROP!", "TRAPDOOR SWALLOWS THREE", "DOWN AND OUT"]),
                 f"Tears at {nm(down[0])}, {nm(down[1])} and {nm(down[2])} - Division 1 beckons. "
                 + rng.choice(["The parachute money will soften the blow.", "Expect a fire sale.",
                               "Some big names will want out."]))
    me = career["my_club"]
    if me in up:
        _add_article(career, local_paper(career), "division", rng.choice(["BACK IN THE BIG TIME!", "WE'RE GOING UP!",
                                                                         "PROMOTED!"]),
                     f"{nm(me)} are a Premier Division club. The town will be partying all summer - "
                     f"and the manager has a squad to strengthen.", club=me)
        _journo_post(career, f"Huge summer ahead for {nm(me)} after promotion. Expect plenty of incomings.")
    elif me in down:
        _add_article(career, local_paper(career), "division", rng.choice(["Relegated", "The drop confirmed",
                                                                         "A sad day for the club"]),
                     f"{nm(me)} will play in Division 1 next season. The manager says the aim is to come "
                     f"straight back up - the fans will hold him to that.", club=me)
        _journo_post(career, f"Relegation clauses kick in at {nm(me)}. Some players will be looking for a way out.")


def playoff_story(career, m, st):
    """The papers on a play-off result (career/playoffs.py)."""
    rng = _rng(career, "po" + m["id"])
    r = m["result"]
    nm = lambda i: _name(career, i)
    me = career["my_club"]
    if m["round"] == "semi" and m["leg"] == 2:
        tie = st["ties"][m["tie"]]
        w = tie["winner"]
        l = tie["a"] if w == tie["b"] else tie["b"]
        how = {"pens": " on penalties", "et": " after extra time"}.get(tie["how"], "")
        a = r["agg"] if m["home"] == w else r["agg"][::-1]
        _add_article(career, BROADSHEET, "playoffs", f"{_name(career, w, True)} reach the play-off final",
                     f"{nm(w)} beat {nm(l)} {a[0]}-{a[1]} on aggregate{how} and will play at the national stadium.",
                     club=me if me in (w, l) else None)
    elif m["round"] == "final":
        w = st["winner"]
        l = m["away"] if w == m["home"] else m["home"]
        how = (f" on penalties ({max(r['pens'])}-{min(r['pens'])})" if r.get("pens") else
               " after extra time" if r.get("et") else "")
        _add_article(career, TABLOID, "playoffs", rng.choice(["THE RICHEST GAME IN FOOTBALL", "PROMOTION PARTY",
                                                             f"{_name(career, w, True).upper()} ARE GOING UP"]),
                     f"{nm(w)} won the play-off final{how} against {nm(l)} - worth well over £100m to them. "
                     + rng.choice([f"Heartbreak for {nm(l)}.", f"{nm(l)} will have to do it all again.",
                                   "Scenes at the final whistle."]), club=me if me in (w, l) else None)


def cup_story(career, comp, m):
    """The papers on a cup tie (career/cups.py): your results, giant-killings, the final."""
    from career import cups
    r = m.get("result")
    if not r:
        return
    rd = comp["rounds"][m["round"]] if m.get("round") is not None and "rounds" in comp else None
    tie = rd["ties"][m["tie"]] if rd and m.get("tie") is not None else None
    if tie is None or tie.get("winner") is None or tie.get("how") == "bye":
        return
    w = tie["winner"]
    l = tie["a"] if w == tie["b"] else tie["b"]
    nm = lambda i: cups.name(career, i)
    me = career["my_club"]
    rng = _rng(career, "cup" + m["id"])
    how = {"pens": " on penalties", "et": " after extra time"}.get(tie.get("how"), "")
    score = f"{r['hg']}-{r['ag']}" if not r.get("agg") else f"{r['agg'][0]}-{r['agg'][1]} on aggregate"
    if rd["name"] == "Final":
        _add_article(career, BROADSHEET, "cup", f"{nm(w)} win {comp['name']}",
                     f"{nm(w)} beat {nm(l)}{how} in the final ({nm(m['home'])} {score} {nm(m['away'])}).",
                     club=me if me in (w, l) else None)
        _add_article(career, TABLOID, "cup", rng.choice([f"{cups.name(career, w, True).upper()} LIFT THE CUP",
                                                         "CUP GLORY!", "SILVERWARE!"]),
                     f"Scenes at the final whistle as {nm(w)} got their hands on {comp['name']}.",
                     club=me if me in (w, l) else None)
        return
    # a giant-killing: a much smaller club through
    from career import spain
    W, L = cups.club(career, w), cups.club(career, l)
    if W and L and spain.xi_rating(L, L.get("lineup") or {}) - spain.xi_rating(W, W.get("lineup") or {}) >= 8:
        _add_article(career, TABLOID, "cup", rng.choice(["GIANT-KILLING!", "CUP SHOCK!", "THE MAGIC OF THE CUP"]),
                     f"{nm(w)} knocked out {nm(l)} in {comp['name']} {rd['name'].lower()}{how} ({score}). "
                     + rng.choice(["What a night.", "Nobody saw that coming.", "The pubs will be busy tonight."]),
                     club=me if me in (w, l) else None)
    elif me in (w, l):
        if w == me:
            _add_article(career, local_paper(career), "cup", rng.choice(["Through to the next round", "Cup run goes on"]),
                         f"{nm(me)} are through in {comp['name']} after beating {nm(l)}{how} ({score}).", club=me)
        else:
            _add_article(career, local_paper(career), "cup", rng.choice(["Out of the cup", "Cup exit"]),
                         f"{nm(me)} are out of {comp['name']}, beaten by {nm(w)}{how} ({score}).", club=me)


def awards_story(career, out):
    """The papers on the season's awards (career/awards.py)."""
    from career import divisions
    for div in divisions.ORDER:
        aw = out.get(div)
        if not aw:
            continue
        p, b = aw.get("player"), aw.get("golden_boot")
        if p:
            _add_article(career, BROADSHEET, "awards", f"{p['name']} is the {divisions.name(div)}'s player of the season",
                         f"{p['name']} ({_name(career, p['club'])}, {p['note']}) takes the award"
                         + (f"; {b['name']} ({_name(career, b['club'])}) wins the Golden Boot with {b['note']}." if b else "."),
                         club=career["my_club"] if career["my_club"] in (p["club"], (b or {}).get("club")) else None)


def record_story(career, club, p, goals, holder, old):
    """A club's league-goals-in-a-season record falls (career/legends.py)."""
    _add_article(career, TABLOID, "record", f"{p['Name']} breaks {holder}'s record!",
                 f"{p['Name']} scored {goals} league goals for {club['name']} this season - beating the club record "
                 f"of {old} set by {holder}.", club=club["id"])


def _spain(career):
    if "spain" not in career:
        return
    from career import spain
    s = career["spain"]
    md = s.get("matchday", 1) - 1
    m = _m(career)
    if md < 1 or m.get("spain_md") == md or md % 3:
        return
    m["spain_md"] = md
    try:
        t = spain.table(career)
        lead = t[0]
        nm = spain.club(career, lead["club"])["name"]
        _add_article(career, BROADSHEET, "spain", f"Spain: {nm} set the pace",
                     f"In the {spain.NAME}, {nm} lead after {md} games with {lead['pts']} points.")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Friendlies (career/friendlies.py)
# ---------------------------------------------------------------------------
def friendly(career, f):
    """A friendly's result: a few lines in the local paper, the club's post."""
    r = f.get("result")
    if not r:
        return
    me = career["my_club"]
    us = _name(career, me)
    them = f["name"]
    rng = random.Random(f"friendly:{f['id']}")
    home_name, away_name = (us, them) if f["home"] else (them, us)
    line = f"{home_name} {r['hg']}-{r['ag']} {away_name}"
    our_side = 0 if f["home"] else 1
    sc = {}
    for g in r.get("goals", []):
        if g["team"] == our_side:
            n = g["name"].split(" ")[-1]
            sc[n] = sc.get(n, 0) + 1
    scorers = ", ".join(f"{n}{' (' + str(k) + ')' if k > 1 else ''}" for n, k in sc.items())
    gf, ga = r["gf"], r["ga"]
    pre = f["date"][5:7] in ("07", "08") and f["date"] < (career.get("calendar") or ["9999"])[0]
    what = "Pre-season" if pre else "Friendly"
    if gf > ga:
        head = rng.choice([f"{what}: {us.split(' ')[-1]} win at {them}" if not f["home"] else f"{what}: comfortable run-out against {them}",
                           f"{what}: {us} too strong for {them}"])
    elif gf == ga:
        head = f"{what}: {us} held by {them}"
    else:
        head = rng.choice([f"{what}: {them} beat {us}", f"{what} setback for {us}"])
    body = f"{line}. " + (f"Goals: {scorers}. " if scorers else "") + rng.choice(
        ["The manager used the whole squad.", "Useful minutes in the legs.", "Results don't matter in these games - fitness does.",
         "A good workout."])
    _add_article(career, local_paper(career), "friendly", head, body, club=me, date=f["date"])
    _add_post(career, us, "@" + us.replace(" ", ""), "club",
              f"{what.upper()} FT | {home_name} {r['hg']}-{r['ag']} {away_name}" + (f"  ({scorers})" if scorers else ""),
              300 + 400 * rng.random(), club=me, date=f["date"])
