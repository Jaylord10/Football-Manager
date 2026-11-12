"""
career/dialogue.py
==================
Conversations with your players: a proper back-and-forth (3-5 exchanges).

You pick a TOPIC (how he's feeling, his form, his playing time, resting him,
his future, the dressing room / captaincy); he answers in his own words; you
pick from a few replies; he reacts... and so on until it wraps up.

What he says depends on his mood, why he feels that way, his character
(professionalism, temperament, leadership - all hidden), his age and squad
status, his form and minutes, who's keeping him out of the side, the next
opponents.  Lines he's said lately aren't repeated.

How your answers land depends on the same things: tell a man to fight for
his place when he's better than the one ahead of him and he'll feel
wronged; joke with a level-headed lad and he'll laugh, with a moody one and
he won't; a professional respects honesty...  His morale moves as you go
(you see how it's going), and some talks end in something concrete: a
promise, a rest, a word with a team-mate, a transfer request.

    start(career, club, p, topic)  -> conversation (dict)
    choose(conv, i)                -> the conversation, moved on
"""

import random
import zlib

from career import morale, clubs as clubs_mod, calendar as cal

COOLDOWN = 7
TOPICS = [
    ("feel", "How are you feeling?"),
    ("form", "Talk about his form"),
    ("minutes", "His playing time"),
    ("rest", "Rest him for the next game"),
    ("future", "His future at the club"),
    ("room", "The dressing room"),
]
BOSS = ["gaffer", "boss", "gaffer", "boss", "coach"]


# ---------------------------------------------------------------------------
# What we know going into the chat
# ---------------------------------------------------------------------------
def context(career, club, p):
    from career import captains, chats
    t = morale.traits(p)
    m = morale.level(p)
    text, v = morale.reason(p)
    why = p.get("morale_why") or {}
    reason = _reason_key(why) if text else None
    want, status = morale.expected_share(club, p)
    share = min(1.0, p.get("mins_avg", 45) / 90.0)
    lineup = club.get("lineup") or {}
    starting = p["id"] in lineup.values()
    rival, rival_slot = None, None
    if not starting:                                        # who's in his place? (the spot he'd be best in)
        spots = [s for s in lineup if (s == "GK") == (p["Pos"] == "GK")]
        rival_slot = max(spots, key=lambda s: clubs_mod.overall(p, s), default=None)
        if rival_slot:
            rival = clubs_mod.player_by_id(club, lineup[rival_slot])
    nxt = chats._next_two(career, club) if career.get("matchday", 0) <= len(career.get("fixtures", [])) else []
    goals5 = _recent_goals(career, club, p)
    form = why.get("results", 0.0) + 1.5 * why.get("goals", 0.0) + 0.6 * goals5
    return {
        "career": career, "club": club, "p": p, "name": p["Name"].split(" ")[0], "last": p["Name"].split(" ")[-1],
        "mood": m, "low": m < 45, "very_low": m < 30, "high": m >= 65,
        "reason": reason, "reason_v": v, "reason_text": text,
        "prof": t["prof"], "temp": t["temp"], "lead": captains.leadership(p), "feel": morale._feel(p),
        "age": int(p.get("Age", 25)), "young": int(p.get("Age", 25)) <= 21, "veteran": int(p.get("Age", 25)) >= 32,
        "status": status, "want": want, "share": share, "short": share < want - 0.15, "starting": starting,
        "rival": rival, "better_than_rival": rival is not None and clubs_mod.overall(p, rival_slot) > clubs_mod.overall(rival, rival_slot) + 0.5,
        "next": nxt[0] if nxt else None, "next2": nxt[1] if len(nxt) > 1 else None,
        "tired": p.get("condition", 1.0) < 0.9, "form": form, "goals5": goals5,
        "captain": club.get("captain") == p["id"], "vice": club.get("vice") == p["id"],
        "years": (p.get("contract") or {}).get("years", p.get("years", 2)),
        "wants_out": bool(p.get("wants_out")), "listed": bool(p.get("listed")),
    }


def _reason_key(why):
    """The biggest thing on his mind (as morale.reason picks it)."""
    parts = {k: why.get(k, 0.0) for k in ("results", "goals", "minutes", "talk", "promise", "captaincy")}
    return max(parts, key=lambda k: abs(parts[k]))


def _recent_goals(career, club, p):
    days = list(career.get("results", {}).values())[-5:]
    return sum(1 for day in days for m in day for g in m.get("goals", [])
               if g.get("name") == p["Name"] and not g.get("own_goal")
               and (m["home"] if g.get("team") == 0 else m["away"]) == club["id"])


# ---------------------------------------------------------------------------
# Picking his words (not the same thing twice in a row)
# ---------------------------------------------------------------------------
def _say(conv, options):
    """options: list of strings (with {placeholders}); picks one he hasn't said lately."""
    p = conv["ctx"]["p"]
    said = p.setdefault("said", [])
    fresh = [o for o in options if _key(o) not in said] or options
    line = conv["rng"].choice(fresh)
    said.append(_key(line))
    del said[:-40]
    return _fill(line, conv)


def _key(line):
    return format(zlib.crc32(line.encode()) & 0xFFFFF, "x")


def _fill(text, conv):
    c = conv["ctx"]
    rival = c["rival"]
    nxt, nxt2 = c["next"], c["next2"]
    return text.format(
        boss=conv["boss"], name=c["name"], rival=(rival["Name"].split(" ")[-1] if rival else "the lad ahead of me"),
        opp=(nxt[2] if nxt else "the next lot"), opp2=(nxt2[2] if nxt2 else "the one after"),
        club=c["club"]["name"], goals=c["goals5"], pos=c["p"]["Pos"])


def _pick(conv, *pools):
    """The first pool whose condition holds: [(cond, [lines]), ...]."""
    for cond, lines in pools:
        if cond:
            return _say(conv, lines)
    return _say(conv, pools[-1][1])


# ---------------------------------------------------------------------------
# The conversation
# ---------------------------------------------------------------------------
def can_talk(career, p):
    """(yes, why not) - once a week per man."""
    from career import chats
    return chats.can_talk(career, p)


def topics(career, club, p):
    """[(key, label, allowed, why not)] - what you can raise with him."""
    from career import chats
    out = []
    lineup = club.get("lineup") or {}
    for key, label in TOPICS:
        ok, why = True, ""
        if key == "rest":
            nxt = chats._next_two(career, club)
            if not nxt:
                ok, why = False, "No match coming up."
            elif p.get("rest_for") == nxt[0][0]:
                ok, why = False, "He's already resting for that one."
            elif p["id"] not in lineup.values():
                ok, why = False, "He's not in your XI anyway."
        out.append((key, label, ok, why))
    return out


def start(career, club, p, topic, mid=None):
    """topic: one of TOPICS, or "asked" (he asked to see you) / "request" (his transfer request) - mid: the inbox message."""
    rng = random.Random(f"chat:{p['id']}:{career['date']}:{topic}:{len(p.get('said', []))}")
    conv = {"topic": topic, "mid": mid, "log": [], "choices": [], "done": False, "delta": 0.0, "warmth": 0,
            "rng": rng, "boss": rng.choice(BOSS), "ctx": context(career, club, p), "stage": None, "outcome": [], "replies": 0}
    opener = {"rest": f"I'm going to rest you against {_fill('{opp}', conv)}.", "asked": "You wanted to see me?",
              "request": "I've seen your transfer request. Sit down."}.get(topic) or dict(TOPICS)[topic]
    _you(conv, opener)
    STAGES[topic + "_open"](conv)
    return conv


def choose(conv, i):
    """You pick reply i."""
    label, fn = conv["choices"][i]
    conv["choices"] = []
    conv["replies"] += 1
    _you(conv, label)
    fn(conv)
    if conv["done"]:
        _finish(conv)
    return conv


def _you(conv, text):
    conv["log"].append(("you", text))


def _him(conv, text):
    conv["log"].append(("him", text))


def _offer(conv, *choices):
    """choices: (label, function) - shown as your replies."""
    conv["choices"] = [(_fill(l, conv), f) for l, f in choices if l]


def _mood(conv, d):
    """His morale moves (a bad moment counts for more with a sensitive man)."""
    if d < 0:
        d *= conv["ctx"]["feel"]
    conv["delta"] += d
    conv["warmth"] += 1 if d > 0.4 else -1 if d < -0.4 else 0
    if conv["warmth"] <= -2 or conv["delta"] <= -4:
        conv["cold"] = True                                 # (he's in no mood for small talk now)
    p = conv["ctx"]["p"]
    p["morale"] = round(max(3.0, min(98.0, morale.level(p) + d)), 1)


def _end(conv, text=None):
    if text:
        _him(conv, text)
    conv["done"] = True
    conv["choices"] = []


def _close(conv):
    """Wrapping up: if it's been short, you can move on to something else first; then his last word."""
    if conv["replies"] < 3 and not conv.get("segued") and not conv.get("cold"):
        conv["segued"] = True
        c = conv["ctx"]
        if conv["log"][-1][0] == "you":                    # (he answers you first)
            w = conv["warmth"]
            _him(conv, _pick(conv, (w >= 1, ["Cheers, {boss}.", "Thanks, {boss}.", "Will do.", "Appreciate it."]),
                             (w <= -1, ["Mm.", "Right.", "If you say so."]),
                             (True, ["Okay.", "Yeah.", "Sure, {boss}."])))
        new = c["p"].get("joined") and cal.days_between(c["p"]["joined"], c["career"]["date"]) < 120
        _offer(conv,
               ("Anyway - {opp} next. Are you ready?" if c["next"] else None, match_talk),
               ("How are you settling in?" if new else "How's life away from football?", life_talk),
               ("That's all. Off you go.", _goodbye))
        return
    _goodbye(conv)


