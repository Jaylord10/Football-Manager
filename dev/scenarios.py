"""Jay's moments as tests (27 Nov): rebuild each moment he judged (data/decide/jay_moments.json - where everyone was)
and let the scoreboard (ai/scoreboard.py) weigh it up, with no guesswork (perfect judgement) - does it pick what he'd
pick?  Writes a log the picture tool reads (dev/decision_pic.py <out.json> <png> 0 1 ...).
usage: python dev/scenarios.py <engine_dir> <out.json>"""
import os, sys, io, contextlib, json, math, random

eng, out = sys.argv[1], sys.argv[2]
os.chdir(eng); sys.path.insert(0, eng)
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["FM_DECISION_LOG"] = "1"
from pygame.math import Vector2
with contextlib.redirect_stdout(io.StringIO()):
    import ai.scoreboard as sb
    from ai.team_shape import to_world
sb.LOG_ON = True
sb.JUDGE_NOISE = (0.0, 0.0)
sb.NOISE_FLOOR = 0.0


class P:
    def __init__(self, team, a, l, role, facing=None):
        self.team, self.role, self.name = team, role, role
        self.pos = Vector2(to_world(team, a, l))
        self.vel = Vector2(0, 0)
        f = Vector2(1, 0) if facing is None else Vector2(math.cos(math.radians(facing)), math.sin(math.radians(facing)))
        self.facing = f if team == 0 else -f
        self.attributes = {}
        self.state = "dribble"
        self.is_active = True
        self.has_ball = True
        self._picture = False
        self.last_decision_time = -9.0


class Mech:
    def __getattr__(self, name):
        def f(*a, **k):
            self.called = name
        return f


data = json.load(open(os.path.join(eng, "data", "decide", "jay_moments.json")))
res = []
for m in data["moments"]:
    me = P(0, m["a"], m["l"], m["role"], m.get("facing"))
    me.attributes = dict(m.get("attributes", {}))
    mates = [P(0, a, l, r) for a, l, r in m["mates"]]
    opps = [P(1, 110 - a, -l, "X") for a, l in m["opps"]]          # (theirs, in their own frame)
    gk = P(1, 2.0, 0.0, "GK")
    random.seed(1)
    with contextlib.redirect_stdout(io.StringIO()):
        sb.decide(me, [x for x in mates if x.role != "GK"], mates, opps + [gk], opps, None, 10.0, Mech())
    d = sb.LOG[-1]
    d["mates"], d["opps"] = m["mates"], m["opps"]
    if m.get("facing") is not None:
        d["facing"] = m["facing"]

    def match(o, want):
        kind, how = want
        if o["kind"] != kind:
            return False
        if kind in ("pass", "through") and how:
            return o["target"] == how
        if kind == "carry" and how and o["at"]:
            dl, da = o["at"][1] - m["l"], o["at"][0] - m["a"]
            inside = dl * (-1 if m["l"] > 0 else 1) > 1.0
            return {"left": dl < -1.0, "inside": inside, "forward": da > 2.0, "upfield": da >= abs(dl) and da > 2.0}[how]
        return True
    best = d["options"][0]
    ok = any(match(best, w) for w in m["ok"])
    banned = [o for o in d["options"] for w in m.get("not_offered", []) if match(o, w)]
    if banned:
        ok = False
        print(f"     (shouldn't be on his list at all: {', '.join(o['kind'] + ' ' + o['target'] for o in banned)})")
    res.append(ok)
    print(f"\n{'OK  ' if ok else 'MISS'} {m['name']}\n     Jay: {m['jay']}\n     scoreboard: {best['kind']} {best['target']} "
          f"({100 * best['value']:.2f}%)")
    for o in d["options"][:6]:
        print(f"        {o['kind']:8s} {o['target']:9s} {100 * o['value']:6.2f}%  comes off {o['p']:.2f}")
print(f"\n{sum(res)} of {len(res)} as Jay would")
json.dump({"log": sb.LOG}, open(out, "w"))
