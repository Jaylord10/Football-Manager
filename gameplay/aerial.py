"""
gameplay/aerial.py
==================
Headers and aerial duels.

Before this nothing was ever headed.  A lofted ball (a cross, a long ball, a
clearance, a goal kick) simply dropped, and whoever was nearest collected it
once it was down - there were no headed goals, no flick-ons, no headed
clearances, and a defender couldn't cut out a cross until it was below a metre.

1. READING THE FLIGHT (update_movement, every frame)
   While a lofted ball is in the air, players work out where it will come
   down to head height and go for that spot: the man it's meant for, the
   nearest one or two from each side.  Anticipation decides how soon after
   it's struck they read it, pace who gets there.  A keeper comes for it if
   it's dropping into his six-yard box area and he can get there first.

2. THE CHALLENGE (resolve, every frame)
   When the ball comes down within reach of players - how high a man can get
   comes from his Jumping - they contest it.  Who wins: Jumping (height),
   Heading (connecting with it), Strength (the shove), Anticipation (timing),
   a running jump, and luck.  Sometimes nobody times it and it drops between
   them, or just flicks off a head.  A keeper uses his hands, so he reaches
   higher and usually wins it if he gets there.
   A ball nobody challenges for and low enough to chest down is just
   controlled, as before.

3. FOULS IN THE AIR
   A small chance in each challenge of a push, a climb or an arm - more with
   high Aggression.  Referees give few of them against defenders in their own
   box, so penalties from it are rare.

4. WHAT THE WINNER DOES WITH IT
   - an attacker near goal: a header at goal (slower than a kicked shot,
     placed by his Heading) - about 14% of Premier League goals are headers;
   - a defender in his own third: a headed clearance (ai/clearance.py picks
     where: up and away, out wide, or behind);
   - anywhere else: a headed pass to a team-mate - a flick-on into a runner,
     a knock-down to a man nearby - or just heading it on.
   - a keeper: catches it if he's clean (Handling, fewer bodies around him),
     otherwise punches it clear.
   Won under a challenge, the header is often scruffy: it goes roughly the
   right way at less pace.

All tuning numbers are in the TUNING block.
"""

import math
import random
from collections import Counter
from pygame.math import Vector2
from config.constants import M_TO_PX, WIDTH, HEIGHT, GOAL_WIDTH, GRAVITY

# ---------------------------------------------------------------------------
# TUNING  (metres, m/s, seconds, degrees; stats 1-20)
# ---------------------------------------------------------------------------
# Reading the flight
CONTACT_Z      = 2.2           # m: the height he aims to meet it at, on its way down
LOFTED_MIN     = 1.6           # m: a ball that won't get higher than this isn't an aerial ball
READ_DELAY     = (0.45, 0.15)  # s after it's struck before he reads it (worst, best Anticipation)
SLACK          = 0.8           # s: he goes for it if he can get there this soon after it does
GO_RANGE       = 28.0          # m: further than this he doesn't bother
PER_TEAM       = 2             # men per side who go for it (plus the man it's meant for)...
PER_TEAM_BOX   = 3             # ...defenders when it's coming down in their own box
GK_CLAIM_DEPTH = 9.0           # m from his goal line...
GK_CLAIM_WIDTH = 11.0          # ...and this far either side of the centre: he can come for it
GK_CLAIM_SLACK = 0.25          # s: only if he gets there (nearly) as soon as it does

