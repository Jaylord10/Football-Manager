"""hist_shots.py -> 2 seasons + half a season (fake results), then the Career tab on a few player pages
(career/playerhist.py) saved to $FM_OUT/shots."""
import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
GAME = _os.environ.get("FM_GAME", _os.path.dirname(DEV))
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")
import os, sys
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
src = open(_os.path.join(DEV, "season2.py")).read()
src = src.split("league.save(c,")[0]
sys.argv = [sys.argv[0], GAME, "2"]
exec(src)
half = len(c["fixtures"]) // 2
for md in range(1, half + 1):
    league.advance_to_match(c)
    res = []
    for h, a in c["fixtures"][md - 1]:
        players, goals = [], []
        for side, cid, n in ((0, h, poisson(1.4)), (1, a, poisson(1.1))):
            club = c["clubs"][cid]
            xi = list(club["lineup"].items())
            for slot, pid in xi:
                players.append({"team": side, "id": pid, "minutes": 90, "stamina": 0.75, "start": True, "yellow": 0, "red": None})
            for _ in range(n):
                gp = rng.choice([pid for s, pid in xi if s != "GK"])
                goals.append({"team": side, "pid": gp, "own_goal": False, "name": clubs.player_by_id(club, gp)["Name"], "minute": 50})
        res.append({"home": h, "away": a, "hg": sum(1 for g in goals if g["team"] == 0), "ag": sum(1 for g in goals if g["team"] == 1), "goals": goals, "players": players})
    league.record_matchday(c, res); av.after_matchday(c, md, res, rng)
from career import playerhist, spain, foreign
everyone = [(cl["id"], p) for cl in c["clubs"] + spain.clubs(c) + [x for cfg in foreign.LEAGUES for x in foreign.clubs(c, cfg)] for p in cl["players"]]
withh = [(cid, p) for cid, p in everyone if p.get("hist")]
print("players", len(everyone), "with a record", len(withh))
movers = [(cid, p) for cid, p in withh if len({x["c"] for x in p["hist"]}) > 1]
print("players with two clubs or more:", len(movers))
for cid, p in movers[:5]:
    print(" ", p["Name"], p["hist"])
me = c["clubs"][c["my_club"]]
best = max(me["players"], key=lambda p: sum(x["g"] for x in p.get("hist", [])))
print("my top scorer", best["Name"], best.get("hist"), best.get("awards"))
import pygame
from career import ui, clubinfo
clubinfo._PROFILES.clear(); clubinfo._IMG.clear()
league.save = lambda *a, **k: None
app = ui.App(); app.career = c
OUT = _os.path.join(OUTDIR, "shots"); os.makedirs(OUT, exist_ok=True)
def shot(name):
    app.win.fill(ui.BG); app.buttons = []
    getattr(app, "draw_" + app.screen)()
    for b in app.buttons: b.draw(app.win, app.fonts, (0, 0))
    pygame.image.save(app.win, f"{OUT}/{name}.png")
app.screen = "squad"
app.view_player(me["id"], best["id"]); shot("hist_profile")
app.player_tab = "career"; shot("hist_mine")
decorated = max(withh, key=lambda cp: (len(playerhist.trophies(cp[1])), len(cp[1].get("awards") or [])))
app.view_player(decorated[0], decorated[1]["id"]); app.player_tab = "career"; shot("hist_decorated")
print("decorated", decorated[1]["Name"], playerhist.trophies(decorated[1]), decorated[1].get("awards"))
if movers:
    cid, p = movers[0]
    app.view_player(cid, p["id"]); app.player_tab = "career"; shot("hist_mover")
fo = [(cid, p) for cid, p in withh if cid >= 100]
if fo:
    cid, p = max(fo, key=lambda cp: sum(x["g"] for x in cp[1]["hist"]))
    app.view_player(cid, p["id"]); app.player_tab = "career"; shot("hist_abroad")
print("done")
