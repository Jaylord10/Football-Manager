"""
career/finance.py
=================
Money: club finances, player wages and contracts, and what players are worth.
On Premier League scale (real figures):

INCOME
  - central money (TV and league commercial): every club gets the same
    equal share - £95.1m in 2023/24 (UK + overseas TV + central commercial)
    - paid in ten monthly instalments August-May, plus facility fees (~£15m,
    for televised games), plus a merit payment at the end of the season of
    ~£2.8m per place (top club ~£56m, bottom ~£2.8m).  Top club in total
    ~£176m, bottom ~£110m.
  - matchday: every home game, the crowd x the average ticket (a big
    club's 70,000+ at ~£80 is ~£110m a season, a small one's 25,000 ~£20m)
  - commercial: sponsorship, shirts, tours - £20m (small) to £300m+ (the
    biggest), monthly

SPENDING
  - player wages: Premier League wage bills run from ~£200m a year (the
    biggest) down to ~£33m (the smallest) - 2024/25 estimates
  - the rest of a real club's wage bill.  The players' own pay above is
    like Capology's estimates (Man City ~£4.5m a week, ~£234m a year), but
    the wages in a club's accounts are nearly double (Man City £408m,
    Liverpool £428m in 2024/25 - 61% of Liverpool's income), because they
    also hold:
      * BONUSES and APPEARANCE FEES - for wins and for every game a player
        plays (paid month by month), for winning the league or a cup, for
        promotion;
      * employer's NATIONAL INSURANCE - 15% of everyone's pay (the UK rate
        since April 2025);
      * the STAFF - coaches, medical, analysts, scouts, the office: STAFF
        of income;
      * the ACADEMY - the U21s and U18s, their coaches and the training
        ground (a top-category academy must spend at least £2.5m a year;
        the big clubs spend far more).
  - running the club (the stadium, travel, kit, insurance, write-downs of
    past transfer fees...): OTHER_COSTS of income.
  Deloitte, 2024/25: Premier League income £6.8bn, wages £4.4bn (65%),
  everything else left an operating profit of only £263m (8 clubs out of
  20 made one) - and after transfers the league lost £948m before tax.
  So here, before transfers, a club keeps only a few per cent of its
  income; buying players tips many into a loss.

WHAT A PLAYER IS WORTH (like Transfermarkt): it doubles every 6 rating
points - a 60 is ~£8m, 65 ~£15m, 70 ~£27m, 75 ~£48m, 80 ~£85m - more for
youngsters with potential, less in his thirties and when his contract is
running out.

CONTRACTS: every player has a weekly wage and a contract to 30 June of a
year.  (Renewals and players leaving for free come next.)

A club's size (how much money it makes) comes from its place in the
world's pecking order (data/world/clubs.csv, strongest first).

THE SPANISH LEAGUE (career/spain.py) has its own money (LEAGUE["es"]),
from LaLiga's real figures (2024/25, EUR converted to GBP at ~0.85):
  - TV: 50% shared equally (~£25m each), 25% by where you finish (~£24m
    for the champions down to ~£1m), 25% by "social implantation"
    (crowds, audiences: the big clubs' share ~£60m, the smallest ~£6m) -
    Real Madrid / Barcelona took ~£114m, the smallest clubs ~£32m
  - a far steeper pecking order than the Premier League: two giants with
    huge commercial income, then a long way down
"""

import datetime as dt
import random

from career import calendar as cal
from career import clubs as clubs_mod

M = 1_000_000

# --- Club size, by rank (0 = biggest) ------------------------------------------------
WAGE_BILL = (200 * M, 35 * M, 1.8)       # top, bottom, curve
CAPACITY = (75_000, 25_000, 1.5)
TICKET = (80, 40, 1.2)                   # average £ per fan
COMMERCIAL = (300 * M, 20 * M, 2.5)
BALANCE = (150 * M, 20 * M, 1.5)         # money in the bank at the start
CROWD_FULL = 0.97                        # Premier League grounds are ~97% full

