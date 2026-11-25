"""The left inside forward and the right winger against Jay's maps (25 Nov, evening): before and after.
usage: python dev/wide_check.py <engine_dir> <seeds e.g. 1,2> <seconds per half> <out.json>
WIDE_BOTH=1: both teams play an inside forward on the left (LM_blue) and a winger on the right (RM_blue) - results
split by team (team 0 kicks left to right, team 1 right to left).
Every half a second in open play, for the team with the ball, for each of the two:
  where      in his green area / yellow (where he shoots from) / amber / outside it (by position, against the map in
             ai/spot_value.py MAPS - so the same test works on the old engine)
  height     m ahead of the ball, across = m from the middle (his team's left minus), dist = m from the ball
  free_ahead 3 m+ ahead of the ball and free for a pass (lane clear by 2 m, nobody within 3 m), within 40 m
And on the ball: where he got it (passes received), his shots (and how many from yellow), his crosses."""
import os, sys, io, contextlib, random, json, math

eng, seeds, half, out = sys.argv[1], [int(s) for s in sys.argv[2].split(",")], float(sys.argv[3]), sys.argv[4]
os.chdir(eng); sys.path.insert(0, eng)
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("FM_MATCH_CONFIG", "match_config_benchmark.json")
with contextlib.redirect_stdout(io.StringIO()):
    import gameplay.match_engine as me
    import gameplay.mechanics as mech
    from config.constants import M_TO_PX, WIDTH

# (a copy of Jay's maps from ai/spot_value.py, so the old engine can be measured against them too)
MAPS = {
    "LM": {"green": [(36.0, 97.0, -35.0, -26.0), (82.0, 100.0, -26.0, -9.0)], "shoot": [(83.0, 96.0, -17.0, -9.0)],
           "amber": [(27.0, 36.0, -35.0, -22.0), (36.0, 82.0, -26.0, -22.0), (97.0, 110.0, -35.0, -26.0),
                     (100.0, 110.0, -26.0, -9.0), (82.0, 110.0, -9.0, -4.0)]},
    "RM": {"green": [(36.0, 110.0, 26.0, 35.0), (97.0, 110.0, 21.0, 26.0), (101.0, 110.0, 13.0, 21.0)], "shoot": [],
           "amber": [(27.0, 97.0, 22.0, 26.0), (27.0, 36.0, 26.0, 35.0)]},
}
inside = lambda rs, a, l: any(a0 <= a <= a1 and l0 <= l <= l1 for a0, a1, l0, l1 in rs)


def where(role, a, l):
    m = MAPS[role]
    if inside(m["shoot"], a, l):
        return "yellow"
    if inside(m["green"], a, l):
        return "green"
    if inside(m["amber"], a, l):
        return "amber"
    return "outside"


def frame(team, x, y):
    return (x, y - 35.0) if team == 0 else (110.0 - x, 35.0 - y)


def seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)), t * math.sqrt(L2)


E = {"e": None}
EV = []                                            # (team, role, kind, where)


def _hook(kind):
    orig = getattr(mech.GameMechanics, "execute_" + kind)

    def f(self, player, *a, **k):
        e_ = E["e"]
        if e_ is not None and player.role in ("LM", "RM") and e_.match_state in ("first_half", "second_half"):
            pa, pl = frame(player.team, player.pos.x / M_TO_PX, player.pos.y / M_TO_PX)
            EV.append((player.team, player.role, kind, where(player.role, pa, pl), pa))
        return orig(self, player, *a, **k)
    setattr(mech.GameMechanics, "execute_" + kind, f)


for k in ("shot", "cross", "pass"):
    _hook(k)