# The challenge
EARLIEST       = 0.35          # s after it's struck before anyone can head it
LOW_Z          = 1.2           # m: below this it's a chest / foot ball (normal control)
CHEST_MAX      = 1.7           # m: unchallenged and below this, he just controls it
HEAD_STANDING  = 2.0           # m: highest he can head it without jumping...
JUMP           = (0.30, 0.025) # ...plus a jump of base + per Jumping point (13 -> 0.63 m)
GK_HANDS       = 2.35          # m: a keeper's standing reach with his hands (+ his jump)
REACH_R        = 1.5           # m: horizontally, how far from him he can meet it (attacking it, leaning in)
GK_REACH_R     = 1.6
DEF_BOX_REACH_R = 2.0          # m: a defender in his own box, set and facing it, attacks the ball across his zone
CHALLENGE_R    = 2.5           # m: an opponent this close is challenging him for it
W_JUMP, W_HEAD, W_STR, W_ANT = 0.35, 0.30, 0.20, 0.15
RUN_UP         = 1.5           # bonus for a running jump (scaled by his speed towards it, up to 6 m/s)
DIST_PENALTY   = 2.0           # x (distance / reach): at the edge of his reach he's at a disadvantage
NOISE          = 3.0           # sd of the luck in a challenge
GK_BONUS       = 6.0           # a keeper can use his hands
DEF_BOX_BONUS  = 3.0           # a defender in his own box, facing the ball, attacking it - the
                               # attacker has to get across him and redirect it
NOBODY         = 0.10          # chance nobody times it right in a challenge...
FLICK_OFF      = 0.35          # ...and if so, the chance it flicks off a head on the way
CLEAN_MARGIN   = 1.5           # won by this much (or unchallenged): a clean header
SCRUFFY_TURN   = 55.0          # degrees: a scruffy header goes up to this far off where he meant
SCRUFFY_SPEED  = 0.6

# Fouls
FOUL           = 0.07          # chance of a foul in a challenge...
FOUL_PER_AGGRESSION = 0.005    # ...+ per point of the challengers' average Aggression over 10
FOUL_DEF_BOX   = 0.3           # x for a defender in his own box (referees rarely give them)
FOUL_YELLOW    = 0.10

# Headers at goal
SHOOT_CHANCE   = ((8.0, 0.90), (11.0, 0.75), (14.0, 0.45))   # (m from goal, chance he goes for goal)
SHOT_SPEED     = (10.0, 0.35)  # m/s: base + per Heading point (13 -> 14.5), + a little for a run-up
SHOT_ANGLE_SD  = (4.0, 0.5)    # degrees: base + per Heading point below 20
SHOT_HEIGHT    = (0.10, 1.80)  # m at the goal line (aim)
SHOT_HEIGHT_SD = 0.35
AIM_INSIDE     = (1.2, 0.5)    # m inside the post he aims (worst, best Heading)

# Headed clearances / passes
CLEAR_ZONE     = 36.0          # m from his own goal: a defender heads it clear...
CLEAR_PRESSED  = 4.0           # ...if an opponent is this close (or he's in his box)
CLEAR_SPEED    = (12.0, 0.25, 0.15)  # m/s: base + per Heading + per Strength point
CLEAR_LIFT     = (5.0, 9.0)    # m/s up
CLEAR_ANGLE_SD = (10.0, 0.6)   # degrees: base + per Heading point below 20
PASS_RANGE     = 25.0          # m: team-mates he can head it to
PASS_ANGLE_SD  = (6.0, 0.5)
PASS_LIFT      = (1.5, 4.0)
ON_SPEED       = (10.0, 14.0)  # m/s: just heading it on

# Keeper
GK_CATCH       = 0.80          # chance he holds it...
GK_CATCH_PER_POINT = 0.03      # ...+ per Handling point over 10
GK_CROWD       = 0.15          # ...- per opponent within 1.5 m of him
GK_PUNCH_SPEED = (14.0, 20.0)
GK_PUNCH_TURN  = 40.0

STATS = Counter()              # read by sim.py

_K_AIR = 0.995                 # per frame (Ball.update)
_K_GROUND = 0.992


def _stat(p, name):
    v = p.attributes.get(name, 10)
    if v > 25:
        v /= 5.0
    return max(1.0, min(20.0, v))


def _lerp(lo_hi, q):
    lo, hi = lo_hi
    return lo + (hi - lo) * q


