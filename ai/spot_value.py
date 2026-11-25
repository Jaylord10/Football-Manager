"""
ai/spot_value.py
================
Judging where to stand when we have the ball.

The team shape (ai/team_shape.py) gives every player a base spot.  This
module lets him improve on it the way a good player would, by looking at
the spots around it and asking:

  1. CAN THE BALL GET TO ME?   Is the passing lane from the ball open - could
     any defender get to the line of the pass before the ball does?  And is
     it a sensible distance (not 2 m, not 45 m)?
  2. HOW MUCH TIME WOULD I HAVE?   When the ball arrives, how long before the
     nearest defender is on me?  ("pitch control")
  3. IS IT DANGEROUS?   How likely is a goal from there (a simple threat map:
     closer and more central = better), and does a pass there go past
     defenders (breaking a line)?
  4. DOES IT MOVE US FORWARD?  Being ahead of the ball gives the man on it
     a forward option - wingers and strikers care most about this.
  5. TEAM RULES:
       - don't stand on top of a teammate, or in his lane at the same height
       - don't stand right behind a teammate as seen from the ball (you'd
         be hiding behind him)
       - full-backs and midfielders nearest the ball stay 8-25 m away:
         close enough to help, far enough to be useful (wingers and
         strikers stay up as outlets)
  6. STAY TRUE TO THE SHAPE: the further from his base spot, the bigger the
     cost - depending on position and role (centre-backs barely move, a
     roaming winger goes where he likes).

Players choose one at a time, nearest to the ball first, so each one knows
where the others have gone.  Off The Ball decides how good the judgement is:
a 20 picks the best spot, a 5 often picks a decent-but-wrong one.  A player
sticks with his current choice unless another is clearly better, so he
doesn't dither.

The overlay (D in the match window) shows what he was after: "come short",
"pull wide", "pocket between the lines", "open a passing angle", ...

All tuning numbers are in the TUNING block.  Distances in metres, in the
team's attacking frame (a = up the pitch from our goal, l = sideways).
"""

import math
import random

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
PITCH_L, HALF_W = 110.0, 35.0
GOAL_A = PITCH_L

# Where he looks
SEARCH_RADIUS = {"FB": 8.0, "CM": 10.0, "WM": 10.0, "ST": 10.0}
RINGS = (4.0, 8.0, 12.0)
DIRECTIONS = [(math.cos(k * math.pi / 4), math.sin(k * math.pi / 4)) for k in range(8)]
EDGE = 2.0

# Weights
W_LANE = 2.0          # open passing lane
W_TIME = 2.0          # time on the ball when it arrives
W_DANGER = 2.5        # threat of the spot (x role's attacking weight)
W_BREAK = 0.8         # per defender a pass there takes out (max 3)
W_SUPPORT = 1.0       # nearest supporters at a good distance from the ball
W_PROGRESS = 1.2      # being ahead of the ball (an outlet that moves us up the pitch)...
PROGRESS_SPAN = 20.0  # ...counted up to this many metres ahead / behind
PROGRESS_WEIGHT = {"FB": 0.7, "CM": 0.9, "WM": 1.3, "ST": 1.0}   # (FB 0.5, CM 0.6 before 21 Nov)
SUPPORT_KINDS = ("FB", "CM")   # who drops in close to support the ball (wingers/strikers stay up)
W_CROWD = 1.5         # too close to a teammate
W_LANE_SHARE = 0.6    # same vertical lane and similar height as a teammate
W_SHADOW = 1.0        # hidden behind a teammate as seen from the ball
TETHER = {"FB": 0.45, "CM": 0.35, "WM": 0.30, "ST": 0.25}   # cost per 10 m from the base spot
ATTACK_WEIGHT = {"FB": 0.6, "CM": 0.8, "WM": 1.0, "ST": 1.0}

# Physics of the judgement
PASS_SPEED = 16.0     # m/s average pass speed
DEF_SPEED = 6.5       # m/s a defender closes down at
DEF_REACTION = 0.25   # s
LANE_REACH = 0.8      # m a defender can stretch to cut a pass out
IDEAL_PASS = (8.0, 25.0)
MAX_PASS = 40.0
CROWD_DIST = 7.0      # m
LANE_WIDTH = 14.0     # five vertical lanes of 14 m across a 70 m pitch
SAME_HEIGHT = 10.0    # m
SUPPORTERS = 3        # this many nearest the ball care about support distance

