"""
career/stadium.py
=================
Growing the ground: a club's profile (career/clubinfo.py) can list
DEVELOPMENT PHASES - rebuilding a stand, in order (phase 2 needs phase 1).
You ask the board (Board screen); they say yes if the club can afford it and
they trust you, otherwise they tell you why not.  Once approved:

  - building starts next month and takes the phase's months; the cost is paid
    month by month (so the bank - and the transfer budget - feel it)
  - while it's built, part of the stand is shut (fewer seats, less gate money)
  - when it opens: the new capacity for good, the stand's new details on the
    club page, the new pictures if they've been made, a story in the papers
    and a lift for the fans

Real-world feel: Anfield's Main Stand (2016) cost about £114m for some 8,500
extra seats; the Anfield Road End (2024) about £80m for 7,000 - roughly £11-13k
a seat, and around two years' building.

career["stadium"][club id] = {"done": [phase ids], "building": {id, start, end, paid},
                              "asked": date of the last no}
"""

import datetime as dt

from career import calendar as cal, clubinfo, finance as fin

MIN_CONFIDENCE = 45           # the board won't spend big on a manager they don't trust
CASH_SHARE = 0.5              # ...and want this share of the cost in the bank before they start
ASK_AGAIN_DAYS = 90           # after a no
FAN_LIFT = 4                  # fans' mood when it opens (career/media.py)


def _st(career, club):
    return career.setdefault("stadium", {}).setdefault(str(club["id"]), {"done": []})


def phases(club):
    pr = clubinfo.profile(club)
    return (pr or {}).get("ground", {}).get("development", [])


def next_phase(career, club):
    """The next phase that could be started (or None)."""
    st = _st(career, club)
    if st.get("building"):
        return None
    for ph in phases(club):
        if ph["id"] in st["done"]:
            continue
        if ph.get("requires") and ph["requires"] not in st["done"]:
            return None
        return ph
    return None


def building(career, club):
    """(phase, state) being built - or (None, None)."""
    st = _st(career, club)
    b = st.get("building")
    if not b:
        return None, None
    ph = next((p for p in phases(club) if p["id"] == b["id"]), None)
    return ph, b


def stands(career, club):
    """The ground's stands now (phases done applied; one being built marked)."""
    pr = clubinfo.profile(club)
    if not pr:
        return []
    out = [dict(s) for s in pr["ground"]["stands"]]
    st = _st(career, club)
    for ph in phases(club):
        if ph["id"] in st["done"]:
            for s in out:
                if s["name"] == ph["stand"]:
                    s.update(ph["after"])
                    s["built"] = (st.get("years") or {}).get(ph["id"], "new")
    ph, b = building(career, club)
    if ph:
        for s in out:
            if s["name"] == ph["stand"]:
                s["building"] = True
                s["open_now"] = s["capacity"] - ph["closed_during"]
    return out


def capacity(career, club):
    """Seats open now (None: the club has no profile - the finance figure stands)."""
    ss = stands(career, club)
    if not ss:
        return None
    return sum(s.get("open_now", s["capacity"]) for s in ss)


def full_capacity(career, club):
    return sum(s["capacity"] for s in stands(career, club))


def images(career, club):
    """{which: path} - the latest pictures for the ground as it is now."""
    pr = clubinfo.profile(club)
    if not pr:
        return {}
    out = dict(pr["ground"].get("images") or {})
    st = _st(career, club)
    for ph in phases(club):
        if ph["id"] in st["done"]:
            import os
            out.update({k: v for k, v in (ph.get("images") or {}).items() if os.path.exists(v)})
    return out


def sync(career):
    """Make each club's finance capacity match its ground (on load, and when anything changes)."""
    for c in career.get("clubs", []):
        cap = capacity(career, c)
        if cap and "finance" in c:
            c["finance"]["capacity"] = cap


