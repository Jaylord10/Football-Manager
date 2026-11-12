"""
ai/urgency.py
=============
How urgently each player needs to get where he's going.

Real players don't move at a speed set by distance alone.  A defender 20 m
out of position while the opposition knock it around at the back walks
back; the same defender with a winger running past him sprints flat out.
So every frame each outfield player gets an URGENCY between 0 and 1, and
core/locomotion.py turns it into a pace:

    0.00  walk         (~1.3 m/s)
    0.25  jog          (~2.8 m/s)
    0.50  run          (~4.3 m/s)
    0.75  high-speed   (~6.0 m/s)
    1.00  flat out     (his top speed)

What raises urgency
-------------------
Without the ball (defending):
  - DANGER: the ball is near our goal, or moving towards it quickly.
  - BEATEN: the ball is goal-side of him and he has to get back behind it.
    This is the big one: a beaten player sprints to recover.
  - TRANSITION: we've just lost the ball.  For the first few seconds
    everyone gets back into shape hard.

With the ball (attacking):
  - COUNTER: we've just won the ball and his spot is forward - bomb on.
  - KEEP UP: the attack has moved on and his spot is well ahead of him -
    get up there (wingers and strikers were trailing 10 m behind play).
  - PROGRESS: the further up the pitch the ball is, the sharper the
    movement around it.  Recycling at the back is done at walking pace.

Out of possession each defender judges DANGER and BEATEN from his own read
of the play (ai/reading.py), so a slow reader reacts later than a sharp one,
and the further he is out of position the harder he goes (FAR).  On top of
that everyone picks his own pace (MOOD): a little quicker or slower than the
next man, changing every few seconds - so a back four never moves at exactly
the same speed.

Everything is scaled by NEED (nobody hurries for a half-metre adjustment;
from a few metres away he's on it), by the position's DUTY (centre-backs track back harder than
strikers; strikers burst forward harder than centre-backs), and finally by
his WORK RATE: a hard worker treats every situation as more urgent, a lazy
forward jogs back even when he shouldn't.

All tuning numbers are in the TUNING block.
"""

import random
from config.constants import WIDTH, HEIGHT, M_TO_PX
import core.fatigue as fatigue

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
NEED_MIN          = 0.5    # m from his spot: closer than this he doesn't need to hurry at all
NEED_RANGE        = 3.0    # m: need reaches 1 at NEED_MIN + NEED_RANGE
# (how fast he actually goes for a short distance is limited by arriving
#  smoothly - core/locomotion.py - so urgency doesn't need to scale with distance)
BALL_MOVING       = 0.15   # + this for everyone while a pass / loose ball is travelling fast...
BALL_MOVING_SPEED = 8.0    # ...faster than this (m/s): the whole shape shifts with it
TRANSITION_TIME   = 5.0    # s after possession changes that count as a transition

# Defending
DANGER_NEAR       = 10.0   # m from our goal: maximum danger
DANGER_FAR        = 60.0   # m from our goal: no danger
DANGER_TOWARDS    = 15.0   # m/s of ball speed towards our goal that adds the max bonus...
DANGER_TOWARDS_MAX = 0.25  # ...which is this much
DEF_BASE          = 0.20   # urgency just getting into shape
DEF_DANGER        = 0.40   # + this x danger
DEF_TRANSITION    = 0.30   # + this x transition
BEATEN_MIN        = 1.0    # m: ball must be this far goal-side of him to count as beaten
BEATEN_FULL       = 8.0    # m: fully beaten
RECOVER_BASE      = 0.45   # urgency of a recovery run...
RECOVER_DANGER    = 0.35   # + this x danger
RECOVER_TRANSITION = 0.25  # + this x transition

DEF_FAR           = 0.25   # + up to this the further he is from his spot...
DEF_FAR_FROM      = 4.0    # ...starting this far (m)...
DEF_FAR_FULL      = 20.0   # ...full at this far

# Everyone: his own choice of pace
MOOD_RANGE        = 0.07   # +/- this on his urgency...
MOOD_CHANGE       = (2.0, 5.0)  # ...re-picked every this many seconds

# Attacking
ATT_BASE          = 0.20
ATT_PROGRESS      = 0.30   # + this x how far up the pitch the ball is
COUNTER_FORWARD   = 0.70   # + this x transition when his spot is ahead of him
COUNTER_OTHER     = 0.20   # + this x transition otherwise
FORWARD_MIN       = 3.0    # m: spot counts as "ahead" if it's this far forward
CATCH_UP          = 0.45   # + up to this when his spot is well ahead of him (the attack has left him behind)...
CATCH_UP_FROM     = 4.0    # ...starting when it's this far ahead...
CATCH_UP_FULL     = 14.0   # ...full when it's this far ahead
CATCH_UP_ROLES    = ("LM", "RM", "ST1", "ST2")   # the attackers who have to be up with play

# How hard each position works in each phase
DEF_DUTY = {"LB": 0.95, "RB": 0.95, "LCB": 1.0, "RCB": 1.0, "LCM": 0.9, "RCM": 0.9,
            "LM": 0.8, "RM": 0.8, "ST1": 0.55, "ST2": 0.55}
ATT_DUTY = {"LB": 0.75, "RB": 0.75, "LCB": 0.4, "RCB": 0.4, "LCM": 0.85, "RCM": 0.85,
            "LM": 1.0, "RM": 1.0, "ST1": 1.0, "ST2": 1.0}