# --- Central money (2023/24) ---------------------------------------------------------
EQUAL_SHARE = 95.1 * M                   # every club
FACILITY_FEES = 15 * M                   # TV appearances, roughly - every club here
MERIT_PER_PLACE = 2.8 * M                # x (21 - position)
CENTRAL_MONTHS = (8, 9, 10, 11, 12, 1, 2, 3, 4, 5)
OTHER_COSTS = 0.30                       # running the club (stadium, travel, write-downs...): share of income
STAFF = 0.12                             # coaches, medical, scouts, the office: share of income
NI = 0.15                                # employer's National Insurance on all pay (UK, from April 2025)
WIN_BONUS = 0.004                        # each league win: this x the players' yearly wages, between them
APPEARANCE = 0.2                         # each game a player plays (league or cup): this x his weekly wage
TROPHY_BONUS = 0.10                      # winning the league, or promotion: x the players' yearly wages
CUP_BONUS = {"association_cup": 0.04, "league_cup": 0.02, "champions_cup": 0.08, "shield": 0.04,
             "world_club": 0.02}         # ...and the cups
# Elsewhere (Division 1, Spain, Germany, Italy) the wage bills above are already the accounts' totals
# (the Championship's ~£9m-65m; Deloitte's figures abroad), so the staff and NI there come out of the
# old 40% running costs instead - about the same money as before, split into its parts:
COSTS = {"pl": (OTHER_COSTS, STAFF, True)}                # other, staff, NI on the players' wages?
COSTS_ELSEWHERE = (0.28, 0.08, False)
ACADEMY = {"pl": (16 * M, 3 * M, 1.5), "d1": (4 * M, 1 * M, 1.5), "es": (12 * M, 1.5 * M, 2.0),
           "de": (12 * M, 1.5 * M, 2.0), "it": (10 * M, 1.5 * M, 2.0)}       # the U21s and U18s, a year
RESERVE = 0.6                            # money in the bank above this x a season's income...
AI_CUSHION = 0.10                        # AI clubs' transfer budgets: keep this x a season's income in the bank,
AI_BANK_SPEND = 0.6                      # ...spend this share of the rest
AI_SURPLUS_SPEND = 0.8                   # ...and of this season's expected surplus

# --- Each league's money (the Premier League figures above are "pl") ---------------
LEAGUE = {
    "pl": {"wage_bill": WAGE_BILL, "capacity": CAPACITY, "ticket": TICKET, "commercial": COMMERCIAL,
           "balance": BALANCE, "crowd": CROWD_FULL, "central": EQUAL_SHARE + FACILITY_FEES,
           "size_share": (0, 0, 1.0), "merit": MERIT_PER_PLACE},
    "es": {"wage_bill": (210 * M, 22 * M, 2.6), "capacity": (80_000, 9_000, 2.0), "ticket": (60, 25, 1.5),
           "commercial": (400 * M, 8 * M, 4.0), "balance": (100 * M, 5 * M, 2.0), "crowd": 0.80,
           "central": 25 * M, "size_share": (60 * M, 6 * M, 2.5), "merit": 1.19 * M},
    # DIVISION 1 (career/divisions.py) - the Championship's real scale (2023/24-2024/25): the EFL's
    # central money ~£9m a club (basic award + the Premier League's solidarity payment), no merit
    # money; wage bills ~£9m (the smallest) to ~£65m (a big club just down - more with parachute
    # payments, which come next); grounds 10,000-38,000 about 80% full at ~£22-35 a ticket
    # GERMANY and ITALY (career/foreign.py) - Deloitte's figures, roughly (2023/24, EUR at ~0.85): the
    # Bundesliga's biggest wage bill ~£300m (one giant), the smallest ~£20m, grounds ~93% full and cheap
    # tickets; Serie A's wage bills ~£230m down to ~£20m, grounds ~75% full, TV money shared more evenly
    "de": {"wage_bill": (260 * M, 20 * M, 2.6), "capacity": (81_000, 15_000, 1.4), "ticket": (40, 22, 1.2),
           "commercial": (450 * M, 8 * M, 4.0), "balance": (100 * M, 5 * M, 2.0), "crowd": 0.93,
           "central": 40 * M, "size_share": (40 * M, 5 * M, 2.0), "merit": 1.0 * M},
    "it": {"wage_bill": (230 * M, 18 * M, 2.2), "capacity": (75_000, 12_000, 1.4), "ticket": (45, 20, 1.3),
           "commercial": (250 * M, 6 * M, 3.0), "balance": (60 * M, 3 * M, 2.0), "crowd": 0.75,
           "central": 35 * M, "size_share": (50 * M, 5 * M, 2.0), "merit": 1.2 * M},
    "d1": {"wage_bill": (65 * M, 9 * M, 1.8), "capacity": (38_000, 10_000, 1.5), "ticket": (35, 22, 1.2),
           "commercial": (25 * M, 2 * M, 2.0), "balance": (25 * M, 2 * M, 1.5), "crowd": 0.80,
           "central": 9 * M, "size_share": (0, 0, 1.0), "merit": 0},
}


