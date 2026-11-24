"""Showing for the ball in REAL matches: Metrica Sports' sample tracking data (two anonymised professional matches,
every player 25 times a second - https://github.com/metrica-sports/sample-data).
usage: python dev/support_real.py <metrica data folder> [out.json]
Moments every 0.5 s while a player has the ball in open play (between receiving a pass and playing the next one)."""
import csv, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import support_measures as sm

L, W = 105.0, 68.0
FPS = 25


def load_tracking(path):
    with open(path) as f:
        r = csv.reader(f)
        next(r); next(r)
        head = next(r)
        cols = {}
        for i, h in enumerate(head):
            if h.startswith("Player") or h == "Ball":
                cols[h] = i
        frames = {}
        for row in r:
            fr = int(row[1])
            pos = {}
            for name, i in cols.items():
                try:
                    x, y = float(row[i]), float(row[i + 1])
                except (ValueError, IndexError):
                    continue
                if math.isnan(x) or math.isnan(y):
                    continue
                pos[name] = (x * L, y * W)
            frames[fr] = (int(row[0]), pos)
    return frames


def run_game(folder, game):
    base = os.path.join(folder, f"Sample_Game_{game}", f"Sample_Game_{game}_")
    home = load_tracking(base + "RawTrackingData_Home_Team.csv")
    away = load_tracking(base + "RawTrackingData_Away_Team.csv")
    with open(base + "RawEventsData.csv") as f:
        ev = list(csv.DictReader(f))
    # Which way each team attacks in each period: their keeper is the player furthest back on average
    side = {}
    for per in (1, 2):
        for team, tr in (("Home", home), ("Away", away)):
            sums = {}
            for fr, (p, pos) in list(tr.items())[::250]:
                if p != per:
                    continue
                for n, (x, y) in pos.items():
                    if n == "Ball":
                        continue
                    s = sums.setdefault(n, [0.0, 0])
                    s[0] += x; s[1] += 1
            avg = {n: s[0] / s[1] for n, s in sums.items() if s[1] > 20}
            gk = min(avg, key=lambda n: min(avg[n], L - avg[n]))
            side[(team, per)] = (1 if avg[gk] < L / 2 else -1, gk)
    passes = [e for e in ev if e["Type"] == "PASS" and e["To"]]
    moments = []
    for a, b in zip(passes, passes[1:]):
        if a["Team"] != b["Team"] or a["To"] != b["From"] or a["Period"] != b["Period"]:
            continue                                     # (only a clean spell: he received it, then passed it)
        per = int(a["Period"])
        team = a["Team"]
        direction, gk = side[(team, per)]
        mine, theirs = (home, away) if team == "Home" else (away, home)
        carrier = a["To"]
        f0, f1 = int(a["End Frame"]) + 2, int(b["Start Frame"]) - 1
        for fr in range(f0, f1, FPS // 2):
            if fr not in mine or fr - 5 not in mine or fr not in theirs:
                continue
            pos, prev = mine[fr][1], mine[fr - 5][1]
            if carrier not in pos:
                continue
            mates = []
            for n, (x, y) in pos.items():
                if n in ("Ball", carrier, gk) or n not in prev:
                    continue
                px, py = prev[n]
                mates.append((x, y, (x - px) * FPS / 5, (y - py) * FPS / 5))
            opps = [xy for n, xy in theirs[fr][1].items() if n != "Ball"]
            if len(mates) < 8 or len(opps) < 9:
                continue
            moments.append(sm.moment(pos[carrier], direction, mates, opps, L))
    return moments


if __name__ == "__main__":
    folder = sys.argv[1]
    allm = []
    for g in (1, 2):
        m = run_game(folder, g)
        print(f"game {g}: {len(m)} moments", flush=True)
        allm += m
    res = sm.summarise(allm)
    if len(sys.argv) > 2:
        json.dump(res, open(sys.argv[2], "w"), indent=1)
    for z, d in res.items():
        print(z, {k: round(v, 2) for k, v in d.items()})
