# Turning to kick (branch turn-to-kick) - NOT deployed, needs more work

What it does (core/kick_angle.py): a player can kick within 70 deg of where he faces; further round he must
turn first, bringing the ball with him (his body-turn speed x 0.6), and if he hasn't got round the kick is
less accurate (up to 3x the error for a back-heel).  Keepers and set-piece takers are left alone.

## Measured (benchmark match, two "average" squads, full 90-minute matches)
- Kicks struck more than 70 deg from his facing: 39% of passes before, 6% after; nearly straight behind
  (over 150 deg): 9% before, under 1% after.
- Over 8 + 8 matches: goals per match about the same (3.5 / 3.6), pass completion the same (87%),
  passes -5%, shots -12% (closer to real: Premier League ~25 shots a match).

## The problem
Results swing towards one squad (Average Rovers) whichever end it attacks:
- before the fix: Athletic 29 goals, Rovers 19 (16 matches, home and away);
- with the fix:    Athletic 11, Rovers 41;
- a gentler version (90 deg arc, turns 0.9x, half the error penalty, 8 matches): Athletic 10, Rovers 17.
The squads are near-identical player for player.  The difference shows in shots on target that beat the
keeper: with the fix, Rovers' beat him 35% of the time and Athletic's 12% (before: 17% and 24%).
Not explained yet.  Next: test with real career squads (many clubs) rather than these two, and log who
takes the shots and from where.

Tests: scratch scripts (kickstats / gdiag2), FM_KA_NOTURN / FM_KA_NOERR switch each half off (with both off
the replay hash is the old 50d07957...), FM_KA_ARC / FM_KA_TURNK / FM_KA_ERR set the tuning.
