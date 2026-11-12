"""
career/matches.py
=================
Playing the league's matches with the real match engine.

  - YOUR MATCH is watched in the game window as normal (or played in the
    background if you choose to skip it).
  - THE OTHER MATCHES each run in their own background process, at the
    same time, on the computer's other cores - the full engine, every
    match, just without drawing it.  They start when you kick off, so
    they're usually done by the time you've watched yours.

Each match gets a small match_config file (in saves/configs/) pointing at the
two clubs' squad files, roles and tactics, exactly like match_config.json.
"""

import json
import multiprocessing as mp
import os
import sys
import time

from career import clubs as clubs_mod

CONFIG_DIR = os.path.join("saves", "configs")
SQUAD_DIR = os.path.join("saves", "squads")
HALF_SECONDS = float(os.environ.get("FM_CAREER_HALF", "2700"))   # 45-minute halves (tests can shorten it)


def write_config(career, home_id, away_id, tag, auto_subs=None, human=None, extra=None, friendly=False):
    """A match_config file for this fixture; returns its path.
    auto_subs: {club id: False} for a club whose manager makes his own changes
    (you, watching) - everyone else's are made by the AI / your assistant.
    extra: {club id: club} for clubs not in your league (a friendly's opponents);
    friendly: lots of substitutes, no half-time team talk table (career/friendlies.py)."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    clubs = career["clubs"]
    extra = extra or {}

    from career import availability, league
    date = career.get("date") if friendly else (league.match_date(career) or career.get("date"))

    def team(cid, side):
        c = extra[cid] if cid in extra else clubs[cid]
        c["_vs"] = away_id if cid == home_id else home_id         # (a loanee can't face his parent club)
        out = availability.unavailable_ids(c, date) if date else set()   # injured / suspended
        path = clubs_mod.write_squad_csv(c, SQUAD_DIR, out)
        t = {"id": side, "name": c["name"], "file": path.replace("\\", "/"),
             "primary_color": c["colour"], "roles": c["roles"], "tactics": c["tactics"],
             "instructions": c.get("instructions", {})}
        t["formation"] = clubs_mod.formation_of(c)     # its spots (config/slots.py)
        t.update(clubs_mod.match_squad(c, out))       # bench, ids (gameplay/substitutions.py)
        t["auto_subs"] = (auto_subs or {}).get(cid, True)
        t["human"] = cid == human                     # you, watching: the S panel
        t["friendly"] = bool(friendly)
        if cid == career.get("my_club") and not friendly:   # the half-time team talk (career/teamtalk.py)
            from career import teamtalk
            t["ht_talk"] = teamtalk.half_table(career, c, cid == home_id, t_opp(cid))
        return t

    def t_opp(cid):
        return away_id if cid == home_id else home_id

    name = lambda i: (extra[i] if i in extra else clubs[i])["name"]
    cfg = {"match_name": f"{name(home_id)} v {name(away_id)}",
           "home_team": team(home_id, 0), "away_team": team(away_id, 1)}
    path = os.path.join(CONFIG_DIR, f"{tag}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    return path


# ---------------------------------------------------------------------------
# Background matches
# ---------------------------------------------------------------------------
def _worker(config_path, half_seconds, queue, tag, workdir):
    """Runs in its own process: play one match headless, put the result on the queue."""
    try:
        os.chdir(workdir)
        if workdir not in sys.path:
            sys.path.insert(0, workdir)
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
        os.environ["FM_MATCH_CONFIG"] = config_path
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            import gameplay.match_engine as me
            me.RL_ENABLED = False
            me.HALF_DURATION_REAL = half_seconds
            engine = me.MatchEngine(career=True)
        dt = 1.0 / 60.0
        limit = int((half_seconds * 2 + 600) / dt)
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink):
            for i in range(limit):
                if engine.match_state == "full_time":
                    break
                engine.step(dt)
                if i % 3600 == 0:
                    queue.put(("progress", tag, engine.match_minute()))
                    sink.seek(0); sink.truncate(0)
        queue.put(("done", tag, engine.result()))
    except Exception as e:                                  # report it rather than hang the matchday
        import traceback
        queue.put(("error", tag, f"{e}\n{traceback.format_exc()}"))


class BackgroundMatches:
    """Plays a list of fixtures in background processes, a few at a time."""

    def __init__(self, career, fixtures, matchday):
        self.matchday = matchday
        self.ctx = mp.get_context("spawn")       # same on Windows and everywhere else
        self.queue = self.ctx.Queue()
        self.pending = []
        self.running = {}
        self.results = {}
        self.minutes = {}
        self.errors = {}
        cores = os.cpu_count() or 2
        self.max_parallel = max(1, min(len(fixtures), cores - 1 if cores > 2 else cores))
        for home, away in fixtures:
            tag = f"md{matchday}_{home}_{away}"
            cfg = write_config(career, home, away, tag)
            self.pending.append((tag, home, away, cfg))
        self.fixtures = {tag: (home, away) for tag, home, away, _ in self.pending}
        self.started = time.time()
        self._fill()

    def _fill(self):
        while self.pending and len(self.running) < self.max_parallel:
            tag, home, away, cfg = self.pending.pop(0)
            p = self.ctx.Process(target=_worker, args=(cfg, HALF_SECONDS, self.queue, tag, os.getcwd()),
                                 daemon=True)
            p.start()
            self.running[tag] = p
            self.minutes[tag] = 0

    def poll(self):
        """Call regularly: collects finished matches, starts waiting ones."""
        while True:
            try:
                kind, tag, data = self.queue.get_nowait()
            except Exception:
                break
            if kind == "progress":
                self.minutes[tag] = data
            elif kind == "done":
                self.results[tag] = data
                self.minutes[tag] = 90
            else:
                self.errors[tag] = data
        for tag, p in list(self.running.items()):
            if tag in self.results or tag in self.errors:
                p.join(timeout=0.1)
                del self.running[tag]
            elif not p.is_alive() and tag not in self.results:
                self.errors[tag] = "the match process stopped unexpectedly"
                del self.running[tag]
        self._fill()

    def done(self):
        return not self.pending and not self.running

    def progress(self):
        """(finished, total, list of (home, away, minute))"""
        total = len(self.fixtures)
        fin = len(self.results) + len(self.errors)
        live = [(self.fixtures[t][0], self.fixtures[t][1], self.minutes.get(t, 0)) for t in self.fixtures
                if t not in self.results and t not in self.errors]
        return fin, total, live

    def result_list(self):
        out = []
        for tag, (home, away) in self.fixtures.items():
            r = self.results.get(tag)
            if r is None:
                continue
            out.append(_summary(home, away, r))
        return out

    def stop(self):
        for p in self.running.values():
            if p.is_alive():
                p.terminate()


# ---------------------------------------------------------------------------
# Watching your match
# ---------------------------------------------------------------------------
def watch(career, home, away, matchday):
    """Play the match in the game window.  Returns (result, quit_requested)."""
    me_id = career["my_club"]
    cfg = write_config(career, home, away, f"md{matchday}_{home}_{away}_watch",
                       auto_subs={me_id: career.get("assistant_subs", True)}, human=me_id)
    os.environ["FM_MATCH_CONFIG"] = cfg
    import config.formations as formations
    from core.database import PlayerDatabase
    formations.db = PlayerDatabase(cfg)            # load these two squads
    import gameplay.match_engine as me
    me.RL_ENABLED = False
    me.HALF_DURATION_REAL = HALF_SECONDS
    engine = me.MatchEngine(career=True)
    engine.run()
    if engine.my_team is not None:
        career["assistant_subs"] = engine.subs.auto[engine.my_team]   # remembered for next time
    if engine.match_state != "full_time":
        return None, engine.quit_requested         # left before the end
    r = engine.result()
    return _summary(home, away, r), engine.quit_requested


def watch_friendly(career, f):
    """Watch a friendly (career/friendlies.py).  Returns (result, quit_requested)."""
    from career import friendlies
    me_id = career["my_club"]
    home, away = friendlies.sides(career, f)
    extra = {c["id"]: c for c in (home, away) if c["id"] != me_id}
    cfg = write_config(career, home["id"], away["id"], f"friendly_{f['id']}_watch",
                       auto_subs={me_id: career.get("assistant_subs", True)}, human=me_id, extra=extra, friendly=True)
    os.environ["FM_MATCH_CONFIG"] = cfg
    import config.formations as formations
    from core.database import PlayerDatabase
    formations.db = PlayerDatabase(cfg)
    import gameplay.match_engine as me
    me.RL_ENABLED = False
    me.HALF_DURATION_REAL = HALF_SECONDS
    engine = me.MatchEngine(career=True)
    engine.run()
    if engine.my_team is not None:
        career["assistant_subs"] = engine.subs.auto[engine.my_team]
    if engine.match_state != "full_time":
        return None, engine.quit_requested
    return _summary(home["id"], away["id"], engine.result()), engine.quit_requested


def watch_playoff(career, m):
    """Watch a play-off match (career/playoffs.py): a competitive match, 90 minutes.  (result, quit)"""
    me_id = career["my_club"]
    cfg = write_config(career, m["home"], m["away"], f"playoff_{m['id']}_watch",
                       auto_subs={me_id: career.get("assistant_subs", True)}, human=me_id)
    os.environ["FM_MATCH_CONFIG"] = cfg
    import config.formations as formations
    from core.database import PlayerDatabase
    formations.db = PlayerDatabase(cfg)
    import gameplay.match_engine as me
    me.RL_ENABLED = False
    me.HALF_DURATION_REAL = HALF_SECONDS
    engine = me.MatchEngine(career=True)
    engine.run()
    if engine.my_team is not None:
        career["assistant_subs"] = engine.subs.auto[engine.my_team]
    if engine.match_state != "full_time":
        return None, engine.quit_requested
    return _summary(m["home"], m["away"], engine.result()), engine.quit_requested


def _summary(home, away, r):
    """What the career keeps from a match."""
    return {"home": home, "away": away, "hg": r["hg"], "ag": r["ag"], "goals": r["goals"],
            "possession": r["possession"], "subs": r.get("subs", []), "players": r.get("players", []),
            "ht_talk": r.get("ht_talk")}
