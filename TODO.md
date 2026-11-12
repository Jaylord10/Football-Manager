# The to-do list

How this works: Jay adds and reorders things here (or asks Claude to). Unattended / overnight sessions take
the **first unticked item under "Ready to go"**, work on it on a branch (`overnight/<date>-<topic>`), run the
checks in CLAUDE.md, push, and write a report (what changed, how it was tested, screenshots, sources). They
tick it as "done, waiting for Jay's OK" - **nothing goes onto Jay's PC or into `main` without his OK.**
Items under "Talk to Jay first" are never started unattended.

## Ready to go (agreed - work through in order)

- [ ] **Papers and media for promotion, relegation and the play-offs** - previews, reports, "back in the big time".
- [ ] **Club profiles for the other 37 clubs** - history, location, ground, honours that match the roll,
      image prompts (Jay makes the pictures). One club per report, starting with Castleford Rangers
      (Northwick's derby rivals), then Millbrook United and Kingsmere City.

## Talk to Jay first (bigger decisions)

- [ ] **The money balance** (found by the long test - it was already like this before Division 1): Premier
      Division wage bills are only ~25-30% of income (real Premier League: ~60-70%), so clubs pile up cash -
      the median bank balance goes from ~£100m to ~£280m in 10 seasons. Options: bigger wage bills, higher
      running costs, AI clubs spending more on transfers.
- [ ] **Clubs in debt** - a few Division 1 clubs run up debts of £30-50m and nothing happens to them.
      Real life: owners' money, or administration (a points deduction). Do we want that?

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

## Done (waiting for Jay's OK) - all on branch `overnight/2026-11-12-division1`

- Division 1 stage 3, the money: parachute payments, sponsors and tickets up / down, relegation wage cuts.
- Division 1 stage 4, the roll of honour: second-tier roll, old titles for Division 1 clubs, a club page for
  every club.
- Division 1 stage 5, the long test (10 seasons from a Premier Division club and from a Division 1 club):
  promoted clubs mostly finish 15th-20th and often go straight back down (realistic); both divisions keep
  their strength; nothing breaks.
- Play-off dates on the calendar; Division 1 results, play-off page and top scorers on the screens.
