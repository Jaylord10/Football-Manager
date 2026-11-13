"""
career/staff.py
===============
Your backroom staff: who they are, what they cost, what they do - and hiring and sacking them.

You start with a full staff at your club (better at a bigger club):
  - ASSISTANT MANAGER (1): how much he picks up about the players (the notes on their profiles and in his
    weekly report).
  - FIRST-TEAM COACHES (2): how fast your players improve.
  - GOALKEEPING COACH (1): how fast your keepers improve.
  - FITNESS COACH (1): quicker recovery between games, fewer training injuries.
  - PHYSIO (1): injured players back sooner.
  - CHIEF SCOUT (1): his report on other clubs' players - how good they could become (the better the scout,
    the closer his guess).
  - ACADEMY COACH (1): the youngsters coming up from the academy each summer.

Each has a name, an age, an ability out of 20, a wage (a year) and a contract.  The staff your club starts
with are what a club its size would have, so with them nothing changes; better ones help, worse ones hurt.
Their wages are the "Coaching staff" line in the finances.

HIRING: a list of people looking for work (new names every month).  A role with no space: sack someone first.
SACKING: he's paid half of what's left on his contract (a settlement).
Contracts end on 30 June; staff whose contracts end stay on for two more years at the same wage unless you
let them go.

Real-world scale (2024/25): a Premier League assistant manager earns roughly £0.5m-£3m a year, a first-team
coach £0.3m-£2m, a head of medical or a chief scout £0.1m-£0.5m; Championship clubs about a third of that.
"""

import datetime as dt
import random

from career import calendar as cal
from career import finance as fin

M = 1_000_000
ROLES = (("assistant", "Assistant manager", 1), ("coach", "First-team coach", 2), ("gk", "Goalkeeping coach", 1),
         ("fitness", "Fitness coach", 1), ("physio", "Physio", 1), ("scout", "Chief scout", 1),
         ("academy", "Academy coach", 1))
LABEL = {k: lab for k, lab, _ in ROLES}
SLOTS = {k: n for k, _, n in ROLES}
WHAT = {"assistant": "Picks up more about moods and fitness.",
        "coach": "Players improve faster.",
        "gk": "Keepers improve faster.",
        "fitness": "Quicker recovery, fewer training injuries.",
        "physio": "Injured players back sooner.",
        "scout": "Better guesses at other clubs' young players.",
        "academy": "Better youngsters from the academy."}
PLURAL = {"coach": "First-team coaches"}
BASE_WAGE = {"assistant": 0.6 * M, "coach": 0.4 * M, "gk": 0.25 * M, "fitness": 0.25 * M, "physio": 0.15 * M,
             "scout": 0.2 * M, "academy": 0.2 * M}       # a year, at ability 10 in the Premier Division
WAGE_STEP = 1.25                 # each point of ability: wages x this
LEAGUE_WAGES = {"pl": 1.0, "d1": 0.35}
MARKET_PER_ROLE = 4
SETTLEMENT = 0.5                 # sacked: half what's left on his contract
FIRST = ["Steve", "Gary", "Paul", "Mark", "Kevin", "Neil", "Ian", "Tony", "Graham", "Alan", "Dave", "Mick", "Rob",
         "Simon", "Lee", "Darren", "Phil", "Andy", "Chris", "Martin", "Stuart", "Colin", "Luis", "Marco", "Pieter",
         "Anders", "Henrik", "Tomas", "Rui", "Sergio", "Gianni", "Pascal", "Jonas", "Dean", "Ray", "Terry"]
LAST = ["Holt", "Mercer", "Garside", "Pickford", "Lowe", "Barton", "Kerr", "Dawson", "Shaw", "Hollis", "Whelan",
        "Cotterill", "Ramsey", "Booth", "Fenwick", "Doyle", "Harper", "Lindqvist", "Moretti", "Jansen", "Silva",
        "Duarte", "Kowalski", "Brennan", "Gallagher", "Thorne", "Walsh", "Beckett", "Swann", "Crowther",
        "Ainsworth", "Haig", "McAllister", "Okafor", "Varga", "Nolan", "Stroud", "Pennock"]