# --- Going up and down (career/divisions.py) - the Premier League's real rules ------------
# PARACHUTE PAYMENTS for a relegated club: 55% of the Premier League's equal share in the first
# season down, 45% in the second, 20% in the third - the third only for a club that had more than
# one season up (Premier League rules since 2016/17; ~£49m / £40m / £17m in 2023/24).  They stop if
# the club goes back up.  Division 1 clubs WITHOUT parachute money get a "solidarity" payment
# instead (30% of the third-year parachute, ~£5m - part of Division 1's central money above).
PARACHUTE = (0.55, 0.45, 0.20)
SOLIDARITY = 0.30 * 0.20 * EQUAL_SHARE
# Sponsors, shirt deals and ticket prices follow a club up or down: a relegated club's commercial
# income falls about a third at once (relegation clauses in shirt and kit deals), tickets ~15%;
# a promoted club's climb part of the way at once.  Then, each summer, half of what's left of the
# gap to a club of its size in its new division.
DROP_COMMERCIAL, DROP_TICKET = 0.35, 0.15
CLIMB_NOW = 0.4                          # promoted: this share of the gap straight away
PROMOTED_LIFT = 1.3                      # ...to at least this x what it made in Division 1 (bonus clauses in kit deals)
GLIDE = 0.5                              # each summer after: this share of what's left
# RELEGATION WAGE CUTS: most Premier League contracts cut a player's wage if the club goes down -
# usually 25-50% (Norwich 2022 and Tottenham's contracts: 50%; Arsenal's reportedly 25%).  Each
# club has its standard clause; your contracts can set it player by player (career/contracts.py).
CLUB_CLAUSES = (25, 30, 40, 40, 50)


def club_clause(club):
    """The club's standard relegation wage cut (%) - the same all career."""
    return random.Random(f"clause:{club.get('name')}").choice(CLUB_CLAUSES)


def league_of(club):
    return club.get("league", "pl")


def _lg(club):
    return LEAGUE[league_of(club)]
INVEST = 0.5                             # ...this share of it goes on the stadium, facilities, debts, owners

# --- Player value -------------------------------------------------------------------
VALUE_AT_65 = 15 * M
VALUE_DOUBLES = 6.0                      # rating points
VALUE_AGE = {16: 0.9, 17: 0.95, 18: 1.0, 19: 1.05, 20: 1.1, 21: 1.1, 22: 1.1, 23: 1.05, 24: 1.0, 25: 1.0,
             26: 1.0, 27: 0.95, 28: 0.85, 29: 0.75, 30: 0.62, 31: 0.5, 32: 0.38, 33: 0.28, 34: 0.2, 35: 0.15}
