"""dev/oddities.py CONFIG [MINUTES] [SEED] - play a match and list the moments that would look odd on screen.

    FM_MATCH_CONFIG-style config (a career match config); MINUTES of football (default 90).
Looks for (each lasting long enough to be seen):
  overlap    two players' bodies through each other (centres < 0.45 m apart for 0.5 s)
  frozen     an outfielder standing dead still (< 0.2 m/s) for 8 s with the ball live and within 25 m of him
  jitter     running back and forth (3+ about-turns at > 2 m/s within 2 s)
  moonwalk   running fast (> 4 m/s) facing the other way (> 140 deg off) for 0.8 s
  teleport   a player moving more than 1.5 m in one frame
  offpitch   a player (not sent off) more than 3 m outside the lines with the ball live, for 2 s
  ballspeed  the ball faster than 40 m/s
  ballaway   the ball "owned" but more than 2.5 m from its owner for 0.3 s
  ballhigh   the ball over 30 m up
"""
import os, sys, io, contextlib, random, math, collections
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.dirname(HERE)
os.chdir(W); sys.path.insert(0, W)
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["FM_MATCH_CONFIG"] = sys.argv[1]
mins = float(sys.argv[2]) if len(sys.argv) > 2 else 90.0
random.seed(int(sys.argv[3]) if len(sys.argv) > 3 else 1)
with contextlib.redirect_stdout(io.StringIO()):
    import gameplay.match_engine as me
    me.RL_ENABLED = False
    e = me.MatchEngine(career=True)
from config.constants import M_TO_PX, WIDTH, HEIGHT
M = M_TO_PX
FPS = 60
found = collections.defaultdict(list)          # kind -> [(minute, who, detail)]
run = collections.defaultdict(float)           # (kind, key) -> seconds it's been going on
flag = set()
turns = collections.defaultdict(list)


def note(kind, key, dt, need, minute, who, detail=""):
    """Something's been going on for `need` seconds: note it once (until it stops)."""
    run[(kind, key)] += dt
    if run[(kind, key)] >= need and (kind, key) not in flag:
        flag.add((kind, key))
        found[kind].append((minute, who, detail))


def stop(kind, key):
    run.pop((kind, key), None)
    flag.discard((kind, key))


def name(p):
    return f"{getattr(p, 'name', '?')} ({'Blue' if p.team == 0 else 'Red'} {p.role})"


prev = {}
sink = io.StringIO()
n = 0
dt = 1.0 / FPS
with contextlib.redirect_stdout(sink):
    while e.match_state != "full_time" and n < mins * 60 * FPS:
        e.step(dt); n += 1
        if n % 600 == 0:
            sink.seek(0); sink.truncate(0)
        live = e.match_state in ("first_half", "second_half") and not e.ball.is_dead
        minute = e.time_elapsed / 60.0
        b = e.ball
        ps = [p for p in e.team0 + e.team1 if getattr(p, "is_active", True)]
        for p in ps:
            k = id(p)
            if k in prev and (p.pos - prev[k]).length() > 1.5 * M and live:
                found["teleport"].append((minute, name(p), f"{(p.pos - prev[k]).length() / M:.1f} m"))
            prev[k] = p.pos.copy()
        if n % 3:                                   # (the rest: 20 times a second)
            continue
        d3 = dt * 3
        if not live:
            for key in list(run):
                if key[0] in ("frozen", "offpitch", "moonwalk"):
                    run.pop(key, None)
            continue
        # overlap
        for i, p in enumerate(ps):
            for q in ps[i + 1:]:
                key = (id(p), id(q))
                if (p.pos - q.pos).length() < 0.45 * M:
                    note("overlap", key, d3, 0.5, minute, name(p) + " / " + name(q))
                else:
                    stop("overlap", key)
        for p in ps:
            k = id(p)
            sp = p.vel.length() / M
            # frozen
            if p.role != "GK" and sp < 0.2 and b.owner is not p and (p.pos - b.pos).length() < 25 * M:
                note("frozen", k, d3, 8.0, minute, name(p), getattr(p, "pos_reason", ""))
            else:
                stop("frozen", k)
            # moonwalk
            if sp > 4.0 and p.facing.length_squared() > 0 and \
                    p.facing.normalize().dot(p.vel.normalize()) < math.cos(math.radians(140)):
                note("moonwalk", k, d3, 0.8, minute, name(p), getattr(p, "pos_reason", ""))
            else:
                stop("moonwalk", k)
            # jitter
            if sp > 2.0:
                h = math.atan2(p.vel.y, p.vel.x)
                t = turns[k]
                if t and abs((h - t[-1][1] + math.pi) % (2 * math.pi) - math.pi) > math.radians(150):
                    t.append((e.time_elapsed, h))
                elif not t:
                    t.append((e.time_elapsed, h))
                else:
                    t[-1] = (t[-1][0], h)
                while t and e.time_elapsed - t[0][0] > 2.0:
                    t.pop(0)
                if len(t) >= 4:
                    found["jitter"].append((minute, name(p), getattr(p, "pos_reason", "")))
                    turns[k] = []
            # off the pitch
            out = max(-p.pos.x, p.pos.x - WIDTH, -p.pos.y, p.pos.y - HEIGHT) / M
            if out > 3.0:
                note("offpitch", k, d3, 2.0, minute, name(p), f"{out:.0f} m out")
            else:
                stop("offpitch", k)
        bs = b.vel.length() / M
        if bs > 40:
            found["ballspeed"].append((minute, "", f"{bs:.0f} m/s"))
        if b.z / M > 30:
            found["ballhigh"].append((minute, "", f"{b.z / M:.0f} m"))
        if b.owner is not None and (b.owner.pos - b.pos).length() > 2.5 * M:
            note("ballaway", id(b.owner), d3, 0.3, minute, name(b.owner), f"{(b.owner.pos - b.pos).length() / M:.1f} m")
        else:
            for key in [k2 for k2 in run if k2[0] == "ballaway"]:
                stop(*key)

print(f"score {e.score}, {n / FPS / 60:.0f} minutes")
for kind in ("overlap", "frozen", "jitter", "moonwalk", "teleport", "offpitch", "ballspeed", "ballaway", "ballhigh"):
    L = found.get(kind, [])
    print(f"{kind:10s} {len(L)}")
    roles = collections.Counter(who.split(" ")[-1].rstrip(")") for m, who, det in L)
    if L:
        print("    by role:", dict(roles.most_common(8)))
        print("    why:", dict(collections.Counter(det for m, who, det in L).most_common(5)))
    for m, who, det in L[:int(os.environ.get("ODD_SHOW", "6"))]:
        print(f"    {m:5.1f}'  {who}  {det}")
