# The 50 player-animation improvements (overnight 17-18 Nov) - branch anim-50

3D picture only: the match engine is untouched (replay hash stays 50d07957...).  Each item checked with close-up
strips from a recorded match (scratch tool: find the moment, follow the player, a picture every 0.1 s).

## Done
- 3/4/5/6 Kicks by how the ball left him (viewer._kick_kind): short or across his body - a side-foot pass with
  the inside of the foot (the other foot when it goes across him); rising fast - a lofted ball, leaning back;
  back and out to the side - a flick with the outside of the foot; behind him - a back-heel, the ball drawn
  under his heel as he plays it.  (Levanon & Dapena 1998 on the side-foot pass.)  In a 15-minute sample:
  90 instep kicks, 84 side-foot passes, 18 back-heels, 13 flicks, 5 lofted.
- 28 Losing the ball in a tackle: a stumble - a lurch forward, arms flung out, a step to stay up.
- 31 About 1 in 3 fouled players stay down hurt: drop back onto the grass holding the shin, knee pulled up, for
  ~3 s, then sit up, crouch and get up.  (The rest: the fall from earlier tonight.)
- 32 The man who gave the foul away: "I got the ball!" - both hands up, then a shrug.
- 39/40/41/36 Set pieces: the taker puts the ball down, walks back a few paces facing where it's going
  (corner 2 m, free kick 2.4 m, penalty 2.6 m, goal kick 3 m), and runs up to it as he takes it - a penalty with
  a stutter.  Corners and free kicks out wide: an arm up first.  (The engine keeps the taker on the ball; this
  is drawn only.)
- 42 The wall jumps as the free kick is struck (knees tucked, hands still crossed).
- Fixed on the way: the wall's arms came out to the sides (now crossed in front), and the booked player's
  protest held his arms straight out like a scarecrow (now hands up, elbows bent).

## Already there before tonight
- 12 Shot follow-through landing on the kicking foot; 13 leaning into bends; 14 leaning forward when setting
  off, back when braking; 29 getting up after a sliding tackle (the slide ends kneeling, then up).