POTENTIAL_COUNTS = {16: 0.7, 17: 0.65, 18: 0.6, 19: 0.55, 20: 0.5, 21: 0.4, 22: 0.3, 23: 0.2}
CONTRACT_VALUE = {0: 0.45, 1: 0.8}       # under 1 year left / 1-2 years: x this
VALUE_MIN = 0.1 * M
KEEPER = 0.6                             # keepers cost and earn less (record fees ~£70m v £100m+ outfield)

# --- Wages -------------------------------------------------------------------------
WAGE_DOUBLES = 8.0                       # within a club: a player 8 rating points better earns 2x
WAGE_AGE_YOUNG = {16: 0.15, 17: 0.2, 18: 0.3, 19: 0.45, 20: 0.6, 21: 0.75}   # youngsters earn less
CONTRACT_YEARS = {16: (2, 3), 17: (2, 3), 18: (2, 4), 19: (2, 4), 20: (2, 5), 30: (1, 3), 32: (1, 2)}


def _curve(top, bottom, power, rank, n):
    x = (n - 1 - rank) / max(1, n - 1)          # 1 for the biggest, 0 for the smallest
    return bottom + (top - bottom) * x ** power


def money(x):
    """'£12.5m', '£850k'"""
    if abs(x) >= M:
        v = x / M
        return f"£{v:,.1f}m" if abs(v) < 100 else f"£{v:,.0f}m"
    return f"£{x / 1000:,.0f}k"


def weekly(x):
    return f"£{x / 1000:,.0f}k/wk" if x >= 1000 else f"£{x:,.0f}/wk"


# ---------------------------------------------------------------------------
# Value and wages
# ---------------------------------------------------------------------------
def contract_years_left(p, date):
    end = p.get("contract_end")
    if not end:
        return 3
    return max(0.0, cal.days_between(date, end) / 365.25)


def value(p, date=None):
    """What he's worth on the market (£)."""
    rating = clubs_mod.overall(p)
    age = p.get("Age", 26)
    pot = p.get("Potential") or rating
    eff = rating + max(0.0, pot - rating) * POTENTIAL_COUNTS.get(age, 0.0)
    v = VALUE_AT_65 * 2 ** ((eff - 65) / VALUE_DOUBLES)
    v *= VALUE_AGE.get(age, 0.1 if age > 35 else 1.0)
    if p.get("Pos") == "GK":
        v *= KEEPER
    if date:
        left = contract_years_left(p, date)
        v *= CONTRACT_VALUE.get(int(left), 1.0)
    v = max(VALUE_MIN, v)
    # Round like a transfer fee
    step = 5 * M if v >= 50 * M else M if v >= 10 * M else 0.25 * M if v >= M else 0.05 * M
    return round(v / step) * step


def _wage_weight(p):
    w = 2 ** ((clubs_mod.overall(p) - 65) / WAGE_DOUBLES)
    if p.get("Pos") == "GK":
        w *= KEEPER
    return w * WAGE_AGE_YOUNG.get(p.get("Age", 26), 1.0)


def set_wages(club, total):
    """Share a yearly wage bill across the squad by quality (and youngsters less)."""
    weights = {p["id"]: _wage_weight(p) for p in club["players"]}
    s = sum(weights.values()) or 1.0
    for p in club["players"]:
        annual = total * weights[p["id"]] / s
        p["wage"] = _round_wage(annual / 52)


def _round_wage(w):
    step = 5000 if w >= 50000 else 1000 if w >= 10000 else 250
    return max(500, int(round(w / step) * step))


def fair_wage(p, club_size_rank, n=20, league="pl"):
    """What a player like him would earn at a club of this size (£/week) - for new contracts."""
    total = _curve(*LEAGUE[league]["wage_bill"], club_size_rank, n)
    per_player = total / 25 / 52                 # an average squad member
    return _round_wage(per_player * _wage_weight(p) / 1.15)


