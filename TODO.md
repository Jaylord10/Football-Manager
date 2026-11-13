# The to-do list

How this works: Jay adds and reorders things here (or asks Claude to). Unattended / overnight sessions take
the **first unticked item under "Ready to go"**, work on it on a branch (`overnight/<date>-<topic>`), run the
checks in CLAUDE.md, push, and write a report (what changed, how it was tested, screenshots, sources). They
tick it as "done, waiting for Jay's OK" - **nothing goes onto Jay's PC or into `main` without his OK.**
Items under "Talk to Jay first" are never started unattended.

## Ready to go (agreed - work through in order)

Jay, 12 Nov: "do the cup competitions including European and world club cup; German and Italian leagues if time
allows; leave the 3D view; club photos are mine. Make the game as in depth as possible."

- [x] **End-of-season awards** - done (on Jay's PC).
- [x] **Transfers with Germany and Italy** - done (on Jay's PC).
- [x] **A long test with everything on** - done: `dev/long_all.py`. It found cup ties clashing with
      European nights (fixed: ties are moved a day or two). Clubs in the Shield play Thursday then Saturday
      (real clubs get moved to Sunday - see "Talk to Jay first").
- [x] **Club profiles**: Castleford, Millbrook, Kingsmere, Eastvale, Whitcombe, Stonecross, Lydmouth done.
      Next: Westmoor County, Riverton Dynamo, Sandmere Athletic (Whitcombe's North East derby), then the rest.
- [x] **The record books** (History tab), new club legends, broken club records, cup final details - done.
- [x] **Players' career records** (season by season, trophies, awards) - done.
- [x] **Your career as a manager** (record, reputation, bigger clubs asking for you) - done.

## Talk to Jay first (bigger decisions)

- [x] **The money balance, part 1** - done 13 Nov (on Jay's PC): the rest of a real wage bill (bonuses,
      appearance fees, NI, staff, the academy's U21s and U18s); Premier Division wages now ~60-70% of income.
- [ ] **The money balance, part 2**: AI clubs spend their spare money on transfers (the middle club's bank
      still creeps up ~£8-10m a season; small Premier Division clubs make £30-45m a year before transfers).
- [ ] **Clubs in debt** - a few Division 1 clubs run up debts of £30-50m and nothing happens to them.
      Real life: owners' money, or administration (a points deduction). Do we want that?

- [ ] **Extra time and penalty shoot-outs in the match engine** (needed for cups; the play-offs use quick ones now).
- [ ] **The broadcast 3D view** (Panda3D side project): proper player models, football animations
      (Mixamo), the engine telling the view about kicks / tackles / headers, ball at feet, real lighting.
- [ ] **Bramhall's ground expansion** - which stand could grow, once Jay's seen his pictures.
- [ ] **Thursday-Saturday**: clubs in the Continental Shield play Thursday night then the league on
      Saturday (real life moves their league game to Sunday). Needs league games on different days.
- [ ] **Northwick win nearly everything** in the 10-season test (8 titles, 5 Champions' Cups). Real life:
      Man City won 6 of 7, Real Madrid 6 Champions Leagues in 11 - so not mad, but maybe too much.
- [ ] **Naming the national stadium** (the play-off final's venue - "the National Stadium" for now).

## Waiting on Jay

- [ ] Bramhall Borough pictures: `crest.png`, `inside.jpg`, `aerial.jpg` in `data/world/clubs/bramhall/`.

## Parked (from earlier)

- [ ] Formation imbalance (some shapes too strong / weak in the engine).
- [ ] NewGAN pool face 0039.

## Done - on Jay's PC since 13 Nov (backup: `_backup_before_overnight`)

- Division 1 stage 3, the money: parachute payments, sponsors and tickets up / down, relegation wage cuts.
- Division 1 stage 4, the roll of honour: second-tier roll, old titles for Division 1 clubs, a club page for
  every club.
- Division 1 stage 5, the long test (10 seasons from a Premier Division club and from a Division 1 club):
  promoted clubs mostly finish 15th-20th and often go straight back down (realistic); both divisions keep
  their strength; nothing breaks.
- Play-off dates on the calendar; Division 1 results, play-off page and top scorers on the screens.
- The papers on promotion, relegation and the play-offs; a round-up of the other division.
- Castleford Rangers' club profile (picture prompts in the morning summary); the roll of honour tidied.
- The Association Cup and the League Cup (draws, one-off ties, two-legged semis, extra time and penalties, finals
  at the national stadium, the FA's real prize money, giant-killings in the papers).
- The Continental Champions' Cup and Shield (groups, knockouts, UEFA prize money) and the World Club Trophy.
- Germany's and Italy's leagues in the background, feeding the continental cups; an "Abroad" tab.
- End-of-season awards; transfers with Germany and Italy; big clubs rest players in early cup rounds.
- Club profiles for Millbrook United and Kingsmere City (picture prompts in the morning summary).
- Players' career records (a Career tab on every player); your own career and reputation as a manager.
- The long test with everything on (dev/long_all.py); cup ties moved off clashing dates.
- Four more club profiles (Eastvale, Whitcombe, Stonecross, Lydmouth); the History tab; new legends and
  broken records; cup finals show venue, date and scorers. Morning report with screenshots and picture prompts.
