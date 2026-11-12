"""
ai/reading.py
=============
Reading the play: each defender's OWN idea of where the ball is.

Before this the whole defending block worked out its shape from the exact
ball position, every frame, all at once - so eight players shifted in perfect
lockstep, like a table-football rod.  Real players don't.  Each one looks up,
reads the play, and adjusts; a sharp one re-reads constantly and sees where
the ball is GOING, a slow one reacts late to where it WAS.

So every defender keeps his own "read" of the ball:
  - He re-reads it every so often.  How often comes from Anticipation and
    Decisions: ~0.15 s for the best, ~0.75 s for the worst, with a bit of
    randomness so a back four never re-read on the same frame.
  - When he reads it, Anticipation decides how far ahead he sees: a good
    reader takes the ball's (or the dribbler's) movement into account and
    shifts to where it's heading; a poor one shifts to where it is now.
  - Between reads his spot in the shape doesn't change, so after a quick
    switch of play the sharp players are already moving while the slow ones
    are still where they were - and gaps open up.
  - He HOLDS HIS ZONE: he doesn't chase his exact spot every time the ball
    rolls a yard.  Only when the play has moved his spot further than his
    tolerance does he shuffle across to the new one.  A good decision-maker
    keeps a tight tolerance (~1 m); a poor one lets it drift (~3 m) and then
    has to make up more ground in one go.  Everyone's tolerance is a little
    different, so a back four never shuffles as one.

POSITIONING HABITS: nobody stands exactly on the textbook spot.  Each player
drifts a little off it - deeper or higher, wider or narrower - and the drift
wanders slowly over the match.  How far comes from Defensive Positioning
(where he stands) and Teamwork (how well he keeps the line with the others):
a top defender is within ~0.5 m, an average one ~1.5 m, a striker who never
defends 2-3 m.  So a poor centre-back sits a yard deep and plays a runner
onside; a switched-off midfielder leaves a gap between the lines.

ai/team_shape.py builds each defender's spot from his own read.  Pressing,
blocking and marking (ai/pressing.py) still react to the real ball.

All tuning numbers are in the TUNING block.
"""

import random
from pygame.math import Vector2
from config.constants import M_TO_PX

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
READ_BEST      = 0.15   # s between reads for Anticipation + Decisions 20...
READ_WORST     = 0.75   # s ...and for 1
READ_JITTER    = 0.30   # +/- this share of randomness on each gap
LOOK_LOOSE     = (0.15, 0.55)   # s ahead he sees a passed / loose ball (worst, best Anticipation)
LOOK_DRIBBLE   = (0.0, 0.45)    # s ahead he sees a dribbler going (worst, best)
ZONE_TOL       = (3.0, 1.0)     # m he lets his spot drift before adjusting (worst, best Decisions)...
ZONE_TOL_SPREAD = 0.35          # ...each player's own tolerance varies by +/- this share
HABIT_DEPTH    = (3.0, 0.4)     # m he can be off the line, depth (worst, best Def. Positioning + Teamwork)
HABIT_WIDTH    = (2.5, 0.4)     # m off his spot sideways (worst, best Def. Positioning)
HABIT_CHANGE   = (4.0, 9.0)     # s between changes in his drift...
HABIT_EASE     = 0.4            # ...which he drifts into at this many m/s (no sudden jumps)
STALE          = 1.0    # s: a read older than this (he wasn't defending) is replaced at once


from core.stats import stat20 as _stat    # (cached: attributes never change during a match)


def _q(v):
    """1-20 -> 0-1"""
    return (v - 1.0) / 19.0


def read_gap(p):
    """Average seconds between his reads of the play."""
    sharp = _q(0.5 * (_stat(p, "Anticipation") + _stat(p, "Decisions")))
    return READ_WORST - (READ_WORST - READ_BEST) * sharp


def _look(p, lo_hi):
    lo, hi = lo_hi
    return lo + (hi - lo) * _q(_stat(p, "Anticipation"))


def _see(p, ball):
    """Where he thinks the ball is going to be, right now."""
    if ball.owner is None:
        if ball.vel.length() > 0.5 * M_TO_PX:
            return ball.pos + ball.vel * _look(p, LOOK_LOOSE)
        return Vector2(ball.pos)
    return ball.owner.pos + ball.owner.vel * _look(p, LOOK_DRIBBLE)


def focus(p, ball, now):
    """His current read of the ball (world position, px)."""
    seen = getattr(p, "_read_focus", None)
    fresh_start = seen is None or now - getattr(p, "_read_used", -99.0) > STALE
    p._read_used = now
    if fresh_start or now >= getattr(p, "_read_next", 0.0):
        seen = _see(p, ball)
        p._read_focus = seen
        gap = read_gap(p) * random.uniform(1.0 - READ_JITTER, 1.0 + READ_JITTER)
        if fresh_start:
            gap *= random.random()          # first read: everyone starts at a different point in his rhythm
        p._read_next = now + gap
    return Vector2(seen)


def hold_zone(p, spot, now):
    """
    His actual target, given the spot the shape gives him: he stays on the
    spot he last took up until the new one is further away than his tolerance.
    """
    held = getattr(p, "_zone_spot", None)
    if held is None or now - getattr(p, "_zone_used", -99.0) > STALE:
        held = None
    p._zone_used = now
    tol = getattr(p, "_zone_tol", None)
    if tol is None:
        lo, hi = ZONE_TOL
        tol = (lo + (hi - lo) * _q(_stat(p, "Decisions"))) * random.uniform(1 - ZONE_TOL_SPREAD, 1 + ZONE_TOL_SPREAD)
        p._zone_tol = tol
    if held is None or (spot - held).length() > tol * M_TO_PX:
        held = Vector2(spot)
        p._zone_spot = held
    return Vector2(held)


def habit(p, now):
    """(depth, sideways) offset in m from his textbook spot, drifting slowly."""
    if now >= getattr(p, "_habit_next", -1.0):
        q_line = _q(0.5 * (_stat(p, "Defensive Positioning") + _stat(p, "Teamwork")))
        q_pos = _q(_stat(p, "Defensive Positioning"))
        dmax = HABIT_DEPTH[0] + (HABIT_DEPTH[1] - HABIT_DEPTH[0]) * q_line
        wmax = HABIT_WIDTH[0] + (HABIT_WIDTH[1] - HABIT_WIDTH[0]) * q_pos
        p._habit_goal = (random.uniform(-dmax, dmax), random.uniform(-wmax, wmax))
        p._habit_next = now + random.uniform(*HABIT_CHANGE)
    cur = getattr(p, "_habit", None)
    last = getattr(p, "_habit_t", now)
    if cur is None:
        cur = p._habit_goal
    else:
        step = HABIT_EASE * max(0.0, min(0.5, now - last))
        cur = tuple(c + max(-step, min(step, g - c)) for c, g in zip(cur, p._habit_goal))
    p._habit, p._habit_t = cur, now
    return cur