def give_contract(p, start_year, rng):
    lo, hi = (2, 5)
    for a in sorted(CONTRACT_YEARS):
        if p.get("Age", 26) >= a:
            lo, hi = CONTRACT_YEARS[a]
    years = rng.randint(lo, hi)
    p["contract_end"] = dt.date(start_year + years, 6, 30).isoformat()


def wage_bill(club):
    """A year's wages: his own players (a loanee: the share this club pays) + its share of players lent out."""
    own = sum(p.get("wage", 0) * (p["loan"]["share"] if p.get("loan") else 1.0) for p in club["players"])
    return (own + sum(e.get("wage_part", 0) for e in club.get("loaned_out", []))) * 52


# ---------------------------------------------------------------------------
# Setting up a career's finances
# ---------------------------------------------------------------------------
def league_clubs(career, club):
    """The clubs in the same league (division) as this one."""
    lg = league_of(club)
    if lg == "es" and "spain" in career:
        return career["spain"]["clubs"]
    if lg in ("de", "it") and "leagues" in career and lg in career["leagues"]:
        return career["leagues"][lg]["clubs"]               # (career/foreign.py - from the real career)
    return [c for c in career["clubs"] if league_of(c) == lg]


def league_size(career, club):
    return len(league_clubs(career, club))


def size_rank(career, club):
    """0 = the biggest club in its league (the world's order: strongest first by id)."""
    order = sorted(league_clubs(career, club), key=lambda c: -c.get("strength", 0))
    return next(i for i, c in enumerate(order) if c["id"] == club["id"])


def stature(career, club):
    """Where a club stands in the Premier League's pecking order (0 = the biggest) -
    for any club: a Spanish club counts as the Premier League clubs it's bigger than."""
    if league_of(club) == "pl":
        return size_rank(career, club)
    pl = [c for c in (career.get("pl_clubs") or career["clubs"]) if league_of(c) == "pl"]
    if league_of(club) == "d1":
        return len(pl) + size_rank(career, club)       # (Division 1: smaller than every Premier Division club)
    return sum(1 for c in pl if c.get("strength", 0) > club.get("strength", 0))


def init(career, seed=2026, only=None):
    """Give every club its finances and every player a contract - the same in every career.
    only: just these clubs (a new division joining an older save)."""
    rng = random.Random(seed)
    year = career.get("year", 2026)
    for c in (career["clubs"] if only is None else only):
        n = league_size(career, c)
        r = size_rank(career, c)
        lg = _lg(c)
        bill = _curve(*lg["wage_bill"], r, n)
        c["finance"] = {
            "balance": round(_curve(*lg["balance"], r, n)),
            "capacity": int(round(_curve(*lg["capacity"], r, n), -2)),
            "ticket": round(_curve(*lg["ticket"], r, n)),
            "commercial": round(_curve(*lg["commercial"], r, n)),
            "season": _empty_season(),
            "history": [],
        }
        set_wages(c, bill)
        for p in c["players"]:
            give_contract(p, year, rng)
        set_budgets(career, c)


def _empty_season():
    return {"tv": 0, "matchday": 0, "commercial": 0, "prize": 0, "transfers_in": 0,
            "wages": 0, "bonuses": 0, "staff": 0, "academy": 0, "ni": 0, "other": 0, "transfers_out": 0}


SPEND_KINDS = ("wages", "bonuses", "staff", "academy", "ni", "other", "transfers_out")


def academy_cost(career, club):
    """The U21s and U18s for a year (bigger clubs spend more)."""
    lg = league_of(club)
    top, bottom, power = ACADEMY.get(lg, ACADEMY["d1"])
    return _curve(top, bottom, power, size_rank(career, club), len(league_clubs(career, club)))


def _costs(club):
    return COSTS.get(league_of(club), COSTS_ELSEWHERE)


def _costs_of(club, amount):
    """Each bit of income brings its share of running costs and staff (and the staff's NI)."""
    other, staff, _ = _costs(club)
    _book(club, "other", -other * amount)
    _book(club, "staff", -staff * amount)
    _book(club, "ni", -NI * staff * amount)


