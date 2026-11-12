"""
core/fatigue.py
===============
How players tire - and recover.

Before: stamina drained slowly with speed and was refilled to 100% at
every kick-off (so after every goal), and the formula read a "Physical"
stat that isn't in the player files - so the Stamina stat did nothing.

Now each player has two "tanks", like real footballers:

ENERGY  (player.energy, 0-1)  - the short-term sprint reserve.
    High-speed running and hard accelerations burn it in seconds; walking
    and jogging refill it over ~half a minute.  A player who has just made
    three sprints in a row is gassed: slower, and less keen to sprint
    again until he's had a breather.  Works in real seconds.

STAMINA (player.stamina, 1 -> lower)  - how the match is wearing him down.
    Every metre costs a little, high-intensity running costs a lot.  It
    only goes down (apart from a small top-up at half-time).  Tired players
    recover their sprint energy more slowly, lose a little top speed and
    pick their moments - so the end of the game is more stretched.
    This works in MATCH time: the sim plays a half in 3 real minutes, so
    each real second counts as 15 match seconds of wear.

The Stamina stat (1-20) decides how fast both drain and recover.

All tuning numbers are in the TUNING block (speeds in m/s, time in seconds).
"""

import math
from config.constants import M_TO_PX

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
# Short-term sprint energy
ENERGY_SPEED_FROM  = 5.0     # m/s: running faster than this burns energy...
ENERGY_BURN        = 0.012   # ...at this x (speed - 5) ^ 1.5 per second (9 m/s sprint: ~10%/s)
ACCEL_FROM         = 2.5     # m/s^2: accelerating harder than this burns energy...
ACCEL_BURN         = 0.015   # ...at this per m/s^2 above it, per second
RECOVER_WALK_TAU   = 25.0    # s: time constant to refill while walking (< 2 m/s)
RECOVER_JOG_TAU    = 50.0    # s: ...and while jogging (2-4 m/s); no recovery faster than that
JOG_LIMIT          = 4.0
WALK_LIMIT         = 2.0

# Match stamina (wear and tear) - per MATCH second
WEAR_PER_LOAD      = 0.000185   # stamina lost per match-second at load 1 (load = (speed/5)^2)
WEAR_BASE_LOAD     = 0.03       # even standing around costs a little
HALF_TIME_RECOVERY = 0.06       # stamina back at half-time (capped at 1)
MATCH_SECONDS_PER_HALF = 45 * 60

# Stamina stat: 20 tires ~30% slower than 10, 1 tires ~27% faster
STAT_WEAR          = 0.03       # wear x (1 - 0.03 x (Stamina - 10))
STAT_RECOVERY      = 0.03       # energy recovery x (1 + 0.03 x (Stamina - 10))

# Effects
TOP_SPEED_ENERGY   = 0.12       # top speed x (1 - 0.12 x (1 - energy))
TOP_SPEED_STAMINA  = 0.15       # top speed x (1 - 0.15 x (1 - stamina))
ACCEL_ENERGY       = 0.35       # acceleration x (1 - 0.35 x (1 - energy))
RECOVERY_STAMINA   = 1.0        # energy recovery x (1 - 1.0 x (1 - stamina)): worn-out legs recover slowly
WILL_ENERGY        = 0.30       # urgency x (1 - 0.30 x (1 - energy)): gassed players pick their moments
WILL_STAMINA       = 0.50       # urgency x (1 - 0.50 x (1 - stamina))


from core.stats import stat20 as _stat    # (cached: attributes never change during a match)


_me = None


def _time_scale():
    """Match seconds per real second (45 min per half)."""
    global _me
    if _me is None:
        try:
            import gameplay.match_engine as me
            _me = me
        except Exception:
            from config.constants import HALF_DURATION_REAL as half
            return MATCH_SECONDS_PER_HALF / max(half, 1.0)
    return MATCH_SECONDS_PER_HALF / max(_me.HALF_DURATION_REAL, 1.0)


def init(player):
    player.stamina = 1.0
    player.energy = 1.0
    player._fat_prev_vel = None


def update(player, dt):
    """Call once per frame after the player has moved."""
    if not hasattr(player, "energy"):
        init(player)
    vel = player.vel
    vel_len = vel.length()
    v = vel_len / M_TO_PX
    prev = player._fat_prev_vel
    player._fat_prev_vel = vel.copy() if hasattr(vel, "copy") else vel * 1
    st = _stat(player, "Stamina")

    # --- Sprint energy ---
    burn = 0.0
    if v > ENERGY_SPEED_FROM:
        burn += ENERGY_BURN * (v - ENERGY_SPEED_FROM) ** 1.5
    if prev is not None and dt > 0 and v > 0.5:
        along = (vel - prev).dot(vel) / (vel_len * M_TO_PX * dt)
        if along > ACCEL_FROM:
            burn += ACCEL_BURN * (along - ACCEL_FROM)
    energy = player.energy - burn * dt
    if v < JOG_LIMIT:
        tau = RECOVER_WALK_TAU if v < WALK_LIMIT else RECOVER_JOG_TAU
        rate = (1.0 + STAT_RECOVERY * (st - 10)) * (1.0 - RECOVERY_STAMINA * (1.0 - player.stamina))
        energy += (1.0 - energy) * (1.0 - math.exp(-dt * rate / tau))
    player.energy = max(0.0, min(1.0, energy))

    # --- Match stamina ---
    if player.role == "GK":
        return          # keepers barely tire (and their simple movement code is jumpy)
    load = WEAR_BASE_LOAD + (v / 5.0) ** 2
    wear = WEAR_PER_LOAD * load * (1.0 - STAT_WEAR * (st - 10)) * dt * _time_scale()
    player.stamina = max(0.0, player.stamina - wear)


def half_time(players):
    for p in players:
        p.stamina = min(1.0, getattr(p, "stamina", 1.0) + HALF_TIME_RECOVERY)
        p.energy = 1.0


# --- Effects -----------------------------------------------------------------
def speed_factor(player):
    e = getattr(player, "energy", 1.0)
    s = getattr(player, "stamina", 1.0)
    return (1.0 - TOP_SPEED_ENERGY * (1.0 - e)) * (1.0 - TOP_SPEED_STAMINA * (1.0 - s))


def accel_factor(player):
    return 1.0 - ACCEL_ENERGY * (1.0 - getattr(player, "energy", 1.0))


def willingness(player):
    """How keen he is to put in a hard effort right now (multiplies urgency)."""
    e = getattr(player, "energy", 1.0)
    s = getattr(player, "stamina", 1.0)
    return (1.0 - WILL_ENERGY * (1.0 - e)) * (1.0 - WILL_STAMINA * (1.0 - s))


def condition(player):
    """Overall freshness 0-1 for AI choices (pressing, runs): the worse of the two."""
    return min(getattr(player, "energy", 1.0), getattr(player, "stamina", 1.0))