# Stepping up (Jay, 21 Nov: "a player would simply wait in space to receive the ball when he could have done the
# same thing 5-10 yards further ahead").  Once he's picked his spot he looks further up the pitch from it: if the
# space there is just as open - the ball can still get to him, he'd still have time on it, he's not on top of a
# team-mate - he takes that instead.  The furthest such step wins.
STEP_UP = (4.5, 6.75, 9.0)         # m forward of his spot he looks (5, 7.5, 10 yards)
STEP_UP_LANE = 0.75                # the pass there must still be this open...
STEP_UP_TIME = 0.6                 # ...he'd still have this long on the ball (s)...
STEP_UP_TIME_LOSS = 0.8            # ...and not much less than where he was
STEP_UP_CROWD = 0.35               # ...nor crowding a team-mate more than this
STEP_UP_LIMIT = {"FB": 9.0, "CM": 9.0, "WM": 9.0, "ST": 9.0}   # m: the most each kind steps up
STEP_UP_HOLD = 4.5                 # m: a holding midfielder (cm_forward < 0.3) only steps up this far
STEP_UP_SEE = (0.45, 1.0)          # chance he spots it: Off The Ball 1 -> 20 (re-judged every 0.2 s)

# Decision quality
NOISE_AT_1 = 0.9      # score noise at Off The Ball 1 (0 at 20)
STICKY = 0.25         # bonus for keeping his current choice


from core.stats import stat20 as _stat    # (cached: attributes never change during a match)


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def threat(a, l):
    """Rough chance a move from here ends in a goal (0-~0.6)."""
    d = math.hypot(GOAL_A - a, l)
    centrality = 1.0 - min(1.0, abs(l) / HALF_W) * 0.5
    return 0.6 * math.exp(-d / 16.0) * centrality + 0.01


def kind(role):
    if role in ("LB", "RB"):
        return "FB"
    if role in ("LCM", "RCM"):
        return "CM"
    if role in ("LM", "RM"):
        return "WM"
    return "ST"


def choose(players, slots, ctx):
    """
    players: list of (player, a, l, why, settings) - base spots from the shape
    ctx: dict with ball (a, l), opponents [(a, l)], teammates_fixed [(a, l)]
         (centre-backs etc.), max_a, min_a
    Returns {id(player): (a, l, why)}.
    """
    ba, bl = ctx["ball"]
    opps = ctx["opponents"]
    chosen = list(ctx["fixed"])                       # spots already taken
    result = {}
    # Nearest the ball choose first; provisional spots for the rest
    order = sorted(players, key=lambda t: (t[1] - ba) ** 2 + (t[2] - bl) ** 2)
    provisional = {id(t[0]): (t[1], t[2]) for t in order}
    for rank, (p, a0, l0, why, s) in enumerate(order):
        others = chosen + [v for k, v in provisional.items() if k != id(p)]
        best = _best(p, a0, l0, s, rank, others, ba, bl, opps, ctx)
        a, l, label = best
        provisional.pop(id(p), None)
        chosen.append((a, l))
        if label:
            why = f"{why}: {label}" if why else label
        result[id(p)] = (a, l, why)
    return result


# ---------------------------------------------------------------------------
# HIS OWN AREA (25 Nov - Jay's idea, for the left-sided box-to-box midfielder; ai/team_shape.py marks him):
# "a box-to-box midfielder on the left centre has an area that he scores points for staying in; he then gets more
#  points for receiving the ball further upfield" - and he only shows close to the man on the ball when that man
# really needs it (ai/patterns.py does that, on top).
#   score = how far up the pitch  +  can the pass reach him  +  time on the ball when it arrives
#           - outside his area  - on top of / hidden behind a team-mate
#   A spot the ball can't get to with some space (lane under Z_MIN_LANE or under Z_MIN_TIME s on it) only counts if
#   nothing is on: then he holds a spot in his area a little ahead of the ball, waiting.
# ---------------------------------------------------------------------------
Z_CHANNEL     = 12.0      # m: the middle of his area, this far left of the middle of the pitch (+ half the team's lean)...
Z_HALF_ACROSS = 7.0       # ...and this far either side of it (the left inside channel, ~5-19 m left of centre - not
                          #  the touchline, that's the winger's)
