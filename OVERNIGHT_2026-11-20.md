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

## 2. Shot styles you can see (3D only)
- A shot close in (under 17 m) that isn't struck flat out (under 27 m/s) is now a side-foot placed finish:
  a fuller backswing than a pass, the foot turned out and locked, body over it, a follow-through to the corner.
- A dink (soft, 9-20 m/s, rising steeply towards goal from inside 25 m): a short soft backswing, leaning
  back, the toe under it, a little lifted finish.
- Struck behind him (he hadn't turned - the turning fix): the back-heel / flick, as for passes.
- Otherwise the full laces drive, as before.
- In 16 one-on-ones: 4 finishes, 3 dinks, 3 drives (and the scruffy back-heels when he hadn't got round).
- Checks: check.py all good; the engine's untouched by this one.

## 8. Second balls (match engine)
- A loose ball on the ground used to be chased by ONE man - whoever was nearest, from either team - running at
  where the ball was.  Now each team sends its man who'll get there first, to the point where he can meet it
  (the ball's still rolling), and both go for it if the second one's within 1.5 s of the first.
- 20 minutes of a real-club match (Lydmouth-style fixture rc3): samples of a loose ball with nobody chasing
  from the side that last touched it - 151 of 286 before, 29 of 195 after; the other side - 110 of 286 before,
  none after.

## 10. The oddity checker (dev/oddities.py) - and the worst thing it found
- `python dev/oddities.py <match config> [minutes] [seed]` plays a match and lists anything that would look odd:
  bodies through each other, a player stood dead still with the ball near, running back and forth, running
  backwards fast (the moonwalk), teleporting, wandering off the pitch, the ball too fast / too high / away from
  the man who "has" it.
- First run (45 min, a real-club fixture): 63 "back and forth" moments - every one of them a KEEPER.  Cause: his
  spot only followed the ball across when someone had it - between passes it snapped back to the middle, and the
  "narrow the angle" spot switched on and off as the ball changed hands, so he twitched about.
  Fix (match engine): he follows the ball across all the time, narrows the angle while the other lot have it or
  it's loose off them, and his spot moves smoothly (5 m/s, 9 m/s coming out to a man through on him).
  After: 2 in 45 min (and the keepers' "moonwalks" 2 -> 0).
- A full 90 on another fixture: nothing else of note (9 players standing still for 8 s - all straight after the
  second-half kick-off).

## 9. Match stats at half time and full time
- New gameplay/match_stats.py counts, from what actually happens: shots, on target (scored or the keeper had to
  save it - "shots on target" used to count only goals), big chances (inside 12 m, no defender within 2 m, or a
  penalty), passes and pass accuracy (where the ball went next - tackles don't count), corners, fouls, cards,
  distance run (km) and the fastest anyone went (km/h).
- Shown on the half-time and full-time screens as a TV-style table with a bar per row; also in the match result
  ("stats") for later (player ratings, the papers, your "no numbers" idea).  The top bar's "shots on target" uses
  it too.
- A full real-club match: 664 v 710 passes at 86-87%, 117-120 km run, fastest 34.2 km/h (real Premier League:
  ~82-85% pass accuracy, ~105-115 km a team - so we run a little far; the record speed is 37.4 km/h).
- Doesn't change the match engine (replay hash the same as the commit before).

## 4. Reactions: appeals (3D only)
- A free kick, offside or penalty given: about two in three of the side it's given to, within 18 m of the ball,
  put an arm straight up to the referee as the whistle goes (not all at the same instant) for ~1.5 s.
- Already there from the 50-animation night: hands on head after a miss, applauding a near miss, the fouler's
  "I got the ball!", the booked man's protest, keepers on their knees when beaten, heads down when conceding.