def _q(v):
    return (v - 1.0) / 19.0


def _frame(team, v):
    from ai.team_shape import to_frame
    return to_frame(team, v)


def _active(p):
    return getattr(p, "is_active", True)


def reach_z(p):
    """m: the highest he can get to it."""
    base = GK_HANDS if p.role == "GK" else HEAD_STANDING
    return base + JUMP[0] + JUMP[1] * _stat(p, "Jumping")


# ---------------------------------------------------------------------------
# 1. Reading the flight
# ---------------------------------------------------------------------------
def _predict(ball):
    """Where (px) and when (s from now) it comes down to CONTACT_Z - or None for a ground ball."""
    cache = getattr(ball, "_aerial_pred", None)
    if cache is not None and cache[0] == getattr(ball, "last_kick_time", None):
        point, t_abs = cache[1], cache[2]
        if point is None:
            return None
        import core.clock as clock
        return point, t_abs - clock.now()
    dt = 1.0 / 60.0
    pos, vel, z, vz = Vector2(ball.pos), Vector2(ball.vel), ball.z, ball.vz
    top = z
    for i in range(1, 240):
        pos += vel * dt
        vel *= _K_AIR if z > 0.1 else _K_GROUND
        z += vz * dt
        vz -= GRAVITY * dt
        top = max(top, z)
        if vz < 0 and z <= CONTACT_Z * M_TO_PX:
            if top < LOFTED_MIN * M_TO_PX:
                result = None
            else:
                result = (Vector2(pos), i * dt)
            break
        if z < 0:
            result = None
            break
    else:
        result = None
    import core.clock as clock
    if result is None:
        ball._aerial_pred = (getattr(ball, "last_kick_time", None), None, None)
        return None
    ball._aerial_pred = (getattr(ball, "last_kick_time", None), result[0], clock.now() + result[1])
    return result


def _is_aerial(ball):
    if ball.owner is not None or ball.is_dead:
        return False
    from gameplay.ricochet import is_live_shot
    if is_live_shot(ball):
        return False
    return getattr(ball, "_aerial_done", None) != getattr(ball, "last_kick_time", None)


def update_movement(team0, team1, ball, now):
    """Send the right men to where a lofted ball is coming down."""
    if not _is_aerial(ball):
        return
    pr = getattr(ball, "_aerial_pred", None)
    if pr is not None and pr[0] == getattr(ball, "last_kick_time", None) and pr[1] is None:
        return                                       # already worked out: not an aerial ball
    pred = _predict(ball)
    if pred is None:
        return
    spot, t = pred
    if t < 0:
        return
    since = now - getattr(ball, "last_kick_time", now)
    import ai.intercepts as intercepts
    aimed = getattr(ball, "intended_target", None)
    from ai.box_marking import marker_of
    for team in (team0, team1):
        cands = []
        keeper = None
        # The man marking the one it's meant for goes with him, and reads it as quickly as he does
        tracker = marker_of(aimed, team, now) if aimed is not None and aimed not in team else None
        for p in team:
            if not _active(p) or p.has_ball:
                continue
            if p is not aimed and p is not tracker and since < _lerp(READ_DELAY, _q(_stat(p, "Anticipation"))):
                continue                              # hasn't read it yet (the man it's for knows it's coming)
            d = (p.pos - spot).length() / M_TO_PX
            if p.role == "GK":
                a, l = _frame(p.team, spot)
                if a < GK_CLAIM_DEPTH and abs(l) < GK_CLAIM_WIDTH:
                    if intercepts._time_to(p, spot) <= t + GK_CLAIM_SLACK:
                        keeper = p
                continue
            if d > GO_RANGE:
                continue
            tt = intercepts._time_to(p, spot)
            if tt <= t + SLACK or p is aimed or p is tracker:
                cands.append((0.0 if (p is aimed or p is tracker) else tt, p))
        cands.sort(key=lambda c: c[0])
        sa, sl = _frame(team[0].team, spot) if team else (50.0, 0.0)
        n_go = PER_TEAM_BOX if (sa < 18.0 and abs(sl) < 21.0) else PER_TEAM
        chosen = [p for _, p in cands[:n_go + (1 if (aimed in team or tracker is not None) else 0)]]
        if keeper is not None:
            chosen.append(keeper)
        for p in chosen:
            p.target = Vector2(spot)
            p.state = "chase"
            p.pos_reason = "go for it in the air" if p.role != "GK" else "come for the cross"
            p._aerial_for = getattr(ball, "last_kick_time", None)