Z_CLEAR       = 5.0       # m: never a spot this close to a team-mate's
Z_BEHIND      = 6.0       # m: the bottom of his area - at most this far behind the ball...
Z_ABOVE_CB    = 6.0       # ...and at least this far ahead of the centre-backs
Z_TOP_GAP     = 16.0      # m: the top of it - the edge of their box (and onside)
Z_STEP        = 3.0       # m between the spots he weighs up
Z_HEIGHT      = 1.0       # per 10 m further up than the ball
Z_LANE        = 1.0       # an open passing lane (0-1)
Z_TIME        = 0.5       # per second on the ball when it arrives (up to 2 s)
Z_MIN_LANE    = 0.7       # the pass must be at least this open...
Z_MIN_TIME    = 0.5       # ...and leave him this long on the ball (s)
Z_MIN_PASS    = 6.0       # m: nearer than this is on top of the man on the ball
Z_OUTSIDE     = 0.25      # per m outside his area
Z_WAIT_AHEAD  = 8.0       # m: nothing on - he waits about this far ahead of the ball, in his area
Z_STICKY      = 0.3       # bonus for staying with the spot he had (so he doesn't dither)

# Which area: "map" - Jay's map (25 Nov, "Left Box to Box.png"), fixed on the pitch; or "channel" - the first
# version (25 Nov, night), the left inside channel moving with the ball.  Both are kept - switch here.
Z_AREA = "map"
# Jay's map, in m (up the pitch from our goal line; across from the middle, left minus):
#   green - where he should mainly be: from 11 m off our goal line to 11 m off theirs, from the middle of the pitch
#           out to ~9 m off the left touchline
#   amber - he can go there, but it's not as good: the whole length, out to ~4 m off the touchline and ~4 m over
#           to the right of the middle
#   anywhere else - not his.
MAP_GREEN = ((11.0, 99.0), (-26.0, 0.0))
MAP_AMBER = ((0.0, 110.0), (-31.0, 4.0))
MAP_AMBER_COST = 0.8      # points off for a spot in amber (about 8 m of height's worth)
MAP_BEHIND = 8.0          # m: a box-to-box keeps up with play - never more than this far behind the ball


def _zone_best(p, s, others, ba, bl, opps, ctx):
    if Z_AREA == "map":
        return _map_best(p, s, others, ba, bl, opps, ctx)
    side_c = 0.5 * s.get("zone_c", 0.0) - Z_CHANNEL
    l_lo, l_hi = max(-HALF_W + EDGE, side_c - Z_HALF_ACROSS), min(HALF_W - EDGE, side_c + Z_HALF_ACROSS)
    a_lo = max(s.get("zone_cb_a", 10.0) + Z_ABOVE_CB, ba - Z_BEHIND)
    a_hi = min(ctx["max_a"], GOAL_A - Z_TOP_GAP)
    if a_hi < a_lo:
        a_lo = a_hi
    otb = _stat(p, "Off The Ball")
    noise = NOISE_AT_1 * (20.0 - otb) / 19.0
    prev = getattr(p, "_zone_spot", None)
    best = None
    a = a_lo - Z_STEP
    while a <= a_hi + 1e-6:
        l = l_lo - Z_STEP
        while l <= l_hi + Z_STEP + 1e-6:
            pass_d = math.hypot(a - ba, l - bl)
            if pass_d >= Z_MIN_PASS and all(math.hypot(ta - a, tl - l) >= Z_CLEAR for ta, tl in others):
                lane, t = lane_and_time(a, l, ba, bl, opps, pass_d)
                outside = max(0.0, a_lo - a) + max(0.0, l_lo - l, l - l_hi)
                crowd = sum((CROWD_DIST - math.hypot(ta - a, tl - l)) / CROWD_DIST
                            for ta, tl in others if math.hypot(ta - a, tl - l) < CROWD_DIST)
                on = lane >= Z_MIN_LANE and t >= Z_MIN_TIME and pass_d <= MAX_PASS
                if on:
                    sc = Z_HEIGHT * (a - ba) / 10.0 + Z_LANE * lane + Z_TIME * _clamp(t, 0.0, 2.0)
                else:
                    sc = -10.0 - 0.1 * abs(a - (ba + Z_WAIT_AHEAD)) + 0.5 * lane
                sc -= Z_OUTSIDE * outside + W_CROWD * crowd
                if prev is not None and math.hypot(a - prev[0], l - prev[1]) < Z_STEP:
                    sc += Z_STICKY
                if noise > 0:
                    sc += random.gauss(0.0, noise * 0.3)
                if best is None or sc > best[0]:
                    best = (sc, a, l, on)
            l += Z_STEP
        a += Z_STEP
    if best is None:
        return None
    _, a, l, on = best
    p._zone_spot = (a, l)
    p._spot_offset = None
    p._stepped_up = False
    return a, l, ("show high in his area" if on else "hold his area: nothing on yet")


