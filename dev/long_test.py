"""long_test.py GAME N [MYCLUB] -> N seasons (fake results for your division, quick results for the other):
the health of both divisions season by season - strength, money, squads, crowds, who goes up and down."""
import os, sys, random, time, statistics as st
GAME = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 10
MY = int(sys.argv[3]) if len(sys.argv) > 3 else 2
sys.path.insert(0, GAME); os.chdir(GAME)
from career import world, league, availability as av, clubs, finance as fin, divisions, crowds, morale
c = league.new_career(world.load(), MY, seed=5)
rng = random.Random(11)
def strength(cl):
    return st.mean(clubs.overall(clubs.player_by_id(cl, pid), s) for s, pid in cl["lineup"].items())
def poisson(lam):
    k, p, L = 0, 1.0, 2.718281828 ** -lam
    while True:
        p *= rng.random()
        if p < L: return k
        k += 1
def m(x): return fin.money(x)
fate = {}            # promoted club -> where it finished next season
prev_up = []
for season in range(N):
    t0 = time.time()
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
    tables = divisions.tables(c)
    for cid in prev_up:
        fate[cid] = fate.get(cid, []) + [next(i for i, r in enumerate(tables["pl"], 1) if r["club"] == cid) if cid in [r["club"] for r in tables["pl"]] else None]
    up, down = divisions.movers(c, tables)
    print(f"=== season {season + 1} ({c['year']}/{str(c['year'] + 1)[-2:]})  {time.time() - t0:.0f}s")
    for d in ("pl", "d1"):
        cl = divisions.clubs_in(c, d)
        xi = sorted((strength(x) for x in cl), reverse=True)
        bal = sorted(x["finance"]["balance"] for x in cl)
        wr = [fin.wage_bill(x) / max(1, fin.expected_income(c, x)) for x in cl]
        sq = [len(x["players"]) for x in cl]
        sup = [crowds.support(c, x) for x in cl]
        t = tables[d]
        print(f"  {d}: XI {xi[0]:.0f}/{st.median(xi):.0f}/{xi[-1]:.0f}  pts {t[0]['pts']}/{t[9]['pts']}/{t[-1]['pts']}  "
              f"bank {m(bal[0])}/{m(st.median(bal))}/{m(bal[-1])}  wages/income {min(wr):.2f}/{st.median(wr):.2f}/{max(wr):.2f}  "
              f"squads {min(sq)}-{max(sq)}  support {min(sup):,}-{max(sup):,}")
    print("  up:", [c["clubs"][i]["short"] for i in up], " down:", [c["clubs"][i]["short"] for i in down])
    prev_up = up
    league.new_season(c, seed=season)
    if c.get("board", {}).get("sacked"):
        c["board"]["sacked"] = False
allp = sum(len(x["players"]) for x in c["clubs"])
print("players in England:", allp, " free agents:", len(c.get("free_agents", {}).get("players", [])))
print("promoted clubs' finishes in later seasons:", {c["clubs"][k]["short"]: v for k, v in fate.items()})
