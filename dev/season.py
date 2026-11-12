"""season.py N -> N seasons with random results; morale spread, by status, and examples"""
import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
GAME = _os.environ.get("FM_GAME", _os.path.dirname(DEV))   # the game folder (default: this repo)
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")

import os, sys, random, statistics as st, collections
sys.path.insert(0, GAME); os.chdir(GAME)
from career import world, league, availability as av, clubs, morale, contracts
w = world.load(); _os.makedirs(OUTDIR, exist_ok=True); os.chdir(OUTDIR)
c = league.new_career(w, int(os.environ.get("MYCLUB", 0)), seed=3)
rng = random.Random(7)
def strength(cl):
    xi = [clubs.overall(clubs.player_by_id(cl, pid), s) for s, pid in cl["lineup"].items()]
    return st.mean(xi)
def poisson(lam):
    k, p, L = 0, 1.0, 2.718281828 ** -lam
    while True:
        p *= rng.random()
        if p < L: return k
        k += 1
def report(tag):
    allp = [(cl, p) for cl in c["clubs"] for p in cl["players"]]
    lab = collections.Counter(morale.label(p) for _, p in allp)
    print(f"--- {tag}: " + "  ".join(f"{k} {100*v/len(allp):.0f}%" for k, v in lab.most_common()))
    by = collections.defaultdict(list)
    for cl, p in allp:
        by[morale.expected_share(cl, p)[1]].append(morale.level(p))
    print("    by status: " + "  ".join(f"{k} {st.mean(v):.0f} (n{len(v)})" for k, v in by.items()))
    pos = sorted(range(20), key=lambda i: -league_points(i))
    for i in (pos[0], pos[9], pos[-1]):
        cl = c["clubs"][i]
        print(f"    {cl['name']:18} pts {league_points(i):3}  morale avg {st.mean(morale.level(p) for p in cl['players']):.0f}")
    notes = [morale.assistant_note(p) for _, p in allp]
    notes = [n for n in notes if n]
    print(f"    assistant notes: {len(notes)}  e.g.", notes[:4])
def league_points(cid):
    t = league.table(c)
    return next(r["pts"] for r in t if r["club"] == cid)
for season in range(int(sys.argv[1]) if len(sys.argv) > 1 else 1):
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
                bench = [p for p in club["players"] if p["id"] not in dict(xi).values()]
                rng.shuffle(bench)
                subbed = rng.sample([pid for s, pid in xi if s != "GK"], 3)
                for slot, pid in xi:
                    players.append({"team": side, "id": pid, "minutes": 70 if pid in subbed else 90, "stamina": 0.75, "start": True, "yellow": 0, "red": None})
                for p in bench[:3]:
                    players.append({"team": side, "id": p["id"], "minutes": 20, "stamina": 0.9, "start": False, "yellow": 0, "red": None})
                att = [pid for s, pid in xi if s != "GK" and s not in ("LCB", "RCB", "CB")]
                for _ in range(n):
                    gp = rng.choice(att + att[-3:])
                    goals.append({"team": side, "pid": gp, "own_goal": False,
                                  "name": clubs.player_by_id(club, gp)["Name"], "minute": 50})
            res.append({"home": h, "away": a, "hg": hg, "ag": ag, "goals": goals, "players": players})
        league.record_matchday(c, res); av.after_matchday(c, md, res, rng)
        if md in (5, 19):
            report(f"season {season+1} matchday {md}")
    report(f"season {season+1} end")
t = league.table(c)
for row in (t[0], t[-1]):
    cl = c["clubs"][row["club"]]
    print(cl["name"], row)
    for p in sorted(cl["players"], key=lambda p: -p.get("mins_avg", 0))[:20:3]:
        print("   ", p["Name"], p.get("status"), round(p.get("mins_avg", 0)), p.get("morale"), p.get("morale_why"), p.get("traits"))
