# Overnight report - live 3D (night of 16-17 November)

Morning pal - here's what I did on the 3D match view while you were asleep. **It's all on the separate
`live-3d` branch. Nothing has gone onto your PC and nothing is on `main`.** The picture sheet is
`broadcast3d/overnight_sheet.png`.

## What changed
1. **Lighter work for your computer** - the players' bodies are now bent into shape by the graphics card
   instead of the main processor (about 40 bodies, 14,000 points each, every picture). Pictures look the same
   (I compared them pixel by pixel). If your laptop's graphics ever don't like it, `FM_GPUSKIN=0` puts it back
   the old way.
2. **Replay angles** - a goal from out wide (a cross or an angled shot) is now replayed side-on, from a camera
   on the touchline level with the edge of the box; a shot from the middle is still replayed from behind the goal.
3. **Penalty shoot-out camera** - behind the taker, looking at the keeper and the goal, like on TV.
4. **Half-time stats card** - possession, shots, passes, tackles, headers, fouls, with the score, shown at
   half-time to the right of the game's own "HALF TIME" message (behind your team-talk panel when that's up).
5. **Goal close-ups by the near corner flag** - the stand doesn't block it, and the camera now pans right to
   the flag (before, the scorer was half out of the picture).
6. **Crowd close up** - fans were thin streaks (squeezed to a third of their width); now each fan is the width
   of a real seat (Green Guide: 0.46-0.5 m).
7. **Night games** - players were dark silhouettes under the floodlights; now they're lit from all four
   corners, as real stadium lights are designed to do for TV (UEFA Stadium Lighting Guide 2023).

## How it was tested
- Match engine replay unchanged: hash 50d079570600bcab322bbb19be341bb2.
- Every screen draws (only arrange / bid / choose / loan / talks "fail", as expected).
- Two seasons run fine (`season2.py`), tables and money sensible.
- `broadcast3d/check.py`: all good (day, night, rain, other grounds, the live window...).
- Live test matches inside the game at 8x: a full 90 minutes (kick-off, half-time, subs, full time) and short
  ones to check the half-time card. A shoot-out was recorded and drawn to check that camera.

## Things for you to decide (they'd change the match engine, so I didn't touch them)
- Keepers let go of the ball the moment they catch it (real keepers hold it a few seconds).
- Corners, subs walking on, and the ball running ahead of dribblers - as before.
- In the shoot-out the ball sometimes flies before the taker's foot reaches it, and the keeper can stand
  still while it goes in (the engine's timing of the kick and the dive).
- The 3D picture's possession figure can differ by a point from the game's own bar (they're counted
  slightly differently).

Full details and sources: `broadcast3d/LIVE3D_LOG.md`.
