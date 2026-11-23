"""How a pressing team behaves (23 Nov): blue (team 0) on a chosen defensive style, red as set.
usage: python dev/press_check.py <engine_dir> <style> <seeds e.g. 1,2,3> <seconds_of_football_per_half>
Prints, over the matches:
  keeper in hands : how close blue's nearest man gets to red's keeper while he holds it, and how many are within 10 m
  keeper at feet  : the same with it at his feet
  open play       : how many blue players are within 8 m of red's man on the ball (and how often 3 or more are)
  wins high       : times blue won the ball in red's third, per match; goals."""
import os, sys, io, contextlib, random

eng, style, seeds, half = sys.argv[1], sys.argv[2], [int(s) for s in sys.argv[3].split(",")], float(sys.argv[4])
os.chdir(eng); sys.path.insert(0, eng)
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["FM_MATCH_CONFIG"] = "match_config_benchmark.json"
with contextlib.redirect_stdout(io.StringIO()):
    import gameplay.match_engine as me
    import ai.tactics as tactics
    from config.constants import M_TO_PX, WIDTH

REASONS = {}
tot = dict(hands=0, hands_min=0.0, hands_10=0, hands_5=0, feet=0, feet_10=0, open=0, open_n=0, open_3=0,
           wins_high=0, goals=[0, 0], matches=0)
for seed in seeds:
    random.seed(seed)
    with contextlib.redirect_stdout(io.StringIO()):
        me.RL_ENABLED = False
        me.HALF_DURATION_REAL = half
        tactics.OVERRIDE[0] = style
        e = me.MatchEngine(career=True)
    random.seed(seed)
    n = 0
    last_owner_team = None
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink):
        while e.match_state != "full_time" and n < 400000:
            e.step(1 / 60); n += 1
            if n % 600 == 0:
                sink.seek(0); sink.truncate(0)
            b = e.ball
            o = b.owner
            if o is None or b.is_dead or e.match_state not in ("first_half", "second_half"):
                continue
            if o.team != last_owner_team:
                if o.team == 0 and last_owner_team == 1:
                    attack_right = True                      # (blue attack the right-hand goal in the first half)
                    if e.match_state == "second_half":
                        attack_right = False
                    x = o.pos.x / WIDTH
                    if (x > 2 / 3) if attack_right else (x < 1 / 3):
                        tot["wins_high"] += 1
                last_owner_team = o.team
            if o.team != 1:
                continue
            ds = sorted((p.pos - o.pos).length() / M_TO_PX for p in e.team0 if getattr(p, "is_active", True))
            if o.role == "GK":
                if getattr(o, "_feet", False):
                    tot["feet"] += 1
                    tot["feet_10"] += sum(1 for d in ds if d < 10)
                else:
                    tot["hands"] += 1
                    tot["hands_min"] += ds[0]
                    tot["hands_10"] += sum(1 for d in ds if d < 10)
                    tot["hands_5"] += ds[0] < 5
                    if ds[0] < 5:
                        near = min((p for p in e.team0 if getattr(p, "is_active", True)), key=lambda p: (p.pos - o.pos).length())
                        key = f"{near.role}:{near.state}:{getattr(near, 'pos_reason', '')}"
                        REASONS[key] = REASONS.get(key, 0) + 1
            else:
                k = sum(1 for d in ds if d < 8)
                tot["open"] += 1
                tot["open_n"] += k
                tot["open_3"] += k >= 3
    r = e.result()
    tot["goals"][0] += r["hg"]; tot["goals"][1] += r["ag"]
    tot["matches"] += 1

h, f, op, m = max(1, tot["hands"]), max(1, tot["feet"]), max(1, tot["open"]), tot["matches"]
print(f"style {style}, {m} matches")
print(f"  keeper in hands: nearest blue {tot['hands_min'] / h:.1f} m on average, {tot['hands_10'] / h:.2f} blue within 10 m,"
      f" someone within 5 m {100 * tot['hands_5'] / h:.0f}% of the time")
print(f"  keeper at feet : {tot['feet_10'] / f:.2f} blue within 10 m")
print(f"  open play      : {tot['open_n'] / op:.2f} blue within 8 m of the ball, 3 or more {100 * tot['open_3'] / op:.1f}% of the time")
print(f"  wins in their third: {tot['wins_high'] / m:.1f} a match;  goals blue {tot['goals'][0]} red {tot['goals'][1]}")
for k, v in sorted(REASONS.items(), key=lambda kv: -kv[1])[:8]:
    print(f"    nearest man within 5 m of the keeper: {k}  ({v} frames)")