def _goodbye(conv):
    """His last word, by how it's gone (unless he's just had it)."""
    if conv["log"] and conv["log"][-1][0] == "him":
        return _end(conv)
    w = conv["warmth"]
    _end(conv, _pick(conv,
        (w >= 2, ["Cheers, {boss}. Good chat.", "Thanks {boss} - I feel better for that.", "Appreciate it, {boss}. I won't let you down.",
                  "Nice one. I'll get back out there.", "Good talk, {boss}. Means a lot."]),
        (w <= -2, ["Right. Are we done?", "Fine. Whatever you say.", "...I'll see you at training.", "Got it.", "Yeah. Okay."]),
        (True, ["Alright, {boss}.", "Okay. Thanks.", "Fair enough.", "Understood.", "Sound, {boss}."])))


def _finish(conv):
    c = conv["ctx"]
    p = c["p"]
    p["last_chat"] = c["career"]["date"]
    if conv["topic"] in ("feel", "minutes", "form", "future", "asked", "request"):   # (his player screen: "He told you...")
        p["told"] = {"text": c["reason_text"] or "nothing in particular on his mind", "date": c["career"]["date"]}
    why = p.setdefault("morale_why", {})
    why["talk"] = round(0.5 * why.get("talk", 0.0) + conv["delta"], 2)
    if abs(conv["delta"]) >= 2:
        p["revealed"] = p.get("revealed", 0) + 1


# ---------------------------------------------------------------------------
# HOW ARE YOU FEELING?
# ---------------------------------------------------------------------------
def feel_open(conv):
    c = conv["ctx"]
    r = c["reason"]
    if r == "minutes" and c["reason_v"] < 0:
        _him(conv, _pick(conv, (c["temp"] >= 14, [
            "Honestly? Fed up. I'm busting a gut in training and getting nothing for it.",
            "Not great, {boss}. Sitting on that bench is doing my head in.",
            "You really want to know? I'm sick of watching from the stands."]),
            (True, ["Bit frustrated, if I'm honest. I want to be playing.",
                    "I'm okay... but I'm not getting the minutes I want, {boss}.",
                    "I feel sharp, I just need games.",
                    "Hard, to be honest. Every week I look at the teamsheet and I'm not on it."])))
        _offer(conv, ("Your chance will come. Keep working.", feel_wait),
               ("What do you think you're doing better than {rival}?", feel_rival),
               ("It's a squad game - everyone plays their part.", feel_squad),
               ("Would you go out on loan to get games?" if c["age"] <= 23 else None, feel_loan))
    elif r == "results" and c["reason_v"] < 0:
        _him(conv, _pick(conv, (c["lead"] >= 14, [
            "Worried about the lads. Heads are dropping in there.",
            "We're better than this, {boss}. Someone needs to stand up.",
            "I'm alright. It's the group I'm worried about."]),
            (True, ["Not brilliant. These results are getting to everyone.",
                    "Down, to be honest. Losing's horrible.",
                    "It's tough right now, {boss}. Can't seem to buy a win.",
                    "Gutted. You go home after games like that and it eats you."])))
        _offer(conv, ("We're too good to stay down there. It'll turn.", feel_reassure),
               ("I need you to lead by example.", feel_lead),
               ("Are the lads still behind me?", feel_behind),
               ("Cheer up - could be worse. You could be the kit man.", feel_joke))
    elif c["high"] or (r in ("goals", "results", "minutes") and c["reason_v"] > 0):
        _him(conv, _pick(conv, (c["goals5"] >= 2, [
            "Buzzing, {boss}. {goals} in the last few - I want more.",
            "Can't stop scoring, can I? Long may it last.",
            "Great. When they're going in, football's easy."]),
            (True, ["Really good, {boss}. Enjoying it.", "Never better.", "Happy. Training's sharp, the lads are flying.",
                    "Good, thanks for asking. Feeling fit and strong.", "Loving it here, {boss}."])))
        _offer(conv, ("Keep it up - you're flying.", feel_praise),
               ("Don't get carried away.", feel_grounded),
               ("Who's impressed you in training lately?", feel_who),
               ("Glad to hear it. Anything you need from me?", feel_need))
    else:
        _him(conv, _say(conv, ["Fine, {boss}. Can't complain.", "Alright. Same old.", "Not bad. Ticking along.",
                               "Okay, I think. Why, have I done something?", "Good, yeah. Body feels decent."]))
        _offer(conv, ("Anything on your mind?", feel_anything),
               ("Good. Keep your head down and keep working.", feel_headdown),
               ("I want more from you this season.", feel_more))


def feel_wait(conv):
    c = conv["ctx"]
    if c["share"] < 0.15 and c["want"] >= 0.6:
        _mood(conv, -1.5)
        _him(conv, _say(conv, ["I've heard that before, {boss}. When?", "With respect, that's what you said last month.",
                               "Coming when, though?"]))
        _offer(conv, ("You'll get games - I promise.", feel_promise_start),
               ("When you're better than {rival}.", feel_blunt),
               ("Soon. I mean it.", feel_soon))
    else:
        _mood(conv, 2.0 if c["prof"] >= 12 else 1.0)
        _him(conv, _say(conv, ["Okay. I'll keep my head down.", "I'll be ready when you need me.", "Fair enough, {boss}. I'll keep pushing.",
                               "Right. I'll make it hard for you to leave me out."]))
        _offer(conv, ("That's the attitude.", lambda cv: (_mood(cv, 1.0), _close(cv))),
               ("Show me in training this week.", lambda cv: (_mood(cv, 0.5), _close(cv))))


def feel_rival(conv):
    c = conv["ctx"]
    if c["better_than_rival"]:
        _mood(conv, 0.5)
        _him(conv, _say(conv, ["Honestly? Everything. Look at the numbers - I'm quicker, sharper, I've got more in my locker than {rival}.",
                               "I'm better than him, {boss}. You know it, the lads know it.",
                               "You've seen training. Who's sharper - me or {rival}?"]))
        _offer(conv, ("You're right. You'll get games - I promise.", feel_promise_start),
               ("Maybe - but he's earned his spot. Earn it back.", feel_earn),
               ("No, he's ahead of you. That's my call.", feel_blunt))
    else:
        if c["prof"] >= 12:
            _mood(conv, 1.0)
            _him(conv, _say(conv, ["...Fair question. He's playing well. I need to be better.",
                                   "If I'm honest, he's in form. But I'm close.",
                                   "Not much right now. I'll work on it."]))
            _offer(conv, ("That's honest. Keep at it and you'll get your chance.", lambda cv: (_mood(cv, 1.5), _close(cv))),
                   ("Tell you what - keep pushing in training and we'll see.", lambda cv: (_mood(cv, 0.5), _close(cv))))
        else:
            _mood(conv, -1.0)
            _him(conv, _say(conv, ["I don't know, I just think I deserve a go.", "Why does it matter? I want to play.",
                                   "Everything. He's not that good."]))
            _offer(conv, ("He's ahead of you, and the numbers say so.", feel_blunt),
                   ("Then show me. Training, every day.", lambda cv: (_mood(cv, 0.5), _close(cv))))


def feel_squad(conv):
    c = conv["ctx"]
    if c["young"] or c["prof"] >= 13:
        _mood(conv, 1.5)
        _him(conv, _say(conv, ["Yeah, I get it. I'll be ready.", "Fair. I just want to help the team.", "Okay, {boss}. Understood."]))
        _offer(conv, ("Good lad.", lambda cv: (_mood(cv, 0.5), _close(cv))),
               ("You'll get minutes in the cup games.", lambda cv: (_mood(cv, 1.0), _close(cv))))
    elif c["temp"] >= 13:
        _mood(conv, -2.5)
        _him(conv, _say(conv, ["Don't give me that. I didn't come here to make up the numbers.",
                               "Squad game? I'm not a squad player, {boss}.", "That's a cop-out and you know it."]))
        _offer(conv, ("Watch your tone.", feel_tone),
               ("Okay - you're right, you deserve better. I'll look at it.", lambda cv: (_mood(cv, 2.0), _close(cv))),
               ("Then maybe this isn't the club for you.", feel_door))
    else:
        _mood(conv, -0.5)
        _him(conv, _say(conv, ["I suppose.", "Yeah... I guess.", "If you say so, {boss}."]))
        _close(conv)


def feel_loan(conv):
    c = conv["ctx"]
    keen = c["young"] and (c["share"] < 0.3)
    if keen:
        _mood(conv, 2.0)
        _him(conv, _say(conv, ["Actually... yeah. I'd rather play every week somewhere than sit here.",
                               "If it's the right club, I'd go. I need games.", "Honestly, I've been thinking the same."]))
        conv["outcome"].append("He'd welcome a loan move - you can put him on the loan list from his screen.")
        c["p"]["loan_wish"] = c["career"]["date"]
        _offer(conv, ("Leave it with me.", lambda cv: (_mood(cv, 0.5), _close(cv))))
    else:
        _mood(conv, -1.0 if c["temp"] >= 12 else 0.0)
        _him(conv, _say(conv, ["No. I want to fight for my place here.", "I'd rather stay, {boss}.",
                               "Are you trying to get rid of me?"]))
        _offer(conv, ("No - just options. Stay and fight then.", lambda cv: (_mood(cv, 1.0), _close(cv))),
               ("Think about it.", lambda cv: (_mood(cv, -0.5), _close(cv))))


