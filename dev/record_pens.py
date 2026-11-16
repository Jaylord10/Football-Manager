"""Record a penalty shoot-out for the 3D viewer (a check of the shoot-out camera): a career match set up as a
knockout, a few seconds played, then straight to penalties.  usage: python dev/record_pens.py <game_dir> <out.json>
[seconds of shoot-out]   (copy the game to a scratch folder first: it writes saves)."""
import os, sys, io, contextlib, json, random
G = sys.argv[1]; OUT = sys.argv[2]; SECS = float(sys.argv[3]) if len(sys.argv) > 3 else 60
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
sys.path.insert(0, G); os.chdir(G)
sys.path.insert(0, os.path.join(G, "broadcast3d"))
with contextlib.redirect_stdout(io.StringIO()):
    from career import ui, matches
    app = ui.App(); app.new_career_screen(); app.start_career(7); c = app.career
me_id = c["my_club"]
opp = next(i for i in range(20) if i != me_id)
cfg = matches.write_config(c, me_id, opp, "penstest", auto_subs={me_id: True}, human=None)
os.environ["FM_MATCH_CONFIG"] = cfg
import config.formations as formations
from core.database import PlayerDatabase
formations.db = PlayerDatabase(cfg)
formations.db.knockout = {"agg": [0, 0]}
random.seed(5)
import live
with contextlib.redirect_stdout(io.StringIO()):
    import gameplay.match_engine as me
    me.RL_ENABLED = False
    e = me.MatchEngine(career=True)
frames = []
n = 0
with contextlib.redirect_stdout(io.StringIO()):
    while n < 240:                                   # (4 s of play, so everyone's on the pitch)
        e.step(1 / 60); n += 1
    e._start_penalties()
    n = 0
    while n < SECS * 60 and e.match_state == "penalties":
        e.step(1 / 60); n += 1
        if n % 2 == 0:
            frames.append(live.frame_from_engine(e))
names = [[p.name, p.role, getattr(p, "number", None) or (i % 11) + 1] for i, p in enumerate(e.team0 + e.team1)]
json.dump({"home": c["clubs"][me_id]["name"], "away": c["clubs"][opp]["name"], "names": names, "frames": frames},
          open(OUT, "w"))
print("frames", len(frames), "pens", e.shootout.score(), "kicks", e.shootout.kicks)
