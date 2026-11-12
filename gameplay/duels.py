"""
gameplay/duels.py
=================
One-v-one duels between the man on the ball and a defender.

Before: any defender within 2.5 m automatically tried a tackle every second
(~40% each time, better from the front).  Defenders never had to choose, a
missed tackle cost them nothing, and the carrier had no way to go past
anyone - so even Messi beat his man only ~25% of the time (real: ~57%,
league average ~50%).

Now there are two kinds of duel:

1. TAKE-ON (the attacker's move).  The carrier has chosen to go at his man
   (ai/carrier.py) and runs at a defender standing in front of him (within
   TAKEON_DIST) - just carrying the ball into space and bumping into
   someone isn't a take-on.  One roll:
       his Dribbling / Agility / Acceleration
       vs the defender's Tackling / Agility / Anticipation / Def. Positioning
   plus a bonus for running at pace and a penalty if another defender is
   close enough to cover.
     - Win:  the defender is wrong-footed (can't move for STAGGER_BEATEN
             seconds) and the carrier bursts past him.
     - Lose: the defender nicks it - he wins it outright, or it pops loose.

2. TACKLE (the defender's choice).  A defender within TACKLE_REACH weighs
   up his chance of winning the ball.  He only dives in if it's good
   enough - otherwise he stays on his feet and jockeys (keeps goal-side and
   waits; see ai/pressing.py).  When he does go in:
     - Win:  he takes the ball.
     - Miss: he's on the floor / off balance for STAGGER_MISSED seconds,
             and it may be a foul.
   Good moments to go in: the carrier has his back to goal or is turning,
   has only just received it, or is coming straight at him.  Aggressive
   players go in more readily, players with poor Decisions misjudge it, and
   the last man is more careful.

All tuning numbers are in the TUNING block.  Stats are 1-20.
"""

import random
from collections import Counter
from pygame.math import Vector2
from config.constants import WIDTH, M_TO_PX

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
# Take-ons
TAKEON_DIST        = 1.6    # m: carrier this close to a defender in front of him -> take-on
TAKEON_FRONT       = 0.35   # how "in front" the defender must be (cos of angle to his run)
TAKEON_MIN_SPEED   = 1.5    # m/s: carrier must be moving
TAKEON_BASE        = 0.47   # success chance when attacker and defender are equal...
TAKEON_PER_POINT   = 0.020  # ...plus this per point the attacker is better
TAKEON_PACE_BONUS  = 0.05   # carrier running at > 5 m/s
TAKEON_COVER       = 0.10   # another defender within COVER_DIST of the carrier
COVER_DIST         = 4.0    # m
TAKEON_RANGE       = (0.12, 0.85)
TAKEON_LOOSE       = 0.35   # a failed take-on: this share pop loose instead of the defender winning it
PAIR_COOLDOWN      = 1.2    # s before the same defender can be taken on again

# Wanting to take him on (ai/carrier.py, ai/decisive.py): a good dribbler wants
# to get 1v1 and go past his man; an ordinary one often passes or shoots instead
WANT_SLOPE         = 1.6    # chance = WANT_SLOPE x dribbling ability (0-1) - WANT_OFFSET
WANT_OFFSET        = 0.55   #   (ability 13 -> ~45%, 16 -> ~70%, 19 -> ~95%, 9 -> ~10%)
WANT_COVERED       = 0.5    # x this if another defender is covering
WANT_EVERY         = 2.0    # s: he makes his mind up about a defender this often

# Tackles
TACKLE_REACH       = 1.8    # m
TACKLE_BASE        = 0.36   # chance to win the ball when tackler and dribbler are equal...
TACKLE_PER_POINT   = 0.03   # ...plus this per point of Tackling over the carrier's Dribbling
FROM_FRONT         = 0.15   # carrier coming straight at him
FROM_BEHIND        = -0.45  # chasing from behind
BACK_TO_GOAL       = 0.12   # carrier facing his own goal / turning
HEAVY_TOUCH        = 0.20   # carrier's first touch was heavy (ai/carrier.py): ball exposed...
CLEAN_TOUCH        = -0.05  # ...or clean: he's already protecting it
JUST_RECEIVED_TIME = 0.3    # (the controlling touch, ai/decision_timing.py)
SETTING            = 0.12   # carrier is setting himself to pass / shoot (ai/decision_timing.py): get a foot in
SHIELDED           = -0.12  # carrier has his body between the defender and the ball...
SHIELD_PER_STRENGTH = 0.01  # ...more so the stronger he is (per point over 10)
TACKLE_RANGE       = (0.05, 0.92)
COMMIT_THRESHOLD   = 0.66   # dives in when his chance is at least this...
COMMIT_PER_AGGRESSION = 0.012  # ...minus this per Aggression point over 10
COMMIT_LAST_MAN    = 0.12   # ...plus this if he's the last defender
IMPATIENCE_AFTER   = 2.0    # s on the same man before he starts losing patience...
IMPATIENCE_PER_S   = 0.06   # ...then his commit threshold drops this much per second
IMPATIENCE_MAX     = 0.25
COMMIT_HIGH_PRESS  = -0.06  # ...minus this in the opposition half (losing it there costs little)
MISJUDGE_SD        = 0.15   # how far off his judgement can be at Decisions 1 (0 at 20)
THINK_TIME         = (0.50, 1.00)  # s between decisions at Decisions 20 / 1
POKE_SPEED         = (3.0, 8.0)    # m/s: a tackle that pokes it away sends it off this fast