# ---------------------------------------------------------------------------
# 2. The challenge
# ---------------------------------------------------------------------------
def _contenders(team0, team1, ball, now):
    out = []
    for p in team0 + team1:
        if not _active(p) or now < getattr(p, "_no_touch_until", -1.0):
            continue
        if now < getattr(p, "stagger_until", 0.0):
            continue
        r = (GK_REACH_R if p.role == "GK" else REACH_R)
        a, l = _frame(p.team, p.pos)
        in_own_box = a < 16.5 and abs(l) < 20.16
        if p.role == "GK":
            if a > 18.0 or abs(l) > 21.0:
                continue                              # keepers only use their hands in their box
        elif in_own_box:
            r = DEF_BOX_REACH_R
        d = (p.pos - ball.pos).length() / M_TO_PX
        if d <= r and ball.z <= reach_z(p) * M_TO_PX:
            out.append((p, d / r))
    return out


def _quality(p, edge, ball):
    to_ball = ball.pos - p.pos
    run = 0.0
    if to_ball.length_squared() > 1e-6:
        run = max(0.0, min(6.0, p.vel.dot(to_ball.normalize()) / M_TO_PX)) / 6.0
    q = (W_JUMP * _stat(p, "Jumping") + W_HEAD * _stat(p, "Heading")
         + W_STR * _stat(p, "Strength") + W_ANT * _stat(p, "Anticipation")
         + RUN_UP * run - DIST_PENALTY * edge + random.gauss(0.0, NOISE))
    if p.role == "GK":
        q += GK_BONUS
    else:
        a, l = _frame(p.team, p.pos)
        if a < 16.5 and abs(l) < 20.16:
            q += DEF_BOX_BONUS
    return q


