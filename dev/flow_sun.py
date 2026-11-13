import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
GAME = _os.environ.get("FM_GAME", _os.path.dirname(DEV))
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")
exec(open(_os.path.join(DEV, "tac_flow.py")).read().split('if __name__ == "__main__":')[0])
if __name__ == '__main__':
    app = ui.App(); app.new_career_screen(); app.start_career(2); c = app.career
    from career import league as lg
    k = 0
    while c["matchday"] <= 5 and k < 12:
        before = c["matchday"]
        play(app, c)
        print("  md", before, "->", c["matchday"], "date", c["date"], "my md5 date", lg.match_date(c, 5, 2))
        k += 1
    r = c["results"].get("5")
    print("md5 results:", len(r or []), [(x["home"], x["away"], x["hg"], x["ag"]) for x in (r or []) if 2 in (x["home"], x["away"])])
    app.quit()
