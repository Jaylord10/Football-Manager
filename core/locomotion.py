"""
core/locomotion.py
==================
How outfield players physically move: speeding up, slowing down, turning.

Before: players accelerated at ~49 m/s^2 (real footballers manage 3-6),
could brake at 200 m/s^2, turned at 400 deg/s at full sprint, and jogged
everywhere at ~6 m/s.  That's why movement looked robotic: instant starts,
instant stops, instant about-turns.

Now each frame:
  1. Decide how fast the player WANTS to go (sprint / run / jog / walk).
     Chasing, running in behind and pressing are flat out (pressing pace
     depends on Work Rate).  Getting into position ("support" / "defend")
     depends on his URGENCY from ai/urgency.py - a beaten defender sprints
     back, a centre-back in a quiet spell walks - see URGENCY_PACE.
  2. Ease off when approaching the target so he arrives smoothly.
  3. Change velocity within physical limits:
       - forward acceleration (Acceleration stat, weaker near top speed)
       - braking (Agility stat)
       - sideways / turning acceleration (Agility stat) - so a sprinting
         player has to run a wide arc, while a slow player can turn sharply.
     ...scaled by EFFORT (see effort()): those limits are what he can do
     flat out.  A player jogging into position doesn't explode off the mark
     or slam on the brakes - he eases into it, and only uses his full
     acceleration when it matters (chasing, pressing, a run in behind, an
     urgent recovery).

All tuning numbers are in the TUNING block (metres, seconds, stats 1-20).
"""

import math
from pygame.math import Vector2
from config.constants import M_TO_PX, WIDTH, HEIGHT


# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
TOP_SPEED_RANGE   = (7.5, 10.5)  # m/s for Top Speed 1 -> 20

ACCEL_BASE        = 3.5          # m/s^2 forward acceleration from a standstill...
ACCEL_PER_POINT   = 0.20         # ...plus this per Acceleration point (13 -> 5.9)
ACCEL_FADE        = 0.60         # at top speed only (1 - 0.6) = 40% of it is left
BRAKE_BASE        = 6.5          # m/s^2 braking...
BRAKE_PER_POINT   = 0.12         # ...plus per Agility point (13 -> 8.1)
TURN_BASE         = 4.5          # m/s^2 sideways acceleration...
TURN_PER_POINT    = 0.22         # ...plus per Agility point (13 -> 7.4, i.e. ~53 deg/s at 8 m/s)
DRIBBLE_ACCEL     = 0.85         # acceleration multiplier with the ball at feet

BALL_LINE_MARGIN  = 1.6          # m: a player on the ball keeps this far inside the lines
ARRIVE_DECEL      = 3.5          # m/s^2 comfortable slowing when arriving at a target
STOP_RADIUS       = 0.25         # m: close enough - stand still

# Intent speeds, as a fraction of the player's top speed
SPRINT_STATES = {"chase": 1.00, "run": 1.00, "intercept": 1.00, "tackle": 0.9}
JOG_STATES    = {"support": 0.58, "defend": 0.66, "idle": 0.50, "guard": 0.50}
JOG_MIN_SPEED = 1.3              # m/s: walking pace when the target is very close
JOG_PER_M     = 0.22             # m/s of extra pace per metre of distance to the target
HOLD_SPEED    = 0.10             # "hold": planted, barely creeping
# Dead-ball time: walking into position, celebrating a goal
WALK_BASE     = 1.4              # m/s "walk"...
WALK_PER_M    = 0.04             # ...a bit brisker the further he has to go...
WALK_MAX      = 2.6              # ...up to this
CELEBRATE     = 0.75             # "celebrate": share of top speed running to the scorer

# Effort: how much of his physical limits he uses (0-1).  Sprinting states
# use everything; repositioning uses more the more urgent it is.
EFFORT_STATES = {"chase": 1.0, "run": 1.0, "press": 1.0, "intercept": 1.0, "tackle": 1.0,
                 "dribble": 0.8, "shield": 0.6, "hold": 0.25, "walk": 0.2, "celebrate": 0.8}
EFFORT_DEFAULT = 0.4
EFFORT_URGENCY = (0.15, 1.0)    # support / defend: effort at urgency 0 and 1
EFFORT_STAGGER = 0.5            # a wrong-footed defender losing his momentum
ACCEL_MIN_SHARE = 0.25          # at effort 0 he uses this share of his acceleration...
BRAKE_MIN_SHARE = 0.35          # ...of his braking...
TURN_MIN_SHARE  = 0.50          # ...and of his turning
ARRIVE_BRAKE_SHARE = 0.85       # plans his arrival using this share of the braking he's using

