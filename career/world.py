"""
career/world.py
===============
The football world: the 20 clubs and their 500 players - the same in every
new career (like a Football Manager database), so you get to know them and
we can tune them.

It lives in two files you can open and edit:

  data/world/clubs.csv    one row per club: id, name, short name, colour,
                          strength, style (defence, build-up), role set
  data/world/players.csv  one row per player: club, id, name, position, age,
                          potential (hidden in the game), then every
                          attribute on the 0-100 scale (the engine uses /5)

If the files aren't there they're built once from WORLD_SEED with the
generator in career/clubs.py (realistic pace etc. - see its notes), and
written out.  Delete them to build a fresh world; edit them to change it.
A career copies the world when it starts, so editing the files never
changes a career already in progress.
"""

import csv
import os

from career import clubs as clubs_mod

WORLD_DIR = os.path.join("data", "world")
CLUBS_FILE = os.path.join(WORLD_DIR, "clubs.csv")
PLAYERS_FILE = os.path.join(WORLD_DIR, "players.csv")
WORLD_SEED = 2026

CLUB_COLS = ["id", "name", "short", "r", "g", "b", "strength", "defence", "build_up", "roles"]
PLAYER_META = ["club", "id", "Name", "Pos", "Age", "Potential"]


def build(seed=WORLD_SEED):
    """Generate the world and write it to the files."""
    world = clubs_mod.generate(seed, n_clubs=20)
    save(world)
    return world


def save(world, clubs_file=CLUBS_FILE, players_file=PLAYERS_FILE, extra=()):
    """extra: more player columns (the Spanish league: non_eu)."""
    os.makedirs(WORLD_DIR, exist_ok=True)
    with open(clubs_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CLUB_COLS)
        for c in world:
            w.writerow([c["id"], c["name"], c["short"], *c["colour"], c["strength"],
                        c["tactics"]["defence"], c["tactics"]["build_up"], c["roles"].get("base", "blue")])
    with open(players_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(PLAYER_META + list(extra) + clubs_mod.COLUMNS)
        for c in world:
            for p in c["players"]:
                w.writerow([c["id"], p["id"], p["Name"], p["Pos"], p["Age"], p.get("Potential", "")]
                           + [int(bool(p.get(e))) for e in extra] + [p[col] for col in clubs_mod.COLUMNS])


def load(clubs_file=CLUBS_FILE, players_file=PLAYERS_FILE, extra=(), build_fn=None):
    """The world from the files (built first if they're missing).  Returns the clubs, strongest first."""
    if not (os.path.exists(clubs_file) and os.path.exists(players_file)):
        return (build_fn or build)()
    world = {}
    with open(clubs_file, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            cid = int(row["id"])
            world[cid] = {
                "id": cid, "name": row["name"], "short": row["short"],
                "colour": [int(row["r"]), int(row["g"]), int(row["b"])],
                "strength": int(float(row["strength"])) if float(row["strength"]).is_integer() else float(row["strength"]),
                "roles": {"base": row.get("roles") or "blue"},
                "tactics": {"defence": row["defence"], "build_up": row["build_up"]},
                "instructions": {},
                "players": [],
            }
    with open(players_file, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            c = world.get(int(row["club"]))
            if c is None:
                continue
            p = {"id": int(row["id"]), "Name": row["Name"], "Pos": row["Pos"], "Age": int(row["Age"])}
            try:
                p["Potential"] = float(row["Potential"])
            except (TypeError, ValueError):
                p["Potential"] = None
            for col in clubs_mod.COLUMNS:
                try:
                    p[col] = int(float(row[col]))
                except (TypeError, ValueError, KeyError):
                    p[col] = 50
            for e in extra:
                p[e] = str(row.get(e, "0")).strip() in ("1", "True", "true")
            c["players"].append(p)
    out = [world[k] for k in sorted(world)]
    for c in out:
        c["lineup"] = clubs_mod.best_lineup(c)
    return out
