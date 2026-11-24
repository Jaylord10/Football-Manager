"""The realism scorecard (24 Nov): real football (dev/scorecard_real.py) against our matches
(dev/scorecard_engine.py, one json per match).
usage: python dev/scorecard.py <real.json> <out.csv> <match1.json> [match2.json ...]
Each row: area, measure, real, ours, how far off, verdict (close / a bit off / way off), where the real figure is from.
Verdict: within 15% of the real figure (or 3 points, for a share of 10% or more) is close; within 35% (or 8 points) a bit
off; further is way off."""
import csv, json, math, os, statistics, sys

DEV = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DEV)
import pass_measures as pm
import support_measures as sm
import scorecard_real as scr

SB = "StatsBomb open data, Premier League 2015/16 (120 matches)"
MT = "Metrica Sports sample tracking data (2 professional matches)"
OPTA = "Opta via The Analyst: Premier League ball in play 2022-23 (54 min 49 s, 55.7%)"

# (area, measure, source, percentage?)
ROWS = [
    ("Goals and shots", "goals per match", SB, False),
    ("Goals and shots", "shots per match", SB, False),
    ("Goals and shots", "shots on target %", SB, True),
    ("Goals and shots", "goals per shot % (no pens)", SB, True),
    ("Goals and shots", "shots from inside the box %", SB, True),
    ("Goals and shots", "average shot distance m", SB, False),
    ("Goals and shots", "headed shots %", SB, True),
    ("Goals and shots", "chance quality (xG per shot)", SB, False),
    ("Goals and shots", "goals per xG (finishing)", SB, False),
    ("Passing", "open-play passes per match", SB, False),
    ("Passing", "passes completed %", SB, True),
    ("Passing", "forward passes %", SB, True),
    ("Passing", "backward passes %", SB, True),
    ("Passing", "long balls %", SB, True),
    ("Passing", "long balls completed %", SB, True),
    ("Passing", "average pass length m", SB, False),
    ("Passing", "crosses per match", SB, False),
    ("Passing", "crosses completed %", SB, True),
    ("On the ball", "first-time passes %", SB, True),
    ("On the ball", "held it 3 s+ before passing %", SB, True),
    ("On the ball", "carried it 5 m+ before passing %", SB, True),
    ("On the ball", "defender within 2 m of the passer %", MT, True),
    ("On the ball", "nearest defender to the passer (median) m", MT, False),
    ("On the ball", "take-ons per match", SB, False),
    ("On the ball", "take-ons won %", SB, True),
    ("Possession", "passes per possession", SB, False),
    ("Possession", "possessions with 5+ passes %", SB, True),
    ("Possession", "ball in play %", OPTA, True),
    ("Defending", "tackles per match", SB, False),
    ("Defending", "clearances per match", SB, False),
    ("Defending", "fouls per match", SB, False),
    ("Defending", "yellow cards per match", SB, False),
    ("Set pieces", "corners per match", SB, False),
    ("Set pieces", "throw-ins per match", SB, False),
    ("Set pieces", "free kicks per match", SB, False),
    ("Set pieces", "goal kicks per match", SB, False),
    ("Set pieces", "offsides per match", SB, False),
    ("Running and shape", "km run per player per 90 (keepers included)", MT, False),
    ("Running and shape", "time walking %", MT, True),
    ("Running and shape", "time jogging %", MT, True),
    ("Running and shape", "time running %", MT, True),
    ("Running and shape", "time at high speed %", MT, True),
    ("Running and shape", "time sprinting %", MT, True),
    ("Running and shape", "team length with the ball m", MT, False),
    ("Running and shape", "team width with the ball m", MT, False),
    ("Running and shape", "team length without the ball m", MT, False),
    ("Running and shape", "team width without the ball m", MT, False),
    ("Support", "team-mates free for a pass (on the ball)", MT, False),
    ("Support", "nobody ahead free, middle third %", MT, True),
    ("Support", "nobody ahead free, final third %", MT, True),
    ("Support", "team-mates near the ball: speed m/s", MT, False),
    ("Support", "nearest team-mate to the man on the ball m", MT, False),
]
REAL_EXTRA = {"ball in play %": 55.7}


