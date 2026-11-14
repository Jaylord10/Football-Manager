"""
career/press.py
===============
The longer pieces in the papers, and the everyday chatter on social media (career/media.py does the rest).

NEWSPAPERS
  - MATCH REPORTS (your local paper, after every league match): several paragraphs - how the game went, the
    goals in order with their minutes, cards and injuries, the changes, both managers' words afterwards, the
    paper's man of the match, the crowd, the table and what's next.
  - PREVIEWS (your local paper): your next league match - both sides' form (last five), where they are, the
    team news (who's injured or banned), each side's danger man, and your pre-match words.
  - TALKING POINTS (The National Chronicle, each matchday from the third): the title race, the bottom, the
    goalscorers, the team in form and the team in a rut - with the numbers.
  - FEATURES (now and then): an academy prospect, a veteran, the top scorer, the club's history.
  - THE COLUMN (The Daily Roar, every couple of weeks): "Big Mick Says" - a loud opinion on something real.

SOCIAL MEDIA (every day, not just match days - career/transfers.py on_day -> day): your club's account
(training, tickets, injury news, on-this-day), fans (away trips, the pies, the kit, derby countdowns, transfer
wishes), and the wider game - a football-facts account, a groundhopper, a referee-watch account and a
"transfer insider" who is wrong more often than right.

All of it is built from what's really happening in your career (results, the table, injuries, scorers,
fixtures, the club profiles in data/world/clubs).
"""

import random

from career import league, calendar as cal

COLUMNIST = ("Big Mick Malone", "@BigMickSays")
FACTS = ("Football Facts", "@FootyFactsUK")
HOPPER = ("The Groundhopper", "@Groundhopper92")
REFWATCH = ("Ref Watch", "@RefWatchUK")
ITK = ("Transfer Insider", "@TransferITK_")
POSTS_PER_DAY = 1.3            # random everyday posts (on average)


def _media():
    from career import media
    return media


def _rng(career, salt):
    return random.Random(f"press:{salt}:{career.get('date')}:{career.get('year')}")


def _club(career, cid):
    return career["clubs"][cid]


def _nm(career, cid, short=False):
    return _media()._name(career, cid, short)


