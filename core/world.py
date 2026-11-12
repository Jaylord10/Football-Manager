"""
core/world.py
=============
A tiny shared registry of who's on the pitch, set by the match engine.

Lets low-level actions (like a pass) work out things such as "how close is
the nearest opponent?" without every caller having to pass the teams in.
"""

players = []      # all 22 players (both teams), set by MatchEngine
ball = None       # the match ball, set by MatchEngine


def opponents_of(player):
    return [p for p in players
            if p.team != player.team and getattr(p, "is_active", True)]
