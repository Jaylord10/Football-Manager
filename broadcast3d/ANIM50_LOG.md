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
- 33-38 Keepers: a split step (a little hop onto both feet) as the shot is struck; catching it - hands out
  behind the ball, then pulled into the chest; holding it tucked into his chest (it used to sit between his
  hanging hands); long throws overarm, the ball in his right hand behind his head (short ones still rolled);
  pointing to set up the wall at free kicks near his goal; beaten - down on his knees, a slap of the grass.
  (Goal kicks: the step-back and run-up above.)
- 44 Celebrations: scorers who don't knee-slide now finish with their own - kissing the badge, or a hand cupped
  to the crowd.
- 46 A near miss: a team-mate nearby applauds the effort, hands together over his head (about half the time).
- 48 Full time: shaking hands with the opponent next to him in the centre circle.
- 49 The referee's whistle: hand to his mouth when he gives a free kick, then he points which way.
  (No "advantage" signal: the match engine doesn't play advantage.)
- 15/16 Closing the man on the ball down: within 3.5 m and not sprinting, a defender jockeys - low, knees
  bent, side-on, arms out a little, eyes on the ball.
- 27 Running shoulder to shoulder with an opponent: they lean into each other.
- 30 Chasing a man from just behind: about a third of players reach out for his shirt.
- 43 Corners: players marking each other in the box jostle, arms out, holding their ground.
- 25 Headers: the nearest opponent within 2 m goes up with him.
- 26 A header glanced on behind him is a flick-on (head back), not a header driven through.
- 7/8 Volleys (the ball struck at knee to hip height), and chest and thigh control for a dropping ball.  Rare:
  this match engine nearly always plays the ball on the ground (none in the 15-minute sample).
- 9/10 Step-overs: the trickier half of players throw one in running at a defender 2-4 m in front (one every
  few seconds at most), the body dipping to sell it.

## Already there before tonight
- 12 Shot follow-through landing on the kicking foot; 13 leaning into bends; 14 leaning forward when setting
  off, back when braking; 2 the plant foot beside the ball (the instep kick); 24 headers with a proper
  jump (crouch, spring off both feet, arms up, land on bent knees); 45 heads down / hands on knees when they concede; 29 getting up after a sliding tackle (the slide ends kneeling, then up); 50 assistants side-stepping
  along the line level with the second-last defender (they sprint when they must).