def bonus(career, club, share, why=None):
    """Bonuses for the players: share x their yearly wages (plus NI)."""
    if "finance" not in club:
        return 0
    amount = share * wage_bill(club)
    _book(club, "bonuses", -amount)
    if _costs(club)[2]:
        _book(club, "ni", -NI * amount)
    return amount


def _last_month(career, club, m):
    """(league wins, appearance fees) for the month before month m (English clubs): the win bonuses, and
    APPEARANCE x his weekly wage for every league or cup game each player played."""
    from career import league, cups
    y = career.get("year", 2026) + (1 if m <= 7 else 0)
    pm, py = (m - 1, y) if m > 1 else (12, y - 1)
    prefix = f"{py}-{pm:02d}"
    cid = club["id"]
    wage = {p["id"]: p.get("wage", 0) for p in club["players"]
            if not (p.get("terms") or {}).get("appearance")}      # (his own contract's fees: career/contracts.py)
    wins, fees = 0, 0.0
    def played(r, side):
        return sum(APPEARANCE * wage.get(a["id"], 0) for a in r.get("players", [])
                   if a.get("team") == side and a.get("minutes", 0) > 0)
    try:
        for md, day in league.results_of(career, cid).items():
            d = league.match_date(career, int(md)) or ""
            if not d.startswith(prefix):
                continue
            for r in day:
                if cid in (r["home"], r["away"]):
                    side = 0 if r["home"] == cid else 1
                    f, a = (r["hg"], r["ag"]) if side == 0 else (r["ag"], r["hg"])
                    wins += f > a
                    fees += played(r, side)
        for mt in cups.all_matches(career):
            r = mt.get("result")
            if r and cid in (mt["home"], mt["away"]) and mt["date"].startswith(prefix):
                fees += played(r, 0 if mt["home"] == cid else 1)
    except Exception:
        return wins, fees
    return wins, fees


def parachute_now(club):
    """This season's parachute payment (instead of the solidarity payment) - 0 if none."""
    pc = (club.get("finance") or {}).get("parachute") or []
    if not pc or league_of(club) != "d1":
        return 0.0
    return pc[0] - SOLIDARITY


def expected_income(career, club):
    f = club["finance"]
    lg = _lg(club)
    n = len(league_clubs(career, club))
    home_games = (n - 1)
    pos = size_rank(career, club) + 1                       # expected to finish about where they rank
    central = lg["central"] + _size_share(career, club) + lg["merit"] * (n + 1 - pos) + parachute_now(club)
    gate = home_games * f["capacity"] * lg["crowd"] * f["ticket"]
    return central + gate + f["commercial"]


def set_budgets(career, club):
    """The board's budgets for the season: wages (a share of income, never below
    the current bill) and transfers (some of the cash in the bank)."""
    f = club["finance"]
    income = expected_income(career, club)
    bill = wage_bill(club)
    f["wage_budget"] = round(max(bill * 1.05, min(income * 0.45, bill * 1.25)), -5)
    other, staff, ni = _costs(club)
    surplus = income * (1 - other - staff * (1 + NI)) - f["wage_budget"] * (1 + (NI if ni else 0)) * 1.1 \
        - academy_cost(career, club)
    if club["id"] == career.get("my_club"):
        f["transfer_budget"] = round(max(0.0, 0.35 * f["balance"] + 0.5 * surplus), -5)
    else:
        # AI clubs spend to improve, like real ones: most of their spare money, keeping a cushion
        cushion = AI_CUSHION * income
        f["transfer_budget"] = round(max(0.0, AI_BANK_SPEND * (f["balance"] - cushion) + AI_SURPLUS_SPEND * surplus), -5)


# ---------------------------------------------------------------------------
# Money in and out during the season
# ---------------------------------------------------------------------------
def _book(club, kind, amount):
    f = club["finance"]
    f["balance"] = round(f["balance"] + amount)
    f["season"][kind] = round(f["season"].get(kind, 0) + abs(amount))


