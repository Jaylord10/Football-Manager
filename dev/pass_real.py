"""Passing decisions in REAL matches: StatsBomb's free event data (https://github.com/statsbomb/open-data), e.g.
the Premier League 2015/16.  usage: python dev/pass_real.py <folder of event .json files> [out.json]"""
import glob, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pass_measures as pm

SX, SY = 105.0 / 120.0, 68.0 / 80.0          # (StatsBomb's pitch is 120 x 80 yards-ish units, attacking +x)
SET = {"Corner", "Free Kick", "Throw-in", "Goal Kick", "Kick Off"}


def secs(e):
    h, m, s = e["timestamp"].split(":")
    return e["period"] * 10000 + int(h) * 3600 + int(m) * 60 + float(s)


def run(path):
    ev = json.load(open(path))
    out = []
    got = {}                                       # player id -> (time, location) he last received it
    for e in ev:
        t = e["type"]["name"]
        pid = e.get("player", {}).get("id")
        if t == "Ball Receipt*" and "ball_receipt" not in e and e.get("location"):
            got[pid] = (secs(e), e["location"])
            continue
        if t != "Pass" or not e.get("location"):
            continue
        p = e["pass"]
        if p.get("type", {}).get("name") in SET:
            got.pop(pid, None)
            continue
        if p.get("outcome", {}).get("name") in ("Unknown", "Injury Clearance"):
            continue
        x0, y0 = e["location"]
        x1, y1 = p["end_location"]
        dx, dy = (x1 - x0) * SX, (y1 - y0) * SY
        rec = dict(dx=dx, dy=dy, length=math.hypot(dx, dy), pressed=bool(e.get("under_pressure")),
                   ok="outcome" not in p, zone=min(2, int(3 * x0 / 120.0)), hold=None, carry=None)
        g = got.pop(pid, None)
        if g and 0 <= secs(e) - g[0] < 30:
            rec["hold"] = secs(e) - g[0]
            rec["carry"] = math.hypot((x0 - g[1][0]) * SX, (y0 - g[1][1]) * SY)
        out.append(rec)
    return out


if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(sys.argv[1], "*.json")))
    allp = []
    for f in files:
        allp += run(f)
    print(f"{len(files)} matches, {len(allp)} open-play passes")
    res = pm.summarise(allp)
    if len(sys.argv) > 2:
        json.dump(res, open(sys.argv[2], "w"), indent=1)
    pm.show(res)
