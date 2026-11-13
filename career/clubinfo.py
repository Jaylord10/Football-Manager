"""
career/clubinfo.py
==================
Who the clubs are: each club's profile (data/world/clubs/<short>.json - its
history, honours, colours and kits, rivals, legends, records, and its ground
in detail), its crest and ground pictures, and the roll of honour for every
competition (data/world/honours.json - every season's winners, built so the
clubs' histories agree with each other).

COMPETITIONS (made-up equivalents of the real ones): the League (and a
Second Division below it), the Founders' Cup, the Charter Cup, the Crown of
Europe (Europe's elite), the Europa Trophy (Europe's second tier) and the
Intercontinental Cup (Europe's champions v South America's).

The ground's facts (stands, pitch, home end, away fans) are kept as data so
pictures can be made from them - and, later, the match engine.
"""

import json
import os

import pygame

DIR = os.path.join("data", "world", "clubs")
ROLL_FILE = os.path.join("data", "world", "honours.json")
ORDER = ["league", "second_tier", "second_tier_playoffs", "association_cup", "league_cup", "champions_cup", "shield",
         "world_club"]
_PROFILES = {}
_ROLL = None
_IMG = {}


def _slug(club):
    return club.get("short", club.get("name", "")).lower().replace(" ", "_")


def profile(club):
    """The club's profile (or None - not written yet)."""
    k = _slug(club)
    if k not in _PROFILES:
        try:
            _PROFILES[k] = json.load(open(os.path.join(DIR, k + ".json"), encoding="utf-8"))
        except (OSError, ValueError):
            _PROFILES[k] = None
    return _PROFILES[k]


def roll():
    global _ROLL
    if _ROLL is None:
        try:
            _ROLL = json.load(open(ROLL_FILE, encoding="utf-8"))
        except (OSError, ValueError):
            _ROLL = {"competitions": {}, "roll": {}}
    return _ROLL


def _played(career):
    """{key: {year: [winner, runner-up]}} - the seasons played in this career (career["history"])."""
    out = {"league": {}, "second_tier": {}, "second_tier_playoffs": {}}
    if not career:
        return out
    from career import league
    clubs = career.get("clubs", [])
    nm = lambda i: clubs[i]["name"] if 0 <= i < len(clubs) else None
    for h in career.get("history", []):
        y = h.get("year_end") or league.FIRST_SEASON + h.get("season", 1)
        t = h.get("tables") or {}
        if t.get("pl"):
            out["league"][y] = [nm(t["pl"][0]), nm(t["pl"][1])]
        elif h.get("champion") is not None:
            out["league"][y] = [nm(h["champion"]), None]
        if t.get("d1"):
            out["second_tier"][y] = [nm(t["d1"][0]), nm(t["d1"][1])]
        if len(h.get("up") or []) >= 3:
            out["second_tier_playoffs"][y] = [nm(h["up"][2]), None]
    for h in career.get("cup_history", []):                 # (career/cups.py: the cups played since)
        for key in ("association_cup", "league_cup", "champions_cup", "shield", "world_club"):
            if h.get(key + "_names") and h[key + "_names"][0] != "?":
                out.setdefault(key, {})[h.get(key + "_year") or h.get("year_end")] = h[key + "_names"]
    return out


def honours(name, career=None):
    """[(competition name, [years won])] for a club, from the roll of honour (biggest first) - and,
    with the career, the seasons played since."""
    r = roll()
    played = _played(career)
    out = []
    for key in ORDER:
        years = sorted(int(y) for y, v in r["roll"].get(key, {}).items() if v[0] == name)
        years += sorted(y for y, v in played.get(key, {}).items() if v[0] == name)
        if years:
            out.append((r["competitions"].get(key, key), years))
    return out


def runners_up(name, key="league", career=None):
    years = sorted(int(y) for y, v in roll()["roll"].get(key, {}).items() if v[1] == name)
    return years + sorted(y for y, v in _played(career).get(key, {}).items() if v[1] == name)


def image(club, which, size=None, career=None):
    """The crest / ground picture as a surface (fitted inside size=(w, h)), or None.  With the career:
    the ground as it is now (a rebuilt stand's new pictures - career/stadium.py)."""
    pr = profile(club)
    if not pr:
        return None
    if career is not None:
        from career import stadium
        path = stadium.images(career, club).get(which)
    else:
        path = (pr.get("ground", {}).get("images") or {}).get(which)
    if not path:
        return None
    key = (path, size)
    if key not in _IMG:
        try:
            img = pygame.image.load(path)
            img = img.convert_alpha() if pygame.display.get_surface() else img
            if size:
                w, h = img.get_size()
                k = min(size[0] / w, size[1] / h)
                img = pygame.transform.smoothscale(img, (max(1, int(w * k)), max(1, int(h * k))))
            _IMG[key] = img
        except (pygame.error, OSError):
            _IMG[key] = None
    return _IMG[key]


def season(y):
    """1893 -> '1892-93'."""
    return f"{y - 1}-{str(y)[-2:]}"