def resolve(team0, team1, ball, now, ai_system):
    """
    Called every frame after the ball moves, before the keepers and the
    normal pick-up.  Returns a foul dict (like a tackle foul) or None.
    """
    if not _is_aerial(ball):
        return None
    if now - getattr(ball, "last_kick_time", now) < EARLIEST:
        return None
    if ball.z < LOW_Z * M_TO_PX:
        return None
    cons = _contenders(team0, team1, ball, now)
    if not cons:
        return None
    key = getattr(ball, "last_kick_time", None)
    teams = {p.team for p, _ in cons}
    # Is anyone being challenged?  (an opponent at him, even if not quite in reach)
    challenged = len(teams) > 1
    if not challenged:
        for p, _ in cons:
            opps = team1 if p.team == 0 else team0
            if any(_active(o) and (o.pos - p.pos).length() < CHALLENGE_R * M_TO_PX for o in opps):
                challenged = True
                break
    if not challenged and not any(p.role == "GK" for p, _ in cons):
        # Nobody near him.  In front of goal he has a free header at it;
        # anywhere else he takes it down and controls it (the normal pick-up).
        for p, _ in cons:
            roll = getattr(p, "_free_header", None)
            if roll is None or roll[0] != key:
                roll = (key, random.random())
                p._free_header = roll
            if _free_header_at_goal(p, ball, roll[1]):
                ball._aerial_done = key
                STATS["free_headers"] += 1
                STATS["won_att" if p.team == getattr(ball, "last_kick_team", p.team) else "won_def"] += 1
                STATS["won_by_" + _role_group(p)] += 1
                opponents = team1 if p.team == 0 else team0
                header_shot(p, ball, now, opponents, True)
                return None
        return None

    ball._aerial_done = key
    STATS["duels" if challenged else "gk_alone"] += 1

    scored = sorted(((_quality(p, e, ball), p) for p, e in cons), key=lambda s: -s[0])
    best_q, winner = scored[0]
    rivals = [s for s in scored[1:] if s[1].team != winner.team]
    margin = best_q - rivals[0][0] if rivals else 99.0

    foul = None
    if challenged:
        # A foul in the challenge?
        everyone = [p for p, _ in cons]
        opps_near = [o for o in (team1 if winner.team == 0 else team0)
                     if _active(o) and o.role != "GK" and (o.pos - winner.pos).length() < CHALLENGE_R * M_TO_PX]
        pool = [p for p in everyone if p.team != winner.team and p.role != "GK"] or opps_near
        if pool:
            fouler = random.choice(pool)
            aggr = sum(_stat(p, "Aggression") for p in everyone) / len(everyone)
            p_foul = FOUL + FOUL_PER_AGGRESSION * (aggr - 10.0)
            fa, fl = _frame(fouler.team, fouler.pos)
            if fa < 16.5 and abs(fl) < 20.16:
                p_foul *= FOUL_DEF_BOX
            if random.random() < p_foul:
                STATS["fouls"] += 1
                card = "yellow" if random.random() < FOUL_YELLOW else "foul"
                fouler.last_foul_time = now
                return {"fouler": fouler, "fouled": winner, "pos": Vector2(fouler.pos),
                        "card_type": card, "attacking_team": winner.team}
        # Nobody times it right?
        if random.random() < NOBODY:
            STATS["nobody"] += 1
            if random.random() < FLICK_OFF:
                flicker = random.choice(everyone)
                ball.vel = ball.vel.rotate(random.uniform(-25.0, 25.0)) * 0.85
                ball._aerial_pred = None
                ball.last_toucher = flicker
                ball.last_toucher_team = flicker.team
            return None

    STATS["won_att" if winner.team == getattr(ball, "last_kick_team", winner.team) else "won_def"] += 1
    STATS["won_by_" + _role_group(winner)] += 1
    clean = (not challenged) or margin >= CLEAN_MARGIN
    opponents = team1 if winner.team == 0 else team0
    teammates = team0 if winner.team == 0 else team1
    if winner.role == "GK":
        _keeper(winner, ball, now, opponents, ai_system)
    else:
        _header(winner, ball, now, teammates, opponents, clean, challenged)
    return foul


def _shoot_chance(p, ball):
    a, l = _frame(p.team, ball.pos)
    in_front = (110.0 - a) > 0.5 and abs(l) <= 0.9 * (110.0 - a) + 3.0
    if not in_front:
        return 0.0
    goal = Vector2(WIDTH, HEIGHT / 2) if p.team == 0 else Vector2(0.0, HEIGHT / 2)
    d_goal = (goal - ball.pos).length() / M_TO_PX
    for dist, chance in SHOOT_CHANCE:
        if d_goal <= dist:
            return chance
    return 0.0


def _free_header_at_goal(p, ball, roll):
    return roll < _shoot_chance(p, ball)


def _role_group(p):
    r = p.role
    if r == "GK":
        return "gk"
    if r in ("LCB", "RCB", "CB", "LB", "RB"):
        return "def"
    if r.startswith("ST"):
        return "fwd"
    return "mid"