def _map_best(p, s, others, ba, bl, opps, ctx):
    """Jay's map: anywhere in green or amber (amber costs MAP_AMBER_COST), keeping up with play (no more than
    MAP_BEHIND behind the ball, 6 m clear of the centre-backs, onside) - the highest spot where he can get the ball
    with some space, as in the channel version."""
    (ga0, ga1), (gl0, gl1) = MAP_GREEN
    (aa0, aa1), (al0, al1) = MAP_AMBER
    a_lo = max(aa0, s.get("zone_cb_a", 10.0) + Z_ABOVE_CB, ba - MAP_BEHIND)
    a_hi = min(aa1 - 1.0, ctx["max_a"])
    if a_hi < a_lo:
        a_lo = a_hi
    otb = _stat(p, "Off The Ball")
    noise = NOISE_AT_1 * (20.0 - otb) / 19.0
    prev = getattr(p, "_zone_spot", None)
    best = None
    a = a_lo
    while a <= a_hi + 1e-6:
        l = max(al0, -HALF_W + EDGE)
        while l <= min(al1, HALF_W - EDGE) + 1e-6:
            pass_d = math.hypot(a - ba, l - bl)
            if pass_d >= Z_MIN_PASS and all(math.hypot(ta - a, tl - l) >= Z_CLEAR for ta, tl in others):
                green = ga0 <= a <= ga1 and gl0 <= l <= gl1
                lane, t = lane_and_time(a, l, ba, bl, opps, pass_d)
                crowd = sum((CROWD_DIST - math.hypot(ta - a, tl - l)) / CROWD_DIST
                            for ta, tl in others if math.hypot(ta - a, tl - l) < CROWD_DIST)
                on = lane >= Z_MIN_LANE and t >= Z_MIN_TIME and pass_d <= MAX_PASS
                if on:
                    sc = Z_HEIGHT * (a - ba) / 10.0 + Z_LANE * lane + Z_TIME * _clamp(t, 0.0, 2.0)
                else:
                    sc = -10.0 - 0.1 * abs(a - (ba + Z_WAIT_AHEAD)) + 0.5 * lane
                sc -= (0.0 if green else MAP_AMBER_COST) + W_CROWD * crowd
                if prev is not None and math.hypot(a - prev[0], l - prev[1]) < Z_STEP:
                    sc += Z_STICKY
                if noise > 0:
                    sc += random.gauss(0.0, noise * 0.3)
                if best is None or sc > best[0]:
                    best = (sc, a, l, on, green)
            l += Z_STEP
        a += Z_STEP
    if best is None:
        return None
    _, a, l, on, green = best
    p._zone_spot = (a, l)
    p._spot_offset = None
    p._stepped_up = False
    where = "green" if green else "amber"
    return a, l, (f"show high in his area ({where})" if on else f"hold his area ({where}): nothing on yet")


