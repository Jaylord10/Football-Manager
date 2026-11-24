"""Passing decisions: the same measures for real event data (StatsBomb) and our match engine (23 Nov).

One record per open-play pass (not corners, free kicks, throw-ins, goal kicks, kick-offs):
  dx, dy      where it went, metres (dx along the way he's attacking)
  length      metres
  pressed     an opponent on him when he played it (StatsBomb's "under pressure"; ours: one within PRESS_M)
  ok          it reached a team-mate
  hold        seconds he had it before passing (from getting it), when known
  carry       metres he moved with it before passing, when known
  zone        third of the pitch he passed from (0 own, 1 middle, 2 final)
"""
import math

PRESS_M = 4.5          # (StatsBomb's pressure: a defender closing him down, roughly within 5 yards)
LONG_M = 32.0          # (a long ball: 35 yards)


def direction(dx, dy):
    a = math.degrees(math.atan2(dy, dx))
    if -45 <= a <= 45:
        return "forward"
    if a >= 135 or a <= -135:
        return "back"
    return "sideways"


def summarise(passes):
    def block(ps):
        n = len(ps)
        if not n:
            return None
        d = {}
        d["n"] = n
        d["completed %"] = 100.0 * sum(p["ok"] for p in ps) / n
        for k in ("forward", "sideways", "back"):
            d[f"{k} %"] = 100.0 * sum(direction(p["dx"], p["dy"]) == k for p in ps) / n
        lg = [p for p in ps if p["length"] >= LONG_M]
        d["long %"] = 100.0 * len(lg) / n
        d["long completed %"] = (100.0 * sum(p["ok"] for p in lg) / len(lg)) if lg else 0.0
        d["average length m"] = sum(p["length"] for p in ps) / n
        fw = [p for p in ps if direction(p["dx"], p["dy"]) == "forward"]
        d["forward completed %"] = (100.0 * sum(p["ok"] for p in fw) / len(fw)) if fw else 0.0
        hs = sorted(p["hold"] for p in ps if p.get("hold") is not None)
        if hs:
            d["hold median s"] = hs[len(hs) // 2]
            d["first time %"] = 100.0 * sum(h < 0.6 for h in hs) / len(hs)
            d["held 3s+ %"] = 100.0 * sum(h >= 3.0 for h in hs) / len(hs)
        cs = [p["carry"] for p in ps if p.get("carry") is not None]
        if cs:
            d["carried 5m+ %"] = 100.0 * sum(c >= 5.0 for c in cs) / len(cs)
        return d
    res = {"all": block(passes), "under pressure": block([p for p in passes if p["pressed"]]),
           "not pressed": block([p for p in passes if not p["pressed"]])}
    for z, name in ((0, "own third"), (1, "middle third"), (2, "final third")):
        res[name] = block([p for p in passes if p["zone"] == z])
    return {k: v for k, v in res.items() if v}


def show(res):
    keys = ["n", "completed %", "forward %", "sideways %", "back %", "forward completed %", "long %",
            "long completed %", "average length m", "hold median s", "first time %", "held 3s+ %", "carried 5m+ %"]
    for name, d in res.items():
        print(f"{name}: " + ", ".join(f"{k} {d[k]:.1f}" if isinstance(d[k], float) else f"{k} {d[k]}"
                                      for k in keys if k in d))
