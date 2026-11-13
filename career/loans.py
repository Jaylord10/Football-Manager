"""
career/loans.py
===============
Loans: a player goes to another club for a while and comes back.

THE DEAL
  - LENGTH: the rest of the season (back on 30 June) or half a season (a
    summer loan ends on 1 January and he's back for the January window)
  - LOAN FEE: up front, to the parent club (often nothing for a youngster)
  - WAGES: the club he goes to pays a share (WAGE SHARES), his parent club
    the rest - he keeps his contract with them
  - OPTION TO BUY: the borrowing club may make it permanent for a set fee
    (any time in a window while he's there, or at the end) - or an
    OBLIGATION: the fee is due and he stays when the loan ends
  - RECALL CLAUSE: the parent club can call him back in the January window
  - he can't play against his parent club in the league

THE RULES (real ones)
  - Premier League (2019/20 on): at most 2 players on loan from other
    Premier League clubs at once, at most 4 such loans in a season, only one
    at a time from the same club, and a club can loan only one goalkeeper to
    another Premier League club in a season
  - FIFA (2024/25 on): at most 6 players loaned out and 6 loaned in at any
    time, and at most 3 between the same two clubs - players aged 21 and
    under don't count (FIFA exempts under-21s and club-trained players)

WHY LOAN: young players develop with games (career/training.py - minutes
make a real difference), and a club gets a player it couldn't afford to buy.
Clubs lend the youngsters who aren't getting a game, to smaller clubs who'll
play them; you can ask any club about a loan, and put your own players on
the loan list - clubs then come to you.  Each month you get a report on the
players you've lent out.
"""

import datetime as dt
import random

from career import calendar as cal
from career import clubs as clubs_mod
from career import finance as fin

WAGE_SHARES = (0.0, 0.25, 0.5, 0.6, 0.75, 1.0)    # share of his wage the borrowing club pays
PL_MAX_AT_ONCE = 2           # loans in from other Premier League clubs, at once
PL_MAX_SEASON = 4            # ...and in a season
PL_GK_OUT = 1                # keepers loaned to other Premier League clubs, a season
FIFA_MAX = 6                 # loaned in / out at once (over-21s)
FIFA_PAIR = 3                # between the same two clubs
FIFA_AGE = 21                # 21 and under don't count
AI_LOAN_OUT = 0.02           # per AI club per window day: lends out a youngster who isn't playing
LISTED_INTEREST = 0.05       # per day, a player on your loan list: a club asks for him
KEY_RANK = 11                # a club won't lend one of its best this many players (the XI, more or less)
YOUNG = 23                   # up to this age, a club lends him for his development


# ---------------------------------------------------------------------------
# Finding loans
# ---------------------------------------------------------------------------
def _all_clubs(career):
    from career import transfers
    return career["clubs"] + transfers.spain_clubs(career)


def _real(career):
    """(Spain's view of the career - career/spain.py - or the career itself)"""
    return getattr(career, "parent", career)


def _seller(career, cid):
    from career import transfers
    return transfers.seller(_real(career), cid)


def on_loan(p):
    return p.get("loan")


def loans_in(career, club):
    return [p for p in club["players"] if p.get("loan")]


def loans_out(career, club):
    """[(player, borrowing club)] - the club's players away on loan."""
    out = []
    for e in club.get("loaned_out", []):
        b = _seller(career, e["to"])
        p = next((q for q in b["players"] if q.get("loan") and q["loan"]["from"] == club["id"]
                  and q["Name"] == e["name"]), None)
        if p is not None:
            out.append((p, b))
    return out


def counts(p):
    return p.get("Age", 26) > FIFA_AGE


def is_pl(club):
    return club.get("league", "pl") == "pl"