# Fouls
MISSED_FOUL_BASE   = 0.30   # a missed tackle is a foul this often...
MISSED_FOUL_BEHIND = 0.20   # ...plus this if he went in from behind
TRIP_BASE          = 0.18   # a beaten defender trips / pulls back the attacker this often
FOUL_PER_AGGRESSION = 0.02  # both: + this per Aggression point over 10
YELLOW_TRIP        = 0.10   # bringing down a man who's beaten you: usually just a foul...
YELLOW_TRIP_BREAK  = 0.50   # ...but stopping a promising attack is a booking half the time
BREAK_ZONE         = 45.0   # m from goal: a "promising attack" is inside this, with nobody else goal-side
YELLOW_BEHIND      = 0.25   # so is a tackle from behind
YELLOW_OTHER       = 0.08   # an ordinary mistimed tackle rarely is
YELLOW_PER_AGGRESSION = 0.01

# Consequences
STAGGER_BEATEN     = 0.70   # s a beaten defender can't react
STAGGER_MISSED     = 0.90   # s a defender who missed a tackle is out of it
BURST_DIST         = 6.0    # m: carrier knocks it past and goes
BURST_SIDE         = 1.5    # m to the side, away from the defender
BURST_SPEED_MULT   = 1.05

STATS = Counter()     # ("takeon", player_name) / ("takeon_won", ...), ("tackle"), ("tackle_won")


from core.stats import stat20 as _stat    # (cached: attributes never change during a match)


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def _heading(p):
    if p.vel.length_squared() > (0.5 * M_TO_PX) ** 2:
        return p.vel.normalize()
    if p.facing.length_squared() > 0:
        return p.facing.normalize()
    return Vector2(1, 0) if p.team == 0 else Vector2(-1, 0)


# ---------------------------------------------------------------------------
def handle(team0, team1, ball, now):
    """
    Resolve duels for this frame.
    Returns (ball_won: bool, foul_info: dict | None) like the old handle_tackles.
    """
    carrier = ball.owner
    if carrier is None or ball.z > 5.0 or carrier.role == "GK":
        return False, None
    defenders = [d for d in (team1 if carrier.team == 0 else team0)
                 if getattr(d, "is_active", True) and d.role != "GK"]
    if not defenders:
        return False, None

    # Nearest first, so the man in front gets the first say
    defenders.sort(key=lambda d: (d.pos - carrier.pos).length_squared())
    heading = _heading(carrier)

    for d in defenders:
        rel = d.pos - carrier.pos
        dist_m = rel.length() / M_TO_PX
        if dist_m > max(TAKEON_DIST, TACKLE_REACH):
            break
        if now < getattr(d, "stagger_until", 0.0):
            continue
        front = rel.normalize().dot(heading) if dist_m > 0.01 else 1.0

        # 1. Take-on: carrier runs at a defender in front of him
        if (carrier.state == "dribble" and dist_m <= TAKEON_DIST and front >= TAKEON_FRONT
                and now >= getattr(carrier, "_busy_until", 0.0)      # not while controlling / setting a pass
                and getattr(carrier, "_go_at_him", True)              # only if he's CHOSEN to take him on (ai/carrier.py)
                and carrier.vel.length() / M_TO_PX >= TAKEON_MIN_SPEED
                and now >= getattr(d, "_duel_cooldown_until", 0.0)):
            d._duel_cooldown_until = now + PAIR_COOLDOWN
            return _take_on(carrier, d, defenders, ball, now, heading)

        # 2. Defender's decision: tackle or jockey
        if dist_m <= TACKLE_REACH and now >= getattr(d, "_tackle_think_until", 0.0):
            dec = _stat(d, "Decisions")
            d._tackle_think_until = now + THINK_TIME[1] + (THINK_TIME[0] - THINK_TIME[1]) * (dec - 1) / 19
            # Directly behind a carrier running away: no realistic tackle
            if front < -0.8 and carrier.vel.length() > 1.0 * M_TO_PX:
                continue
            p_win = tackle_chance(d, carrier, now)
            judged = p_win + random.gauss(0.0, MISJUDGE_SD * (20 - dec) / 19)
            if judged >= _commit_threshold(d, carrier, defenders, now):
                return _tackle(d, carrier, ball, now, p_win)
    return False, None


