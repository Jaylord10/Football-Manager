"""
career/captains.py
==================
Captain and vice-captain.

LEADERSHIP (hidden, 1-20): how much the dressing room listens to him.  It
comes from his character (professionalism, composure, teamwork) plus chance,
and grows with age and experience.  You don't see the number - your
assistant tells you who the lads look up to once he's been at the club a
while (or as soon as you ask him to recommend a captain).

THE ARMBAND (club["captain"], club["vice"]):
  - when the captain plays, his leadership lifts the whole squad's morale a
    little (it settles a touch higher) and softens the blow of a defeat; the
    vice-captain does it when the captain's not out there.
  - being made captain is a proud moment for a man; losing the armband hurts
    (more if he's hot-headed).
AI clubs give it to their best leader among the regulars, and keep him unless
he's gone or dropped out of the side.
"""

import random

from career import morale, clubs as clubs_mod

NAMED_CAPTAIN = 5.0          # morale for the man you make captain
NAMED_VICE = 2.0
STRIPPED_CAPTAIN = -7.0      # ...and for one who loses it (x his temperament)
STRIPPED_VICE = -3.0
LIFT = 0.35                  # each point of leadership above 10: the squad's normal morale this much higher
STEADY = 0.025               # each point above 10: a defeat hurts this much less (share)
KNOW_AFTER_DAYS = 60         # your assistant can tell you about a man's leadership after this long


def leadership(p):
    """1-20 (hidden)."""
    t = morale.traits(p)
    if "lead" not in t:
        rng = random.Random(f"lead:{p['id']}:{p['Name']}")
        comp = float(p.get("Composure", 50)) / 5.0
        tw = float(p.get("Teamwork", 50)) / 5.0
        t["lead"] = round(0.3 * (t["prof"] - 10) + 0.2 * (comp - 10) + 0.15 * (tw - 10) + rng.gauss(8.5, 3.2), 1)
    age = int(p.get("Age", 25))
    return max(1.0, min(20.0, t["lead"] + 0.35 * max(-4, min(8, age - 24))))


def armband(club):
    """(captain, vice) - players or None."""
    return (clubs_mod.player_by_id(club, club.get("captain")), clubs_mod.player_by_id(club, club.get("vice")))


def leader_on_pitch(club, played_ids):
    """Whose leadership counts this match: the captain if he played, else the vice."""
    cap, vice = armband(club)
    for p in (cap, vice):
        if p is not None and p["id"] in played_ids:
            return p
    return None


def set_captain(club, pid, role="captain"):
    """Give the armband (role: captain / vice).  Returns [(player, morale change, why)]."""
    other = "vice" if role == "captain" else "captain"
    old = clubs_mod.player_by_id(club, club.get(role))
    new = clubs_mod.player_by_id(club, pid)
    if new is None or (old is not None and old["id"] == pid):
        return []
    out = []
    if club.get(other) == pid:                      # (moving him between the two)
        club[other] = None
    if old is not None:
        d = (STRIPPED_CAPTAIN if role == "captain" else STRIPPED_VICE) * morale._feel(old)
        _change(old, d)
        out.append((old, d, "lost the armband" if role == "captain" else "is no longer vice-captain"))
    club[role] = pid
    d = NAMED_CAPTAIN if role == "captain" else NAMED_VICE
    _change(new, d)
    out.append((new, d, "made captain" if role == "captain" else "made vice-captain"))
    return out


def _change(p, d):
    p["morale"] = round(max(3.0, min(98.0, morale.level(p) + d)), 1)
    why = p.setdefault("morale_why", {})
    why["captaincy"] = round(why.get("captaincy", 0.0) + d, 2)


def recommend(club):
    """Your assistant's pick: (captain, vice) from the regulars, by leadership."""
    xi = [clubs_mod.player_by_id(club, pid) for pid in (club.get("lineup") or {}).values()]
    xi = [p for p in xi if p is not None and p.get("loan", {}).get("to") in (None, club["id"])]
    xi.sort(key=lambda p: -leadership(p))
    return (xi[0] if xi else None, xi[1] if len(xi) > 1 else None)


def ai_pick(club):
    """AI clubs: keep the captain while he's here and playing; otherwise the best leader in the side."""
    xi_ids = set((club.get("lineup") or {}).values())
    for role in ("captain", "vice"):
        p = clubs_mod.player_by_id(club, club.get(role))
        if p is None or p["id"] not in xi_ids:
            club[role] = None
    cands = sorted((clubs_mod.player_by_id(club, i) for i in xi_ids), key=lambda p: -leadership(p) if p else 0)
    cands = [p for p in cands if p is not None and p["id"] not in (club.get("captain"), club.get("vice"))]
    if club.get("captain") is None and cands:
        club["captain"] = cands.pop(0)["id"]
    if club.get("vice") is None and cands:
        club["vice"] = cands.pop(0)["id"]


def assistant_view(p, club, today):
    """What your assistant says about his leadership (hidden) - once he knows the man."""
    from career import calendar as cal
    joined = p.get("joined")
    known = club.get("captain") == p["id"] or club.get("vice") == p["id"] or not joined or \
        cal.days_between(joined, today) >= KNOW_AFTER_DAYS
    if not known:
        return None
    lead = leadership(p)
    if lead >= 16:
        return "The lads look up to him - a natural leader."
    if lead >= 13:
        return "He has a voice in the dressing room."
    if lead <= 5:
        return "Quiet in the dressing room - not a leader."
    return None


def tidy(club):
    """The captain's left (sold, released, loaned out): the vice steps up."""
    here = {p["id"] for p in club["players"] if p.get("loan", {}).get("to") in (None, club["id"])}
    if club.get("vice") not in here:
        club["vice"] = None
    if club.get("captain") not in here:
        club["captain"], club["vice"] = club.get("vice"), None
