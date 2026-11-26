"""Jay's right winger (26 Nov: "he isn't trying to get high enough up the pitch - he should be aiming to get 1v1 against
the left back").  Jay's set-up for team 0: 4-3-3, full press, the right winger on the Winger role (RM_blue).
usage: python dev/winger_check.py <engine_dir> <seed> <seconds per half> <out.json>
Every half a second his team has the ball past its own third:
  gap     m between him and their back line (their offside line; + = he's that far behind it)
  fb_gap  m between him and their left back, up the pitch (+ = he's behind him)
  wide    m in from the right touchline
When he gets the ball: how far up, how many of them within 10 m (1 = one against one), the nearest one."""
import os, sys, io, contextlib, random, json, math

eng, seed, half, out = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
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
    database.TACTICS[0] = {"defence": "high_press", "build_up": "mixed"}
    db = formations.db
    if not hasattr(db, "formation") or db.formation is None:
        db.formation = {}
    db.formation[0] = ["GK", "LB", "LCB", "RCB", "RB", "DM", "LCM", "RCM", "LW", "RW", "ST"]
    e = me.MatchEngine(career=True)
for q in e.team0:
    if getattr(q, "slot", None) == "RW":
        q.role_style = "RM_blue"
random.seed(seed)
fr = lambda v: (v.x / M_TO_PX, v.y / M_TO_PX - 35.0)          # team 0 attacks left to right: its own frame
S, GOT = [], []
n = 0
last = None
prev_owner = None
sink = io.StringIO()
with contextlib.redirect_stdout(sink):
    while e.match_state != "full_time" and n < 2_000_000:
        e.step(1 / 60); n += 1
        if n % 600 == 0:
            sink.seek(0); sink.truncate(0)
        if e.match_state not in ("first_half", "second_half"):
            prev_owner = None
            continue
        b = e.ball
        o = b.owner
        rw = next((q for q in e.team0 if getattr(q, "slot", None) == "RW"), None)
        if rw is None:
            break
        opps = [q for q in e.team1 if getattr(q, "is_active", True)]
        if o is rw and prev_owner is not None and prev_owner is not rw and prev_owner.team == 0 and not b.is_dead:
            ra, rl = fr(rw.pos)
            ds = sorted(math.hypot(fr(q.pos)[0] - ra, fr(q.pos)[1] - rl) for q in opps)
            GOT.append({"a": ra, "within10": sum(d < 10 for d in ds), "nearest": ds[0]})
        if o is not None:
            prev_owner = o
            last = o.team
        if n % 30 or b.is_dead or last != 0:
            continue
        ba = fr(b.pos)[0]
        if ba < 36.7:
            continue
        depths = sorted((fr(q.pos)[0] for q in opps), reverse=True)
        line = max(depths[1], 55.0)
        lb = next((q for q in e.team1 if q.role == "LB"), None)       # (their left back: on our right)
        ra, rl = fr(rw.pos)
        S.append({"gap": line - ra, "fb_gap": (fr(lb.pos)[0] - ra) if lb else None, "wide": 35.0 - rl,
                  "ahead": ra - ba, "final": ba >= 73.3, "why": getattr(rw, "pos_reason", "")})
med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None
def summ(ss):
    return {"n": len(ss), "behind their back line m (median)": round(med([s["gap"] for s in ss]), 1),
            "within 3 m of their back line %": round(100.0 * sum(s["gap"] <= 3.0 for s in ss) / max(1, len(ss)), 1),
            "behind their left back m (median)": round(med([s["fb_gap"] for s in ss if s["fb_gap"] is not None]), 1),
            "in from the touchline m (median)": round(med([s["wide"] for s in ss]), 1),
            "ahead of the ball m (median)": round(med([s["ahead"] for s in ss]), 1)}
whys = {}
for s in S:
    k = s["why"].split("(")[0].strip()[-40:]
    whys[k] = whys.get(k, 0) + 1
res = {"ball in the middle third": summ([s for s in S if not s["final"]]),
       "ball in their third": summ([s for s in S if s["final"]]),
       "got the ball": {"n": len(GOT), "m up the pitch (median)": round(med([g["a"] for g in GOT]), 1) if GOT else None,
                        "in their third %": round(100.0 * sum(g["a"] >= 73.3 for g in GOT) / max(1, len(GOT)), 1),
                        "one against one % (1 of them within 10 m)": round(100.0 * sum(g["within10"] == 1 for g in GOT) / max(1, len(GOT)), 1),
                        "nearest of them m (median)": round(med([g["nearest"] for g in GOT]), 1) if GOT else None},
       "why": {k: round(100.0 * v / len(S), 1) for k, v in sorted(whys.items(), key=lambda kv: -kv[1])[:8]},
       "score": list(e.score)}
json.dump(res, open(out, "w"), indent=1)
print(json.dumps(res, indent=1))
