"""
ai/patterns.py
==============
Teamwork patterns in possession - things that only work when two or three
players agree.  Worked out together with the team shape (ai/team_shape.py)
after each player has judged his own spot (ai/spot_value.py), and they
override those spots.

1. SUPPORT UNDER PRESSURE
   When the man on the ball is being closed down, the two best-placed
   teammates come to help: each takes a spot 7-13 m from him with an OPEN
   passing lane and time on the ball, on DIFFERENT sides (so one defender
   can't block both), preferring angles that let the team keep moving
   forward.  Under pressure a backwards option is fine - keeping the ball
   is what matters.

2. FILL THE GAP
   When a player is pulled away from his place in the shape - on a run in
   behind, or helping a teammate under pressure - his spot is left empty.  If
   it matters (rest defence in front of the centre-backs, a striker's spot
   on the last line, the width on a flank), the nearest teammate whose own
   job matters less slides across to cover it, so the shape doesn't fall
   apart.  Teamwork decides how willing a player is to do this.

Overlay labels: "support: come short (left)", "fill the gap: LB's spot".

All tuning numbers are in the TUNING block.  Distances in metres, in the
team's attacking frame (a = up the pitch from our goal, l = sideways,
negative = our left).
"""

import math

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
# Support under pressure
PRESSED_DIST       = 5.0     # m: an opponent this close = pressed...
CLOSING_DIST       = 9.0     # ...or this close and closing in fast
CLOSING_SPEED      = 2.5     # m/s
SUPPORT_RADII      = (7.0, 10.0, 13.0)
SUPPORT_ANGLES     = 16      # directions tried around the man on the ball
SUPPORTERS         = 2
SUPPORT_RANGE      = 22.0    # m: only players this close to the ball can help
MIN_SEPARATION_DEG = 60.0    # the two supporters' angles from the ball differ by at least this
W_LANE             = 3.0
W_TIME             = 2.0
W_FORWARD          = 0.4     # per 10 m forward of the ball (backwards is allowed under pressure)
W_REACH            = 0.15    # cost per metre he has to travel to get there
W_AWAY_FROM_PRESS  = 0.8     # spots on the far side from the presser
STICKY             = 0.5     # last time's supporter keeps the job unless clearly worse

# Fill the gap
FILL_RANGE         = 18.0    # m: a teammate this close can cover
TEAMWORK_MIN       = 6.0     # players below this Teamwork don't bother


from core.stats import stat20 as _stat    # (cached: attributes never change during a match)


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


# ---------------------------------------------------------------------------
def pressed(car, opps_now):
    """car = (a, l, va, vl) of the man on the ball; opps_now = [(a, l, va, vl)]."""
    ca, cl = car[0], car[1]
    worst = None
    for oa, ol, ova, ovl in opps_now:
        d = math.hypot(oa - ca, ol - cl)
        if d < 0.1:
            return (oa, ol)
        closing = -((oa - ca) * (ova - car[2]) + (ol - cl) * (ovl - car[3])) / d
        if d < PRESSED_DIST or (d < CLOSING_DIST and closing > CLOSING_SPEED):
            if worst is None or d < worst[0]:
                worst = (d, oa, ol)
    return None if worst is None else (worst[1], worst[2])