def season_key(career):
    y = career.get("year", 2026)
    return str(y)


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------
def allowed(career, parent, borrower, p):
    """(ok, why not)"""
    if p.get("loan"):
        return False, f"{p['Name']} is already out on loan."
    if fin.contract_years_left(p, career["date"]) <= 0.05:
        return False, "His contract is about to run out."
    if counts(p):
        n_in = sum(1 for q in borrower["players"] if q.get("loan") and counts(q))
        if n_in >= FIFA_MAX:
            return False, f"{borrower['name']} already have {FIFA_MAX} over-21s on loan (FIFA's limit)."
        n_out = sum(1 for q, _ in loans_out(career, parent) if counts(q))
        if n_out >= FIFA_MAX:
            return False, f"{parent['name']} already have {FIFA_MAX} over-21s out on loan (FIFA's limit)."
    pair = sum(1 for q in borrower["players"] if q.get("loan") and q["loan"]["from"] == parent["id"])
    if pair >= FIFA_PAIR:
        return False, f"FIFA allows only {FIFA_PAIR} loans between the same two clubs."
    if is_pl(parent) and is_pl(borrower):
        dom = [q for q in borrower["players"] if q.get("loan") and q["loan"].get("domestic")]
        if len(dom) >= PL_MAX_AT_ONCE:
            return False, f"{borrower['name']} already have {PL_MAX_AT_ONCE} players on loan from league clubs."
        if borrower.get("pl_loans", {}).get(season_key(career), 0) >= PL_MAX_SEASON:
            return False, f"{borrower['name']} have used their {PL_MAX_SEASON} loans from league clubs this season."
        if any(q["loan"]["from"] == parent["id"] for q in dom):
            return False, f"{borrower['name']} already have a player on loan from {parent['name']}."
        if p["Pos"] == "GK" and parent.get("pl_gk_out", {}).get(season_key(career), 0) >= PL_GK_OUT:
            return False, f"{parent['name']} have already lent a goalkeeper to a league club this season."
    return True, ""


# ---------------------------------------------------------------------------
# The deal
# ---------------------------------------------------------------------------
def default_end(date):
    """Half a season from the summer = 1 January; otherwise the end of the season."""
    d = cal.parse(date)
    season_end = dt.date(d.year + (1 if d.month >= 7 else 0), 6, 30)
    return season_end.isoformat()


def half_end(date):
    d = cal.parse(date)
    if d.month >= 7:
        return dt.date(d.year + 1, 1, 1).isoformat()
    return default_end(date)


def start(career, parent_cid, borrower_cid, p, terms, date=None):
    """The loan begins: fee, wages, the move."""
    from career import registration, transfers, availability as av
    date = date or career["date"]
    parent, borrower = _seller(career, parent_cid), _seller(career, borrower_cid)
    fee = terms.get("fee", 0)
    if fee:
        fin._book(borrower, "transfers_out", -fee)
        fin._book(parent, "transfers_in", fee)
    from career import playerhist
    playerhist.leaving(career, parent_cid, p)            # (his career record)
    parent["players"].remove(p)
    if p["id"] in (parent.get("lineup") or {}).values():
        parent["lineup"] = clubs_mod.best_lineup(parent)
    registration.tidy(parent)
    domestic = is_pl(parent) and is_pl(borrower)
    share = terms.get("share", 1.0)
    p["loan"] = {"from": parent_cid, "from_name": parent["name"], "since": date,
                 "until": terms.get("until") or default_end(date), "fee": fee, "share": share,
                 "option": terms.get("option"), "obligation": bool(terms.get("obligation")),
                 "recall": bool(terms.get("recall")), "domestic": domestic, "apps": 0, "goals": 0,
                 "start_rating": clubs_mod.overall(p)}
    p["id"] = max((q["id"] for q in borrower["players"]), default=-1) + 1
    for k in ("listed", "asking", "loan_listed"):
        p.pop(k, None)
    borrower["players"].append(p)
    parent.setdefault("loaned_out", []).append({"name": p["Name"], "to": borrower_cid,
                                               "wage_part": round(p.get("wage", 0) * (1 - share))})
    sk = season_key(career)
    if domestic:
        borrower.setdefault("pl_loans", {})[sk] = borrower.get("pl_loans", {}).get(sk, 0) + 1
        if p["Pos"] == "GK":
            parent.setdefault("pl_gk_out", {})[sk] = parent.get("pl_gk_out", {}).get(sk, 0) + 1
    from career import foreign
    if borrower_cid >= transfers.ID_SPAIN and foreign.league_of_id(borrower_cid) is None:
        from career import spain
        spain.arrives(p)
    # Registration
    note = ""
    if borrower_cid == career["my_club"]:
        if not registration.is_u21(p, borrower):
            ok, why = registration.can_register(borrower, p)
            if ok and transfers.in_window(date):
                borrower.setdefault("registered", []).append(p["id"])
            else:
                note = f" He isn't registered yet: {why.lower() if why else 'the window is closed'}."
    else:
        registration.auto_register(borrower)
        borrower["lineup"] = clubs_mod.best_lineup(borrower)
    words = describe(p["loan"])
    career.setdefault("transfer_log", []).append({"date": date, "player": p["Name"], "pos": p["Pos"],
                                                  "from": parent["name"], "to": borrower["name"], "fee": fee,
                                                  "loan": True})
    career["transfer_log"] = career["transfer_log"][-300:]
    for cid in (parent_cid, borrower_cid):
        if cid == career["my_club"]:
            who = f"joins {borrower['name']} on loan" if cid == parent_cid else f"joins on loan from {parent['name']}"
            av._news(career, date, cid, f"{p['Name']} ({p['Pos']}, {p['Age']}) {who}: {words}.{note}", "transfer")


