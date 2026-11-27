"""
ai/scoreboard.py - the man on the ball weighs up every option on ONE scale (26 Nov, Jay: "I like the idea of the
scoreboard").

The old way (ai/carrier.py _decide) is a checklist: clear it? shoot? killer ball? combination? run with it? man on
him? best way forward? patience? safe pass? - and the FIRST yes wins, so the order decides, not how good the option
is, and every fix added another rule on top.

Here every option gets a value in the same units - the chance his team scores from what happens next - and the best
one wins:

    value = P(it comes off) x (what we have then)  -  P(it doesn't) x (what they have then)

"What we have" with the ball at a spot is its Expected Threat (xT): worked out from 120 real Premier League matches
(StatsBomb open data, dev/xt_grid.py -> data/decide/xt.json).  A shot is worth its real chance of going in (xG, fitted
on the same matches).  Losing the ball costs what THEY then have from that spot - nothing much in their own third,
a lot on the edge of our box.  Pressure isn't a rule: it changes the odds (waiting gets riskier as a man closes;
taking him on is worth it if his dribbling beats the defender and there's grass behind).

The options:
  pass      to each team-mate he sees (lane open? who gets there first? how far? pressed?) - real completion rates
  through   a ball into space for a runner (gameplay/through_pass.py's plan)
  cross     into the box from wide (ai/decisive.py's target), headed chance at the end
  shoot     xG from where he is, less for men in the way / a man on him; Finishing / Long Shots
  carry     run with it, 6 m forward or diagonal: does anyone get there first?
  take_on   go at the man in front of him: gameplay/duels.py's own odds (Dribbling, Agility vs Tackling...) x what's
            beyond him; Flair makes him fancy it more
  hold      keep it / shield it a moment: how likely is he to lose it if he waits (Strength, Balance)
  clear     get rid of it (ai/clearance.py's aim): a 50-50 wherever it lands

His attributes decide how WELL he judges it: Decisions (and Composure when a man's on him) set how far off his sense
of each value is, Vision whether he even sees team-mates out of his eyeline (unless he'd scanned).

Switch: FM_DECIDE=scoreboard (or ENABLED below).  The old checklist stays the default until Jay says.
"What was he thinking": every decision's options and values go in LOG (FM_DECISION_LOG=1) and on the player as
_options (dev/decisions.py prints them).
"""

import json
import math
import os
import random

from pygame.math import Vector2

from config.constants import WIDTH, HEIGHT, M_TO_PX

ENABLED = os.environ.get("FM_DECIDE", "") == "scoreboard"
LOG_ON = bool(os.environ.get("FM_DECISION_LOG"))
LOG = []
LOG_MAX = 20000

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
PITCH_L, HALF_W = 110.0, 35.0
GOAL_W = 7.32
CARRY_M = 6.0              # m he runs with it, per decision
CARRY_SPEED = 5.0          # m/s with the ball
CARRY_ANGLES = (0, 35, -35, 70, -70)
CARRY_LOST = 0.03          # lost per carry with nobody near (real: 3.1% of carries end dispossessed / miscontrol)
CARRY_MIN_GAP = 2.5        # m: a man nearer than this - running with it is a take-on (or a shield), not a carry
CARRY_CLOSE = (6.0, 0.35)  # a man within 6 m: up to this much more risk (he closes as you go)
CHASER_SPEED = 6.5         # m/s an opponent closes at...
CHASER_REACT = 0.25        # ...after this long
TAKE_ON_RANGE = 6.0        # m: a man in front within this can be taken on
TAKE_ON_BEYOND = 5.0       # m past him he'd be if he beats him
HOLD_SAFE = 7.0            # m: nobody nearer - keeping it is (nearly) free
HOLD_LOSS_MAX = 0.30       # chance of losing it if he waits with a man right on him (average Strength)
HOLD_COST = 0.003          # waiting isn't free: they get back into shape (in xT units)
PRESSED_M = 3.0            # a man this close = he's passing under pressure (real completion falls)
# SPACE (27 Nov, Jay: "a carry towards 11 players isn't sensible", "he shouldn't pass to ST2, he's marked", the free
# LM for a switch): the real values are averages for an area - here a spot is worth more the longer he'd have there
# before anyone can close him down, and more again if there's grass ahead to run into (one move ahead).
SPACE_MIN = 0.4            # x a spot's value with a man on him as he gets there (marked)
SPACE_MIN_GOAL = 0.75      # ...for a carry in their third: heading for goal matters more than space there (27 Nov,
                           # Jay: "the carry towards goal threat needs to matter in the final third")
NEXT_W = 0.7               # a carry also counts for the best pass he'd have from where it takes him (towards free
                           # team-mates, then switch it - Jay), with the man who comes out to him taken off whoever
                           # he was marking (drag the full-back across and the striker's free - Jay); marked down
                           # because the defenders get back while he carries (27 Nov, Jay - was 0.9)
PRESSED_NO_BACK = 120.0    # deg: with a man on him he can't pass to anyone further round than this from the way he's
                           # facing - he'd have to turn into the man (27 Nov, Jay: "the LB shouldn't be an option")
ACROSS_FROM = (85.0, 14.0) # a ball across the box: he's past this far up and at least this far out wide...
ACROSS_TO = (85.0, 14.0)   # ...to a team-mate past this far up and within this of the middle
ACROSS_AHEAD = (0.0, 2.0, 4.0)  # m in front of him (towards goal) it could go
FIRST_TIME_FINISH = 0.85   # x a shot's chance when he has to hit it first time
THIRD = 110.0 / 3
SPACE_FULL = 1.5           # s he'd have before anyone gets to him, for the full value
LOOK_M = (5.0, 40.0)       # m: how far he could run from there before anyone can get across him (5 m steps, up to
                           # 25 m: a whole free flank)...
