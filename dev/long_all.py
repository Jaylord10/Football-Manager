"""long_all.py GAME N [MYCLUB] -> N seasons with EVERYTHING on (both divisions, the cups, Europe, the World
Club Trophy, Spain / Germany / Italy, transfers between them all).  Fake results for your division's league
matches (like long_test.py); everything else is played by the game itself.

Each season it prints:
  - who won what (league, both cups, the continental cups, the World Club Trophy)
  - how busy the English clubs were: matches per club, the shortest gap between two matches, how often a
    club had to play twice within 3 days (real life: a top club plays ~55-60 games; 2 days apart only over
    Christmas / a cup replay week)
  - fitness: the average condition of the first XIs of clubs in Europe vs. the rest (just before league games)
  - money and strength in every league (bank and XI: top / median / bottom)
  - transfers: how many moves between which leagues
"""
import os, sys, random, time, statistics as st, collections, datetime as dt
GAME = sys.argv[1]; N = int(sys.argv[2]) if len(sys.argv) > 2 else 10
MY = int(sys.argv[3]) if len(sys.argv) > 3 else 2
sys.path.insert(0, GAME); os.chdir(GAME)
from career import world, league, availability as av, clubs, finance as fin, divisions, cups, europe, spain, \
    foreign, training
c = league.new_career(world.load(), MY, seed=5)
rng = random.Random(11)


def strength(cl):
    lu = cl.get("lineup") or {}
    return st.mean(clubs.overall(clubs.player_by_id(cl, pid), s) for s, pid in lu.items()) if lu else 0


def poisson(lam):
    k, p, L = 0, 1.0, 2.718281828 ** -lam
    while True:
        p *= rng.random()
        if p < L: return k
        k += 1


def m(x): return fin.money(x)


def league_name_map():
    out = {}
    for x in c["clubs"]:
        out[x["name"]] = "eng"
    for x in spain.clubs(c):
        out[x["name"]] = "es"
    for cfg in foreign.LEAGUES:
        for x in foreign.clubs(c, cfg):
            out[x["name"]] = cfg.key
    return out


def cond(cl):
    lu = cl.get("lineup") or {}
    ps = [clubs.player_by_id(cl, pid) for pid in lu.values()]
    return st.mean(training.condition(p) for p in ps if p) if ps else 1.0


