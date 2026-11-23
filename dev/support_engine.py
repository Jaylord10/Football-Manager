"""Showing for the ball in OUR match engine: the same measures as dev/support_real.py (dev/support_measures.py).
usage: python dev/support_engine.py <engine_dir> <seeds e.g. 1,2,3> <seconds_of_football_per_half> [out.json]
Moments every 0.5 s while a player has the ball in open play, both teams."""
import os, sys, io, contextlib, random, json

eng, seeds, half = sys.argv[1], [int(s) for s in sys.argv[2].split(",")], float(sys.argv[3])
out = sys.argv[4] if len(sys.argv) > 4 else None
DEV = os.path.dirname(os.path.abspath(__file__))
os.chdir(eng); sys.path.insert(0, eng); sys.path.insert(0, DEV)
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("FM_MATCH_CONFIG", "match_config_benchmark.json")
import support_measures as sm
with contextlib.redirect_stdout(io.StringIO()):
    import gameplay.match_engine as me
    from config.constants import M_TO_PX, WIDTH

L = WIDTH / M_TO_PX
moments = []
for seed in seeds:
    random.seed(seed)
    with contextlib.redirect_stdout(io.StringIO()):
        me.RL_ENABLED = False
        me.HALF_DURATION_REAL = half
        e = me.MatchEngine(career=True)
    random.seed(seed)
    n = 0
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        while e.match_state != "full_time" and n < 600000:
            e.step(1 / 60); n += 1
            if n % 600 == 0:
                sink.seek(0); sink.truncate(0)
            if n % 30:
                continue
            b = e.ball
            c = b.owner
            if c is None or b.is_dead or e.match_state not in ("first_half", "second_half"):
                continue
            team, other = (e.team0, e.team1) if c.team == 0 else (e.team1, e.team0)
            gk = next((p for p in team if p.role == "GK"), None)
            direction = 1 if (gk is not None and gk.pos.x < WIDTH / 2) else -1
            mates = [(p.pos.x / M_TO_PX, p.pos.y / M_TO_PX, p.vel.x / M_TO_PX, p.vel.y / M_TO_PX)
                     for p in team if p is not c and p is not gk and getattr(p, "is_active", True)]
            opps = [(p.pos.x / M_TO_PX, p.pos.y / M_TO_PX) for p in other if getattr(p, "is_active", True)]
            moments.append(sm.moment((c.pos.x / M_TO_PX, c.pos.y / M_TO_PX), direction, mates, opps, L))
    print(f"seed {seed}: {len(moments)} moments so far", file=sys.stderr, flush=True)

res = sm.summarise(moments)
if out:
    json.dump(res, open(out, "w"), indent=1)
for z, d in res.items():
    print(z, {k: round(v, 2) for k, v in d.items()})
