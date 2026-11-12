# ===========================================================================
# gameplay/goalkeeping.py
# Keeper physical ability and save resolution.
#
# Before: keepers dived at 24 m/s with a fixed 0.15 s reaction, ignored their
# stats, and any ball inside a fixed radius was automatically parried, so
# almost every shot near the keeper was saved and nothing was ever caught.
#
# Now:
#   * Dive speed, reaction time and reach come from Shot Stopping.
#   * When the ball comes within reach, ONE save roll is made per shot.
#     The chance falls with shot speed and with how far the keeper has to
#     stretch.
#   * A successful save is HELD, TIPPED BEHIND or PARRIED BACK INTO PLAY:
#       - he holds it if he can: Handling, the pace of the shot, and whether
#         it's at him or he's at full stretch / over his head;
#       - one he can only just reach, or one over his head, he can't hold -
#         he tips it round the post or over the bar for a corner (a good
#         Shot Stopper does this more, rather than spilling it);
#       - otherwise he pushes it away into play (a rebound).
#     An average keeper ends up holding ~45-50% of his saves, tipping ~30%
#     behind and parrying ~20-25% back into play; a poor one spills a third.
#   * Slow balls (back-passes, weak shots, overhit passes) are simply claimed.
#
# All tuning numbers are in the TUNING block below.
# ===========================================================================

import random
from pygame.math import Vector2
from core.utils import distance, clamp
from config.constants import M_TO_PX, HEIGHT, WIDTH, GOAL_WIDTH, GOAL_HEIGHT, GRAVITY


# ---------------------------------------------------------------------------
# TUNING  (metres, m/s, seconds; stats on the 1-20 scale)
# ---------------------------------------------------------------------------
DIVE_SPEED      = (5.0, 0.18)    # m/s: base + per Shot Stopping point  (13 -> 7.3 m/s)
REACTION_TIME   = (0.34, -0.009) # s:   base + per point                 (13 -> 0.22 s)
REACH_DIVING    = (1.00, 0.03)   # m from the keeper's centre            (13 -> 1.4 m)
REACH_STANDING  = 1.00           # m when not diving (shot straight at him: body, legs, arms)
REACH_SPREAD    = 1.15           # m when the shot came from close range (keeper spreads himself)
SPREAD_RANGE    = 9.0            # m: shots struck closer than this to the keeper
MAX_HEIGHT_DIVING   = 2.5        # m: highest ball a diving keeper can touch
MAX_HEIGHT_STANDING = 2.3

SAVE_BASE            = 0.58      # save chance before modifiers
SAVE_PER_POINT       = 0.025     # per Shot Stopping point             (13 -> +0.33)
SAVE_SPEED_FREE      = 18.0      # m/s: shots slower than this get no speed penalty
SAVE_SPEED_PENALTY   = 0.012     # per m/s above SAVE_SPEED_FREE
SAVE_STRETCH_PENALTY = 0.25      # x (distance / reach): fingertip saves are harder
SAVE_TIME_BONUS      = 0.40      # per second of flight beyond SAVE_TIME_FREE (time to set & read it)
SAVE_TIME_FREE       = 0.45      # s
SAVE_TIME_BONUS_MAX  = 0.20

LET_GO_MARGIN = 0.25             # m: keeper leaves shots heading this far outside the frame

CATCH_BASE         = 0.50        # chance he holds it, before modifiers
CATCH_PER_POINT    = 0.03        # per Handling point
CATCH_SPEED_FREE   = 15.0
CATCH_SPEED_PENALTY = 0.025      # per m/s above CATCH_SPEED_FREE
CATCH_STRETCH_PENALTY = 0.25     # x (distance / reach): at full stretch he can't hold it
CATCH_HIGH_PENALTY = 0.20        # ...or above his head
HIGH_SAVE          = 1.7         # m: a save above this is "over his head"

# Not held: tip it behind for a corner, or parry it back into play?
TIP_BASE           = 0.10        # chance he tips it behind...
TIP_STRETCH        = 0.40        # ...+ this x (distance / reach) - fingertips
TIP_HIGH           = 0.25        # ...+ this over his head
TIP_PER_POINT      = 0.01        # ...+ this per Shot Stopping point over 10
TIP_OVER_HEIGHT    = 1.5         # m: above this he tips it over the bar, below it round the post
TIP_POST_GAP       = (0.35, 2.5) # m outside the post it crosses the line (round the post)
TIP_OVER_CLEAR     = (0.3, 1.2)  # m above the bar it crosses the line (over the bar)
TIP_SPEED          = (0.35, 0.60)  # share of the shot's pace it keeps (round the post)
TIP_OVER_SPEED     = (4.0, 9.0)  # m/s towards the line (over the bar - it loops up)

PENALTY_SAVE_FACTOR = 0.45       # from the spot the keeper has to guess
PARRY_NO_TOUCH    = 0.5          # s after a parry before the keeper can touch it again

COLLECT_MAX_SPEED = 12.0         # m/s: slower balls this close are just claimed
COLLECT_RADIUS    = 2.0          # m
COLLECT_MAX_HEIGHT = 2.0         # m


