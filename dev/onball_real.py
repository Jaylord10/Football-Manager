"""On the ball, frame by frame, in REAL matches (24 Nov): how long players take from the ball arriving to playing
it on.  Metrica Sports' sample data: two professional matches, every player and the ball 25 times a second, and
the events (who passed to whom, which frame).
usage: python dev/onball_real.py <metrica data folder> <out.json>

For every pass a player received and then played on himself (his next action was a pass, a cross or a shot):
  on_ball      seconds from the ball arriving (the pass's end frame) to him playing it (his pass's start frame)
  control      seconds until the ball was under control: within 1.3 m of him, moving with him (under 2.5 m/s
               relative) for 3 frames in a row.  None = he never settled it: played first time
  after        on_ball - control: the time to get his head up, decide and set the pass
  first_time   1 if he never controlled it (or played it within 0.5 s)
  carry        metres he moved between getting it and playing it
  speed_in     how fast he was moving when it arrived (m/s)
  press_in     nearest opponent when it arrived (m);  press_out: when he played it
  kind         what he did: pass / shot;  dir: forward / sideways / back (for passes)
  zone         third of the pitch he got it in (0 own, 1 middle, 2 final)
"""
import csv, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support_real as sr

L, W, FPS = 105.0, 68.0, 25
CTRL_DIST, CTRL_REL, CTRL_FRAMES = 1.3, 2.5, 3


def ball_track(folder, g):
    """frame -> (x, y) of the ball, from the home file."""
    base = os.path.join(folder, f"Sample_Game_{g}", f"Sample_Game_{g}_")
    out = {}
    with open(base + "RawTrackingData_Home_Team.csv") as f:
        r = csv.reader(f)
        next(r); next(r); next(r)
        for row in r:
            try:
                x, y = float(row[-2]), float(row[-1])
            except ValueError:
                continue
            if math.isnan(x) or math.isnan(y):
                continue
            out[int(row[1])] = (x * L, y * W)
    return out


def measure(frames, get_player, get_ball, get_opps, f0, f1, fps):
    """The shared measure: f0 the frame it arrived, f1 the frame he played it.  get_*(frame) -> positions (m)."""
    rec = {"on_ball": (f1 - f0) / fps}
    run, ctrl = 0, None
    for fr in range(f0, f1 + 1):
        p, b, pb, bb = get_player(fr), get_ball(fr), get_player(fr - 1), get_ball(fr - 1)
        if None in (p, b, pb, bb):
            run = 0
            continue
        d = math.hypot(b[0] - p[0], b[1] - p[1])
        rel = math.hypot((b[0] - bb[0]) - (p[0] - pb[0]), (b[1] - bb[1]) - (p[1] - pb[1])) * fps
        run = run + 1 if (d < CTRL_DIST and rel < CTRL_REL) else 0
        if run >= CTRL_FRAMES:
            ctrl = (fr - CTRL_FRAMES + 1 - f0) / fps
            break
    rec["control"] = ctrl
    rec["after"] = (rec["on_ball"] - ctrl) if ctrl is not None else None
    rec["first_time"] = 1 if (ctrl is None or rec["on_ball"] < 0.5) else 0
    p0, p1, pp = get_player(f0), get_player(f1), get_player(f0 - 3)
    rec["carry"] = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) if p0 and p1 else None
    rec["speed_in"] = math.hypot(p0[0] - pp[0], p0[1] - pp[1]) * fps / 3 if p0 and pp else None
    near = lambda fr, p: min((math.hypot(x - p[0], y - p[1]) for x, y in get_opps(fr)), default=None) if p else None
    rec["press_in"], rec["press_out"] = near(f0, p0), near(f1, p1)
    return rec


