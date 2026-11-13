"""
career/ffp.py
=============
Financial fair play - a simple version of the real rules for 2026-27.

From 2026-27 the Premier League's old loss limit (PSR) is replaced by a SQUAD COST RATIO, and the
Championship has its own version:
  - squad costs = players' wages (and bonuses) + transfer fees spread over the contract (here: four
    years) + agents' fees;
  - they can be up to 85% of the club's income (plus profit on players sold);
  - between 85% and 30 points above it (115%): a fine;
  - above that: six points off, plus a point for every £6.5m over (Premier League);
  - in the Championship owners can put in up to £15m a season (£33m over three) to help.
Here the check is made when the season's accounts close (June), and any points come off at the start of
the next season.  On 1 March the board warns you if you're heading over.

Kept per club in club["finance"]: "buys" ([year, fee] for the last four seasons), "scr" (the last check);
points deductions in career["deductions"] = {club id: {"year": ..., "pts": ...}}.
"""

M = 1_000_000
LIMIT = 0.85                 # green: squad costs up to this x income
RED = LIMIT + 0.30           # above this: points off
FINE_SHARE = 0.25            # between the two: a fine of this x the overspend
POINTS = 6                   # above red: six points...
PER_POINT = 6.5 * M          # ...and one more for every £6.5m over
MAX_POINTS = 15
SPREAD = 4                   # transfer fees spread over this many seasons (a typical contract)
OWNER_SEASON = {"d1": 15 * M}        # owners' money that counts (Championship: £15m a season, £33m over 3)
OWNER_THREE = {"d1": 33 * M}
LEAGUES = ("pl", "d1")


def _f(club):
    return club.get("finance") or {}


def bought(career, club, fee):
    """A club pays a fee (career/transfers.py move_player): it's spread over the next four seasons."""
    f = _f(club)
    if not f or fee <= 0:
        return
    year = career.get("year", 2026)
    f.setdefault("buys", []).append([year, round(fee)])
    f["buys"] = [b for b in f["buys"] if b[0] > year - SPREAD]


def amortised(career, club):
    """This season's share of the fees paid for players (each spread over SPREAD seasons)."""
    year = career.get("year", 2026)
    return sum(fee / SPREAD for y, fee in _f(club).get("buys", []) if year - SPREAD < y <= year)


def squad_cost(career, club, season=None, part=1.0):
    s = season or _f(club).get("season", {})
    return s.get("wages", 0) + s.get("bonuses", 0) + part * amortised(career, club)


def revenue(career, club, season=None):
    s = season or _f(club).get("season", {})
    return (s.get("tv", 0) + s.get("matchday", 0) + s.get("commercial", 0) + s.get("prize", 0)
            + s.get("transfers_in", 0) + s.get("owner", 0))


def ratio(career, club, season=None, part=1.0):
    rev = revenue(career, club, season)
    return squad_cost(career, club, season, part) / rev if rev > 0 else 0.0


def _part(career):
    """How much of the season's money has gone through (July = 0 ... June = 1)."""
    d = career.get("date") or ""
    try:
        m = int(d[5:7])
    except ValueError:
        return 1.0
    return max(1, (m - 7) % 12) / 12.0


def projected(career, club):
    """Mid-season: the ratio if the rest of the season goes like the part played so far (wages and income
    run month by month, and the transfer fees' share so far)."""
    return ratio(career, club, part=_part(career))


def owner_money(career, club):
    """Division 1: the owners put money in to cover a loss - up to £15m a season, £33m over three."""
    from career import finance as fin
    lg = fin.league_of(club)
    if lg not in OWNER_SEASON:
        return 0
    f = _f(club)
    if f.get("balance", 0) >= 0:
        return 0
    year = career.get("year", 2026)
    put = [x for x in f.get("owner_log", []) if x[0] > year - 3]
    room = min(OWNER_SEASON[lg], OWNER_THREE[lg] - sum(a for _, a in put))
    amount = min(room, -f["balance"])
    if amount <= 0:
        return 0
    fin._book(club, "owner", amount)
    f["owner_log"] = put + [[year, round(amount)]]
    return amount


def check(career, club):
    """The season's accounts are in (career/finance.py season_end): within the limit, a fine, or points."""
    from career import finance as fin, transfers as trf
    lg = fin.league_of(club)
    f = _f(club)
    if lg not in LEAGUES or not f:
        return None
    owner_money(career, club)
    rev = revenue(career, club)
    cost = squad_cost(career, club)
    if rev <= 0:
        return None
    r = cost / rev
    verdict = {"year": career.get("year"), "ratio": round(r, 3), "cost": round(cost), "revenue": round(rev),
               "fine": 0, "points": 0}
    me = club["id"] == career.get("my_club")
    if r > RED:
        over = cost - RED * rev
        pts = min(MAX_POINTS, POINTS + int(over // PER_POINT))
        verdict["points"] = pts
        career.setdefault("deductions", {})[str(club["id"])] = {"year": career.get("year", 2026) + 1, "pts": pts}
        _news(career, club, f"{club['name']} broke the squad cost rules ({r:.0%} of income on the squad, "
                            f"the limit is {LIMIT:.0%}): {pts} points off next season.")
        if me:
            trf._message(career, "board", f"The league has docked us {pts} points for next season: we spent "
                                          f"{r:.0%} of our income on the squad (the limit is {LIMIT:.0%}).")
    elif r > LIMIT:
        fine = FINE_SHARE * (cost - LIMIT * rev)
        verdict["fine"] = round(fine)
        fin._book(club, "other", -fine)
        if me:
            trf._message(career, "board", f"The league has fined us {fin.money(fine)}: we spent {r:.0%} of our "
                                          f"income on the squad (the limit is {LIMIT:.0%}). Any higher than "
                                          f"{RED:.0%} and it's points.")
    f["scr"] = verdict
    return verdict


def warn(career):
    """1 March: the board's warning if you're heading over the limit."""
    from career import finance as fin, transfers as trf
    club = career["clubs"][career["my_club"]]
    if fin.league_of(club) not in LEAGUES or not _f(club):
        return
    r = projected(career, club)
    if r > RED:
        trf._message(career, "board", f"Squad costs are running at {r:.0%} of our income. Over {RED:.0%} at "
                                      f"the end of the season means points off - we need to sell or cut wages.")
    elif r > LIMIT:
        trf._message(career, "board", f"Squad costs are running at {r:.0%} of our income - over the league's "
                                      f"{LIMIT:.0%} limit. We'll be fined unless that comes down by June.")


def deduction(career, club_id):
    """Points off this season."""
    d = (career.get("deductions") or {}).get(str(club_id))
    if d and d.get("year") == career.get("year"):
        return d.get("pts", 0)
    return 0


def _news(career, club, text):
    try:
        from career import availability as av
        av._news(career, career.get("date"), club["id"], text, "board")
    except Exception:
        pass


def ai_room(career, club):
    """How much an AI club can add to its squad costs this season and stay within the limit (the
    board's own sense): a cap on its transfer budget."""
    from career import finance as fin
    if fin.league_of(club) not in LEAGUES:
        return None
    income = fin.expected_income(career, club)
    wages = fin.wage_bill(club) * 1.12                      # (with bonuses)
    room = LIMIT * income - wages - amortised(career, club)
    return max(0.0, room * SPREAD)                          # a fee costs a quarter of itself a season
