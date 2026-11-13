"""
career/legends.py
=================
The clubs' story goes on while you play:

  - NEW LEGENDS: when a player retires after a long career at a club (250 league games or more for them,
    or 150 games and three trophies), he joins that club's legends on its club page - "Defender 2026-2035.
    312 games, 14 goals; League champions x2."
  - RECORDS BROKEN: a club profile's "most league goals in a season" record (data/world/clubs/<short>.json)
    can be beaten - the club page shows the new record, and the papers make a story of it.

Kept in career["legends"] = {club id: [...]} and career["club_records"] = {club id: {"season_goals": ...}}.
(Uses the players' career records, career/playerhist.py.)
"""

import re

GAMES, GAMES_WITH_CUPS, CUPS = 250, 150, 3
MAX_PER_CLUB = 12
POS_WORD = {"GK": "Goalkeeper", "CB": "Defender", "LB": "Full-back", "RB": "Full-back", "LWB": "Wing-back",
            "RWB": "Wing-back", "DM": "Midfielder", "CM": "Midfielder", "AM": "Midfielder", "LM": "Midfielder",
            "RM": "Midfielder", "LW": "Winger", "RW": "Winger", "ST": "Striker"}


def _at(p, cid):
    """(games, goals, [trophies], first year, last year) for a player at one club, from his career record."""
    lines = [x for x in (p.get("hist") or []) if x.get("cid") == cid and not x.get("loan")]
    if not lines:
        return 0, 0, [], None, None
    tro = [t for x in lines for t in x.get("h", [])]
    first = int(lines[0]["y"][:4])
    last = int(lines[-1]["y"][:4]) + 1
    return sum(x["a"] for x in lines), sum(x["g"] for x in lines), tro, first, last


def retired(career, club, p):
    """A player retires (career/ageing.py): a legend of the club he gave most to?"""
    try:
        best = None
        for cid in {x.get("cid") for x in (p.get("hist") or [])}:
            if cid is None or not (0 <= cid < len(career["clubs"])):
                continue
            g, gl, tro, first, last = _at(p, cid)
            if g >= GAMES or (g >= GAMES_WITH_CUPS and len(tro) >= CUPS):
                if best is None or g > best[1]:
                    best = (cid, g, gl, tro, first, last)
        if best is None:
            return None
        cid, g, gl, tro, first, last = best
        counts = {}
        for t in tro:
            counts[t] = counts.get(t, 0) + 1
        won = "; ".join(f"{t} x{n}" if n > 1 else t for t, n in sorted(counts.items(), key=lambda kv: -kv[1]))
        entry = {"name": p["Name"], "role": f"{POS_WORD.get(p['Pos'], 'Player')} {first}-{last}",
                 "note": f"{g} league games, {gl} goals" + (f"; {won}" if won else "") + ".", "year": last}
        lst = career.setdefault("legends", {}).setdefault(str(cid), [])
        lst.append(entry)
        del lst[:-MAX_PER_CLUB]
        from career import transfers as trf
        if cid == career["my_club"]:
            trf._message(career, "news", f"{p['Name']} retires a club legend: {entry['note']}")
        return entry
    except Exception:
        return None


def legends(career, cid):
    """This career's new legends at a club (latest first)."""
    return list(reversed((career or {}).get("legends", {}).get(str(cid), [])))


def _record_goals(text):
    m = re.search(r",\s*(\d+)\s*\(", text or "")
    return int(m.group(1)) if m else None


def record(career, club, key):
    """A club record as it stands now (a broken one replaces the profile's)."""
    new = ((career or {}).get("club_records", {}).get(str(club["id"])) or {}).get(key)
    if new:
        return new
    from career import clubinfo
    return ((clubinfo.profile(club) or {}).get("records") or {}).get(key)


def season_records(career):
    """End of the season: has anyone beaten his club's league-goals-in-a-season record?"""
    from career import clubinfo, media
    for club in career.get("clubs", []):
        old = record(career, club, "season_goals")
        target = _record_goals(old)
        if target is None:
            continue
        best = None
        for p in club["players"]:
            line = (p.get("hist") or [None])[-1]
            if line and line.get("cid") == club["id"] and line["y"].startswith(str(career.get("year"))) \
                    and line["g"] > target and (best is None or line["g"] > best[1]):
                best = (p, line["g"], line["y"])
        if best is None:
            continue
        p, g, y = best
        career.setdefault("club_records", {}).setdefault(str(club["id"]), {})["season_goals"] = \
            f"{p['Name']}, {g} ({y})"
        holder = (old or "").split(",")[0]
        try:
            media.record_story(career, club, p, g, holder, target)
        except Exception:
            pass