def run_game(folder, g):
    base = os.path.join(folder, f"Sample_Game_{g}", f"Sample_Game_{g}_")
    home = sr.load_tracking(base + "RawTrackingData_Home_Team.csv")
    away = sr.load_tracking(base + "RawTrackingData_Away_Team.csv")
    ball = ball_track(folder, g)
    ev = list(csv.DictReader(open(base + "RawEventsData.csv")))
    # Which way each team attacks, per period (their keeper's end)
    side = {}
    for per in (1, 2):
        for team, tr in (("Home", home), ("Away", away)):
            xs = {}
            for fr, (p, pos) in list(tr.items())[::250]:
                if p == per:
                    for n, (x, y) in pos.items():
                        if n != "Ball":
                            xs.setdefault(n, []).append(x)
            avg = {n: sum(v) / len(v) for n, v in xs.items() if len(v) > 20}
            gk = min(avg, key=lambda n: min(avg[n], L - avg[n]))
            side[(team, per)] = 1 if avg[gk] < L / 2 else -1
    out = []
    for i, e in enumerate(ev[:-1]):
        if e["Type"] != "PASS" or not e["To"]:
            continue
        nxt = ev[i + 1]
        if nxt["From"] != e["To"] or nxt["Team"] != e["Team"] or nxt["Type"] not in ("PASS", "SHOT"):
            continue
        f0, f1 = int(e["End Frame"]), int(nxt["Start Frame"])
        if not (0 <= f1 - f0 <= 15 * FPS):
            continue
        mine, theirs = (home, away) if e["Team"] == "Home" else (away, home)
        who = e["To"]
        gp = lambda fr: mine[fr][1].get(who) if fr in mine else None
        gb = lambda fr: ball.get(fr)
        go = lambda fr: [xy for n, xy in theirs[fr][1].items() if n != "Ball"] if fr in theirs else []
        if gp(f0) is None or gp(f1) is None:
            continue
        rec = measure(None, gp, gb, go, f0, f1, FPS)
        rec["kind"] = "shot" if nxt["Type"] == "SHOT" else "pass"
        dirn = side[(e["Team"], int(e["Period"]))]
        if rec["kind"] == "pass" and nxt["End X"] and nxt["Start X"]:
            dx = (float(nxt["End X"]) - float(nxt["Start X"])) * L * dirn
            dy = (float(nxt["End Y"]) - float(nxt["Start Y"])) * W
            a = math.degrees(math.atan2(dy, dx))
            rec["dir"] = "forward" if -45 <= a <= 45 else "back" if abs(a) >= 135 else "sideways"
        x0 = gp(f0)[0]
        rec["zone"] = min(2, int(3 * (x0 if dirn > 0 else L - x0) / L))
        out.append(rec)
    return out


def summarise(recs):
    def pct(vals, q):
        v = sorted(x for x in vals if x is not None)
        return v[min(len(v) - 1, int(q * len(v)))] if v else None
    def block(rs):
        if not rs:
            return None
        ob = [r["on_ball"] for r in rs]
        ctl = [r["control"] for r in rs if r["control"] is not None]
        aft = [r["after"] for r in rs if r["after"] is not None and not r["first_time"]]
        return {
            "n": len(rs),
            "time on the ball, median s": pct(ob, 0.5),
            "time on the ball, quickest quarter under s": pct(ob, 0.25),
            "time on the ball, slowest quarter over s": pct(ob, 0.75),
            "played first time %": 100 * sum(r["first_time"] for r in rs) / len(rs),
            "under 1 s %": 100 * sum(x < 1.0 for x in ob) / len(ob),
            "over 3 s %": 100 * sum(x > 3.0 for x in ob) / len(ob),
            "control: median s to settle it": pct(ctl, 0.5),
            "after control: median s to play it (look, decide, set)": pct(aft, 0.5),
            "after control: quickest quarter under s": pct(aft, 0.25),
            "after control: slowest quarter over s": pct(aft, 0.75),
            "carried it, median m": pct([r["carry"] for r in rs], 0.5),
            "nearest opponent when it arrived, median m": pct([r["press_in"] for r in rs], 0.5),
            "nearest opponent when he played it, median m": pct([r["press_out"] for r in rs], 0.5),
        }
    res = {"all": block(recs),
           "man within 3 m when it arrived": block([r for r in recs if r["press_in"] is not None and r["press_in"] < 3]),
           "nobody within 3 m": block([r for r in recs if r["press_in"] is not None and r["press_in"] >= 3]),
           "own third": block([r for r in recs if r["zone"] == 0]),
           "middle third": block([r for r in recs if r["zone"] == 1]),
           "final third": block([r for r in recs if r["zone"] == 2]),
           "then passed forward": block([r for r in recs if r.get("dir") == "forward"]),
           "then passed back": block([r for r in recs if r.get("dir") == "back"])}
    return {k: v for k, v in res.items() if v}


if __name__ == "__main__":
    recs = run_game(sys.argv[1], 1) + run_game(sys.argv[1], 2)
    res = summarise(recs)
    json.dump({"summary": res, "records": recs}, open(sys.argv[2], "w"))
    for k, v in res.items():
        print(k, {a: (round(b, 2) if isinstance(b, float) else b) for a, b in v.items()})