LOOK_W = 0.6               # ...and the share of what it gains that counts now
PASS_SPEED = (12.0, 0.25)  # m/s a pass travels at, on average: 12 + this x its length (a long ball is struck harder)
CARRY_SLOW = 1.0           # x a carry's value: running with it gives the defence time to get back in shape
TAKE_ON_LOSS = (1.25, 0.75) # x what losing a take-on costs, outside their third / in it (27 Nov, Jay: lose it in
                           # midfield and the team's left massively exposed - a counter with your men committed)
CLEAR_FROM = 36.0          # m from our goal: clearing is an option nearer than this...
CLEAR_PRESSED = 6.0        # ...with a man within this
CLEAR_OURS = 0.25          # share of clearances we end up with
PASS_MIN, PASS_MAX = 4.0, 60.0
SEE_OUT_OF_CONE = (0.30, 0.035)   # chance he knows about a team-mate BEHIND him (unless he'd scanned): + per Vision
                                  # point.  Anyone in front of him or to the side he always knows about (27 Nov, Jay:
                                  # the striker 10 m ahead was left off his list)
BEHIND_DEG = 100.0                # a team-mate more than this far round from the way he's facing is "behind him"
TAKE_ON_MIN = (0.65, 0.52, 0.42)    # he only thinks about taking a man on with at least this chance of beating him -
                                  # in our third / midfield / their third (27 Nov, Jay: outside their third only if he's
                                  # exceptional)
                                  # (real take-ons are won 59% of the time - players don't try the hopeless ones)
TAKE_ON_LANE = 4.0                # m either side of his way to goal: a man in here, in front, is the one in his path
CARRY_BLOCK = (2.5, 60.0)         # a man within 2.5 m and within 60 deg of a carry's direction blocks that carry
PURSUER = (3.0, 0.35)             # a man within 3 m of him (even behind - trying to tackle him, 27 Nov, Jay): up to
                                  # this much more risk on any carry
CROSS_IN_FRONT = 0.3              # x a cross's value when it's aimed in front of their back line, not in behind
JUDGE_NOISE = (0.12, 0.005)       # how far off his sense of a value is (x |value|): - per Decisions point (27 Nov,
                                  # Jay: an average player picked the 2nd-best option far too often - was 0.30)
NOISE_FLOOR = 0.003               # (values near zero still get some noise)
PRESSED_NOISE = 0.5               # x more under pressure, less with Composure
FLAIR_TAKE_ON = 0.03              # per Flair point above 10: how much more a take-on appeals
CROSS_BASE = 0.11                 # crosses that find a man in OUR matches (aimed in behind: 15%; real ones 29%)
CROSS_TO = (98.0, 8.0)            # a cross is met at least this far up (12 m out) and within this of the middle
SHOT_BLOCK = 0.75                 # x per man in the way within 6 m (about a quarter of real shots are blocked)
SHOT_ON_HIM = 0.6                 # x with a man within 1.5 m
SHOT_MIN_XG = 0.012               # not worth considering below this
SHOT_APPEAL = (1.7, 0.95)         # x a shot's value, in the box / from outside it: real players shoot far more than
                                  # "keep it and wait for a better one" says, in the box above all (26 shots a match,
                                  # 58% from inside the box - StatsBomb, PL 2015/16)
TAKE_ON_APPEAL = 1.4              # x what beating him gains: real players take men on ~38 times a match
CHASER_RISK = 0.35                # risk per opponent who can get across a carry
PASS_COST = 0.0013                # a pass that doesn't go 5 m+ forward isn't free either: the defence gets organised
                                  # (tuned so moves last ~4.6 passes, as real ones do - StatsBomb)
LOSS_WEIGHT = 0.75                # x what losing it costs: real players take more risk than a cold sum of the odds
LONG_FAIL = (15.0, 35.0)          # m: a pass lost - near the middle of a short one, near the end of a long one

_DATA = None


def _data():
    global _DATA
    if _DATA is None:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "decide")
        xt = json.load(open(os.path.join(base, "xt.json")))
        xg = json.load(open(os.path.join(base, "xg.json")))
        table = {}
        for k, v in xt["pass_ok"].items():
            band = int(k.split("-")[0]) // 10
            table[(band, k.endswith("pressed"))] = v
        odds = os.path.join(base, "pass_odds.json")
        pw = json.load(open(odds))["w"] if os.path.exists(odds) else None
        _DATA = {"xt": xt["xt"], "na": xt["na"], "nl": xt["nl"], "xg_w": xg["w"], "pass_ok": table, "pass_w": pw}
    return _DATA


# ---------------------------------------------------------------------------
# Real values
# ---------------------------------------------------------------------------
def xt(a, l):
    """Expected Threat with the ball at (a, l) in our frame (m): bilinear between cell centres."""
    d = _data()
    na, nl, g = d["na"], d["nl"], d["xt"]
    x = min(max(a / PITCH_L * na - 0.5, 0.0), na - 1.0)
    y = min(max((l + HALF_W) / (2 * HALF_W) * nl - 0.5, 0.0), nl - 1.0)
    i, j = int(x), int(y)
    i2, j2 = min(i + 1, na - 1), min(j + 1, nl - 1)
    fx, fy = x - i, y - j
    return (g[i][j] * (1 - fx) * (1 - fy) + g[i2][j] * fx * (1 - fy)
            + g[i][j2] * (1 - fx) * fy + g[i2][j2] * fx * fy)


def xt_them(a, l):
    """What THEY have with the ball at our (a, l)."""
    return xt(PITCH_L - a, -l)


