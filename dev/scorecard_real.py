"""The realism scorecard, REAL side (24 Nov): what real football looks like, from free data.
  StatsBomb open data (events: every pass, shot, dribble, tackle, foul... - e.g. Premier League 2015/16)
  Metrica Sports sample data (tracking: every player 25 times a second, two professional matches)
usage: python dev/scorecard_real.py <StatsBomb events folder> <Metrica data folder> <out.json>
Writes {measure: value} plus the shot model (dev/xg.json) the engine side uses."""
import csv, glob, json, math, os, sys

DEV = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DEV)
import pass_measures as pm
import pass_real
import support_measures as sm
import support_real

SB_X, SB_Y = 105.0 / 120.0, 68.0 / 80.0
GOAL_W = 7.32


def shot_geom(x_m, y_m, length=105.0, width=68.0):
    """distance (m) to the middle of the goal, and the angle (radians) the goal mouth fills, from (x, y) attacking
    the goal at x = length."""
    dx, dy = length - x_m, y_m - width / 2
    d = math.hypot(dx, dy)
    a1 = math.atan2(dy - GOAL_W / 2, dx)
    a2 = math.atan2(dy + GOAL_W / 2, dx)
    return d, abs(a2 - a1)


def xg_features(d, ang, header):
    return [1.0, d / 10.0, ang, (d / 10.0) ** 2, 1.0 if header else 0.0]


def fit_xg(shots):
    """Logistic regression, goals ~ distance, angle, header (plain gradient descent)."""
    X = [xg_features(s["d"], s["ang"], s["header"]) for s in shots]
    y = [1.0 if s["goal"] else 0.0 for s in shots]
    w = [0.0] * len(X[0])
    lr = 0.5
    for it in range(3000):
        g = [0.0] * len(w)
        for xi, yi in zip(X, y):
            z = sum(a * b for a, b in zip(w, xi))
            p = 1 / (1 + math.exp(-max(-30, min(30, z))))
            for k in range(len(w)):
                g[k] += (p - yi) * xi[k]
        w = [a - lr * b / len(X) for a, b in zip(w, g)]
    return w