# ---------------------------------------------------------------------------
def expected(career, club):
    """The ability a club of this size usually has (biggest club ~16, smallest Division 1 club ~7)."""
    n = len(career["clubs"]) or 40
    return 16.0 - 9.0 * fin.stature(career, club) / max(1, n - 1)


def wage_for(role, ability, league="pl"):
    w = BASE_WAGE[role] * WAGE_STEP ** (ability - 10) * LEAGUE_WAGES.get(league, 0.35)
    step = 50_000 if w >= 500_000 else 10_000
    return max(20_000, round(w / step) * step)


def _person(rng, role, ability, league, year, used):
    for _ in range(20):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if name not in used:
            break
    used.add(name)
    ability = max(1, min(20, int(round(ability))))
    return {"name": name, "role": role, "ability": ability, "age": rng.randint(33, 64),
            "wage": wage_for(role, ability, league), "until": f"{year + rng.randint(1, 3)}-06-30"}


def club_staff(career, cid=None):
    cid = career["my_club"] if cid is None else cid
    return (career.get("staff") or {}).get(str(cid))


def ensure(career):
    """Your club has its staff (a new career, an older save, a new job)."""
    cid = career["my_club"]
    st = career.setdefault("staff", {})
    if str(cid) in st:
        return st[str(cid)]
    club = career["clubs"][cid]
    rng = random.Random(f"staff:{cid}:{career.get('year')}")
    exp = expected(career, club)
    lg = fin.league_of(club)
    used = set()
    people = []
    for role, _, n in ROLES:
        for _ in range(n):
            people.append(_person(rng, role, exp + rng.gauss(0, 1.2), lg, career.get("year", 2026), used))
    st[str(cid)] = people
    return people


def of_role(career, role):
    return [s for s in (club_staff(career) or []) if s["role"] == role]


def _diff(career, role):
    """How far above (or below) what's usual for the club its staff in this role are (ability points)."""
    people = of_role(career, role)
    if not people:
        return -4.0                                        # (nobody doing the job)
    club = career["clubs"][career["my_club"]]
    avg = sum(s["ability"] for s in people) / len(people)
    if role == "coach" and len(people) < SLOTS["coach"]:
        avg -= 2.0                                         # (one coach short)
    return avg - expected(career, club)


def _mine(career, club):
    return club is not None and club.get("id") == career.get("my_club") and club_staff(career) is not None


# --- What they do (each a multiplier; 1.0 = a usual staff for the club's size) -------------------------
def development(career, club, p):
    if not _mine(career, club):
        return 1.0
    role = "gk" if p.get("Pos") == "GK" else "coach"
    return max(0.7, min(1.4, 1 + 0.04 * _diff(career, role)))


def recovery(career, club):
    if not _mine(career, club):
        return 1.0
    return max(0.85, min(1.2, 1 + 0.03 * _diff(career, "fitness")))


def training_injuries(career, club):
    if not _mine(career, club):
        return 1.0
    return max(0.7, min(1.4, 1 - 0.04 * _diff(career, "fitness")))


def injury_length(career, club):
    if not _mine(career, club):
        return 1.0
    return max(0.65, min(1.35, 1 - 0.04 * _diff(career, "physio")))


def academy(career, club):
    """(extra ability for the youth intake, x the chance of a gem)."""
    if not _mine(career, club):
        return 0.0, 1.0
    d = _diff(career, "academy")
    return 0.5 * d, max(0.5, min(2.0, 1 + 0.1 * d))


def assistant_threshold(career):
    """How strong a player's feelings must be before your assistant picks them up (morale.assistant_note)."""
    if not career or club_staff(career) is None:
        return 2.0
    return max(1.0, min(3.0, 2.0 - 0.15 * _diff(career, "assistant")))


