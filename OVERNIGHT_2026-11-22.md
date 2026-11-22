# Overnight 21-22 Nov: the Mixamo footballer, and the rest of the list

Nothing here is on Jay's PC. The Mixamo work is all on the branch `test/2026-11-21-mixamo` (built on top of
what's on the PC now). A keeper fix the sweep turned up is on `fix/2026-11-22-keeper-shuffle`. The "read the
pass" experiment is on `fix/2026-11-22-read-the-pass`.

## 1. The Mixamo footballer, in the game (branch test/2026-11-21-mixamo)

**How to try it (once it's on the PC):** start a match in 3D (V) and press **P**. It swaps our own figures for
the Mixamo footballers; press P again to swap back. The game remembers which you picked for your next match.
Nothing about the football changes - only what the players look like.

What he does now:
- **Running about** - standing, jogging, running, sprinting, side-steps and running backwards come straight from
  the motion capture in your pack. They blend into each other by how fast the match has him going, and each is
  played at the speed that matches, so his feet grip the grass instead of sliding. Each man has his own way of
  standing (four idles from your pack). Keepers have their own stance and side-step across their goal (the
  pack's keeper idle and sidestep).
- **With the ball, from the motion capture** - passes, shots and chips (left-footed ones use the same moves
  mirrored), headers, throw-ins, and the keeper's overarm throw and his kick out of his hands. Each one is lined
  up so his foot (or head, or hands) meets the ball at the moment the match engine says it does, and a ball he's
  holding sits in his own hands.
- **Everything else** - dives, falls after a foul, slide tackles, appeals, protests, celebrations, the keeper
  catching and holding it: he copies our own figure's move, bone by bone, and eases in and
  out of it (about a tenth of a second), so there's no snap between the two.
- **His own kit** - the club's colours and pattern (stripes, hoops, sash, halves, sleeves...), collar, shorts and
  socks, his name and number on his back, his skin tone, his hair colour, boots like our figures' (half black, the
  rest white or a bright colour). Keepers get their own kit and gloves.
- **Sleeves** (new tonight) - the same November mix as our figures: about two thirds of outfield players in short
  sleeves (bare arms, a hem in the trim colour), the rest in long sleeves, and a few of those in black gloves.
- **The officials and the touchline** (new tonight) - the referee, both assistants (flag in hand), both managers
  (in trousers) and the subs warming up are Mixamo men too. A flag or a card in a hand follows his hand.
- Checks: `broadcast3d/check.py` (now also a Mixamo match and a live Mixamo match) **all good**; every screen draws
  (only the five that need setting up "fail", as always); two seasons run fine. The match engine isn't touched
  (P only changes the picture).

Pictures (sent with this report):
- `mixamo_sprint_compare.jpg` - our figure and the Mixamo man sprinting, same moment.
- `mixamo_dive_compare.jpg` - a keeper's dive, ours above, the Mixamo keeper copying it below.
- `mixamo_foul_protest.png` - a foul and the protests.
- `mixamo_goal.jpg` - a goal and celebration.
- `mixamo_shot.jpg` - a shot: ours on top, the motion-captured strike underneath.
- `mixamo_throwin.jpg` - a throw-in, ours on top, the motion-captured one underneath.
- `mixamo_leftfoot.jpg` - a left-footed strike (the move mirrored).
- `mixamo_officials.jpg` - the referee, an assistant with his flag, a manager.
- `mixamo_sleeves.png` - short sleeves.
- `mixamo_goal_clip.mp4` - 7 seconds of the TV view: a goal, with everyone as Mixamo men.

**Honestly, what's still missing:**
- Only one body and one face (your pack has the one character). Skin, hair colour, height and kit vary; the face
  and build don't.
- The stewards, ball boys and the subs sat on the bench are still our old figures - they're small, at the edge,
  and each Mixamo man costs extra to draw.
- The pack has more we're not using yet: the keeper's catches and dives, slide tackles, the trip and falls,
  "standing up", the chest/knee/stall touches, Victory. Our copied versions of those already look right (they're
  lined up to the engine), so I left them.
- **Speed on your PC is not known yet.** See the numbers below - it's the main thing to check before it goes on.

## 2. Speed (how much harder the computer works)
- The Mixamo men's own sums (31 of them: 22 players, the officials, managers and warm-up subs) took 21 thousandths
  of a second a frame at first. I cut that to **6 thousandths** - he now plays the motion capture himself and only
  does the copying sums while he's doing one of our moves. Your graphics card does the bending of his body.
- Drawing here (no graphics card - everything done the slow way) took about 1.9 times as long per frame as our
  figures, before that cut. That's not what your PC will see, but it does say: **try it on your PC before it goes
  in for good**. If it stutters, the fix is to keep the officials and warm-up subs as our figures, or only use
  Mixamo men in the TV view.

## 3. "Read the pass" (branch fix/2026-11-22-read-the-pass) - an experiment, not for the PC yet
The idea from your note: a receiver reads that a pass is coming and steps towards it (1.6 m) instead of waiting.
How often he reads it goes with his Anticipation (25%-95%), and how quickly. Through balls he leaves alone
(offside). In a 30-minute test, passing went 88% -> 83% for one side - not clear it helps, so I'd leave it.

## 4. Oddities sweep on what's on the PC now, and a keeper fix (branch fix/2026-11-22-keeper-shuffle)
Three full matches on what's on your PC, looking for anything that would look odd on screen. Outfield players
were clean (one striker standing still 8 seconds, once). The keepers weren't:
- **Jitter** - 13 times in 3 matches, all keepers: darting back and forth. Cause: a keeper ran at full speed
  (6.5 m/s) right up to his spot, and his spot creeps 10-20 cm as play moves, so he'd dash, stop, dash the other
  way. Now he eases off as he gets there, the same way outfield players do - a small adjustment is a gentle
  shuffle.
- Also: when a keeper and a defender would reach a loose ball at almost the same moment, the job swapped between
  them every frame, so the keeper went out-back-out-back. Now whoever's going keeps going unless a team-mate
  would clearly get there sooner (a quarter of a second). This applies to everyone, not just keepers.
- **Moonwalk** - 3 times: a keeper running backwards to his goal at full speed. Now, hurrying back (over
  3.5 m/s), he turns and runs.
- Same 3 matches after the fix: **jitters 13 -> 1, moonwalks 3 -> 0**.
- This one does change the match engine (the replay check changes, as it should). Checks: the real-engine
  match-day flow runs fine. The 26-match numbers for it are running now - in the next section if they finish.

## 5. The numbers over 26 matches, on what's on the PC now
| | before the keeper / support-run / squeeze changes | now (on your PC) |
|---|---|---|
| goals a match | 2.96 | **3.92** |
| shots a match | 18.5 | 21.3 |
| open-play shots from outside the box | 25% | 26% |
| open-play shots scored | 14.8% | 16.2% |

Real Premier League: 2.87 goals a match in 2024/25 (1,091 in 380 games) and 3.28 in 2023/24 (1,246). So we're now
about one goal a match too many. Mostly it's the keepers: since the dives became realistic (committed, can't
change direction), they save less. You said leave the numbers until the movement and marking are right, so I've
left it - but it's the first thing to tune when we get to numbers (likely the keeper's reactions and where he
stands, not the dive itself). Source: premierleague.com, "The 2024/25 Premier League season in numbers".
