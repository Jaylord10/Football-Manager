"""How high the back line sits, real vs ours (26 Nov - Jay: "I'm playing a very high back line, why are the centre-backs
so far back?").
usage: python dev/backline_measures.py real <metrica data folder> <out.json>
       python dev/backline_measures.py engine <engine_dir> <seed> <seconds per half> <out.json> [defence style]
Every half a second of open play, for each team: whether it has the ball, where the ball is (m from that team's own
goal line) and where its back line is - the two deepest outfield players (in our engine also the two centre-backs).
All distances on a 105 m pitch (ours is 110 m long: scaled), so they compare."""
import csv, json, math, os, sys

L105 = 105.0


def bands(rows):
    """rows: (phase "with"/"without", ball_a, line_a, cb_a or None) -> summary by where the ball is."""
    out = {}
    for ph in ("with", "without"):
        for name, lo, hi in (("ball in own third", 0, 35), ("ball in middle third", 35, 70),
                             ("ball in their third", 70, 105.1), ("all", 0, 105.1)):
            rs = [r for r in rows if r[0] == ph and lo <= r[1] < hi]
            if not rs:
                continue
            med = lambda xs: sorted(xs)[len(xs) // 2]
            d = {"n": len(rs), "back line m from own goal": round(med([r[2] for r in rs]), 1),
                 "back line behind the ball m": round(med([r[1] - r[2] for r in rs]), 1),
                 "ball m from own goal": round(med([r[1] for r in rs]), 1),
                 "back line past halfway %": round(100.0 * sum(r[2] > L105 / 2 for r in rs) / len(rs), 1)}
            cbs = [r[3] for r in rs if r[3] is not None]
            if cbs:
                d["centre-backs m from own goal"] = round(med(cbs), 1)
            out[f"{'with the ball' if ph == 'with' else 'without the ball'} / {name}"] = d
    return out


def real(folder, out):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import support_real as sr
    rows = []
    for game in (1, 2):
        base = os.path.join(folder, f"Sample_Game_{game}", f"Sample_Game_{game}_")
        home = sr.load_tracking(base + "RawTrackingData_Home_Team.csv")
        away = sr.load_tracking(base + "RawTrackingData_Away_Team.csv")
        with open(base + "RawEventsData.csv") as f:
            ev = list(csv.DictReader(f))
        # which way each team attacks, and its keeper (as support_real.py)
        side = {}
        for per in (1, 2):
            for team, tr in (("Home", home), ("Away", away)):
                sums = {}
                for fr, (p, pos) in list(tr.items())[::250]:
                    if p != per:
                        continue
                    for n, (x, y) in pos.items():
                        if n != "Ball":
                            s = sums.setdefault(n, [0.0, 0]); s[0] += x; s[1] += 1
                avg = {n: s[0] / s[1] for n, s in sums.items() if s[1] > 20}
                gk = min(avg, key=lambda n: min(avg[n], L105 - avg[n]))
                side[(team, per)] = (1 if avg[gk] < L105 / 2 else -1, gk)
        # who has the ball: the last pass / carry / recovery / set piece / shot; nobody after it goes out
        poss = []
        for e in ev:
            fr = int(e["Start Frame"])
            if e["Type"] in ("PASS", "RECOVERY", "SET PIECE", "SHOT"):
                poss.append((fr, e["Team"]))
            elif e["Type"] == "BALL OUT":
                poss.append((int(e["End Frame"]) or fr, None))
        poss.sort()
        k = 0
        cur = None
        for fr in sorted(home):
            while k < len(poss) and poss[k][0] <= fr:
                cur = poss[k]; k += 1
            if fr % 12 or cur is None or cur[1] is None or fr - cur[0] > 25 * 15:
                continue
            per, hp = home[fr]
            ap = away.get(fr, (per, {}))[1]
            ball = hp.get("Ball")
            if ball is None:
                continue
            for team, pos in (("Home", hp), ("Away", ap)):
                dirn, gk = side[(team, per)]
                a = lambda x: x if dirn > 0 else L105 - x
                outf = sorted(a(x) for n, (x, y) in pos.items() if n not in ("Ball", gk))
                if len(outf) < 9:
                    continue
                rows.append(("with" if cur[1] == team else "without", a(ball[0]), (outf[0] + outf[1]) / 2, None))
    res = bands(rows)
    json.dump(res, open(out, "w"), indent=1)
    return res


def engine(eng, seed, half, out, defence):
    import io, contextlib, random
    os.chdir(eng); sys.path.insert(0, eng)
    os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ.setdefault("FM_MATCH_CONFIG", "match_config_benchmark.json")
    with contextlib.redirect_stdout(io.StringIO()):
        import gameplay.match_engine as me
        import core.database as database
        import config.formations as formations
        from config.constants import M_TO_PX, WIDTH
    L = WIDTH / M_TO_PX
    random.seed(seed)
    with contextlib.redirect_stdout(io.StringIO()):
        me.RL_ENABLED = False
        me.HALF_DURATION_REAL = half
        if defence:
            database.TACTICS[0] = {"defence": defence, "build_up": "mixed"}
            db = formations.db
            if not hasattr(db, "formation") or db.formation is None:
                db.formation = {}
            db.formation[0] = ["GK", "LB", "LCB", "RCB", "RB", "DM", "LCM", "RCM", "LW", "RW", "ST"]   # (Jay's 4-3-3)
        e = me.MatchEngine(career=True)
    random.seed(seed)
    rows = []
    n = 0
    last = None
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        while e.match_state != "full_time" and n < 2_000_000:
            e.step(1 / 60); n += 1
            if n % 600 == 0:
                sink.seek(0); sink.truncate(0)
            b = e.ball
            if b.owner is not None:
                last = b.owner.team
            if n % 30 or e.match_state not in ("first_half", "second_half") or b.is_dead or last is None:
                continue
            team = e.team0
            gk = next((p for p in team if p.role == "GK"), None)
            dirn = 1 if gk.pos.x < WIDTH / 2 else -1
            a = lambda x: (x / M_TO_PX if dirn > 0 else L - x / M_TO_PX) * L105 / L
            outf = sorted(a(p.pos.x) for p in team if p.role != "GK" and getattr(p, "is_active", True))
            cbs = [a(p.pos.x) for p in team if p.role in ("LCB", "RCB", "CB")]
            rows.append(("with" if last == 0 else "without", a(b.pos.x), (outf[0] + outf[1]) / 2,
                         sum(cbs) / len(cbs) if cbs else None))
    res = bands(rows)
    res["score (Jay's tactics first)"] = list(e.score)
    json.dump(res, open(out, "w"), indent=1)
    return res


if __name__ == "__main__":
    if sys.argv[1] == "real":
        r = real(sys.argv[2], sys.argv[3])
    else:
        r = engine(sys.argv[2], int(sys.argv[3]), float(sys.argv[4]), sys.argv[5], sys.argv[6] if len(sys.argv) > 6 else None)
    for k, v in r.items():
        print(k, v)