def xg(a, l, header=False):
    """A shot's real chance of going in from (a, l) (no defenders): logistic on distance and angle (dev/xg.json)."""
    dx, dy = PITCH_L - a, l
    dist = math.hypot(dx, dy)
    ang = abs(math.atan2(dy + GOAL_W / 2, dx) - math.atan2(dy - GOAL_W / 2, dx))
    w = _data()["xg_w"]
    feats = [1.0, dist / 10.0, ang, (dist / 10.0) ** 2, 1.0 if header else 0.0]
    z = sum(p * q for p, q in zip(w, feats))
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def best_pass_from(a, l, mates, opps, t_arrive):
    """The best pass he'd have from (a, l), getting there t_arrive s from now - with the defender nearest that spot
    taken out (he's had to come out to the man on the ball).  mates: [(a, l)]."""
    import ai.spot_value as spot_value
    if not opps:
        return 0.0
    k = min(range(len(opps)), key=lambda i: math.hypot(opps[i][0] - a, opps[i][1] - l))
    rest = opps[:k] + opps[k + 1:]
    best = None
    for ma, ml in mates:
        L = math.hypot(ma - a, ml - l)
        if L < PASS_MIN or L > 45.0:
            continue
        lane, t = spot_value.lane_and_time(ma, ml, a, l, rest, L)
        p = pass_odds(L, lane, t, False)
        v = p * space_value(ma, ml, rest, t_arrive + pass_time(L)) \
            - LOSS_WEIGHT * (1 - p) * xt_them(a + 0.6 * (ma - a), l + 0.6 * (ml - l))
        if best is None or v > best:
            best = v
    return best or 0.0


BEHIND_AHEAD = (6.0, 10.0, 14.0, 18.0, 24.0)   # m in front of him the ball could go...
BEHIND_SIDE = (0.0, -3.0, 3.0)                 # ...and m either side (to go round the man he's just beaten)
BEHIND_HARD = (1.0, 1.2)                       # x the speed that arrives with him: hit hard, it gets past men
                                               # sooner and he runs onto it (27 Nov, Jay: "on the floor but hit hard")
BEHIND_REACT = 0.0         # s: a striker on the shoulder times his run - he goes as the ball's struck
BEHIND_ACCEL = 6.0         # m/s^2 from a standing start (a sprinter's first steps)...
BEHIND_TOP = 8.0           # ...up to this
HOPEFUL = 0.4              # a ball with less chance than this of coming off is a "hopeful" one: real players
                           # mostly don't play them however good the end of it looks - x (p / HOPEFUL)^2 on what it
                           # gains (27 Nov, Jay: over the top only if he's an exceptional passer)
BEHIND_LOFT = 0.5          # elevation of a ball chipped over the top (when along the ground it'd be cut out)
BEHIND_LOFT_END = 6.0      # m: a chipped ball can only be reached in its first and last few metres
BEHIND_MAX = 45.0          # m: no ball in behind longer than this (a 70 m diagonal isn't a through ball)
BEHIND_TURN = 0.5          # s a defender loses turning to chase a ball played in behind him (he's been facing the
                           # ball) - the striker on his shoulder's head start


def _in_behind(carrier, teammates, opponents, opps, ca, cl, passing):
    """Balls into space for a team-mate up on (or past) their last line: aimed where he gets to before any defender
    or the keeper (gameplay/through_pass.py's race), towards goal.  Returns [(value, mate, plan, p)]."""
    import gameplay.through_pass as tp
    from ai.team_shape import to_frame, to_world
    out = []
    if not opps:
        return out
    last = max(oa for oa, ol in opps)                 # (their deepest outfield man - the keeper's behind him)
    for m in teammates:
        ma, ml = to_frame(carrier.team, m.pos)
        if ma < ca + 5.0 or ma < last - 3.0 or ma > last + 1.0:      # (up on their line, ahead of the ball)
            continue
        try:
            if tp.is_offside_now(m, carrier, opponents):
                continue
        except Exception:
            pass
        gx, gl = PITCH_L - ma, -ml
        g = math.hypot(gx, gl) or 1.0
        best = None
        for ahead, side in [(x, y) for x in BEHIND_AHEAD for y in BEHIND_SIDE]:
            # towards goal, a little straighter than the line to the near post
            pa = ma + ahead * (0.5 * gx / g + 0.5)
            pl = ml + ahead * (0.5 * gl / g) + side
            if pa > PITCH_L - 6.0 or abs(pl) > HALF_W - 2.0:
                continue
            # his run from a standing start: when does he get there?
            t_top = BEHIND_TOP / BEHIND_ACCEL
            d_acc = 0.5 * BEHIND_ACCEL * t_top * t_top
            t_run = BEHIND_REACT + (math.sqrt(2 * ahead / BEHIND_ACCEL) if ahead <= d_acc
                                    else t_top + (ahead - d_acc) / BEHIND_TOP)
            point = to_world(carrier.team, pa, pl)
            d_m = (point - carrier.pos).length() / M_TO_PX
            if d_m < tp.MIN_PASS_DIST or d_m > BEHIND_MAX:
                continue
            # along the ground if it gets through, otherwise chipped over the top
            loft = 0.0
            k_t = tp._K_GROUND ** t_run
            v_sync = d_m * tp._NEG_LN_K / (1.0 - k_t)
            safety = None
            for hard in BEHIND_HARD:
                v_pass = v_sync * hard
                if v_pass <= tp.MAX_PASS_SPEED and tp.ARRIVAL_SPEED[0] <= v_pass * k_t <= tp.ARRIVAL_SPEED[1] + 6.0:
                    safety = _race_behind(carrier, point, v_pass, t_run, opponents, tp, runner=m)
                    if safety is not None:
                        break
            if safety is None and d_m > 15.0:
                k_air = 0.995 ** 60
                v_air = d_m * -math.log(k_air) / (1.0 - k_air ** t_run)
                if v_air <= 32.0:
                    safety = _race_behind(carrier, point, v_air, t_run, opponents, tp, lofted=True, runner=m)
                    if safety is not None:
                        loft, v_pass = BEHIND_LOFT, v_air
            if safety is None:
                continue
            # (a chip over three men needs a real passer - Jay; along the floor less so)
            skill = 0.012 if not loft else 0.04
            p = _clamp((0.4 if not loft else 0.2) + 0.3 * min(safety, 1.0) + skill * (passing - 10), 0.1, 0.85)
            gain = p * space_value(pa, pl, opps, t_run, running_on=True)
            if p < HOPEFUL:
                gain *= (p / HOPEFUL) ** 2
            v = gain - LOSS_WEIGHT * (1 - p) * xt_them(pa, pl)
            if best is None or v > best[0]:
                plan = {"point": point, "speed_px": v_pass * M_TO_PX, "lead_time": t_run, "safety": safety,
                        "value": v, "score": v, "runner": m, "elevation": loft}
                best = (v, m, plan, p)
        if best:
            out.append(best)
    return out


