# Football Manager (Jay's game)

A football management game in Python and pygame. The career mode (`career/`) runs a 40-club English world
(Premier Division + Division 1, promotion / relegation / play-offs), a background Spanish league, transfers,
contracts, finances, morale, media, club profiles and stadiums. The match engine (`gameplay/`, `core/`, `ai/`,
`roles/`, `config/`) plays every league match.

Jay plays it on his PC at `C:\Users\mjalm\Desktop\Football Manager`. **This repository's `main` branch is
meant to match what's deployed on his PC.** Work happens on branches.

## How Jay likes to work (follow these)

- **One change at a time.** Discuss big items with him before starting them.
- **Test, then report with screenshots** before anything goes onto his PC.
- **Never deploy (or merge to `main`) without his OK.** Overnight / unattended work goes on a branch
  (e.g. `overnight/<date>-<topic>`), with a short report of what changed and how it was tested.
- Back up before deploying: on his PC, the files being replaced go to `_backup_before_<name>` (check the
  name is free first).
- **Honest, real-world grounding**: when tuning anything (money, crowds, ages, attributes, tactics), use real
  football figures and cite sources in the report.
- He's not a programmer: explain things in plain words, no jargon. British English, friendly ("pal").
- He usually stops around 22:30 UK time.

## Must-pass checks before reporting any change

1. **Match engine replay is unchanged** (unless the change is meant to touch the engine):
   `python dev/replay.py . 1 60` must end with `hash 50d079570600bcab322bbb19be341bb2`.
2. **Every screen still draws**: `python dev/all_screens.py` (with `FM_GAME` = the game folder). The screens
   `arrange`, `bid`, `choose`, `loan` and `talks` "fail" there because they need setting up first - that's
   expected; anything else failing is a bug.
3. **Seasons run**: `python dev/season2.py . 2` (fake results, both divisions, money, promotion) - no errors,
   tables and finances sensible.
4. For anything touching match days: a real-engine flow, `dev/flow_d1.py` (copy the game to a scratch folder
   and point `FM_FLOW` at it - it writes saves).

Screenshots: `dev/shot.py` builds a mid-season career and saves screens to `$FM_OUT/shots` (default
`/tmp/fm_dev`). Note `dev/season.py` changes folder after loading the world, so `shot.py` clears the club-profile
cache - keep that line.

## Code map (career mode)

- `career/league.py` - fixtures, tables (per division), save/load, the summer (`new_season`).
- `career/divisions.py` - the two divisions: `club["league"]` is `"pl"` (Premier Division) or `"d1"`;
  ids 0-19 started in the Premier Division, 20-39 in Division 1 (`career["clubs"][id]`, ids never change).
  Your division is `career["fixtures"]/["results"]` (match engine); the other division is
  `career["other"]` (quick results, same calendar). Promotion / relegation in `movers` / `promote`.
- `career/playoffs.py` - Division 1 play-offs (two-legged semis, final at the national stadium).
- `career/spain.py` - the Spanish league (quick results, via a career "view"). Ids 100-119.
- `career/finance.py` - money by league (`LEAGUE["pl" | "d1" | "es"]`), real figures in the notes.
- `career/clubinfo.py` + `data/world/clubs/<short>.json` - club profiles (history, honours, ground, image
  prompts). Ashvale, Northwick and Bramhall have them; their honours years are fixed - never change them.
- `data/world/honours.json` - the roll of honour, built by `dev/make_roll.py` (asserts Ashvale's years).
- `career/ui.py` - every screen (`draw_<screen>`), `career/office.py` - the office picture hub.
- Faces: `faces/newgan` (3,000 NewGAN faces, 128px) - `career/faces.py`. The big NewGAN pack and
  `faces/photos` stay on Jay's PC only.

## Not in this repository

Jay's saves, the `_backup_*` folders, the full NewGAN pack, `faces/photos`, and his picture work folders.