def support_under_pressure(players, car, presser, opps, max_a, half_w):
    """
    players: [(player, cur_a, cur_l)] candidates (not the carrier).
    Returns {id(player): (a, l, label)} for up to SUPPORTERS players.
    """
    import ai.spot_value as spot_value
    ca, cl = car[0], car[1]
    pa, pl = presser
    away = (ca - pa, cl - pl)
    away_len = math.hypot(*away) or 1.0
    away = (away[0] / away_len, away[1] / away_len)

    spots = []
    for r in SUPPORT_RADII:
        for k in range(SUPPORT_ANGLES):
            ang = 2 * math.pi * k / SUPPORT_ANGLES
            a = ca + r * math.cos(ang)
            l = cl + r * math.sin(ang)
            if a > max_a or a < 2.0 or abs(l) > half_w - 2.0:
                continue
            lane, t = spot_value.lane_and_time(a, l, ca, cl, opps)
            if lane < 0.3:
                continue
            score = (W_LANE * lane + W_TIME * _clamp((t + 0.5) / 2.5, 0.0, 1.0)
                     + W_FORWARD * (a - ca) / 10.0
                     + W_AWAY_FROM_PRESS * ((a - ca) * away[0] + (l - cl) * away[1]) / r)
            spots.append((score, a, l, ang))
    if not spots:
        return {}

    cands = [(p, pa_, pl_) for p, pa_, pl_ in players
             if math.hypot(pa_ - ca, pl_ - cl) < SUPPORT_RANGE]
    result = {}
    taken_angles = []
    for _ in range(SUPPORTERS):
        best = None
        for p, pa_, pl_ in cands:
            if id(p) in result:
                continue
            bonus = STICKY if getattr(p, "_support_job", False) else 0.0
            for score, a, l, ang in spots:
                if any(_ang_diff(ang, t) < MIN_SEPARATION_DEG for t in taken_angles):
                    continue
                v = score - W_REACH * math.hypot(a - pa_, l - pl_) + bonus
                if best is None or v > best[0]:
                    best = (v, p, a, l, ang)
        if best is None:
            break
        _, p, a, l, ang = best
        taken_angles.append(ang)
        side = "left" if l < cl - 2.0 else "right" if l > cl + 2.0 else ("ahead" if a > ca else "behind")
        result[id(p)] = (a, l, f"support: come short ({side})")
    for p, _, _ in players:
        p._support_job = id(p) in result
    return result


def _ang_diff(a, b):
    d = abs(math.degrees(a - b)) % 360.0
    return min(d, 360.0 - d)


# ---------------------------------------------------------------------------
IMPORTANCE = {"LCB": 1.0, "RCB": 1.0, "LB": 0.6, "RB": 0.6, "LM": 0.5, "RM": 0.5,
              "LCM": 0.6, "RCM": 0.6, "ST1": 0.7, "ST2": 0.7}


def importance(p, settings):
    imp = IMPORTANCE.get(p.role, 0.5)
    if p.role in ("LCM", "RCM") and settings.get("cm_forward", 0.5) < 0.4:
        imp = 0.85                       # the holding midfielder protects the centre-backs
    if p.role in ("ST1", "ST2") and settings.get("st_style", "pin") == "link":
        imp = 0.45
    return imp


def fill_gaps(entries, busy):
    """
    entries: [(player, slot_a, slot_l, cur_a, cur_l, settings)] for outfield
             players in possession (not the carrier).
    busy:    ids of players who are doing something else (runs, support...)
    Returns {id(player): (a, l, label)} for players sent to cover a gap.
    """
    result = {}
    vacated = []
    for p, sa, sl, ca, cl, s in entries:
        if id(p) in busy:
            vacated.append((importance(p, s), p, sa, sl))
    vacated.sort(key=lambda t: -t[0])
    covering = set()
    for imp, owner, sa, sl in vacated:
        if imp < 0.55:
            continue
        best = None
        for p, pa_, pl_, ca, cl, s in entries:
            if p is owner or id(p) in busy or id(p) in covering or id(p) in result:
                continue
            if any(v[1] is p for v in vacated):
                continue                 # he's away from his own spot too
            if p.role in ("LCB", "RCB") or importance(p, s) >= imp:
                continue
            if _stat(p, "Teamwork") < TEAMWORK_MIN:
                continue
            d = math.hypot(ca - sa, cl - sl)
            if d > FILL_RANGE:
                continue
            if best is None or d < best[0]:
                best = (d, p)
        if best is not None:
            p = best[1]
            covering.add(id(p))
            result[id(p)] = (sa, sl, f"fill the gap: {owner.role}'s spot")
    return result