BEATEN_M = 2.5             # m: a defender this close behind the runner (and on his own side of him) has been beaten
                           # - he can't cut out a ball played in front of the runner without going through him


def _race_behind(carrier, point, v_pass, t_run, opponents, tp, lofted=False, runner=None):
    """gameplay/through_pass.py's race (can anyone cut the pass out, or get to the spot before the runner?), with
    defenders who have to turn and chase back towards their own goal losing BEHIND_TURN."""
    from ai.team_shape import to_frame
    path = point - carrier.pos
    length_m = path.length() / M_TO_PX
    if length_m <= 0:
        return None
    direction = path / path.length()
    pa, _ = to_frame(carrier.team, point)
    ra, rl = to_frame(carrier.team, runner.pos) if runner is not None else (None, None)
    margin = 9.9
    for opp in opponents:
        oa0, ol0 = to_frame(carrier.team, opp.pos)
        beaten = runner is not None and opp.role != "GK" and oa0 < ra and math.hypot(oa0 - ra, ol0 - rl) < BEATEN_M
        gk = opp.role == "GK"
        reach = tp.GK_REACH if gk else tp.DEF_REACH
        spd = tp.GK_SPEED if gk else tp.DEF_SPEED
        rel = opp.pos - carrier.pos
        along = rel.dot(direction) / M_TO_PX
        if not beaten and 0.0 < along < length_m and \
                (not lofted or along < BEHIND_LOFT_END or along > length_m - BEHIND_LOFT_END):
            side = abs(rel.x * direction.y - rel.y * direction.x) / M_TO_PX
            t_ball = tp._ball_time_to(along, v_pass)
            if t_ball is not None:
                t_def = tp.DEF_REACTION + max(0.0, side - reach) / spd
                if t_def <= t_ball:
                    return None
                margin = min(margin, t_def - t_ball)
        oa, _ = to_frame(carrier.team, opp.pos)
        turn = BEHIND_TURN if (not gk and pa > oa) else 0.0
        to_point = (opp.pos - point).length() / M_TO_PX
        t_def = tp.DEF_REACTION + turn + max(0.0, to_point - reach) / spd
        m2 = t_def - (t_run + tp.RUNNER_HEAD_START)
        if m2 <= 0:
            return None
        margin = min(margin, m2)
    return margin


def pass_time(length):
    """s for a pass of this length to get there."""
    return 0.2 + length / (PASS_SPEED[0] + PASS_SPEED[1] * length)


CHASER_BEHIND = 0.6        # s more a defender behind a man running onto a ball in behind needs (he's chasing, not
                           # in front of him)


def space_value(a, l, opps, t_arrive=0.0, look=True, smin=None, running_on=False):
    """What having the ball at (a, l) is worth to us, getting there t_arrive s from now: the spot's real value (xT)
    scaled by the time he'd have there before anyone can close him down (marked: SPACE_MIN of it .. SPACE_FULL s
    free: all of it), plus - one move ahead - part of what a free run from there (LOOK_M forward or diagonal, nobody
    able to get across it) would gain."""
    base = xt(a, l)
    free = min((CHASER_REACT + math.hypot(oa - a, ol - l) / CHASER_SPEED
                + (CHASER_BEHIND if running_on and oa < a else 0.0) for oa, ol in opps), default=9.0) - t_arrive
    smin = SPACE_MIN if smin is None else smin
    v = base * (smin + (1.0 - smin) * _clamp(free / SPACE_FULL, 0.0, 1.0))
    if look:
        best = 0.0
        for ang in (0.0, 35.0, -35.0):
            r = math.radians(ang)
            dist = LOOK_M[0]
            while dist <= LOOK_M[1] + 1e-6:
                a2, l2 = a + dist * math.cos(r), l + dist * math.sin(r)
                if not (0.0 < a2 < PITCH_L and abs(l2) < HALF_W - 1.0):
                    break
                t_run = t_arrive + dist / CARRY_SPEED
                if any(CHASER_REACT + math.hypot(oa - a2, ol - l2) / CHASER_SPEED <= t_run - 0.3 for oa, ol in opps):
                    break                                 # (someone gets across him by here)
                best = max(best, xt(a2, l2) - base)
                dist += LOOK_M[0]
        v += LOOK_W * best
    return v