def describe(loan):
    bits = [f"until {cal.fmt(loan['until'], False)}"]
    bits.append("no fee" if not loan.get("fee") else f"{fin.money(loan['fee'])} fee")
    bits.append(f"they pay {round(loan['share'] * 100)}% of his wages")
    if loan.get("option"):
        bits.append(("obligation to buy" if loan.get("obligation") else "option to buy") +
                    f" at {fin.money(loan['option'])}")
    if loan.get("recall"):
        bits.append("recall clause")
    return ", ".join(bits)


def end(career, borrower, p, date=None, buy=False, why="the loan has ended"):
    """The loan ends: he goes back - or, with an option taken up (or an obligation), stays for good."""
    from career import registration, transfers, availability as av
    date = date or career["date"]
    loan = p.pop("loan")
    parent = _seller(career, loan["from"])
    parent["loaned_out"] = [e for e in parent.get("loaned_out", [])
                            if not (e["name"] == p["Name"] and e["to"] == borrower["id"])]
    if buy or loan.get("obligation"):
        fee = loan.get("option") or 0
        fin._book(borrower, "transfers_out", -fee)
        fin._book(parent, "transfers_in", fee)
        if borrower["id"] >= 0:
            borrower["finance"]["transfer_budget"] = max(0, borrower["finance"].get("transfer_budget", 0) - fee)
        p["joined"] = date
        p["_from_club"] = parent["name"]
        if borrower["id"] == career["my_club"]:
            end_ = cal.parse(p.get("contract_end") or date)
            p["contract_end"] = max(end_, dt.date(cal.parse(date).year + 3, 6, 30)).isoformat()
        else:
            transfers._ai_contract(career, borrower, p, random.Random(p["Name"]))
        career.setdefault("transfer_log", []).append({"date": date, "player": p["Name"], "pos": p["Pos"],
                                                      "from": parent["name"], "to": borrower["name"], "fee": fee})
        for cid in (parent["id"], borrower["id"]):
            if cid == career["my_club"]:
                av._news(career, date, cid, f"{p['Name']}'s move to {borrower['name']} is made permanent "
                                            f"({fin.money(fee)}).", "transfer")
        return
    from career import playerhist
    p["loan"] = loan                                     # (so the record says "loan")
    playerhist.leaving(career, borrower["id"], p)
    p.pop("loan", None)
    borrower["players"].remove(p)
    if p["id"] in (borrower.get("lineup") or {}).values():
        borrower["lineup"] = clubs_mod.best_lineup(borrower)
    registration.tidy(borrower)
    p["id"] = max((q["id"] for q in parent["players"]), default=-1) + 1
    p["condition"] = p.get("condition", 1.0)
    parent["players"].append(p)
    if parent["id"] == career["my_club"]:
        if not registration.is_u21(p, parent) and registration.can_register(parent, p)[0]:
            parent.setdefault("registered", []).append(p["id"])
        r0 = loan.get("start_rating", clubs_mod.overall(p))
        av._news(career, date, parent["id"], f"{p['Name']} is back from his loan at {borrower['name']} ({why}): "
                                             f"{loan.get('apps', 0)} games, rating {r0} -> {clubs_mod.overall(p)}.",
                 "transfer")
    else:
        registration.auto_register(parent)
        parent["lineup"] = clubs_mod.best_lineup(parent)
    if borrower["id"] == career["my_club"]:
        av._news(career, date, borrower["id"], f"{p['Name']} goes back to {parent['name']} ({why}).", "transfer")