# ---------------------------------------------------------------------------
def dribble_ability(carrier):
    """0-1: how good he is at beating a man (Dribbling, Agility, Acceleration)."""
    a = 0.5 * _stat(carrier, "Dribbling") + 0.3 * _stat(carrier, "Agility") + 0.2 * _stat(carrier, "Acceleration")
    return (a - 1.0) / 19.0


def wants_take_on(carrier, d, defenders, now):
    """Does he fancy taking this defender on?  Decided every WANT_EVERY s per defender."""
    memo = getattr(carrier, "_want_takeon", None)
    if memo is None:
        memo = carrier._want_takeon = {}
    key = getattr(d, "role", "?") + str(getattr(d, "team", ""))
    rec = memo.get(key)
    if rec is None or now - rec[0] > WANT_EVERY:
        p = WANT_SLOPE * dribble_ability(carrier) - WANT_OFFSET
        if any(o is not d and (o.pos - carrier.pos).length() < COVER_DIST * 2 * M_TO_PX for o in defenders):
            p *= WANT_COVERED
        rec = (now, random.random() < max(0.03, min(0.97, p)))
        memo[key] = rec
    return rec[1]


def takeon_chance(carrier, d, defenders):
    att = 0.5 * _stat(carrier, "Dribbling") + 0.3 * _stat(carrier, "Agility") \
        + 0.2 * _stat(carrier, "Acceleration")
    dfn = 0.4 * _stat(d, "Tackling") + 0.2 * _stat(d, "Agility") \
        + 0.2 * _stat(d, "Anticipation") + 0.2 * _stat(d, "Defensive Positioning")
    p = TAKEON_BASE + TAKEON_PER_POINT * (att - dfn)
    if carrier.vel.length() / M_TO_PX > 5.0:
        p += TAKEON_PACE_BONUS
    if any(o is not d and (o.pos - carrier.pos).length() < COVER_DIST * M_TO_PX for o in defenders):
        p -= TAKEON_COVER
    return _clamp(p, *TAKEON_RANGE)


def _take_on(carrier, d, defenders, ball, now, heading):
    p = takeon_chance(carrier, d, defenders)
    STATS[("takeon", carrier.name)] += 1
    if random.random() < p:
        STATS[("takeon_won", carrier.name)] += 1
        d.stagger_until = now + STAGGER_BEATEN
        # Knock it past him on the side away from him, and go
        side = Vector2(-heading.y, heading.x)
        if (d.pos - carrier.pos).dot(side) > 0:
            side = -side
        target = carrier.pos + heading * (BURST_DIST * M_TO_PX) + side * (BURST_SIDE * M_TO_PX)
        from gameplay.ball_control import execute_dribble
        execute_dribble(carrier, target, ball, now, speed_mult=BURST_SPEED_MULT)
        carrier.last_decision_time = now
        carrier._burst_until = now + 0.6
        # ...unless the beaten man brings him down
        p_trip = TRIP_BASE + FOUL_PER_AGGRESSION * (_stat(d, "Aggression") - 10)
        return False, _maybe_foul(d, carrier, now, p_trip,
                                  YELLOW_TRIP_BREAK if _promising(carrier, defenders, d) else YELLOW_TRIP)
    # Lost it
    if random.random() < TAKEON_LOOSE:
        _pop_loose(carrier, d, ball, now)
        return False, None
    _win_ball(d, carrier, ball, now)
    return True, None


# ---------------------------------------------------------------------------
def tackle_chance(d, carrier, now):
    gap = _stat(d, "Tackling") - _stat(carrier, "Dribbling")
    p = TACKLE_BASE + TACKLE_PER_POINT * gap
    if carrier.vel.length_squared() > (0.5 * M_TO_PX) ** 2:
        approach = (carrier.pos - d.pos).normalize().dot(carrier.vel.normalize())
        if approach > 0.6:
            p += FROM_BEHIND
        elif approach < -0.4:
            p += FROM_FRONT
    attack_x = 1.0 if carrier.team == 0 else -1.0
    if carrier.facing.x * attack_x < -0.2:
        p += BACK_TO_GOAL
    if now - getattr(carrier, "last_received_time", -10.0) < JUST_RECEIVED_TIME:
        p += CLEAN_TOUCH if getattr(carrier, "_touch_clean", True) else HEAVY_TOUCH
    timing = getattr(carrier, "_timing", None)
    if timing is not None and timing.get("pending") is not None:
        p += SETTING
    # Shielding: the defender is behind the way he's facing - the ball's on the far side of him
    to_d = d.pos - carrier.pos
    if to_d.length_squared() > 0 and carrier.facing.length_squared() > 0 \
            and to_d.normalize().dot(carrier.facing.normalize()) < -0.3:
        p += SHIELDED - SHIELD_PER_STRENGTH * (_stat(carrier, "Strength") - 10)
    return _clamp(p, *TACKLE_RANGE)


