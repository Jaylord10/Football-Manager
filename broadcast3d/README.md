# Broadcast 3D view (prototype)

A TV-style 3D picture of a match at Kiln Lane, drawn with Panda3D from a match recorded by our own engine.

**It's completely separate from the game.** Nothing in `career/`, `gameplay/` or `rendering/` uses it - the
game still shows matches in the 2D view exactly as before. It only joins the game once Jay is happy with it,
and even then the 2D view stays as an option.

## Watching it

    pip install panda3d panda3d-gltf pillow
    python broadcast3d/viewer.py 5600 --live

opens a window and plays the sample match from frame 5600 (30 frames a second, so 5600 = about 3 minutes in).
Keys: **space** pause, **left / right** back / on 10 seconds, **[ / ]** slower / faster, **1** TV camera,
**2** close camera, **Esc** quit.  `--teams=Penrith,Fernley` shows other clubs' kits; `--overcast` a grey day;
`--match=file.json` another recording.

Making pictures / clips instead: `python broadcast3d/viewer.py 5600 300 out` renders 300 frames into `out/`
(`--close` a close camera on the ball, `--follow=N --side` a camera on one player: 0-21 the players, then the
referee, the two assistants, the two managers and the subs).  `kitshow.py "Home" "Away" out.png` - a picture of
both sides' kits.

## What's in it

- `record.py` - plays a match in the engine and saves every player's position, facing, speed and state, the
  ball, the keepers' dives, dead balls (who takes them) and goal celebrations, 30 times a second
  (`python broadcast3d/record.py 120 [seed]` = two minutes; uses `saves/career.json`, or `FM_SAVE`).
- `viewer.py` - the ground (stands, a crowd that moves and goes up after a goal, adverts, dugouts, floodlights),
  the pitch (grass you can see close up, nets that bulge), the players, the referee and his assistants
  (placed the way officials work a game), the managers and the subs, the ball (rolling), the TV camera on the
  gantry, the scoreboard.  Works out from the recording who kicks, shoots, heads, tackles, takes a throw-in,
  and with which foot.
- `players3d.py` - the players: the mannequin figure, its kit drawn pixel by pixel by the shader (patterns,
  collars, names and numbers on the back, crests), faces and haircuts, heights, leaning into turns.
- `gait.py` - the movements built from real figures: the walk (normal gait data), kicks and shots (kicking
  studies), headers, tackles, the keeper's set position, dives and getting up, throws and punts, throw-ins,
  celebrations, sitting on the bench.  Sources are in the file.
- `kits.py` - each club's kits from its profile, the clash rule, keepers' colours.
- `shaders/` - the lighting (a low sun with soft shadows, sky light) and the kits.
- `match.json.gz` - a sample recorded match (Ashvale v Northwick).

Credits: the player figure is "Mannequiny" by GDQuest and contributors (https://www.gdquest.com/,
github.com/GDQuest/godot-3d-mannequin), CC-BY 4.0. Xbot is from the three.js examples.