def xg(w, d, ang, header):
    z = sum(a * b for a, b in zip(w, xg_features(d, ang, header)))
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def statsbomb(folder):
    files = sorted(glob.glob(os.path.join(folder, "*.json")))
    M = len(files)
    c = dict(goals=0, shots=0, on_target=0, np_shots=0, np_goals=0, in_box=0, dist=0.0, headers=0, sb_xg=0.0,
             dribbles=0, dribbles_ok=0, tackles=0, clearances=0, interceptions=0, fouls=0, yellows=0, reds=0,
             corners=0, throw_ins=0, free_kicks=0, goal_kicks=0, offsides=0, crosses=0, crosses_ok=0, possessions=0,
             poss_passes=0, poss5=0)
    shots = []
    allp = []
    for f in files:
        ev = json.load(open(f))
        allp += pass_real.run(f)
        poss = {}
        for e in ev:
            t = e["type"]["name"]
            if e.get("period", 1) > 4:
                continue
            if t == "Shot":
                s = e["shot"]
                c["shots"] += 1
                out = s["outcome"]["name"]
                goal = out == "Goal"
                c["goals"] += goal
                c["on_target"] += out in ("Goal", "Saved", "Saved To Post")
                x, y = e["location"][0] * SB_X, e["location"][1] * SB_Y
                d, ang = shot_geom(x, y)
                head = s.get("body_part", {}).get("name") == "Head"
                c["headers"] += head
                c["dist"] += d
                c["in_box"] += e["location"][0] >= 102 and 18 <= e["location"][1] <= 62
                if s.get("type", {}).get("name") != "Penalty":
                    c["np_shots"] += 1
                    c["np_goals"] += goal
                    c["sb_xg"] += s.get("statsbomb_xg", 0.0)
                    shots.append(dict(d=d, ang=ang, header=head, goal=goal))
            elif t == "Own Goal Against":
                c["goals"] += 1
            elif t == "Dribble":
                c["dribbles"] += 1
                c["dribbles_ok"] += e["dribble"].get("outcome", {}).get("name") == "Complete"
            elif t == "Duel" and e.get("duel", {}).get("type", {}).get("name") == "Tackle":
                c["tackles"] += 1
            elif t == "Clearance":
                c["clearances"] += 1
            elif t == "Interception":
                c["interceptions"] += 1
            elif t == "Foul Committed":
                c["fouls"] += 1
                card = e.get("foul_committed", {}).get("card", {}).get("name", "")
                c["yellows"] += card in ("Yellow Card", "Second Yellow")
                c["reds"] += card in ("Red Card", "Second Yellow")
            elif t == "Bad Behaviour":
                card = e.get("bad_behaviour", {}).get("card", {}).get("name", "")
                c["yellows"] += card in ("Yellow Card", "Second Yellow")
                c["reds"] += card in ("Red Card", "Second Yellow")
            elif t == "Offside":
                c["offsides"] += 1
            elif t == "Pass":
                p = e["pass"]
                ty = p.get("type", {}).get("name")
                c["corners"] += ty == "Corner"
                c["throw_ins"] += ty == "Throw-in"
                c["free_kicks"] += ty == "Free Kick"
                c["goal_kicks"] += ty == "Goal Kick"
                c["offsides"] += p.get("outcome", {}).get("name") == "Pass Offside"
                if p.get("cross") and ty not in ("Corner", "Free Kick"):
                    c["crosses"] += 1
                    c["crosses_ok"] += "outcome" not in p
                if ty not in pass_real.SET:
                    poss[e["possession"]] = poss.get(e["possession"], 0) + 1
            if "possession" in e:
                poss.setdefault(e["possession"], 0)
        c["possessions"] += len(poss)
        c["poss_passes"] += sum(poss.values())
        c["poss5"] += sum(1 for v in poss.values() if v >= 5)
    w = fit_xg(shots)
    our_xg = sum(xg(w, s["d"], s["ang"], s["header"]) for s in shots)
    pr = pm.summarise(allp)["all"]
    per = lambda k: c[k] / M
    out = {
        "matches (events)": M,
        "goals per match": per("goals"),
        "shots per match": per("shots"),
        "shots on target %": 100 * c["on_target"] / c["shots"],
        "goals per shot % (no pens)": 100 * c["np_goals"] / c["np_shots"],
        "shots from inside the box %": 100 * c["in_box"] / c["shots"],
        "average shot distance m": c["dist"] / c["shots"],
        "headed shots %": 100 * c["headers"] / c["shots"],
        "chance quality (xG per shot)": our_xg / len(shots),
        "goals per xG (finishing)": c["np_goals"] / our_xg,
        "open-play passes per match": len(allp) / M,
        "passes completed %": pr["completed %"],
        "forward passes %": pr["forward %"],
        "backward passes %": pr["back %"],
        "long balls %": pr["long %"],
        "long balls completed %": pr["long completed %"],
        "average pass length m": pr["average length m"],
        "first-time passes %": pr["first time %"],
        "held it 3 s+ before passing %": pr["held 3s+ %"],
        "carried it 5 m+ before passing %": pr["carried 5m+ %"],
        "crosses per match": per("crosses"),
        "crosses completed %": 100 * c["crosses_ok"] / max(1, c["crosses"]),
        "take-ons per match": per("dribbles"),
        "take-ons won %": 100 * c["dribbles_ok"] / max(1, c["dribbles"]),
        "tackles per match": per("tackles"),
        "clearances per match": per("clearances"),
        "fouls per match": per("fouls"),
        "yellow cards per match": per("yellows"),
        "corners per match": per("corners"),
        "throw-ins per match": per("throw_ins"),
        "free kicks per match": per("free_kicks"),
        "goal kicks per match": per("goal_kicks"),
        "offsides per match": per("offsides"),
        "passes per possession": c["poss_passes"] / c["possessions"],
        "possessions with 5+ passes %": 100 * c["poss5"] / c["possessions"],
    }
    json.dump({"w": w, "note": "goals ~ distance, angle, header; fitted on StatsBomb PL 2015/16 non-penalty shots"},
              open(os.path.join(DEV, "xg.json"), "w"), indent=1)
    out["(check: our shot model vs StatsBomb's own xG per shot)"] = c["sb_xg"] / c["np_shots"]
    return out