def feel_promise_start(conv):
    c = conv["ctx"]
    p = c["p"]
    if p.get("promise"):                                    # (you've already promised)
        _mood(conv, -1.0)
        _him(conv, _say(conv, ["You said that already, {boss}. I'm still waiting.", "That's what you told me last time.",
                               "I'll believe it when I see my name on the teamsheet."]))
        _offer(conv, ("And I meant it. Be patient.", lambda cv: (_mood(cv, 0.5), _close(cv))))
        return
    _mood(conv, 4.0)
    p["promise"] = {"made": c["career"]["date"],
                    "check": (cal.parse(c["career"]["date"]) + _days(35)).isoformat(), "share": min(0.9, max(c["want"], 0.5))}
    conv["outcome"].append("You promised him games - the game will check in five weeks.")
    _him(conv, _say(conv, ["Get in. I won't let you down, {boss}.", "That's all I wanted to hear.",
                           "You'll not regret it.", "Brilliant. I'll be ready."]))
    _offer(conv, ("Make sure you take it.", lambda cv: (_close(cv))))


def feel_blunt(conv):
    c = conv["ctx"]
    if c["prof"] >= 13 and c["temp"] < 12:
        _mood(conv, 0.0)
        _him(conv, _say(conv, ["Okay. I respect you being straight with me.", "Hard to hear. But fair enough.",
                               "Right. Then I'll have to be better than him."]))
        _close(conv)
    else:
        _mood(conv, -3.5)
        _him(conv, _say(conv, ["Wow. Okay.", "That's how it is, is it?", "Then why did you sign me?",
                               "You've never given me a proper chance."]))
        if c["temp"] >= 14 and c["very_low"]:
            _offer(conv, ("Fight for it then.", feel_door_slammed),
                   ("Look - I didn't mean it like that.", lambda cv: (_mood(cv, 1.5), _close(cv))))
        else:
            _close(conv)


def feel_door_slammed(conv):
    from career import chats
    c = conv["ctx"]
    _mood(conv, -2.0)
    chats._transfer_request(c["career"], c["p"])
    conv["outcome"].append("He's handed in a transfer request.")
    _end(conv, _say(conv, ["No. I want out. I'll put it in writing.", "I'm done here, {boss}. Find me a club.",
                           "Then I'm off. You'll have my request in the morning."]))


def feel_earn(conv):
    c = conv["ctx"]
    _mood(conv, 1.0 if c["prof"] >= 11 else -1.5)
    _him(conv, _say(conv, ["Fine. I'll earn it.", "Right. Watch this space.", "...Okay."] if c["prof"] >= 11 else
                    ["I've earned it ten times over.", "Unbelievable.", "Whatever."]))
    _close(conv)


def feel_soon(conv):
    _mood(conv, 0.5)
    _him(conv, _say(conv, ["I'll hold you to that.", "Okay. Soon.", "Right. I'll be ready."]))
    _close(conv)


def feel_tone(conv):
    c = conv["ctx"]
    if c["prof"] >= 10:
        _mood(conv, 0.0)
        _him(conv, _say(conv, ["...Sorry, {boss}. It's just frustrating.", "Fair. I'm out of order. But I mean it.",
                               "Sorry. I just want to play."]))
        _offer(conv, ("I know. Keep working and it'll come.", lambda cv: (_mood(cv, 1.5), _close(cv))),
               ("Apology accepted.", lambda cv: (_mood(cv, 0.5), _close(cv))))
    else:
        _mood(conv, -2.0)
        _him(conv, _say(conv, ["My tone? You're the one wasting me.", "Don't talk to me like a kid.", "Whatever."]))
        _offer(conv, ("We're done here.", lambda cv: (_mood(cv, -1.0), _close(cv))),
               ("Look - let's both calm down.", lambda cv: (_mood(cv, 1.0), _close(cv))))


def feel_door(conv):
    c = conv["ctx"]
    _mood(conv, -3.0)
    if c["temp"] >= 12:
        conv["outcome"].append("He's handed in a transfer request.")
        from career import chats
        chats._transfer_request(c["career"], c["p"])
        _end(conv, _say(conv, ["Fine. Then sell me.", "Maybe it isn't. I'll speak to my agent.", "Right. I'm off then."]))
    else:
        _him(conv, _say(conv, ["...Is that what you want?", "Wow. Okay.", "I didn't say that."]))
        _offer(conv, ("No. I want you fighting for your place here.", lambda cv: (_mood(cv, 2.0), _close(cv))),
               ("Think about it.", lambda cv: (_mood(cv, -1.0), _close(cv))))


def feel_reassure(conv):
    c = conv["ctx"]
    _mood(conv, 2.0 if c["prof"] >= 9 else 1.0)
    _him(conv, _say(conv, ["Yeah. We've got the players.", "Hope so, {boss}. I believe in this group.",
                           "One win and it all changes.", "We just need a bit of luck."]))
    _offer(conv, ("We make our own luck. Hard work.", lambda cv: (_mood(cv, 0.5), _close(cv))),
           ("Exactly. {opp} next - let's start there.", lambda cv: (_mood(cv, 1.0), _close(cv))))


def feel_lead(conv):
    c = conv["ctx"]
    if c["lead"] >= 13:
        _mood(conv, 3.0)
        _him(conv, _say(conv, ["I will. I'll get the lads together.", "Leave it with me, {boss}.",
                               "I've been waiting for someone to say that."]))
        if _rally(conv, 0.8):
            conv["outcome"].append("He'll rally the dressing room - the squad's a little happier.")
        _offer(conv, ("That's why I came to you.", lambda cv: (_mood(cv, 0.5), _close(cv))))
    else:
        _mood(conv, -1.0)
        _him(conv, _say(conv, ["Me? I'm not really the shouting type.", "I'll try, but that's not me, {boss}.",
                               "I just do my job. I'm not a captain."]))
        _offer(conv, ("Then lead by how you play.", lambda cv: (_mood(cv, 1.0), _close(cv))),
               ("Fair enough. Just keep going.", lambda cv: (_close(cv))))


RALLY_GAP = 14          # days: a rallying word only works so often


def _rally(conv, d):
    """A leader has a word with the lads: everyone a touch happier (once a fortnight - it wears thin)."""
    c = conv["ctx"]
    club, today = c["club"], c["career"]["date"]
    last = club.get("rallied")
    if last and cal.days_between(last, today) < RALLY_GAP:
        conv["outcome"].append("The lads only had a rallying talk recently - it won't add much.")
        return False
    club["rallied"] = today
    for q in club["players"]:
        if q is not c["p"]:
            q["morale"] = round(max(3.0, min(98.0, morale.level(q) + d)), 1)
    return True


def feel_behind(conv):
    c = conv["ctx"]
    avg = sum(morale.level(q) for q in c["club"]["players"]) / max(1, len(c["club"]["players"]))
    if avg >= 55:
        _mood(conv, 1.0)
        _him(conv, _say(conv, ["Course we are. Nobody's hiding.", "100%, {boss}. We know it's on us.",
                               "The lads are with you. It's just not clicking."]))
    elif avg >= 42:
        _mood(conv, 0.0)
        _him(conv, _say(conv, ["Mostly. A few are grumbling.", "Most of them. Some need an arm round them.",
                               "It's a mixed bag, honestly."]))
    else:
        _mood(conv, -0.5)
        _him(conv, _say(conv, ["Honestly? It's tough in there right now.", "I won't lie to you - it's not great.",
                               "Some of them have stopped believing, {boss}."]))
    worst = min((q for q in c["club"]["players"] if q is not c["p"]), key=morale.level, default=None)
    if worst is not None and morale.level(worst) < 40:
        conv["outcome"].append(f"He mentioned {worst['Name']} is struggling.")
        _him(conv, _say(conv, [f"{worst['Name'].split(' ')[-1]} is really down. Might be worth a word.",
                               f"Keep an eye on {worst['Name'].split(' ')[-1]}. He's not himself."]))
    _offer(conv, ("Thanks for being honest.", lambda cv: (_mood(cv, 1.0), _close(cv))),
           ("Keep that between us.", lambda cv: (_mood(cv, 0.5), _close(cv))))


def feel_joke(conv):
    c = conv["ctx"]
    if c["temp"] <= 9 or c["high"]:
        _mood(conv, 2.0)
        _him(conv, _say(conv, ["Ha! Might have to. Cheers {boss}, needed that.", "Ha - that's the best idea anyone's had all week.",
                               "*laughs* Okay, okay. Point taken - stop moping."]))
        _offer(conv, ("Seriously though - chin up. We'll be fine.", lambda cv: (_mood(cv, 1.0), _close(cv))))
    else:
        _mood(conv, -2.0)
        _him(conv, _say(conv, ["Is this a joke to you?", "...Not really in the mood, {boss}.", "Funny. Really funny."]))
        _offer(conv, ("Sorry - bad moment. I hear you.", lambda cv: (_mood(cv, 1.0), _close(cv))),
               ("Lighten up.", lambda cv: (_mood(cv, -1.5), _close(cv))))