# Running onto a pass (ai/movement.py marks the receiver).  He isn't easing
# into a parking space: he brakes late and hard (real players can pull up from
# a sprint at ~8-10 m/s^2), and if the ball is rolling the same way he's
# running he doesn't stop at all - he arrives matching its pace, to take it in
# his stride.
RECEIVE_BRAKE_SHARE = 0.80      # share of his full braking used when meeting the ball
RECEIVE_MATCH_SHARE = 0.90      # arrive at this share of the ball's speed along his run
RECEIVE_FLAG_TIME   = 0.10      # s: how long ai/movement.py's "receiving" mark lasts

# Pressing (ai/pressing.py): pace depends on Work Rate
PRESS_BASE    = 0.82             # fraction of top speed at Work Rate 0...
PRESS_PER_WR  = 0.009            # ...plus this per point (10 -> 0.91, 20 -> 1.0)

# Urgency (ai/urgency.py) -> pace for players moving into position ("support" /
# "defend").  (urgency, m/s) points; None = his top speed.  In between it's linear.
URGENCY_PACE  = [(0.00, 1.3), (0.25, 2.8), (0.50, 4.3), (0.75, 6.0), (0.90, 7.5), (1.00, None)]
SHAPE_FLOOR_BASE = 1.3           # m/s: however calm, he doesn't dawdle when away from his spot:
SHAPE_FLOOR_PER_M = 0.17         # ...at least this + this per metre away...
SHAPE_FLOOR_MAX  = 3.5           # ...up to a good jog
DEFAULT_SPEED = 0.70             # any other state


from core.stats import stat20 as _stat    # (cached: attributes never change during a match)
import core.clock as _clock
import core.world as _world
import core.fatigue as _fatigue
import core.orientation as _orientation

CONTACT_XS = None    # (all_players, their current x) - set by the match engine while it moves everyone


def top_speed_ms(player):
    # Asked for over a million times a match: remembered until his sprint
    # energy or stamina changes (the only things it depends on besides Top Speed)
    e = getattr(player, "energy", 1.0)
    s = getattr(player, "stamina", 1.0)
    c = player.__dict__.get("_ts_cache")
    if c is not None and c[0] == e and c[1] == s:
        return c[2]
    ts = _stat(player, "Top Speed")
    lo, hi = TOP_SPEED_RANGE
    speed = lo + (ts - 1) / 19.0 * (hi - lo)
    v = speed * _fatigue.speed_factor(player)     # tired / gassed players are slower
    player.__dict__["_ts_cache"] = (e, s, v)
    return v


def intent_speed_ms(player, dist_m):
    """How fast the player wants to move right now (m/s)."""
    top = top_speed_ms(player)
    state = player.state
    if state in SPRINT_STATES:
        return top * SPRINT_STATES[state]
    if state == "dribble":
        dribbling = _stat(player, "Dribbling")
        efficiency = 0.80 + (dribbling / 20.0) * 0.15
        return top * efficiency * getattr(player, "_dribble_speed_mult", 1.0)
    if state == "shield":
        return top * getattr(player, "_dribble_speed_mult", 0.25)
    if state == "hold":
        return top * HOLD_SPEED
    if state == "press":
        return top * min(1.0, PRESS_BASE + PRESS_PER_WR * _stat(player, "Work Rate"))
    if state == "walk":
        return min(top, WALK_BASE + WALK_PER_M * dist_m, WALK_MAX)
    if state == "celebrate":
        return top * CELEBRATE
    urgency = getattr(player, "urgency", None)
    if urgency is not None and state in ("support", "defend"):
        return min(top, max(urgency_pace(urgency, top),
                            min(SHAPE_FLOOR_MAX, SHAPE_FLOOR_BASE + SHAPE_FLOOR_PER_M * dist_m)))
    if state in JOG_STATES:
        # Walk when nearly there, jog to reposition, run if far out of position
        return min(top * JOG_STATES[state], JOG_MIN_SPEED + JOG_PER_M * dist_m)
    return top * DEFAULT_SPEED


def urgency_pace(u, top):
    """m/s for an urgency between 0 and 1 (see URGENCY_PACE)."""
    pts = URGENCY_PACE
    x0, v0 = pts[0]
    v0 = top if v0 is None else min(v0, top)
    if u <= x0:
        return v0
    for x1, v1 in pts[1:]:
        v1 = top if v1 is None else min(v1, top)
        if u <= x1:
            return v0 + (v1 - v0) * (u - x0) / (x1 - x0)
        x0, v0 = x1, v1
    return v0


