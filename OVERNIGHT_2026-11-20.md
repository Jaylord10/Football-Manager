# Overnight 20-21 Nov: Jay's list (branch overnight/2026-11-20-matchday-list)

Nothing here is on Jay's PC.  Each item is its own commit.

## 1. Keepers in one-on-ones
- The starfish: a keeper who's come out to the shooter (within 6 m as he strikes it) jumps into a big X -
  legs and arms spread to fill the goal - instead of the little split step.
- Diving at a man's feet: when the keeper takes the ball off an attacker (or claims it with one within 2.5 m),
  he goes down sideways low along the ground, then gets up with it.
- Beaten by a dink: the ball looping over him (1.9-3.6 m up, within 1.6 m of him), he stretches up for it with
  one hand, head back.
- The dink itself (match engine): it used to aim for 1.4-2.1 m at the goal line, so over a keeper 4-5 m out it
  was only ~1.2 m high - he caught it.  Now the strike is worked out to be ~2.9 m high going over him and to drop
  in at ~1.5 m under the bar (the softest/quickest strike from 9-17.5 m/s that does both).  And a keeper doesn't
  dive at a ball that's going over his head on the way - he can only stretch up and watch.
- Test: 150 clean-through one-on-ones (the real AI): 35% scored; dinks 15 of 19.  Strips checked in 3D.
- Checks: broadcast3d/check.py all good; replay runs (hash 229e6a3f... - unchanged from main in the first 60 s).