def _pl(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _player(career, cid, pid):
    from career import clubs as clubs_mod
    return clubs_mod.player_by_id(_club(career, cid), pid)


def _results_of(career, cid):
    out = []
    for md in sorted(league.results_of(career, cid), key=lambda k: int(k)):
        for r in league.results_of(career, cid)[md]:
            if cid in (r["home"], r["away"]):
                out.append(r)
    return out


def form(career, cid, n=5):
    s = ""
    for r in _results_of(career, cid)[-n:]:
        gf, ga = (r["hg"], r["ag"]) if r["home"] == cid else (r["ag"], r["hg"])
        s += "W" if gf > ga else "D" if gf == ga else "L"
    return s


def _scorers_of(career, cid):
    goals = {}
    for r in _results_of(career, cid):
        side = 0 if r["home"] == cid else 1
        for g in r.get("goals", []):
            if g.get("team") == side and not g.get("own_goal") and g.get("pid") is not None:
                goals[g["pid"]] = goals.get(g["pid"], 0) + 1
    out = []
    for pid, n in sorted(goals.items(), key=lambda x: -x[1]):
        p = _player(career, cid, pid)
        if p is not None:
            out.append((n, 0, p, _club(career, cid)))
    return out


def _quote(career, rng, who, lines):
    return f"{who} said: \"{rng.choice(lines)}\""


def _other_manager(career, cid):
    """A name for another club's manager (made up, but always the same for a club and season)."""
    from career import staff
    r = random.Random(f"mgr:{cid}:{career.get('year')}")
    return f"{r.choice(staff.FIRST)} {r.choice(staff.LAST)}"


# ---------------------------------------------------------------------------------------------------------
# The match report
# ---------------------------------------------------------------------------------------------------------
GOAL_VERBS = ["put {us} ahead", "gave {us} the lead", "opened the scoring for {us}", "broke the deadlock"]
EQUAL_VERBS = ["levelled for {us}", "drew {us} level", "equalised for {us}", "hauled {us} back on terms"]
EXTEND_VERBS = ["made it {score}", "doubled the advantage", "added another for {us}", "stretched the lead to {score}"]
PULL_VERBS = ["pulled one back for {us}", "gave {us} hope", "reduced the arrears"]
WIN_VERBS = ["won it for {us}", "settled it", "snatched it for {us}"]


def _when(minute):
    if minute <= 5:
        return "inside the first five minutes"
    if minute <= 45:
        return f"on {minute} minutes"
    if minute <= 50:
        return "just after the break"
    if minute >= 85:
        return f"with {90 - minute + 1} minute{'s' if 90 - minute + 1 != 1 else ''} left" if minute < 90 else "in stoppage time"
    return f"on {minute} minutes"


def _goal_story(career, r, rng):
    """The goals, in order, told like a reporter would."""
    goals = sorted(r.get("goals", []), key=lambda g: g.get("minute", 0))
    if not goals:
        return None
    names = (_nm(career, r["home"]), _nm(career, r["away"]))
    sc = [0, 0]
    bits = []
    final = (r["hg"], r["ag"])
    for i, g in enumerate(goals):
        side = g.get("team", 0)
        before = list(sc)
        sc[side] += 1
        us = names[side]
        who = g["name"] if not g.get("own_goal") else f"an own goal from {g['name']}"
        if g.get("own_goal"):
            us = names[side]
        last = i == len(goals) - 1
        if before[side] == before[1 - side] and last and final[side] > final[1 - side] and len(goals) > 1:
            verb = rng.choice(WIN_VERBS)
        elif before[0] == before[1] == 0:
            verb = rng.choice(GOAL_VERBS)
        elif before[side] == before[1 - side]:
            verb = rng.choice(GOAL_VERBS[:2])
        elif before[side] + 1 == before[1 - side]:
            verb = rng.choice(EQUAL_VERBS)
        elif before[side] > before[1 - side]:
            verb = rng.choice(EXTEND_VERBS)
        else:
            verb = rng.choice(PULL_VERBS)
        verb = verb.format(us=us, score=f"{max(sc)}-{min(sc)}")
        if g.get("own_goal"):
            bits.append(f"{who} {verb.replace('for ' + us, '').strip()} {_when(g.get('minute', 0))}")
        else:
            bits.append(f"{who} {verb} {_when(g.get('minute', 0))}")
    if len(bits) == 1:
        return bits[0][0].upper() + bits[0][1:] + "."
    text = "; ".join(bits[:-1]) + "; and " + bits[-1] + "."
    return text[0].upper() + text[1:]


def _incidents(career, r):
    """Red cards, injuries, bookings."""
    out = []
    reds, injured, yellows = [], [], 0
    for a in r.get("players", []):
        cid = r["home"] if a["team"] == 0 else r["away"]
        p = _player(career, cid, a["id"])
        nm = p["Name"] if p else a.get("name", "")
        if a.get("red"):
            reds.append(f"{nm} ({_nm(career, cid, True)})")
        if a.get("injury"):
            injured.append(f"{nm} ({_nm(career, cid, True)})")
        yellows += a.get("yellow", 0) or 0
    if reds:
        out.append(f"{' and '.join(reds)} {'was' if len(reds) == 1 else 'were'} sent off.")
    if injured:
        out.append(f"{' and '.join(injured)} went off injured.")
    if yellows >= 6:
        out.append(f"The referee showed {yellows} yellow cards in a bad-tempered game.")
    elif yellows:
        out.append(f"{_pl(yellows, 'booking')} in all.")
    return " ".join(out)


def _man_of_match(career, r, side):
    """The paper's pick from the side named: two goals beats one, the winner beats the rest; a clean sheet
    gives it to the keeper."""
    cid = r["home"] if side == 0 else r["away"]
    goals = {}
    for g in r.get("goals", []):
        if g.get("team") == side and not g.get("own_goal") and g.get("pid") is not None:
            goals[g["pid"]] = goals.get(g["pid"], 0) + 1
    if goals:
        pid = max(goals, key=goals.get)
        p = _player(career, cid, pid)
        if p:
            return p, (f"{goals[pid]} goals" if goals[pid] > 1 else "the goal" if sum(goals.values()) == 1 else "a goal")
    ga = r["ag"] if side == 0 else r["hg"]
    starters = [a for a in r.get("players", []) if a["team"] == side and a.get("start")]
    if ga == 0:
        for a in starters:
            p = _player(career, cid, a["id"])
            if p and p.get("Pos") == "GK":
                return p, "a clean sheet"
    rng = random.Random(f"motm:{r['home']}:{r['away']}:{r['hg']}{r['ag']}")
    ps = [_player(career, cid, a["id"]) for a in starters]
    ps = [p for p in ps if p and p.get("Pos") != "GK"]
    if ps:
        from career import clubs as clubs_mod
        p = max(ps, key=lambda q: clubs_mod.overall(q) + rng.uniform(0, 6))
        return p, "tireless all afternoon"
    return None, ""


MY_WORDS = {
    "W_big": ["That's as good as we've played. Every one of them was outstanding.",
              "I'm delighted. We were ruthless, and that's what I've been asking for.",
              "The supporters deserved that. We gave them something to sing about."],
    "W": ["Three points, that's all that matters. We dug in when we had to.",
          "Pleased. Not perfect, but we found a way, and good sides do that.",
          "The lads showed real character. I'm proud of them."],
    "D": ["A point. We'll take it and move on.", "Frustrated - we did enough to win it.",
          "Fair result, I think. Both sides had their chances."],
    "L": ["Not good enough. I take responsibility for that.", "We didn't turn up today. Simple as that.",
          "We'll look at it, learn from it, and go again on Monday."],
    "L_big": ["That was unacceptable. The supporters deserved far more.",
              "I'm not going to hide - that was a bad day, for me as much as the players."],
}
THEIR_WORDS = {
    "W": ["We knew it would be tough here. Great result for us.", "Clinical when it mattered. Very pleased."],
    "D": ["A fair point, I think.", "We'll take a point away from here."],
    "L": ["We were second best and we know it.", "Disappointing. We didn't do the basics right."],
}


def match_report(career, r):
    """The local paper's full report of your league match: (headline, body).  The headline comes from
    career/media.py; this is the body, in paragraphs."""
    m = _media()
    me = career["my_club"]
    rng = _rng(career, f"report:{r['home']}:{r['away']}")
    home, gf, ga, opp = m._for(r, me)
    us, them = _nm(career, me), _nm(career, opp)
    res = "W" if gf > ga else "D" if gf == ga else "L"
    big = abs(gf - ga) >= 3
    line = f"{_nm(career, r['home'])} {r['hg']}-{r['ag']} {_nm(career, r['away'])}"
    paras = []
    from career import clubinfo
    pr = clubinfo.profile(_club(career, r["home"]))
    ground = pr["ground"]["name"] if pr else None
    at = f" at {ground}" if ground else (" at home" if home else " away from home")
    if res == "W":
        lead = rng.choice([f"{us} beat {them} {gf}-{ga}{at}.",
                           f"{us} took all three points from {them}, winning {gf}-{ga}{at}."])
    elif res == "D":
        lead = rng.choice([f"{us} and {them} drew {gf}-{ga}{at}.",
                           f"It finished {gf}-{ga} between {us} and {them}{at}."])
    else:
        lead = rng.choice([f"{us} lost {gf}-{ga} to {them}{at}.",
                           f"{them} beat {us} {ga}-{gf}{at}."])
    poss = r.get("possession")
    if isinstance(poss, (int, float)):
        pu = round(poss if home else 100 - poss)
        lead += " " + (f"{us} had {pu}% of the ball" + (" but couldn't make it count." if pu >= 55 and res != "W"
                       else " and used it well." if pu >= 55 else " and did it the hard way." if res == "W"
                       else "."))
    paras.append(lead)
    gs = _goal_story(career, r, rng)
    paras.append(gs if gs else rng.choice(["Chances were few and far between, and neither keeper was really "
                                           "tested.", "A tight, cagey game never really caught fire."]))
    inc = _incidents(career, r)
    our = 0 if home else 1
    changes = [a for a in r.get("players", []) if a["team"] == our and not a.get("start") and a.get("minutes", 0) > 0]
    if changes:
        names = []
        for a in changes[:3]:
            p = _player(career, me, a["id"])
            if p:
                names.append(f"{p['Name'].split(' ')[-1]} ({90 - a['minutes'] + 1 if a['minutes'] < 90 else 1}')")
        if names:
            inc = (inc + " " if inc else "") + f"{us.split(' ')[0]}'s changes: {', '.join(names)}."
    if inc:
        paras.append(inc)
    key = ("W_big" if res == "W" and big else "L_big" if res == "L" and big else res)
    paras.append(_quote(career, rng, (m.manager_name(career) or 'The manager'), MY_WORDS[key]) + " "
                 + _quote(career, rng, f"{them.split(' ')[0]} manager {_other_manager(career, opp)}",
                          THEIR_WORDS[{"W": "L", "L": "W", "D": "D"}[res]]))
    p, why = _man_of_match(career, r, our)
    if p:
        paras.append(f"Our man of the match: {p['Name']} - {why}.")
    tail = []
    if r.get("att"):
        tail.append(m._crowd_line(career, r))
    tail += [m._table_line(career, me), m._next_line(career, me)]
    paras.append(" ".join(t for t in tail if t))
    return "\n\n".join(x for x in paras if x)


# ---------------------------------------------------------------------------------------------------------
# The preview
# ---------------------------------------------------------------------------------------------------------
def preview(career):
    """Your next league match, previewed in the local paper."""
    from career import availability as av
    m = _media()
    nf = league.next_fixture(career)
    if not nf:
        return
    md, h, a = nf
    me = career["my_club"]
    opp = a if h == me else h
    st = m._m(career)
    if st.get("previewed") == [career.get("year"), md]:
        return
    st["previewed"] = [career.get("year"), md]
    rng = _rng(career, f"preview:{md}")
    us, them = _nm(career, me), _nm(career, opp)
    when = league.match_date(career, md)
    paras = []
    pu, po = league.position_of(career, me), league.position_of(career, opp)
    fu, fo = form(career, me), form(career, opp)
    if fu or fo:
        paras.append(f"{us} ({m._ord(pu)}, form {fu or '-'}) {'host' if h == me else 'travel to'} {them} "
                     f"({m._ord(po)}, form {fo or '-'}) on {cal.fmt(when)}.")
    else:
        paras.append(f"{us} {'host' if h == me else 'travel to'} {them} on {cal.fmt(when)}.")
    news = []
    for cid in (me, opp):
        out = [p for p in _club(career, cid)["players"] if av.injured(p, when) or av.banned(p)]
        out.sort(key=lambda p: -p.get("Ability", 0) if isinstance(p.get("Ability"), (int, float)) else 0)
        if out:
            who = ", ".join(f"{p['Name']} ({'banned' if av.banned(p) else 'injured'})" for p in out[:3])
            news.append(f"{_nm(career, cid).split(' ')[0]} are without {who}"
                        + (f" and {len(out) - 3} more" if len(out) > 3 else "") + ".")
        else:
            news.append(f"{_nm(career, cid).split(' ')[0]} have a full squad to pick from.")
    paras.append("Team news: " + " ".join(news))
    danger = []
    for cid in (me, opp):
        sc = _scorers_of(career, cid)
        if sc:
            n, _, p, _ = sc[0]
            danger.append(f"{p['Name']} ({_pl(n, 'league goal')})")
    if len(danger) == 2:
        paras.append(f"Players to watch: {danger[0]} for {us.split(' ')[0]}, {danger[1]} for {them.split(' ')[0]}.")
    from career import clubinfo
    pr = clubinfo.profile(_club(career, me))
    derby = None
    if pr:
        derby = next((x for x in pr.get("rivals", []) if x["club"] == _club(career, opp)["name"]), None)
    if derby:
        paras.append(f"{'It is ' + derby['derby'] + '. ' if derby.get('derby') else 'A big one: '}"
                     f"{derby['why'][0].upper() + derby['why'][1:]}.")
    paras.append(_quote(career, rng, (m.manager_name(career) or 'The manager'),
                        ["We respect them, but we're going there to win." if h != me else
                         "Our supporters will be right behind us. Let's give them something.",
                         "Every game in this league is hard. We'll be ready.",
                         "The players know what's needed. Preparation's been good this week."]))
    head = rng.choice([f"Preview: {us} v {them}" if h == me else f"Preview: {them} v {us}",
                       f"{'Derby day' if derby and derby.get('derby') else 'Next up'}: {them}"])
    m._add_article(career, m.local_paper(career), "preview", head, "\n\n".join(paras), club=me)


# ---------------------------------------------------------------------------------------------------------
# Talking points - the broadsheet's look round the league
# ---------------------------------------------------------------------------------------------------------
def talking_points(career, md):
    m = _media()
    if md < 3:
        return
    t = league.table(career)
    if len(t) < 6:
        return
    rng = _rng(career, f"tp:{md}")
    paras = []
    a, b = t[0], t[1]
    gap = a["pts"] - b["pts"]
    paras.append(f"At the top, {_nm(career, a['club'])} have {a['pts']} points from {a['p']} games, "
                 + (f"level with {_nm(career, b['club'])}." if gap == 0 else
                    f"{_pl(gap, 'point')} clear of {_nm(career, b['club'])}.")
                 + f" {_nm(career, a['club'])}'s form: {form(career, a['club']) or '-'}.")
    from career import divisions
    if not (divisions.exists(career) and divisions.my_div(career) == "d1"):
        bot = t[-3:]
        safe = t[-4]
        paras.append(f"At the bottom, {', '.join(_nm(career, x['club']) for x in bot[:-1])} and "
                     f"{_nm(career, bot[-1]['club'])} are in the relegation places; "
                     f"{_nm(career, safe['club'])} sit just above them on {safe['pts']} points.")
    else:
        paras.append(f"In the race for the play-offs: {', '.join(_nm(career, x['club']) for x in t[2:6])}.")
    sc = league.top_scorers(career, None, 3)
    if sc:
        n, apps, p, club = sc[0]
        line = f"{p['Name']} of {club['name']} leads the scoring charts with {_pl(n, 'goal')} in {_pl(apps, 'game')}"
        if len(sc) > 1:
            n2, _, p2, c2 = sc[1]
            line += f"; {p2['Name']} ({c2['name']}) has {n2}"
        paras.append(line + ".")
    forms = [(x["club"], form(career, x["club"])) for x in t]
    hot = max(forms, key=lambda f: (f[1].count("W") * 3 + f[1].count("D"), rng.random()))
    cold = min(forms, key=lambda f: (f[1].count("W") * 3 + f[1].count("D"), rng.random()))
    if hot[1]:
        paras.append(f"Team in form: {_nm(career, hot[0])} ({hot[1]}). Out of form: {_nm(career, cold[0])} "
                     f"({cold[1]})" + (" - and the pressure is building on their manager, "
                                       f"{_other_manager(career, cold[0])}." if cold[1].count("L") >= 4
                                       and cold[0] != career["my_club"] else "."))
    gf = max(t, key=lambda x: x["gf"])
    ga = min(t, key=lambda x: x["ga"])
    paras.append(f"Most goals: {_nm(career, gf['club'])} ({gf['gf']}). Meanest defence: {_nm(career, ga['club'])} "
                 f"({_pl(ga['ga'], 'goal')} conceded).")
    head = rng.choice([f"Talking points after matchday {md}", "The weekend's talking points",
                       f"{_nm(career, a['club'])} lead the way: the talking points"])
    m._add_article(career, m.BROADSHEET, "talking", head, "\n\n".join(paras))


# ---------------------------------------------------------------------------------------------------------
# Features and the column
# ---------------------------------------------------------------------------------------------------------
def feature(career, md):
    """Now and then (about one matchday in four): a longer piece about someone at your club."""
    m = _media()
    rng = _rng(career, f"feature:{md}")
    if rng.random() > 0.27:
        return
    me = career["my_club"]
    club = _club(career, me)
    us = _nm(career, me)
    kinds = ["veteran", "scorer", "history"]
    if club.get("academy"):
        kinds.append("academy")
    kind = rng.choice(kinds)
    from career import clubs as clubs_mod
    if kind == "academy":
        kids = sorted(club["academy"], key=lambda p: -clubs_mod.overall(p))[:4]
        if not kids:
            return
        p = rng.choice(kids)
        from career import youth
        team = youth.NAME.get(p.get("squad"), "academy")
        g, gl = youth.stats(p, p.get("squad") or "u18")
        head = rng.choice([f"Academy watch: {p['Name']}", f"Is {p['Name'].split(' ')[0]} the next big thing?"])
        body = (f"Ask anyone at the {us} training ground about the {team} and one name keeps coming up: "
                f"{p['Name']}, a {p['Age']}-year-old {p['Pos']}.\n\n"
                + (f"He has {_pl(g, 'game')} and {_pl(gl, 'goal')} for the {team} this season. " if g else "")
                + rng.choice(["The coaches love his attitude - first in, last out.",
                              "He's quiet off the pitch and fearless on it.",
                              "Scouts from other clubs have already been asking about him."]) + "\n\n"
                + _quote(career, rng, f"Academy coach", ["He's got a chance. It's up to him now.",
                                                         "We don't put pressure on the boys, but he's special.",
                                                         "If he keeps working, the first team isn't far away."]))
    elif kind == "veteran":
        old = sorted(club["players"], key=lambda p: -p.get("Age", 0))[:3]
        if not old or old[0].get("Age", 0) < 30:
            return
        p = rng.choice(old)
        head = rng.choice([f"{p['Name']}: 'I'm not finished yet'", f"Still going strong: {p['Name']}"])
        body = (f"At {p['Age']}, {p['Name']} is one of the old heads in the {us} dressing room.\n\n"
                + _quote(career, rng, p["Name"].split(" ")[-1],
                         ["I look after myself. Ice baths, early nights - the boring stuff.",
                          "The young lads keep me sharp. I'm not handing my shirt over without a fight.",
                          "I'll know when it's time. It isn't time."]) + "\n\n"
                + rng.choice(["The manager calls him 'the best professional I've worked with'.",
                              "Team-mates say he's the first to put an arm round a struggling youngster."]))
    elif kind == "scorer":
        sc = _scorers_of(career, me)
        if not sc:
            return
        n, _, p, _ = sc[0]
        head = rng.choice([f"{p['Name']} on his {_pl(n, 'goal')}", f"Goals, goals, goals: {p['Name']}"])
        body = (f"{p['Name']} has {_pl(n, 'league goal')} for {us} this season - more than anyone else at the "
                f"club.\n\n" + _quote(career, rng, p["Name"].split(" ")[-1],
                                       ["I just try to be in the right place. The lads make it easy.",
                                        "Every striker goes through dry spells. You keep making the runs.",
                                        "I don't look at the numbers. Well - maybe a bit."]))
    else:
        from career import clubinfo
        pr = clubinfo.profile(club)
        if not pr or not pr.get("history"):
            return
        h = rng.choice(pr["history"])
        head = f"From the archive: {h['title']} ({h['years']})"
        body = h["text"] + "\n\n" + rng.choice(["Ask the older supporters and they'll tell you all about it.",
                                                "A reminder of what this club can be."])
    m._add_article(career, m.local_paper(career), "feature", head, body, club=me)


COLUMN_TOPICS = ("top", "bottom", "scorer", "spender", "manager")


def column(career, md):
    """The Daily Roar's columnist, every other matchday."""
    m = _media()
    if md < 4 or md % 2:
        return
    rng = _rng(career, f"column:{md}")
    t = league.table(career)
    topic = rng.choice(COLUMN_TOPICS)
    me = career["my_club"]
    if topic == "top":
        c = t[0]["club"]
        head = rng.choice([f"MICK: {_nm(career, c).split(' ')[0].upper()} WILL BOTTLE IT",
                           f"MICK: NOBODY STOPS {_nm(career, c).split(' ')[0].upper()} NOW"])
        body = (f"Everyone's talking about {_nm(career, c)}. Top of the league, {t[0]['pts']} points. "
                + rng.choice(["Well, I've seen it all before. Wait till the spring, when the legs go.",
                              "And do you know what? Fair play. They're the real deal."]))
    elif topic == "bottom":
        c = t[-1]["club"]
        head = f"MICK: {_nm(career, c).split(' ')[0].upper()} ARE A DISGRACE"
        body = (f"Bottom of the table on {t[-1]['pts']} points. I went to watch {_nm(career, c)} and I wanted my "
                f"money back. " + rng.choice(["Somebody at that club needs to grow a backbone.",
                                              "The players should be embarrassed. Some of them are, to be fair."]))
    elif topic == "scorer":
        sc = league.top_scorers(career, None, 1)
        if not sc:
            return
        n, _, p, club = sc[0]
        head = f"MICK: {p['Name'].split(' ')[-1].upper()} IS THE REAL DEAL"
        body = (f"{n} goals. {p['Name']} of {club['name']} is the best finisher in the country and I said so in "
                f"August. " + rng.choice(["A big club will pay silly money for him next summer.",
                                          "Put him in the national side. Now."]))
    elif topic == "spender":
        log = [e for e in career.get("transfer_log") or [] if e.get("fee")]
        if not log:
            return
        e = max(log[-40:], key=lambda e: e.get("fee", 0))
        head = f"MICK: {m._money(e['fee']).upper()}?! FOR HIM?!"
        body = (f"{e['to']} paid {m._money(e['fee'])} for {e['player']}. I've seen him play. "
                + rng.choice(["Good luck with that.", "Mind you, I said the same about a few who turned out alright."]))
    else:
        c = rng.choice([x["club"] for x in t[-6:]])
        if c == me:
            head = f"MICK: {(m.manager_name(career, short=True) or 'THE BOSS').upper()} IS RUNNING OUT OF TIME"
            body = (f"{_nm(career, c)} sit {m._ord(league.position_of(career, c))}. The manager talks a good game. "
                    + rng.choice(["Talk's cheap.", "Results, son. That's all anyone remembers."]))
        else:
            head = f"MICK: {_other_manager(career, c).split(' ')[-1].upper()} MUST GO"
            body = (f"{_nm(career, c)} are {m._ord(league.position_of(career, c))} and going nowhere. "
                    f"{_other_manager(career, c)} has had long enough.")
    m._add_article(career, m.TABLOID, "column", head, f"BIG MICK SAYS\n\n{m._named(career, body)}")
    m._add_post(career, COLUMNIST[0], COLUMNIST[1], "journo", f"New column: {head.split(': ', 1)[-1].capitalize()}",
                rng.uniform(1500, 6000))


def after_matchday(career, md, my):
    """(career/media.py after_matchday) the longer pieces."""
    preview(career)
    talking_points(career, md)
    feature(career, md)
    column(career, md)


# ---------------------------------------------------------------------------------------------------------
# Every day on social media
# ---------------------------------------------------------------------------------------------------------
def day(career, iso, rng=None):
    """0-3 everyday posts (career/transfers.py on_day)."""
    if "media" not in career:
        return
    r = random.Random(f"day:{iso}")
    n = sum(1 for _ in range(3) if r.random() < POSTS_PER_DAY / 3)
    for _ in range(n):
        try:
            r.choice(_DAILY)(career, iso, r)
        except (IndexError, KeyError, ValueError, TypeError):
            pass                                        # (a post that doesn't fit today: none)


def _club_post(career, iso, r):
    from career import availability as av
    m = _media()
    me = career["my_club"]
    acc = (_nm(career, me), "@" + _nm(career, me).replace(" ", ""))
    nf = league.next_fixture(career)
    club = _club(career, me)
    opts = []
    if nf:
        md, h, a = nf
        opp = a if h == me else h
        days = cal.days_between(iso, league.match_date(career, md))
        if 0 < days <= 6:
            opts.append(f"Training this morning. {_pl(days, 'day')} until {_nm(career, opp)}"
                        f" ({'home' if h == me else 'away'}).")
            if h == me:
                pct = r.randint(78, 99)
                opts.append(f"Tickets for {_nm(career, opp)} at home: {pct}% sold. Get yours before they go.")
    inj = [p for p in club["players"] if av.injured(p, iso)]
    if inj:
        p = r.choice(inj)
        wks = max(1, round(cal.days_between(iso, p["injury"]["until"]) / 7))
        opts.append(f"Injury update: {p['Name']} ({p['injury']['name']}) is expected back in about "
                    f"{_pl(wks, 'week')}.")
    from career import clubinfo
    pr = clubinfo.profile(club)
    if pr and pr.get("legends"):
        lg = r.choice(pr["legends"])
        opts.append(f"Club legend: {lg['name']} - {lg['role']}. {lg['note']}")
    opts.append(r.choice(["Recovery session done. Back at it tomorrow.",
                          "Behind the scenes at the training ground today.",
                          "Thank you for your support, as always."]))
    m._add_post(career, acc[0], acc[1], "club", r.choice(opts), r.uniform(800, 4000), club=me, date=iso)


def _fan_post(career, iso, r):
    m = _media()
    me = career["my_club"]
    kind, disp, handle = r.choice(m._fans(career))
    club = _club(career, me)
    from career import clubinfo
    pr = clubinfo.profile(club)
    ground = pr["ground"]["name"] if pr else "the ground"
    nf = league.next_fixture(career)
    opts = [f"£{r.choice(['4.20', '4.50', '4.80', '5.00'])} for a pie at {ground}. Daylight robbery. Still bought two.",
            "Anyone else not sleep after Saturday? Just me?", "Kit for next season better be a nice one. No gimmicks.",
            "Who's our player of the season so far? Wrong answers only.",
            "Need a striker. Have needed a striker since about 2009."]
    if nf:
        md, h, a = nf
        opp = a if h == me else h
        if h != me:
            opts.append(f"Away to {_nm(career, opp)}. Train booked, packed lunch sorted. Who's coming?")
        if pr:
            rv = next((x for x in pr.get("rivals", []) if x["club"] == _club(career, opp)["name"]), None)
            if rv:
                d = cal.days_between(iso, league.match_date(career, md))
                if 0 < d <= 10:
                    opts.append(f"{_pl(d, 'day')} until {rv.get('derby') or _nm(career, opp)}. "
                                f"Can't think about anything else.")
    best = max(club["players"], key=lambda p: p.get("Value", 0) or 0)
    opts.append(f"If anyone tries to buy {best['Name'].split(' ')[-1]} I'm chaining myself to the gates.")
    m._add_post(career, disp, handle, "fan", m._fresh(career, r, opts), r.uniform(50, 900), club=me, date=iso)


def _facts_post(career, iso, r):
    m = _media()
    t = league.table(career)
    if not t or not t[0]["p"]:
        return
    sc = league.top_scorers(career, None, 1)
    opts = [f"{_nm(career, t[0]['club'])} have scored {t[0]['gf']} league goals this season. "
            f"Only {_nm(career, min(t, key=lambda x: x['gf'])['club'])} have fewer than "
            f"{min(t, key=lambda x: x['gf'])['gf'] + 1}.",
            f"{_nm(career, min(t, key=lambda x: x['ga'])['club'])} have conceded just "
            f"{min(t, key=lambda x: x['ga'])['ga']} - the best defence in the league."]
    if sc:
        n, apps, p, club = sc[0]
        opts.append(f"{p['Name']} ({club['name']}): {n} goals in {apps} games. A goal every "
                    f"{round(apps * 90 / max(1, n))} minutes or so.")
    m._add_post(career, FACTS[0], FACTS[1], "journo", r.choice(opts), r.uniform(1000, 8000), date=iso)


def _hopper_post(career, iso, r):
    m = _media()
    from career import clubinfo
    cands = [c for c in career["clubs"] if clubinfo.profile(c)]
    if not cands:
        return
    c = r.choice(cands)
    pr = clubinfo.profile(c)
    g = pr["ground"]
    text = (f"Ground no. {r.randint(40, 92)}: {g['name']}, {c['name']}. "
            + r.choice([f"{g.get('atmosphere', 'Good noise')[0].upper()}{g.get('atmosphere', 'good noise')[1:]}.",
                        f"Capacity {g['capacity']:,}. Proper old-school feel.",
                        "Pie: 7/10. Tea: 4/10. Atmosphere: 8/10."]))
    m._add_post(career, HOPPER[0], HOPPER[1], "journo", text, r.uniform(200, 1500), club=c["id"], date=iso)


def _itk_post(career, iso, r):
    m = _media()
    clubs = career["clubs"]
    buyer = r.choice(clubs)
    seller = r.choice([c for c in clubs if c is not buyer])
    p = max(seller["players"], key=lambda q: (q.get("Value", 0) or 0) * r.uniform(0.5, 1.5))
    text = r.choice([f"EXCLUSIVE: {buyer['name']} preparing a bid for {p['Name']}. Talks advanced. Here we go soon.",
                     f"Sources tell me {p['Name']} has agreed personal terms with {buyer['name']}.",
                     f"{p['Name']} to {buyer['name']}? Watch this space."])
    m._add_post(career, ITK[0], ITK[1], "journo", text, r.uniform(300, 3000), date=iso)


def _ref_post(career, iso, r):
    m = _media()
    res = [x for md in career.get("results", {}).values() for x in md]
    if not res:
        return
    x = r.choice(res[-10:])
    text = r.choice([f"Reviewing {_nm(career, x['home'], True)} v {_nm(career, x['away'], True)}: the referee got the "
                     f"big calls right. Not a popular opinion, we know.",
                     f"{_nm(career, x['home'], True)} v {_nm(career, x['away'], True)}: clear penalty missed in the "
                     f"second half. Poor."])
    m._add_post(career, REFWATCH[0], REFWATCH[1], "journo", text, r.uniform(200, 2000), date=iso)


_DAILY = (_club_post, _club_post, _fan_post, _fan_post, _fan_post, _facts_post, _hopper_post, _itk_post, _ref_post)
