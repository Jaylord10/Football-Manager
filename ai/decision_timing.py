"""
ai/decision_timing.py
=====================
Giving the man on the ball HUMAN timing.

Before this a player decided 60 times a second, with perfect knowledge of
everyone on the pitch, and the ball left his foot the instant he decided.
Under pressure he received and released it in two frames (0.03 s); when free
he waited exactly 0.4 s and passed.  The ball spent 0.85 s with each player on
average - real players have it for ~2.5 s.

Now, from the moment he receives it:

  1. FIRST TOUCH  - he has to control it (~0.3 s) before he can do anything
     else.  (A genuine first-time pass is still possible - see 4.)
  2. LOOK         - unless he already knows his options, he has to get his
     head up and see them: ~0.25 s for a top decision-maker, ~0.6 s for a
     poor one; hurried (but shorter) when he's under pressure.
  3. SETTING IT UP - a pass or shot takes ~0.15-0.35 s to set (plant foot,
     open the body, swing), a bit longer for a long ball.  While he sets it
     a defender can still get there and block or tackle.
  4. THE PICTURE  - players scan before the ball arrives.  A good reader of
     the game (Anticipation + Decisions) usually already knows where his
     options are, so he skips the LOOK - and under pressure he can play it
     first time (gameplay/ball_control.py).  A poor one often can't.
     If a defender is about to be on him he RUSHES it instead: quicker to
     set, but less accurate - so pressure now costs misplaced passes, not
     just tackles.
  5. THINKING     - after a decision he sticks with it for a moment: options
     are re-checked every ~0.25-0.6 s (Decisions), not every frame.

Messi-level players (Decisions/Anticipation 20) are quicker at every step,
but nobody is instant.

All tuning numbers are in the TUNING block (seconds).
"""

import random

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
TOUCH          = 0.30          # s to control the ball
LOOK           = (0.60, 0.25)  # s to get the head up and see the options (worst, best Decisions)
HURRIED        = 0.70          # under pressure the look is quicker (and less thorough)
REDECIDE       = (0.60, 0.25)  # s between re-checks of his options (worst, best Decisions)
SETUP_PASS     = (0.35, 0.15)  # s to set a pass (worst, best Passing)...
SETUP_LONG     = 0.10          # ...+ this for a long ball (over LONG_PASS m)
LONG_PASS      = 30.0
SETUP_SHOT     = (0.40, 0.20)  # s to set a shot (worst, best Finishing / Composure)
PICTURE        = (0.20, 0.75)  # chance he already knows his options when it arrives (worst, best reader)
HURRY_DIST     = 3.0           # m: an opponent this close (or arriving within the set-up) = he rushes it...
HURRY_SETUP    = 0.4           # ...setting it in this share of the time...
HURRY_ERROR    = 1.4           # ...and it's this much less accurate (gameplay/passing.py)


from core.stats import stat20 as _stat    # (cached: attributes never change during a match)


def _lerp(lo_hi, stat):
    lo, hi = lo_hi
    return lo + (hi - lo) * (stat - 1.0) / 19.0


def has_picture(p, ball):
    """Did he scan before this ball arrived?  Rolled once per pass he receives."""
    key = getattr(ball, "last_kick_time", None)
    if getattr(p, "_picture_for", object()) != key:
        reader = 0.5 * (_stat(p, "Anticipation") + _stat(p, "Decisions"))
        p._picture_for = key
        p._picture = random.random() < _lerp(PICTURE, reader)
    return p._picture


def first_decision(p, pressured, picture):
    """Seconds after receiving before he can make his first decision."""
    t = TOUCH
    if not picture:
        look = _lerp(LOOK, _stat(p, "Decisions"))
        t += look * (HURRIED if pressured else 1.0)
    return t


def redecide_gap(p):
    return _lerp(REDECIDE, _stat(p, "Decisions"))


def setup_time(p, kind, dist_m=0.0):
    if kind == "shot":
        return _lerp(SETUP_SHOT, 0.5 * (_stat(p, "Finishing") + _stat(p, "Composure")))
    t = _lerp(SETUP_PASS, _stat(p, "Passing"))
    if dist_m > LONG_PASS:
        t += SETUP_LONG
    return t


def _closing(p, within):
    """Is an opponent on him, or about to be within the next `within` seconds?"""
    import core.world as world
    from config.constants import M_TO_PX
    opps = world.opponents_of(p) if world.players else []
    for o in opps:
        if o.role == "GK" or not getattr(o, "is_active", True):
            continue
        rel = p.pos - o.pos
        d = rel.length()
        if d < HURRY_DIST * M_TO_PX:
            return True
        if d > 0:
            closing = o.vel.dot(rel / d)                       # px/s towards him
            if d - closing * within < HURRY_DIST * M_TO_PX:
                return True
    return False


class Deferred:
    """
    Stands in for the mechanics object while the carrier decides: passes and
    shots are not struck straight away but queued with their set-up time;
    everything else (dribbling etc.) goes straight through.
    """
    def __init__(self, mechanics, carrier, now):
        self._m = mechanics
        self._carrier = carrier
        self._now = now
        self.queued = None

    def __getattr__(self, name):
        return getattr(self._m, name)

    def execute_pass(self, passer, receiver, ball, current_time, opponents=None, through_plan=None):
        d = (receiver.pos - passer.pos).length()
        from config.constants import M_TO_PX
        delay = setup_time(passer, "pass", d / M_TO_PX)
        if _closing(passer, delay):
            delay *= HURRY_SETUP
            passer._hurried = True
        else:
            passer._hurried = False
        self.queued = {"kind": "pass", "args": (passer, receiver, ball, current_time, opponents, through_plan),
                       "at": self._now + delay}
        return True

    def execute_cross(self, passer, receiver, ball, current_time, opponents=None, kind="cross"):
        d = (receiver.pos - passer.pos).length()
        from config.constants import M_TO_PX
        delay = setup_time(passer, "pass", d / M_TO_PX)
        if _closing(passer, delay):
            delay *= HURRY_SETUP
        self.queued = {"kind": "cross", "args": (passer, receiver, ball, opponents, kind),
                       "at": self._now + delay}
        return True

    def execute_clearance(self, player, ball, current_time, kind, aim, pressured=False, first_time=False):
        import ai.clearance as clearance
        delay = clearance.setup_time(player)
        if _closing(player, delay):
            delay *= HURRY_SETUP
        self.queued = {"kind": "clear", "args": (player, ball, kind, aim, pressured),
                       "at": self._now + delay}
        return True

    def execute_shot(self, player, ball, current_time, opponents=None, shot_type=None):
        delay = setup_time(player, "shot")
        self.queued = {"kind": "shot", "args": (player, ball, current_time, opponents),
                       "kw": {"shot_type": shot_type} if shot_type else {}, "at": self._now + delay}
        return True