def feel_praise(conv):
    _mood(conv, 1.5)
    _him(conv, _say(conv, ["Cheers, {boss}.", "Thanks. Confidence is everything.", "Means a lot coming from you."]))
    _offer(conv, ("Keep your feet on the ground, mind.", lambda cv: (_close(cv))),
           ("Next stop: {opp}. Go and do it again.", lambda cv: (_mood(cv, 0.5), _close(cv))))


def feel_grounded(conv):
    c = conv["ctx"]
    if c["prof"] >= 12:
        _mood(conv, 0.5)
        _him(conv, _say(conv, ["Never. Next game's all that matters.", "Don't worry, {boss}. Head's screwed on.", "Course not."]))
    else:
        _mood(conv, -1.5)
        _him(conv, _say(conv, ["Can't I enjoy it for five minutes?", "Who's getting carried away?", "Bit harsh, {boss}."]))
    _close(conv)


def feel_who(conv):
    c = conv["ctx"]
    kids = sorted((q for q in c["club"]["players"] if q is not c["p"] and int(q.get("Age", 25)) <= 21),
                  key=lambda q: -float(q.get("Potential", 0) or 0))
    _mood(conv, 0.5)
    if kids:
        k = kids[0]
        conv["outcome"].append(f"He rates young {k['Name']}.")
        _him(conv, _say(conv, [f"{k['Name'].split(' ')[-1]}. The kid's got something - he'll be some player.",
                               f"Young {k['Name'].split(' ')[-1]}. Keeps nutmegging me. Annoying, but he's good.",
                               f"Honestly? {k['Name'].split(' ')[-1]}. Give him a chance and see."]))
    else:
        _him(conv, _say(conv, ["The whole group's flying, to be fair.", "Hard to pick one. Everyone's sharp."]))
    _offer(conv, ("Interesting. I'll keep an eye on him.", lambda cv: (_close(cv))),
           ("Look after him out there.", lambda cv: (_mood(cv, 0.5), _close(cv))))


def feel_need(conv):
    c = conv["ctx"]
    _mood(conv, 1.0)
    if c["tired"]:
        _him(conv, _say(conv, ["Maybe a breather at some point - legs are heavy.", "Honestly, a rest wouldn't hurt."]))
    elif not c["starting"]:
        _him(conv, _say(conv, ["Just a run in the team, {boss}.", "Minutes. That's all."]))
    else:
        _him(conv, _say(conv, ["Nothing, {boss}. All good.", "Just keep picking me!", "A new contract wouldn't hurt... joking. Mostly."]))
    _close(conv)


def feel_anything(conv):
    c = conv["ctx"]
    if c["short"]:
        _mood(conv, 0.5)
        _him(conv, _say(conv, ["Since you ask... I'd like more minutes.", "I want to be playing more, {boss}."]))
        _offer(conv, ("I'll bear it in mind.", lambda cv: (_mood(cv, 0.5), _close(cv))),
               ("Keep training like you are and it'll come.", feel_wait))
    else:
        _mood(conv, 0.5)
        _him(conv, _say(conv, ["Not really. Just want to keep winning.", "All good. The new pre-match meal's grim though.",
                               "Nothing worth bothering you with."]))
        _close(conv)


def feel_headdown(conv):
    _mood(conv, 0.5 if conv["ctx"]["prof"] >= 10 else 0.0)
    _him(conv, _say(conv, ["Will do.", "Always.", "Yes, {boss}."]))
    _close(conv)


def feel_more(conv):
    c = conv["ctx"]
    if c["form"] > 0.8:
        _mood(conv, -2.5)
        _him(conv, _say(conv, ["More? I've been one of our best.", "What else do you want me to do?", "That's a bit much, {boss}."]))
        _offer(conv, ("You're right - you've been good. I just know there's more.", lambda cv: (_mood(cv, 2.0), _close(cv))),
               ("I set the standards here.", lambda cv: (_mood(cv, -1.0), _close(cv))))
    elif c["prof"] >= 12:
        _mood(conv, 2.0)
        _him(conv, _say(conv, ["Fair. I know I can do better.", "Good. I want more from myself too.", "I'll give it to you."]))
        _close(conv)
    else:
        _mood(conv, -1.0)
        _him(conv, _say(conv, ["Right.", "Okay...", "Noted."]))
        _close(conv)


# ---------------------------------------------------------------------------
# HIS FORM
# ---------------------------------------------------------------------------
def form_open(conv):
    c = conv["ctx"]
    _him(conv, _pick(conv,
        (c["form"] > 1.0, ["I'm flying, {boss}. Best I've felt in ages.", "Everything I hit is going in!",
                           "Feeling good. Confidence is high.", "Can't complain - the lads are making it easy."]),
        (c["form"] < -0.8, ["It's not going for me right now.", "I know. I've been poor.", "Can't seem to get going, {boss}.",
                            "Bit of a rough patch, to be honest."]),
        (True, ["Steady, I think. Could be better, could be worse.", "Okay. Not my best, not my worst.",
                "I'm doing my job. Want to do more."])))
    _offer(conv, ("You've been excellent.", form_praise), ("I expect more from you.", form_more),
           ("How do you think you're playing?", form_ask))


def form_praise(conv):
    c = conv["ctx"]
    if c["form"] > 0.5:
        _mood(conv, 3.0)
        _him(conv, _say(conv, ["Cheers {boss} - I'm loving it.", "Thanks. It's easy when the team's playing like this.",
                               "Appreciate that. Means a lot."]))
        _offer(conv, ("I want more goals from you, though.", form_want_goals),
               ("Keep doing exactly that.", lambda cv: (_mood(cv, 0.5), _close(cv))),
               ("You could be a leader in this team." if c["lead"] >= 12 and not c["captain"] else None, form_leader))
    elif c["prof"] >= 12:
        _mood(conv, -1.5)
        _him(conv, _say(conv, ["With respect, I know I haven't. Don't sugar-coat it.", "Come on, {boss}. You've seen the games.",
                               "That's kind, but it's not true."]))
        _offer(conv, ("Fair. You've not been at your best.", form_admit),
               ("I mean it - you're doing the dirty work.", lambda cv: (_mood(cv, 0.5), _close(cv))),
               ("Anything I can help with?", form_help))
    else:
        _mood(conv, 1.0)
        _him(conv, _say(conv, ["Thanks, {boss}. Nice to hear.", "Yeah? Cheers.", "Good to know you rate me."]))
        _close(conv)


def form_more(conv):
    c = conv["ctx"]
    if c["form"] > 0.5:
        _mood(conv, -3.5)
        _him(conv, _say(conv, ["What more do you want? I've been one of the best out there.", "Are you watching the same games as me?",
                               "Unbelievable. Look at the numbers, {boss}."]))
        _offer(conv, ("You're right - I was harsh.", lambda cv: (_mood(cv, 2.0), _close(cv))),
               ("Good isn't good enough here.", form_double_down),
               ("I know there's more in you. That's a compliment.", lambda cv: (_mood(cv, 1.5 if cv["ctx"]["prof"] >= 11 else 0.0), _close(cv))))
    elif c["prof"] >= 12 and c["temp"] < 13:
        _mood(conv, 3.0)
        _him(conv, _say(conv, ["You're right. I'll show you in training this week.", "I know. I expect more from myself.",
                               "Message received, {boss}."]))
        _offer(conv, ("That's what I want to hear.", lambda cv: (_mood(cv, 0.5), _close(cv))),
               ("Anything getting in the way?", form_help))
    elif c["temp"] >= 13:
        _mood(conv, -4.0)
        _him(conv, _say(conv, ["I've been doing my job. Look at the others before you look at me.", "Don't pin this on me.",
                               "Typical. Blame the player."]))
        _offer(conv, ("I'm not blaming you - I'm backing you to be better.", lambda cv: (_mood(cv, 2.0), _close(cv))),
               ("I'll pin it where I like.", form_double_down))
    else:
        _mood(conv, 0.5)
        _him(conv, _say(conv, ["Fair enough, {boss}.", "Okay. I'll work on it.", "Understood."]))
        _close(conv)


def form_ask(conv):
    c = conv["ctx"]
    honest = c["prof"] >= 11
    if c["form"] < -0.5 and not honest:
        _him(conv, _say(conv, ["Fine, I think. It's the system that's not suiting me.", "Good! It's the others letting me down.",
                               "I'm playing well. Nobody's giving me the ball."]))
        _offer(conv, ("Hmm. The numbers say otherwise.", lambda cv: (_mood(cv, -1.5), _close(cv))),
               ("What would suit you better?", form_help))
    else:
        _mood(conv, 1.0)
        _him(conv, _say(conv, ["Honestly? " + ("Really well." if c["form"] > 0.5 else "Not well enough." if c["form"] < -0.5 else "Okay. Room to improve."),
                               "I'd give myself " + ("an eight" if c["form"] > 0.5 else "a five" if c["form"] < -0.5 else "a six and a half") + ", {boss}."]))
        _offer(conv, ("Agreed.", lambda cv: (_mood(cv, 1.0), _close(cv))),
               ("Harsh on yourself." if c["form"] > -0.5 else "Fair assessment.", lambda cv: (_mood(cv, 1.0), _close(cv))),
               ("Anything I can do to help?", form_help))


