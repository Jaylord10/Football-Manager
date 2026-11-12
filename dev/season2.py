"""season2.py ROOT N -> N seasons with a fake engine (random results) on the code at ROOT; checks both divisions."""
import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
GAME = _os.environ.get("FM_GAME", _os.path.dirname(DEV))   # the game folder (default: this repo)
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")

import os, sys, random, time, statistics as st
ROOT = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 1
sys.path.insert(0, ROOT); os.chdir(ROOT)
from career import world, league, availability as av, clubs, finance as fin
w = world.load()
t0 = time.time()
c = league.new_career(w, int(os.environ.get("MYCLUB", 2)), seed=3)
print("clubs", len(c["clubs"]), "new career %.1fs" % (time.time() - t0))
rng = random.Random(7)
def strength(cl):
    return st.mean(clubs.overall(clubs.player_by_id(cl, pid), s) for s, pid in cl["lineup"].items())
def poisson(lam):
    k, p, L = 0, 1.0, 2.718281828 ** -lam
    while True:
        p *= rng.random()
        if p < L: return k
        k += 1
for season in range(N):
    t1 = time.time()
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
    print(f"season {season + 1}: {time.time() - t1:.0f}s")
    if "other" in c:
        print("  other matchday", c["other"]["matchday"])
        for d in ("pl", "d1"):
            t = league.table(c, d)
            print(f"  {d}: ", ", ".join(f"{c['clubs'][r['club']]['short']} {r['pts']}" for r in t[:3]), " ... ",
                  ", ".join(f"{c['clubs'][r['club']]['short']} {r['pts']}" for r in t[-2:]), " P", t[0]["p"])
        for cid in (2, 20, 39):
            cl = c["clubs"][cid]; f = cl["finance"]
            print(f"  {cl['name']:20} {cl['league']} bal {fin.money(f['balance'])} wages {fin.money(fin.wage_bill(cl))} cap {f['capacity']} squad {len(cl['players'])}")
    league.new_season(c, seed=season)
    print("  history:", {k: v for k, v in c["history"][-1].items() if k != "tables"})
league.save(c, _os.path.join(OUTDIR, "career_%s.json") % os.path.basename(ROOT.rstrip("/")))