def _best(p, a0, l0, s, rank, others, ba, bl, opps, ctx):
    if s.get("zone_b2b"):
        z = _zone_best(p, s, others, ba, bl, opps, ctx)
        if z is not None:
            return z
    k = kind(p.role)
    radius = SEARCH_RADIUS.get(k, 8.0) * (1.0 + 0.5 * s.get("roam", 0.0))
    tether = TETHER.get(k, 0.3) * (1.0 - 0.5 * s.get("roam", 0.0))
    attack_w = ATTACK_WEIGHT.get(k, 0.8)
    prog_w = PROGRESS_WEIGHT.get(k, 0.6)
    supporter = k in SUPPORT_KINDS
    otb = _stat(p, "Off The Ball")
    noise = NOISE_AT_1 * (20.0 - otb) / 19.0
    prev = getattr(p, "_spot_offset", None)

    cands = [(0.0, 0.0)]
    for r in RINGS:
        if r <= radius + 1e-6:
            cands += [(r * dx, r * dy) for dx, dy in DIRECTIONS]
    if prev is not None and math.hypot(*prev) <= radius + 1e-6:
        cands.append(prev)

    best = None
    for da, dl in cands:
        a = _clamp(a0 + da, ctx["min_a"], ctx["max_a"])
        l = _clamp(l0 + dl, -HALF_W + EDGE, HALF_W - EDGE)
        sc, parts = _score(a, l, a0, l0, rank if supporter else 99, others, ba, bl, opps,
                           tether, attack_w, prog_w)
        if prev is not None and abs(da - prev[0]) < 1e-6 and abs(dl - prev[1]) < 1e-6:
            sc += STICKY
        if noise > 0:
            sc += random.gauss(0.0, noise * 0.3)
        if best is None or sc > best[0]:
            best = (sc, a, l, (da, dl), parts)
    _, a, l, off, parts = best
    step = _step_up(p, k, s, a, l, others, ba, bl, opps, ctx, otb, parts)
    if step is not None:
        p._step_from = (a, l)                                         # (for the overlay / pictures)
        a, parts = step
        p._step_to = (a, l)
        off = (a - a0, off[1])
    p._stepped_up = step is not None
    p._spot_offset = off
    if step is not None:
        return a, l, "step up into the space"
    return a, l, _label(a, l, a0, l0, ba, bl, parts)


def _step_up(p, k, s, a, l, others, ba, bl, opps, ctx, otb, parts):
    """Is the same space open 5-10 yards further up?  -> (a, parts) for the furthest that is, or None."""
    if a <= ba - 15.0:
        return None                                   # (well behind the ball: he's the safety, not an outlet)
    lo, hi = STEP_UP_SEE
    if random.random() > lo + (hi - lo) * (otb - 1.0) / 19.0:
        return None
    limit = STEP_UP_LIMIT.get(k, 9.0)
    if k == "CM" and s.get("cm_forward", 0.5) < 0.3:
        limit = STEP_UP_HOLD
    limit = min(limit, STEP_UP[0] + (STEP_UP[-1] - STEP_UP[0]) * _clamp((otb - 5.0) / 10.0, 0.0, 1.0))
    #       (Off The Ball 15+ sees the space 10 yards on; 5 or less only the 5 yards in front of him)
    t0 = parts["time"]
    best = None
    for step in STEP_UP:
        if step > limit + 1e-6:
            break
        a2 = a + step
        if a2 > ctx["max_a"]:
            break                                     # (offside up there)
        lane, t = lane_and_time(a2, l, ba, bl, opps)
        if lane < STEP_UP_LANE or t < STEP_UP_TIME or t < t0 - STEP_UP_TIME_LOSS:
            break                                     # (closed up - and further on won't be better)
        crowd = sum((CROWD_DIST - math.hypot(ta - a2, tl - l)) / CROWD_DIST
                    for ta, tl in others if math.hypot(ta - a2, tl - l) < CROWD_DIST)
        if crowd > STEP_UP_CROWD:
            break
        best = (a2, dict(parts, lane=lane, time=t, pass_d=math.hypot(a2 - ba, l - bl)))
    return best


def lane_and_time(a, l, ba, bl, opps, pass_d=None):
    """
    For a pass from (ba, bl) to (a, l): how open the lane is (0-1) and how
    many seconds he'd have on the ball when it arrives (can be negative).
    """
    hypot = math.hypot
    if pass_d is None:
        pass_d = hypot(a - ba, l - bl)
    t_ball = 0.15 + pass_d / PASS_SPEED

    # Lane open?  Any defender who gets to the line of the pass before the ball?
    lane = 1.0
    if pass_d > 3.0:
        ua, ul = (a - ba) / pass_d, (l - bl) / pass_d
        end = pass_d - 0.5
        for oa, ol in opps:
            along = (oa - ba) * ua + (ol - bl) * ul
            if along <= 0.5 or along >= end:
                continue
            side = abs((oa - ba) * ul - (ol - bl) * ua)
            t_def = DEF_REACTION + max(0.0, side - LANE_REACH) / DEF_SPEED
            t_here = 0.15 + along / PASS_SPEED
            margin = t_def - t_here
            if margin < 0.25:
                lane = min(lane, _clamp((margin + 0.25) / 0.5, 0.0, 1.0))
    if pass_d > MAX_PASS:
        lane *= 0.3

    # Time on the ball when it arrives
    if opps:
        t_def_spot = min([DEF_REACTION + hypot(oa - a, ol - l) / DEF_SPEED for oa, ol in opps])
    else:
        t_def_spot = 9.0
    return lane, t_def_spot - t_ball