def form_want_goals(conv):
    c = conv["ctx"]
    _mood(conv, 1.0 if c["prof"] >= 10 else -0.5)
    _him(conv, _say(conv, ["Me too. I'll get there.", "Get me the ball in the box and I will.", "Working on it every day, {boss}."]))
    _close(conv)


def form_leader(conv):
    _mood(conv, 2.5)
    _him(conv, _say(conv, ["Really? I'd love that.", "I'm ready for that, {boss}.", "That means a lot. I won't let you down."]))
    conv["outcome"].append("He'd relish more responsibility - think about the armband.")
    _close(conv)


def form_admit(conv):
    c = conv["ctx"]
    _mood(conv, 2.0 if c["prof"] >= 12 else 0.0)
    _him(conv, _say(conv, ["Thank you. I'd rather you tell me straight.", "I know. I'll put it right.", "Appreciate the honesty."]))
    _offer(conv, ("Work on it and you'll be back.", lambda cv: (_mood(cv, 1.0), _close(cv))),
           ("Anything getting in the way?", form_help))


def form_help(conv):
    c = conv["ctx"]
    if c["tired"]:
        _him(conv, _say(conv, ["Honestly, I'm knackered. Legs are gone.", "I need a breather, {boss}."]))
        _offer(conv, ("Then you're resting against {opp}.", rest_from_form),
               ("Push through - we need you.", lambda cv: (_mood(cv, -1.0), _close(cv))))
    elif not c["starting"]:
        _him(conv, _say(conv, ["Rhythm. I need a run of games.", "It's hard to find form off the bench."]))
        _offer(conv, ("You'll get a run of games - I promise.", feel_promise_start), ("Take your chances when they come.", lambda cv: (_close(cv))))
    else:
        _him(conv, _say(conv, ["Just a bit of confidence. One good game.", "Probably mental. Overthinking it.",
                               "Keep picking me and it'll come."]))
        _offer(conv, ("You're starting against {opp}. Go and enjoy it.", lambda cv: (_mood(cv, 2.0), _close(cv))),
               ("Stop overthinking. Play.", lambda cv: (_mood(cv, 1.0), _close(cv))))


def form_double_down(conv):
    c = conv["ctx"]
    if c["prof"] >= 14:
        _mood(conv, 0.5)
        _him(conv, _say(conv, ["...Fine. I'll show you.", "Okay. Challenge accepted.", "Right."]))
        _close(conv)
    else:
        _mood(conv, -2.0)
        _him(conv, _say(conv, ["Whatever.", "You'll see.", "Unreal."]))
        _close(conv)


# ---------------------------------------------------------------------------
# PLAYING TIME
# ---------------------------------------------------------------------------
def minutes_open(conv):
    c = conv["ctx"]
    if c["short"]:
        _him(conv, _pick(conv,
            (c["temp"] >= 13, ["About time we talked about this. I'm not playing.", "I want to know why I'm not in the team.",
                               "Finally. I've been waiting for this chat."]),
            (True, ["I'd like more games, {boss}. Simple as that.", "I'm ready. I just need the chance.",
                    "I'm not getting the minutes I thought I would."])))
        _offer(conv, ("You'll get games - I promise.", feel_promise_start),
               ("Fight for your place.", minutes_fight),
               ("{rival} is ahead of you at the moment.", minutes_rival),
               ("Would a loan help?" if c["age"] <= 23 else "If you want to leave, we'd listen to offers.", feel_loan if c["age"] <= 23 else minutes_listen))
    else:
        _him(conv, _say(conv, ["I'm happy with my minutes, {boss}.", "No complaints - I'm playing.", "All good. Just keep picking me!"]))
        _offer(conv, ("Good. Keep earning them.", lambda cv: (_mood(cv, 1.0), _close(cv))),
               ("You might be rested a bit more soon.", minutes_warn))


def minutes_fight(conv):
    c = conv["ctx"]
    if c["better_than_rival"]:
        _mood(conv, -3.0)
        _him(conv, _say(conv, ["I am fighting. I'm better than {rival} and you know it.", "Fight how? I'm doing everything right.",
                               "What more can I do, {boss}?"]))
        _offer(conv, ("You're right. You'll get your games - I promise.", feel_promise_start),
               ("Keep fighting.", lambda cv: (_mood(cv, -1.0), _close(cv))),
               ("Then maybe this isn't the club for you.", feel_door))
    elif c["prof"] >= 12 and c["temp"] < 13:
        _mood(conv, 2.0)
        _him(conv, _say(conv, ["Fair enough. I'll show you.", "I will. Watch me.", "Okay. I'll make it impossible to drop me."]))
        _close(conv)
    else:
        _mood(conv, -2.0)
        _him(conv, _say(conv, ["That's it? That's all you've got?", "I've been fighting for months.", "Right."]))
        _offer(conv, ("I know it's hard. Your time's coming.", feel_wait), ("That's my answer.", feel_blunt))


def minutes_rival(conv):
    c = conv["ctx"]
    if c["better_than_rival"]:
        _mood(conv, -2.0)
        _him(conv, _say(conv, ["Ahead of me? On what evidence?", "Come on. You know I'm better than {rival}.",
                               "He's had a good month. I've had a good career."]))
        _offer(conv, ("Fair point. You'll get games - I promise.", feel_promise_start),
               ("My decision. Live with it.", feel_blunt))
    else:
        _mood(conv, 0.5 if c["prof"] >= 11 else -1.0)
        _him(conv, _say(conv, ["Yeah... he's in form. I'll give you a problem though.", "Okay. For now.",
                               "Fine. He won't stay ahead for long."]))
        _close(conv)


def minutes_listen(conv):
    c = conv["ctx"]
    if c["very_low"] or c["wants_out"]:
        _mood(conv, 3.0)
        from career import chats
        chats._list(c["career"], c["p"])
        conv["outcome"].append("He's on the transfer list.")
        _end(conv, _say(conv, ["Thank you. Honestly, that's best for everyone.", "Appreciate it, {boss}. No hard feelings.",
                               "I think it's time. Thanks."]))
    else:
        _mood(conv, -3.0)
        _him(conv, _say(conv, ["Whoa - I didn't say I wanted to leave.", "You want rid of me?", "That's not what I meant at all."]))
        _offer(conv, ("No - I want you here, fighting for a place.", lambda cv: (_mood(cv, 2.0), _close(cv))),
               ("Think about it.", lambda cv: (_mood(cv, -1.0), _close(cv))))


def minutes_warn(conv):
    c = conv["ctx"]
    _mood(conv, -1.5 if c["temp"] >= 11 else -0.5)
    _him(conv, _say(conv, ["Why? I'm fit.", "Rested? I don't need resting.", "Okay... as long as it's not for long."]))
    _offer(conv, ("Just managing the load. You're important.", lambda cv: (_mood(cv, 1.5), _close(cv))),
           ("We'll see how you go.", lambda cv: (_close(cv))))


# ---------------------------------------------------------------------------
# REST HIM
# ---------------------------------------------------------------------------
def rest_open(conv):
    from career import chats
    c = conv["ctx"]
    if not c["next"] or not c["starting"]:
        _end(conv, _say(conv, ["Rest? I'm not even in the team.", "I'm not playing anyway, {boss}."]))
        return
    bigger = c["next2"] is not None and c["next2"][1] - c["next"][1] >= chats.BIGGER_GAME
    conv["bigger"] = bigger
    if c["tired"]:
        _mood(conv, 2.0)
        _him(conv, _say(conv, ["Thanks {boss}. My legs are shot.", "Honestly? Thank you. I need it.", "Good call. I'm running on empty."]))
        _rest(conv)
        _offer(conv, ("Recover properly - I need you for {opp2}.", lambda cv: (_mood(cv, 1.0), _close(cv))),
               ("Use the time well.", lambda cv: (_close(cv))))
    elif c["want"] < 0.5:
        _him(conv, _say(conv, ["Okay, {boss}.", "No problem.", "Fair enough."]))
        _rest(conv)
        _close(conv)
    else:
        _mood(conv, -2.0)
        _him(conv, _say(conv, ["Rest? I feel great. I want to play.", "I don't need a rest, {boss}.", "Why? I'm in form."]))
        _offer(conv, ("It's about {opp2} - I need you fresh for that." if bigger else "It's just squad rotation.", rest_reason),
               ("It's not up for discussion.", rest_insist),
               ("Okay - you can play.", rest_back_down))


def _rest(conv):
    c = conv["ctx"]
    c["p"]["rest_for"] = c["next"][0]
    conv["outcome"].append(f"He's rested for {c['next'][2]}.")
    conv["rested"] = True


def rest_reason(conv):
    c = conv["ctx"]
    if conv.get("bigger") and c["prof"] >= 11:
        _mood(conv, 2.0)
        _him(conv, _say(conv, ["Ah, I get it. I'll be ready for {opp2}.", "Fair. Makes sense.", "Okay - I'll be flying for {opp2}."]))
    elif conv.get("bigger"):
        _mood(conv, 0.5)
        _him(conv, _say(conv, ["I'd rather play both, but fine.", "Okay... {opp2} it is.", "If you say so."]))
    else:
        _mood(conv, -1.5 if c["temp"] >= 11 else 0.0)
        _him(conv, _say(conv, ["Rotation? I'm one of the best players here.", "Fine.", "Okay, {boss}."]))
    _rest(conv)
    _close(conv)


