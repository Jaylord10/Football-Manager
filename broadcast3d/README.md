# Broadcast 3D view (prototype)

A TV-style 3D picture of a match at Kiln Lane, drawn with Panda3D from a match recorded by our own engine.

**In the game (branch `live-3d`):** career matches can be watched in 3D inside the match screen -
`live.py`. The engine plays the match exactly as before; a second process draws it (half a second behind, so
kicks and shots are drawn right), and the picture goes onto the pitch area of the game's window - the score bar,
subs, half-time talk and pause stay the game's. **V** 2D / 3D (remembered), **C** camera, **Enter** skips a
goal replay (the match waits while one's on). If the 3D view can't run, the match carries on in 2D and
`live_3d.log` says why; `last_live.log` has the graphics chip and how long each picture takes. The day's light
and weather come from the date and kick-off time, the crowd from the game's crowd for the match, the play-off
final is at a national bowl.

The recordings and `viewer.py` on its own still work as before (below).

## Watching it

    pip install panda3d panda3d-gltf pillow
    python broadcast3d/viewer.py 5600 --live

opens a window and plays the sample match from frame 5600 (30 frames a second, so 5600 = about 3 minutes in;
13300 = just before the goal).
Keys: **space** pause, **left / right** back / on 10 seconds, **[ / ]** slower / faster, **1** TV camera,
**2** close camera, **Esc** quit.  `--teams=Penrith,Fernley` shows other clubs' kits; `--overcast` a grey day; `--night` an evening game under the floodlights; `--rain` Lancashire drizzle;
`--match=file.json` another recording.

Making pictures / clips instead: `python broadcast3d/viewer.py 5600 300 out` renders 300 frames into `out/`
(`--close` a close camera on the ball, `--follow=N --side` a camera on one player: 0-21 the players, then the
referee, the two assistants, the two managers and the subs).  `kitshow.py "Home" "Away" out.png` - a picture of
both sides' kits.  `check.py` - a quick check that every mode still works (day, night, rain, other grounds,
the live window).

## What's in it

- `record.py` - plays a match in the engine and saves every player's position, facing, speed and state, the
  ball, the keepers' dives, dead balls (who takes them), goal celebrations and bookings, 30 times a second
  (`python broadcast3d/record.py 120 [seed]` = two minutes; uses `saves/career.json`, or `FM_SAVE`).
- `viewer.py` - the ground (stands, a crowd that moves and goes up after a goal, adverts, dugouts, floodlights,
  corner flags), the pitch (grass you can see close up, worn goalmouths, nets that bulge), the players, the
  referee and his assistants (placed the way officials work a game: the diagonal, flags for offside, cards),
  the managers, subs on the bench and warming up, stewards and ball boys, the ball (rolling), the TV camera on
  the gantry, the scoreboard and captions (goals, bookings).  Works out from the recording who kicks, shoots,
  heads, tackles, takes a throw-in, and with which foot.
- `mhbody.py` - the footballer's body now: MakeHuman's (makehuman.org, CC0) - a properly modelled man (lean and
  muscular, ~1.80 m), his arms turned out to our skeleton's rest pose and our skeleton's joints moved onto his, his
  shirt and shorts made loose, boots on.  Writes `models/mh_body.npz` and `models/footballer_mh.glb` (needs the
  MakeHuman data: `git clone https://github.com/makehumancommunity/makehuman`, `MH_DATA=.../makehuman/data`).
- `body.py` - our own smooth body (rounded shapes melted together), kept as the fallback: `--oldbody` (or
  `FM_BODY=own`) shows it; `python broadcast3d/body.py` rebuilds `models/body.npz`.  `--pieces` the mannequin's.
- `skeleton.py` - the footballer's skeleton: the mannequin's with arms of real length (fingertips halfway down
  the thigh); writes `models/footballer.glb`.
- `players3d.py` - the players: the mannequin's skeleton with the smooth body, its kit drawn pixel by pixel by the shader (patterns,
  collars, names and numbers on the back, crests), faces and haircuts, heights, leaning into turns.
- `gait.py` - the movements built from real figures (our own jog, run and sprint - feet planted while down, the
  hip and knee angles worked out from the leg's own lengths - blended by speed; `--oldrun` the mannequin's run; side-steps and backpedalling with the feet planted: each
  foot stays put on the grass while it's down, the step cycle run at his speed; faster across or backwards, he
  turns his hips and runs): the walk (normal gait data), kicks and shots (kicking
  studies), headers, tackles, the keeper's set position, dives and getting up, throws and punts, throw-ins,
  celebrations, sitting on the bench.  Sources are in the file.
- `grounds.py` - every other club's ground built from its profile: stands on the right sides, tiers and size from
  capacity, roof types, filled-in corners or a bowl, the away fans where the profile puts them, the stand names
  on the roofs, the club's own adverts.  (`--teams=Kingsmere,Penrith` plays at The Mere.)
- `kits.py` - each club's kits from its profile, the clash rule, keepers' colours.
- `shaders/` - the lighting (a low sun with soft shadows, sky light) and the kits.
- `match.json.gz` - a sample recorded match (Ashvale v Northwick, the first 8 minutes of play: free kicks, a goal kick, throw-ins, saves, and a Northwick goal at frame 13506).

Credits: the players' bodies are made from the MakeHuman base mesh, targets and skeleton weights (MakeHuman
team, CC0 - makehuman/LICENSE.ASSETS.md).  The skeleton is "Mannequiny" by GDQuest and contributors (https://www.gdquest.com/,
github.com/GDQuest/godot-3d-mannequin), CC-BY 4.0. Xbot is from the three.js examples.

## Ideas for next (not done yet)

In the view (no engine change needed):
- The TV camera: follow the scorer during celebrations, a reverse angle / behind-the-goal replay after goals,
  a slower zoom (left alone for now, as asked).
- The grounds' special features from their profiles (viaducts, rivers, chimneys, big screens) - only Kiln Lane
  has its own so far.
- Slide tackles, shielding the ball, players pointing / calling for it, keepers organising the wall.
- Rain / mud on kits for winter games; breath in the cold under the floodlights.

Things the match engine does that the view has to cover for (to talk about - these change the engine):
- A keeper releases the ball the moment he catches it (real keepers hold it a few seconds).
- After a goal the ball goes straight back to the centre spot (the view now carries it on into the net).
- Few throw-ins (1-6 a match in the recordings against ~35 in a Premier League game - Hudl / Opta, 2023/24) and
  few goals (1 goal in 9 recorded matches; the 2024/25 Premier League had ~2.9 a game - premierleague.com).
