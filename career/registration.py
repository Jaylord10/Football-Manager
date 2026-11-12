"""
career/registration.py
======================
Squad registration - Premier League rules:

  - a club registers a squad of at most 25 players
  - at most 17 of them can be non-homegrown: a HOMEGROWN player spent three
    seasons at a club in this country before he turned 21 (here: three
    seasons at a league club, or came up through an academy)
  - UNDER-21s (21 or younger at the start of the season) don't need
    registering and can always play
  - the list is fixed when a transfer window closes (1 September, 2
    February); during a window you can change it freely.  A free agent
    signed outside a window can be added if there's room.
  - an unregistered senior player can't play in the league
  - and so a club can always put out a team: at least MIN_SQUAD players it
    can pick (registered + under-21s) - the board signs free agents if not

AI clubs register their best 25 (keeping to the homegrown rule).

SPANISH CLUBS (career/spain.py): 25 registered, at most 5 non-EU players;
players of 22 or under can play from the B team without a place.
"""

from career import calendar as cal
from career import clubs as clubs_mod

MAX_SQUAD = 25
MAX_NON_HOMEGROWN = 17
U21_AGE = 21
MIN_SQUAD = 18
HOMEGROWN_SHARE = 0.45      # the world's players at the start (Premier League squads: ~40-50%)
DEADLINES = ((9, 1), (2, 2))


def is_u21(p, club=None):
    """Doesn't need a place on the list (under-21s here; Spain: 22 or under, the B team)."""
    limit = 22 if club is not None and club.get("league") == "es" else U21_AGE
    return p.get("Age", 26) <= limit


def _foreign(club, p):
    """Counts against the quota: non-homegrown here, non-EU in Spain."""
    if club.get("league") == "es":
        return bool(p.get("non_eu"))
    return not homegrown(p)


def max_foreign(club):
    return 5 if club.get("league") == "es" else MAX_NON_HOMEGROWN


def foreign_label(club):
    return "non-EU" if club.get("league") == "es" else "non-homegrown"


def homegrown(p):
    return bool(p.get("homegrown"))


def seniors(club):
    return [p for p in club["players"] if not is_u21(p, club)]


def registered_ids(club):
    return set(club.get("registered", []))


def can_play(club, p):
    """Under-21s always; seniors only if registered."""
    return is_u21(p, club) or p["id"] in registered_ids(club)


def counts(club):
    reg = [p for p in club["players"] if p["id"] in registered_ids(club) and not is_u21(p, club)]
    return len(reg), sum(1 for p in reg if _foreign(club, p))


def check(club):
    """Problems with the list, or [] if it's legal."""
    n, non_hg = counts(club)
    out = []
    if n > MAX_SQUAD:
        out.append(f"{n} senior players registered - the limit is {MAX_SQUAD}")
    if non_hg > max_foreign(club):
        out.append(f"{non_hg} {foreign_label(club)} players registered - the limit is {max_foreign(club)}")
    eligible = sum(1 for p in club["players"] if can_play(club, p))
    if eligible < MIN_SQUAD:
        out.append(f"only {eligible} players can play - you need at least {MIN_SQUAD}")
    return out


def can_register(club, p):
    """(ok, reason)"""
    if is_u21(p, club):
        return True, "Under-21s don't need registering"
    n, non_hg = counts(club)
    if p["id"] in registered_ids(club):
        return True, ""
    if n >= MAX_SQUAD:
        return False, f"The squad is full ({MAX_SQUAD}) - take someone off the list first"
    if _foreign(club, p) and non_hg >= max_foreign(club):
        return False, f"No room for another {foreign_label(club)} player ({max_foreign(club)} max)"
    return True, ""


def window_open(date):
    from career import transfers
    return transfers.in_window(date)


def best_list(club):
    """The best legal 25: best players first, keeping to the homegrown rule."""
    reg, non_hg = [], 0
    for p in sorted(seniors(club), key=lambda q: -clubs_mod.overall(q)):
        if len(reg) >= MAX_SQUAD:
            break
        if _foreign(club, p):
            if non_hg >= max_foreign(club):
                continue
            non_hg += 1
        reg.append(p["id"])
    return reg


def auto_register(club):
    club["registered"] = best_list(club)


def tidy(club):
    """Drop ids of players who've left; keep the list legal (dropping the weakest)."""
    ids = {p["id"] for p in club["players"]}
    club["registered"] = [i for i in club.get("registered", []) if i in ids]
    while check_limits(club):
        reg = [p for p in club["players"] if p["id"] in registered_ids(club) and not is_u21(p, club)]
        n, non_hg = counts(club)
        pool = [p for p in reg if _foreign(club, p)] if non_hg > max_foreign(club) else reg
        worst = min(pool, key=clubs_mod.overall)
        club["registered"].remove(worst["id"])


def check_limits(club):
    n, non_hg = counts(club)
    return n > MAX_SQUAD or non_hg > max_foreign(club)


def setup(career, rng):
    """A new career / older save: homegrown flags and everyone's list."""
    for c in career["clubs"]:
        fresh = [p for p in c["players"] if "homegrown" not in p]
        for p in fresh:
            p["homegrown"] = is_u21(p) or rng.random() < HOMEGROWN_SHARE
        # Every club starts with enough homegrown seniors to fill a squad legally
        if fresh:
            snr = [p for p in seniors(c) if not homegrown(p)]
            short = (MAX_SQUAD - MAX_NON_HOMEGROWN + 1) - sum(1 for p in seniors(c) if homegrown(p))
            for p in sorted(snr, key=lambda q: rng.random())[:max(0, short)]:
                p["homegrown"] = True
        if "registered" not in c:
            auto_register(c)


def new_season(career):
    """Summer: young players at league clubs edge towards homegrown status;
    AI clubs re-register; yours is kept (and tidied) - change it in the window."""
    for c in career["clubs"]:
        for p in c["players"]:
            if not p.get("homegrown") and p.get("Age", 26) <= U21_AGE:
                p["hg_seasons"] = p.get("hg_seasons", 0) + 1
                if p["hg_seasons"] >= 3:
                    p["homegrown"] = True
        if c["id"] == career["my_club"]:
            tidy(c)
            # newcomers (youth intake are under-21; signings) - add while there's room
            for p in sorted(seniors(c), key=lambda q: -clubs_mod.overall(q)):
                if p["id"] not in registered_ids(c) and can_register(c, p)[0]:
                    c["registered"].append(p["id"])
        else:
            auto_register(c)


def deadline(career, date):
    """A window has closed: lists are fixed.  Yours is made legal if it isn't (news)."""
    from career import availability as av
    d = cal.parse(date)
    if (d.month, d.day) not in DEADLINES:
        return
    for c in career["clubs"]:
        if c["id"] != career["my_club"]:
            auto_register(c)
            continue
        before = set(c.get("registered", []))
        tidy(c)
        dropped = before - set(c["registered"])
        if dropped:
            names = ", ".join(clubs_mod.player_by_id(c, i)["Name"] for i in dropped if clubs_mod.player_by_id(c, i))
            av._news(career, date, c["id"], f"Squad registration: your list was over the limits, so {names} "
                                            f"had to be left out until the next window.", "squad")
        else:
            n, non_hg = counts(c)
            av._news(career, date, c["id"], f"The transfer window has closed: your squad list is fixed "
                                            f"({n} registered, {non_hg} non-homegrown).", "squad")
