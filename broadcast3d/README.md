# Broadcast 3D view (prototype)

A TV-style 3D picture of a match at Kiln Lane, drawn with Panda3D from a match recorded by our own engine.

**It's completely separate from the game.** Nothing in `career/`, `gameplay/` or `rendering/` uses it - the
game still shows matches in the 2D view exactly as before. It only joins the game once Jay is happy with it,
and even then the 2D view stays as an option.

- `record.py` - plays a match in the engine and saves every player's position, facing and speed, and the
  ball, 30 times a second, to `match.json` (`python broadcast3d/record.py 120` = two minutes; uses
  `saves/career.json`, or the save named in `FM_SAVE`).
- `viewer.py` - draws it: the ground (stands, crowd, adverts, floodlights), the pitch, the players and the ball,
  the TV camera on the gantry following play, the scoreboard. `python broadcast3d/viewer.py 5700 300 out`
  renders 300 frames from frame 5700 into `out/`; `--anim` uses the animated players (`players3d.py`),
  `--live` opens a window, `--intro` adds a fly-in.
- `geom.py` - simple shapes (boxes, stands); `textures.py` - makes the textures in `tex/`.
- `match.json.gz` - a sample recorded match (Ashvale v Northwick) so the viewer works straight away.
- `models/` - Xbot / Soldier, rigged figures from the three.js examples (placeholders until proper
  footballer models).

Needs: `pip install panda3d`.

Next (from the to-do list): proper player models in kits, football animations (Mixamo), the engine telling the
view about kicks / tackles / headers, the ball at players' feet, real lighting, each club's own ground from its
profile.

Credits: the player figure is "Mannequiny" by GDQuest and contributors (https://www.gdquest.com/,
github.com/GDQuest/godot-3d-mannequin), CC-BY 4.0. Xbot is from the three.js examples.