def scout_report(career, p):
    """(low, high) - your chief scout's guess at how good another club's player could become - or None."""
    scouts = of_role(career, "scout")
    if not scouts or p.get("Age", 26) >= 29:
        return None
    from career import clubs as clubs_mod
    ability = scouts[0]["ability"]
    spread = max(1, round((21 - ability) / 2.5))
    true = max(clubs_mod.overall(p), round(p.get("Potential") or clubs_mod.overall(p)))
    rng = random.Random(f"scout:{p['Name']}:{scouts[0]['name']}")
    guess = true + rng.randint(-spread, spread)
    return guess - spread, guess + spread


# --- Money -------------------------------------------------------------------------------------------
def wage_bill(career):
    return sum(s["wage"] for s in club_staff(career) or [])


# --- The job market ---------------------------------------------------------------------------------
def market(career):
    """People looking for work - new names on the 1st of each month."""
    month = (career.get("date") or "2026-07-01")[:7]
    mk = career.get("staff_market")
    if mk and mk.get("month") == month:
        return mk["list"]
    club = career["clubs"][career["my_club"]]
    lg = fin.league_of(club)
    exp = expected(career, club)
    rng = random.Random(f"market:{month}:{career['my_club']}")
    used = {s["name"] for s in club_staff(career) or []}
    out = []
    year = int(month[:4]) + (1 if int(month[5:]) >= 7 else 0)
    for role, _, _ in ROLES:
        for k in range(MARKET_PER_ROLE):
            ab = exp + rng.choice((-4, -2, 0, 1, 2, 3, 5)) + rng.gauss(0, 1)
            out.append(_person(rng, role, ab, lg, year - 1, used))
    for i, s in enumerate(out):
        s["mid"] = i
        s["wage"] = round(s["wage"] * 1.1 / 10_000) * 10_000          # (a new man wants a bit more)
    career["staff_market"] = {"month": month, "list": out}
    return out


def room(career, role):
    return SLOTS[role] - len(of_role(career, role))


def hire(career, mid):
    """Take on someone from the market."""
    from career import transfers as trf
    mk = market(career)
    s = next((x for x in mk if x.get("mid") == mid), None)
    if s is None or room(career, s["role"]) <= 0:
        return False
    mk.remove(s)
    s = dict(s)
    s.pop("mid", None)
    y = int(career["date"][:4]) + (1 if int(career["date"][5:7]) >= 7 else 0)
    s["until"] = f"{y + 1}-06-30" if s["age"] >= 60 else f"{y + 2}-06-30"
    club_staff(career).append(s)
    trf._message(career, "news", f"{s['name']} joins as {LABEL[s['role']].lower()} ({fin.money(s['wage'])} a year).")
    return True


def settlement(career, s):
    days = max(0, cal.days_between(career["date"], s["until"]))
    return SETTLEMENT * s["wage"] * days / 365.0


def sack(career, name):
    from career import transfers as trf
    people = club_staff(career) or []
    s = next((x for x in people if x["name"] == name), None)
    if s is None:
        return 0
    pay = settlement(career, s)
    people.remove(s)
    club = career["clubs"][career["my_club"]]
    if pay > 0:
        fin._book(club, "coaching", -pay)
    trf._message(career, "news", f"{s['name']} ({LABEL[s['role']].lower()}) has left the club"
                                 + (f" - a settlement of {fin.money(pay)}." if pay else "."))
    return pay


def summer(career):
    """30 June: contracts that end are renewed for two years (you'd have let them go before if you wanted)."""
    for s in club_staff(career) or []:
        if s["until"] <= career.get("date", ""):
            y = int(s["until"][:4])
            s["until"] = f"{y + 2}-06-30"
            s["age"] = s.get("age", 45)
        s["age"] = s.get("age", 45) + 1


def monthly(career, club):
    """Wages (the 1st of each month - career/finance.py)."""
    if club.get("id") != career.get("my_club") or club_staff(career) is None:
        return
    pay = wage_bill(career) / 12
    fin._book(club, "coaching", -pay)
    if fin.league_of(club) == "pl":
        fin._book(club, "ni", -fin.NI * pay)
