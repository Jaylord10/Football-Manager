"""
career/transfers.py
===================
The transfer market: windows, players at clubs outside the league, and
buying - with full negotiations.

WINDOWS (Premier League): summer 1 July - 1 September, January 1 January -
2 February.  Free agents can be signed at any time.

WHERE PLAYERS COME FROM
  - the other league clubs
  - the Spanish league's 20 clubs (career/spain.py, ids 100-119) - they buy
    and sell too: mostly at home, the big ones everywhere
  - the rest of the world ("abroad"): a smaller pool of players with
    contracts at fictional foreign clubs, refreshed every summer
  - free agents (career/contracts.py) - no fee

BUYING: you bid for a player.  A BID has
  - a fee, paid up front or in instalments (over 2-4 years, a part each 1 July)
  - an add-on: an extra fee once he's played N league games for you
  - a sell-on clause: a share of the profit if you sell him on
The selling club weighs it up against what they want for him: his value
(career/finance.py) x how important he is to them (their best players
cost more - and the very best aren't for sale unless you blow them away),
youngsters with potential cost more, and a contract running out costs less.
Money now is worth more than money later; add-ons and sell-ons count a
little.  They accept, tell you what they'd take, or turn you down - after
BID_PATIENCE bids they stop listening for a fortnight.  A release clause in
his contract: bid that up front and they can't refuse.

Then PERSONAL TERMS with the player (the contract talks screen) - and a big
star may not want to drop down to a much smaller club.  When he signs, the
fee goes (instalments are owed - Finances), add-ons are tracked, and he goes
on the registered squad list if there's room.

The board's transfer budget covers the whole fee (all instalments).
"""

import datetime as dt
import random

from career import calendar as cal
from career import clubs as clubs_mod
from career import finance as fin

WINDOWS = (((7, 1), (9, 1)), ((1, 1), (2, 2)))
BID_PATIENCE = 4
PATIENCE_DAYS = 14
IMPORTANCE = ((3, 1.5), (11, 1.25), (18, 1.05), (99, 0.9))   # rank in his squad below this: x this
TOP_FEE = 100 * fin.M               # asking prices above this climb slower...
TOP_FEE_SLOPE = 0.4             # ...this much per £ - the very best top out around £130-150m
NOT_FOR_SALE = 1.6           # the best 3 at an AI league club, 2+ years left: only for this x value
PROSPECT = 1.2               # 21 or under with real potential
INSTALMENT_DISCOUNT = 0.93   # each year a payment is put off, it's worth this much now
ADDON_COUNTS = 0.5
SELL_ON_COUNTS = 0.3         # x pct x fee
ACCEPT_AT = 0.97
COUNTER_FROM = 0.72
STAR_SNUB = 8                # a key player won't drop this many places down the pecking order
ABROAD_SIZE = 60             # (160 before the Spanish league: Spain is now the main market abroad)
ABROAD_REFRESH = 0.35        # share of the abroad pool replaced each summer
ID_SPAIN = 100               # Spanish clubs' ids: 100-119 (career/spain.py)
FOREIGN_CLUBS = ["Sporting Esteira", "FC Rheinfeld", "Olympique Varennes", "Ajaxia Noord",
                 "Dinamo Kravetz", "AC Montevera", "Estrela da Serra", "Galatur SK", "FC Lindholm",
                 "Union Saint-Lys", "Celtic Harbour", "Hellas Korinna", "Al-Waha FC", "Boca del Plata"]


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------
def in_window(date):
    d = cal.parse(date)
    for (m1, d1), (m2, d2) in WINDOWS:
        start = dt.date(d.year, m1, d1)
        end = dt.date(d.year, m2, d2)
        if start <= d <= end:
            return True
    return False


def window_between(a, b):
    """Is a window open on any day from a to b?"""
    d, end = cal.parse(a), cal.parse(b)
    while d <= end:
        if in_window(d.isoformat()):
            return True
        d += dt.timedelta(days=1)
    return False


def window_text(date):
    d = cal.parse(date)
    for (m1, d1), (m2, d2) in WINDOWS:
        if dt.date(d.year, m1, d1) <= d <= dt.date(d.year, m2, d2):
            return f"Transfer window open until {cal.fmt(dt.date(d.year, m2, d2).isoformat(), False)}"
    # next one
    for y in (d.year, d.year + 1):
        opens = sorted(dt.date(y, m1, d1) for (m1, d1), _ in WINDOWS)
        for o in opens:
            if o > d:
                return f"Transfer window closed - opens {cal.fmt(o.isoformat(), False)}"
    return ""


# ---------------------------------------------------------------------------
# Clubs outside the league
# ---------------------------------------------------------------------------
def abroad(career):
    a = career.get("abroad")
    if a is None:
        a = career["abroad"] = {"id": -2, "name": "Abroad", "short": "Abroad", "colour": [150, 110, 180],
                                "players": [], "lineup": {}, "strength": 64}
    return a


