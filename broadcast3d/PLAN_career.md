# Watching your own career matches in 3D: the plan (to talk through with Jay)

Nothing in here is built yet. It's the plan only.

## How a match day works now
- Your match plays in the 2D window (the match engine draws it with pygame). You can pause, make subs and change tactics.
- Everyone else's matches play without a picture, in the background.
- The 3D view (`broadcast3d/`) is separate. It plays a **recording**: every player's position, facing and speed, the ball, and who takes each dead ball, 30 times a second (`record.py`).

## Three ways to bring them together, from easiest to hardest

### A. "Watch it again in 3D" after the match (small, safe)
- While your match plays in 2D, the engine also writes the recording, which costs almost nothing.
- At full time a **"Watch in 3D"** button opens the 3D viewer on that match, either the whole game or just the goals and big chances (highlights).
- The engine and the 2D match stay exactly as they are, and the 3D view only reads the recording.
- **Size:** a match is about 2–3 MB as a recording, kept for your last few matches only.

### B. Choose 2D or 3D before kick-off: the match plays in 3D (medium)
- The engine runs inside the 3D window instead of the pygame one, and the 3D view draws each moment as it happens.
- **Needs:** the touchline controls (pause, subs, tactics, shouts) rebuilt for the 3D window, or a key that flips back to the 2D screen to make changes and then returns.
- **Speed:** both the engine and the 3D picture have to keep up 60 times a second on your laptop, so we'd measure first.

### C. 3D highlights for the other matches (later)
- The other matches play without a picture, so the same recording could give goals from around the league for a "Match of the Day" show.

## My suggestion
- **A first:** it's quick, can't break the game, and lets you see your own matches in 3D straight away.
- **B next:** once we know how fast the 3D view runs on your laptop (the `Watch 3D match.bat` launcher shows that).
- **Your choice:** A could go on its own branch for you to try, if you'd like.
