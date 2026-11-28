"""What the commentary would say in a match, and when - to read through before making the sound files.
Plays a career match without a screen (at normal speed, as you'd watch it) with gameplay/commentary.py listening,
lines timed by their length (about 14 characters a second), and writes every line said.

usage: python dev/commentary_transcript.py <save.json> <out.txt> [seed] [seconds per half]"""
import os, sys, io, contextlib, random
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.dirname(HERE)
os.chdir(W); sys.path.insert(0, W)
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
save, out = sys.argv[1], sys.argv[2]
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 5
half = float(sys.argv[4]) if len(sys.argv) > 4 else 600.0
from career import league, matches
league.save = lambda *a, **k: None
c = league.load(save)
home, away = c["my_club"], next(cl["id"] for cl in c["clubs"] if cl["id"] != c["my_club"] and
                                 cl.get("league") == c["clubs"][c["my_club"]].get("league"))
cfg = matches.write_config(c, home, away, "proto", auto_subs={home: True}, human=None)
os.environ["FM_MATCH_CONFIG"] = cfg
import config.formations as formations
from core.database import PlayerDatabase
formations.db = PlayerDatabase(cfg)
random.seed(seed)
with contextlib.redirect_stdout(io.StringIO()):
    import gameplay.match_engine as me
    me.RL_ENABLED = False; me.HALF_DURATION_REAL = half
    e = me.MatchEngine(career=True)
import gameplay.commentary as commentary
cm = commentary.Commentary(e, audio=False, seed=seed)
e.commentary = None                              # (ours is driven here)
e.match_speed = 1                                # (watched at normal speed)
length = lambda text: 0.35 + len(text) / 14.0
n = 0
with contextlib.redirect_stdout(io.StringIO()):
    while e.match_state != "full_time" and n < 4 * half * 60 + 60 * 60 * 5:
        e.step(1 / 60); n += 1
        cm.update(e, 1 / 60)
        if n % 2 == 0:
            cm.tick(e, clock=e.time_elapsed, length=length)
    for _ in range(60 * 30):                     # (the full-time words)
        e.time_elapsed += 1 / 60
        cm.tick(e, clock=e.time_elapsed, length=length)
who = {"comm": "Commentator", "co": "Co-comm"}
lines = [f"{e._team_name(0)} {e.score[0]}-{e.score[1]} {e._team_name(1)}", ""]
for t, minute, voice, text in cm.log:
    lines.append(f"{minute:>3}'  {who.get(voice, voice):12s} {text}")
open(out, "w").write("\n".join(lines) + "\n")
print(f"{len(cm.log)} lines said -> {out}")
