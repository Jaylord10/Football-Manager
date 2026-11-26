"""Real values for the pitch (26 Nov, for the decision scoreboard - ai/scoreboard.py): Expected Threat (xT, Karun Singh
2018 - https://karun.in/blog/expected-threat.html) worked out from StatsBomb's free event data, Premier League 2015/16
(120 matches).  The value of having the ball in a spot = the chance his team scores from it within the next few
actions: shoot from here (that spot's real scoring rate) or move it on (where real players moved it, and how often
it got there).
Also the real odds the scoreboard needs: passes reaching a team-mate by length and pressure, take-ons won, carries
lost.
usage: python dev/xt_grid.py <folder of StatsBomb event .json files> <out.json>
The grid is in our frame: a (0 = our goal line, 110 = theirs) x l (-35 our left .. +35 our right), NA x NL cells."""
import glob, json, math, os, sys

NA, NL = 16, 12
SX, SY = 120.0, 80.0                                 # (StatsBomb's pitch units, attacking +x; y 0 = their left touchline)
SET = {"Corner", "Free Kick", "Throw-in", "Goal Kick", "Kick Off"}


def cell(x, y):
    i = min(NA - 1, max(0, int(x / SX * NA)))
    j = min(NL - 1, max(0, int(y / SY * NL)))
    return i, j


def main(folder, out):
    shots = [[0] * NL for _ in range(NA)]
    goals = [[0] * NL for _ in range(NA)]
    moves = [[0] * NL for _ in range(NA)]
    trans = {}
    pas = {}                                          # (length band, pressed) -> [n, ok]
    takeon = [0, 0]
    carries = [0, 0]                                  # [n, lost straight after]
    for f in sorted(glob.glob(os.path.join(folder, "*.json"))):
        ev = json.load(open(f))
        for k, e in enumerate(ev):
            t = e["type"]["name"]
            loc = e.get("location")
            if not loc:
                continue
            i, j = cell(*loc)
            if t == "Shot":
                if e["shot"].get("type", {}).get("name") == "Penalty":
                    continue
                shots[i][j] += 1
                if e["shot"].get("outcome", {}).get("name") == "Goal":
                    goals[i][j] += 1
            elif t == "Pass":
                p = e["pass"]
                if p.get("type", {}).get("name") in SET or p.get("outcome", {}).get("name") in ("Unknown", "Injury Clearance"):
                    continue
                moves[i][j] += 1
                ok = "outcome" not in p
                if ok:
                    i2, j2 = cell(*p["end_location"])
                    trans[(i, j, i2, j2)] = trans.get((i, j, i2, j2), 0) + 1
                L = math.hypot((p["end_location"][0] - loc[0]) * 105 / 120, (p["end_location"][1] - loc[1]) * 68 / 80)
                band = min(5, int(L / 10))
                key = (band, bool(e.get("under_pressure")))
                s = pas.setdefault(key, [0, 0]); s[0] += 1; s[1] += ok
            elif t == "Carry":
                end = e["carry"]["end_location"]
                if math.hypot(end[0] - loc[0], end[1] - loc[1]) < 1.0:
                    continue
                moves[i][j] += 1
                i2, j2 = cell(*end)
                trans[(i, j, i2, j2)] = trans.get((i, j, i2, j2), 0) + 1
                carries[0] += 1
                nxt = ev[k + 1]["type"]["name"] if k + 1 < len(ev) else ""
                carries[1] += nxt in ("Dispossessed", "Miscontrol")
            elif t == "Dribble":
                takeon[0] += 1
                takeon[1] += e["dribble"].get("outcome", {}).get("name") == "Complete"
    # Expected Threat: xT(z) = s(z) g(z) + m(z) sum T(z->z') xT(z')
    s = [[0.0] * NL for _ in range(NA)]
    g = [[0.0] * NL for _ in range(NA)]
    m = [[0.0] * NL for _ in range(NA)]
    for i in range(NA):
        for j in range(NL):
            n = shots[i][j] + moves[i][j]
            if n:
                s[i][j] = shots[i][j] / n
                m[i][j] = moves[i][j] / n
            g[i][j] = goals[i][j] / shots[i][j] if shots[i][j] >= 5 else 0.0
    T = {}
    for (i, j, i2, j2), c in trans.items():
        T.setdefault((i, j), []).append((i2, j2, c / moves[i][j]))
    xt = [[0.0] * NL for _ in range(NA)]
    for _ in range(60):
        new = [[s[i][j] * g[i][j] + m[i][j] * sum(p * xt[a][b] for a, b, p in T.get((i, j), []))
                for j in range(NL)] for i in range(NA)]
        xt = new
    # into our frame: a = x / 120 * 110; l = y / 80 * 70 - 35 (StatsBomb y 0 is the attacking team's left)
    res = {"source": "StatsBomb open data, Premier League 2015/16, %d matches" % len(glob.glob(os.path.join(folder, "*.json"))),
           "method": "Expected Threat (Karun Singh, 2018), %d x %d grid, open play, penalties left out" % (NA, NL),
           "na": NA, "nl": NL, "a_len": 110.0, "width": 70.0,
           "xt": [[round(v, 5) for v in row] for row in xt],
           "pass_ok": {f"{b * 10}-{b * 10 + 10}{'+' if b == 5 else ''} m{' pressed' if pr else ''}": round(v[1] / v[0], 3)
                       for (b, pr), v in sorted(pas.items()) if v[0] >= 30},
           "take_on_won": round(takeon[1] / max(1, takeon[0]), 3), "take_ons": takeon[0],
           "carry_lost": round(carries[1] / max(1, carries[0]), 4), "carries": carries[0]}
    json.dump(res, open(out, "w"), indent=1)
    return res


if __name__ == "__main__":
    r = main(sys.argv[1], sys.argv[2])
    for i in range(NA):
        print(" ".join(f"{v:.3f}" for v in r["xt"][i]))
    print({k: v for k, v in r.items() if k not in ("xt",)})