def recall(career, p, borrower):
    """The parent club calls him back (January window, with a recall clause)."""
    end(career, borrower, p, why="recalled")


def can_recall(career, p):
    from career import transfers
    d = cal.parse(career["date"])
    return bool(p.get("loan", {}).get("recall")) and d.month in (1, 2) and transfers.in_window(career["date"])


def wage_part_update(career, p):
    """His wage changed (a new contract while away): the parent's share follows."""
    loan = p.get("loan")
    if not loan:
        return
    parent = _seller(career, loan["from"])
    for e in parent.get("loaned_out", []):
        if e["name"] == p["Name"]:
            e["wage_part"] = round(p.get("wage", 0) * (1 - loan["share"]))


# ---------------------------------------------------------------------------
# Asking a club for one of their players on loan
# ---------------------------------------------------------------------------
def _rank(club, p):
    r = clubs_mod.overall(p)
    return sum(1 for q in club["players"] if q is not p and clubs_mod.overall(q) > r)


def would_play(club, p):
    """Where he'd stand at this club: 0 = the best player ... (his rank in their squad)."""
    return _rank(club, p)


def their_terms(career, parent_cid, p, borrower):
    """What the parent club wants: (ok, why_not, minimum share, minimum fee, want recall, option floor)."""
    parent = _seller(career, parent_cid)
    rank = _rank(parent, p)
    age = p.get("Age", 26)
    young = age <= YOUNG
    starter = p["id"] in (parent.get("lineup") or {}).values()
    if starter or (rank < KEY_RANK and not (young and p.get("mins_avg", 45) < 30)):
        return False, f"{parent['name']}: he's part of our plans - not available on loan.", 0, 0, False, 0
    v = fin.value(p, career["date"])
    plays = would_play(borrower, p) < 14 if borrower else True
    share = 0.5 if young and plays else 0.75 if young else 1.0
    fee = 0 if age <= 21 else round(v * (0.03 if young else 0.06), -5)
    return True, "", share, fee, young, round(v * 1.1 / 500_000) * 500_000


def ask(career, parent_cid, p, terms):
    """Your loan offer.  Returns (accepted, reply)."""
    from career import transfers
    date = career["date"]
    me = career["clubs"][career["my_club"]]
    parent = _seller(career, parent_cid)
    name = transfers.club_name_of(career, parent_cid, p)
    if not transfers.in_window(date):
        return False, "The transfer window is closed."
    if parent_cid < 0:
        return False, "Only clubs lend players - free agents sign contracts."
    ok, why = allowed(career, parent, me, p)
    if not ok:
        return False, why
    if terms.get("fee", 0) + (terms.get("option") or 0 if terms.get("obligation") else 0) > \
            me["finance"].get("transfer_budget", 0):
        return False, f"The board won't allow it: the transfer budget is {fin.money(me['finance'].get('transfer_budget', 0))}."
    talks = career.setdefault("loan_talks", {})
    k = f"{parent_cid}:{p['id']}:{p['Name']}"
    t = talks.setdefault(k, {"n": 0})
    if t.get("closed_until") and cal.parse(t["closed_until"]) > cal.parse(date):
        return False, f"{name} won't discuss him again yet."
    ok, why, share, fee, want_recall, floor = their_terms(career, parent_cid, p, me)
    if not ok:
        return False, why
    # The player: does he want to come?  He wants games.
    r = would_play(me, p)
    if r >= 16 and fin.stature(career, me) > fin.stature(career, parent):
        return False, f"{p['Name']} doesn't want the move - he wouldn't get a game."
    problems = []
    if terms.get("share", 1.0) + 1e-9 < share:
        problems.append(f"you'd have to pay at least {round(share * 100)}% of his wages")
    if terms.get("fee", 0) < fee:
        problems.append(f"they want a loan fee of {fin.money(fee)}")
    if want_recall and not terms.get("recall"):
        problems.append("they want a recall clause")
    if terms.get("option") and terms["option"] < floor:
        problems.append(f"an option to buy would have to be at least {fin.money(floor)}")
    t["n"] += 1
    if not problems:
        talks.pop(k, None)
        start(career, parent_cid, me["id"], p, terms)
        return True, f"Done: {p['Name']} joins you on loan from {name}."
    reply = f"{name}: " + "; ".join(problems) + "."
    if t["n"] >= 3:
        t["closed_until"] = (cal.parse(date) + dt.timedelta(days=14)).isoformat()
        t["n"] = 0
        reply += " They've had enough - no more talks for two weeks."
    return False, reply