def _new_abroad_player(career, rng, used):
    a = abroad(career)
    strengths = sorted(c.get("strength", 60) for c in career["clubs"] if fin.league_of(c) == "pl")
    pos = rng.choice(["GK", "LB", "RB", "CB", "CB", "CM", "CM", "LM", "RM", "ST", "ST"])
    if rng.random() < ELITE_ABROAD:
        level = rng.uniform(strengths[-1] - 3, strengths[-1] + 4)       # the very best clubs abroad
    else:
        level = rng.triangular(strengths[0] - 12, strengths[-1] + 1, strengths[len(strengths) // 2] - 3)
    age = rng.randint(18, 32)
    pid = career.get("abroad_next_id", 0)
    career["abroad_next_id"] = pid + 1
    p = clubs_mod._player(rng, pos, level, used, pid, age=age)
    p["abroad_club"] = rng.choice(FOREIGN_CLUBS)
    p["homegrown"] = False
    p["condition"] = 1.0
    n = len(career["clubs"])
    p["wage"] = fin.fair_wage(p, n // 2, n)
    fin.give_contract(p, career.get("year", 2026), rng)
    a["players"].append(p)
    return p


def ensure_abroad(career, rng=None):
    rng = rng or random.Random(career.get("year", 2026) * 7)
    a = abroad(career)
    used = {p["Name"] for c in career["clubs"] for p in c["players"]} | {p["Name"] for p in a["players"]}
    while len(a["players"]) < ABROAD_SIZE:
        _new_abroad_player(career, rng, used)


def refresh_abroad(career, rng):
    """Summer: some move on (out of our sight), new ones appear; everyone a year older."""
    a = abroad(career)
    for p in a["players"]:
        p["Age"] = p.get("Age", 26) + 1
    a["players"] = [p for p in a["players"] if p["Age"] <= 33 and rng.random() > ABROAD_REFRESH]
    if len(a["players"]) > ABROAD_SIZE:                  # (older saves: the pool shrinks to its new size)
        rng.shuffle(a["players"])
        a["players"] = a["players"][:ABROAD_SIZE]
    ensure_abroad(career, rng)
    for p in a["players"]:
        if not p.get("contract_end") or cal.parse(p["contract_end"]) < dt.date(career.get("year", 2026), 7, 1):
            fin.give_contract(p, career.get("year", 2026), rng)


def spain_clubs(career):
    """The clubs abroad we trade with: Spain's, Germany's and Italy's (career/spain.py, career/foreign.py)."""
    from career import foreign
    out = career["spain"]["clubs"] if "spain" in career else []
    return out + [c for cfg in foreign.LEAGUES for c in foreign.clubs(career, cfg)]


def seller(career, cid):
    if cid == -2:
        return abroad(career)
    if cid == -1:
        from career import contracts
        return contracts.free_agents(career)
    from career import foreign
    if foreign.league_of_id(cid) is not None:
        return foreign.club(career, cid)
    if cid >= ID_SPAIN:
        return career["spain"]["clubs"][cid - ID_SPAIN]
    return career["clubs"][cid]


def club_name_of(career, cid, p):
    if cid == -2:
        return p.get("abroad_club", "abroad")
    return seller(career, cid)["name"]


# ---------------------------------------------------------------------------
# What they want for him
# ---------------------------------------------------------------------------
def _rank_in_squad(club, p):
    r = clubs_mod.overall(p)
    return sum(1 for q in club["players"] if q is not p and clubs_mod.overall(q) > r)


def asking_price(career, cid, p):
    """(price, not_for_sale) - what the selling club wants up front."""
    club = seller(career, cid)
    date = career.get("date")
    v = fin.value(p, date)
    rank = _rank_in_squad(club, p) if cid >= 0 else 10
    mult = next(m for limit, m in IMPORTANCE if rank < limit)
    if p.get("Age", 26) <= 21 and (p.get("Potential") or 0) - clubs_mod.overall(p) >= 8:
        mult *= PROSPECT
    price = v * mult
    nfs = False
    if cid >= 0 and rank < 3 and fin.contract_years_left(p, date) >= 2:
        nfs = True
        price = max(price, v * NOT_FOR_SALE)
    if p.get("listed") or (cid >= 0 and ai_listed(career, cid, p)):
        price *= 0.85
    if cid >= 0 and just_signed(p, date):
        price *= JUST_SIGNED_PRICE                     # they've only just bought him
    if price > TOP_FEE:                                # (nobody pays £200m+: the British record is ~£125m)
        price = TOP_FEE + (price - TOP_FEE) * TOP_FEE_SLOPE
    step = 5 * fin.M if price >= 50 * fin.M else fin.M if price >= 10 * fin.M else 0.25 * fin.M
    return max(step, round(price / step) * step), nfs


def just_signed(p, date):
    j = p.get("joined")
    return bool(j and date and cal.days_between(j, date) < JUST_SIGNED_DAYS)


def bid_worth(bid):
    fee = bid["fee"]
    years = max(1, bid.get("years", 1))
    per = fee / years
    worth = sum(per * INSTALMENT_DISCOUNT ** y for y in range(years))
    worth += ADDON_COUNTS * bid.get("addon", 0)
    worth += SELL_ON_COUNTS * bid.get("sell_on", 0) / 100.0 * fee
    return worth


def _key(cid, p):
    return f"{cid}:{p['id']}:{p['Name']}"


# ---------------------------------------------------------------------------
# Negotiating a fee (your bids)
# ---------------------------------------------------------------------------
# A bid goes off and the club answers in a day or few (REPLY_DAYS; next day in
# the window's last week) - in your inbox.  Behind their asking price there's a
# lowest price they'd really take (the FLOOR); bid up and they come down part
# of the way to meet you, like haggling.  What sets the floor:
#   listed / surplus to them - cheaper;  his last year (he can walk for free) -
#   cheaper;  the club short of money - cheaper;  he's unhappy - cheaper;
#   the window's last week - dearer (the seller holds the cards);  no one to
#   replace him - dearer and they dig in;  some clubs just hold firm.
# Their counter can come as a plain fee, a fee + add-on or a fee + sell-on.
# Now and then another club is in for him too: beat their bid by the date or
# he goes there.
REPLY_DAYS = (1, 3)
DEADLINE_WEEK = 7              # the window's last days: replies next day, prices up
DEADLINE_PRICE = 1.08
LISTED_FLOOR = 0.75            # (on top of the listed asking price)
LAST_YEAR = 0.70               # contract up next summer
TWO_YEARS = 0.88
SKINT = 0.85                   # the selling club's in the red
UNHAPPY = 0.88
NO_COVER = 1.15                # nobody to replace him...
COVER_GAP = 8                  # (...no one at his position within this of his rating)
FLOOR_RANGE = ((3, (0.88, 0.95)), (11, (0.80, 0.90)), (99, (0.75, 0.85)))   # how far below the asking price
                               # they'd really go - by his place in their squad (their best: hardly at all)
FIRM = 0.20                    # chance a club holds its price (more for its best players)
FIRM_FLOOR = 0.97
MEET = 0.5                     # bid between the floor and the ask: they come this share of the way
NUDGE = 0.2                    # bid a bit below the floor: they come down this much
INSULT = 0.8                   # below this x the floor: no movement
RIVAL_CHANCE = 0.18            # another club in for him too
RIVAL_DAYS = 4
AI_SURPLUS_RANK = 20           # an AI club's player this far down its squad: they'd let him go (listed)


def ai_listed(career, cid, p):
    """An AI club's player they'd let go (as good as listed): surplus to the squad, or an older backup."""
    if cid < 0 or cid == career.get("my_club"):
        return False
    club = seller(career, cid)
    rank = _rank_in_squad(club, p)
    return rank >= AI_SURPLUS_RANK or (p.get("Age", 26) >= 31 and rank >= 14)


def _window_left(date):
    """Days left in the window (None outside one)."""
    if not in_window(date):
        return None
    d = cal.parse(date)
    for (sm, sd), (em, ed) in WINDOWS:
        end = dt.date(d.year, em, ed)
        start = dt.date(d.year, sm, sd)
        if start <= d < end:
            return (end - d).days
    return None


def _no_cover(career, cid, p):
    """Selling him leaves them without anyone near his level in his position?"""
    if cid < 0:
        return False
    club = seller(career, cid)
    fam, r = clubs_mod.family(p["Pos"]), clubs_mod.overall(p)
    return not any(q is not p and clubs_mod.family(q["Pos"]) == fam and clubs_mod.overall(q) >= r - COVER_GAP
                   and not q.get("loan") for q in club["players"])


def _terms(career, cid, p, t):
    """(asking price now, floor, firm, notes) for this player's talks."""
    date = career["date"]
    base, nfs = asking_price(career, cid, p)
    rng = random.Random(f"talks:{cid}:{p['id']}:{p['Name']}:{t.get('opened')}")
    f, notes = 1.0, []
    listed = p.get("listed") or ai_listed(career, cid, p)
    if listed:
        f *= LISTED_FLOOR
        notes.append("they'd let him go")
    yl = fin.contract_years_left(p, date)
    if yl < 1:
        f *= LAST_YEAR
        notes.append("his contract's up next summer")
    elif yl < 2:
        f *= TWO_YEARS
    if cid >= 0 and seller(career, cid).get("finance", {}).get("balance", 1) < 0:
        f *= SKINT
        notes.append("they need the money")
    from career import morale
    if cid >= 0 and morale.level(p) < 40:
        f *= UNHAPPY
        notes.append("he wants the move")
    left = _window_left(date)
    if left is not None and left <= DEADLINE_WEEK:
        f *= DEADLINE_PRICE
        notes.append("it's the last week of the window")
    cover = _no_cover(career, cid, p)
    if cover:
        f *= NO_COVER
        notes.append("they've no one to replace him")
    rank = _rank_in_squad(seller(career, cid), p) if cid >= 0 else 10
    firm = cover or nfs or (not listed and rng.random() < FIRM + (0.2 if rank < 5 else 0))
    ask = base * f
    rng_floor = next(r for lim, r in FLOOR_RANGE if rank < lim)
    floor = ask * (FIRM_FLOOR if firm else rng.uniform(*rng_floor))
    rv = t.get("rival")
    if rv:
        floor = max(floor, rv["fee"] * 1.02)
        ask = max(ask, rv["fee"] * 1.1)
    if t.get("ask"):                                   # (where the haggling has got to)
        ask = max(floor, min(ask, t["ask"]))
    return ask, floor, firm, notes


def _step(fee):
    return 5 * fin.M if fee >= 50 * fin.M else fin.M if fee >= 10 * fin.M else 0.25 * fin.M


def _up(fee):
    st = _step(fee)
    return max(st, -(-fee // st) * st)


def _counter(rng, ask):
    """Their terms, worth about `ask`: a fee, a fee + add-on, or a fee + sell-on."""
    x = rng.random()
    if x < 0.55 or ask < 2 * fin.M:
        return {"fee": _up(ask), "years": 1, "addon": 0, "addon_apps": 20, "sell_on": 0}
    if x < 0.8:
        addon = _step(ask * 0.15) * max(1, round(ask * 0.15 / _step(ask * 0.15)))
        return {"fee": _up(ask - ADDON_COUNTS * addon), "years": 1, "addon": addon, "addon_apps": 30, "sell_on": 0}
    pct = 15
    return {"fee": _up(ask / (1 + SELL_ON_COUNTS * pct / 100.0)), "years": 1, "addon": 0, "addon_apps": 20,
            "sell_on": pct}


def counter_text(o):
    bits = [fin.money(o["fee"]) + ("" if o.get("years", 1) == 1 else f" over {o['years']} years")]
    if o.get("addon"):
        bits.append(f"{fin.money(o['addon'])} after {o.get('addon_apps', 20)} games")
    if o.get("sell_on"):
        bits.append(f"{o['sell_on']}% sell-on")
    return " + ".join(bits)


def talks_for(career, cid, p):
    return career.get("bids", {}).get(_key(cid, p))


def make_bid(career, cid, p, bid):
    """Your bid.  Returns (agreed, reply): agreed True (a release clause met), or None - the bid's
    gone off and they'll answer in a day or few (bids_day) - or False (not sent, and why)."""
    date = career["date"]
    if not in_window(date):
        return False, "The transfer window is closed."
    me = career["clubs"][career["my_club"]]
    budget = me["finance"].get("transfer_budget", 0)
    if bid["fee"] > budget:
        return False, f"The board won't allow it: the transfer budget is {fin.money(budget)}."
    talks = career.setdefault("bids", {})
    k = _key(cid, p)
    t = talks.get(k)
    if t and t.get("closed_until") and cal.parse(t["closed_until"]) > cal.parse(date):
        return False, f"They've stopped answering your calls about him (until {cal.fmt(t['closed_until'], False)})."
    if not t or t.get("closed_until"):
        t = talks[k] = {"bids": 0, "opened": date}
    if t.get("pending"):
        return False, "You're still waiting for their answer to your last bid."
    if t.get("agreed"):
        return True, "The fee's already agreed - now agree personal terms."
    name = club_name_of(career, cid, p)
    clause = p.get("release_clause")                     # met up front: they can't say no
    if clause and bid["fee"] >= clause and bid.get("years", 1) == 1:
        t["agreed"] = dict(bid)
        t.pop("rival", None)
        return True, f"You've met his release clause - {name} have to accept. Now agree personal terms."
    sw = swap_player(career, bid)
    if bid.get("swap"):
        if sw is None:
            return False, "The player you offered isn't at the club any more."
        if not _willing(career, me["id"], cid, sw):
            return False, f"{sw['Name']} doesn't want to go to {name}."
    left = _window_left(date)
    rng = random.Random(f"reply:{k}:{date}:{t['bids']}")
    days = 1 if left is not None and left <= DEADLINE_WEEK else rng.randint(*REPLY_DAYS)
    t["last_bid"] = dict(bid)
    t["pending"] = {"bid": dict(bid), "made": date,
                    "reply_on": (cal.parse(date) + dt.timedelta(days=days)).isoformat()}
    return None, f"Bid sent. {name} will come back to you {'tomorrow' if days == 1 else 'in the next few days'}."


def _reply(career, k, t, rng):
    """Their answer to your pending bid - a message in your inbox."""
    cid, pid, pname = k.split(":", 2)
    cid, pid = int(cid), int(pid)
    club = seller(career, cid)
    p = clubs_mod.player_by_id(club, pid)
    bid = t.pop("pending")["bid"]
    data = {"cid": cid, "pid": pid, "player": pname}
    if p is None or p["Name"] != pname:
        career["bids"].pop(k, None)
        _bid_msg(career, f"Your bid for {pname}: he's no longer at the club.", data)
        return
    name = club_name_of(career, cid, p)
    date = career["date"]
    if not in_window(date):
        t["last_reply"] = "The window shut before they answered."
        _bid_msg(career, f"{name} on {p['Name']}: the window has shut - no deal.", data)
        return
    worth = bid_worth(bid)
    sw = swap_player(career, bid)
    if sw is not None:
        from career import loans
        worth += loans.swap_value(career, cid, sw)
    if not t.get("rival") and t["bids"] == 0 and rng.random() < RIVAL_CHANCE:
        _add_rival(career, cid, p, t, rng)
    ask, floor, firm, notes = _terms(career, cid, p, t)
    t["bids"] += 1
    rv = t.get("rival")
    why = f" ({', '.join(notes[:2])})" if notes and rng.random() < 0.7 else ""
    accept = worth >= ask * ACCEPT_AT or (worth >= floor and rng.random() < 0.15 + 0.6 * (worth - floor) /
                                          max(1.0, ask - floor))
    if accept:
        t["agreed"] = dict(bid)
        t.pop("rival", None)
        t.pop("counter_offer", None)
        reply = f"{name} accept your bid of {counter_text(bid)} for {p['Name']}. Now agree personal terms."
        t["last_reply"] = reply
        _bid_msg(career, reply, dict(data, agreed=True))
        return
    insult = worth < floor * INSULT
    if insult:
        new_ask = ask
    elif worth >= floor:
        new_ask = max(floor, ask - (ask - worth) * MEET)
    else:
        new_ask = max(floor, ask - (ask - worth) * NUDGE)
    if firm:
        new_ask = max(new_ask, floor / FIRM_FLOOR * 0.99)
    t["ask"] = new_ask
    co = _counter(rng, new_ask)
    t["counter_offer"] = co
    nfs = asking_price(career, cid, p)[1]
    if nfs and worth < floor * 0.9:
        reply = f"{name}: {p['Name']} is not for sale. It would take something exceptional - {counter_text(co)}."
    elif "they've no one to replace him" in notes and worth < floor:
        reply = (f"{name} don't want to sell - they've no one to replace him. They'd only think about "
                 f"{counter_text(co)}.")
    elif insult:
        reply = f"{name} reject it out of hand{why}. They want {counter_text(co)}."
    elif firm:
        reply = f"{name} won't budge{why}: {counter_text(co)}, take it or leave it."
    else:
        reply = f"{name} turn it down but they're talking{why}: they'd take {counter_text(co)}."
    if rv:
        reply += f" {rv['name']} have bid around {fin.money(rv['fee'])} - beat it by {cal.fmt(rv['until'], False)}."
    t["bids"] += 1 if insult else 0
    if t["bids"] >= BID_PATIENCE:
        t["closed_until"] = (cal.parse(date) + dt.timedelta(days=PATIENCE_DAYS)).isoformat()
        reply += " They're tired of your bids - no more talks for two weeks."
    t["last_reply"] = reply
    _bid_msg(career, f"{p['Name']}: {reply}", data)


def _bid_msg(career, text, data):
    mid = _message(career, "bid_reply", text, data, stop=True)
    for m in inbox(career):
        if m["id"] == mid:
            m["state"] = "info"
    return mid


def _add_rival(career, cid, p, t, rng):
    """Another club bids for him too."""
    base, _ = asking_price(career, cid, p)
    opts = [c for c in career["clubs"] + spain_clubs(career)
            if c["id"] not in (cid, career["my_club"]) and c.get("finance", {}).get("transfer_budget", 0) >= base * 0.9]
    if not opts:
        return
    c = rng.choice(opts)
    left = _window_left(career["date"]) or 1
    t["rival"] = {"cid": c["id"], "name": c["name"], "fee": _up(base * rng.uniform(0.92, 1.05)),
                  "until": (cal.parse(career["date"]) + dt.timedelta(days=min(RIVAL_DAYS, max(1, left - 1)))).isoformat()}


def bids_day(career, iso, rng):
    """Every day: answers to your bids; rivals who've waited long enough get their man."""
    talks = career.get("bids", {})
    for k in list(talks):
        t = talks.get(k)
        if not t:
            continue
        pend = t.get("pending")
        if pend and cal.parse(iso) >= cal.parse(pend["reply_on"]):
            _reply(career, k, t, random.Random(f"{k}:{iso}:{t['bids']}"))
        rv = t.get("rival")
        if rv and not t.get("agreed") and not t.get("pending") and cal.parse(iso) > cal.parse(rv["until"]):
            cid, pid, pname = k.split(":", 2)
            cid, pid = int(cid), int(pid)
            club = seller(career, cid)
            p = clubs_mod.player_by_id(club, pid)
            talks.pop(k, None)
            if p is None or p["Name"] != pname or not in_window(iso):
                continue
            buyer = seller(career, rv["cid"])
            move_player(career, cid, rv["cid"], p, rv["fee"], 1, iso)
            _ai_contract(career, buyer, p, rng)
            _after_ai_move(career, buyer, iso)
            if cid >= 0:
                _after_ai_move(career, club, iso)
            _bid_msg(career, f"Too late: {pname} has joined {rv['name']} for {fin.money(rv['fee'])}.",
                     {"cid": rv["cid"], "pid": None, "player": pname})


def swap_player(career, bid):
    """Your player offered as part of a bid (or None)."""
    s = bid.get("swap")
    if not s:
        return None
    me = career["clubs"][career["my_club"]]
    q = clubs_mod.player_by_id(me, s["pid"])
    return q if q is not None and q["Name"] == s["name"] else None


def agreed_bid(career, cid, p):
    t = career.get("bids", {}).get(_key(cid, p))
    return t.get("agreed") if t else None


def will_talk(career, cid, p):
    """(yes, reason) - does he want to join you?"""
    if cid < 0:
        return True, ""
    me = career["clubs"][career["my_club"]]
    them = seller(career, cid)
    drop = fin.stature(career, me) - fin.stature(career, them)
    if drop >= STAR_SNUB and _rank_in_squad(them, p) < 3:
        return False, f"{p['Name']} doesn't want to drop down to a club of your size."
    return True, ""


# ---------------------------------------------------------------------------
# Completing a transfer
# ---------------------------------------------------------------------------
def move_player(career, from_cid, to_cid, p, fee, years=1, date=None):
    """A transfer between any two clubs (league clubs, abroad -2): the money
    (instalments owed each 1 July), a sell-on to his old-old club, the move."""
    from career import registration
    date = date or career["date"]
    src, dst = seller(career, from_cid), seller(career, to_cid)
    years = max(1, years)
    first = fee / years
    if to_cid >= 0:
        fin._book(dst, "transfers_out", -first)
    if from_cid >= 0:
        fin._book(src, "transfers_in", first)
        src["finance"]["transfer_budget"] = src["finance"].get("transfer_budget", 0) + round(fee * SALE_TO_BUDGET)
    if to_cid >= 0:
        for y in range(1, years):
            when = dt.date(cal.parse(date).year + (1 if cal.parse(date).month >= 7 else 0) + y - 1, 7, 1)
            career.setdefault("payables", []).append({"from": to_cid, "to": from_cid, "amount": round(first),
                                                      "due": when.isoformat(), "player": p["Name"]})
        dst["finance"]["transfer_budget"] = max(0, dst["finance"].get("transfer_budget", 0) - fee)
    else:
        # (clubs abroad pay up front)
        if from_cid >= 0 and years > 1:
            fin._book(src, "transfers_in", fee - first)
    # A sell-on clause from an earlier deal: the old club gets its share of the profit
    so = p.pop("sell_on", None)
    if so and fee > so.get("fee", 0) and from_cid >= 0:
        cut = (fee - so["fee"]) * so["pct"] / 100.0
        fin._book(src, "transfers_out", -cut)
        if so["to"] >= 0:
            fin._book(seller(career, so["to"]), "transfers_in", cut)
    p.pop("addon", None)
    from_name = p.get("_from_club", "?") if from_cid == -1 else club_name_of(career, from_cid, p)
    src["players"].remove(p)
    if from_cid >= 0:
        if p["id"] in (src.get("lineup") or {}).values():
            src["lineup"] = clubs_mod.best_lineup(src)
        registration.tidy(src)
    p["id"] = (max((q["id"] for q in dst["players"]), default=-1) + 1) if to_cid != -2 else \
        _abroad_id(career)
    for k in ("_from_rank", "abroad_club", "listed", "asking", "status"):
        p.pop(k, None)
    if to_cid == -2:
        p["abroad_club"] = random.Random(p["Name"]).choice(FOREIGN_CLUBS)
    p["_from_club"] = from_name
    p["joined"] = date
    from career import foreign
    if to_cid >= ID_SPAIN and foreign.league_of_id(to_cid) is None:
        from career import spain
        spain.arrives(p)                                 # EU passport or not
    p["condition"] = p.get("condition", 1.0)
    dst["players"].append(p)
    career.setdefault("transfer_log", []).append({"date": date, "player": p["Name"], "pos": p["Pos"],
                                                  "from": from_name, "to": club_name_of(career, to_cid, p),
                                                  "fee": fee})
    career["transfer_log"] = career["transfer_log"][-300:]
    return from_name


def _abroad_id(career):
    pid = career.get("abroad_next_id", 0)
    career["abroad_next_id"] = pid + 1
    return pid


def complete(career, cid, p, bid, contract):
    """You sign him: the money, the move, the paperwork."""
    from career import contracts, registration, availability as av
    me = career["clubs"][career["my_club"]]
    date = career["date"]
    key = _key(cid, p)
    fee = bid["fee"]
    years = max(1, bid.get("years", 1))
    sw = swap_player(career, bid)
    from_name = move_player(career, cid, me["id"], p, fee, years)
    if sw is not None:
        # The player going the other way: no fee for him, a contract at his new club
        move_player(career, me["id"], cid, sw, 0, 1)
        if cid >= 0:
            dst = seller(career, cid)
            _ai_contract(career, dst, sw, random.Random(sw["Name"]))
            _after_ai_move(career, dst, date)
        av._news(career, date, me["id"], f"{sw['Name']} goes to {from_name} as part of the deal.", "transfer")
    if bid.get("addon"):
        p["addon"] = {"to": cid, "amount": bid["addon"], "apps": bid.get("addon_apps", 20), "count": 0}
    if bid.get("sell_on"):
        p["sell_on"] = {"to": cid, "pct": bid["sell_on"], "fee": fee}
    contracts.sign(career, me, p, contract)
    # Registration
    note = ""
    if not registration.is_u21(p):
        ok, why = registration.can_register(me, p)
        if ok and (in_window(date) or cid == -1):
            me.setdefault("registered", []).append(p["id"])
        else:
            note = f" He isn't registered yet: {why.lower() if why else 'the window is closed'}."
    fee_txt = "a free transfer" if fee == 0 else fin.money(fee) + (f" (over {years} years)" if years > 1 else "")
    where = "as a free agent" if cid == -1 else f"from {from_name} for {fee_txt}"
    av._news(career, date, me["id"], f"{p['Name']} ({p['Pos']}, {p['Age']}) signs {where}.{note}", "transfer")
    career.get("bids", {}).pop(key, None)


def pay_due(career, date):
    """Instalments falling due."""
    left = []
    for d in career.get("payables", []):
        if cal.parse(d["due"]) <= cal.parse(date):
            if d["from"] >= 0:
                fin._book(seller(career, d["from"]), "transfers_out", -d["amount"])
            if d["to"] >= 0:
                fin._book(seller(career, d["to"]), "transfers_in", d["amount"])
        else:
            left.append(d)
    career["payables"] = left


def owed(career, club_id):
    return sum(d["amount"] for d in career.get("payables", []) if d["from"] == club_id)


def count_appearances(career, results):
    """Add-ons: league appearances for the club that bought him."""
    from career import availability as av
    me = career["clubs"][career["my_club"]]
    played = set()
    for r in results:
        for a in r.get("players", []):
            cid = r["home"] if a["team"] == 0 else r["away"]
            if cid == me["id"] and a.get("minutes", 0) > 0:
                played.add(a["id"])
    for p in me["players"]:
        ad = p.get("addon")
        if ad and p["id"] in played:
            ad["count"] += 1
            if ad["count"] >= ad["apps"]:
                fin._book(me, "transfers_out", -ad["amount"])
                if ad["to"] >= 0:
                    fin._book(seller(career, ad["to"]), "transfers_in", ad["amount"])
                av._news(career, career["date"], me["id"], f"{p['Name']} has played {ad['apps']} games: the "
                                                           f"{fin.money(ad['amount'])} add-on is paid.", "transfer")
                p.pop("addon")


# ---------------------------------------------------------------------------
# Every day
# ---------------------------------------------------------------------------
def on_day(career, iso, rng):
    """Called for each day (career/training.py run_all)."""
    from career import registration
    if career.get("_on_day") == iso:
        return                                          # (each day once)
    career["_on_day"] = iso
    registration.deadline(career, iso)
    pay_due(career, iso)
    from career import loans
    loans.day(career, iso, rng)                         # loans ending; the AI's loans; requests for yours
    market_day(career, iso, rng)
    bids_day(career, iso, rng)                          # answers to your bids (and rivals)
    from career import spain
    spain.day(career, iso, rng)                         # the Spanish league's day
    from career import foreign
    foreign.day(career, iso, rng)                       # Germany's and Italy's leagues (career/foreign.py)
    from career import cups
    cups.day(career, iso, rng)                          # the cups: draws, and everyone else's ties (career/cups.py)


def search(career, pos=None, max_age=None, max_fee=None, source="all", limit=200, for_sale=False, sort="rating"):
    """Players you could bid for: [(cid, player, price, not_for_sale)]
    for_sale: leave out the ones their club won't sell;  sort: rating / price / age."""
    out = []
    groups = []
    if source in ("all", "league"):
        groups += [(c["id"], c) for c in career["clubs"] if c["id"] != career["my_club"]]
    if source in ("all", "spain"):
        groups += [(c["id"], c) for c in spain_clubs(career)]
    if source in ("all", "abroad"):
        groups.append((-2, abroad(career)))
    for cid, club in groups:
        for p in club["players"]:
            if p.get("loan") or (pos and clubs_mod.family(p["Pos"]) != pos):
                continue
            if max_age and p.get("Age", 26) > max_age:
                continue
            price, nfs = asking_price(career, cid, p)
            if (max_fee and price > max_fee) or (for_sale and nfs):
                continue
            out.append((cid, p, price, nfs))
    key = {"price": lambda t: (t[2], -clubs_mod.overall(t[1])),
           "age": lambda t: (t[1].get("Age", 26), -clubs_mod.overall(t[1]))}.get(sort, lambda t: -clubs_mod.overall(t[1]))
    out.sort(key=key)
    return out[:limit]


# ---------------------------------------------------------------------------
# Selling, offers for your players, and the AI clubs' market
# ---------------------------------------------------------------------------
# During a window, every day:
#   - AI clubs look to strengthen: the weakest place in their XI, a player
#     clearly better than who they've got, at a price and wage they can
#     afford, from another league club or from abroad (they pay the asking
#     price; the player has to fancy the move)
#   - clubs abroad now and then buy one of the league's best players
#   - your players: clubs make offers for the ones you've listed (and now
#     and then for your best ones) - they land in your INBOX: accept, reject
#     or counter.  Continue stops when one arrives.
LIST_INTEREST = 0.05         # per day, a player you've listed
STAR_INTEREST = 0.003        # per day, one of your best few (not listed)
OFFER_DAYS = 7               # an offer stands this long
AI_BUY_CHANCE = 0.06         # per AI club per window day: has a go at strengthening
ABROAD_RAID = 0.0015         # per day, for each club's best 3: a club abroad bids
MAX_COUNTER = 1.25           # a buyer goes up to this x what he's worth (if they can afford it)
SIZE_STEP_DOWN = 5           # a club's top-3 player won't drop this many places in the pecking order
AI_SQUAD_MAX = 28
BIG_CLUB_GAP = 4             # a club this many places bigger can prise away a smaller club's star
ELITE_ABROAD = 0.08          # share of the players abroad who are genuinely world class
# The other league: clubs mostly buy at home (LaLiga clubs sign few players from the Premier League;
# Premier League clubs buy from Spain more often; the biggest clubs shop everywhere) - per attempt,
# the chance a club looks there at all: this for the smallest, rising to 1 for the biggest
LOOK_ABROAD = {"pl": 0.4, "es": 0.15, "d1": 0.12, "de": 0.25, "it": 0.2}
JUST_SIGNED_DAYS = 330       # a club doesn't sell a player it signed this recently (to an AI club; you pay more)
JUST_SIGNED_PRICE = 1.25
WINDOW_SQUAD_MIN = 22        # in a window, an AI club below this signs a free agent now and then
WINDOW_TOP_UP = 0.15         # (chance per day)


def inbox(career):
    return career.setdefault("inbox", [])


def unread(career):
    return sum(1 for m in inbox(career) if not m.get("read"))


def _message(career, kind, text, data=None, stop=False):
    box = inbox(career)
    mid = max((m["id"] for m in box), default=0) + 1
    box.append({"id": mid, "date": career.get("_today", career["date"]), "kind": kind, "text": text,
                "data": data or {}, "read": False, "state": "open"})
    career["inbox"] = box[-80:]
    if stop:
        career["stop"] = True
    return mid


def _starter_by_group(club):
    """For each position group, the weakest rating among the starters there."""
    out = {}
    for slot, pid in (club.get("lineup") or {}).items():
        p = clubs_mod.player_by_id(club, pid)
        if p is None:
            continue
        g = clubs_mod.fam_group(clubs_mod.SLOT_POS[slot])
        r = clubs_mod.overall(p, slot)
        out[g] = min(out.get(g, 99), r)
    return out


def _willing(career, from_cid, to_cid, p):
    """Would he move?  Abroad: yes.  A big drop down the pecking order for one of a club's best: no."""
    if from_cid < 0 or to_cid < 0:
        return True
    src, dst = seller(career, from_cid), seller(career, to_cid)
    drop = fin.stature(career, dst) - fin.stature(career, src)
    return not (drop >= SIZE_STEP_DOWN and _rank_in_squad(src, p) < 3)


def _ai_contract(career, club, p, rng):
    from career import contracts
    rank = fin.size_rank(career, club)
    age = p.get("Age", 26)
    years = 5 if age <= 22 else 4 if age <= 27 else 3 if age <= 30 else 2
    contracts.sign(career, club, p, {"wage": fin.fair_wage(p, rank, fin.league_size(career, club), fin.league_of(club)),
                                     "years": years,
                                     "status": contracts.expected_status(club, p)})


def _after_ai_move(career, club, date):
    from career import registration, ageing
    if len(club["players"]) > AI_SQUAD_MAX:
        ageing.trim_squad(career, club, date)
    registration.auto_register(club)
    club["lineup"] = clubs_mod.best_lineup(club)


def ai_try_buy(career, club, rng, date):
    """An AI club strengthens its weakest position, if it can."""
    budget = club["finance"].get("transfer_budget", 0)
    if budget < fin.M:
        return
    weakest = _starter_by_group(club)
    if not weakest:
        return
    group = min(weakest, key=lambda g: weakest[g])
    current = weakest[group]
    room = (club["finance"].get("wage_budget", 0) - fin.wage_bill(club)) / 52
    rank = fin.size_rank(career, club)
    n = fin.league_size(career, club)
    cands = []
    lg = fin.league_of(club)
    big = (1 - rank / max(1, len(fin.league_clubs(career, club)) - 1)) ** 3
    other = rng.random() < LOOK_ABROAD[lg] + (1 - LOOK_ABROAD[lg]) * big
    pools = [(c["id"], c) for c in career["clubs"] + spain_clubs(career) if c["id"] != club["id"]
             and (other or fin.league_of(c) == lg)] + [(-2, abroad(career))]
    here = fin.stature(career, club)
    for cid, pool in pools:
        for p in pool["players"]:
            if clubs_mod.fam_group(p["Pos"]) != group or p.get("Age", 26) > 31:
                continue
            if cid >= 0 and just_signed(p, date):
                continue
            if p.get("loan"):
                continue                     # (he belongs to another club)
            if cid >= 0 and p["id"] in (pool.get("lineup") or {}).values() \
                    and fin.stature(career, pool) < here:
                continue                     # a bigger club doesn't sell a first-choice player to a smaller one
            r = clubs_mod.overall(p)
            if r < current + (2 if rank < 6 else 3):
                continue
            price, nfs = asking_price(career, cid, p)
            if nfs and not (cid >= 0 and here + BIG_CLUB_GAP <= fin.stature(career, seller(career, cid))):
                continue                     # (a much bigger club can pay the not-for-sale price)
            if price > budget:
                continue
            if fin.fair_wage(p, rank, n, fin.league_of(club)) > room + p.get("wage", 0) * 0.2:
                continue
            cands.append((r - 6.0 * price / max(budget, 1), cid, p, price))
    if not cands:
        return
    cands.sort(key=lambda t: -t[0])
    _, cid, p, price = rng.choice(cands[:3])
    if cid == career["my_club"]:
        offer_for_mine(career, p, rng, date, buyer=club["id"])
        return
    if not _willing(career, cid, club["id"], p):
        return
    years = 1 if price < 15 * fin.M else rng.choice((1, 2, 3))
    move_player(career, cid, club["id"], p, price, years, date)
    _ai_contract(career, club, p, rng)
    _after_ai_move(career, club, date)
    if cid >= 0:
        _after_ai_move(career, seller(career, cid), date)


def abroad_raid(career, club, p, rng, date):
    """A club abroad buys one of a league club's best players."""
    price, _ = asking_price(career, club["id"], p)
    fee = price * rng.uniform(1.0, 1.2)
    step = fin.M if fee >= 10 * fin.M else 0.25 * fin.M
    fee = round(fee / step) * step
    if club["id"] == career["my_club"]:
        offer_for_mine(career, p, rng, date, buyer=-2, fee=fee)
        return
    move_player(career, club["id"], -2, p, fee, 1, date)
    _after_ai_move(career, club, date)


def offer_for_mine(career, p, rng, date, buyer=None, fee=None):
    """A club wants one of your players: an offer in your inbox."""
    me = career["clubs"][career["my_club"]]
    if any(m["kind"] == "offer" and m["state"] == "open" and m["data"].get("player") == p["Name"]
           for m in inbox(career)):
        return
    v = fin.value(p, date)
    if buyer is None:
        need = clubs_mod.fam_group(p["Pos"])
        r = clubs_mod.overall(p)
        options = []
        for c in career["clubs"] + spain_clubs(career):
            if c["id"] == me["id"]:
                continue
            if c["finance"].get("transfer_budget", 0) < v * 0.8:
                continue
            if _starter_by_group(c).get(need, 99) <= r + 1:
                options.append(c["id"])
        if r >= 68:
            options.append(-2)
        if not options:
            return
        buyer = rng.choice(options)
    if fee is None:
        target = p.get("asking") if p.get("listed") else v * rng.uniform(0.85, 1.1)
        fee = min(target, v * MAX_COUNTER)
        step = fin.M if fee >= 10 * fin.M else 0.25 * fin.M
        fee = max(step, round(fee / step) * step)
    budget = (seller(career, buyer)["finance"].get("transfer_budget", 0) if buyer >= 0 else 300 * fin.M)
    top = min(budget, max(fee, v * MAX_COUNTER))
    years = 1 if buyer < 0 or fee < 15 * fin.M else rng.choice((1, 2))
    bname = abroad_name(p) if buyer == -2 else seller(career, buyer)["name"]
    expires = (cal.parse(date) + dt.timedelta(days=OFFER_DAYS)).isoformat()
    paid = "" if years == 1 else f" (over {years} years)"
    _message(career, "offer",
             f"{bname} offer {fin.money(fee)}{paid} for {p['Name']} ({p['Pos']}, {p['Age']}).",
             {"buyer": buyer, "buyer_name": bname, "player": p["Name"], "pid": p["id"], "fee": fee,
              "years": years, "top": top, "expires": expires, "rounds": 0}, stop=True)


def abroad_name(p):
    return random.Random(p["Name"] + "buy").choice(FOREIGN_CLUBS)


def respond(career, mid, action, counter=None, rng=None):
    """Your answer to an offer: 'accept', 'reject' or 'counter' (with a fee).  Returns what happened."""
    from career import availability as av
    rng = rng or random.Random()
    m = next((x for x in inbox(career) if x["id"] == mid), None)
    if m is None or m["state"] != "open":
        return "That offer is no longer open."
    d = m["data"]
    me = career["clubs"][career["my_club"]]
    p = clubs_mod.player_by_id(me, d["pid"])
    if p is None or p["Name"] != d["player"]:
        m["state"] = "gone"
        return "He's no longer at the club."
    if cal.parse(career["date"]) > cal.parse(d["expires"]) or not in_window(career["date"]):
        m["state"] = "expired"
        return "The offer has expired."
    if action == "reject":
        m["state"] = "rejected"
        return f"You turn down {d['buyer_name']}'s offer."
    if action == "counter":
        d["rounds"] += 1
        if counter <= d["top"]:
            d["fee"] = counter
            action = "accept"
        elif d["rounds"] >= 2 or rng.random() < 0.4:
            m["state"] = "withdrawn"
            return f"{d['buyer_name']} won't go that high - they've pulled out."
        else:
            d["fee"] = d["top"]
            m["text"] = f"{d['buyer_name']} improve their offer for {p['Name']} to {fin.money(d['top'])} - final offer."
            return m["text"]
    # Accept: he has to agree to go
    if not _willing(career, me["id"], d["buyer"], p):
        m["state"] = "refused"
        return f"{p['Name']} doesn't want to join {d['buyer_name']} - the deal is off."
    fee = d["fee"]
    move_player(career, me["id"], d["buyer"], p, fee, d["years"])
    if d["buyer"] >= 0:
        buyer = seller(career, d["buyer"])
        _ai_contract(career, buyer, p, rng)
        _after_ai_move(career, buyer, career["date"])
    m["state"] = "accepted"
    av._news(career, career["date"], me["id"], f"{p['Name']} has been sold to {d['buyer_name']} for "
                                               f"{fin.money(fee)}.", "transfer")
    return f"Deal done: {p['Name']} joins {d['buyer_name']} for {fin.money(fee)}."


SALE_TO_BUDGET = 0.5         # the board lets you spend this share of a sale


def market_day(career, iso, rng):
    """The AI market and offers for your players - every day of a window."""
    if not in_window(iso):
        return
    career["_today"] = iso
    me = career["clubs"][career["my_club"]]
    for c in career["clubs"] + spain_clubs(career):
        if c["id"] == me["id"]:
            continue
        if rng.random() < AI_BUY_CHANCE:
            ai_try_buy(career, c, rng, iso)
        if len(c["players"]) < WINDOW_SQUAD_MIN and rng.random() < WINDOW_TOP_UP:
            from career import contracts
            contracts.sign_free_agent(career, c)            # replace the players they've sold
    # Clubs abroad (the big clubs here are the buyers - it's the smaller ones who lose players abroad)
    for c in career["clubs"] + spain_clubs(career):
        size = fin.size_rank(career, c) / max(1, fin.league_size(career, c) - 1)   # 0 biggest .. 1 smallest
        best = sorted(c["players"], key=lambda q: -clubs_mod.overall(q))[:3]
        for p in best:
            if just_signed(p, iso) or p.get("loan"):
                continue
            if p.get("Age", 26) <= 29 and rng.random() < ABROAD_RAID * 2 * size ** 1.5:
                abroad_raid(career, c, p, rng, iso)
                break
    # Interest in your players
    ranked = sorted(me["players"], key=lambda q: -clubs_mod.overall(q))
    stars = {q["id"] for q in ranked[:4]}
    for p in list(me["players"]):
        if p.get("loan"):
            continue
        if p.get("listed") and rng.random() < LIST_INTEREST:
            offer_for_mine(career, p, rng, iso)
        elif p["id"] in stars and rng.random() < STAR_INTEREST:
            offer_for_mine(career, p, rng, iso)
    # Old offers lapse
    for m in inbox(career):
        if m["kind"] == "offer" and m["state"] == "open" and cal.parse(iso) > cal.parse(m["data"]["expires"]):
            m["state"] = "expired"
    career.pop("_today", None)