def _commit_threshold(d, carrier, defenders, now=None):
    t = COMMIT_THRESHOLD - COMMIT_PER_AGGRESSION * (_stat(d, "Aggression") - 10)
    # Stood off him for a while and he's going nowhere: sooner or later he goes in
    if now is not None:
        if getattr(d, "_engaged_with", None) is not carrier or now - getattr(d, "_engaged_seen", -9.0) > 1.0:
            d._engaged_with, d._engaged_since = carrier, now
        d._engaged_seen = now
        waited = now - d._engaged_since - IMPATIENCE_AFTER
        if waited > 0:
            t -= min(IMPATIENCE_MAX, IMPATIENCE_PER_S * waited)
    own_goal_x = 0.0 if d.team == 0 else WIDTH
    # Last man: nobody else between the carrier and our goal
    my_gap = abs(d.pos.x - own_goal_x)
    if not any(o is not d and abs(o.pos.x - own_goal_x) < my_gap for o in defenders):
        t += COMMIT_LAST_MAN
    if (carrier.pos.x - WIDTH / 2) * (1 if d.team == 0 else -1) > 0:
        t += COMMIT_HIGH_PRESS
    return t


def _tackle(d, carrier, ball, now, p_win):
    STATS["tackle"] += 1
    d.last_tackle_time = now
    if random.random() < p_win:
        STATS["tackle_won"] += 1
        _win_ball(d, carrier, ball, now)
        return True, None
    # Missed: out of the game for a moment, and maybe a foul
    behind = carrier.vel.length_squared() > (0.5 * M_TO_PX) ** 2 and \
        (carrier.pos - d.pos).normalize().dot(carrier.vel.normalize()) > 0.6
    d.stagger_until = now + STAGGER_MISSED
    d.vel *= 0.5
    p_foul = MISSED_FOUL_BASE + (MISSED_FOUL_BEHIND if behind else 0.0) \
        + FOUL_PER_AGGRESSION * (_stat(d, "Aggression") - 10)
    return False, _maybe_foul(d, carrier, now, p_foul, YELLOW_BEHIND if behind else YELLOW_OTHER)


def _promising(carrier, defenders, beaten):
    """Was he through on goal?  Close enough, and no other defender goal-side of him."""
    goal_x = WIDTH if carrier.team == 0 else 0.0
    if abs(goal_x - carrier.pos.x) / M_TO_PX > BREAK_ZONE:
        return False
    return not any(o is not beaten and abs(goal_x - o.pos.x) < abs(goal_x - carrier.pos.x)
                   for o in defenders)


def _maybe_foul(d, carrier, now, p_foul, p_yellow):
    """Roll for a foul, then for a card (gameplay/cards.py can also make it a red)."""
    if now - getattr(d, "last_foul_time", -99.0) < 4.0:      # no foul spam from one player
        return None
    if random.random() >= p_foul:
        return None
    from gameplay.cards import assess_tackle
    card = assess_tackle(d, carrier, now, False)
    if card in ("none", "foul"):
        p_y = p_yellow + YELLOW_PER_AGGRESSION * (_stat(d, "Aggression") - 10)
        card = "yellow" if random.random() < p_y else "foul"
    d.last_foul_time = now
    return {"fouler": d, "fouled": carrier, "pos": Vector2(carrier.pos),
            "card_type": card, "attacking_team": carrier.team}


def _win_ball(d, carrier, ball, now):
    carrier.has_ball = False
    carrier.state = "tackled"
    ball.owner = d
    d.has_ball = True
    d.last_received_time = now
    ball.last_toucher = d
    ball.last_toucher_team = d.team
    d.last_tackle_time = now
    d.state = "tackle"


def _pop_loose(carrier, d, ball, now):
    """The defender gets a foot to it: nobody has it, it rolls away."""
    carrier.has_ball = False
    carrier.state = "tackled"
    ball.owner = None
    ball.last_toucher = d
    ball.last_toucher_team = d.team
    axis = carrier.pos - d.pos
    if axis.length_squared() < 1e-6:
        axis = Vector2(1, 0)
    axis = axis.normalize()
    side = Vector2(-axis.y, axis.x) * random.choice((-1.0, 1.0))
    direction = (side + axis * random.uniform(-0.8, 0.8)).normalize()
    ball.vel = direction * (random.uniform(*POKE_SPEED) * M_TO_PX)
    ball.pos = Vector2(ball.pos) + direction * (0.8 * M_TO_PX)