# ---------------------------------------------------------------------------
# Every day of a window: the AI's loans, offers for your loan-listed players
# ---------------------------------------------------------------------------
def _borrowers(career, parent, p, rng):
    """Smaller clubs where he'd play (in his position: better than their weakest starter there)."""
    from career import transfers
    group = clubs_mod.fam_group(p["Pos"])
    r = clubs_mod.overall(p)
    here = fin.stature(career, parent)
    out = []
    for c in _all_clubs(career):
        if c["id"] in (parent["id"], career["my_club"]):
            continue
        if fin.stature(career, c) <= here:
            continue                                     # (they go to smaller clubs)
        if (c.get("league") == "es") != (parent.get("league") == "es") and rng.random() < 0.7:
            continue                                     # (mostly at home)
        if len(c["players"]) >= 28:
            continue
        worst = transfers._starter_by_group(c).get(group)
        if worst is None or r < worst - 1:
            continue
        if not allowed(career, parent, c, p)[0]:
            continue
        out.append(c)
    return out


def ai_lend(career, club, rng, date):
    """An AI club lends out a young player who isn't playing."""
    cands = [p for p in club["players"] if not p.get("loan") and p.get("Age", 26) <= YOUNG
             and p.get("mins_avg", 45) < 25 and _rank(club, p) >= KEY_RANK
             and fin.contract_years_left(p, date) > 0.6
             and (p.get("Potential") or 0) >= club.get("strength", 60) - 8]
    if not cands or len(club["players"]) <= 22:
        return
    p = max(cands, key=lambda q: q.get("Potential") or 0)
    bs = _borrowers(career, club, p, rng)
    if not bs:
        return
    b = rng.choice(bs)
    share = rng.choice((0.5, 0.75, 1.0))
    start(career, club["id"], b["id"], p, {"fee": 0, "share": share, "recall": True,
                                          "until": default_end(date) if rng.random() < 0.75 else half_end(date)},
          date)


def offers_for_listed(career, rng, date):
    """Clubs ask for the players you've put on the loan list."""
    from career import transfers
    me = career["clubs"][career["my_club"]]
    for p in list(me["players"]):
        if not p.get("loan_listed") or rng.random() >= LISTED_INTEREST:
            continue
        if any(m["kind"] == "loan" and m["state"] == "open" and m["data"].get("player") == p["Name"]
               for m in transfers.inbox(career)):
            continue
        bs = _borrowers(career, me, p, rng)
        if not bs:
            continue
        b = rng.choice(bs)
        young = p.get("Age", 26) <= YOUNG
        terms = {"fee": 0 if young else round(fin.value(p, date) * rng.uniform(0.02, 0.06), -5),
                 "share": rng.choice((0.5, 0.75, 1.0) if young else (0.75, 1.0)),
                 "until": default_end(date) if rng.random() < 0.7 else half_end(date),
                 "recall": young}
        if not young and rng.random() < 0.3:
            terms["option"] = round(fin.value(p, date) * rng.uniform(1.0, 1.3), -5)
        expires = (cal.parse(date) + dt.timedelta(days=transfers.OFFER_DAYS)).isoformat()
        transfers._message(career, "loan", f"{b['name']} would like {p['Name']} on loan: {describe(terms)}.",
                           {"borrower": b["id"], "player": p["Name"], "pid": p["id"], "terms": terms,
                            "expires": expires}, stop=True)


def respond(career, mid, action):
    """Your answer to a loan request: 'accept' or 'reject'."""
    from career import transfers
    m = next((x for x in transfers.inbox(career) if x["id"] == mid), None)
    if m is None or m["state"] != "open":
        return "That request is no longer open."
    d = m["data"]
    me = career["clubs"][career["my_club"]]
    p = clubs_mod.player_by_id(me, d["pid"])
    if p is None or p["Name"] != d["player"]:
        m["state"] = "gone"
        return "He's no longer at the club."
    if cal.parse(career["date"]) > cal.parse(d["expires"]) or not transfers.in_window(career["date"]):
        m["state"] = "expired"
        return "The request has expired."
    if action == "reject":
        m["state"] = "rejected"
        return "You turn the request down."
    b = _seller(career, d["borrower"])
    ok, why = allowed(career, me, b, p)
    if not ok:
        m["state"] = "refused"
        return why
    start(career, me["id"], b["id"], p, d["terms"])
    m["state"] = "accepted"
    return f"{p['Name']} goes on loan to {b['name']}."


