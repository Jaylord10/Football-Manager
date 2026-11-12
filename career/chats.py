"""
career/chats.py
===============
Talking to your players one at a time (the "Talk to him" button on his
screen).  Once a week per player - any more and it stops meaning anything.

  HOW ARE YOU FEELING?   He tells you what's on his mind (if anything) -
                         you'll see it on his screen afterwards.
  PRAISE HIS FORM        Lifts him if he's been doing well; if he hasn't, a
                         professional sees through it.
  I EXPECT MORE          Can fire up a professional who's been poor; a
                         hot-head takes it badly, and anyone who's actually
                         been doing well will feel hard done by.
  REST HIM FOR THE NEXT GAME
                         He sits the next match out.  Tired legs, or a
                         squad man: no problem.  A fresh first-teamer: he
                         wants to play - unless he can see there's a bigger
                         game straight after, and he's sensible about it.
  PROMISE MORE GAMES     Lifts him now.  The game remembers: in five weeks,
                         if he hasn't been getting the minutes his status
                         says, the promise is broken and he takes it hard.

Every reply depends on his hidden personality (career/morale.py traits): after
a few chats your assistant starts to tell you what sort of character he is.
"""

from career import morale, clubs as clubs_mod, calendar as cal

COOLDOWN = 7                 # days between chats with the same man
PROMISE_DAYS = 35
PROMISE_KEPT = 3.0
PROMISE_BROKEN = -10.0
BIGGER_GAME = 2.0            # rating points: the match after next is this much tougher -> "a bigger game"
TIRED = 0.90                 # condition below this: he knows he needs a breather

OPTIONS = [
    ("feel", "How are you feeling?"),
    ("praise", "Praise his form"),
    ("more", "Tell him you expect more"),
    ("rest", "Rest him for the next game"),
    ("promise", "Promise him more games"),
]


def can_talk(career, p):
    """(yes, why not)"""
    last = p.get("last_chat")
    if last and cal.days_between(last, career["date"]) < COOLDOWN:
        return False, f"You spoke to him on {cal.fmt(last, year=False)} - give it a few days."
    return True, ""


def options(career, club, p):
    """[(key, label, allowed, why not)]"""
    out = []
    for key, label in OPTIONS:
        ok, why = True, ""
        if key == "rest":
            nxt = _next_two(career, club)
            if not nxt:
                ok, why = False, "No match coming up."
            elif p.get("rest_for") == nxt[0][0]:
                ok, why = False, "He's already resting for that one."
            elif p["id"] not in (club.get("lineup") or {}).values():
                ok, why = False, "He's not in your XI anyway."
        if key == "promise" and p.get("promise"):
            ok, why = False, "You've already promised him."
        out.append((key, label, ok, why))
    return out


def talk(career, club, p, key):
    """Have the chat.  Returns {"reply": his words, "delta": morale change}."""
    t = morale.traits(p)
    prof, temp = t["prof"], t["temp"]
    feel = morale._feel(p)
    form = _form(p)                          # > 0 doing well, < 0 poorly
    reply, d, reveals = "", 0.0, False
    name = p["Name"].split(" ")[0]

    if key == "feel":
        text, v = morale.reason(p)
        if text:
            reply = _feel_words(p, text, v)
            p["told"] = {"text": text, "date": career["date"]}
        else:
            reply = "I'm alright, gaffer. Just want to keep playing my part."
            p["told"] = {"text": "nothing in particular on his mind", "date": career["date"]}
        d = 0.5                                  # (he likes being asked)
    elif key == "praise":
        if form > 0.5:
            d, reply = 3.5, "Cheers boss, that means a lot. I'm feeling sharp."
        elif form > -0.5:
            d, reply = 1.5, "Thanks gaffer. I'll keep working."
        elif prof >= 12:
            d, reply, reveals = -1.5, "With respect, I know I've not been at it. Don't sugar-coat it.", True
        else:
            d, reply = 1.0, "Thanks boss, nice to hear."
    elif key == "more":
        if form > 0.5:
            d, reply, reveals = -4.0, "What more do you want? I've been one of the best out there.", True
        elif prof >= 12 and temp < 13:
            d, reply, reveals = 3.0, "You're right. I'll show you in training this week.", True
        elif temp >= 13:
            d, reply, reveals = -5.0, "I've been doing my job. Look at the others before you look at me.", True
        else:
            d, reply = 0.5, "Fair enough, boss."
    elif key == "rest":
        nxt = _next_two(career, club)
        p["rest_for"] = nxt[0][0]
        want, status = morale.expected_share(club, p)
        bigger = len(nxt) > 1 and nxt[1][1] - nxt[0][1] >= BIGGER_GAME
        later = f" for {nxt[1][2]}" if len(nxt) > 1 else ""
        if p.get("condition", 1.0) < TIRED:
            d, reply = 2.0, "Thanks gaffer, my legs could do with it."
        elif want < 0.5:
            d, reply = -0.5, "Okay, boss."
        elif bigger and prof >= 11:
            d, reply, reveals = 0.0, f"Understood. I'll be ready{later}.", True
        elif bigger:
            d, reply, reveals = -2.0, f"I'd rather play, but if it's about being right{later}... fine.", True
        else:
            d, reply, reveals = -4.0, "I don't need a rest, gaffer. I want to play.", True
    elif key == "promise":
        want, status = morale.expected_share(club, p)
        p["promise"] = {"made": career["date"], "check": (cal.parse(career["date"]) + _days(PROMISE_DAYS)).isoformat(),
                        "share": min(0.9, max(want, 0.5))}
        d, reply = 4.0, "That's all I wanted to hear, boss. I won't let you down."

    d *= feel if d < 0 else 1.0
    p["morale"] = round(max(3.0, min(98.0, morale.level(p) + d)), 1)
    why = p.setdefault("morale_why", {})
    if key != "feel":
        why["talk"] = round(0.5 * why.get("talk", 0.0) + d, 2)
    p["last_chat"] = career["date"]
    if reveals:
        p["revealed"] = p.get("revealed", 0) + 1
    return {"reply": f"{name}: “{reply}”", "delta": round(d, 1)}


