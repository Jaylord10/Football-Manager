# Live 3D match view — overnight log (branch live-3d)

## Built (16 Nov evening)
- broadcast3d/live.py: the 3D view in its own process, fed by the engine every 1/30 s of football; picture into
  shared memory; the game blits it into the pitch area. 0.5 s behind the engine; score bar matches the picture.
- Engine waits during goal replays (Enter skips). V switches 2D/3D (remembered per career). C = camera.
- Falls back to 2D if the 3D fails (broadcast3d/live_3d.log says why).
- Subs: the new man (name, number 12+, own face/build) appears when the picture reaches the change.
- Sent off: walks off to the tunnel instead of vanishing.
- Banners (FOUL!) at the moment the picture shows; TV caption for bookings instead of the 2D card flash.
- Captions use the engine's minute; sweat by minute.
- At half-time / full-time the camera frames the pitch (it was pointing at the ball off the pitch).
- Gantry close-ups leave the near side of the ground out (a scorer by the near corner flag was hidden by a stand).
- Team sheets for the first 6 seconds.
- Key bar / bottom bar say the 3D keys.
- Smooth: drawn between recorded frames (any frame rate).
- Camera spring in small steps (at 16x it blew up: crash -> 2D fallback worked; fixed).
- Light and weather from the date and kick-off: evening = floodlights; 3pm Nov-Jan = dull + floodlights;
  rain ~1 in 4 matches Oct-Feb, 1 in 6 otherwise.
  Sources: timeanddate.com Manchester sunsets (~15:50 in December); Met Office Woodford averages 1991-2020
  (~15 rain days/month Oct-Jan, 11-14 otherwise).
- Textures saved whole-or-nothing (a half-written pitch picture broke a start).

## Checks
- replay hash 50d079570600bcab322bbb19be341bb2 (unchanged)
- all_screens: only arrange/bid/choose/loan/talks (expected)
- season2: ok
- broadcast3d/check.py: all good
- live flows: kick-off -> half-time -> goal + replay -> full time, at 8x.

## Night 2 (16-17 Nov, unattended)

### 1. Players' bodies bent by the graphics card (GPU skinning) - KEPT
- Before, every frame the processor moved every point of every player's body (14,000 points each, ~40 people
  on screen counting subs, stewards and officials) onto his skeleton.  Now the graphics card does it in the
  lighting shader (shaders/lit.vert) and in the sun's shadow picture (sunshadow.py: the players carry a
  "skin" tag and get their own skinned depth shader).  The processor only works out the 45 joints per man.
- `FM_GPUSKIN=0` (or `--cpuskin`) puts it back the old way, in case a graphics chip doesn't like it.
- Tested: pictures before/after (viewer.py 6000, a close side-on follow of the keeper at 6260, the kit
  picture) - the same to the eye; at most ~130 of 921,600 pixels differ, by idle-sway rounding.
  broadcast3d/check.py: all good.  Frame time on this test machine (software drawing, so the "card" is the
  processor too): 142 -> 133 ms; on a real graphics chip the card does this work almost for free, so the
  saving there is bigger.

### 2. Replay angles - DONE
- `viewer.replay_angle(F, g)` works back from the goal to where the shot was hit (the ball flying towards the
  goal, fast) and where the ball was 1.5 s before that.  Shot from wider than 12 m off the middle, or a ball
  from the wing (over 22 m out) just before: a SIDE-ON replay - a camera on the near touchline level with the
  edge of the box, 7 m up, panning with the ball on a long lens (about 28 m of pitch across the picture).
  Otherwise (a central shot): BEHIND THE GOAL as before.  Both the stand-alone viewer and the live view use it.
  `--replay=side` / `--replay=goal` forces one, for checking.
- Why: that's how TV directors cut replays - an angle that shows what the wide shot doesn't: from the side for
  crosses and angled finishes (you see the ball come across and the run), from behind the goal for shots from
  the middle (you see the shot's line and the keeper).
- Tested: the sample goal (a central shot from ~8 m off the middle -> behind the goal, as before) and the same
  goal forced side-on; 470 frames each, pictures looked at.

### 3. Penalty shoot-out camera - DONE
- During a shoot-out (frames with state "penalties") the TV camera stands behind the taker: 15 m behind the
  spot, 3.2 m up, a touch off the middle, looking down the line of the kick - the taker, the ball on the spot,
  the keeper and the whole goal in the picture, with a slight hand-held breathing.  C (the close camera) still
  overrides it.
- `dev/record_pens.py <copy of game> out.json [seconds]` records a shoot-out (a career match set up as a
  knockout, straight to penalties) for checking; viewed with `viewer.py 40 160 out --match=out.json`.
- Tested: a 10-kick shoot-out recorded and drawn; pictures looked at.

### 4. Half-time stats card - DONE
- When the picture reaches half-time (or the half-time of extra time), the 3D view puts up the TV stats card
  (possession, shots, passes, tackles won, headers, fouls suffered, worked out from the match so far) with a
  "HALF-TIME  WES 0 - 0 NOR" band on top.  In the game it sits to the right, clear of the game's own
  "HALF TIME / score / 2nd half starting shortly" in the middle; when your half-time talk panel is up it's
  behind it, and there once it's gone.  It goes when the second half starts.
- Team sheets still up at half-time (only in very short test halves) are taken down first.
- A club in black shirts gets its trim colour for the bar on the card (a black bar didn't show).
- dev/live3d_flow.py now also saves a picture a second after the PICTURE's own state changes
  (`_shown_halftime<n>.png` etc.), as well as the engine's.
- Tested: live flows (NOHUMAN=1 HALF=40, 8x) - card shows at half-time, gone in the second half;
  `viewer.py 9000 1 out --stats --ht` for a still.

### 5. Gantry close-up by the near corner flag - FIXED
- Re-checked with the sample goal's celebration moved to each near corner (dev/corner_celebration.py), at Kiln
  Lane, The Mere (Kingsmere) and Northwick's bowl.  The near stand no longer blocks it (the clip from last
  night works), BUT the camera stopped panning 9 m short of the corner flag, so the scorer was squashed into
  the edge of the picture (half cut off at the far left/right).  The close-up can now pan right to the flag
  (2 m in from the goal line), so he's framed properly.  The dark strip along the bottom of those close-ups is
  the back of the near advertising boards - which is what you see from a real gantry too.
- Tested: 3 grounds x both corners, pictures looked at.

### 6. Crowd: people the right width - DONE (found while checking the shoot-out camera)
- Close up (the shoot-out camera, replays from behind the goal) the fans were thin vertical streaks: one crowd
  picture (about 80 fans across) was stretched over only 14 m of stand, so each fan was ~0.17 m wide but a
  whole row (~0.6 m) tall.  Now one picture covers 36 m: a fan every ~0.45 m, the width of a real seat (Green
  Guide - the Guide to Safety at Sports Grounds, 6th edition, section 12.6: seats at least 0.46 m wide, 0.5 m
  recommended), and the people are as wide as they are tall in the picture, so they look like people.
- Tested: the TV view (looks the same from the gantry - a touch chunkier, as a real crowd), and the shoot-out
  view before/after (picture: crowd_before_after.png).
