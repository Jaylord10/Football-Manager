"""
career/contracts.py
===================
Contracts: negotiating them, renewing them, and players leaving on a free.

A CONTRACT: a weekly wage, a length (to 30 June of a year), a squad status
(the playing time you promise him), a signing-on fee, and optionally a
release clause (a fee at which he can leave - players like having one).

NEGOTIATING: every player (well, his agent) has what he wants - and what
he'd settle for:
  - WAGE: what a player like him earns at a club like yours (career/
    finance.py), more if he's already on more (nobody takes a pay cut
    to stay), more from a smaller club (a bigger one is a step up), and his
    agent's greed
  - LENGTH: youngsters and players in their thirties want security (long
    deals), players in their prime want to keep their options open
  - STATUS: what he expects from where he'd fit in your squad - promise
    him less and he wants more money; promise more and he'll take a bit less
  - a signing-on fee and a release clause make a deal sweeter
You make an offer; he accepts, or says what's wrong and what he wants.
After NEGOTIATION_ROUNDS offers without a deal, he walks away (for a few
weeks).

RENEWALS: from 1 January players in the last six months of their contract
are free to agree a move elsewhere at the end of the season - your
expiring players want talks.  AI clubs renew the players they want to
keep.  Anyone whose contract ends on 30 June leaves on a free.

FREE AGENTS: players without a club - released, out of contract, or from
outside the league (a new batch every summer).  Sign them on a contract,
no transfer fee.  AI clubs short of players sign them too.
"""

import datetime as dt
import random

from career import calendar as cal
from career import clubs as clubs_mod
from career import finance as fin

STATUSES = ["Key player", "First team", "Rotation", "Backup", "Prospect"]
STATUS_WAGE = {"Key player": 1.0, "First team": 0.92, "Rotation": 0.85, "Backup": 0.8, "Prospect": 0.75}
STATUS_GAP = 0.10            # each step below what he expects: wants this much more money
NEGOTIATION_ROUNDS = 5
WALK_AWAY_DAYS = 28
PAY_RISE_TO_STAY = 1.10      # renewing: wants at least this x his current wage
BIGGER_CLUB = 0.04           # each place higher in the pecking order: takes this much less (max 25%)
GREED = (0.95, 1.20)         # his agent
SIGNING_FEE_COUNTS = 0.5     # a signing-on fee counts as this share of its value spread over the contract
CLAUSE_WORTH = 0.05          # a release clause near his value is worth this much wage to him
FREE_AGENTS_EACH_SUMMER = 60 # new players from outside the league
SQUAD_TARGET = 25            # AI clubs below this sign free agents
MY_SQUAD_MIN = 18            # your squad never drops below this (the board signs free agents)
KEEP_SHARE = 0.70            # AI clubs renew the better 70% of their expiring players (and young prospects)


def _key(club, p):
    return f"{club['id']}:{p['id']}:{p.get('Name')}"


def expected_status(club, p):
    """Where he'd fit: the best few are key players, then first team, rotation..."""
    better = sorted((clubs_mod.overall(q) for q in club["players"] if q is not p), reverse=True)
    r = clubs_mod.overall(p)
    rank = sum(1 for x in better if x > r)
    if p.get("Age", 26) <= 19 and rank >= 11:
        return "Prospect"
    if rank < 4:
        return "Key player"
    if rank < 12:
        return "First team"
    if rank < 18:
        return "Rotation"
    return "Backup"


