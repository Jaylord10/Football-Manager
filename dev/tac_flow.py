import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
GAME = _os.environ.get("FM_GAME", _os.path.dirname(DEV))   # the game folder (default: this repo)
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")

import os, sys, time, json, glob
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["FM_CAREER_HALF"] = "15"
sys.path.insert(0, _os.environ.get("FM_FLOW", GAME)); os.chdir(_os.environ.get("FM_FLOW", GAME))
from career import league, ui, clubs as cm
from career import spain, transfers as trf
import pygame
def play(app, c):
    for i in range(30):
        app.go("home"); app.continue_to_match()
        if app.screen == "prematch": break
        for m in trf.inbox(c):
            if m["kind"] == "offer" and m["state"] == "open": trf.respond(c, m["id"], "reject")
            if m["kind"] == "loan" and m["state"] == "open":
                from career import loans; print("   loan request:", loans.respond(c, m["id"], "accept"))
    print("  to match:", app.screen, c["date"], "halts", i)
    app.simulate_match()
    t0 = time.time()
    while (app.my_result is None or len(app._pending()) < 9) and time.time() - t0 < 600:
        app._keep_running(); app.win.fill(ui.BG); app.buttons = []; app.draw_results(); time.sleep(0.3)
    print("  result", app.my_result["hg"], app.my_result["ag"], "others", len(app._pending()), f"{time.time()-t0:.0f}s")
    app.finish_matchday()


if __name__ == "__main__":
    app = ui.App(); app.new_career_screen(); app.start_career(7); c = app.career
    me = c["clubs"][7]
    print("my shape:", cm.formation_name(me))
    from collections import Counter
    print("PL shapes:", Counter(cm.formation_name(x) for x in c["clubs"]).most_common())
    app.go("tactics"); app._preset("3-4-2-1"); print("now", cm.formation_name(me), app.tactics_msg)
    for k in range(2):
        play(app, c)
        cfgs = sorted(glob.glob("saves/match_configs/*.json") + glob.glob("saves/*/*.json"), key=os.path.getmtime)[-12:]
        for f in cfgs:
            d = json.load(open(f))
            if "home_team" in d:
                print("  ", os.path.basename(f), d["home_team"]["name"][:12], d["home_team"].get("formation") and len(d["home_team"]["formation"]),
                      cm.formation_name({"formation": d["home_team"].get("formation")}), "v", cm.formation_name({"formation": d["away_team"].get("formation")}))
    r = c["results"]
    for md in r:
        print("md", md, [(m["hg"], m["ag"]) for m in r[md]])
    app.quit()
