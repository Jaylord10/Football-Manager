"""Record a real match from the engine: every 2nd frame (30 fps) - positions, facing, speed, state, ball, the
keepers' dives, dead balls (throw-ins, goal kicks, corners, free kicks, kick-offs: "r" = [kind, taker]) and goal
celebrations ("c" = [team, scorer]) and bookings ("card" = [yellow / second_yellow / red, player]).  usage: python record.py SECONDS [SEED]  (FM_SAVE = the save to use, FM_REC_OUT = where)"""
import os, sys, io, contextlib, json, random
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.dirname(HERE)                # (the game folder)
os.chdir(W); sys.path.insert(0, W)
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
from career import league, matches
league.save = lambda *a, **k: None
c = league.load(os.environ.get("FM_SAVE", os.path.join(W, "saves", "career.json")))
home, away = c["my_club"], 0               # Ashvale v Northwick at Kiln Lane
cfg = matches.write_config(c, home, away, "proto", auto_subs={home: True}, human=None)
os.environ["FM_MATCH_CONFIG"] = cfg
import config.formations as formations
from core.database import PlayerDatabase
formations.db = PlayerDatabase(cfg)
random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else 7)
with contextlib.redirect_stdout(io.StringIO()):
    import gameplay.match_engine as me
    me.RL_ENABLED = False; me.HALF_DURATION_REAL = 600.0
    e = me.MatchEngine(career=True)
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 120
frames = []
n = 0
with contextlib.redirect_stdout(io.StringIO()):
    while n < secs * 60 and e.match_state != "full_time":
        e.step(1 / 60); n += 1
        if n % 2:
            continue
        b = e.ball
        fr = {"t": round(e.time_elapsed, 2), "s": list(e.score), "st": e.match_state,
              "b": [round(b.pos.x, 1), round(b.pos.y, 1), round(getattr(b, "z", 0.0), 1)],
              "o": (e.team0 + e.team1).index(b.owner) if b.owner in e.team0 + e.team1 else -1,
              "p": [[round(p.pos.x, 1), round(p.pos.y, 1), round(p.facing.x, 3), round(p.facing.y, 3),
                     round(p.vel.length(), 1), p.state, int(getattr(p, "is_active", True)),
                     getattr(p, "dive_state", "") if p.role == "GK" else ""] for p in e.team0 + e.team1]}
        everyone = e.team0 + e.team1
        if getattr(b, "is_dead", False) and getattr(b, "restart_type", None):        # (a dead ball: who takes it)
            tk = getattr(b, "restart_taker", None)
            fr["r"] = [b.restart_type, everyone.index(tk) if tk in everyone else -1]
        cd = getattr(e, "_card_display", None)                                        # (a booking: who, which card)
        if cd and e.time_elapsed < cd.get("until", 0):
            who = next((j for j, p in enumerate(everyone) if getattr(p, "name", None) == cd.get("name")), -1)
            fr["card"] = [cd.get("type"), who]
        cel = getattr(b, "_celebration", None)
        if cel and e.time_elapsed < cel.get("until", 0) and cel.get("scorer") in everyone:   # (a goal celebration)
            fr["c"] = [cel["team"], everyone.index(cel["scorer"])]
        frames.append(fr)
names = [[p.name, p.role, getattr(p, "number", i + 1)] for i, p in enumerate(e.team0 + e.team1)]
json.dump({"home": c["clubs"][home]["name"], "away": c["clubs"][away]["name"], "names": names, "frames": frames},
          open(os.environ.get("FM_REC_OUT", os.path.join(HERE, "match.json")), "w"))
print("frames", len(frames), "score", e.score, "state", e.match_state)
