"""How often a pass really reaches its man in OUR engine (26 Nov, for ai/scoreboard.py): every open-play pass played
(by the old checklist, so all sorts get tried), the situation when it's struck - length, how open the lane is and how
much time the receiver has (ai/spot_value.py lane_and_time), the passer pressed or not - and whether the next man to
get the ball was a team-mate.
usage: python dev/pass_odds.py collect <engine_dir> <seed> <seconds per half> <out.json>
       python dev/pass_odds.py fit <out_model.json> <collected1.json> [...]"""
import os, sys, io, contextlib, random, json, math


def feats(L, lane, t, pressed):
    t = max(-2.0, min(3.0, t))
    return [1.0, L / 10.0, (L / 10.0) ** 2, lane, t, t * t, 1.0 if pressed else 0.0, max(0.0, L - 25.0) / 10.0]


def predict(w, L, lane, t, pressed):
    z = sum(a * b for a, b in zip(w, feats(L, lane, t, pressed)))
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def collect(eng, seed, half, out):
    os.chdir(eng); sys.path.insert(0, eng)
    os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ.setdefault("FM_MATCH_CONFIG", "match_config_benchmark.json")
    with contextlib.redirect_stdout(io.StringIO()):
        import gameplay.match_engine as me
        import gameplay.mechanics as mech
        import ai.spot_value as sv
        from ai.team_shape import to_frame
    E = {"e": None, "open": None}
    recs = []
    orig = mech.GameMechanics.execute_pass

    def f(self, passer, receiver, ball, now, opponents=None, through_plan=None):
        e = E["e"]
        if e is not None and through_plan is None and e.match_state in ("first_half", "second_half") \
                and not getattr(passer, "_set_piece_restart", False):
            tid = passer.team
            other = e.team1 if tid == 0 else e.team0
            ca, cl = to_frame(tid, passer.pos)
            ma, ml = to_frame(tid, receiver.pos)
            opps = [to_frame(tid, o.pos) for o in other if o.role != "GK" and getattr(o, "is_active", True)]
            L = math.hypot(ma - ca, ml - cl)
            lane, t = sv.lane_and_time(ma, ml, ca, cl, opps, L)
            near = min((math.hypot(oa - ca, ol - cl) for oa, ol in opps), default=99)
            E["open"] = {"team": tid, "passer": passer, "L": L, "lane": lane, "t": t, "pressed": near < 3.0}
        return orig(self, passer, receiver, ball, now, opponents, through_plan)
    mech.GameMechanics.execute_pass = f
    random.seed(seed)
    with contextlib.redirect_stdout(io.StringIO()):
        me.RL_ENABLED = False
        me.HALF_DURATION_REAL = half
        e = me.MatchEngine(career=True)
    E["e"] = e
    random.seed(seed)
    n = 0
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        while e.match_state != "full_time" and n < 2_000_000:
            e.step(1 / 60); n += 1
            if n % 600 == 0:
                sink.seek(0); sink.truncate(0)
            o = E["open"]
            if o is None:
                continue
            b = e.ball
            if b.is_dead or e.match_state not in ("first_half", "second_half"):
                recs.append({k: v for k, v in o.items() if k != "passer"} | {"ok": 0}); E["open"] = None
            elif b.owner is not None and b.owner is not o["passer"]:
                recs.append({k: v for k, v in o.items() if k != "passer"} | {"ok": int(b.owner.team == o["team"])})
                E["open"] = None
    json.dump(recs, open(out, "w"))
    print(len(recs), "passes,", sum(r["ok"] for r in recs), "reached a team-mate")


def fit(out, files):
    R = [r for f in files for r in json.load(open(f))]
    X = [feats(r["L"], r["lane"], r["t"], r["pressed"]) for r in R]
    y = [r["ok"] for r in R]
    # (27 Nov: Newton's method - plain gradient steps hadn't settled, and over-rated long and blocked passes)
    import numpy as np
    Xa, ya = np.array(X), np.array(y, dtype=float)
    wa = np.zeros(Xa.shape[1])
    for it in range(50):
        pa = 1 / (1 + np.exp(-np.clip(Xa @ wa, -30, 30)))
        H = (Xa * (pa * (1 - pa))[:, None]).T @ Xa + 1e-3 * np.eye(len(wa))
        step = np.linalg.solve(H, Xa.T @ (pa - ya) + 1e-3 * wa)
        wa -= step
        if np.abs(step).max() < 1e-8:
            break
    w = [float(v) for v in wa]
    # check by band
    print(f"{len(R)} passes, {100 * sum(y) / len(y):.1f}% reached a team-mate")
    for name, sel in (("under 15 m", lambda r: r["L"] < 15), ("15-30 m", lambda r: 15 <= r["L"] < 30),
                      ("30 m+", lambda r: r["L"] >= 30), ("lane under 0.5", lambda r: r["lane"] < 0.5),
                      ("receiver closed (t < 0)", lambda r: r["t"] < 0), ("pressed", lambda r: r["pressed"])):
        rs = [r for r in R if sel(r)]
        if rs:
            real = sum(r["ok"] for r in rs) / len(rs)
            pred = sum(predict(w, r["L"], r["lane"], r["t"], r["pressed"]) for r in rs) / len(rs)
            print(f"  {name:24s} n {len(rs):4d}  really {100 * real:5.1f}%  model {100 * pred:5.1f}%")
    json.dump({"w": w, "features": "1, L/10, (L/10)^2, lane, t, t^2, pressed, (L-25)+/10 (t clamped -2..3)",
               "passes": len(R), "note": "fitted on our engine's open-play passes (dev/pass_odds.py)"},
              open(out, "w"), indent=1)


if __name__ == "__main__":
    if sys.argv[1] == "collect":
        collect(sys.argv[2], int(sys.argv[3]), float(sys.argv[4]), sys.argv[5])
    else:
        fit(sys.argv[2], sys.argv[3:])