# ---------------------------------------------------------------------------
# Talks with his agent (FM-style): every player has a MAIN CONCERN - money,
# playing time, security (a long deal) or a big up-front payment - and holds
# out on that; on the rest he'll give ground.  His agent wants a fee too.
# Each offer is weighed as one package (wage + bonuses + signing-on fee + pay
# rises, what he'd really earn a week); get close and he comes down part of
# the way to meet you (never below what he'd really settle for).  Lowball him
# or ignore what he cares about and the agent's patience runs out.
#
# BONUSES (paid when they happen - career/contracts.py pay_bonuses):
#   appearance fee (per league game he plays), goal bonus (forwards and
#   midfielders) or clean-sheet bonus (keepers and defenders), and a yearly
#   pay rise (each 1 July).
# ---------------------------------------------------------------------------
CONCERNS = (("money", 4), ("time", 3), ("security", 2), ("signing", 2))
CONCERN_TEXT = {"money": "the money - the wage matters most to him",
                "time": "playing time - he wants to be sure he'll play",
                "security": "security - he wants a long contract",
                "signing": "a good signing-on fee"}
SETTLE = (0.86, 0.94)         # how far below his opening ask he'd really go (on the package)
MOVE = 0.45                   # an offer near enough: he comes this share of the way
NEAR = 0.88                   # ...near enough = the package is at least this x what he wants now
LOWBALL = 0.75                # below this x: the agent's insulted (patience goes twice as fast)
ROUNDS = 5
AGENT_FEE_WEEKS = (3, 8)      # the agent's fee: this many weeks of the wage (renewal: half)
GAMES_WEEK = 38 / 52.0        # league games a week (on average over a year)
PLAYS = {"Key player": 0.92, "First team": 0.78, "Rotation": 0.5, "Backup": 0.25, "Prospect": 0.15}
GOALS = {"ST": 0.42, "LW": 0.22, "RW": 0.22, "AM": 0.2, "LM": 0.12, "RM": 0.12, "CM": 0.07, "DM": 0.04}
CLEAN_SHEETS = 0.3            # per game (for keepers and defenders)
DEFENDERS = {"GK", "CB", "LB", "RB", "LWB", "RWB"}
BONUS_WORTH = 0.8             # a pound of expected bonus is worth this much wage to him (it's not guaranteed)
RISE_WORTH = 0.8
SIGNING_WORTH = {"signing": 1.0}    # (others: SIGNING_FEE_COUNTS)


STATUS_AS = {"Key player": "a key player", "First team": "a first-team player", "Rotation": "a rotation player",
             "Backup": "a backup", "Prospect": "a prospect"}


def bonus_kind(p):
    return "clean_sheet" if p.get("Pos") in DEFENDERS else "goal"


def package(p, offer, concern=None):
    """What the offer is worth to him a week (wage + expected bonuses + signing-on fee + pay rises)."""
    wage = offer["wage"]
    weeks = max(1, offer["years"] * 52)
    plays = PLAYS.get(offer.get("status", "First team"), 0.5) * GAMES_WEEK
    bonus = offer.get("appearance", 0) * plays
    if bonus_kind(p) == "goal":
        bonus += offer.get("goal_bonus", 0) * GOALS.get(p.get("Pos"), 0.05) * plays
    else:
        bonus += offer.get("goal_bonus", 0) * CLEAN_SHEETS * plays
    rise = wage * offer.get("rise", 0) / 100.0 * (offer["years"] - 1) / 2.0
    sign_w = SIGNING_WORTH.get(concern, SIGNING_FEE_COUNTS)
    return wage + BONUS_WORTH * bonus + sign_w * offer.get("signing_fee", 0) / weeks + RISE_WORTH * rise