# ---------------------------------------------------------------------------
# 4. What he does with it
# ---------------------------------------------------------------------------
def _keeper(gk, ball, now, opponents, ai_system):
    crowd = sum(1 for o in opponents if _active(o) and (o.pos - gk.pos).length() < 1.5 * M_TO_PX)
    p_catch = GK_CATCH + GK_CATCH_PER_POINT * (_stat(gk, "Handling") - 10.0) - GK_CROWD * crowd
    if random.random() < max(0.15, min(0.92, p_catch)):
        from gameplay.goalkeeping import _claim
        _claim(gk, ball, now, ai_system)
        STATS["gk_catch"] += 1
        return
    away = Vector2(1.0, 0.0) if gk.team == 0 else Vector2(-1.0, 0.0)
    direction = away.rotate(random.uniform(-GK_PUNCH_TURN, GK_PUNCH_TURN))
    _strike(gk, ball, now, direction * random.uniform(*GK_PUNCH_SPEED), random.uniform(3.0, 7.0))
    ball.last_header = {"kind": "punch", "player": gk, "time": now}
    STATS["gk_punch"] += 1


def _strike(p, ball, now, vel_ms, vz_ms, target=None):
    z = ball.z
    ball.kick(vel_ms * M_TO_PX, kicker=p)
    ball.z = z
    ball.vz = vz_ms * M_TO_PX
    ball.last_kick_time = now
    ball.intended_target = target
    ball.pass_start_pos = Vector2(p.pos)
    p._next_run_touch = now + 0.3
    p._no_touch_until = now + 0.25
    p.has_ball = False


def _header(p, ball, now, teammates, opponents, clean, challenged):
    a, l = _frame(p.team, ball.pos)
    # At goal?
    p_shoot = _shoot_chance(p, ball)
    if not clean:
        p_shoot *= 0.7
    if random.random() < p_shoot:
        return header_shot(p, ball, now, opponents, clean)
    # A defender in his own third heads it clear
    near = min(((o.pos - p.pos).length() / M_TO_PX for o in opponents if _active(o) and o.role != "GK"),
               default=99.0)
    in_own_box = a < 16.5 and abs(l) < 20.16
    if a < CLEAR_ZONE and (near < CLEAR_PRESSED or in_own_box):
        return _headed_clearance(p, ball, now, teammates, opponents, clean)
    return _headed_pass(p, ball, now, teammates, opponents, clean)


def header_shot(p, ball, now, opponents, clean=True):
    goal_x = float(WIDTH) if p.team == 0 else 0.0
    post_top, post_bot = HEIGHT / 2 - GOAL_WIDTH / 2, HEIGHT / 2 + GOAL_WIDTH / 2
    heading = _stat(p, "Heading")
    q = _q(heading)
    keeper = next((o for o in opponents if o.role == "GK" and _active(o)), None)
    if keeper is not None:
        side = 1 if (post_bot - keeper.pos.y) > (keeper.pos.y - post_top) else -1
        if random.random() > 0.6 + 0.25 * q:
            side = -side
    else:
        side = random.choice((-1, 1))
    inside = _lerp(AIM_INSIDE, q) * M_TO_PX
    aim = Vector2(goal_x, (post_bot - inside) if side > 0 else (post_top + inside))
    to_aim = aim - ball.pos
    if to_aim.length_squared() < 1.0:
        to_aim = Vector2(1.0 if p.team == 0 else -1.0, 0.0)
    sd = SHOT_ANGLE_SD[0] + SHOT_ANGLE_SD[1] * (20.0 - heading)
    if not clean:
        sd *= 1.6
    direction = to_aim.normalize().rotate(random.gauss(0.0, sd))
    run = max(0.0, min(6.0, p.vel.length() / M_TO_PX))
    speed = (SHOT_SPEED[0] + SHOT_SPEED[1] * heading + 0.3 * run) * (0.8 if not clean else 1.0)
    dist_m = to_aim.length() / M_TO_PX
    t = max(0.1, dist_m / speed)
    h = max(0.0, random.uniform(*SHOT_HEIGHT) + random.gauss(0.0, SHOT_HEIGHT_SD))
    vz = (h - ball.z / M_TO_PX + 0.5 * 9.8 * t * t) / t
    _strike(p, ball, now, direction * speed, vz)
    p.state = "shoot"
    ball.shot_info = {"time": now, "type": "header", "shooter": p, "speed_ms": speed}
    ball.last_owner = p
    ball.last_header = {"kind": "shot", "player": p, "time": now}
    STATS["at_goal"] += 1
    return p.team