WORK_RATE_EFFECT  = 0.35   # Work Rate 20 -> x1.35 urgency, 10 -> x1.0, 1 -> x0.69


from core.stats import stat20 as _stat    # (cached: attributes never change during a match)


# Spots outside the 4-4-2 (config/slots.py) that attack like a wide man: a
# number 10, a winger, a wing-back (he has to get up the line)
_ATT_LIKE = {"AM": "LM", "W": "LM", "WB": "LM"}


def _att_key(p):
    slot = getattr(p, "slot", None)
    if slot is None or slot == p.role:
        return p.role
    from config import slots as slots_mod
    return _ATT_LIKE.get(slots_mod.kind(slot), p.role)


def _clamp01(x):
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def work_rate_mult(player):
    return 1.0 + WORK_RATE_EFFECT * (_stat(player, "Work Rate") - 10.0) / 10.0


def _mood(p, now):
    if now >= getattr(p, "_mood_next", -1.0):
        p._mood = random.uniform(-MOOD_RANGE, MOOD_RANGE)
        p._mood_next = now + random.uniform(*MOOD_CHANGE)
    return p._mood


def _danger(sign, pos, vel):
    own_goal_x = 0.0 if sign > 0 else WIDTH
    dgx = (pos.x - own_goal_x) / M_TO_PX
    dgy = (pos.y - HEIGHT / 2) / M_TO_PX
    d_goal = (dgx * dgx + dgy * dgy) ** 0.5
    danger = _clamp01(1.0 - (d_goal - DANGER_NEAR) / (DANGER_FAR - DANGER_NEAR))
    if d_goal > 0.1:
        towards = -(vel.x * dgx + vel.y * dgy) / (d_goal * M_TO_PX)   # m/s towards our goal
        danger = _clamp01(danger + DANGER_TOWARDS_MAX * _clamp01(towards / DANGER_TOWARDS))
    return danger


def update_team(team, ball, in_possession, since_change, now=None):
    """
    Set player.urgency (0-1) for every outfield player in the team.
    since_change: seconds since this team won / lost the ball.
    """
    if not team:
        return
    sign = 1.0 if team[0].team == 0 else -1.0
    trans = _clamp01(1.0 - since_change / TRANSITION_TIME)

    if in_possession:
        # How far up the pitch is the ball? 0 = our goal line, 1 = theirs
        frac = ball.pos.x / WIDTH if sign > 0 else 1.0 - ball.pos.x / WIDTH
        progress = _clamp01((frac - 0.35) / 0.5)
    else:
        ball_danger = _danger(sign, ball.pos, ball.vel)

    import ai.tactics as tactics
    style_bonus = tactics.style(team[0].team)["urgency_bonus"]   # pressing teams are sharper without the ball
    ball_moving = BALL_MOVING if (ball.owner is None and
                                  ball.vel.length() > BALL_MOVING_SPEED * M_TO_PX) else 0.0

    for p in team:
        if p.role == "GK":
            continue
        gap_m = (p.target - p.pos).length() / M_TO_PX
        need = _clamp01((gap_m - NEED_MIN) / NEED_RANGE)
        ahead_of_spot = (p.target.x - p.pos.x) * sign / M_TO_PX   # + = his spot is forward

        if in_possession:
            u = ATT_BASE + ATT_PROGRESS * progress + ball_moving
            u += trans * (COUNTER_FORWARD if ahead_of_spot > FORWARD_MIN else COUNTER_OTHER)
            # Keep up with the attack: the play has moved on and left him behind
            akey = _att_key(p)
            if akey in CATCH_UP_ROLES:
                u += CATCH_UP * _clamp01((ahead_of_spot - CATCH_UP_FROM) / (CATCH_UP_FULL - CATCH_UP_FROM))
            u *= ATT_DUTY.get(akey, 0.8)
        else:
            # His own read of where the ball is (ai/reading.py) - he reacts when he sees it
            seen = getattr(p, "_read_focus", None) if p.state == "defend" else None
            if seen is not None and now is not None and now - getattr(p, "_read_used", -99.0) < 0.5:
                danger = _danger(sign, seen, ball.vel)
                ball_x = seen.x
            else:
                danger, ball_x = ball_danger, ball.pos.x
            u = DEF_BASE + DEF_DANGER * danger + DEF_TRANSITION * trans + ball_moving + style_bonus
            u += DEF_FAR * _clamp01((gap_m - DEF_FAR_FROM) / (DEF_FAR_FULL - DEF_FAR_FROM))
            # Beaten?  Ball goal-side of him and his spot is back towards our goal
            ball_behind_m = (p.pos.x - ball_x) * sign / M_TO_PX
            if ball_behind_m > BEATEN_MIN and ahead_of_spot < -2.0:
                beaten = _clamp01((ball_behind_m - BEATEN_MIN) / (BEATEN_FULL - BEATEN_MIN))
                recover = RECOVER_BASE + RECOVER_DANGER * danger + RECOVER_TRANSITION * trans
                u = max(u, recover * (0.6 + 0.4 * beaten))
            u *= DEF_DUTY.get(p.role, 0.9)

        if now is not None:
            u += _mood(p, now)
        # Gassed or worn-out players pick their moments (core/fatigue.py)
        p.urgency = _clamp01(need * u * work_rate_mult(p) * fatigue.willingness(p))
