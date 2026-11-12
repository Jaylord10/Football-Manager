import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
GAME = _os.environ.get("FM_GAME", _os.path.dirname(DEV))   # the game folder (default: this repo)
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")

import os, sys, random
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.argv = [sys.argv[0], "0"]
exec(open(_os.path.join(DEV, "season.py")).read().split("for season in range")[0])
import pygame
os.chdir(GAME)
from career import ui
# 12 matchdays of results (same fake engine as season.py)
src = open(_os.path.join(DEV, "season.py")).read()
body = src.split("for md in range(1, len(c[\"fixtures\"]) + 1):")[1].split("        if md in (5, 19):")[0]
for md in range(1, 13):
    exec(body.replace("\n        ", "\n"))
league.save = lambda *a, **k: None
from career import clubinfo as _ci; _ci._PROFILES.clear(); _ci._IMG.clear()   # (season.py looked them up from the wrong folder)
app = ui.App(); app.career = c
OUT = _os.path.join(OUTDIR, "shots"); os.makedirs(OUT, exist_ok=True)
def shot(name):
    app.win.fill(ui.BG); app.buttons = []
    getattr(app, "draw_" + app.screen)()
    for b in app.buttons: b.draw(app.win, app.fonts, (0, 0))
    pygame.image.save(app.win, f"{OUT}/{name}.png")
app.go("squad"); shot("squad")
me = c["clubs"][c["my_club"]]
print("my club", me["name"], "pos", league.position_of(c, me["id"]))
me["players"][5]["morale"] = 33.0; me["players"][5]["morale_why"] = {"results": -0.8, "goals": 0, "minutes": -2.6, "status": "First team"}
withnote = [p for p in me["players"] if morale.assistant_note(p)]
pick = (withnote or me["players"])[0]
app.player_view = (me["id"], pick["id"]); app.go("player"); shot("player_note")
quiet = [p for p in me["players"] if not morale.assistant_note(p) and p["Pos"] == "GK"]
if quiet:
    app.player_view = (me["id"], quiet[0]["id"]); app.go("player"); shot("player_quiet")
for p in me["players"]:
    print(f"{p['Name']:20} {morale.label(p):9} {p.get('morale')}  {morale.assistant_note(p)}")
