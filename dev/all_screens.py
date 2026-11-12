import os as _os
DEV = _os.path.dirname(_os.path.abspath(__file__))
GAME = _os.environ.get("FM_GAME", _os.path.dirname(DEV))   # the game folder (default: this repo)
OUTDIR = _os.environ.get("FM_OUT", "/tmp/fm_dev")

import os, sys, traceback
src = open(_os.path.join(DEV, "shot.py")).read().split('app.go("squad"); shot("squad")')[0]
exec(src)
from career import transfers as trf
me = c["clubs"][c["my_club"]]
names = sorted(n[5:] for n in dir(app) if n.startswith("draw_") and callable(getattr(app, n)))
print("screens:", names)
# make some inbox traffic: a news item, and run a transfer window day to get offers
trf._message(c, "news", "Test news item.")
p0 = me["players"][3]
trf._message(c, "offer", f"Somebody bid for {p0['Name']}", {"pid": p0["id"], "player": p0["Name"], "fee": 5_000_000,
             "club": 2, "expires": c["date"]})
app.player_view = (me["id"], p0["id"]); app.open_chat(p0["id"])
app.loan_pid = p0["id"]
bad = []
for n in names:
    try:
        app.screen = n
        shot("all_" + n)
    except Exception as e:
        bad.append((n, repr(e)[:150]))
for m in trf.inbox(c):
    app.inbox_sel = m["id"]
    try:
        app.screen = "inbox"; shot(f"inbox_{m['kind']}_{m['id']}")
    except Exception as e:
        bad.append(("inbox " + m["kind"], traceback.format_exc()[-300:]))
print("problems:", bad if bad else "none")
