import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
GAME = _os.environ.get("FM_GAME", _os.path.dirname(DEV))   # the game folder (default: this repo)
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")

import os, sys, random
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
src = open(_os.path.join(DEV, "season2.py")).read().split("for season in range(N):")[0]
sys.argv = [sys.argv[0], GAME, "1"]
os.environ["MYCLUB"] = "25"
exec(src)
for md in range(1, len(c["fixtures"]) + 1):
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
t = league.table(c)
c["my_club"] = t[2]["club"]          # (test: make "us" the club in 3rd)
import pygame
from career import ui, clubinfo, playoffs
clubinfo._PROFILES.clear(); clubinfo._IMG.clear()
league.save = lambda *a, **k: None
app = ui.App(); app.career = c
OUT = _os.path.join(OUTDIR, "shots"); os.makedirs(OUT, exist_ok=True)
def shot(name):
    app.win.fill(ui.BG); app.buttons = []
    getattr(app, "draw_" + app.screen)()
    for b in app.buttons: b.draw(app.win, app.fonts, (0, 0))
    pygame.image.save(app.win, f"{OUT}/{name}.png")
app.screen = "home"; shot("po_0")
print("screen", app.screen)
for k in range(1, 5):
    if playoffs.my_next(c) is None:
        break
    app._playoff_play(False); app.screen = "home"; shot(f"po_{k}")
    print(k, app.screen, playoffs.lines(c)[-1])
app.screen = "playoff"; shot("po_end")
app.go("fixtures"); app.fixtures_div = "d1"; app.fixtures_md = 39; shot("po_fixtures")
app.go("calendar"); app.cal_ym = (2027, 6); shot("po_calendar")
app._playoff_continue(); shot("po_season_end")
print([m["text"][:120] for m in c["inbox"][-4:]])