def demands(career, club, p, renewal):
    """What he wants (his opening position) - kept for the whole negotiation."""
    rng = random.Random(f"{career.get('year')}:{club['id']}:{p['id']}:{p.get('Name')}")
    n = fin.league_size(career, club) if club["id"] >= 0 else 20
    rank = fin.size_rank(career, club) if club["id"] >= 0 else n // 2
    base = fin.fair_wage(p, rank, n, fin.league_of(club))
    here = fin.stature(career, club) if club["id"] >= 0 else n // 2
    status = expected_status(club, p) if club["id"] >= 0 else "First team"
    wage = base * rng.uniform(*GREED)
    if renewal:
        wage = max(wage, p.get("wage", 0) * PAY_RISE_TO_STAY)
    else:
        # A move: more than he's on now; a step up in club size takes a little less
        cur_rank = p.get("_from_rank")
        if cur_rank is not None:
            wage *= 1.0 - min(0.25, BIGGER_CLUB * max(0, cur_rank - here))
        wage = max(wage, p.get("wage", 0) * 1.05)
    age = p.get("Age", 26)
    years = 5 if age <= 21 else 4 if age <= 25 else 3 if age <= 29 else 2
    concern = _pick(rng, CONCERNS)
    if concern == "security":
        years = min(5, years + 1)
    wage = fin._round_wage(wage)
    weeks = rng.uniform(*AGENT_FEE_WEEKS) * (0.5 if renewal else 1.0)
    signing = 0
    if concern == "signing" or (not renewal and p.get("_from_club") is not None and rng.random() < 0.5):
        signing = _round_money(wage * rng.uniform(8, 20) if concern == "signing" else wage * rng.uniform(2, 6))
    return {"wage": wage, "years": years, "status": status, "patience": ROUNDS, "renewal": renewal,
            "concern": concern, "agent_fee": _round_money(wage * weeks), "signing_fee": signing,
            "settle": rng.uniform(*SETTLE), "releg_risk": round(releg_risk(career, club), 3)}


def _pick(rng, items):
    total = sum(w for _, w in items)
    x = rng.random() * total
    for v, w in items:
        x -= w
        if x <= 0:
            return v
    return items[-1][0]


def _round_money(x):
    step = 1_000_000 if x >= 10_000_000 else 100_000 if x >= 1_000_000 else 25_000 if x >= 100_000 else 5_000
    return int(round(x / step) * step)


def asking(want):
    """His terms as an offer (what the agent puts on the table)."""
    return {"wage": want["wage"], "years": want["years"], "status": want["status"],
            "signing_fee": want.get("signing_fee", 0), "agent_fee": want.get("agent_fee", 0),
            "appearance": 0, "goal_bonus": 0, "rise": 0, "release_clause": 0}


def releg_risk(career, club):
    """How likely he thinks the club is to go down (a Premier Division club, by its size): a relegation
    clause costs him its cut x this.  (Division 1: no relegation, no clause.)"""
    if club.get("id", -1) < 0 or fin.league_of(club) != "pl":
        return 0.0
    n, r = fin.league_size(career, club), fin.size_rank(career, club)
    return 0.02 + 0.40 * (r / max(1, n - 1)) ** 3


def _need(p, want, offer):
    """The package he needs, given what's in this offer that isn't money (status, length, a relegation
    clause - a wage cut if the club goes down: worth its cut x the chance of going down to him)."""
    need = package(p, asking(want), want.get("concern")) * want.get("give", 1.0)
    cut = offer.get("relegation_cut", 0) or 0
    if cut:
        need *= 1.0 + cut / 100.0 * want.get("releg_risk", 0.0) * (1.5 if want.get("concern") == "money" else 1.0)
    si = STATUSES.index(offer["status"])
    wi = STATUSES.index(want["status"])
    gap = STATUS_GAP * (2.0 if want.get("concern") == "time" else 1.0)
    need *= 1.0 + gap * max(0, si - wi) - 0.03 * max(0, wi - si)
    years_short = want["years"] - offer["years"]
    if years_short > 0:
        need *= 1.0 + (0.12 if want.get("concern") == "security" else 0.05) * years_short
    elif years_short < 0 and 22 <= p.get("Age", 26) <= 29:
        need *= 1.0 + 0.03 * (-years_short)
    clause = offer.get("release_clause")
    if clause:
        val = fin.value(p)
        need -= p.get("wage", offer["wage"]) * CLAUSE_WORTH * min(2.0, val / max(clause, 1))
    return need