def effort(player, now):
    """0-1: how hard he's working his body right now."""
    if now < getattr(player, "stagger_until", 0.0):
        return EFFORT_STAGGER
    if now < getattr(player, "_burst_until", 0.0):
        return 1.0
    state = player.state
    if state in ("support", "defend"):
        u = getattr(player, "urgency", None)
        if u is not None:
            lo, hi = EFFORT_URGENCY
            return lo + (hi - lo) * u
    return EFFORT_STATES.get(state, EFFORT_DEFAULT)


def step(player, dt, all_players=None):
    """Move one outfield player for one frame."""
    # (Worked in plain x / y numbers rather than Vector2s - exactly the same
    # arithmetic in the same order, just without building lots of small
    # vector objects: pygame's v / k is v * (1 / k), so that's copied too.)
    sqrt = math.sqrt
    pos = player.pos
    tgt = player.target
    tx = tgt.x - pos.x
    ty = tgt.y - pos.y
    tt_len = sqrt(tx * tx + ty * ty)
    dist_m = tt_len / M_TO_PX

    now = _clock._now
    e = effort(player, now)
    player.effort = e
    agility = _stat(player, "Agility")
    brake = (BRAKE_BASE + BRAKE_PER_POINT * agility) * M_TO_PX * (BRAKE_MIN_SHARE + (1 - BRAKE_MIN_SHARE) * e)
    arrive_decel = min(ARRIVE_DECEL, ARRIVE_BRAKE_SHARE * brake / M_TO_PX)
    staggered = now < getattr(player, "stagger_until", 0.0)
    top = top_speed_ms(player)        # (energy / stamina don't change until fatigue.update after this)

    # --- 1+2. Desired velocity: intent speed, eased off near the target ---
    if staggered:
        # Wrong-footed / on the floor after losing a duel (gameplay/duels.py)
        dx = dy = 0.0
    elif dist_m > STOP_RADIUS:
        want = intent_speed_ms(player, dist_m)
        end_speed = 0.0
        if player.state == "chase" and now - getattr(player, "_receiving_at", -9.0) < RECEIVE_FLAG_TIME:
            full_brake = (BRAKE_BASE + BRAKE_PER_POINT * agility)
            arrive_decel = RECEIVE_BRAKE_SHARE * full_brake
            b = _world.ball
            if b is not None:
                bv = b.vel
                along = (bv.x * tx + bv.y * ty) / (tt_len * M_TO_PX)   # m/s, + = rolling his way
                end_speed = max(0.0, RECEIVE_MATCH_SHARE * along)
        arrive = sqrt(end_speed * end_speed + 2.0 * arrive_decel * max(0.0, dist_m - STOP_RADIUS))
        want = min(want, arrive)
        k = want * M_TO_PX
        dx = (tx / tt_len) * k
        dy = (ty / tt_len) * k
    else:
        dx = dy = 0.0

    # --- 2b. With the ball: don't carry it out of play ---
    # Treat the lines (minus a margin) like a wall: no running towards a line
    # faster than he could stop before reaching it.
    has_ball = player.has_ball
    if has_ball:
        d = _respect_lines(player, Vector2(dx, dy))
        dx, dy = d.x, d.y

    # --- 2c. Body orientation: watching the ball he can only shuffle or
    # backpedal; to go faster he turns and runs (core/orientation.py) ---
    face_target = None
    if not has_ball and not staggered:
        d, face_target = _orientation.plan(player, Vector2(dx, dy), top, _world.ball)
        dx, dy = d.x, d.y

    # --- 3. Physical limits on changing velocity ---
    v = player.vel
    vx, vy = v.x, v.y
    speed = sqrt(vx * vx + vy * vy)
    top_px = top * M_TO_PX
    accel = (ACCEL_BASE + ACCEL_PER_POINT * _stat(player, "Acceleration")) * M_TO_PX
    if has_ball and now >= getattr(player, "_burst_until", 0.0):
        accel *= DRIBBLE_ACCEL          # (not while bursting past a beaten defender)
    accel *= max(0.0, 1.0 - ACCEL_FADE * min(1.0, speed / max(top_px, 1.0)))
    accel *= _fatigue.accel_factor(player)
    accel *= ACCEL_MIN_SHARE + (1 - ACCEL_MIN_SHARE) * e
    lateral = (TURN_BASE + TURN_PER_POINT * agility) * M_TO_PX * (TURN_MIN_SHARE + (1 - TURN_MIN_SHARE) * e)

    dvx = dx - vx
    dvy = dy - vy
    if speed > 0.3 * M_TO_PX:
        inv = 1.0 / speed
        ux = vx * inv
        uy = vy * inv
        along = dvx * ux + dvy * uy
        sx = dvx - ux * along
        sy = dvy - uy * along
        along = max(-brake * dt, min(accel * dt, along))
        side_len = sqrt(sx * sx + sy * sy)
        if side_len > lateral * dt:
            k = (lateral * dt) / side_len
            sx *= k
            sy *= k
        nvx = (vx + ux * along) + sx
        nvy = (vy + uy * along) + sy
    else:
        # From (nearly) standing: accelerate in any direction
        dv_len = sqrt(dvx * dvx + dvy * dvy)
        max_dv = accel * dt              # (setting off: it's acceleration, not braking)
        if dv_len > max_dv:
            k = max_dv / dv_len
            nvx = vx + dvx * k
            nvy = vy + dvy * k
        else:
            nvx = vx + dvx
            nvy = vy + dvy
    player.vel = Vector2(nvx, nvy)

    # --- Body contact: keep players from overlapping ---
    if all_players:
        min_dist = 0.65 * M_TO_PX
        pos = player.pos
        px, py = pos.x, pos.y
        # Almost nobody is within touching distance: find the few who are first
        # (same test as below, done in one go), and only if one of them actually
        # pushes him - which moves him - check the rest one by one as before.
        neg = -min_dist
        cx = CONTACT_XS
        if cx is not None and cx[0] is all_players:
            near = [i for i, x in enumerate(cx[1]) if neg <= px - x <= min_dist and all_players[i] is not player]
        else:
            near = [i for i, o in enumerate(all_players) if neg <= px - o.pos.x <= min_dist and o is not player]
        start = len(all_players)
        for i in near:
            other = all_players[i]
            ddy = py - other.pos.y
            if ddy > min_dist or ddy < -min_dist:
                continue
            d_vec = player.pos - other.pos
            d_len = d_vec.length()
            if 0 < d_len < min_dist:
                overlap = min_dist - d_len
                push_dir = d_vec / d_len
                player.pos += push_dir * (overlap * 0.5)
                px, py = player.pos.x, player.pos.y
                if player.vel.dot(push_dir) < 0:
                    player.vel -= player.vel.project(push_dir) * 0.7
                start = i + 1            # he's moved: the rest the slow way
                break
        for other in all_players[start:]:
            if other is player:
                continue
            # quick rejection: almost every pair is nowhere near touching
            ddx = px - other.pos.x
            if ddx > min_dist or ddx < -min_dist:
                continue
            ddy = py - other.pos.y
            if ddy > min_dist or ddy < -min_dist:
                continue
            d_vec = player.pos - other.pos
            d_len = d_vec.length()
            if 0 < d_len < min_dist:
                overlap = min_dist - d_len
                push_dir = d_vec / d_len
                player.pos += push_dir * (overlap * 0.5)
                px, py = player.pos.x, player.pos.y
                if player.vel.dot(push_dir) < 0:
                    player.vel -= player.vel.project(push_dir) * 0.7

    player.pos += player.vel * dt

    # Which way the body faces
    if has_ball:
        # On the ball: faces where he's carrying it (turn rate already limited above)
        if player.vel.length_squared() > 25:          # > 0.5 m/s
            player.facing = player.vel.normalize()
    elif not staggered:
        _orientation.turn(player, face_target, dt, top)


def _respect_lines(player, desired):
    m = BALL_LINE_MARGIN * M_TO_PX
    brake = (BRAKE_BASE + BRAKE_PER_POINT * _stat(player, "Agility")) * M_TO_PX * 0.6
    x, y = player.pos.x, player.pos.y
    dx, dy = desired.x, desired.y

    def cap(comp, room_low, room_high):
        # allowed speed towards a line = sqrt(2 * a * room left before it)
        if comp < 0:
            return max(comp, -math.sqrt(2.0 * brake * max(0.0, room_low)))
        return min(comp, math.sqrt(2.0 * brake * max(0.0, room_high)))

    dx = cap(dx, x - m, WIDTH - m - x)
    dy = cap(dy, y - m, HEIGHT - m - y)
    return Vector2(dx, dy)