def ask(career, club):
    """You ask the board to start the next phase.  Returns (yes, what they say)."""
    ph = next_phase(career, club)
    if ph is None:
        return False, "There's nothing to build just now."
    st = _st(career, club)
    today = career["date"]
    if st.get("asked") and cal.days_between(st["asked"], today) < ASK_AGAIN_DAYS:
        return False, (f"The board said no on {cal.fmt(st['asked'], False)} - give it until "
                       f"{cal.fmt((cal.parse(st['asked']) + dt.timedelta(days=ASK_AGAIN_DAYS)).isoformat(), False)}.")
    from career import board
    conf = board.state(career).get("confidence", 50)
    bal = club["finance"]["balance"]
    if conf < MIN_CONFIDENCE:
        st["asked"] = today
        return False, "The board won't commit that kind of money while they're unsure about you. Win them over first."
    from career import crowds
    ok, why = crowds.demand_case(career, club, full_capacity(career, club))
    if not ok:
        st["asked"] = today
        return False, why
    if bal < ph["cost"] * CASH_SHARE:
        st["asked"] = today
        return False, (f"The board say the club can't afford it yet: they want at least "
                       f"{fin.money(ph['cost'] * CASH_SHARE)} in the bank before they start (there's {fin.money(bal)}).")
    start = _first_of_next_month(today)
    end = _add_months(start, ph["months"])
    st["building"] = {"id": ph["id"], "start": start, "end": end, "paid": 0}
    st.pop("asked", None)
    sync(career)
    _news(career, club, ph, "approved", start, end)
    return True, (f"Approved. {why} {ph['name']}: {fin.money(ph['cost'])}, paid as it's built. Work starts on "
                  f"{when(start)} and it should open on {when(end)}. Part of the "
                  f"{ph['stand']} will be shut while it's built ({ph['closed_during']:,} seats).")


def monthly(career, date):
    """The 1st of each month: pay the builders; open the stand when it's done."""
    for club in career.get("clubs", []):
        ph, b = building(career, club)
        if not ph or date < b["start"]:
            continue
        months = max(1, ph["months"])
        part = ph["cost"] / months
        if b["paid"] < ph["cost"] - 1:
            fin._book(club, "other", -part)
            b["paid"] = b.get("paid", 0) + part
        if date >= b["end"]:
            st = _st(career, club)
            st["done"].append(ph["id"])
            st.setdefault("years", {})[ph["id"]] = cal.parse(date).year
            st.pop("building", None)
            sync(career)
            _news(career, club, ph, "opened")


def when(iso):
    """'1 Aug 2026'"""
    d = cal.parse(iso)
    return f"{d.day} {d.strftime('%b')} {d.year}"


def _first_of_next_month(iso):
    d = cal.parse(iso)
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return dt.date(y, m, 1).isoformat()


def _add_months(iso, n):
    d = cal.parse(iso)
    m = d.month - 1 + n
    return dt.date(d.year + m // 12, m % 12 + 1, 1).isoformat()


def _news(career, club, ph, what, start=None, end=None):
    from career import media, transfers
    if club["id"] != career.get("my_club"):
        return
    paper = media.local_paper(career)
    g = clubinfo.profile(club)["ground"]["name"]
    if what == "approved":
        media._add_article(career, paper, "club", f"{ph['stand']} to be rebuilt",
                           f"The board have approved a {fin.money(ph['cost'])} rebuild of the {ph['stand']} at {g}. "
                           f"{ph['about']} Work starts on {when(start)} and the new stand should "
                           f"open on {when(end)}, taking {g} to {full_after(career, club, ph):,}.",
                           club=club["id"])
        transfers._message(career, "info", f"The board have approved the {ph['stand']} rebuild.", {})
    else:
        media._add_article(career, paper, "club", f"The new {ph['stand']} opens",
                           f"The rebuilt {ph['stand']} opened today: {ph['after']['capacity']:,} seats, and {g} now "
                           f"holds {full_capacity(career, club):,}. {ph.get('opened_line', '')}", club=club["id"])
        transfers._message(career, "info", f"The new {ph['stand']} is open - {g} now holds "
                                           f"{full_capacity(career, club):,}.", {})
        m = media._m(career)
        m["mood"] = min(100, m.get("mood", 50) + FAN_LIFT)


def full_after(career, club, ph):
    return full_capacity(career, club) + ph["adds"]
