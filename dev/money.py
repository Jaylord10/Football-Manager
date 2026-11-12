import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
GAME = _os.environ.get("FM_GAME", _os.path.dirname(DEV))   # the game folder (default: this repo)
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")

import os, sys
src = open(_os.path.join(DEV, "season2.py")).read()
src = src.replace('    league.new_season(c, seed=season)', '''    from career import divisions, finance as fin
    up, down = divisions.movers(c, divisions.tables(c))
    snap = {i: (fin.money(c["clubs"][i]["finance"]["commercial"]), c["clubs"][i]["finance"]["ticket"], fin.money(fin.wage_bill(c["clubs"][i]))) for i in up + down}
    league.new_season(c, seed=season)
    for i in up + down:
        cl = c["clubs"][i]; f = cl["finance"]
        print(f"  {'UP  ' if i in up else 'DOWN'} {cl['short']:12} comm {snap[i][0]}->{fin.money(f['commercial'])} (target {fin.money(f.get('commercial_target') or 0)}) "
              f"ticket {snap[i][1]}->{f['ticket']} wages {snap[i][2]}->{fin.money(fin.wage_bill(cl))} parachute {[fin.money(x) for x in f.get('parachute') or []]} "
              f"income exp {fin.money(fin.expected_income(c, cl))} wage budget {fin.money(f['wage_budget'])} transfer budget {fin.money(f['transfer_budget'])} bal {fin.money(f['balance'])}")
    if c["my_club"] in down: print("  ", [m["text"] for m in c["inbox"][-3:]])''')
exec(compile(src, "money", "exec"))