def _score(a, l, a0, l0, rank, others, ba, bl, opps, tether, attack_w, prog_w):
    hypot = math.hypot
    pass_d = hypot(a - ba, l - bl)
    # 1 + 2. Lane open? Time on the ball?
    lane, time_on_ball = lane_and_time(a, l, ba, bl, opps, pass_d)
    time_s = _clamp((time_on_ball + 0.5) / 2.5, 0.0, 1.0)

    # 3. Danger, and defenders taken out of the game
    danger = _clamp(threat(a, l) / 0.45, 0.0, 1.0)
    broken = 0
    if a > ba + 3.0:
        broken = sum(1 for oa, ol in opps if ba < oa < a - 1.0 and abs(ol - (bl + (l - bl) * (oa - ba) / (a - ba))) < 12.0)

    # 4. Team rules
    support = 0.0
    if rank < 3:
        lo, hi = IDEAL_PASS
        if pass_d < lo:
            support = -(lo - pass_d) / lo
        elif pass_d > hi:
            support = -min(1.0, (pass_d - hi) / 15.0)
        else:
            support = 0.3
    crowd = shared = shadow = 0.0
    my_lane = int((l + HALF_W) // LANE_WIDTH)
    far_ball = pass_d > 3.0
    if far_ball:
        ua, ul = (a - ba) / pass_d, (l - bl) / pass_d
        shadow_to = pass_d - 2.0
    for ta, tl in others:
        d = hypot(ta - a, tl - l)
        if d < CROWD_DIST:
            crowd += (CROWD_DIST - d) / CROWD_DIST
        if abs(ta - a) < SAME_HEIGHT and int((tl + HALF_W) // LANE_WIDTH) == my_lane:
            shared += 1.0 - abs(ta - a) / SAME_HEIGHT
        # Hidden behind him from the ball?
        if far_ball:
            tb = hypot(ta - ba, tl - bl)
            if 2.0 < tb < shadow_to:
                if abs((ta - ba) * ul - (tl - bl) * ua) < 2.5 and (ta - ba) * ua + (tl - bl) * ul > 0:
                    shadow = 1.0

    drift = hypot(a - a0, l - l0)
    progress = _clamp((a - ba) / PROGRESS_SPAN, -1.0, 1.0)
    score = (W_LANE * lane + W_TIME * time_s + W_DANGER * danger * attack_w
             + W_PROGRESS * progress * prog_w
             + W_BREAK * min(broken, 3) * lane + W_SUPPORT * support
             - W_CROWD * crowd - W_LANE_SHARE * shared - W_SHADOW * shadow
             - tether * drift / 10.0)
    parts = {"lane": lane, "time": time_on_ball, "danger": danger, "broken": broken,
             "opps": opps, "pass_d": pass_d}
    return score, parts


def _label(a, l, a0, l0, ba, bl, parts):
    """Why this spot - for the debug overlay."""
    moved = math.hypot(a - a0, l - l0)
    if moved < 2.0:
        return ""
    opps = parts["opps"]
    ahead = sum(1 for oa, ol in opps if oa > a)
    behind = sum(1 for oa, ol in opps if oa < a)
    room = min((math.hypot(oa - a, ol - l) for oa, ol in opps), default=99.0)
    d0, d1 = math.hypot(a0 - ba, l0 - bl), math.hypot(a - ba, l - bl)
    if ahead >= 4 and behind >= 3 and room >= 5.0 and a > ba:
        return "pocket between the lines"
    if abs(l) > abs(l0) + 3.0:
        return "pull wide"
    if d1 < d0 - 3.0:
        return "come short"
    if a > a0 + 3.0:
        return "get forward"
    return "open a passing angle"