def metrica(folder):
    """Running, team shape, pressure on the passer, support - from tracking."""
    L, W, FPS = 105.0, 68.0, 25
    band = [0, 0, 0, 0, 0]                 # walk <2, jog 2-4, run 4-5.5, high speed 5.5-7, sprint >7 m/s
    dist, player_frames, top = 0.0, 0, 0.0
    length_att, width_att, length_def, width_def, shape_n_att, shape_n_def = 0.0, 0.0, 0.0, 0.0, 0, 0
    near = []
    for g in (1, 2):
        base = os.path.join(folder, f"Sample_Game_{g}", f"Sample_Game_{g}_")
        home = support_real.load_tracking(base + "RawTrackingData_Home_Team.csv")
        away = support_real.load_tracking(base + "RawTrackingData_Away_Team.csv")
        ev = list(csv.DictReader(open(base + "RawEventsData.csv")))
        # who has it, frame by frame (from the events: the team of the last event that's a pass / carry / etc.)
        poss = {}
        for e in ev:
            if e["Type"] in ("PASS", "SET PIECE", "SHOT", "RECOVERY"):
                for fr in range(int(e["Start Frame"]), int(e["End Frame"] or e["Start Frame"]) + 1):
                    poss[fr] = e["Team"]
        gks = {}
        for team, tr in (("Home", home), ("Away", away)):
            frames = sorted(tr)
            prev = None
            for fr in frames:
                per, pos = tr[fr]
                if prev is not None and fr == prev[0] + 1:
                    for n, (x, y) in pos.items():
                        if n == "Ball" or n not in prev[1]:
                            continue
                        px, py = prev[1][n]
                        v = math.hypot(x - px, y - py) * FPS
                        if v > 12.5:
                            continue
                        dist += v / FPS
                        player_frames += 1
                        top = max(top, v)
                        band[0 if v < 2 else 1 if v < 4 else 2 if v < 5.5 else 3 if v < 7 else 4] += 1
                prev = (fr, pos)
                if fr % 25 == 0:
                    xs = sorted(x for n, (x, y) in pos.items() if n != "Ball")
                    ys = sorted(y for n, (x, y) in pos.items() if n != "Ball")
                    if len(xs) >= 10:
                        # (outfield only: drop the keeper - the deepest or highest man, whichever is nearer a goal)
                        out_x = xs[1:] if xs[0] < L - xs[-1] else xs[:-1]
                        length = out_x[-1] - out_x[0]
                        width = ys[-1] - ys[0]
                        if poss.get(fr) == team:
                            length_att += length; width_att += width; shape_n_att += 1
                        elif poss.get(fr) is not None:
                            length_def += length; width_def += width; shape_n_def += 1
        for e in ev:
            if e["Type"] != "PASS":
                continue
            fr = int(e["Start Frame"])
            mine, theirs = (home, away) if e["Team"] == "Home" else (away, home)
            if fr not in mine or e["From"] not in mine[fr][1] or fr not in theirs:
                continue
            px, py = mine[fr][1][e["From"]]
            near.append(min(math.hypot(x - px, y - py) for k, (x, y) in theirs[fr][1].items() if k != "Ball"))
    tot = sum(band)
    near.sort()
    sup = sm.summarise(support_real.run_game(folder, 1) + support_real.run_game(folder, 2))
    return {
        "matches (tracking)": 2,
        "km run per player per 90 (keepers included)": dist / player_frames * FPS * 90 * 60 / 1000,
        "time walking %": 100 * band[0] / tot,
        "time jogging %": 100 * band[1] / tot,
        "time running %": 100 * band[2] / tot,
        "time at high speed %": 100 * band[3] / tot,
        "time sprinting %": 100 * band[4] / tot,
        "team length with the ball m": length_att / max(1, shape_n_att),
        "team width with the ball m": width_att / max(1, shape_n_att),
        "team length without the ball m": length_def / max(1, shape_n_def),
        "team width without the ball m": width_def / max(1, shape_n_def),
        "defender within 2 m of the passer %": 100 * sum(d < 2 for d in near) / len(near),
        "nearest defender to the passer (median) m": near[len(near) // 2],
        "team-mates free for a pass (on the ball)": sup["all"]["open"],
        "nobody ahead free, middle third %": 100 * sup["middle third"]["no_fwd"],
        "nobody ahead free, final third %": 100 * sup["final third"]["no_fwd"],
        "team-mates near the ball: speed m/s": sup["all"]["move"],
        "nearest team-mate to the man on the ball m": sup["all"]["nearest"],
    }


if __name__ == "__main__":
    res = statsbomb(sys.argv[1])
    print("events done", flush=True)
    res.update(metrica(sys.argv[2]))
    json.dump(res, open(sys.argv[3], "w"), indent=1)
    for k, v in res.items():
        print(f"{k}: {v:.2f}" if isinstance(v, float) else f"{k}: {v}")