def rest_insist(conv):
    c = conv["ctx"]
    _mood(conv, -2.0 if c["temp"] >= 11 else -0.5)
    _rest(conv)
    _end(conv, _say(conv, ["Fine.", "Right.", "...Okay, {boss}."] if c["temp"] >= 11 else ["Understood.", "Okay.", "You're the boss."]))


def rest_back_down(conv):
    _mood(conv, 1.5)
    _end(conv, _say(conv, ["Cheers, {boss}! You won't regret it.", "Thank you. I'll be brilliant.", "Get in."]))


def rest_from_form(conv):
    _mood(conv, 2.0)
    _rest(conv)
    _end(conv, _say(conv, ["Thanks {boss}. I'll come back stronger.", "Needed that. Thank you."]))


# ---------------------------------------------------------------------------
# HIS FUTURE
# ---------------------------------------------------------------------------
def future_open(conv):
    c = conv["ctx"]
    _him(conv, _pick(conv,
        (c["wants_out"] or c["very_low"], ["Honestly? I've been thinking about moving on.", "I'm not sure my future's here, {boss}.",
                                           "I think it might be time for a change."]),
        (c["veteran"], ["I've got a few good years left in me. Maybe one more contract.", "I'd love to finish my career here.",
                        "I've been thinking about what comes after football, to be honest."]),
        (c["young"], ["I want to be a regular here. That's the dream.", "I want to learn, play, get better.",
                      "I'm ambitious, {boss}. I want to play at the top."]),
        (True, ["I'm happy here. I'd like to stay.", "I see myself here long-term, if you'll have me.",
                "Depends on the club's ambitions, I suppose."])))
    _offer(conv, ("You're a big part of my plans.", future_plans),
           ("We'll talk about a new contract soon.", future_contract),
           ("Ever thought about coaching?" if c["veteran"] else "Keep developing and the sky's the limit." if c["young"] else None,
            future_coach if c["veteran"] else future_young),
           ("If the right offer came in, we'd listen.", minutes_listen))


def future_plans(conv):
    c = conv["ctx"]
    if c["short"]:
        _mood(conv, -1.0)
        _him(conv, _say(conv, ["Doesn't feel like it from the bench.", "Then play me.", "With respect, show me."]))
        _offer(conv, ("I will. You'll get games - I promise.", feel_promise_start), ("Be patient.", feel_wait))
    else:
        _mood(conv, 3.0)
        _him(conv, _say(conv, ["That's great to hear, {boss}.", "Brilliant. I want to win things here.", "Means a lot. Thank you."]))
        _close(conv)


def future_contract(conv):
    c = conv["ctx"]
    _mood(conv, 2.0 if c["years"] <= 2 else 1.0)
    c["p"]["contract_talk"] = c["career"]["date"]
    conv["outcome"].append("He'd welcome a new contract - you can offer one from his screen.")
    _him(conv, _say(conv, ["Sounds good. I'll tell my agent.", "Music to my ears.", "Looking forward to it, {boss}."]))
    _close(conv)


def future_coach(conv):
    c = conv["ctx"]
    _mood(conv, 1.5 if c["lead"] >= 11 else 0.5)
    _him(conv, _say(conv, ["Funny you ask - I've started my badges.", "I'd love to. Help the young lads.",
                           "Me, a coach? Ha. Maybe. Not yet though!"]))
    _close(conv)


def future_young(conv):
    _mood(conv, 2.0)
    _him(conv, _say(conv, ["That's all I want to hear.", "I'll work every day.", "Thanks, {boss}. I won't let you down."]))
    _close(conv)


# ---------------------------------------------------------------------------
# THE DRESSING ROOM (and the armband)
# ---------------------------------------------------------------------------
def room_open(conv):
    c = conv["ctx"]
    players = c["club"]["players"]
    avg = sum(morale.level(q) for q in players) / max(1, len(players))
    if c["captain"] or c["vice"] or c["lead"] >= 13:
        _him(conv, _pick(conv,
            (avg >= 60, ["Buzzing in there, {boss}. Everyone's together.", "Best atmosphere I've known.", "The lads are flying."]),
            (avg >= 45, ["It's alright. A couple of lads are grumbling.", "Mixed. Most are fine.", "Steady. Nothing to worry about yet."]),
            (True, ["Not good, {boss}. Heads are down.", "It's tense. People are frustrated.", "Honestly? It's a bit of a mess."])))
        worst = min((q for q in players if q is not c["p"]), key=morale.level, default=None)
        options = [("Anyone I should worry about?", room_worst)] if worst is not None else []
        if not c["captain"] and c["lead"] >= 13:
            options.append(("Would you want more responsibility?", room_responsibility))
        options.append(("Have a word with the lads for me.", room_rally))
        _offer(conv, *options)
    else:
        _mood(conv, 0.0)
        _him(conv, _say(conv, ["The dressing room? I just keep my head down, {boss}.", "Couldn't tell you. I'm not one for the politics.",
                               "Ask the captain - I just play."]))
        _offer(conv, ("Fair enough.", lambda cv: (_close(cv))),
               ("Who do the lads listen to?", room_who))


def room_worst(conv):
    c = conv["ctx"]
    worst = min((q for q in c["club"]["players"] if q is not c["p"]), key=morale.level)
    _mood(conv, 0.5)
    if morale.level(worst) < 45:
        text, _ = morale.reason(worst)
        conv["outcome"].append(f"{worst['Name']} is unhappy" + (f" - {text}." if text else "."))
        _him(conv, _say(conv, [f"{worst['Name'].split(' ')[-1]}. He's " + (text or "not himself") + ".",
                               f"Keep an eye on {worst['Name'].split(' ')[-1]} - he's struggling."]))
        _offer(conv, ("Can you have a word with him?", room_word_with), ("I'll deal with it.", lambda cv: (_close(cv))))
    else:
        _him(conv, _say(conv, ["Nobody really. We're in a good place.", "No - honestly, everyone's fine."]))
        _close(conv)


def room_word_with(conv):
    c = conv["ctx"]
    worst = min((q for q in c["club"]["players"] if q is not c["p"]), key=morale.level)
    last = worst.get("cheered")
    if c["lead"] >= 12 and not (last and cal.days_between(last, c["career"]["date"]) < RALLY_GAP):
        d = 3.0 if c["lead"] >= 15 else 1.5
        worst["morale"] = round(min(98.0, morale.level(worst) + d), 1)
        worst["cheered"] = c["career"]["date"]
        conv["outcome"].append(f"He had a word with {worst['Name']} - it helped.")
        _mood(conv, 1.0)
        _him(conv, _say(conv, ["Leave it with me.", "I'll sort him out, {boss}.", "No problem. I'll take him for a coffee."]))
    else:
        _him(conv, _say(conv, ["I'll try, but we're not close.", "I can, but I'm not sure he'll listen to me."]))
    _close(conv)


def room_responsibility(conv):
    _mood(conv, 2.0)
    conv["outcome"].append("He'd love more responsibility - he could wear the armband.")
    _him(conv, _say(conv, ["I'd love that, {boss}.", "Absolutely. I'm ready.", "If you think I'm the man, I won't let you down."]))
    _close(conv)


def room_rally(conv):
    c = conv["ctx"]
    if c["lead"] >= 13:
        if _rally(conv, 1.0 if c["lead"] < 16 else 1.8):
            conv["outcome"].append("He's rallied the dressing room - the squad's a little happier.")
        _mood(conv, 1.0)
        _him(conv, _say(conv, ["Done. I'll get them together after training.", "On it, {boss}.", "Leave it with me."]))
    else:
        _mood(conv, -0.5)
        _him(conv, _say(conv, ["I'll try, but I'm not sure they'll listen to me.", "Not sure I'm the right man, {boss}."]))
    _close(conv)


def room_who(conv):
    from career import captains
    c = conv["ctx"]
    best = max((q for q in c["club"]["players"] if q is not c["p"]), key=captains.leadership, default=None)
    if best is not None:
        conv["outcome"].append(f"The lads listen to {best['Name']}.")
        _him(conv, _say(conv, [f"{best['Name'].split(' ')[-1]}. When he talks, everyone listens.",
                               f"Probably {best['Name'].split(' ')[-1]}. He's the voice in there."]))
    _close(conv)


# ---------------------------------------------------------------------------
# MOVING ON: the next match, life off the pitch (keeps a short chat going)
# ---------------------------------------------------------------------------
def match_talk(conv):
    c = conv["ctx"]
    nxt = c["next"]
    tough = nxt is not None and nxt[1] > morale._strength(c["club"]) + 1.5
    easy = nxt is not None and nxt[1] < morale._strength(c["club"]) - 1.5
    if c.get("rested_now") or conv.get("rested"):
        _him(conv, _say(conv, ["I'll be cheering from the stands, {boss}!", "I'll be ready for the one after.",
                               "Can't wait for {opp2}."]))
        _offer(conv, ("Good man.", _goodbye))
        return
    if not c["starting"]:
        _him(conv, _pick(conv, (c["temp"] >= 14, ["Ready? I'm always ready. You just don't pick me.", "Ready to sit and watch, you mean?"]),
                         (True, ["If you need me off the bench, I'll be ready.", "Always. Give me ten minutes and I'll change it.",
                                 "Ready, {boss}. Just say the word."])))
        _offer(conv, ("Be ready - you might get your chance.", lambda cv: (_mood(cv, 1.0), _goodbye(cv))),
               ("Keep the bench warm for me.", lambda cv: (_mood(cv, -1.5 if cv["ctx"]["temp"] >= 11 else 0.0), _goodbye(cv))))
        return
    _him(conv, _pick(conv,
        (tough, ["Big one, that. They've got some players.", "Ready. These are the games you want to play in.",
                 "Bring them on, {boss}. Nobody fancies us there."]),
        (easy, ["Should be three points, that.", "Can't take them lightly, mind.", "We'll be fine. Just need to start fast."]),
        (True, ["Yeah, I'm ready. It'll be tight.", "Up for it, {boss}. Can't wait.", "Ready. What do you want from me?"])))
    _offer(conv, ("I want you to take the game to them.", match_attack),
           ("Keep it tight and stay disciplined.", match_tight),
           ("Just enjoy it and play your game.", match_enjoy))