R, GOT = {}, {}
both = bool(os.environ.get("WIDE_BOTH"))
for seed in seeds:
    random.seed(seed)
    with contextlib.redirect_stdout(io.StringIO()):
        me.RL_ENABLED = False
        me.HALF_DURATION_REAL = half
        e = me.MatchEngine(career=True)
    E["e"] = e
    if both:
        for q in e.team0 + e.team1:
            if q.role == "LM":
                q.role_style = "LM_blue"
            elif q.role == "RM":
                q.role_style = "RM_blue"
    random.seed(seed)
    n = 0
    last_owner = None
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        while e.match_state != "full_time" and n < 2_000_000:
            e.step(1 / 60); n += 1
            if n % 600 == 0:
                sink.seek(0); sink.truncate(0)
            if e.match_state not in ("first_half", "second_half"):
                last_owner = None
                continue
            b = e.ball
            c = b.owner
            if c is not None and c is not last_owner and last_owner is not None and last_owner.team == c.team \
                    and c.role in ("LM", "RM") and not b.is_dead:
                pa, pl = frame(c.team, c.pos.x / M_TO_PX, c.pos.y / M_TO_PX)
                GOT.setdefault(f"t{c.team} {c.role}" if both else c.role, []).append((where(c.role, pa, pl), pa))
            if c is not None:
                last_owner = c
            if n % 30 or c is None or b.is_dead:
                continue
            team, other = (e.team0, e.team1) if c.team == 0 else (e.team1, e.team0)
            gk = next((p for p in team if p.role == "GK"), None)
            dirn = 1 if (gk is not None and gk.pos.x < WIDTH / 2) else -1
            m = lambda v: (v.x / M_TO_PX, v.y / M_TO_PX)
            cx, cy = m(c.pos)
            opps = [m(o.pos) for o in other if getattr(o, "is_active", True)]
            for role in ("LM", "RM"):
                p = next((q for q in team if q.role == role), None)
                if p is None or p is c:
                    continue
                px, py = m(p.pos)
                pa, pl = frame(c.team, px, py)
                height = (px - cx) * dirn
                d = math.hypot(px - cx, py - cy)
                lane_ok = all(not (seg(ox, oy, cx, cy, px, py)[0] < 2.0 and seg(ox, oy, cx, cy, px, py)[1] > 3.0)
                              for ox, oy in opps)
                free = height > 3.0 and lane_ok and min(math.hypot(ox - px, oy - py) for ox, oy in opps) > 3.0 \
                    and d <= 40.0
                ba, _ = frame(c.team, cx, cy)
                R.setdefault(f"t{c.team} {role}" if both else role, []).append(
                    {"where": where(role, pa, pl), "a": pa, "across": pl, "height": height, "dist": d,
                     "free": 1 if free else 0, "ball_third": min(2, int(ba / 36.7)), "why": getattr(p, "pos_reason", "")})
    print(f"seed {seed} done", file=sys.stderr, flush=True)


def med(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


def summ(rs):
    if not rs:
        return None
    pc = lambda f: round(100.0 * sum(1 for r in rs if f(r)) / len(rs), 1)
    d = {"n": len(rs), "green %": pc(lambda r: r["where"] == "green"), "yellow %": pc(lambda r: r["where"] == "yellow"),
         "amber %": pc(lambda r: r["where"] == "amber"), "outside %": pc(lambda r: r["where"] == "outside"),
         "free ahead %": pc(lambda r: r["free"]), "height median": round(med(r["height"] for r in rs), 1),
         "across median": round(med(r["across"] for r in rs), 1), "dist median": round(med(r["dist"] for r in rs), 1)}
    for th, name in ((0, "ball own third"), (1, "ball middle third"), (2, "ball final third")):
        sub = [r for r in rs if r["ball_third"] == th]
        if sub:
            d[name] = {"n": len(sub), "in green/yellow %": round(100.0 * sum(r["where"] in ("green", "yellow") for r in sub) / len(sub), 1),
                       "outside %": round(100.0 * sum(r["where"] == "outside" for r in sub) / len(sub), 1),
                       "a median": round(med(r["a"] for r in sub), 1), "across median": round(med(r["across"] for r in sub), 1)}
    return d


def why(rs):
    c = {}
    for r in rs:
        w = r["why"].split(":")[0].split("(")[0].strip()[:40]
        c[w] = c.get(w, 0) + 1
    return {k: round(100.0 * v / max(1, len(rs)), 1) for k, v in sorted(c.items(), key=lambda kv: -kv[1])[:8]}


res = {"positions": {k: summ(v) for k, v in sorted(R.items())}, "received": {}, "on the ball": {},
       "points": {k: [(round(r["a"], 1), round(r["across"], 1), r["where"]) for r in v] for k, v in sorted(R.items())},
       "why": {k: why(v) for k, v in sorted(R.items())},
       "why when outside": {k: why([r for r in v if r["where"] == "outside"]) for k, v in sorted(R.items())},
       "outside where": {k: {"a median": med(r["a"] for r in v if r["where"] == "outside"),
                             "across median": med(r["across"] for r in v if r["where"] == "outside")}
                         for k, v in sorted(R.items())}}
for k, v in sorted(GOT.items()):
    res["received"][k] = {"n": len(v), **{w: round(100.0 * sum(1 for x in v if x[0] == w) / len(v), 1)
                                          for w in ("green", "yellow", "amber", "outside")},
                          "median m up the pitch": round(med(x[1] for x in v), 1)}
for t in (0, 1):
    for role in ("LM", "RM"):
        evs = [x for x in EV if x[1] == role and (x[0] == t or not both)]
        if not evs:
            continue
        key = f"t{t} {role}" if both else role
        sh = [x for x in evs if x[2] == "shot"]
        res["on the ball"][key] = {"shots": len(sh), "shots from yellow": sum(1 for x in sh if x[3] == "yellow"),
                                   "crosses": sum(1 for x in evs if x[2] == "cross"),
                                   "passes": sum(1 for x in evs if x[2] == "pass")}
    if not both:
        break
res["goals"] = None
json.dump(res, open(out, "w"))
print(json.dumps({k: v for k, v in res.items() if k != "points"}, indent=1))