def _headed_clearance(p, ball, now, teammates, opponents, clean):
    import ai.clearance as clearance
    kind, aim = clearance.plan(p, teammates, opponents, True)
    to_aim = aim - ball.pos
    if to_aim.length_squared() < 1.0:
        to_aim = Vector2(1.0 if p.team == 0 else -1.0, 0.0)
    sd = CLEAR_ANGLE_SD[0] + CLEAR_ANGLE_SD[1] * (20.0 - _stat(p, "Heading"))
    direction = to_aim.normalize().rotate(random.gauss(0.0, sd))
    speed = CLEAR_SPEED[0] + CLEAR_SPEED[1] * _stat(p, "Heading") + CLEAR_SPEED[2] * _stat(p, "Strength")
    lift = random.uniform(*CLEAR_LIFT)
    if kind != "away":
        speed, lift = min(speed, 13.0), lift * 0.5
    if not clean:
        direction = direction.rotate(random.uniform(-SCRUFFY_TURN, SCRUFFY_TURN))
        speed *= SCRUFFY_SPEED
    _strike(p, ball, now, direction * speed, lift)
    ball.last_clearance = {"team": p.team, "time": now, "kind": kind, "player": p,
                           "sliced": not clean, "first_time": True, "headed": True}
    ball.last_header = {"kind": "clearance", "player": p, "time": now}
    clearance.STATS[kind] += 1
    clearance.STATS["team%d" % p.team] += 1
    clearance.STATS["headed"] += 1
    STATS["clearance"] += 1
    return p.team


def _headed_pass(p, ball, now, teammates, opponents, clean):
    fwd = Vector2(1.0, 0.0) if p.team == 0 else Vector2(-1.0, 0.0)
    best, best_s = None, -1e9
    for m in teammates:
        if m is p or m.role == "GK" or not _active(m):
            continue
        rel = m.pos - ball.pos
        d = rel.length() / M_TO_PX
        if d < 3.0 or d > PASS_RANGE:
            continue
        if rel.normalize().dot(fwd) < -0.3:
            continue
        space = min(((o.pos - m.pos).length() / M_TO_PX for o in opponents if _active(o)), default=20.0)
        s = min(space, 8.0) + 0.3 * rel.dot(fwd) / M_TO_PX - 0.1 * d
        if m.state == "chase" or getattr(m, "pos_reason", "").startswith("run"):
            s += 2.0                                  # a runner: flick it on into his path
        if s > best_s:
            best, best_s = m, s
    if best is not None:
        lead = best.vel * 0.5
        to_t = (best.pos + lead) - ball.pos
        d = to_t.length() / M_TO_PX
        sd = PASS_ANGLE_SD[0] + PASS_ANGLE_SD[1] * (20.0 - _stat(p, "Heading"))
        direction = to_t.normalize().rotate(random.gauss(0.0, sd))
        speed = max(8.0, min(18.0, 6.0 + 0.6 * d))
        target = best
        STATS["pass"] += 1
        kind = "flick-on" if (best.pos - ball.pos).dot(fwd) > 5.0 * M_TO_PX else "knock-down"
    else:
        direction = fwd.rotate(random.uniform(-30.0, 30.0))
        speed = random.uniform(*ON_SPEED)
        target = None
        STATS["on"] += 1
        kind = "on"
    if not clean:
        direction = direction.rotate(random.uniform(-SCRUFFY_TURN, SCRUFFY_TURN))
        speed *= SCRUFFY_SPEED
        target = None
    _strike(p, ball, now, direction * speed, random.uniform(*PASS_LIFT), target)
    ball.last_header = {"kind": kind, "player": p, "time": now}
    return p.team