def evaluate(career, club, p, offer, want):
    """(accepted, reply, counter_offer, insulted) - want["give"] moves as you haggle."""
    concern = want.get("concern", "money")
    need = _need(p, want, offer)
    got = package(p, offer, concern)
    si, wi = STATUSES.index(offer["status"]), STATUSES.index(want["status"])
    reasons = []
    deal_breaker = False
    if concern == "time" and si > wi:
        reasons.append(f"he wants to be {STATUS_AS[want['status']]} - playing time is what matters to him")
        deal_breaker = True
    elif si - wi >= 2:
        reasons.append(f"he expects to be {STATUS_AS[want['status']]}")
        deal_breaker = True
    if concern == "security" and offer["years"] < want["years"] - 1:
        reasons.append(f"he wants a long deal - at least {want['years'] - 1} years")
        deal_breaker = True
    agent_short = offer.get("agent_fee", 0) < want.get("agent_fee", 0) * 0.85
    if agent_short:
        reasons.append(f"his agent wants a fee of around {fin.money(want['agent_fee'])}")
    if concern == "signing" and offer.get("signing_fee", 0) < want.get("signing_fee", 0) * 0.7:
        reasons.append(f"he wants a signing-on fee - around {fin.money(want['signing_fee'])}")
        deal_breaker = True
    money_ok = got >= need * 0.985
    if not money_ok:
        reasons.append(f"the money's not there yet")
    if not reasons:
        return True, "He accepts the terms - the contract is agreed.", None, False
    insulted = got < need * LOWBALL
    # He gives ground when you're near (never below what he'd settle for)
    if not insulted and got >= need * NEAR:
        floor = want.get("settle", 0.9)
        give = want.get("give", 1.0)
        target = give - (1 - got / need) * MOVE * give
        want["give"] = max(floor, min(give, target))
        if not deal_breaker and not agent_short and got >= _need(p, want, offer) * 0.985:
            return True, "He's happy to meet you there - the contract is agreed.", None, False
    counter = dict(offer)
    need2 = _need(p, want, dict(offer, status=want["status"] if deal_breaker and si > wi else offer["status"]))
    gap = need2 - package(p, dict(offer, wage=0), concern)
    counter["wage"] = fin._round_wage(max(offer["wage"], gap))
    if si - wi >= 2 or (concern == "time" and si > wi):
        counter["status"] = want["status"]
    if concern == "security" and offer["years"] < want["years"] - 1:
        counter["years"] = want["years"]
    if agent_short:
        counter["agent_fee"] = want["agent_fee"]
    if concern == "signing" and offer.get("signing_fee", 0) < want.get("signing_fee", 0) * 0.7:
        counter["signing_fee"] = want["signing_fee"]
    return False, "Not yet: " + "; ".join(reasons) + ".", counter, insulted


def mood(t):
    """The agent's patience, in words."""
    left = t["want"]["patience"] - t["rounds"]
    return ("Happy to keep talking." if left >= 4 else "Still keen to do a deal." if left == 3 else
            "Getting impatient." if left == 2 else "One more like that and we walk." if left == 1 else
            "Walked out.")


def make_offer(career, club, p, offer, renewal):
    """Your offer.  Returns (accepted, reply)."""
    talks = career.setdefault("talks", {})
    k = _key(club, p)
    t = talks.get(k)
    today = career.get("date")
    if t and t.get("walked_until") and cal.parse(t["walked_until"]) > cal.parse(today):
        return False, f"He doesn't want to talk again yet (until {cal.fmt(t['walked_until'], False)})."
    if not t or t.get("walked_until") or "concern" not in t.get("want", {}):
        t = talks[k] = {"want": demands(career, club, p, renewal), "rounds": 0}
    want = t["want"]
    ok, reply, counter, insulted = evaluate(career, club, p, offer, want)
    if ok:
        talks.pop(k, None)
        return True, reply
    t["rounds"] += 2 if insulted else 1
    t["counter"] = counter
    if insulted:
        reply = "The agent's insulted. " + reply
    if t["rounds"] >= want["patience"]:
        t["walked_until"] = (cal.parse(today) + dt.timedelta(days=WALK_AWAY_DAYS)).isoformat()
        return False, reply + " Talks have broken down - he's walked away for now."
    return False, reply


