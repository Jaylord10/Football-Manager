"""Seeded headless replay: prints a fingerprint of every frame + timing.
usage: python replay.py <engine_dir> <seed> <seconds_of_football_per_half> [trace_out]"""
import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
GAME = _os.environ.get("FM_GAME", _os.path.dirname(DEV))   # the game folder (default: this repo)
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")

import os, sys, io, contextlib, time, random, hashlib
eng, seed, half = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
out = sys.argv[4] if len(sys.argv) > 4 else None
NOHASH = out == "nohash"
if NOHASH: out = None
os.chdir(eng); sys.path.insert(0, eng)
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["FM_MATCH_CONFIG"] = "match_config_benchmark.json"
random.seed(seed)
with contextlib.redirect_stdout(io.StringIO()):
    import gameplay.match_engine as me
    me.RL_ENABLED = False
    me.HALF_DURATION_REAL = half
    e = me.MatchEngine(career=True)
random.seed(seed)
import gc
GC = os.environ.get("FM_GC")
if GC == "freeze": gc.collect(); gc.freeze()
if GC == "high": gc.collect(); gc.freeze(); gc.set_threshold(50000, 50, 100)
h = hashlib.md5(); lines = []
t0 = time.time(); n = 0
sink = io.StringIO()
with contextlib.redirect_stdout(sink):
    while e.match_state != "full_time" and n < 400000:
        e.step(1/60); n += 1
        if NOHASH:
            if n % 600 == 0: sink.seek(0); sink.truncate(0)
            continue
        s = "%d %r %r %r|" % (n, e.ball.pos.x, e.ball.pos.y, getattr(e.ball, "z", 0.0))
        s += "".join("%r,%r,%r,%r,%s;" % (p.pos.x, p.pos.y, p.vel.x, p.vel.y, p.state) for p in e.team0 + e.team1)
        h.update(s.encode())
        if out and n % 60 == 0: lines.append(s)
        if n % 600 == 0: sink.seek(0); sink.truncate(0)
wall = time.time() - t0
r = e.result()
print("frames", n, "wall %.1f" % wall, "score %d-%d" % (r["hg"], r["ag"]), "hash", h.hexdigest())
if out: open(out, "w").write("\n".join(lines))
