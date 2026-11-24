"""The realism scorecard, OUR side (24 Nov): plays one match on the real engine and counts the same things as
dev/scorecard_real.py.  One match per process (the teams load when the engine's imported).
usage: FM_MATCH_CONFIG=<config.json> python dev/scorecard_engine.py <engine_dir> <seed> <out.json> [seconds per half]
Combine several with dev/scorecard.py."""
import os, sys, io, contextlib, random, json, math

eng, seed, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
half = float(sys.argv[4]) if len(sys.argv) > 4 else 45 * 60.0
DEV = os.path.dirname(os.path.abspath(__file__))
os.chdir(eng); sys.path.insert(0, eng); sys.path.insert(0, DEV)
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("FM_MATCH_CONFIG", "match_config_benchmark.json")
import pass_measures as pm
import support_measures as sm
with contextlib.redirect_stdout(io.StringIO()):
    import gameplay.match_engine as me
    import gameplay.mechanics as mech
    import gameplay.duels as duels
    from config.constants import M_TO_PX, WIDTH, HEIGHT

L, W = WIDTH / M_TO_PX, HEIGHT / M_TO_PX
DT = 1 / 60
E = {"e": None}
passes, pending, got = [], [], {}
C = dict(clearances=0, crosses=0, crosses_ok=0)


def _dir(team_id):
    e = E["e"]
    team = e.team0 if team_id == 0 else e.team1
    gk = next((p for p in team if p.role == "GK"), None)
    return 1 if (gk is not None and gk.pos.x < WIDTH / 2) else -1


def _record(passer, receiver, ball, t, cross=False):
    e = E["e"]
    if e is None or ball.is_dead or getattr(ball, "restart_taker", None) is passer:
        return
    other = e.team1 if passer.team == 0 else e.team0
    dirn = _dir(passer.team)
    x0, y0 = passer.pos.x / M_TO_PX, passer.pos.y / M_TO_PX
    x1, y1 = receiver.pos.x / M_TO_PX, receiver.pos.y / M_TO_PX
    dx, dy = (x1 - x0) * dirn, (y1 - y0) * dirn
    near = min(((p.pos - passer.pos).length() / M_TO_PX for p in other if getattr(p, "is_active", True)), default=99)
    depth = x0 if dirn > 0 else L - x0
    rec = dict(dx=dx, dy=dy, length=math.hypot(dx, dy), pressed=near < pm.PRESS_M, ok=False, near=near,
               zone=min(2, int(3 * depth / L)), hold=None, carry=None, team=passer.team, cross=cross)
    g = got.get(id(passer))
    if g and 0 <= t - g[0] < 30:
        rec["hold"] = t - g[0]
        rec["carry"] = math.hypot(x0 - g[1][0], y0 - g[1][1])
    pending.append(rec)


_pass, _cross, _clear = mech.GameMechanics.execute_pass, mech.GameMechanics.execute_cross, \
    mech.GameMechanics.execute_clearance


def execute_pass(self, passer, receiver, ball, current_time, *a, **k):
    _record(passer, receiver, ball, current_time)
    return _pass(self, passer, receiver, ball, current_time, *a, **k)


def execute_cross(self, passer, receiver, ball, current_time, *a, **k):
    _record(passer, receiver, ball, current_time, cross=True)
    return _cross(self, passer, receiver, ball, current_time, *a, **k)


def execute_clearance(self, player, ball, *a, **k):
    if not ball.is_dead:
        C["clearances"] += 1
    return _clear(self, player, ball, *a, **k)


mech.GameMechanics.execute_pass = execute_pass
mech.GameMechanics.execute_cross = execute_cross
mech.GameMechanics.execute_clearance = execute_clearance

random.seed(seed)
with contextlib.redirect_stdout(io.StringIO()):
    me.RL_ENABLED = False
    me.HALF_DURATION_REAL = half
    e = me.MatchEngine(career=True)
E["e"] = e
random.seed(seed)

