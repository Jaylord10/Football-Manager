"""Passing decisions in OUR match engine: the same measures as dev/pass_real.py (dev/pass_measures.py).
usage: python dev/pass_engine.py <engine_dir> <seeds e.g. 1,2,3> <seconds_of_football_per_half> [out.json]
Every open-play pass and cross (not set pieces), both teams."""
import os, sys, io, contextlib, random, json, math

eng, seeds, half = sys.argv[1], [int(s) for s in sys.argv[2].split(",")], float(sys.argv[3])
out = sys.argv[4] if len(sys.argv) > 4 else None
DEV = os.path.dirname(os.path.abspath(__file__))
os.chdir(eng); sys.path.insert(0, eng); sys.path.insert(0, DEV)
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("FM_MATCH_CONFIG", "match_config_benchmark.json")
import pass_measures as pm
with contextlib.redirect_stdout(io.StringIO()):
    import gameplay.match_engine as me
    import gameplay.mechanics as mech
    from config.constants import M_TO_PX, WIDTH

L = WIDTH / M_TO_PX
E = {"engine": None}
passes, pending = [], []
got = {}                                   # id(player) -> (time, (x, y) m) he got it


def _record(passer, receiver, ball, t):
    e = E["engine"]
    if e is None or ball.is_dead or getattr(ball, "restart_taker", None) is passer:
        return
    team, other = (e.team0, e.team1) if passer.team == 0 else (e.team1, e.team0)
    gk = next((p for p in team if p.role == "GK"), None)
    dirn = 1 if (gk is not None and gk.pos.x < WIDTH / 2) else -1
    x0, y0 = passer.pos.x / M_TO_PX, passer.pos.y / M_TO_PX
    x1, y1 = receiver.pos.x / M_TO_PX, receiver.pos.y / M_TO_PX
    dx, dy = (x1 - x0) * dirn, (y1 - y0) * dirn
    near = min(((p.pos - passer.pos).length() / M_TO_PX for p in other if getattr(p, "is_active", True)), default=99)
    depth = x0 if dirn > 0 else L - x0
    rec = dict(dx=dx, dy=dy, length=math.hypot(dx, dy), pressed=near < pm.PRESS_M, ok=False, near=near,
               zone=min(2, int(3 * depth / L)), hold=None, carry=None, team=passer.team)
    g = got.get(id(passer))
    if g and 0 <= t - g[0] < 30:
        rec["hold"] = t - g[0]
        rec["carry"] = math.hypot(x0 - g[1][0], y0 - g[1][1])
    pending.append(rec)


_pass, _cross = mech.GameMechanics.execute_pass, mech.GameMechanics.execute_cross
_clear = mech.GameMechanics.execute_clearance
CLEAR = [0]


def execute_clearance(self, player, ball, *a, **k):
    if not ball.is_dead:
        CLEAR[0] += 1
    return _clear(self, player, ball, *a, **k)


def execute_pass(self, passer, receiver, ball, current_time, *a, **k):
    _record(passer, receiver, ball, current_time)
    return _pass(self, passer, receiver, ball, current_time, *a, **k)


def execute_cross(self, passer, receiver, ball, current_time, *a, **k):
    _record(passer, receiver, ball, current_time)
    return _cross(self, passer, receiver, ball, current_time, *a, **k)


mech.GameMechanics.execute_pass = execute_pass
mech.GameMechanics.execute_cross = execute_cross
mech.GameMechanics.execute_clearance = execute_clearance

for seed in seeds:
    random.seed(seed)
    with contextlib.redirect_stdout(io.StringIO()):
        me.RL_ENABLED = False
        me.HALF_DURATION_REAL = half
        e = me.MatchEngine(career=True)
    E["engine"] = e
    random.seed(seed)
    n, last_owner = 0, None
    got.clear(); pending.clear()
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        while e.match_state != "full_time" and n < 600000:
            e.step(1 / 60); n += 1
            if n % 600 == 0:
                sink.seek(0); sink.truncate(0)
            b = e.ball
            o = b.owner
            if o is not None and o is not last_owner:
                got[id(o)] = (e.time_elapsed, (o.pos.x / M_TO_PX, o.pos.y / M_TO_PX))
                for r in pending:                      # (the pass is settled: whose is it now?)
                    r["ok"] = (o.team == r["team"])
                    passes.append(r)
                pending.clear()
            elif b.is_dead and pending:
                passes += pending                      # (out of play, or a foul: it didn't get there)
                pending.clear()
            last_owner = o
    print(f"seed {seed}: {len(passes)} passes so far", file=sys.stderr, flush=True)

res = pm.summarise(passes)
if out:
    json.dump(res, open(out, "w"), indent=1)
pm.show(res)
ds = sorted(p["near"] for p in passes)
for r in (2, 3, 4.5, 6):
    print(f"passes with an opponent within {r} m: {100 * sum(d < r for d in ds) / len(ds):.0f}%")
print("median nearest opponent", round(ds[len(ds) // 2], 1), "m")
print("clearances per 100 open-play passes", round(100 * CLEAR[0] / len(passes), 1))