def _stat(keeper, name):
    value = keeper.attributes.get(name, 10)
    if value > 25:
        value /= 5.0
    return clamp(value, 1, 20)


def _heading_off_target(keeper, ball):
    """Straight-line prediction: will the ball cross the goal line outside the frame?"""
    goal_x = 0.0 if keeper.team == 0 else float(WIDTH)
    vx = ball.vel.x
    if abs(vx) < 1.0 or (goal_x - ball.pos.x) * vx <= 0:
        return False                      # not travelling towards this goal line
    t = (goal_x - ball.pos.x) / vx
    y = ball.pos.y + ball.vel.y * t
    z = ball.z + ball.vz * t - 0.5 * GRAVITY * t * t
    margin = LET_GO_MARGIN * M_TO_PX
    top, bottom = HEIGHT / 2 - GOAL_WIDTH / 2, HEIGHT / 2 + GOAL_WIDTH / 2
    return y < top - margin or y > bottom + margin or z > GOAL_HEIGHT + margin


def init_keeper(keeper):
    """Set a keeper's physical ability from his attributes (called once at spawn)."""
    ss = _stat(keeper, "Shot Stopping")
    keeper.dive_speed    = (DIVE_SPEED[0] + DIVE_SPEED[1] * ss) * M_TO_PX
    keeper.dive_reaction = max(0.08, REACTION_TIME[0] + REACTION_TIME[1] * ss)
    keeper.reach_diving  = REACH_DIVING[0] + REACH_DIVING[1] * ss
    keeper.reach_standing = REACH_STANDING
    keeper._last_save_roll = None


def _claim(keeper, ball, current_time, ai_system):
    ball.owner = keeper
    ball.vel = Vector2(0, 0)
    ball.z = 0.0
    ball.vz = 0.0
    keeper.has_ball = True
    keeper.last_received_time = current_time
    ball.last_toucher = keeper
    ball.last_toucher_team = keeper.team
    keeper.dive_state = "recover"
    keeper.last_dive_time = current_time
    ai_system.last_possession_team = keeper.team
    ball.last_save = {"type": "catch", "time": current_time, "keeper": keeper}


def _parry(keeper, ball, current_time, speed_ms):
    away_x = 1.0 if keeper.team == 0 else -1.0       # team 0 defends x = 0
    side = 1.0 if ball.pos.y >= HEIGHT / 2 else -1.0  # push it towards the nearer post / wide
    deflect = Vector2(away_x * random.uniform(0.2, 0.7), side * random.uniform(0.6, 1.0)).normalize()
    rebound = speed_ms * random.uniform(0.30, 0.55) * M_TO_PX
    ball.kick(deflect * rebound, kicker=keeper, elevation=random.uniform(0.0, 0.3))
    ball.last_kick_time = current_time
    keeper.dive_state = "recover"
    keeper.last_dive_time = current_time
    keeper._no_touch_until = current_time + PARRY_NO_TOUCH   # don't instantly re-gather it
    ball.last_save = {"type": "parry", "time": current_time, "keeper": keeper}


def _tip_behind(keeper, ball, current_time, speed_ms, z_m):
    """Fingertips round the post, or over the bar: it goes out for a corner."""
    import math
    goal_x = 0.0 if keeper.team == 0 else float(WIDTH)   # team 0 defends x = 0
    out_dir = -1.0 if keeper.team == 0 else 1.0           # towards (and over) his goal line
    top, bottom = HEIGHT / 2 - GOAL_WIDTH / 2, HEIGHT / 2 + GOAL_WIDTH / 2
    if z_m > TIP_OVER_HEIGHT:
        # Over the bar: it loops up and drops behind the goal
        k = 0.995 ** 60                                                # air friction per second
        nlk = -math.log(k)
        to_line = abs(goal_x - ball.pos.x)
        far = to_line + 1.0 * M_TO_PX                                  # past the line (and the goal-line check)
        v = random.uniform(*TIP_OVER_SPEED) * M_TO_PX
        v = max(v, far * nlk / 0.8)                                    # make sure it gets there
        z_line = GOAL_HEIGHT + random.uniform(*TIP_OVER_CLEAR) * M_TO_PX
        vz = 0.0
        for d in (to_line, far):                                       # above the bar all the way over
            t = max(0.05, -math.log(1.0 - d * nlk / v) / nlk)
            vz = max(vz, (z_line - ball.z + 0.5 * GRAVITY * t * t) / t)
        sideways = ball.vel.y * random.uniform(0.1, 0.4)
        ball.kick(Vector2(out_dir * v, sideways), kicker=keeper)
        ball.vz = vz
        kind = "tip_over"
    else:
        # Round the post: pick a point on the goal line just outside the nearer post
        side = 1.0 if ball.pos.y >= HEIGHT / 2 else -1.0
        if abs(ball.pos.y - HEIGHT / 2) < 0.5 * M_TO_PX and abs(ball.vel.y) > 1.0:
            side = 1.0 if ball.vel.y > 0 else -1.0                     # central: the way it was going
        # outside the post - and never back across the face of the goal if he's already wide of it
        off = max(GOAL_WIDTH / 2 + random.uniform(*TIP_POST_GAP) * M_TO_PX,
                  abs(ball.pos.y - HEIGHT / 2) + 0.3 * M_TO_PX)
        cross_y = HEIGHT / 2 + side * off
        to_point = Vector2(goal_x, cross_y) - ball.pos
        if to_point.length_squared() < 1.0:
            to_point = Vector2(out_dir, side)
        speed = max(6.0, speed_ms * random.uniform(*TIP_SPEED)) * M_TO_PX
        ball.kick(to_point.normalize() * speed, kicker=keeper, elevation=random.uniform(0.0, 0.12))
        kind = "tip_round"
    ball.intended_target = None
    ball.last_kick_time = current_time
    keeper.dive_state = "recover"
    keeper.last_dive_time = current_time
    keeper._no_touch_until = current_time + 2.0           # it's going out - he doesn't chase it
    ball.last_save = {"type": "tip", "how": kind, "time": current_time, "keeper": keeper}