def talk_state(career, club, p, renewal):
    """(want, rounds so far, counter) - the talks so far (want: his opening position)."""
    t = career.get("talks", {}).get(_key(club, p))
    if t and "concern" in t.get("want", {}) and not t.get("walked_until"):
        return t["want"], t["rounds"], t.get("counter"), t
    return demands(career, club, p, renewal), 0, None, None


def sign(career, club, p, offer):
    """Put an agreed contract in place (and pay the signing-on fee)."""
    year = cal.parse(career["date"]).year + (1 if cal.parse(career["date"]).month >= 7 else 0)
    p["wage"] = offer["wage"]
    p["contract_end"] = dt.date(year + offer["years"] - 1, 6, 30).isoformat()
    p["status"] = offer["status"]
    if p.get("loan"):
        from career import loans
        loans.wage_part_update(career, p)            # (a new deal while he's away on loan)
    if offer.get("release_clause"):
        p["release_clause"] = offer["release_clause"]
    else:
        p.pop("release_clause", None)
    if "relegation_cut" in offer:                   # (your contracts: set in the talks)
        p["releg_cut"] = offer["relegation_cut"]
    else:
        p.pop("releg_cut", None)                    # (the club's standard clause - career/finance.py)
    p.pop("cut_from", None)                         # (a new contract: a new wage)
    terms = {k: offer[k] for k in ("appearance", "goal_bonus", "rise") if offer.get(k)}
    if terms:
        p["terms"] = terms                          # (bonuses and pay rises: pay_bonuses / yearly_rises)
    else:
        p.pop("terms", None)
    fee = offer.get("signing_fee", 0) + offer.get("agent_fee", 0)
    if fee and "finance" in club:
        fin._book(club, "other", -fee)


def pay_bonuses(career, results):
    """After a matchday: your players' appearance fees and goal / clean-sheet bonuses (their contracts)."""
    me = career["clubs"][career["my_club"]]
    by_id = {p["id"]: p for p in me["players"] if p.get("terms")}
    if not by_id:
        return 0
    total = 0
    for r in results:
        side = 0 if r.get("home") == me["id"] else 1 if r.get("away") == me["id"] else None
        if side is None:
            continue
        conceded = r.get("ag", 0) if side == 0 else r.get("hg", 0)
        goals = {}
        for g in r.get("goals", []):
            if g.get("team") == side and not g.get("own_goal"):
                goals[g.get("pid")] = goals.get(g.get("pid"), 0) + 1
        for a in r.get("players", []):
            p = by_id.get(a.get("id")) if a.get("team") == side else None
            if p is None or not a.get("minutes"):
                continue
            t = p["terms"]
            pay = t.get("appearance", 0)
            if t.get("goal_bonus"):
                if bonus_kind(p) == "goal":
                    pay += t["goal_bonus"] * goals.get(p["id"], 0)
                elif conceded == 0 and a.get("minutes", 0) >= 60:
                    pay += t["goal_bonus"]
            total += pay
    if total:
        fin._book(me, "bonuses", -total)
    return total


def yearly_rises(career):
    """1 July: pay rises written into contracts."""
    for c in career["clubs"]:
        for p in c["players"]:
            r = (p.get("terms") or {}).get("rise")
            if r and not p.get("loan"):
                p["wage"] = fin._round_wage(p["wage"] * (1 + r / 100.0))


def wage_room(career, club):
    """Weekly wage the board still allows."""
    f = club.get("finance", {})
    return max(0, (f.get("wage_budget", 0) - fin.wage_bill(club)) / 52)