def pass_odds(length, lane, t_recv, pressed):
    """How often a pass like this really reaches its man in our matches (dev/pass_odds.py fits it on the engine's own
    passes): length, how open the lane is, the receiver's time when it arrives, the passer pressed or not.  Falls back
    to the real completion rate by length (with the lane) if it hasn't been fitted."""
    w = _data()["pass_w"]
    if w is None:
        p = pass_base(length, pressed) * (0.25 + 0.75 * lane)
        return p * max(0.25, 1.0 + t_recv) if t_recv < 0 else p
    tc = max(-2.0, min(3.0, t_recv))
    f = [1.0, length / 10.0, (length / 10.0) ** 2, lane, tc, tc * tc, 1.0 if pressed else 0.0]
    z = sum(a * b for a, b in zip(w, f))
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def pass_base(length, pressed):
    """Real share of open-play passes of this length that reach a team-mate (StatsBomb, PL 2015/16)."""
    t = _data()["pass_ok"]
    band = min(5, int(length / 10))
    return t.get((band, pressed), t.get((band, False), 0.5))


# ---------------------------------------------------------------------------
def _stat(p, name, default=None):
    v = p.attributes.get(name, default if default is not None else 10)
    if v is None:
        v = 10
    if v > 25:
        v /= 5.0
    return max(1.0, min(20.0, float(v)))


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def decide(carrier, teammates, teammates_with_gk, opponents, field_opps, ball, now, mechanics):
    """Weigh up every option, do the best one (as he judges it).  Returns his team id."""
    import ai.spot_value as spot_value
    from ai.team_shape import to_frame, to_world

    tid = carrier.team
    ca, cl = to_frame(tid, carrier.pos)
    opp_list = [o for o in field_opps if getattr(o, "is_active", True)]
    opps = [to_frame(tid, o.pos) for o in opp_list]
    near_d, near_o = 99.0, None
    for o, (oa, ol) in zip(opp_list, opps):
        d = math.hypot(oa - ca, ol - cl)
        if d < near_d:
            near_d, near_o = d, o
    pressed = near_d < PRESSED_M
    here_us, here_them = xt(ca, cl), xt_them(ca, cl)
    goal_dir = Vector2(1, 0) if tid == 0 else Vector2(-1, 0)

    # A shield he's just started: hold it a moment (shielding is slow and deliberate)
    if carrier.state == "shield" and now - getattr(carrier, "last_decision_time", -9) < 0.6:
        return tid

    opts = []           # (value, kind, target, extra, p)

    # --- passes -------------------------------------------------------------
    from ai.vision import can_see_teammate
    picture = getattr(carrier, "_picture", False)
    vision = _stat(carrier, "Vision", carrier.attributes.get("Decisions", 10))
    see_p = SEE_OUT_OF_CONE[0] + SEE_OUT_OF_CONE[1] * vision
    passing = _stat(carrier, "Passing")
    for m in teammates_with_gk:
        ma, ml = to_frame(tid, m.pos)
        L = math.hypot(ma - ca, ml - cl)
        if L < PASS_MIN or L > PASS_MAX:
            continue
        if not picture and _behind(carrier, m) and random.random() > see_p:
            continue
        if pressed and _angle_from_facing(carrier, m) > PRESSED_NO_BACK:
            continue
        lane, t = spot_value.lane_and_time(ma, ml, ca, cl, opps, L)
        p = _clamp(pass_odds(L, lane, t, pressed) + 0.012 * (passing - 10), 0.03, 0.97)
        v_ok = space_value(ma, ml, opps, pass_time(L))
        f = 0.6 + 0.35 * _clamp((L - LONG_FAIL[0]) / (LONG_FAIL[1] - LONG_FAIL[0]), 0.0, 1.0)
        fa, fl = ca + f * (ma - ca), cl + f * (ml - cl)
        cost = PASS_COST if ma - ca < 5.0 else 0.0
        if p < HOPEFUL:
            v_ok *= (p / HOPEFUL) ** 2
        opts.append((p * v_ok - LOSS_WEIGHT * (1 - p) * xt_them(fa, fl) - cost, "pass", m, None, p))

    # --- through ball into space ---------------------------------------------
    try:
        import ai.decisive as decisive
        tgt, sc = decisive.score_through_ball_opportunity(carrier, teammates, opponents)
        plan = decisive.last_through_plan
        if tgt is not None and plan is not None:
            pa, pl = to_frame(tid, Vector2(plan["point"]))
            p = _clamp(0.35 + 0.45 * min(plan.get("safety", 0.5), 1.0) + 0.01 * (passing - 10), 0.1, 0.9)
            v_t = space_value(pa, pl, opps, pass_time(math.hypot(pa - ca, pl - cl)))
            opts.append((p * v_t - LOSS_WEIGHT * (1 - p) * xt_them(pa, pl), "through", tgt, plan, p))
    except Exception:
        pass

    # --- a ball in behind for a man on their last line (27 Nov, Jay: "he MUST play it to ST1, he's through on
    #     goal" - the old through-ball plan only works for a man already running) ------------------------------
    for v, tgt, plan, p in _in_behind(carrier, teammates, opponents, opps, ca, cl, passing):
        opts.append((v, "through", tgt, plan, p))

    # --- a ball across the box, in front of the runners (27 Nov, Jay: "ST1 and ST2 are both beyond their markers - it
    #     needs a ball just in front of them") -------------------------------------------------------------------
    for v, tgt, plan, p in _across_box(carrier, teammates, opponents, opps, ca, cl, passing):
        opts.append((v, "through", tgt, plan, p))

    # --- cross ---------------------------------------------------------------
    try:
        import ai.decisive as decisive
        tgt, sc = decisive.score_decisive_cross(carrier, teammates, opponents)
        if tgt is not None:
            # (27 Nov, Jay: "a decent option provided it's in behind the centre-backs - to the edge of the area it's
            #  poor": valued where gameplay/crossing.py really aims it, less when that's in front of their line)
            import gameplay.crossing as crossing_mod
            ta, tl = to_frame(tid, crossing_mod._aim(carrier, tgt, opponents, "cross"))
            line = sorted((oa for oa, ol in opps), reverse=True)
            behind = bool(line) and ta > line[0] - 1.0 or (len(line) > 1 and ta > line[1] + 1.0)
            crossing = _stat(carrier, "Crossing")
            p = _clamp(CROSS_BASE * (0.6 + 0.8 * sc / 100.0) + 0.01 * (crossing - 10), 0.05, 0.6)
            import roles.library as rl
            want = rl.instructions_for(carrier).get("crossing", "normal")
            p_v = p * (1.2 if want == "more" else 0.8 if want == "less" else 1.0)
            v_cross = xg(ta, tl, header=True) * (1.0 if behind else CROSS_IN_FRONT)
            opts.append((p_v * v_cross - LOSS_WEIGHT * (1 - p) * xt_them(ta, tl), "cross", tgt, (ta, tl), p))
    except Exception:
        pass

    # --- shoot ---------------------------------------------------------------
    if ca > PITCH_L / 2:
        chance = raw = xg(ca, cl)
        if raw >= SHOT_MIN_XG:
            gx = PITCH_L
            in_way = 0
            for oa, ol in opps:
                if oa <= ca or math.hypot(oa - ca, ol - cl) > 6.0:
                    continue
                # inside the triangle from him to the posts?
                f = (oa - ca) / max(0.1, gx - ca)
                lo = cl + f * (-GOAL_W / 2 - cl) - 0.5
                hi = cl + f * (GOAL_W / 2 - cl) + 0.5
                if lo <= ol <= hi:
                    in_way += 1
            chance *= SHOT_BLOCK ** in_way
            if near_d < 1.5:
                chance *= SHOT_ON_HIM
            skill = _stat(carrier, "Finishing") if math.hypot(PITCH_L - ca, cl) < 16.5 else \
                _stat(carrier, "Long Shots", carrier.attributes.get("Finishing", 10))
            chance *= 1.0 + 0.03 * (skill - 10)
            if True:
                # (missed or saved: their goal kick / keeper's ball, at their end of the pitch)
                in_box = PITCH_L - ca <= 16.5 and abs(cl) <= 20.16
                opts.append((SHOT_APPEAL[0 if in_box else 1] * chance - (1 - chance) * xt_them(PITCH_L - 5.0, 0.0), "shoot", None, None,
                             chance))

    # --- run with it ---------------------------------------------------------
    mates_fr = [to_frame(tid, m.pos) for m in teammates_with_gk if m is not carrier]
    dribbling = _stat(carrier, "Dribbling")
    # (in their third his carries point at goal - "straight on" is at the goal, not up the touchline; Jay 27 Nov)
    base_ang = math.degrees(math.atan2(-cl, PITCH_L - ca)) if ca >= 2 * THIRD else 0.0
    for ang0 in CARRY_ANGLES:
        ang = ang0 + base_ang
        r = math.radians(ang)
        ta, tl = ca + CARRY_M * math.cos(r), cl + CARRY_M * math.sin(r)
        if any(math.hypot(oa - ca, ol - cl) < CARRY_BLOCK[0]
               and abs(_angle_diff(math.degrees(math.atan2(ol - cl, oa - ca)), ang)) < CARRY_BLOCK[1]
               for oa, ol in opps):
            continue                                  # (a man right there, that way: that's a take-on, not a carry)
        if not (2.0 < ta < PITCH_L - 2.0 and abs(tl) < HALF_W - 1.5):
            continue
        t_me = CARRY_M / CARRY_SPEED
        risk = CARRY_LOST * (1.3 - 0.03 * (dribbling - 10))
        risk += PURSUER[1] * _clamp((PURSUER[0] - near_d) / PURSUER[0], 0.0, 1.0) * (1.2 - 0.02 * (dribbling - 10))
        risk += CARRY_CLOSE[1] * _clamp((CARRY_CLOSE[0] - near_d) / (CARRY_CLOSE[0] - CARRY_MIN_GAP), 0.0, 1.0) \
            * _closing_share(ca, cl, ang, opps, near_d)
        for oa, ol in opps:
            # can he get to the line of my run before I'm past him?
            best = 99.0
            for k in (0.33, 0.66, 1.0):
                pa, pl = ca + k * (ta - ca), cl + k * (tl - cl)
                t_o = CHASER_REACT + math.hypot(oa - pa, ol - pl) / CHASER_SPEED
                best = min(best, t_o - k * t_me)
            risk += CHASER_RISK * _clamp((0.3 - best) / 0.8, 0.0, 1.0)
        risk = _clamp(risk, 0.02, 0.9)
        there = space_value(ta, tl, opps, t_me, smin=SPACE_MIN_GOAL if ta >= 2 * THIRD else None)
        there = max(there, NEXT_W * best_pass_from(ta, tl, mates_fr, opps, t_me))
        opts.append(((1 - risk) * there * CARRY_SLOW - LOSS_WEIGHT * risk * here_them,
                     "carry", (ta, tl), None,
                     1 - risk))

    # --- take the man on -----------------------------------------------------
    # (27 Nov, Jay: "dribble at the last defender" - the man IN HIS PATH, not just whoever's nearest)
    in_path = [(math.hypot(oa - ca, ol - cl), o) for o, (oa, ol) in zip(opp_list, opps)
               if 0.0 < oa - ca and abs(ol - cl) < TAKE_ON_LANE and math.hypot(oa - ca, ol - cl) < TAKE_ON_RANGE + 2.0]
    if in_path:
        d_path, man = min(in_path, key=lambda x: x[0])
        import gameplay.duels as duels
        p = _clamp(duels.takeon_chance(carrier, man, field_opps), 0.05, 0.95)
        oa, ol = to_frame(tid, man.pos)
        zone = 0 if ca < THIRD else 1 if ca < 2 * THIRD else 2
        if p >= TAKE_ON_MIN[zone]:
            ba, bl = oa + TAKE_ON_BEYOND, ol + (2.0 if ol < cl else -2.0)
            gain = p * space_value(ba, bl, [o for o in opps if o != (oa, ol)], 1.0) * TAKE_ON_APPEAL * (1.0 + FLAIR_TAKE_ON * (_stat(carrier, "Flair") - 10))
            opts.append((gain - TAKE_ON_LOSS[0 if zone < 2 else 1] * (1 - p) * here_them, "take_on", man, (ba, bl), p))

    # --- keep it / shield it ---------------------------------------------------
    if near_d >= HOLD_SAFE:
        lose = 0.01
    else:
        lose = HOLD_LOSS_MAX * _clamp((HOLD_SAFE - near_d) / (HOLD_SAFE - 1.0), 0.0, 1.0)
        lose *= 1.25 - 0.025 * (_stat(carrier, "Strength") - 10) - 0.0125 * (_stat(carrier, "Balance") - 10)
        lose = _clamp(lose, 0.01, 0.9)
    here_now = space_value(ca, cl, opps, 0.5, look=False)
    opts.append(((1 - lose) * here_now - LOSS_WEIGHT * lose * here_them - HOLD_COST, "hold", None, None, 1 - lose))

    # --- get rid of it ------------------------------------------------------------
    if ca < CLEAR_FROM and near_d < CLEAR_PRESSED:
        try:
            import ai.clearance as clearance
            kind, aim = clearance.plan(carrier, teammates, field_opps, pressed)
            la, ll = to_frame(tid, Vector2(aim))
            if kind == "touch":
                v = -0.7 * xt_them(la, ll)
            else:
                v = CLEAR_OURS * xt(la, ll) - (1 - CLEAR_OURS) * xt_them(la, ll)
            opts.append((v, "clear", (kind, aim), None, CLEAR_OURS))
        except Exception:
            pass

    if not opts:
        return tid

    # --- how well he judges them -------------------------------------------------
    sigma = JUDGE_NOISE[0] - JUDGE_NOISE[1] * _stat(carrier, "Decisions")
    if pressed:
        sigma *= 1.0 + PRESSED_NOISE * (1.0 - _stat(carrier, "Composure") / 20.0)
    judged = [(v + random.gauss(0.0, sigma) * (abs(v) + NOISE_FLOOR), v, kind, tgt, extra, p)
              for v, kind, tgt, extra, p in opts]
    judged.sort(key=lambda x: -x[0])
    seen, v, kind, tgt, extra, p = judged[0]

    carrier._options = [(round(j[1], 4), j[2], _name(j[3])) for j in judged[:8]]
    if LOG_ON:
        mates_at = [[round(x, 1) for x in to_frame(tid, m.pos)] + [m.role] for m in teammates_with_gk]
        LOG.append({"mates": mates_at, "opps": [[round(a, 1), round(l, 1)] for a, l in opps],
                    "facing": _facing_deg(carrier),
                    "t": round(now, 2), "team": tid, "player": getattr(carrier, "name", "?"),
                    "role": carrier.role, "a": round(ca, 1), "l": round(cl, 1), "nearest": round(near_d, 1),
                    "chose": kind, "target": _name(tgt), "value": round(v, 4),
                    "options": [{"kind": j[2], "target": _name(j[3]), "value": round(j[1], 4),
                                 "judged": round(j[0], 4), "p": round(j[5], 2), "at": _where(tid, j[3], j[4])}
                                for j in judged]})
        if len(LOG) > LOG_MAX:
            del LOG[:len(LOG) - LOG_MAX]

    # --- do it ---------------------------------------------------------------------
    carrier._go_at_him = False
    if kind == "pass":
        mechanics.execute_pass(carrier, tgt, ball, now)
    elif kind == "through":
        mechanics.execute_pass(carrier, tgt, ball, now, through_plan=extra)
    elif kind == "cross":
        mechanics.execute_cross(carrier, tgt, ball, now, opponents)
    elif kind == "shoot":
        mechanics.execute_shot(carrier, ball, now, opponents)
    elif kind == "clear":
        ck, aim = tgt
        mechanics.execute_clearance(carrier, ball, now, ck, aim, pressed)
    elif kind == "carry":
        ta, tl = tgt
        speed = 1.0 if near_d > 4.0 else 0.85
        mechanics.execute_dribble(carrier, to_world(tid, ta, tl), ball, now, speed_mult=speed)
        carrier.last_decision_time = now
    elif kind == "take_on":
        ba, bl = extra
        mechanics.execute_dribble(carrier, to_world(tid, ba, bl), ball, now, speed_mult=1.0)
        carrier._go_at_him = True
        carrier.last_decision_time = now
    else:  # hold
        if near_o is not None and near_d < PRESSED_M + 1.0:
            away = carrier.pos - near_o.pos
            if away.length_squared() == 0:
                away = -goal_dir
            target = carrier.pos + away.normalize() * (1.5 * M_TO_PX)
            target.x = _clamp(target.x, 0, WIDTH)
            target.y = _clamp(target.y, 0, HEIGHT)
            mechanics.execute_dribble(carrier, target, ball, now, speed_mult=0.25)
            if carrier.state != "shield":
                carrier._shield_since = now
            carrier.state = "shield"
        else:
            # shift it a yard, head up, look again
            target = carrier.pos + goal_dir * (1.0 * M_TO_PX)
            mechanics.execute_dribble(carrier, target, ball, now, speed_mult=0.4)
        carrier.last_decision_time = now
    return tid


