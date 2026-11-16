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