ALL_ERRORS = []
for season in range(N):
    t0 = time.time()
    year = c["year"]
    log_before = len(c.get("transfer_log") or [])
    seen_log = {(e["date"], e["player"], e["to"]) for e in c.get("transfer_log") or []}
    fit_eu, fit_rest = [], []
    for md in range(1, len(c["fixtures"]) + 1):
        league.advance_to_match(c)
        eu_ids = set()
        for comp in europe.comps(c):
            for mm in comp["matches"]:
                eu_ids |= {mm["home"], mm["away"]}
        for h, a in c["fixtures"][md - 1]:
            for cid in (h, a):
                (fit_eu if cid in eu_ids else fit_rest).append(cond(c["clubs"][cid]))
        res = []
        for h, a in c["fixtures"][md - 1]:
            players, goals = [], []
            sh, sa = strength(c["clubs"][h]), strength(c["clubs"][a])
            hg, ag = poisson(1.45 * 1.08 ** (sh - sa)), poisson(1.2 * 1.08 ** (sa - sh))
            for side, cid, n in ((0, h, hg), (1, a, ag)):
                club = c["clubs"][cid]
                xi = list(club["lineup"].items())
                for slot, pid in xi:
                    players.append({"team": side, "id": pid, "minutes": 90, "stamina": 0.75, "start": True,
                                    "yellow": 0, "red": None})
                for _ in range(n):
                    gp = rng.choice([pid for s, pid in xi if s != "GK"])
                    goals.append({"team": side, "pid": gp, "own_goal": False,
                                  "name": clubs.player_by_id(club, gp)["Name"], "minute": 50})
            res.append({"home": h, "away": a, "hg": hg, "ag": ag, "goals": goals, "players": players})
        league.record_matchday(c, res); av.after_matchday(c, md, res, rng)

    # --- how busy were the English clubs (league dates + cup / European dates) ---------------------------
    dates = collections.defaultdict(list)
    for fxs in (c["fixtures"], (c.get("other") or {}).get("fixtures") or []):
        for md, fx in enumerate(fxs, start=1):
            d = league.match_date(c, md)
            for h, a in fx:
                for cid in (h, a):
                    dates[cid].append(d)
    for mm in cups.all_matches(c):
        for cid in (mm["home"], mm["away"]):
            if cid is not None and 0 <= cid < 40:
                dates[cid].append(mm["date"])
    tables = divisions.tables(c)
    up, down = divisions.movers(c, tables)
    hist_before = len(c.get("cup_history") or [])
    print(f"=== season {season + 1} ({year}/{str(year + 1)[-2:]})  {time.time() - t0:.0f}s")
    t = tables["pl"]
    print(f"  champions {c['clubs'][t[0]['club']]['short']}  D1 {c['clubs'][tables['d1'][0]['club']]['short']}  "
          f"up {[c['clubs'][i]['short'] for i in up]}  down {[c['clubs'][i]['short'] for i in down]}")
    # matches + gaps (only where we know the league dates)
    if all(None not in v for v in dates.values()):
        busiest = []
        for cid, ds in dates.items():
            ds = sorted(dt.date.fromisoformat(x) for x in ds)
            gaps = [(b - a).days for a, b in zip(ds, ds[1:])]
            busiest.append((len(ds), min(gaps) if gaps else 99, sum(1 for g in gaps if g < 3),
                            sum(1 for g in gaps if g == 0), cid))
        busiest.sort(reverse=True)
        top = busiest[:4]
        print("  busiest:", ", ".join(f"{c['clubs'][cid]['short']} {n} games (min gap {mg}d, <3d x{k}, same day x{z})"
                                      for n, mg, k, z, cid in top))
        same = [(c["clubs"][cid]["short"], z) for n, mg, k, z, cid in busiest if z]
        if same:
            print("  !! CLASH (two matches on one day):", same)
            ALL_ERRORS.append((season + 1, "clash", same))
    print(f"  fitness before league games: clubs in Europe {st.mean(fit_eu):.3f}  others {st.mean(fit_rest):.3f}"
          if fit_eu else f"  fitness before league games: {st.mean(fit_rest):.3f}")
    # who won what - the summer will close the cups
    league.new_season(c, seed=season)
    if c.get("board", {}).get("sacked"):
        c["board"]["sacked"] = False
    h = (c.get("cup_history") or [{}])[-1]
    won = []
    for key in ("association_cup", "league_cup", "champions_cup", "shield", "world_club"):
        for k in h:
            if k == key + "_names":
                w, r = h[k]
                won.append(f"{k[:-6]}: {w} (beat {r})")
    print("  cups:", "; ".join(won) if won else h)
    tk = [t for t in c.get("takeovers") or [] if t["year"] == c["year"]]
    if tk:
        print("  takeovers:", "; ".join(f"{c['clubs'][t['club']]['short']}: {t['name']} ({t['what']})" for t in tk))
    # the squad cost rules (career/ffp.py): fines and points
    scr = [(x["short"], x["finance"]["scr"]) for x in c["clubs"]
           if (x.get("finance") or {}).get("scr", {}).get("year") == year]
    if scr:
        rs = sorted(v["ratio"] for _, v in scr)
        fined = [f"{n} {m(v['fine'])}" for n, v in scr if v["fine"]]
        docked = [f"{n} -{v['points']}" for n, v in scr if v["points"]]
        print(f"  squad costs: {rs[0]:.0%}/{rs[len(rs) // 2]:.0%}/{rs[-1]:.0%} of income  fined: {', '.join(fined) or '-'}"
              f"  points off: {', '.join(docked) or '-'}")
    # money and strength everywhere
    groups = {"pl": divisions.clubs_in(c, "pl"), "d1": divisions.clubs_in(c, "d1"), "es": spain.clubs(c)}
    for cfg in foreign.LEAGUES:
        groups[cfg.key] = foreign.clubs(c, cfg)
    for k, cl in groups.items():
        if not cl:
            continue
        xi = sorted((strength(x) for x in cl), reverse=True)
        bal = sorted(x["finance"]["balance"] for x in cl if x.get("finance"))
        sq = [len(x["players"]) for x in cl]
        print(f"  {k:>3}: XI {xi[0]:.0f}/{st.median(xi):.0f}/{xi[-1]:.0f}  "
              + (f"bank {m(bal[0])}/{m(st.median(bal))}/{m(bal[-1])}  " if bal else "")
              + f"squads {min(sq)}-{max(sq)}")
    # transfers between leagues this season
    names = league_name_map()
    moves = collections.Counter()
    for e in c.get("transfer_log") or []:
        if (e["date"], e["player"], e["to"]) in seen_log:
            continue
        moves[(names.get(e["from"], "?"), names.get(e["to"], "?"))] += 1
    print("  transfers:", ", ".join(f"{a}->{b} {n}" for (a, b), n in sorted(moves.items(), key=lambda x: -x[1])))
print("PROBLEMS:", ALL_ERRORS or "none")
