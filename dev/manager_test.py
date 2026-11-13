"""manager_test.py GAME N [MYCLUB] -> N seasons (fake results): your record and reputation (career/manager.py),
summer offers taken, one sacking mid-season; then screenshots of "Your career" and the summer offer."""
import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")
import os, sys, random, statistics as st
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
GAME = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 5
MY = int(sys.argv[3]) if len(sys.argv) > 3 else 25
sys.path.insert(0, GAME); os.chdir(GAME)
from career import world, league, availability as av, clubs, board, manager, divisions
c = league.new_career(world.load(), MY, seed=8)
rng = random.Random(3)
def strength(cl):
    return st.mean(clubs.overall(clubs.player_by_id(cl, pid), s) for s, pid in cl["lineup"].items())
def poisson(lam):
    k, p, L = 0, 1.0, 2.718281828 ** -lam
    while True:
        p *= rng.random()
        if p < L: return k
        k += 1
def play(md):
    league.advance_to_match(c)
    res = []
    for h, a in c["fixtures"][md - 1]:
        players, goals = [], []
        sh, sa = strength(c["clubs"][h]), strength(c["clubs"][a])
        boost = float(os.environ.get("BOOST", 0.25)) if c["my_club"] in (h, a) else 0          # (you're a good manager...)
        hg = poisson(1.45 * 1.08 ** (sh - sa) + (boost if h == c["my_club"] else 0))
        ag = poisson(1.2 * 1.08 ** (sa - sh) + (boost if a == c["my_club"] else 0))
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
shown_offer = False
if os.environ.get("REP"):
    manager.state(c)["rep"] = float(os.environ["REP"])
    manager.OFFER_CHANCE = 1.0
for season in range(N):
    for md in range(1, len(c["fixtures"]) + 1):
        if season == 2 and md == 20:
            board.sack(c, "a test")
            offers = board.job_offers(c)
            print("  SACKED - offers:", [c["clubs"][i]["short"] for i in offers])
            board.take_job(c, offers[0])
        play(md)
    me = c["clubs"][c["my_club"]]
    league.new_season(c, seed=season)
    m = manager.state(c)
    s = m["seasons"][-1]
    print(f"season {season + 1}: {s['short']} {s['div']} pos {s['pos']} {s['all']} won {s['won']} notes {s['notes']} "
          f"rep {s['rep_before']} -> {m['rep']} ({manager.label(m['rep'])})")
    if board.state(c).get("sacked"):
        offers = board.job_offers(c)
        print("  sacked at the season's end - offers:", [c["clubs"][i]["short"] for i in offers])
        board.take_job(c, offers[0])
    o = manager.offer(c)
    if o is not None:
        print("  OFFER from", c["clubs"][o]["short"], "(level %.0f, mine %.0f)" % (manager.level(c, c["clubs"][o]), manager.level(c, me)))
        if not shown_offer:
            import pygame
            from career import ui, clubinfo
            clubinfo._PROFILES.clear(); clubinfo._IMG.clear()
            app = ui.App(); app.career = c
            OUT = _os.path.join(OUTDIR, "shots"); os.makedirs(OUT, exist_ok=True)
            app.go("summer"); app.win.fill(ui.BG); app.buttons = []; app.draw_summer()
            for b in app.buttons: b.draw(app.win, app.fonts, (0, 0))
            pygame.image.save(app.win, f"{OUT}/mgr_offer.png")
            shown_offer = True
        if season % 2 == 0:
            manager.take_offer(c); print("  took it: now", c["clubs"][c["my_club"]]["name"], divisions.div_of(c["clubs"][c["my_club"]]))
        else:
            manager.turn_down(c); print("  turned it down")
print("totals", manager.totals(c)[:4], manager.totals(c)[4])
import pygame
from career import ui, clubinfo
clubinfo._PROFILES.clear(); clubinfo._IMG.clear()
league.save = lambda *a, **k: None
app = ui.App(); app.career = c
OUT = _os.path.join(OUTDIR, "shots"); os.makedirs(OUT, exist_ok=True)
app.go("manager"); app.win.fill(ui.BG); app.buttons = []; app.draw_manager()
for b in app.buttons: b.draw(app.win, app.fonts, (0, 0))
pygame.image.save(app.win, f"{OUT}/mgr_career.png")
app.go("board"); app.win.fill(ui.BG); app.buttons = []; app.draw_board()
for b in app.buttons: b.draw(app.win, app.fonts, (0, 0))
pygame.image.save(app.win, f"{OUT}/mgr_board.png")
print("done")