def daily(career, club, date):
    """Called for each day (career/training.py run_days): monthly payments on the 1st."""
    if "finance" not in club:
        return
    d = cal.parse(date)
    if d.day != 1:
        return
    f = club["finance"]
    month(career, club, d.month)


def _size_share(career, club):
    """Spain: the TV money shared by size (crowds, audiences).  (None in the Premier League.)"""
    top, bottom, power = _lg(club)["size_share"]
    if not top:
        return 0.0
    return _curve(top, bottom, power, size_rank(career, club), len(league_clubs(career, club)))


def month(career, club, m):
    """A month's money: central payments (August-May), commercial, wages, running costs."""
    f = club["finance"]
    income = 0.0
    if m in CENTRAL_MONTHS:
        tv = (_lg(club)["central"] + _size_share(career, club) + parachute_now(club)) / len(CENTRAL_MONTHS)
        _book(club, "tv", tv)
        income += tv
    _book(club, "commercial", f["commercial"] / 12)
    income += f["commercial"] / 12
    bill = wage_bill(club)
    _book(club, "wages", -bill / 12)
    if _costs(club)[2]:
        _book(club, "ni", -NI * bill / 12)
    _book(club, "academy", -academy_cost(career, club) / 12)
    _costs_of(club, income)
    if league_of(club) in ("pl", "d1"):
        wins, fees = _last_month(career, club, m)
        if wins:
            bonus(career, club, WIN_BONUS * wins)
        if fees:
            _book(club, "bonuses", -fees)
            if _costs(club)[2]:
                _book(club, "ni", -NI * fees)
    elif m in CENTRAL_MONTHS:
        bonus(career, club, (WIN_BONUS * 18 + APPEARANCE * 0.6 * 40 / 52) / len(CENTRAL_MONTHS))   # (abroad: roughly)


def home_game(career, club, attendance=None):
    """Gate money for a home match: the crowd (career/crowds.py - or, without one, the league's usual
    share of the seats) x the ticket."""
    if "finance" not in club:
        return
    f = club["finance"]
    crowd = attendance if attendance is not None else f["capacity"] * _lg(club)["crowd"]
    gate = crowd * f["ticket"]
    _book(club, "matchday", gate)
    _costs_of(club, gate)


def season_end(career, table):
    """Merit payments, the season's accounts into history, new budgets.  table: one league's."""
    n = len(table)
    by_id = {c["id"]: c for c in career["clubs"]}
    for pos, row in enumerate(table, start=1):
        club = by_id[row["club"]]
        if "finance" not in club:
            continue
        prize = _lg(club)["merit"] * (n + 1 - pos)
        _book(club, "prize", prize)
        _costs_of(club, prize)
        if pos == 1:
            bonus(career, club, TROPHY_BONUS)              # (the title bonus)
        month(career, club, 6)                             # June (July: the new season's days)
        f = club["finance"]
        s = f["season"]
        # Real clubs don't sit on piles of cash: some of the surplus goes into the
        # ground, the training centre, paying off debts - or to the owners
        reserve = RESERVE * expected_income(career, club)
        if f["balance"] > reserve:
            spend = INVEST * (f["balance"] - reserve)
            _book(club, "other", -spend)
            f["invested"] = round(f.get("invested", 0) + spend)
        income = s["tv"] + s["matchday"] + s["commercial"] + s["prize"] + s["transfers_in"]
        spend = sum(s.get(k, 0) for k in SPEND_KINDS)
        f["history"].append({"year": career.get("year"), "position": pos, "income": income, "spend": spend,
                             "profit": income - spend, "balance": f["balance"], "league": league_of(club)})
        if f.get("parachute") and league_of(club) == "d1":
            f["parachute"] = f["parachute"][1:]             # (that season's payment's been made)
        if league_of(club) == "pl":
            club["pl_seasons"] = club.get("pl_seasons", 5) + 1     # (seasons up in a row; the world's clubs: established)
        f["season"] = _empty_season()


