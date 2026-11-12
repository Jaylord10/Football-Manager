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
PROGRESS_WEIGHT = {"FB": 0.5, "CM": 0.6, "WM": 1.3, "ST": 1.0}
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


def _best(p, a0, l0, s, rank, others, ba, bl, opps, ctx):
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
    p._spot_offset = off
    return a, l, _label(a, l, a0, l0, ba, bl, parts)


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
