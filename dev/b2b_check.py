"""The two central midfielders when their team has the ball (25 Nov): the left one (box-to-box, his own area -
ai/spot_value.py _zone_best) against the right one (as before).
usage: python dev/b2b_check.py <engine_dir> <seeds e.g. 1,2,3> <seconds per half> <out.json>
Every half a second in open play, for the team with the ball:
  height     how far up the pitch the LCM / RCM is compared with the ball (m; + = ahead of it)
  dist       how far from the ball
  free_ahead he's 3 m+ ahead of the ball and free for a pass (no opponent within 2 m of the line of the pass, nobody
             within 3 m of him)
And the moment Jay watched: a centre-back on the ball with nobody within 8 m of him - where are the two midfielders?
Also one snapshot of that moment (positions of all 22) for a picture.
B2B_BOTH=1: both teams play both central midfielders as box-to-boxes (LCM_blue), and the results are split by team
(team 0 kicks left to right, team 1 right to left).  across = m from the middle, his team's left minus."""
import os, sys, io, contextlib, random, json, math

eng, seeds, half, out = sys.argv[1], [int(s) for s in sys.argv[2].split(",")], float(sys.argv[3]), sys.argv[4]
os.chdir(eng); sys.path.insert(0, eng)
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("FM_MATCH_CONFIG", "match_config_benchmark.json")
with contextlib.redirect_stdout(io.StringIO()):
    import gameplay.match_engine as me
    from config.constants import M_TO_PX, WIDTH


def seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 < 1e-9 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)), t * math.sqrt(L2)


R = {}
CBFREE = {}
snaps = []
for seed in seeds:
    random.seed(seed)
    with contextlib.redirect_stdout(io.StringIO()):
        me.RL_ENABLED = False
        me.HALF_DURATION_REAL = half
        e = me.MatchEngine(career=True)
    if os.environ.get("B2B_BOTH"):
        for q in e.team0 + e.team1:
            if q.role in ("LCM", "RCM"):
                q.role_style = "LCM_blue"
    random.seed(seed)
    n = 0
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        while e.match_state != "full_time" and n < 2_000_000:
            e.step(1 / 60); n += 1
            if n % 600 == 0:
                sink.seek(0); sink.truncate(0)
            if n % 30 or e.match_state not in ("first_half", "second_half"):
                continue
            b = e.ball
            c = b.owner
            if c is None or b.is_dead:
                continue
            team, other = (e.team0, e.team1) if c.team == 0 else (e.team1, e.team0)
            gk = next((p for p in team if p.role == "GK"), None)
            dirn = 1 if (gk is not None and gk.pos.x < WIDTH / 2) else -1
            m = lambda v: (v.x / M_TO_PX, v.y / M_TO_PX)
            cx, cy = m(c.pos)
            opps = [m(o.pos) for o in other if getattr(o, "is_active", True)]
            near_c = min(math.hypot(x - cx, y - cy) for x, y in opps)
            cb_free = c.role in ("LCB", "RCB") and near_c > 8.0
            for role in ("LCM", "RCM"):
                p = next((q for q in team if q.role == role), None)
                if p is None or p is c:
                    continue
                px, py = m(p.pos)
                across = (py - 35.0) if c.team == 0 else (35.0 - py)
                height = (px - cx) * dirn
                d = math.hypot(px - cx, py - cy)
                lane_ok = all(not (seg(ox, oy, cx, cy, px, py)[0] < 2.0 and seg(ox, oy, cx, cy, px, py)[1] > 3.0)
                              for ox, oy in opps)
                free = height > 3.0 and lane_ok and min(math.hypot(ox - px, oy - py) for ox, oy in opps) > 3.0 \
                    and d <= 40.0
                rec = {"across": across, "height": height, "dist": d, "free_ahead": 1 if free else 0,
                       "why": getattr(p, "pos_reason", "")}
                key = f"t{c.team} {role}" if os.environ.get("B2B_BOTH") else role
                R.setdefault(key, []).append(rec)
                if cb_free:
                    CBFREE.setdefault(key, []).append(rec)
            if cb_free and len(snaps) < 3 * len(seeds) and e.time_elapsed > 20 and \
                    (not snaps or e.time_elapsed - snaps[-1]["t"] > 30 or snaps[-1]["seed"] != seed):
                snaps.append({"seed": seed, "t": e.time_elapsed, "dirn": dirn, "carrier": c.role, "ball": (cx, cy),
                              "mine": [(m(q.pos), q.role, getattr(q, "pos_reason", "")) for q in team],
                              "theirs": [(m(q.pos), q.role) for q in other]})
    print(f"seed {seed} done", file=sys.stderr, flush=True)


def summ(rs):
    if not rs:
        return None
    hs = sorted(r["height"] for r in rs)
    return {"n": len(rs), "height median m": hs[len(hs) // 2], "ahead of the ball %": 100 * sum(h > 0 for h in hs) / len(hs),
            "free ahead %": 100 * sum(r["free_ahead"] for r in rs) / len(rs),
            "distance from the ball median m": sorted(r["dist"] for r in rs)[len(rs) // 2],
            "across median m": sorted(r["across"] for r in rs)[len(rs) // 2]}


def reasons(rs):
    c = {}
    for r in rs:
        w = r["why"]
        k = ("his area: show high" if "show high in his area" in w else "his area: nothing on, waiting" if "hold his area" in w
             else "helping a pressed team-mate" if w.startswith("support") and "(" in w else "filling a gap" if "fill the gap" in w
             else "making a run" if ("run" in w or "overlap" in w or "beyond" in w or "box" in w) else "team shape / other")
        c[k] = c.get(k, 0) + 1
        if "(green)" in w or "(amber)" in w:
            g = "in green" if "(green)" in w else "in amber"
            c[g] = c.get(g, 0) + 1
    return {k: round(100 * v / max(1, len(rs)), 1) for k, v in sorted(c.items(), key=lambda kv: -kv[1])}


res = {"all": {k: summ(v) for k, v in R.items()}, "cb free": {k: summ(v) for k, v in CBFREE.items()}, "snaps": snaps,
       "reasons": {k: reasons(v) for k, v in R.items()}}
json.dump(res, open(out, "w"))
print("why", res["reasons"])
for k in ("all", "cb free"):
    print(k)
    for role in sorted(res[k]):
        print("  ", role, {a: (round(b, 1) if isinstance(b, float) else b) for a, b in (res[k][role] or {}).items()})