def match_attack(conv):
    c = conv["ctx"]
    _mood(conv, 1.0 if c["form"] > 0 or c["temp"] >= 12 else 0.5)
    _him(conv, _pick(conv, (c["p"]["Pos"] in ("GK", "CB", "LB", "RB"),
                            ["I'll get forward when I can.", "Front foot. Got it.", "I'll be on the half-way line, {boss}!"]),
                     (True, ["Music to my ears.", "That's how I like it.", "I'll run at them all day."])))
    _offer(conv, ("Go on then.", _goodbye))


def match_tight(conv):
    c = conv["ctx"]
    attacker = c["p"]["Pos"] in ("ST", "CF", "LW", "RW", "AM", "CAM")
    _mood(conv, -0.5 if attacker and c["temp"] >= 12 else 0.5)
    _him(conv, _say(conv, ["Boring, but okay.", "Understood. Clean sheet first."] if attacker else
                    ["Nothing gets past me.", "Clean sheet. Leave it with me.", "That's my game, {boss}."]))
    _offer(conv, ("Good lad.", _goodbye))


def match_enjoy(conv):
    c = conv["ctx"]
    _mood(conv, 1.5 if c["young"] or c["low"] else 0.5)
    _him(conv, _say(conv, ["Will do, {boss}.", "Thanks. Takes the pressure off.", "Always do!"]))
    _offer(conv, ("See you out there.", _goodbye))


def life_talk(conv):
    c = conv["ctx"]
    rng = conv["rng"]
    new = c["p"].get("joined") and cal.days_between(c["p"]["joined"], c["career"]["date"]) < 120
    if new:
        good = c["mood"] >= 50
        _him(conv, _say(conv, ["Really well. The lads have made me feel at home.", "Good. Found a place near the training ground.",
                               "Great, {boss}. Love the city."] if good else
                        ["Bit slow, honestly. Still living in a hotel.", "It's been harder than I thought.",
                         "Okay. Don't really know anyone yet."]))
        if good:
            _offer(conv, ("Glad to hear it.", lambda cv: (_mood(cv, 1.0), _goodbye(cv))),
                   ("Any of the lads you've got close to?", life_mates))
        else:
            _offer(conv, ("I'll get the club to help you find a place.", lambda cv: (_mood(cv, 2.5), _goodbye(cv))),
                   ("You'll settle. Give it time.", lambda cv: (_mood(cv, 1.0), _goodbye(cv))),
                   ("Get the lads to take you out.", life_mates))
        return
    kind = rng.choice(["family", "golf", "kids", "studies", "dog", "music"] if not c["young"] else ["studies", "music", "games", "driving"])
    _him(conv, _say(conv, {
        "family": ["Good, thanks. The wife's expecting again!", "Busy. The in-laws are staying.", "All good at home, {boss}."],
        "golf": ["Been playing a lot of golf. Handicap's coming down.", "Golf, mostly. Don't tell the physio."],
        "kids": ["Knackered. The little one's not sleeping.", "The kids keep me busy. Football's the easy bit."],
        "studies": ["I've started an online course, actually.", "Doing my coaching badges on the side."],
        "dog": ["Got a new dog. He's chewed everything.", "Walking the dog, mostly. He's a nightmare."],
        "music": ["I'm learning the guitar. Badly.", "I've been DJ-ing in the dressing room. The lads hate it."],
        "games": ["Gaming with the lads, mostly.", "Online all night with the boys - don't worry, I get my sleep!"],
        "driving": ["Just passed my test!", "Learning to drive. Crashed the instructor's car once. Only once."],
    }[kind]))
    _offer(conv, ("Ha - good for you.", lambda cv: (_mood(cv, 1.0), _goodbye(cv))),
           ("As long as it doesn't affect your football.", lambda cv: (_mood(cv, 0.0 if cv["ctx"]["prof"] >= 11 else -1.0), _goodbye(cv))))


def life_mates(conv):
    c = conv["ctx"]
    same = [q for q in c["club"]["players"] if q is not c["p"] and abs(int(q.get("Age", 25)) - c["age"]) <= 3]
    mate = conv["rng"].choice(same) if same else None
    _mood(conv, 1.0)
    if mate:
        _him(conv, _say(conv, [f"{mate['Name'].split(' ')[-1]}'s been great. Showed me round.",
                               f"Me and {mate['Name'].split(' ')[-1]} have been getting on well."]))
    else:
        _him(conv, _say(conv, ["Everyone's been good to me.", "The lads are a good bunch."]))
    _offer(conv, ("Good. A happy dressing room wins games.", _goodbye))


# ---------------------------------------------------------------------------
# HE ASKED TO SEE YOU (an unhappy player at your door - career/chats.py)
# ---------------------------------------------------------------------------
def _msg(conv):
    from career import transfers
    mid = conv.get("mid")
    return next((m for m in transfers.inbox(conv["ctx"]["career"]) if m["id"] == mid), None) if mid is not None else None


def asked_open(conv):
    c = conv["ctx"]
    m = _msg(conv)
    if m is not None:
        m["state"] = "answered"
    r = c["reason"]
    if r == "minutes":
        _him(conv, _pick(conv,
            (c["temp"] >= 14, ["I'll be straight with you, {boss}. I'm sick of this. I didn't come here to sit on the bench.",
                               "I want to know what I have to do to get a game. Because whatever it is, I'm doing it.",
                               "Honestly? I'm close to the end of my tether."]),
            (c["young"], ["Sorry to bother you, {boss}. I just... I want to play. I feel like I'm going backwards.",
                          "I'm not getting any minutes. I'm worried about my development."]),
            (True, ["Thanks for seeing me. I need to know where I stand - I'm not playing.",
                    "I've been patient, {boss}. But I need games.",
                    "I'll keep it short: I'm not happy with my minutes."])))
        _offer(conv, ("You'll get games - I promise.", feel_promise_start),
               ("Fight for your place like everyone else.", minutes_fight),
               ("{rival} is ahead of you at the moment.", minutes_rival),
               ("If you want to leave, we'd listen to offers.", minutes_listen))
    elif r in ("talk", "promise", "captaincy"):
        _him(conv, _pick(conv,
            (r == "promise", ["You gave me your word, {boss}. And nothing happened.", "You promised me games. I believed you.",
                              "I don't know if I can trust what you tell me any more."]),
            (r == "captaincy", ["Why did you take the armband off me? I've given everything for this club.",
                                "I was captain. Now I'm not. I want to know why."]),
            (True, ["I didn't like how you spoke to me, {boss}. I've been thinking about it all week.",
                    "Last time we talked... it didn't sit right with me.", "I feel like you don't rate me."])))
        _offer(conv, ("You're right. I owe you an apology.", asked_sorry),
               ("I stand by what I did.", asked_stand),
               ("Let's draw a line under it and move on.", asked_move_on),
               ("If you want to leave, we'd listen to offers.", minutes_listen))
    else:
        _him(conv, _pick(conv,
            (c["lead"] >= 13, ["The lads are low, {boss}. Someone has to say it.", "I'm worried about this group. We're drifting."]),
            (True, ["I'm struggling, {boss}. Everything feels heavy at the minute.", "I'm not enjoying my football. At all.",
                    "Honestly? I'm fed up. Nothing's going right."])))
        _offer(conv, ("Things will turn round - stick with me.", asked_reassure),
               ("Look at yourself first.", asked_look),
               ("What do you think we need to change?", asked_change),
               ("If you want to leave, we'd listen to offers.", minutes_listen))


def asked_sorry(conv):
    c = conv["ctx"]
    _mood(conv, 3.5 if c["temp"] < 14 else 2.0)
    _him(conv, _say(conv, ["...Thanks, {boss}. That means more than you know.", "I appreciate that. Not many managers would say it.",
                           "Okay. Respect for saying that."]))
    _offer(conv, ("Clean slate. Now go and show me.", lambda cv: (_mood(cv, 1.0), _close(cv))),
           ("Just don't make me regret it.", lambda cv: (_close(cv))))


def asked_stand(conv):
    c = conv["ctx"]
    if c["prof"] >= 14 and c["temp"] < 12:
        _mood(conv, 0.0)
        _him(conv, _say(conv, ["Fine. I don't agree, but I respect you being straight.", "Okay. At least I know where I stand."]))
        _close(conv)
    else:
        _mood(conv, -3.0)
        _him(conv, _say(conv, ["Then we've got a problem.", "Right. Good to know where I stand.", "Unbelievable."]))
        if c["very_low"] and c["temp"] >= 12:
            _offer(conv, ("That's how it is.", feel_door_slammed),
                   ("Look - I hear you. Let's work it out.", lambda cv: (_mood(cv, 2.0), _close(cv))))
        else:
            _close(conv)


