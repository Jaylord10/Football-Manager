"""
career/calendar.py
==================
The season's dates, Premier League style:

  - the season starts on the Saturday on or after 15 August and ends in late May
  - most rounds are on a Saturday (3pm), a few midweek (Wednesday, 7.45pm)
  - no league games on the four international-break weekends (September,
    October, November, March)
  - the Christmas run: Boxing Day, 30 December and 2 January
  - 38 rounds in all (any number works: a bigger league gets extra midweek
    rounds, a smaller one - the old 10-club league's 18 - is spread out)

Dates are kept in the save as "YYYY-MM-DD" text.
"""

import datetime as dt

SEASON_START = (8, 15)        # first Saturday on or after 15 August
SEASON_END = (5, 31)          # nothing after 31 May
# International breaks: (month, which Saturday of the month)
BREAKS = ((9, 2), (10, 2), (11, 3), (3, 4))
FESTIVE = ((12, 26), (12, 30), (1, 2))
# Midweek rounds, added in this order while more rounds are needed: (month, which Wednesday)
MIDWEEKS = ((12, 1), (1, 3), (2, 2), (4, 1), (10, 4), (9, 4), (11, 4), (3, 2), (4, 3))
MIN_GAP = 2                   # days between two rounds at least
KICK_OFF = {"Sat": "15:00", "Sun": "16:30", "Wed": "19:45", "Tue": "19:45", "Mon": "20:00",
            "Thu": "20:00", "Fri": "20:00"}


def _nth_weekday(year, month, weekday, n):
    """The n-th weekday (0=Mon) of a month."""
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _year_for(month, start_year):
    return start_year if month >= 7 else start_year + 1


def season(start_year, rounds):
    """(round dates, international-break dates) for the season starting in start_year."""
    start = dt.date(start_year, *SEASON_START)
    start += dt.timedelta(days=(5 - start.weekday()) % 7)          # Saturday
    end = dt.date(start_year + 1, *SEASON_END)
    breaks = [_nth_weekday(_year_for(m, start_year), m, 5, n) for m, n in BREAKS]
    festive = [dt.date(_year_for(m, start_year), m, d) for m, d in FESTIVE]

    days = list(festive)
    d = start
    while d <= end:
        if d not in breaks and all(abs((d - f).days) >= MIN_GAP for f in festive):
            days.append(d)
        d += dt.timedelta(weeks=1)
    days.sort()

    # More rounds needed: midweek ones (where there's room either side)
    for m, n in MIDWEEKS:
        if len(days) >= rounds:
            break
        w = _nth_weekday(_year_for(m, start_year), m, 2, n)
        if start < w < days[-1] and all(abs((w - x).days) >= MIN_GAP for x in days):
            days.append(w)
            days.sort()
    # Still short (an unusual number of clubs): more Saturdays into June
    d = days[-1]
    while len(days) < rounds:
        d += dt.timedelta(weeks=1)
        days.append(d)
    # Too many (a smaller league): spread the rounds evenly over the season
    if len(days) > rounds:
        if rounds <= 1:
            days = days[:rounds]
        else:
            n = len(days)
            days = [days[round(i * (n - 1) / (rounds - 1))] for i in range(rounds)]
    return [x.isoformat() for x in days], [b.isoformat() for b in breaks]


def parse(s):
    return dt.date.fromisoformat(s)


def fmt(s, year=True):
    """'Sat 15 Aug 2026'"""
    d = parse(s) if isinstance(s, str) else s
    return d.strftime("%a ") + str(d.day) + d.strftime(" %b") + (d.strftime(" %Y") if year else "")


def kick_off(s):
    d = parse(s) if isinstance(s, str) else s
    return KICK_OFF.get(d.strftime("%a"), "15:00")


def season_label(start_year):
    return f"{start_year}/{str(start_year + 1)[-2:]}"


def days_between(a, b):
    return (parse(b) - parse(a)).days


def pre_season_day(calendar):
    """Where a new season starts: the Monday of the week of the first round."""
    first = parse(calendar[0])
    return (first - dt.timedelta(days=first.weekday())).isoformat()
