"""
career/assistant.py
===================
Your assistant's weekly report (in your inbox, after the first matchday of
each week): the mood in the squad and which way it's going, who needs a
word (and why, if he knows), who's flying, promises falling due, tired legs
in the XI, a low captain, key men's contracts running down.

It only says what your assistant would know: why a man is down only when
it's strong enough for him to pick up (morale.assistant_note) or the player
told you himself recently.
"""

from career import morale, clubs as clubs_mod, calendar as cal, captains, chats

EVERY_DAYS = 7
CONTRACT_WARN_DAYS = 180


def _mood_word(avg):
    return ("buzzing" if avg >= 70 else "in good spirits" if avg >= 58 else "mostly fine, with a few grumbles"
            if avg >= 48 else "flat - heads are down" if avg >= 38 else "unhappy")


def _short(p):
    return p["Name"].split(" ")[-1]


def _fit_by_next_match(career, club, p):
    """His condition on the day of the next match (training recovers him each day - career/training.py)."""
    from career import league, training
    nxt = league.match_date(career)
    days = max(0, cal.days_between(career["date"], nxt)) if nxt else 7
    rec = training.INTENSITY[training.settings(club)["intensity"]][1]
    return min(1.0, training.condition(p) + rec * days)


def report(career):
    """The report as [(heading, [lines])] - or None if there's nothing worth saying."""
    club = career["clubs"][career["my_club"]]
    today = career["date"]
    here = [p for p in club["players"] if p.get("loan", {}).get("to") in (None, club["id"])]
    if not here:
        return None
    out = []
    avg = sum(morale.level(p) for p in here) / len(here)
    last = (career.get("report_last") or {}).get("avg")
    if last is None:
        trend = ""
    elif _mood_word(avg) != _mood_word(last):
        trend = " - up on last week" if avg > last else " - down on last week"
    else:
        trend = (" - a bit better than last week" if avg > last + 1.5 else
                 " - a bit worse than last week" if avg < last - 1.5 else " - much the same as last week")
    out.append(("The mood", [f"The squad is {_mood_word(avg)}{trend}."]))
    # who needs a word
    low = sorted((p for p in here if morale.level(p) < 45), key=morale.level)
    lines = []
    for p in low[:3]:
        note = morale.assistant_note(p)
        told = p.get("told") or {}
        if note:
            why = note
        elif told and cal.days_between(told["date"], today) <= 30:
            why = f"{_short(p)} told you he's {told['text']}."
        else:
            why = f"{_short(p)} is {morale.label(p).lower()} and keeping it to himself - worth a chat."
        lines.append(why)
    if len(low) > 3:
        lines.append(f"...and {len(low) - 3} more on the Dressing room screen.")
    if lines:
        out.append(("Needs a word", lines))
    # flying
    best = sorted((p for p in here if morale.level(p) >= 80), key=lambda p: -morale.level(p))
    if best:
        names = ", ".join(_short(p) for p in best[:4])
        out.append(("Flying", [f"{names} {'is' if len(best) == 1 else 'are'} flying."]))
    # promises due
    lines = []
    for p in here:
        pr = p.get("promise")
        if pr and cal.days_between(today, pr["check"]) <= 21:
            share = min(1.0, p.get("mins_avg", 45) / 90.0)
            lines.append(f"You promised {_short(p)} games - he'll judge you on {cal.fmt(pr['check'])[4:10].strip()}. "
                         f"He's playing about {round(100 * share)}% of the minutes; he wants {round(100 * pr['share'])}%.")
    if lines:
        out.append(("Promises", lines))
    # tired legs
    xi = [clubs_mod.player_by_id(club, i) for i in (club.get("lineup") or {}).values()]
    tired = [p for p in xi if p is not None and _fit_by_next_match(career, club, p) < chats.TIRED]
    if tired:
        names = ", ".join(_short(p) for p in tired[:4])
        out.append(("Legs", [f"{names} won't be fully fresh for the next game - think about a rest."]))
    # fitness and sharpness (hidden numbers - career/fitness.py)
    from career import fitness
    note = fitness.squad_note(club, [p["id"] for p in xi if p is not None])
    if note:
        out.append(("Fitness", [note[0].upper() + note[1:]]))
    # captain
    cap, _ = captains.armband(club)
    if cap is not None and morale.level(cap) < 45:
        out.append(("Captain", [f"Your captain {_short(cap)} is {morale.label(cap).lower()}. The lads notice."]))
    # contracts
    lines = []
    for p in here:
        end = p.get("contract_end")
        status = p.get("status", "")
        if end and status in ("Key player", "First team") and 0 <= cal.days_between(today, end) <= CONTRACT_WARN_DAYS:
            lines.append(f"{_short(p)}'s contract runs out on {cal.fmt(end)[4:].strip()} - he's {morale._a(status)}.")
    if lines:
        out.append(("Contracts", lines[:3]))
    return out, avg


def weekly(career):
    """After a matchday: a report, once a week."""
    last = career.get("report_last") or {}
    if last.get("date") and cal.days_between(last["date"], career["date"]) < EVERY_DAYS:
        return None
    got = report(career)
    if got is None:
        return None
    sections, avg = got
    from career import transfers
    mid = transfers._message(career, "report", "Your assistant's weekly report", {"sections": sections})
    for m in transfers.inbox(career):
        if m["id"] == mid:
            m["state"] = "info"
    career["report_last"] = {"date": career["date"], "avg": round(avg, 1)}
    return mid