def asked_move_on(conv):
    c = conv["ctx"]
    _mood(conv, 1.5 if c["prof"] >= 11 else 0.0)
    _him(conv, _say(conv, ["Okay. Fresh start.", "Fine by me, {boss}.", "...Alright. Let's move on."] if c["prof"] >= 11 else
                    ["Easy for you to say.", "I'll try.", "We'll see."]))
    _close(conv)


def asked_reassure(conv):
    c = conv["ctx"]
    p = c["p"]
    last = p.get("reassured")
    p["reassured"] = c["career"]["date"]
    if last and cal.days_between(last, c["career"]["date"]) < 60:          # (it wears thin)
        _mood(conv, 0.0)
        _him(conv, _say(conv, ["You said that last time, {boss}.", "That's what you always say.", "Heard it before."]))
        _offer(conv, ("And I meant it. It's coming.", lambda cv: (_mood(cv, 0.5), _close(cv))),
               ("Then what do you want me to say?", lambda cv: (_mood(cv, -1.0), _close(cv))))
        return
    _mood(conv, 2.5)
    _him(conv, _say(conv, ["Thanks {boss}. I needed to hear that.", "Okay. I believe in you.", "Right. I'm with you."]))
    _offer(conv, ("We do it together.", lambda cv: (_mood(cv, 1.0), _close(cv))),
           ("Next game, let's start the turnaround.", lambda cv: (_mood(cv, 0.5), _close(cv))))


def asked_look(conv):
    c = conv["ctx"]
    if c["prof"] >= 12 and c["temp"] < 13:
        _mood(conv, 2.0)
        _him(conv, _say(conv, ["...Fair. I've not been at my best either.", "You're right. I'll show you in training.",
                               "Okay. Point taken."]))
        _close(conv)
    elif c["temp"] >= 13:
        _mood(conv, -4.0)
        _him(conv, _say(conv, ["Me? I came to you for help.", "I've been fighting. You're just not seeing it.",
                               "Wow. Thanks for nothing."]))
        if morale.level(c["p"]) < 30:
            from career import chats
            chats._transfer_request(c["career"], c["p"])
            conv["outcome"].append("He's handed in a transfer request.")
            _end(conv, _say(conv, ["Then I want out.", "I'm done. Put me on the list."]))
        else:
            _close(conv)
    else:
        _mood(conv, -1.0)
        _him(conv, _say(conv, ["Right. Okay.", "If you say so."]))
        _close(conv)


def asked_change(conv):
    c = conv["ctx"]
    _mood(conv, 1.5)
    _him(conv, _pick(conv,
        (c["lead"] >= 13, ["We need to train harder, and the lads need to hear it from you.", "Belief. We've lost it. Get us a win and it comes back."]),
        (True, ["I don't know. More confidence, maybe.", "Just a win. One win.", "Keep it simple. We're overthinking it."])))
    _offer(conv, ("Good. I'll take that on board.", lambda cv: (_mood(cv, 1.0), _close(cv))),
           ("Then help me lead it." if c["lead"] >= 12 else "Thanks. Keep your head up.", feel_lead if c["lead"] >= 12 else
            (lambda cv: (_mood(cv, 0.5), _close(cv)))))


# ---------------------------------------------------------------------------
# HIS TRANSFER REQUEST
# ---------------------------------------------------------------------------
def request_open(conv):
    c = conv["ctx"]
    r = c["reason"]
    _him(conv, _pick(conv,
        (r == "minutes", ["I want to play, {boss}. It's not happening here, so I want to go somewhere it will.",
                          "I've thought about it a lot. I need games, and I won't get them here."]),
        (r == "promise", ["You broke your word. I can't play for someone I don't trust.", "You promised me. I'm done waiting."]),
        (True, ["I've made my mind up. I want to leave.", "It's time for a change, {boss}. Nothing personal.",
                "I'm not happy. I haven't been for a while."])))
    _offer(conv, ("Okay. I won't stand in your way.", request_let_go),
           ("What would it take for you to stay?", request_what),
           ("You're under contract. You're going nowhere.", request_refuse))


def _settle(conv, state):
    m = _msg(conv)
    if m is not None and m["state"] == "open":
        m["state"] = state


def request_let_go(conv):
    from career import chats
    c = conv["ctx"]
    chats._list(c["career"], c["p"])
    _mood(conv, chats.LET_GO)
    _settle(conv, "accepted")
    conv["outcome"].append("He's on the transfer list.")
    _end(conv, _say(conv, ["Thanks, {boss}. No hard feelings.", "I appreciate you being straight with me.",
                           "Thank you. I'll give everything until I go."]))


def request_refuse(conv):
    from career import chats
    c = conv["ctx"]
    _mood(conv, chats.REFUSED)
    _settle(conv, "rejected")
    c["p"]["wants_out"] = True
    conv["outcome"].append("You've refused his request - he's not happy.")
    _end(conv, _say(conv, ["So I'm stuck here. Fine.", "We'll see about that.", "Then you'll have a very unhappy player."]))


def _chance_to_stay(c):
    """How likely he is to be talked round (0-1): a professional in a bad patch, yes; a hot-head who's been lied to, no."""
    x = 0.45 + 0.03 * (c["prof"] - 10) - 0.025 * (c["temp"] - 10) + 0.012 * (c["mood"] - 30)
    if c["reason"] == "promise":
        x -= 0.25
    return max(0.05, min(0.85, x))


def request_what(conv):
    c = conv["ctx"]
    r = c["reason"]
    if r == "minutes":
        _him(conv, _say(conv, ["Games. A proper run in the team.", "Promise me I'll play. Properly.", "Put me in the team and keep me there."]))
        _offer(conv, ("You'll get games. You have my word." if not c["p"].get("promise") else None, request_promise),
               ("I can't promise that - but you're important to me.", request_persuade),
               ("Then you'd better go.", request_let_go))
    elif r == "promise":
        _him(conv, _say(conv, ["I don't think there's anything you can say. You've said it all before.",
                               "Honestly? I don't believe you any more."]))
        _offer(conv, ("I got it wrong. Give me one more chance.", request_persuade),
               ("Then you'd better go.", request_let_go),
               ("You're staying. End of.", request_refuse))
    else:
        _him(conv, _say(conv, ["I want to feel wanted. I want to be winning.", "Show me this club's going somewhere.",
                               "I don't know, {boss}. Something has to change."]))
        _offer(conv, ("You're a big part of my plans here.", request_persuade),
               ("We'll talk about a new contract.", request_contract),
               ("Then you'd better go.", request_let_go))


def request_promise(conv):
    c = conv["ctx"]
    if conv["rng"].random() < _chance_to_stay(c) + 0.25:
        feel_promise_start(conv)               # (his reply + the promise)
        _withdraw(conv)
    else:
        _mood(conv, 0.5)
        _him(conv, _say(conv, ["Words are cheap, {boss}. My request stands.", "I've heard it before. I still want to go."]))
        _offer(conv, ("Then I'll put you on the list.", request_let_go), ("You're not going anywhere.", request_refuse))


def request_persuade(conv):
    c = conv["ctx"]
    if conv["rng"].random() < _chance_to_stay(c):
        _mood(conv, 3.0)
        _withdraw(conv)
        _him(conv, _say(conv, ["...Okay. I'll give it another go.", "Alright, {boss}. I'll stay - for now.",
                               "Fine. I'll withdraw it. But things need to change."]))
        _offer(conv, ("They will. Thank you.", lambda cv: (_mood(cv, 1.0), _close(cv))))
    else:
        _mood(conv, -0.5)
        _him(conv, _say(conv, ["I'm sorry, {boss}. My mind's made up.", "Nice words. But no.", "It's too late for that."]))
        _offer(conv, ("Then I'll put you on the list.", request_let_go), ("You're not going anywhere.", request_refuse))


def request_contract(conv):
    c = conv["ctx"]
    if conv["rng"].random() < _chance_to_stay(c) + 0.15:
        _mood(conv, 3.0)
        _withdraw(conv)
        c["p"]["contract_talk"] = c["career"]["date"]
        conv["outcome"].append("He'd welcome a new contract - you can offer one from his screen.")
        _him(conv, _say(conv, ["Now we're talking. I'll hold off.", "Okay - if you're serious, I'll withdraw it."]))
        _close(conv)
    else:
        _mood(conv, -0.5)
        _him(conv, _say(conv, ["It's not about money, {boss}.", "A contract won't change how I feel."]))
        _offer(conv, ("Then I'll put you on the list.", request_let_go), ("You're not going anywhere.", request_refuse))


def _withdraw(conv):
    p = conv["ctx"]["p"]
    p.pop("wants_out", None)
    _settle(conv, "withdrawn")
    conv["outcome"].append("He's withdrawn his transfer request.")


def _days(n):
    import datetime
    return datetime.timedelta(days=n)


STAGES = {"asked_open": asked_open, "request_open": request_open, "feel_open": feel_open, "form_open": form_open, "minutes_open": minutes_open, "rest_open": rest_open,
          "future_open": future_open, "room_open": room_open}