def new_season(career, rng=None):
    """Summer: anyone without a contract (the youth intake) gets one; new budgets.
    (Expired contracts have gone - career/contracts.py summer_departures.)"""
    rng = rng or random.Random()
    year = career.get("year", 2026)
    for c in career["clubs"]:
        if "finance" not in c:
            continue
        n = league_size(career, c)
        r = size_rank(career, c)
        _glide(c)
        for p in c["players"]:
            end = p.get("contract_end")
            if not end or cal.parse(end) < dt.date(year, 7, 1):
                give_contract(p, year, rng)
                p["wage"] = max(p.get("wage", 0), fair_wage(p, r, n, league_of(c)))
        set_budgets(career, c)


def ensure(career):
    """Older saves: set finances up the first time they're loaded."""
    missing = [c for c in career["clubs"] if "finance" not in c]
    if len(missing) == len(career["clubs"]):
        init(career)
    elif missing:
        init(career, seed=career.get("year", 2026) + 1888, only=missing)


# ---------------------------------------------------------------------------
# Going up and down (career/divisions.py promote)
# ---------------------------------------------------------------------------
def _targets(career, club):
    """What a club of this size makes in its (new) division: commercial income and ticket price."""
    lg = _lg(club)
    r, n = size_rank(career, club), league_size(career, club)
    return _curve(*lg["commercial"], r, n), _curve(*lg["ticket"], r, n)


def _glide(club):
    f = club.get("finance") or {}
    for k in ("commercial", "ticket"):
        t = f.get(k + "_target")
        if t is None:
            continue
        f[k] = round(f[k] + (t - f[k]) * GLIDE)
        if abs(f[k] - t) <= 0.02 * t:
            f[k] = round(t)
            f.pop(k + "_target", None)


def relegated(career, club):
    """Down: the parachute, smaller sponsors and tickets, and the players' relegation clauses.
    Returns (wage bill a week before, after)."""
    f = club["finance"]
    seasons = club.get("pl_seasons", 5)
    f["parachute"] = [round(x * EQUAL_SHARE) for x in PARACHUTE[:3 if seasons > 1 else 2]]
    club["pl_seasons"] = 0
    com, tic = _targets(career, club)
    f["commercial"] = round(f["commercial"] * (1 - DROP_COMMERCIAL))      # (never up on the way down)
    f["ticket"] = round(f["ticket"] * (1 - DROP_TICKET))
    f["commercial_target"], f["ticket_target"] = min(com, f["commercial"]), min(tic, f["ticket"])
    before = after = 0
    default = club_clause(club)
    for p in club["players"]:
        if p.get("loan") and p["loan"].get("from") != club["id"]:
            continue                                     # (on loan here: his contract's with his own club)
        w = p.get("wage", 0)
        before += w
        cut = p.get("releg_cut", default) or 0
        if cut and w:
            p["cut_from"] = w
            p["wage"] = _round_wage(w * (1 - cut / 100.0))
        after += p.get("wage", 0)
    return before, after


def promoted(career, club):
    """Up: Premier Division money - the parachute stops; sponsors and tickets climb; any wages cut
    by a relegation clause go back to what they were."""
    f = club["finance"]
    f["parachute"] = []
    club["pl_seasons"] = 0
    com, tic = _targets(career, club)
    com = max(com, f["commercial"] * PROMOTED_LIFT)                      # (never down on the way up)
    tic = max(tic, f["ticket"] * 1.1)
    f["commercial"] = round(f["commercial"] + (com - f["commercial"]) * CLIMB_NOW)
    f["ticket"] = round(f["ticket"] + (tic - f["ticket"]) * CLIMB_NOW)
    f["commercial_target"], f["ticket_target"] = com, tic
    for p in club["players"]:
        if p.get("cut_from"):
            p["wage"] = max(p.get("wage", 0), p.pop("cut_from"))
    bonus(career, club, TROPHY_BONUS)                        # (the promotion bonus)