def expiring(club, date, within_days=183, career=None):
    """Contracts running out - his own players (not ones here on loan) and, with career, ones he's lent out."""
    out = []
    players = [p for p in club["players"] if not p.get("loan")]
    if career is not None:
        from career import loans
        players += [p for p, _ in loans.loans_out(career, club)]
    for p in players:
        end = p.get("contract_end")
        if end and 0 <= cal.days_between(date, end) <= within_days:
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# The calendar: January talks, AI renewals, 30 June departures
# ---------------------------------------------------------------------------
def january(career, club, date, rng):
    """1 January: your expiring players are open to talks; AI clubs renew the ones they want."""
    from career import availability as av
    exp = expiring(club, date, career=career)
    if not exp:
        return
    if club["id"] == career["my_club"]:
        names = ", ".join(f"{p['Name']} ({p['Pos']}, {p['Age']})" for p in exp)
        av._news(career, date, club["id"], f"Contracts ending in June: {names}. Offer new deals from their "
                                           f"profiles, or they leave on a free.", "contract")
        return
    for p in exp:
        if _ai_wants(club, p):
            want = demands(career, club, p, True)
            offer = {"wage": want["wage"], "years": min(want["years"], 3 if p["Age"] >= 30 else 4),
                     "status": want["status"]}
            sign(career, club, p, offer)               # (AI clubs: his wage, a sensible length)


