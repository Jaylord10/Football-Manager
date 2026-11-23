"""Their keeper with the ball against a press (23 Nov): blue (team 0) on a defensive style; every so often in
open play red's keeper is handed the ball (in his hands, or at his feet) and we watch blue for the next 3 seconds.
usage: python dev/press_keeper.py <engine_dir> <style> <hands|feet> <seeds e.g. 1,2> [seconds_per_half]
Prints: how close blue's nearest man gets, how many blue are within 10 m of him, what the nearest are doing,
and how the keeper got rid of it (short / long)."""
import os, sys, io, contextlib, random

eng, style, mode, seeds = sys.argv[1], sys.argv[2], sys.argv[3], [int(s) for s in sys.argv[4].split(",")]
half = float(sys.argv[5]) if len(sys.argv) > 5 else 150.0
os.chdir(eng); sys.path.insert(0, eng)
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["FM_MATCH_CONFIG"] = "match_config_benchmark.json"
with contextlib.redirect_stdout(io.StringIO()):
    import gameplay.match_engine as me
    import gameplay.goalkeeping as gk_mod
    import ai.tactics as tactics
    from config.constants import M_TO_PX

EVERY, WATCH = 20.0, 3.0
N = dict(tests=0, frames=0, nearest=0.0, within10=0, within5=0, short=0, long=0, lost=0)
WHO = {}
for seed in seeds:
    random.seed(seed)
    with contextlib.redirect_stdout(io.StringIO()):
        me.RL_ENABLED = False
        me.HALF_DURATION_REAL = half
        tactics.OVERRIDE[0] = style
        e = me.MatchEngine(career=True)
    random.seed(seed)
    next_t, watch_until, keeper = EVERY, -1.0, None
    sink = io.StringIO()
    n = 0
    with contextlib.redirect_stdout(sink):
        while e.match_state != "full_time" and n < 400000:
            e.step(1 / 60); n += 1
            if n % 600 == 0:
                sink.seek(0); sink.truncate(0)
            t = e.time_elapsed
            b = e.ball
            if keeper is None and t >= next_t and not b.is_dead and e.match_state in ("first_half", "second_half"):
                k = next(p for p in e.team1 if p.role == "GK")
                if b.owner is not None:
                    b.owner.has_ball = False
                b.pos = k.pos.__class__(k.pos)
                gk_mod._claim(k, b, t, e.ai, feet=(mode == "feet"))
                keeper, watch_until = k, t + WATCH
                N["tests"] += 1
                continue
            if keeper is not None:
                if b.owner is keeper:
                    ds = sorted(((p.pos - keeper.pos).length() / M_TO_PX, p) for p in e.team0
                                if getattr(p, "is_active", True))
                    N["frames"] += 1
                    N["nearest"] += ds[0][0]
                    N["within10"] += sum(1 for d, _ in ds if d < 10)
                    N["within5"] += ds[0][0] < 5
                    for d, p in ds[:3]:
                        key = f"{p.role}: {getattr(p, 'pos_reason', '') or p.state}"
                        WHO[key] = WHO.get(key, 0) + 1
                else:
                    if b.owner is None and not b.is_dead and b.last_toucher is keeper:
                        sp = b.vel.length() / M_TO_PX
                        N["long" if (getattr(b, "vz", 0.0) > 2.0 or sp > 22) else "short"] += 1
                    elif b.owner is not None and b.owner.team == 0:
                        N["lost"] += 1
                    keeper, next_t = None, t + EVERY
                    continue
                if t > watch_until + 6.0:
                    keeper, next_t = None, t + EVERY

f = max(1, N["frames"])
print(f"style {style}, keeper with it in his {mode}: {N['tests']} times")
print(f"  nearest blue {N['nearest'] / f:.1f} m on average; {N['within10'] / f:.2f} blue within 10 m;"
      f" someone within 5 m {100 * N['within5'] / f:.0f}% of the time")
print(f"  he played it short {N['short']}, long {N['long']}, lost it {N['lost']}")
for k, v in sorted(WHO.items(), key=lambda kv: -kv[1])[:6]:
    print(f"    one of the 3 nearest: {k}  ({100 * v / f:.0f}% of the time)")
