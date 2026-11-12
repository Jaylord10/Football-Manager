# The to-do list

How this works: Jay adds and reorders things here (or asks Claude to). Unattended / overnight sessions take
the **first unticked item under "Ready to go"**, work on it on a branch (`overnight/<date>-<topic>`), run the
checks in CLAUDE.md, push, and write a report (what changed, how it was tested, screenshots, sources). They
tick it as "done, waiting for Jay's OK" - **nothing goes onto Jay's PC or into `main` without his OK.**
Items under "Talk to Jay first" are never started unattended.

## Ready to go (agreed - work through in order)

Jay, 12 Nov: "do the cup competitions including European and world club cup; German and Italian leagues if time
allows; leave the 3D view; club photos are mine. Make the game as in depth as possible."

- [ ] **The Association Cup** (FA Cup): 40 clubs + lower-league sides from the third round (early January), one-off
      ties, extra time and penalties, semi-finals and final at the national stadium; prize money (FA's real figures).
- [ ] **The League Cup**: midweek rounds from August, two-legged semi-finals, a final at the national stadium.
- [ ] **The Continental Champions' Cup and Continental Shield**: groups, two-legged knockouts, a final; places from
      the league (and the cups); UEFA-style prize money.
- [ ] **The World Club Trophy**: Europe's champions v South America's champions.
- [ ] **German and Italian leagues** in the background (like Spain).

- [ ] **Club profiles for the other clubs** - history, location, ground, honours that match the roll,
      image prompts (Jay makes the pictures). Castleford Rangers done; next Millbrook United and Kingsmere City.

## Talk to Jay first (bigger decisions)

- [ ] **The money balance** (found by the long test - it was already like this before Division 1): Premier
      Division wage bills are only ~25-30% of income (real Premier League: ~60-70%), so clubs pile up cash -
      the median bank balance goes from ~£100m to ~£280m in 10 seasons. Options: bigger wage bills, higher
      running costs, AI clubs spending more on transfers.
- [ ] **Clubs in debt** - a few Division 1 clubs run up debts of £30-50m and nothing happens to them.
      Real life: owners' money, or administration (a points deduction). Do we want that?

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
- The papers on promotion, relegation and the play-offs; a round-up of the other division.
- Castleford Rangers' club profile (picture prompts in the morning summary); the roll of honour tidied.