def resolve_keeper_contact(keeper, ball, current_time, ai_system):
    """
    Called every frame for each keeper while the ball is loose near his goal.
    Returns True if the keeper touched the ball.
    """
    if ball.owner is not None or ball.is_dead:
        return False
    if current_time < getattr(keeper, "_no_touch_until", -1.0):
        return False

    d_m = distance(keeper.pos, ball.pos) / M_TO_PX
    speed_ms = ball.vel.length() / M_TO_PX
    z_m = ball.z / M_TO_PX

    # Slow balls close by are simply gathered up
    if speed_ms < COLLECT_MAX_SPEED and d_m < COLLECT_RADIUS and z_m < COLLECT_MAX_HEIGHT:
        _claim(keeper, ball, current_time, ai_system)
        return True

    diving = keeper.dive_state == "diving"
    if diving:
        reach = keeper.reach_diving
    else:
        reach = keeper.reach_standing
        start = getattr(ball, "pass_start_pos", None)     # where the ball was kicked from
        if start is not None and distance(keeper.pos, start) / M_TO_PX < SPREAD_RANGE:
            reach = max(reach, REACH_SPREAD)
    max_z = MAX_HEIGHT_DIVING if diving else MAX_HEIGHT_STANDING
    if d_m > reach or z_m > max_z:
        return False

    # A ball that has just come off one of his own defenders is a shot to him
    from gameplay.ricochet import is_ricochet
    deflected = is_ricochet(ball)

    # Shot clearly missing the frame?  Watch it go (don't parry wide shots in)
    if (ball.last_toucher_team != keeper.team or deflected) and _heading_off_target(keeper, ball):
        return False

    # One save attempt per kick of the ball (not one per frame)
    kick_key = (getattr(ball, "last_kick_time", None), id(ball.last_toucher))
    if keeper._last_save_roll == kick_key:
        return False
    keeper._last_save_roll = kick_key

    # A team-mate's pass/back-pass: just take it
    if ball.last_toucher_team == keeper.team and not deflected:
        _claim(keeper, ball, current_time, ai_system)
        return True

    ss = _stat(keeper, "Shot Stopping")
    handling = _stat(keeper, "Handling")

    flight = current_time - getattr(ball, "last_kick_time", current_time)
    time_bonus = clamp(SAVE_TIME_BONUS * (flight - SAVE_TIME_FREE), 0.0, SAVE_TIME_BONUS_MAX)
    p_save = (SAVE_BASE + SAVE_PER_POINT * ss + time_bonus
              - SAVE_SPEED_PENALTY * max(0.0, speed_ms - SAVE_SPEED_FREE)
              - SAVE_STRETCH_PENALTY * (d_m / reach))
    shot = getattr(ball, "shot_info", None)
    if shot and shot.get("type") == "penalty" and shot.get("time") == getattr(ball, "last_kick_time", None):
        p_save *= PENALTY_SAVE_FACTOR
    if random.random() >= clamp(p_save, 0.05, 0.97):
        return False                      # beaten - the ball carries on

    stretch = clamp(d_m / max(reach, 0.1), 0.0, 1.0)
    high = z_m > HIGH_SAVE
    p_catch = (CATCH_BASE + CATCH_PER_POINT * handling
               - CATCH_SPEED_PENALTY * max(0.0, speed_ms - CATCH_SPEED_FREE)
               - CATCH_STRETCH_PENALTY * stretch
               - (CATCH_HIGH_PENALTY if high else 0.0))
    if random.random() < clamp(p_catch, 0.05, 0.9):
        _claim(keeper, ball, current_time, ai_system)
        return True
    p_tip = TIP_BASE + TIP_STRETCH * stretch + (TIP_HIGH if high else 0.0) + TIP_PER_POINT * (ss - 10)
    if random.random() < clamp(p_tip, 0.05, 0.9):
        _tip_behind(keeper, ball, current_time, speed_ms, z_m)
    else:
        _parry(keeper, ball, current_time, speed_ms)
    return True