def ours(matches):
    from config.constants import M_TO_PX, WIDTH, HEIGHT
    L, W = WIDTH / M_TO_PX, HEIGHT / M_TO_PX
    w = json.load(open(os.path.join(DEV, "xg.json")))["w"]
    mins = sum(m["minutes"] for m in matches)
    per90 = lambda total: total / len(matches)          # (per match, added time included - as the real counts are)
    shots = [s for m in matches for s in m["shots"]]
    np_ = [s for s in shots if s["type"] != "penalty"]
    passes = [p for m in matches for p in m["passes"]]
    pr = pm.summarise(passes)["all"]
    crosses = [p for p in passes if p.get("cross")]
    geo = [scr.shot_geom(s["x"], s["y"], L, W) for s in shots]
    np_xg = sum(scr.xg(w, *scr.shot_geom(s["x"], s["y"], L, W), s["type"] == "header") for s in np_)
    rs = lambda k: sum(m["restarts"].get(k, 0) for m in matches)
    poss = [p for m in matches for p in m["possessions"]]
    band = [sum(m["band"][i] for m in matches) for i in range(5)]
    bt = sum(band) or 1
    pf = sum(m["pframes"] for m in matches)
    dist = sum(m["dist"] for m in matches)
    shp = {k: [sum(m["shape"][k][i] for m in matches) for i in range(3)] for k in ("att", "def")}
    near = sorted(p["near"] for p in passes)
    sup = sm.summarise([s for m in matches for s in m["support"]])
    return {
        "goals per match": per90(sum(m["goals"] for m in matches)),
        "shots per match": per90(len(shots)),
        "shots on target %": 100 * sum(s["on"] for s in shots) / max(1, len(shots)),
        "goals per shot % (no pens)": 100 * sum(s["goal"] for s in np_) / max(1, len(np_)),
        "shots from inside the box %": 100 * sum(s["x"] >= L - 16.5 and abs(s["y"] - W / 2) <= 20.16
                                                 for s in shots) / max(1, len(shots)),
        "average shot distance m": sum(g[0] for g in geo) / max(1, len(geo)),
        "headed shots %": 100 * sum(s["type"] == "header" for s in shots) / max(1, len(shots)),
        "chance quality (xG per shot)": np_xg / max(1, len(np_)),
        "goals per xG (finishing)": sum(s["goal"] for s in np_) / max(1e-9, np_xg),
        "open-play passes per match": per90(len(passes)),
        "passes completed %": pr["completed %"],
        "forward passes %": pr["forward %"],
        "backward passes %": pr["back %"],
        "long balls %": pr["long %"],
        "long balls completed %": pr["long completed %"],
        "average pass length m": pr["average length m"],
        "crosses per match": per90(len(crosses)),
        "crosses completed %": 100 * sum(p["ok"] for p in crosses) / max(1, len(crosses)),
        "first-time passes %": pr.get("first time %", 0.0),
        "held it 3 s+ before passing %": pr.get("held 3s+ %", 0.0),
        "carried it 5 m+ before passing %": pr.get("carried 5m+ %", 0.0),
        "defender within 2 m of the passer %": 100 * sum(d < 2 for d in near) / max(1, len(near)),
        "nearest defender to the passer (median) m": near[len(near) // 2] if near else 0.0,
        "take-ons per match": per90(sum(m["takeons"] for m in matches)),
        "take-ons won %": 100 * sum(m["takeons_won"] for m in matches) / max(1, sum(m["takeons"] for m in matches)),
        "passes per possession": statistics.mean(poss) if poss else 0.0,
        "possessions with 5+ passes %": 100 * sum(p >= 5 for p in poss) / max(1, len(poss)),
        "ball in play %": 100 * sum(m["live_frames"] for m in matches) / max(1, sum(m["frames"] for m in matches)),
        "tackles per match": per90(sum(m["tackles"] for m in matches)),
        "clearances per match": per90(sum(m["clearances"] for m in matches)),
        "fouls per match": per90(sum(m["fouls"] for m in matches)),
        "yellow cards per match": per90(sum(m["yellows"] for m in matches)),
        "corners per match": per90(sum(m["corners"] for m in matches)),
        "throw-ins per match": per90(rs("throw_in")),
        "free kicks per match": per90(rs("free_kick")),
        "goal kicks per match": per90(rs("goal_kick")),
        "offsides per match": per90(rs("offside")),
        "km run per player per 90 (keepers included)": dist / max(1, pf) * 60 * 5400 / 1000,
        "time walking %": 100 * band[0] / bt,
        "time jogging %": 100 * band[1] / bt,
        "time running %": 100 * band[2] / bt,
        "time at high speed %": 100 * band[3] / bt,
        "time sprinting %": 100 * band[4] / bt,
        "team length with the ball m": shp["att"][0] / max(1, shp["att"][2]),
        "team width with the ball m": shp["att"][1] / max(1, shp["att"][2]),
        "team length without the ball m": shp["def"][0] / max(1, shp["def"][2]),
        "team width without the ball m": shp["def"][1] / max(1, shp["def"][2]),
        "team-mates free for a pass (on the ball)": sup["all"]["open"],
        "nobody ahead free, middle third %": 100 * sup["middle third"]["no_fwd"],
        "nobody ahead free, final third %": 100 * sup["final third"]["no_fwd"],
        "team-mates near the ball: speed m/s": sup["all"]["move"],
        "nearest team-mate to the man on the ball m": sup["all"]["nearest"],
    }


def verdict(real, our, pct):
    if real == 0:
        return "close" if abs(our) < 1 else "way off"
    rel = abs(our - real) / abs(real)
    pts = abs(our - real)
    big = pct and abs(real) >= 10.0               # (a few points either way only counts as close on a big share)
    if rel <= 0.15 or (big and pts <= 3):
        return "close"
    if rel <= 0.35 or (big and pts <= 8):
        return "a bit off"
    return "way off"


if __name__ == "__main__":
    real = json.load(open(sys.argv[1]))
    real.update(REAL_EXTRA)
    files = sys.argv[3:]
    matches = [json.load(open(f)) for f in files]
    sys.path.insert(0, os.getcwd())
    o = ours(matches)
    with open(sys.argv[2], "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["area", "measure", "real", "ours", "difference %", "verdict", "real figure from"])
        for area, k, src, pct in ROWS:
            r, u = real[k], o[k]
            diff = 100 * (u - r) / r if r else 0.0
            wr.writerow([area, k, round(r, 2), round(u, 2), round(diff), verdict(r, u, pct), src])
            print(f"{area:18} {k:45} real {r:8.2f}  ours {u:8.2f}  {verdict(r, u, pct)}")
    print(f"{len(matches)} of our matches, {sum(m['minutes'] for m in matches):.0f} minutes")