def day(career, iso, rng):
    """Every day: loans ending; in a window, the AI lends and clubs ask about yours; monthly reports."""
    from career import transfers
    d = cal.parse(iso)
    for c in _all_clubs(career):
        for p in list(c["players"]):
            loan = p.get("loan")
            if not loan:
                continue
            if cal.parse(loan["until"]) < d:
                # the end: an AI borrower with an option takes it if he's worth it
                buy = False
                if loan.get("option") and c["id"] != career["my_club"] and not loan.get("obligation"):
                    buy = clubs_mod.overall(p) >= _starter_level(c, p) and \
                        c["finance"].get("transfer_budget", 0) >= loan["option"]
                end(career, c, p, iso, buy=buy)
            elif d.month == 1 and d.day == 15 and loan.get("recall") and loan["from"] != career["my_club"] \
                    and p.get("mins_avg", 45) < 20:
                end(career, c, p, iso, why="recalled - he wasn't playing")
    if transfers.in_window(iso):
        for c in _all_clubs(career):
            if c["id"] != career["my_club"] and rng.random() < AI_LOAN_OUT:
                ai_lend(career, c, rng, iso)
        offers_for_listed(career, rng, iso)
        for m in transfers.inbox(career):
            if m["kind"] == "loan" and m["state"] == "open" and cal.parse(iso) > cal.parse(m["data"]["expires"]):
                m["state"] = "expired"
    if d.day == 1 and d.month not in (7, 8):
        report(career, iso)


def _starter_level(club, p):
    from career import transfers
    return transfers._starter_by_group(club).get(clubs_mod.fam_group(p["Pos"]), 99)


def report(career, iso):
    """The monthly report on your players out on loan."""
    from career import availability as av
    me = career["clubs"][career["my_club"]]
    out = loans_out(career, me)
    if not out:
        return
    bits = []
    for p, b in out:
        r0 = p["loan"].get("start_rating", clubs_mod.overall(p))
        bits.append(f"{p['Name']} ({b['short']}): {p['loan'].get('apps', 0)} games, rating {r0} -> "
                    f"{clubs_mod.overall(p)}")
    av._news(career, iso, me["id"], "Loan report - " + "; ".join(bits) + ".", "transfer")


def count_games(career, results, league_clubs=None):
    """A loanee's games for his loan club (our league: from the match records)."""
    by = {}
    for r in results:
        for a in r.get("players", []):
            if a.get("minutes", 0) > 0:
                cid = r["home"] if a["team"] == 0 else r["away"]
                by[(cid, a["id"])] = True
    for c in league_clubs or career["clubs"]:
        for p in c["players"]:
            if p.get("loan") and by.get((c["id"], p["id"])):
                p["loan"]["apps"] = p["loan"].get("apps", 0) + 1


def season_end(career):
    """30 June: every loan still running ends (options / obligations decided)."""
    date = career.get("date")
    for c in _all_clubs(career):
        for p in list(c["players"]):
            loan = p.get("loan")
            if loan:
                buy = False
                if loan.get("option") and c["id"] != career["my_club"] and not loan.get("obligation"):
                    buy = clubs_mod.overall(p) >= _starter_level(c, p) and \
                        c["finance"].get("transfer_budget", 0) >= loan["option"]
                end(career, c, p, date, buy=buy)


# ---------------------------------------------------------------------------
# Swaps: a player as part of a transfer bid
# ---------------------------------------------------------------------------
def swap_value(career, cid, q):
    """What a club makes of one of your players offered as part of a deal."""
    from career import transfers
    v = fin.value(q, career["date"])
    if cid == -2:
        return 0.7 * v
    club = _seller(career, cid)
    r = clubs_mod.overall(q)
    if r >= _starter_level(club, q) - 2:
        return 0.9 * v                              # he'd be in their team
    if q.get("Age", 26) <= YOUNG and (q.get("Potential") or 0) >= club.get("strength", 60):
        return 0.75 * v                             # one for the future
    return 0.35 * v                                 # they'd only sell him on