def after_matchday(career):
    """Promises falling due (your club)."""
    club = career["clubs"][career["my_club"]]
    today = career["date"]
    notes = []
    for p in club["players"]:
        pr = p.get("promise")
        if not pr or cal.parse(today) < cal.parse(pr["check"]):
            continue
        share = min(1.0, p.get("mins_avg", 0) / 90.0)
        if share >= pr["share"] - 0.1 or p.get("injury"):
            d, word = PROMISE_KEPT, "kept"
        else:
            d, word = PROMISE_BROKEN * morale._feel(p), "broken"
        p["morale"] = round(max(3.0, min(98.0, morale.level(p) + d)), 1)
        p.setdefault("morale_why", {})["promise"] = round(d, 2)
        p["promise"] = None
        notes.append((p, word))
    return notes


def character_note(p):
    """What your assistant has worked out about him (after he's shown it a couple of times)."""
    if p.get("revealed", 0) < 2:
        return None
    t = morale.traits(p)
    bits = []
    if t["prof"] >= 14:
        bits.append("a real professional")
    elif t["prof"] <= 6:
        bits.append("not the most professional")
    if t["temp"] >= 14:
        bits.append("he can be fiery")
    elif t["temp"] <= 6:
        bits.append("very level-headed")
    if not bits:
        bits.append("a steady sort - nothing extreme")
    return "Assistant: " + "; ".join(bits).capitalize() + "."


# ---------------------------------------------------------------------------
def _days(n):
    import datetime
    return datetime.timedelta(days=n)


def _form(p):
    why = p.get("morale_why") or {}
    return why.get("results", 0.0) + 1.5 * why.get("goals", 0.0)


def _next_two(career, club):
    """[(date, opponent strength, opponent name)] for the next two matches."""
    from career import league
    out = []
    for md in (career["matchday"], career["matchday"] + 1):
        if md > len(career["fixtures"]):
            break
        for h, a in career["fixtures"][md - 1]:
            if club["id"] in (h, a):
                opp = career["clubs"][a if h == club["id"] else h]
                out.append((league.match_date(career, md), morale._strength(opp), opp["name"]))
    return out


def _feel_words(p, text, v):
    if "minutes" in text:
        return "Honestly? I'm frustrated. I came here to play and I'm not getting the games."
    if "results" in text and v < 0:
        return "It's hard at the moment, boss. Everyone's feeling the results."
    if "results" in text:
        return "Loving it, gaffer. The lads are flying."
    if "goals" in text:
        return "Brilliant, boss. Scoring's the best feeling there is."
    if "getting games" in text:
        return "Really happy, gaffer. Thanks for the chances."
    return "I'm okay, thanks for asking."


# ---------------------------------------------------------------------------
# Players coming to YOU (an unhappy player asks for a word - your inbox)
# ---------------------------------------------------------------------------
ASK_BELOW = 40.0          # morale under this, with a clear grievance: he may ask to see you
ASK_CHANCE = 0.25         # per matchday at the line, more the lower he is / the hotter his head
ASK_GAP = 30              # days before he asks again
ANSWER_DAYS = 7           # you've this long to see him
IGNORED = -4.0            # ...or he feels ignored
REQUEST_BELOW = 30.0      # this unhappy and brushed off / ignored: he hands in a transfer request
REFUSED = -6.0            # you turn down his transfer request
LET_GO = 4.0              # you agree he can go (he's put on the transfer list)

ASK_ANSWERS = [("promise", "Promise him more games"), ("fight", "Tell him to fight for his place"),
               ("go", "Say he can leave if the right offer comes")]
ASK_ANSWERS_MOOD = [("reassure", "Reassure him - things will turn round"), ("look", "Tell him to look at himself first"),
                    ("go", "Say he can leave if the right offer comes")]