def _ai_wants(club, p):
    """AI clubs keep their better players and young ones with a future."""
    ratings = sorted((clubs_mod.overall(q) for q in club["players"]), reverse=True)
    cut = ratings[min(len(ratings) - 1, int(len(ratings) * KEEP_SHARE))]
    r = clubs_mod.overall(p)
    age = p.get("Age", 26)
    if age <= 22 and (p.get("Potential") or r) >= club["strength"] - 4:
        return True
    if age >= 34:
        return r >= ratings[len(ratings) // 4]               # only if still one of the best
    return r >= cut


def on_day(career, club, date, rng=None):
    """Called for every day (career/training.py, career/availability.py)."""
    d = cal.parse(date)
    if d.month == 1 and d.day == 1:
        january(career, club, date, rng or random.Random())


def summer_departures(career, rng):
    """30 June: out-of-contract players leave on a free."""
    from career import availability as av
    year = career.get("year", 2026)
    cutoff = dt.date(year, 7, 1)
    fa = free_agents(career)
    mine = []
    for c in career["clubs"]:
        gone = [p for p in c["players"] if p.get("contract_end") and cal.parse(p["contract_end"]) < cutoff]
        for p in gone:
            c["players"].remove(p)
            _to_free_agent(career, c, p)
            if c["id"] == career["my_club"]:
                mine.append(p)
        if gone:
            names = ", ".join(f"{p['Name']} ({p['Pos']}, {p['Age']})" for p in gone)
            av._news(career, career.get("date"), c["id"], f"Out of contract and gone on a free: {names}.",
                     "contract")
    return mine


def _to_free_agent(career, club, p):
    p["_from_rank"] = fin.stature(career, club) if "finance" in club else None
    p["_from_club"] = club["name"]
    p.pop("status", None)
    p.pop("release_clause", None)
    p["contract_end"] = None
    fa = free_agents(career)
    p["id"] = _next_fa_id(career)
    fa["players"].append(p)


def _next_fa_id(career):
    fa = free_agents(career)
    career["fa_next_id"] = max(career.get("fa_next_id", 0), max((p["id"] for p in fa["players"]), default=-1) + 1)
    nid = career["fa_next_id"]
    career["fa_next_id"] += 1
    return nid


def ensure(career, rng=None):
    """Older saves / new careers: a pool of free agents to start with."""
    if "free_agents" not in career or not career["free_agents"].get("players"):
        free_agents(career)
        new_outside_players(career, rng or random.Random(2026))


def free_agents(career):
    """The pool of players without a club (a club-like dict, id -1)."""
    fa = career.get("free_agents")
    if fa is None:
        fa = career["free_agents"] = {"id": -1, "name": "Free agent", "short": "Free agent",
                                      "colour": [120, 120, 120], "players": [], "lineup": {}, "strength": 60}
    return fa


def new_outside_players(career, rng):
    """A new batch of players from outside the league looking for a club."""
    fa = free_agents(career)
    used = {p["Name"] for c in career["clubs"] for p in c["players"]} | {p["Name"] for p in fa["players"]}
    strengths = sorted(c.get("strength", 60) for c in career["clubs"] if fin.league_of(c) != "d1")
    short = sum(max(0, SQUAD_TARGET - len(c["players"])) for c in career["clubs"])
    for _ in range(max(FREE_AGENTS_EACH_SUMMER, int(short * 2))):
        pos = rng.choice(["GK", "LB", "RB", "CB", "CB", "CM", "CM", "LM", "RM", "ST", "ST"])
        # mostly squad players for the smaller clubs, the odd one good enough for the bigger ones
        level = rng.triangular(strengths[0] - 14, strengths[-1] - 6, strengths[0] - 4)
        age = rng.randint(20, 32)
        p = clubs_mod._player(rng, pos, level, used, _next_fa_id(career), age=age, names=career.get("name_pool"))
        p["_from_club"] = "outside the league"
        lg = career.get("league", "pl")
        n = sum(1 for c in career["clubs"] if fin.league_of(c) == lg) or 20
        p["_from_rank"] = len(career["clubs"])          # smaller than any league club
        p["wage"] = fin.fair_wage(p, n - 1, n, lg) // 2
        p["contract_end"] = None
        p["condition"] = 1.0
        fa["players"].append(p)


def ai_sign_free_agents(career, rng):
    """AI clubs short of players sign the best free agents they can afford."""
    from career import availability as av
    fa = free_agents(career)
    for c in sorted(career["clubs"], key=lambda c: -c.get("strength", 0)):
        mine = c["id"] == career["my_club"]
        target = MY_SQUAD_MIN if mine else SQUAD_TARGET
        while len(c["players"]) < target and fa["players"]:
            sign_free_agent(career, c, mine)


def sign_free_agent(career, c, mine=False):
    """A club short of players signs the best free agent it can afford, where it's shortest."""
    from career import availability as av
    fa = free_agents(career)
    if not fa["players"]:
        return None
    have = {}
    for q in c["players"]:
        have[clubs_mod.family(q["Pos"])] = have.get(clubs_mod.family(q["Pos"]), 0) + 1
    from career.ageing import MIN_BY_POS
    need = min(MIN_BY_POS, key=lambda pos: have.get(pos, 0) - MIN_BY_POS[pos])
    cands = [q for q in fa["players"] if clubs_mod.family(q["Pos"]) == need] or fa["players"]
    room = wage_room(career, c)
    best = max(cands, key=lambda q: clubs_mod.overall(q) - (10 if demands(career, c, q, False)["wage"] > room
                                                             else 0))
    want = demands(career, c, best, False)
    fa["players"].remove(best)
    best["id"] = max((q["id"] for q in c["players"]), default=-1) + 1
    for k in ("_from_rank",):
        best.pop(k, None)
    sign(career, c, best, {"wage": want["wage"], "years": want["years"], "status": want["status"]})
    best["condition"] = 1.0
    c["players"].append(best)
    if c.get("league") == "es":
        from career import spain
        spain.arrives(best)
    from career import registration
    if "registered" in c and not registration.is_u21(best, c) and registration.can_register(c, best)[0]:
        c["registered"].append(best["id"])
    who = "The board signed" if mine else "Signed"
    av._news(career, career.get("date"), c["id"],
             f"{who} {best['Name']} ({best['Pos']}, {best['Age']}) on a free transfer"
             + (" - your squad was too small." if mine else "."), "transfer")
    return best


def trim_free_agents(career, keep=150):
    """Nobody stays unemployed for ever: the oldest / weakest drift away."""
    fa = free_agents(career)
    fa["players"].sort(key=lambda p: -clubs_mod.overall(p) + max(0, p.get("Age", 26) - 30) * 2)
    fa["players"] = fa["players"][:keep]