frames = live = 0
band = [0, 0, 0, 0, 0]
dist, pframes, top = 0.0, 0, 0.0
prev = {}
shots, cur_shot = [], None
restarts, seen_restart = {}, set()
shape = {"att": [0.0, 0.0, 0], "def": [0.0, 0.0, 0]}
support = []
poss_team, poss_passes, possessions = None, 0, []
last_owner = None
n = 0
sink = io.StringIO()
with contextlib.redirect_stdout(sink):
    while e.match_state != "full_time" and n < 2_000_000:
        e.step(DT); n += 1
        if n % 600 == 0:
            sink.seek(0); sink.truncate(0)
        if e.match_state not in ("first_half", "second_half"):
            prev.clear()
            continue
        frames += 1
        b = e.ball
        t = e.time_elapsed
        if not b.is_dead:
            live += 1
        # Running
        for p in e.team0 + e.team1:
            if not getattr(p, "is_active", True):
                continue
            k = id(p)
            q = prev.get(k)
            if q is not None:
                d = (p.pos - q).length() / M_TO_PX
                if d < 1.2 and d / DT <= 12.5:          # (a jump - a sub or a reset - isn't running)
                    v = d / DT
                    dist += d
                    pframes += 1
                    top = max(top, v)
                    band[0 if v < 2 else 1 if v < 4 else 2 if v < 5.5 else 3 if v < 7 else 4] += 1
            prev[k] = p.pos.copy()
        # Shots
        si = getattr(b, "shot_info", None)
        if si and si.get("shooter") is not None and (cur_shot is None or si["time"] != cur_shot["time"]):
            sh = si["shooter"]
            dirn = _dir(sh.team)
            x = sh.pos.x / M_TO_PX if dirn > 0 else L - sh.pos.x / M_TO_PX
            y = sh.pos.y / M_TO_PX
            cur_shot = dict(time=si["time"], team=sh.team, x=x, y=y, type=si.get("type"), score=list(e.score),
                            goal=False, on=False, done=False)
            shots.append(cur_shot)
        if cur_shot is not None and not cur_shot["done"]:
            tm = cur_shot["team"]
            sv = getattr(b, "last_save", None)
            if e.score[tm] > cur_shot["score"][tm]:
                cur_shot.update(goal=True, on=True, done=True)
            elif sv and sv.get("time", -1) >= cur_shot["time"] and sv.get("keeper") is not None \
                    and sv["keeper"].team != tm:
                cur_shot.update(on=True, done=True)
            elif t - cur_shot["time"] > 4.0:
                cur_shot["done"] = True
        # Restarts
        if b.is_dead:
            rt = getattr(b, "restart_type", None)
            key = (rt, round(getattr(b, "restart_time", 0.0) or 0.0, 2))
            if rt and key not in seen_restart:
                seen_restart.add(key)
                restarts[rt] = restarts.get(rt, 0) + 1
        # Passes settled; possessions
        o = b.owner
        if o is not None and o is not last_owner:
            got[id(o)] = (t, (o.pos.x / M_TO_PX, o.pos.y / M_TO_PX))
            for r in pending:
                r["ok"] = (o.team == r["team"])
                passes.append(r)
                if r["team"] == poss_team:
                    poss_passes += 1
            pending.clear()
            if o.team != poss_team:
                if poss_team is not None:
                    possessions.append(poss_passes)
                poss_team, poss_passes = o.team, 0
        elif b.is_dead and pending:
            for r in pending:
                passes.append(r)
                if r["team"] == poss_team:
                    poss_passes += 1
            pending.clear()
        last_owner = o
        # Every half a second: team shape and support
        if frames % 30 == 0 and poss_team is not None and not b.is_dead:
            for tid, team in ((0, e.team0), (1, e.team1)):
                xs = sorted(p.pos.x / M_TO_PX for p in team if p.role != "GK" and getattr(p, "is_active", True))
                ys = sorted(p.pos.y / M_TO_PX for p in team if getattr(p, "is_active", True))
                if len(xs) < 8:
                    continue
                s = shape["att" if tid == poss_team else "def"]
                s[0] += xs[-1] - xs[0]; s[1] += ys[-1] - ys[0]; s[2] += 1
            if o is not None:
                team, other = (e.team0, e.team1) if o.team == 0 else (e.team1, e.team0)
                gk = next((p for p in team if p.role == "GK"), None)
                mates = [(p.pos.x / M_TO_PX, p.pos.y / M_TO_PX, p.vel.x / M_TO_PX, p.vel.y / M_TO_PX)
                         for p in team if p is not o and p is not gk and getattr(p, "is_active", True)]
                opps = [(p.pos.x / M_TO_PX, p.pos.y / M_TO_PX) for p in other if getattr(p, "is_active", True)]
                support.append(sm.moment((o.pos.x / M_TO_PX, o.pos.y / M_TO_PX), _dir(o.team), mates, opps, L))
if poss_team is not None:
    possessions.append(poss_passes)

st = e.stats
S = duels.STATS
takeons = sum(v for k, v in S.items() if isinstance(k, tuple) and k[0] == "takeon")
takeons_won = sum(v for k, v in S.items() if isinstance(k, tuple) and k[0] == "takeon_won")
r = e.result()
res = dict(seed=seed, config=os.environ["FM_MATCH_CONFIG"], minutes=frames * DT / 60.0, live_frames=live, frames=frames,
           goals=r["hg"] + r["ag"], shots=shots, passes=passes, clearances=C["clearances"],
           takeons=takeons, takeons_won=takeons_won, tackles=S.get("tackle", 0), tackles_won=S.get("tackle_won", 0),
           fouls=sum(st.fouls), yellows=sum(st.yellows), reds=sum(st.reds), corners=sum(st.corners), restarts=restarts,
           possessions=possessions, band=band, dist=dist, pframes=pframes, top=top,
           shape=shape, support=support)
json.dump(res, open(out, "w"))
print(f"done: {r['hg']}-{r['ag']}, {len(passes)} passes, {len(shots)} shots, {frames * DT / 60:.0f} min")
