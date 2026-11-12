"""
core/clock.py
=============
Single source of truth for GAME time (seconds of simulated play).

The match engine sets it every frame.  Anything that needs "now" but isn't
handed current_time (e.g. Ball.kick) reads it from here.  Previously
Ball.kick used pygame.time.get_ticks() (wall-clock time) while the offside
system compared it against game time, so the two drifted apart, and after
pressing R they were minutes out of step.
"""

_now = 0.0


def now():
    return _now


def set_time(t):
    global _now
    _now = float(t)
