import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
GAME = _os.environ.get("FM_GAME", _os.path.dirname(DEV))   # the game folder (default: this repo)
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")

exec(open(_os.path.join(DEV, "tac_flow.py")).read().split('if __name__ == "__main__":')[0])
if __name__ == '__main__':
    app = ui.App(); app.new_career_screen(); app.start_career(7); c = app.career
    print("clubs", len(c["clubs"]), "other", c["other"]["div"], c["other"]["matchday"])
    for k in range(2):
        play(app, c)
        print("  my md", c["matchday"], "other md", c["other"]["matchday"])
    from career import league as lg
    print("d1 top:", [(c["clubs"][r["club"]]["short"], r["p"], r["pts"]) for r in lg.table(c, "d1")[:3]])
    print("pl top:", [(c["clubs"][r["club"]]["short"], r["p"], r["pts"]) for r in lg.table(c, "pl")[:3]])
    o = c["other"]["results"]["1"][0]; print("att", o.get("att"), "players", len(o["players"]))
    app.quit()
    