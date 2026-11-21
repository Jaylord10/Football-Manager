# Overnight 21-22 Nov: the Mixamo footballer, and the rest of the list

Nothing here is on Jay's PC. The Mixamo work is all on the branch `test/2026-11-21-mixamo` (built on top of
what's on the PC now). The "read the pass" experiment is on `fix/2026-11-22-read-the-pass`.

## 1. The Mixamo footballer, in the game (branch test/2026-11-21-mixamo)

**How to try it (once it's on the PC):** start a match in 3D (V) and press **P**. It swaps our own figures for
the Mixamo footballers; press P again to swap back. The game remembers which you picked for your next match.
Nothing about the football changes - only what the players look like.

What he does now:
- **Running about** - standing, jogging, running, sprinting, side-steps and running backwards come straight from
  the motion capture in your pack. They blend into each other by how fast the match has him going, and each is
  played at the speed that matches, so his feet grip the grass instead of sliding. Each man has his own way of
  standing (four idles from your pack).
- **With the ball, from the motion capture** - right-footed passes, shots and chips, headers, throw-ins, and the
  keeper's overarm throw and his kick out of his hands. Each one is lined up so his foot (or head, or hands)
  meets the ball at the moment the match engine says it does.
- **Everything else** - dives, falls after a foul, slide tackles, appeals, protests, celebrations, the keeper
  catching and holding it, left-footed kicks: he copies our own figure's move, bone by bone, and eases in and
  out of it (about a tenth of a second), so there's no snap between the two.
- **His own kit** - the club's colours and pattern (stripes, hoops, sash, halves, sleeves...), collar, shorts and
  socks, his name and number on his back, his skin tone, his hair colour, boots like our figures' (half black, the
  rest white or a bright colour). Keepers get their own kit and gloves.
- **Sleeves** (new tonight) - the same November mix as our figures: about two thirds of outfield players in short
  sleeves (bare arms, a hem in the trim colour), the rest in long sleeves, and a few of those in black gloves.
- **The officials and the touchline** (new tonight) - the referee, both assistants (flag in hand), both managers
  (in trousers) and the subs warming up are Mixamo men too. A flag or a card in a hand follows his hand.
- `broadcast3d/check.py` now also runs a Mixamo match and a live Mixamo match: **all good**.

Pictures (sent with this report):
- `mixamo_sprint_compare.jpg` - our figure and the Mixamo man sprinting, same moment.
- `mixamo_dive_compare.jpg` - a keeper's dive, ours above, the Mixamo keeper copying it below.
- `mixamo_foul_protest.png` - a foul and the protests.
- `mixamo_goal.jpg` - a goal and celebration.
- `mixamo_shot.jpg` - a shot: ours on top, the motion-captured strike underneath.
- `mixamo_officials.jpg` - the referee, an assistant with his flag, a manager.
- `mixamo_sleeves.png` - short sleeves.

**Honestly, what's still missing:**
- Only one body and one face (your pack has the one character). Skin, hair colour, height and kit vary; the face
  and build don't.
- Left-footed passes and shots copy our figure rather than using motion capture (the pack's moves are all
  right-footed except one pass; flipping a move left-to-right is a job for another night).
- The stewards, ball boys and the subs sat on the bench are still our old figures - they're small, at the edge,
  and each Mixamo man costs extra to draw.
- The pack has more we're not using yet: the keeper's catches and dives, slide tackles, the trip and falls,
  "standing up", the chest/knee/stall touches, Victory. Our copied versions of those already look right (they're
  lined up to the engine), so I left them.
- **Speed on your PC is not known yet.** See the numbers below - it's the main thing to check before it goes on.

## 2. Speed (how much harder the computer works)
(filled in below)

## 3. "Read the pass" (branch fix/2026-11-22-read-the-pass) - an experiment, not for the PC yet
The idea from your note: a receiver reads that a pass is coming and steps towards it (1.6 m) instead of waiting.
How often he reads it goes with his Anticipation (25%-95%), and how quickly. Through balls he leaves alone
(offside). In a 30-minute test, passing went 88% -> 83% for one side - not clear it helps, so I'd leave it.

## 4. Oddities sweep on what's on the PC now
(filled in below)

## 5. The numbers over 26 matches, on what's on the PC now
(filled in below)
