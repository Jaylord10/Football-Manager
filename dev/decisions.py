"""What was he thinking? (26 Nov - the decision scoreboard, ai/scoreboard.py)
Plays a match with the scoreboard on and the decision log on, then shows what was chosen how often, and for any
moment every option the man on the ball had with its value (the chance his team scores from it, xT / xG units).
usage: python dev/decisions.py <engine_dir> <seed> <seconds per half> <out.json> [show N moments]"""
import os, sys, io, contextlib, random, json, collections

eng, seed, half, out = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
show = int(sys.argv[5]) if len(sys.argv) > 5 else 6
os.environ["FM_DECIDE"] = "scoreboard"
os.environ["FM_DECISION_LOG"] = "1"
os.chdir(eng); sys.path.insert(0, eng)
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("FM_MATCH_CONFIG", "match_config_benchmark.json")
with contextlib.redirect_stdout(io.StringIO()):
    import gameplay.match_engine as me
    import ai.scoreboard as sb
random.seed(seed)
with contextlib.redirect_stdout(io.StringIO()):
    me.RL_ENABLED = False
    me.HALF_DURATION_REAL = half
    e = me.MatchEngine(career=True)
random.seed(seed)
n = 0
sink = io.StringIO()
with contextlib.redirect_stdout(sink):
    while e.match_state != "full_time" and n < 2_000_000:
        e.step(1 / 60); n += 1
        if n % 600 == 0:
            sink.seek(0); sink.truncate(0)
c = collections.Counter(d["chose"] for d in sb.LOG)
tot = sum(c.values())
print("score", e.score, "decisions", tot)
print({k: f"{100 * v / tot:.0f}%" for k, v in c.most_common()})
random.seed(1)
for d in random.sample(sb.LOG, min(show, len(sb.LOG))):
    print(f"\n{d['t']:.0f}s team {d['team']} {d['role']} at ({d['a']}, {d['l']}), nearest man {d['nearest']} m -> {d['chose']} {d['target']}")
    for o in d["options"]:
        print(f"    {o['kind']:8s} {o['target']:10s} worth {o['value']:+.4f}  (as he saw it {o['judged']:+.4f})  comes off {o['p']:.2f}")
json.dump({"score": e.score, "chosen": dict(c), "log": sb.LOG}, open(out, "w"))
