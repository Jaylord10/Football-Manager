import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
GAME = _os.environ.get("FM_GAME", _os.path.dirname(DEV))   # the game folder (default: this repo)
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")

import os, sys, runpy
sys.argv = [sys.argv[0]] + sys.argv[1:]
src = open(_os.path.join(DEV, "season2.py")).read()
src = src.replace('    league.new_season(c, seed=season)', '''    from career import playoffs, divisions
    up, down = divisions.movers(c, divisions.tables(c))
    print("  play-offs:", [l for l in playoffs.lines(c)])
    print("  up", [c["clubs"][i]["short"] for i in up], "down", [c["clubs"][i]["short"] for i in down])
    league.new_season(c, seed=season)
    print("  sizes", len(divisions.clubs_in(c, "pl")), len(divisions.clubs_in(c, "d1")), "my div", divisions.my_div(c), "fixtures", len(c["fixtures"]), len(c["fixtures"][0]), "other", c["other"]["div"])
    print("  ", [m["text"][:150] for m in c.get("inbox", [])[-6:] if m["kind"] in ("news", "board")])''')
exec(compile(src, "season3", "exec"))