def _angle_diff(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


def _closing_share(ca, cl, ang, opps, near_d):
    """How much the nearest man is in the way of a carry this way (1: straight ahead of it .. 0: behind it)."""
    best = None
    for oa, ol in opps:
        d = math.hypot(oa - ca, ol - cl)
        if best is None or d < best[0]:
            best = (d, math.degrees(math.atan2(ol - cl, oa - ca)))
    if best is None:
        return 0.0
    return _clamp(1.0 - abs(_angle_diff(best[1], ang)) / 150.0, 0.2, 1.0)


def _facing_vec(carrier):
    f = getattr(carrier, "facing", None)
    if f is None or f.length_squared() == 0:
        f = carrier.vel if carrier.vel.length_squared() > 0 else Vector2(1 if carrier.team == 0 else -1, 0)
    return f.normalize()


def _angle_from_facing(carrier, mate):
    to = mate.pos - carrier.pos
    if to.length_squared() == 0:
        return 0.0
    return abs(_angle_diff(_facing_vec(carrier).angle_to(to.normalize()), 0.0))


def _across_box(carrier, teammates, opponents, opps, ca, cl, passing):
    """A low ball across the box from out wide, just in front of a team-mate there, for him to finish first time.
    Races the defenders like a ball in behind (those he's already got past have to turn).  [(value, mate, plan, p)]"""
    import gameplay.through_pass as tp
    from ai.team_shape import to_frame, to_world
    out = []
    if ca < ACROSS_FROM[0] or abs(cl) < ACROSS_FROM[1]:
        return out
    for m in teammates:
        ma, ml = to_frame(carrier.team, m.pos)
        if ma < ACROSS_TO[0] or abs(ml) > ACROSS_TO[1]:
            continue
        best = None
        for ahead in ACROSS_AHEAD:
            pa, pl = min(ma + ahead, PITCH_L - 4.0), ml
            t_top = BEHIND_TOP / BEHIND_ACCEL
            d_acc = 0.5 * BEHIND_ACCEL * t_top * t_top
            t_run = 0.1 + (math.sqrt(2 * ahead / BEHIND_ACCEL) if ahead <= d_acc else t_top + (ahead - d_acc) / BEHIND_TOP)
            point = to_world(carrier.team, pa, pl)
            d_m = (point - carrier.pos).length() / M_TO_PX
            if d_m < 6.0:
                continue
            t_b = max(t_run, 0.6)
            k_t = tp._K_GROUND ** t_b
            v_pass = min(tp.MAX_PASS_SPEED, d_m * tp._NEG_LN_K / (1.0 - k_t))
            loft = 0.0
            safety = _race_behind(carrier, point, v_pass, t_b, opponents, tp, runner=m)
            if safety is None:
                # (a man in the way of the low ball: whip it over him - a cross into the space in front of the runner)
                k_air = 0.995 ** 60
                v_pass = min(32.0, d_m * -math.log(k_air) / (1.0 - k_air ** t_b))
                safety = _race_behind(carrier, point, v_pass, t_b, opponents, tp, lofted=True, runner=m)
                loft = 0.4
            if safety is None:
                continue
            crossing = _stat(carrier, "Crossing")
            if loft:
                p = _clamp(0.25 + 0.3 * min(safety, 1.0) + 0.02 * (crossing - 10), 0.1, 0.75)
                chance = 0.5 * (xg(pa, pl) + xg(pa, pl, header=True)) * FIRST_TIME_FINISH   # (volley or header)
            else:
                p = _clamp(0.45 + 0.3 * min(safety, 1.0) + 0.012 * (passing - 10), 0.2, 0.9)
                chance = xg(pa, pl) * FIRST_TIME_FINISH
            v = p * chance - LOSS_WEIGHT * (1 - p) * xt_them(pa, pl)
            if best is None or v > best[0]:
                plan = {"point": point, "speed_px": v_pass * M_TO_PX, "lead_time": t_run, "safety": safety,
                        "value": v, "score": v, "runner": m, "elevation": loft}
                best = (v, m, plan, p)
        if best:
            out.append(best)
    return out


def _behind(carrier, mate):
    """Is this team-mate behind him (more than BEHIND_DEG round from the way he's facing)?"""
    to = mate.pos - carrier.pos
    if to.length_squared() == 0:
        return False
    return abs(_angle_diff(_facing_vec(carrier).angle_to(to.normalize()), 0.0)) > BEHIND_DEG


def _facing_deg(carrier):
    """Which way he faces in his team's frame (deg: 0 = towards their goal, + = towards his right)."""
    f = _facing_vec(carrier)
    if carrier.team == 1:
        f = -f
    return round(math.degrees(math.atan2(f.y, f.x)), 0)


def _where(tid, tgt, extra):
    """(a, l) the option takes the ball to, for the log."""
    from ai.team_shape import to_frame
    try:
        if isinstance(extra, dict) and "point" in extra:
            a, l = to_frame(tid, Vector2(extra["point"]))
        elif hasattr(tgt, "pos"):
            a, l = to_frame(tid, tgt.pos)
        elif isinstance(extra, tuple) and len(extra) == 2:
            a, l = extra
        elif isinstance(tgt, tuple) and len(tgt) == 2 and isinstance(tgt[0], (int, float)):
            a, l = tgt
        else:
            return None
        return [round(a, 1), round(l, 1)]
    except Exception:
        return None


def _name(t):
    if t is None:
        return ""
    if hasattr(t, "role"):
        return f"{getattr(t, 'role', '?')}"
    if isinstance(t, tuple) and len(t) == 2 and isinstance(t[0], (int, float)):
        return f"({t[0]:.0f}, {t[1]:.0f})"
    if isinstance(t, tuple):
        return str(t[0])
    return str(t)
