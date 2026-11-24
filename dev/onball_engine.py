"""On the ball, frame by frame, in OUR engine (24 Nov): the same measures as dev/onball_real.py, plus what the
engine itself was doing in each spell on the ball (ai/carrier.py + ai/decision_timing.py).
usage: FM_MATCH_CONFIG=<config.json> python dev/onball_engine.py <engine_dir> <seed> <out.json> [seconds per half]

For every pass a player received and then played on himself (a pass, a cross or a shot):
  the same as the real side - on_ball, control, after, first_time, carry, speed_in, press_in, press_out, kind, dir,
  zone - and from the engine:
  e_first     s from getting it to his first decision (first touch + the look, unless he'd already scanned)
  e_picture   1 if he'd scanned before it arrived (skipped the look)
  e_decide    s from his first decision to committing to the pass / shot (waiting for a good enough option)
  e_checks    how many times he looked at his options before committing
  e_setup     s setting the pass / shot (committed -> ball struck)
  e_hurried   1 if he rushed it (a man closing)
"""
import os, sys, io, contextlib, random, json, math

eng, seed, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
half = float(sys.argv[4]) if len(sys.argv) > 4 else 45 * 60.0
DEV = os.path.dirname(os.path.abspath(__file__))
os.chdir(eng); sys.path.insert(0, eng); sys.path.insert(0, DEV)
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("FM_MATCH_CONFIG", "match_config_benchmark.json")
import onball_real as obr
with contextlib.redirect_stdout(io.StringIO()):
    import gameplay.match_engine as me
    import gameplay.mechanics as mech
    from config.constants import M_TO_PX, WIDTH

L = WIDTH / M_TO_PX
FPS = 60
KICKS = []                                         # (time, kind, player, receiver)


def _hook(kind):
    orig = getattr(mech.GameMechanics, "execute_" + kind)

    def f(self, player, *a, **k):
        KICKS.append((E["e"].time_elapsed, kind, player, a[0] if a and kind in ("pass", "cross") else None))
        return orig(self, player, *a, **k)
    setattr(mech.GameMechanics, "execute_" + kind, f)


E = {"e": None}
for k in ("pass", "cross", "shot", "clearance"):
    _hook(k)

random.seed(seed)
with contextlib.redirect_stdout(io.StringIO()):
    me.RL_ENABLED = False
    me.HALF_DURATION_REAL = half
    e = me.MatchEngine(career=True)
E["e"] = e
random.seed(seed)

# frame-by-frame positions (m) - kept for the current spell only
hist = {}                                          # frame -> {"p": {id: (x, y)}, "b": (x, y), "t": time}
spells = []
cur = None
last_owner = None
n = 0
sink = io.StringIO()


def mpos(v):
    return (v.x / M_TO_PX, v.y / M_TO_PX)


def close_spell(cur, f1, kick):
    """He's played it (kick = (time, kind, player, receiver)) at frame f1: measure the spell like the real side."""
    pid = cur["pid"]
    opp_ids = cur["opp_ids"]
    gp = lambda fr: hist[fr]["p"].get(pid) if fr in hist else None
    gb = lambda fr: hist[fr]["b"] if fr in hist else None
    go = lambda fr: [hist[fr]["p"][i] for i in opp_ids if i in hist[fr]["p"]] if fr in hist else []
    f0 = cur["f0"]
    if gp(f0) is None or gp(f1) is None:
        return None
    rec = obr.measure(None, gp, gb, go, f0, f1, FPS)
    kind = kick[1]
    rec["kind"] = "shot" if kind == "shot" else "pass"
    if kind in ("pass", "cross") and kick[3] is not None:
        dirn = cur["dirn"]
        r = mpos(kick[3].pos)
        p = gp(f1)
        dx, dy = (r[0] - p[0]) * dirn, (r[1] - p[1]) * dirn
        a = math.degrees(math.atan2(dy, dx))
        rec["dir"] = "forward" if -45 <= a <= 45 else "back" if abs(a) >= 135 else "sideways"
    x0 = gp(f0)[0]
    rec["zone"] = min(2, int(3 * (x0 if cur["dirn"] > 0 else L - x0) / L))
    t0 = cur["t0"]
    rec["e_first"] = (cur["first"] - t0) if cur["first"] is not None else None
    rec["e_picture"] = cur["picture"]
    rec["e_decide"] = (cur["commit"] - cur["first"]) if (cur["commit"] is not None and cur["first"] is not None) else None
    rec["e_checks"] = cur["checks"]
    rec["e_setup"] = (kick[0] - cur["commit"]) if cur["commit"] is not None else None
    rec["e_hurried"] = 1 if cur["hurried"] else 0
    rec["clearance"] = 1 if kind == "clearance" else 0
    return rec


with contextlib.redirect_stdout(sink):
    while e.match_state != "full_time" and n < 2_000_000:
        e.step(1 / FPS); n += 1
        if n % 600 == 0:
            sink.seek(0); sink.truncate(0)
        if e.match_state not in ("first_half", "second_half"):
            cur = None; last_owner = None; hist.clear(); KICKS.clear()
            continue
        b = e.ball
        t = e.time_elapsed
        hist[n] = {"p": {id(p): mpos(p.pos) for p in e.team0 + e.team1 if getattr(p, "is_active", True)},
                   "b": mpos(b.pos), "t": t}
        if len(hist) > 60 * 40:
            for k in sorted(hist)[:len(hist) - 60 * 40]:
                del hist[k]
        o = b.owner
        # follow what the engine is doing with the man on the ball
        if cur is not None and o is cur["player"]:
            st = getattr(o, "_timing", None)
            if st is not None and st is not cur["st"]:
                cur["st"] = st
                cur["first"] = st.get("next")
            if st is not None:
                if st.get("pending") is not None and cur["commit"] is None:
                    cur["commit"] = t
                    cur["hurried"] = bool(getattr(o, "_hurried", False))
                if st.get("next") != cur["last_next"]:
                    cur["last_next"] = st.get("next")
                    if cur["commit"] is None and t >= (cur["first"] or 0):
                        cur["checks"] += 1
        # he's played it (or lost it)
        if cur is not None and o is not cur["player"]:
            kick = next((k for k in reversed(KICKS) if k[2] is cur["player"] and k[0] >= cur["t0"]), None)
            if kick is not None and kick[1] in ("pass", "cross", "shot") and cur["from_pass"]:
                rec = close_spell(cur, n - 1, kick)
                if rec:
                    spells.append(rec)
            cur = None
        if o is not None and o is not last_owner and not b.is_dead:
            team, other = (e.team0, e.team1) if o.team == 0 else (e.team1, e.team0)
            gk = next((p for p in team if p.role == "GK"), None)
            prev_kick = KICKS[-1] if KICKS else None
            from_pass = bool(prev_kick and prev_kick[1] in ("pass", "cross") and prev_kick[2].team == o.team
                             and prev_kick[2] is not o and t - prev_kick[0] < 8.0)
            st = getattr(o, "_timing", None)
            cur = dict(player=o, pid=id(o), opp_ids=[id(p) for p in other], f0=n, t0=t, from_pass=from_pass,
                       dirn=1 if (gk is not None and gk.pos.x < WIDTH / 2) else -1,
                       st=st, first=st.get("next") if st else None, last_next=st.get("next") if st else None,
                       picture=1 if getattr(o, "_picture", False) else 0, commit=None, checks=0, hurried=False)
        last_owner = o

res = obr.summarise(spells)
json.dump({"summary": res, "records": spells}, open(out, "w"))
print(f"done: {len(spells)} spells")
