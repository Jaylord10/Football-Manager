# The to-do list

How this works: Jay adds and reorders things here (or asks Claude to). Unattended / overnight sessions take
the **first unticked item under "Ready to go"**, work on it on a branch (`overnight/<date>-<topic>`), run the
checks in CLAUDE.md, push, and write a report (what changed, how it was tested, screenshots, sources). They
tick it as "done, waiting for Jay's OK" - **nothing goes onto Jay's PC or into `main` without his OK.**
Items under "Talk to Jay first" are never started unattended.

## Ready to go (agreed - work through in order)

- [ ] **Division 1 stage 5: the long test** - 10+ seasons from a Premier Division club and a Division 1 club:
      money, squads, crowds and strength of both divisions stay sensible; yo-yo clubs; fix what's off.
- [ ] **Play-offs in the calendar and fixtures screens** - show your play-off dates and results there too.
- [ ] **Division 1 results and top scorers** - a results / scorers view for the other division (like Spain's).
- [ ] **Papers and media for promotion, relegation and the play-offs** - previews, reports, "back in the big time".
- [ ] **Club profiles for the other 37 clubs** - history, location, ground, honours that match the roll,
      image prompts (Jay makes the pictures). One club per report, starting with Castleford Rangers
      (Northwick's derby rivals), then Millbrook United and Kingsmere City.

## Talk to Jay first (bigger decisions)

- [ ] **Cup competitions** - the Association Cup and League Cup are in the history but not in the game yet
      (knockout rounds, replays or not, extra time and penalties in the match engine).
- [ ] **European competitions** - the Continental Champions' Cup and Shield.
- [ ] **Extra time and penalty shoot-outs in the match engine** (needed for cups; the play-offs use quick ones now).
- [ ] **The broadcast 3D view** (Panda3D side project): proper player models, football animations
      (Mixamo), the engine telling the view about kicks / tackles / headers, ball at feet, real lighting.
- [ ] **Bramhall's ground expansion** - which stand could grow, once Jay's seen his pictures.
- [ ] **Naming the national stadium** (the play-off final's venue - "the National Stadium" for now).

## Waiting on Jay

- [ ] Bramhall Borough pictures: `crest.png`, `inside.jpg`, `aerial.jpg` in `data/world/clubs/bramhall/`.

## Parked (from earlier)

- [ ] Formation imbalance (some shapes too strong / weak in the engine).
- [ ] NewGAN pool face 0039.

## Done (waiting for Jay's OK)

- Division 1 stage 3, the money (branch `overnight/2026-11-12-division1`).
- Division 1 stage 4, the roll of honour (same branch).
