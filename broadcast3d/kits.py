"""
broadcast3d/kits.py
===================
Which kits the two sides wear in the 3D view, from the clubs' own profiles (data/world/clubs/<club>.json).

  - Each club's home, away and third kits: shirt, trim, shorts and socks colours, and the pattern read from the
    profile's words - hoops, stripes, a pinstripe, a sash, a band across the chest, halves, contrasting sleeves,
    sock tops ("red with white tops").
  - The home side wears its home kit.  The away side wears its home kit too, unless the shirts clash, then its
    away kit, then its third (like the real kit-clash rule: the referee has to tell them apart).
  - The goalkeepers get a colour of their own, different from both sides' shirts and from each other.
  - A club with no profile yet: its colour from the club list, white or black shorts to go with it.
"""

import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)
CLUBS = os.path.join(GAME, "data", "world", "clubs")
KEEPER_COLOURS = [(240, 205, 40), (60, 170, 90), (235, 120, 40), (125, 70, 170), (90, 175, 225), (230, 110, 170),
                  (40, 40, 44), (150, 150, 155)]
CLASH = 120             # shirts closer than this (colour distance) can't both be worn


def _dist(a, b):
    """How different two colours look (a weighted RGB distance - green counts most, as the eye sees it)."""
    r = (a[0] + b[0]) / 2
    return ((2 + r / 256) * (a[0] - b[0]) ** 2 + 4 * (a[1] - b[1]) ** 2 + (2 + (255 - r) / 256) * (a[2] - b[2]) ** 2) ** 0.5


def _lum(c):
    return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255


def pattern(words):
    """The shirt's pattern, from how the profile describes it."""
    w = words.lower()
    if "pinstripe" in w:
        return "pinstripe"
    if "hoops" in w:
        return "hoops"
    if "stripes" in w and "thin" not in w:
        return "stripes"
    if "sash" in w:
        return "sash"
    if "halves" in w:
        return "halves"
    if "hoop across" in w or "band across" in w or "band" in w:
        return "band"
    if "sleeves" in w and "with" in w:
        return "sleeves"
    return None


def collar(words):
    """The collar, from the profile's words: 0 a plain round neck, 1 a V-neck, 2 a grandad collar (a band with
    a short button opening), 3 a polo-style collar."""
    w = words.lower()
    if "v-neck" in w or "v neck" in w:
        return 1
    if "grandad" in w:
        return 2
    if "crew" in w:
        return 0
    if "collar" in w:
        return 3
    return 0


def profile(name):
    for f in os.listdir(CLUBS):
        if f.endswith(".json"):
            try:
                d = json.load(open(os.path.join(CLUBS, f), encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if d.get("name") == name or d.get("short") == name:
                return d, f[:-5]
    return None, None


def _club_row(name):
    for fn in ("clubs.csv", "d1_clubs.csv"):
        p = os.path.join(GAME, "data", "world", fn)
        if os.path.exists(p):
            for row in csv.DictReader(open(p, encoding="utf-8")):
                if row.get("name") == name or row.get("short") == name:
                    return row
    return None


def club_kits(name):
    """[home, away, third] kits for a club: each {"shirt", "trim", "shorts", "socks", "socktop", "pattern",
    "number"} - and the club's short name and crest file (or None)."""
    d, slug = profile(name)
    if d:
        out = []
        for k in ("home", "away", "third"):
            kd = d["colours"].get(k)
            if not kd:
                continue
            rgb = kd["rgb"]
            words = f"{kd.get('shirt', '')} {kd.get('socks', '')}"
            socktop = rgb["trim"] if "tops" in kd.get("socks", "") else None
            out.append({"shirt": tuple(rgb["shirt"]), "trim": tuple(rgb.get("trim", rgb["shirt"])),
                        "shorts": tuple(rgb["shorts"]), "socks": tuple(rgb["socks"]), "socktop": socktop,
                        "pattern": pattern(kd.get("shirt", "")), "words": words, "collar": collar(kd.get("shirt", ""))})
        crest = os.path.join(CLUBS, slug, "crest.png")
        info = {"short": d.get("short", name), "crest": crest if os.path.exists(crest) else None}
    else:
        row = _club_row(name) or {"r": 120, "g": 120, "b": 120, "short": name}
        c = (int(row["r"]), int(row["g"]), int(row["b"]))
        dark = _lum(c) < 0.5
        home = {"shirt": c, "trim": (245, 245, 245) if dark else (30, 30, 32),
                "shorts": (245, 245, 245) if dark else (30, 30, 32), "socks": c, "socktop": None, "pattern": None}
        away = {"shirt": (245, 245, 245) if dark else (30, 30, 32), "trim": c, "shorts": c,
                "socks": (245, 245, 245) if dark else (30, 30, 32), "socktop": None, "pattern": None}
        out = [home, away]
        info = {"short": row.get("short", name), "crest": None}
    for k in out:
        k["number"] = (245, 245, 245) if _lum(k["shirt"]) < 0.55 else (25, 25, 28)
        if k["pattern"] in ("stripes", "hoops", "halves") and _lum(k["trim"]) > 0.6 and _lum(k["shirt"]) > 0.4:
            k["number"] = (25, 25, 28)
    return out, info


def choose(home_name, away_name):
    """The kits for both sides and both keepers: (home kit, away kit, home keeper, away keeper, home info,
    away info)."""
    hk, hinfo = club_kits(home_name)
    ak, ainfo = club_kits(away_name)
    home = hk[0]
    away = next((k for k in ak if _dist(k["shirt"], home["shirt"]) >= CLASH), None)
    if away is None:
        away = max(ak, key=lambda k: _dist(k["shirt"], home["shirt"]))
    taken = [home["shirt"], away["shirt"], home["shorts"], away["shorts"]]
    keepers = []
    for _ in range(2):
        c = max(KEEPER_COLOURS, key=lambda g: min(_dist(g, t) for t in taken))
        taken.append(c)
        keepers.append({"shirt": c, "trim": (25, 25, 28) if _lum(c) > 0.5 else (240, 240, 240), "shorts": c,
                        "socks": c, "socktop": None, "pattern": None, "keeper": True,
                        "number": (25, 25, 28) if _lum(c) > 0.55 else (245, 245, 245)})
    return home, away, keepers[0], keepers[1], hinfo, ainfo