def answers_for(m):
    """The replies on offer: about minutes, or about how things are going."""
    return ASK_ANSWERS if "minutes" in m["data"].get("reason", "") else ASK_ANSWERS_MOOD


def unhappy_requests(career, rng):
    """After a matchday: unhappy men knock on your door; requests you sat on go stale."""
    from career import transfers
    club = career["clubs"][career["my_club"]]
    today = career["date"]
    for m in transfers.inbox(career):                         # requests you didn't answer
        if m["kind"] == "chat" and m["state"] == "open" and today > m["data"]["expires"]:
            m["state"] = "expired"
            p = clubs_mod.player_by_id(club, m["data"]["pid"])
            if p is not None:
                _change(p, IGNORED * morale._feel(p), "talk")
                if morale.level(p) < REQUEST_BELOW:
                    _transfer_request(career, p)
    for p in club["players"]:
        if p.get("loan", {}).get("to") not in (None, club["id"]) or p.get("listed") or p.get("wants_out"):
            continue
        m_ = morale.level(p)
        text, v = morale.reason(p)
        if m_ >= ASK_BELOW or text is None or v > -1.0:
            continue
        last = p.get("asked")
        if last and cal.days_between(last, today) < ASK_GAP:
            continue
        t = morale.traits(p)
        chance = ASK_CHANCE * (1 + (t["temp"] - 10) / 10) * min(2.0, (ASK_BELOW - m_) / 10 + 0.5)
        if rng.random() >= chance:
            continue
        p["asked"] = today
        transfers._message(career, "chat", f"{p['Name']} wants a word: he's {text}.",
                           {"pid": p["id"], "player": p["Name"], "reason": text,
                            "expires": (cal.parse(today) + _days(ANSWER_DAYS)).isoformat()}, stop=True)


def answer_request(career, mid, key):
    """Your answer to a player who asked to see you, or to his transfer request.  Returns his reply."""
    from career import transfers, finance as fin
    club = career["clubs"][career["my_club"]]
    m = next(x for x in transfers.inbox(career) if x["id"] == mid)
    p = clubs_mod.player_by_id(club, m["data"]["pid"])
    if p is None or m["state"] != "open":
        return "He's not here any more."
    t = morale.traits(p)
    name = p["Name"].split(" ")[0]
    if m["kind"] == "request":                              # his transfer request
        if key == "accept":
            _list(career, p)
            _change(p, LET_GO, "talk")
            m["state"] = "accepted"
            return f"{name}: “Thanks, gaffer. No hard feelings.” (He's on the transfer list.)"
        _change(p, REFUSED * morale._feel(p), "talk")
        m["state"] = "rejected"
        p["wants_out"] = True
        return f"{name}: “So I'm stuck here. Fine.”"
    m["state"] = "answered"
    p["last_chat"] = career["date"]
    if key == "promise":
        res = talk(career, club, p, "promise")
        return res["reply"]
    if key == "go":
        _list(career, p)
        _change(p, LET_GO, "talk")
        return f"{name}: “I appreciate you being straight with me.” (He's on the transfer list.)"
    if key == "reassure":
        last = p.get("reassured")
        p["reassured"] = career["date"]
        if last and cal.days_between(last, career["date"]) < 60:       # (it wears thin)
            _change(p, 0.5, "talk")
            return f"{name}: \u201cYou said that last time, boss.\u201d"
        _change(p, 2.5, "talk")
        return f"{name}: \u201cThanks boss. I needed to hear that.\u201d"
    # fight for your place / look at yourself first
    p["revealed"] = p.get("revealed", 0) + 1
    if t["prof"] >= 12 and t["temp"] < 13:
        _change(p, 2.0, "talk")
        return f"{name}: “Fair enough. I'll show you in training.”"
    if t["temp"] >= 13:
        _change(p, -4.0 * morale._feel(p), "talk")
        if morale.level(p) < REQUEST_BELOW:
            _transfer_request(career, p)
            return f"{name}: “Then I want out.” (He's handed in a transfer request.)"
        return f"{name}: “I've been fighting. You're just not seeing it.”"
    _change(p, -1.0, "talk")
    return f"{name}: “Right. Okay.”"


def _transfer_request(career, p):
    from career import transfers
    if p.get("wants_out") or p.get("listed"):
        return
    p["wants_out"] = True
    transfers._message(career, "request", f"{p['Name']} has handed in a transfer request.",
                       {"pid": p["id"], "player": p["Name"]}, stop=True)


def _list(career, p):
    from career import finance as fin
    p["listed"] = True
    p["asking"] = fin.value(p, career["date"])
    p.pop("wants_out", None)


def _change(p, d, why_key):
    p["morale"] = round(max(3.0, min(98.0, morale.level(p) + d)), 1)
    why = p.setdefault("morale_why", {})
    why[why_key] = round(why.get(why_key, 0.0) + d, 2)
