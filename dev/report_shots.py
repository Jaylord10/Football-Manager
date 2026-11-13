"""report_shots.py -> one season with fake league results (everything else played by the game), with
screenshots along the way for the morning report: the cups and Europe in spring, abroad, the season's end,
the awards.  Saved to $FM_OUT/shots/rep_*.png."""
import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
GAME = _os.environ.get("FM_GAME", _os.path.dirname(DEV))
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")
import os, sys
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("MYCLUB", "0")
src = open(_os.path.join(DEV, "season2.py")).read().split("for season in range(N):")[0]
sys.argv = [sys.argv[0], GAME, "1"]
exec(src)
import pygame
from career import ui, clubinfo, cups
clubinfo._PROFILES.clear(); clubinfo._IMG.clear()
_save = league.save
league.save = lambda *a, **k: None
app = ui.App(); app.career = c
OUT = _os.path.join(OUTDIR, "shots"); os.makedirs(OUT, exist_ok=True)
def shot(name):
    app.win.fill(ui.BG); app.buttons = []
    getattr(app, "draw_" + app.screen)()
    for b in app.buttons: b.draw(app.win, app.fonts, (0, 0))
    pygame.image.save(app.win, f"{OUT}/rep_{name}.png")
def play(md):
    league.advance_to_match(c)
    res = []
    for h, a in c["fixtures"][md - 1]:
        players, goals = [], []
        sh, sa = strength(c["clubs"][h]), strength(c["clubs"][a])
        hg, ag = poisson(1.45 * 1.08 ** (sh - sa)), poisson(1.2 * 1.08 ** (sa - sh))
        for side, cid, n in ((0, h, hg), (1, a, ag)):
            club = c["clubs"][cid]
            xi = list(club["lineup"].items())
            for slot, pid in xi:
                players.append({"team": side, "id": pid, "minutes": 90, "stamina": 0.75, "start": True, "yellow": 0, "red": None})
            for _ in range(n):
                gp = rng.choice([pid for s, pid in xi if s != "GK"])
                goals.append({"team": side, "pid": gp, "own_goal": False, "name": clubs.player_by_id(club, gp)["Name"], "minute": 50})
        res.append({"home": h, "away": a, "hg": hg, "ag": ag, "goals": goals, "players": players})
    league.record_matchday(c, res); av.after_matchday(c, md, res, rng)
n = len(c["fixtures"])
for md in range(1, 13):
    play(md)
app.go("cups"); app.cups_key = "champions_cup"; app.cups_round = None; shot("champions_cup_groups")
app.go("cups"); app.cups_key = "league_cup"; app.cups_round = None; shot("league_cup_autumn")
for md in range(13, 18):
    play(md)
app.go("cups"); app.cups_key = "world_club"; app.cups_round = None; shot("world_club")
app.go("finances"); shot("finances_december")
for md in range(18, 33):
    play(md)
for key in ("association_cup", "league_cup", "champions_cup", "shield"):
    app.go("cups"); app.cups_key = key; app.cups_round = None; shot(key)
app.go("spain"); shot("abroad")
for md in range(33, n + 1):
    play(md)
cups.finish_all(c)
for key in ("association_cup", "champions_cup"):
    app.go("cups"); app.cups_key = key; app.cups_round = None; shot(key + "_final")
app.go("finances"); shot("finances_may")
app.go("table"); shot("table")
app.go("season_end"); shot("season_end")
app.next_season = lambda: None
league.new_season(c, seed=1)
app.go("awards"); shot("awards")
app.go("summer"); shot("summer")
app.go("manager"); shot("manager")
print("done")
