"""
broadcast3d/grounds.py - any club's ground, built from its profile (data/world/clubs/<club>.json, "ground").

Kiln Lane (Ashvale) is built by hand in viewer.py.  Every other ground comes from what its profile says:
  - each stand on its side of the pitch (west = the Main Stand side, under the TV camera; east = the far side;
    north = the left end; south = the right end), its tiers, its size from its capacity, its roof (cantilever,
    on pillars / columns, pitched, glass, part of a bowl), and its name along the roof;
  - the corners: open, some filled in, or closed all the way round (a bowl);
  - the away fans where the profile puts them (an end, a corner, an upper or lower tier);
  - the home fans in the club's colours; the fascias in the club colour.
Real-world sizes: ~0.5 m of row per seat (so ~2 seats a metre of stand), rows ~0.8 m deep and ~0.45 m higher
than the one in front (steeper in upper tiers, ~0.55 m) - the UK Green Guide's sightline ranges.
"""
import math
import kits
import textures
from geom import box

C = HX = HY = None


def _viewer():
    """The viewer module (it's usually the one running, as __main__)."""
    import sys
    m = sys.modules.get("__main__")
    if m is not None and hasattr(m, "Stadium"):
        return m
    import viewer
    return viewer

SIDES = {"west": "near", "east": "far", "north": "left", "south": "right"}
COMPASS = {"north": (-1, 0), "south": (1, 0), "east": (0, 1), "west": (0, -1)}     # (world directions)
HEADING = {"far": 0, "near": 180, "left": 90, "right": -90}


def _away_spec(text, stands):
    """Where the away fans go: (side, part) - part None (the whole stand), "lower" / "upper", or a compass
    direction (the end of the stand nearest it, for a corner)."""
    t = (text or "").lower()
    side = next((s for s in ("north", "south", "east", "west") if t.startswith(s)), None)
    if side is None:
        side = "south"
    part = None
    if "lower" in t:
        part = "lower"
    elif "upper" in t:
        part = "upper"
    elif "corner" in t and "-" in t.split()[0]:
        part = t.split()[0].split("-")[1]
    return side, part


# The play-off final's neutral ground (career/playoffs.py: "the National Bowl"): a modern bowl on the lines of
# Wembley - 90,000 seats in three tiers all the way round, a roof over them all, the pitch a hybrid
# (wembleystadium.com, "Stats and facts").  Fans of both clubs: the "home" end and the other end.
NATIONAL = {
    "name": "the National Bowl",
    "ground": {
        "name": "the National Bowl", "capacity": 90000,
        "pitch": {"surface": "hybrid - perfect"},
        "stands": [{"name": side.title() + " Stand", "side": side, "tiers": 3, "capacity": 22500,
                    "roof": "a modern roof"} for side in ("west", "east", "north", "south")],
        "corners": "a closed bowl - all four corners filled",
        "roof": "a modern roof all the way round",
        "for_the_engine": {"home_end": "south", "away_fans": "north end", "dugouts": "west side, halfway line",
                           "pitch_m": [105, 68]},
    },
}


def _filled_corners(text):
    t = (text or "").lower()
    if any(w in t for w in ("closed", "bowl", "continuous", "all four")):
        return {"north-east", "north-west", "south-east", "south-west"}
    out = set()
    if "filled" not in t:
        return out
    for pair in ("north-east", "north-west", "south-east", "south-west"):
        if pair in t:
            out.add(pair)
    for word, sides in (("northern", ("north-east", "north-west")), ("southern", ("south-east", "south-west")),
                        ("eastern", ("north-east", "south-east")), ("western", ("north-west", "south-west"))):
        if word in t:
            out.update(sides)
    return out


def build(st, prof, kit):
    global C, HX, HY
    v = _viewer()
    C, HX, HY = v.C, v.HX, v.HY
    g = prof["ground"]
    eng = g.get("for_the_engine", {})
    shirt, trim = kit["shirt"], kit.get("trim", kit["shirt"])
    dark = sum(shirt) < 200
    textures.crowd("crowd_hosts.png", [(shirt, 6), (trim, 2), ((30, 30, 34), 2), ((235, 235, 235), 1)], seed=5)
    hosts = "crowd_hosts.png"
    visitors = st.visitors()
    away_side, away_part = _away_spec(eng.get("away_fans"), g["stands"])
    corners = _filled_corners(g.get("corners"))
    st.pitch_surround()
    depth = {}                                                    # (each side: how deep and high it is)
    lamps = []
    for s in g["stands"]:
        where = SIDES.get(s.get("side"), None)
        if where is None:
            continue
        info = _stand(st, where, s, hosts, visitors, (away_side, away_part), shirt, trim, dark)
        depth[s["side"]] = info
        if where != "near":
            lamps.append((where, -info["half"] + 3, info["half"] - 3, info["roof_d0"], info["roof_z"] - 0.4))
    for c in corners:                                             # (filled corners: seats across the gap)
        a, b = c.split("-")
        da, db = depth.get(a), depth.get(b)
        if not da or not db:
            continue
        _corner(st, a, b, min(da["rows"], db["rows"]), hosts, shirt)
    town = (prof.get("location") or {}).get("town") or prof.get("short", "")
    club = prof.get("name", town)
    fg = (255, 255, 255) if dark or sum(shirt) < 450 else (25, 25, 28)
    st.ad_boards([(club.upper(), tuple(shirt), fg), ("THE NATIONAL CHRONICLE", (25, 30, 60), (255, 255, 255)),
                  (f"{town.upper()} EVENING NEWS", (30, 30, 30), (255, 200, 40)),
                  (f"{town.upper()} BUILDING SOC.", (10, 90, 160), (255, 255, 255)),
                  (f"{prof.get('short', town).upper()} FOUNDATION", (240, 240, 240), tuple(shirt) if not dark else (30, 30, 34)),
                  (f"{town.upper()} MOTORS", (20, 60, 40), (240, 210, 120))])
    st.b.led_ads = (g.get("capacity") or 0) >= 40000                  # (the bigger grounds have LED boards)
    near = st.side("near")
    st.dugouts(near)
    # the outside: a wall round the ground, a few streets of houses, hills beyond
    for x0, y0, x1, y1 in ((-HX - 40, HY + 46, HX + 40, HY + 47), (-HX - 40, -HY - 36, HX + 40, -HY - 35),
                           (-HX - 41, -HY - 36, -HX - 40, HY + 47), (HX + 40, -HY - 36, HX + 41, HY + 47)):
        wn = st.root.attachNewNode(st._brick_block(x0, y0, x1, y1, 5)); wn.setTexture(st.T("brick.png"))
    for side_x in (-1, 1):
        for i in range(8):
            hb = st.root.attachNewNode(st._brick_block(side_x * (HX + 56) - 4, -36 + i * 9.5, side_x * (HX + 56) + 4,
                                                        -36 + i * 9.5 + 8.6, 8))
            hb.setTexture(st.T("brick.png"))
    _scenery(st, g, depth, eng)
    st.sky_and_hills(lamps)


# --- what's round the ground: from the profile's "surroundings" (and a big screen from "corners") ----------------
FEATURES = [("viaduct", "viaduct"), ("chimney", "chimney"), ("headframe", "headframe"), ("winding", "headframe"),
            ("pit wheel", "headframe"), ("crane", "cranes"), ("lighthouse", "lighthouse"), ("oast", "oasts"),
            ("cooling tower", "cooling"), ("spire", "spire"), ("cathedral", "spire"), ("skyscraper", "towers"),
            ("tower blocks", "towers"), ("towers", "towers"), ("river", "water"), ("canal", "water"),
            ("mere", "water"), ("sea", "water"), ("harbour", "water"), ("docks", "water"), ("thames", "water"),
            ("brook", "water"), ("mill pond", "water"), ("water tower", "watertower"), ("gasholder", "gasholder")]


def _clause_side(clause, g, eng):
    """Which side of the ground a bit of the description is on (the far side, if it doesn't say)."""
    c = clause.lower()
    if "home end" in c:
        return eng.get("home_end", "north")
    for s in g.get("stands", []):
        nm = (s.get("name") or "").lower()
        if nm and nm in c:
            return s.get("side", "east")
    if "main stand" in c:
        return "west"
    for word in ("north", "south", "east", "west"):
        if word in c:
            return word
    return "east"


def _scenery(st, g, depth, eng):
    import re
    from geom import prism
    text = (g.get("surroundings") or "")
    clauses = [c.strip() for c in re.split(r"[;,]| - ", text) if c.strip()]
    placed = {}
    for clause in clauses:
        cl = clause.lower()
        for key, kind in FEATURES:
            if key in cl:
                side = _clause_side(clause, g, eng)
                k = placed.get(side, 0)
                placed[side] = k + 1
                _feature(st, kind, side, k, depth.get(side, {}).get("d_back", 30.0), prism)
                break
    if "big screen" in (g.get("corners") or "").lower():
        _big_screen(st)


def _side_frame(st, side, dist, along):
    """A point behind a side of the ground: dist metres out from its touchline / goal line, along it by along."""
    where = SIDES[side]
    n = st.side(where)
    p = n.attachNewNode("feature"); p.setPos(along, dist, 0)
    return p


def _feature(st, kind, side, k, d_back, prism):
    end = side in ("north", "south")
    span = 30.0 if end else 55.0
    along = (-0.55 + 0.45 * (k % 3)) * span * (1 if k % 2 == 0 else -1)
    dist = d_back + 25 + 18 * (k % 2)
    if side == "west":                                            # (the camera's side: well behind the TV gantry,
        dist = max(dist, 95.0)                                    #  so it never blocks the picture)
    brick = st.T("brick.png")
    if kind == "chimney":
        p = _side_frame(st, side, dist + 10, along)
        c = prism(p, 2.4, 52, sides=12, taper=0.62, uv_rep=(4, 12)); c.setTexture(brick)
    elif kind == "viaduct":
        p = _side_frame(st, side, dist + 20, 0)
        for i in range(16):
            x = -80 + i * 10.6
            box(p, x - 1.4, -2.5, 0, x + 1.4, 2.5, 26, C((150, 140, 125)))
        box(p, -82, -3, 26, 90, 3, 30, C((150, 140, 125)))
    elif kind == "headframe":
        p = _side_frame(st, side, dist, along)
        col = C((70, 74, 80))
        for sx in (-1, 1):
            leg = box(p, -0.4, -0.4, 0, 0.4, 0.4, 32, col); leg.setPos(sx * 4, 0, 0); leg.setR(-sx * 6)
            br = box(p, -0.3, -0.3, 0, 0.3, 0.3, 30, col); br.setPos(sx * 4, -9, 0); br.setP(18)
        for sx in (-1, 1):
            wh = p.attachNewNode("wheel"); wh.setPos(sx * 2, 0, 31)
            for a in range(0, 360, 30):
                sp = box(wh, -0.12, -0.12, 0, 0.12, 0.12, 3.2, col); sp.setR(a)
    elif kind == "cranes":
        for j in range(2):
            p = _side_frame(st, side, dist + 15, along + j * 22)
            yel = C((215, 170, 40))
            for sx in (-1, 1):
                box(p, sx * 5 - 0.5, -0.5, 0, sx * 5 + 0.5, 0.5, 38, yel)
            box(p, -6, -1, 38, 6, 1, 41, yel)
            box(p, -1, -30, 40, 1, 30, 42, yel)
    elif kind == "lighthouse":
        p = _side_frame(st, side, dist + 40, along)
        for i in range(6):
            col = C((240, 240, 240)) if i % 2 == 0 else C((200, 40, 45))
            t = prism(p, 3.2 - i * 0.25, 5, sides=12, taper=0.93); t.setZ(i * 5); t.setColor(col)
        box(p, -2, -2, 30, 2, 2, 33, C((250, 240, 180)))
    elif kind == "oasts":
        for j in range(3):
            p = _side_frame(st, side, dist + 5, along + j * 9)
            r = prism(p, 3.2, 9, sides=12); r.setTexture(brick)
            cone = prism(p, 3.4, 6, sides=12, taper=0.08); cone.setZ(9); cone.setColor(C((90, 70, 55)))
            box(p, -0.9, -0.9, 15, 0.9, 0.9, 17.5, C((245, 245, 240)))
    elif kind == "cooling":
        for j in range(2):
            p = _side_frame(st, side, dist + 260, along + j * 70)
            a = prism(p, 30, 50, sides=16, taper=0.7); a.setColor(C((170, 170, 168)))
            b = prism(p, 21, 25, sides=16, taper=1.15); b.setZ(50); b.setColor(C((170, 170, 168)))
    elif kind == "spire":
        p = _side_frame(st, side, dist + 150, along)
        tw = box(p, -5, -5, 0, 5, 5, 34, C((150, 140, 120)))
        sp = prism(p, 5.5, 32, sides=8, taper=0.04); sp.setZ(34); sp.setColor(C((120, 115, 105)))
    elif kind == "towers":
        for j in range(4):
            p = _side_frame(st, side, dist + 320 + j * 40, along - 90 + j * 55)
            h = 70 + (j * 37) % 60
            box(p, -9, -9, 0, 9, 9, h, C((150 + j * 8, 160 + j * 6, 170)))
    elif kind == "water":
        p = _side_frame(st, side, dist - 6, 0)
        w = box(p, -140, 0, -0.3, 140, 28, -0.1, (0.32, 0.4, 0.46, 1))
    elif kind == "watertower":
        p = _side_frame(st, side, dist + 12, along)
        for sx in (-1, 1):
            for sy in (-1, 1):
                box(p, sx * 3 - 0.3, sy * 3 - 0.3, 0, sx * 3 + 0.3, sy * 3 + 0.3, 22, C((110, 100, 90)))
        t = prism(p, 5, 7, sides=12); t.setZ(22); t.setTexture(brick)
    elif kind == "gasholder":
        p = _side_frame(st, side, dist + 30, along)
        for a in range(0, 360, 30):
            x, y = 16 * math.cos(math.radians(a)), 16 * math.sin(math.radians(a))
            box(p, x - 0.4, y - 0.4, 0, x + 0.4, y + 0.4, 30, C((80, 84, 92)))
        for z in (10, 20, 30):
            g = prism(p, 16.3, 0.6, sides=24); g.setZ(z); g.setColor(C((80, 84, 92)))


def _big_screen(st):
    """A big screen in a corner (the far right), showing the club name."""
    from panda3d.core import TextNode
    p = st.root.attachNewNode("screen"); p.setPos(HX + 9, HY + 9, 0); p.setH(-135)
    box(p, -0.5, -0.5, 0, 0.5, 0.5, 9, C((50, 52, 58)))
    box(p, -7, -0.6, 9, 7, 0.6, 17, C((25, 25, 28)))
    face = box(p, -6.6, -0.75, 9.4, 6.6, -0.6, 16.6, (0.1, 0.25, 0.4, 1))
    face.setShaderOff(1); face.setLightOff(1)


def _stand(st, where, s, hosts, visitors, away, shirt, trim, dark):
    n = st.side(where)
    end = where in ("left", "right")
    roof_words = (s.get("roof") or "").lower()
    cap = float(s.get("capacity") or 8000)
    tiers = max(1, int(s.get("tiers") or 1))
    half = 36.0 if end else 52.0
    length = 2 * half
    rows = max(12.0, min(70.0, cap / (2.0 * length)))
    if where == "near":                                           # (the camera's stand: just its front rows)
        rows, tiers = min(rows, 14.0), 1
    per = rows / tiers
    d0, z0 = (7.5 if end else 8.5), 1.2
    tops = []
    away_side, away_part = away
    for t in range(tiers):
        rise = 0.45 if t == 0 else 0.55
        d1, z1 = d0 + per * 0.8, z0 + per * rise
        crowd = hosts
        mine = SIDES.get(away_side) == where
        if mine and (away_part is None or (away_part == "lower" and t == 0) or (away_part == "upper" and t == tiers - 1)):
            crowd = visitors
        if mine and away_part in COMPASS:                         # (a corner of this stand for the away fans)
            h = math.radians(HEADING[where])
            lx = (math.cos(h), math.sin(h))                       # (this stand's local x, in the world)
            cx, cy = COMPASS[away_part]
            sgn = 1 if lx[0] * cx + lx[1] * cy > 0 else -1
            cut = half * 0.35 * sgn
            fas = shirt if not dark else trim
            if sgn > 0:
                st.tier(n, -half, cut, d0, z0, d1, z1, hosts, fas)
                st.tier(n, cut, half, d0, z0, d1, z1, visitors, fas)
            else:
                st.tier(n, -half, cut, d0, z0, d1, z1, visitors, fas)
                st.tier(n, cut, half, d0, z0, d1, z1, hosts, fas)
        else:
            st.tier(n, -half, half, d0, z0, d1, z1, crowd, shirt if t == 0 or not dark else trim)
        tops.append((d0, z0, d1, z1))
        if t < tiers - 1:                                         # (the next tier hangs over this one)
            nd0 = d1 - per * 0.8 * 0.3
            box(n, -half, nd0 - 0.4, z1 + 0.4, half, nd0, z1 + 3.2, C(trim if dark else shirt))     # (its fascia)
            d0, z0 = nd0, z1 + 3.4
    d_back, z_top = tops[-1][2], tops[-1][3]
    roof_z = z_top + 3.8
    if where != "near":                                           # (the camera's stand: no back to block the view)
        st.back_wall(n, -half, half, d_back + 0.4, 0, roof_z)
    col = (70, 74, 80)
    columns = 0
    pitched = 0
    if any(w in roof_words for w in ("pillar", "column")) or (("1950s" in roof_words or "1960s" in roof_words)
                                                              and "cantilever" not in roof_words):
        columns = 6 if not end else 4
    if "pitched" in roof_words:
        pitched = 2.5
    roof_d0 = tops[0][0] + (1.0 if columns else 3.0)
    if where != "near":
        st.roof(n, -half - 1, half + 1, roof_d0, d_back + 1.0, roof_z, col=col, columns=columns, pitched=pitched)
        if "glass" in roof_words:                                 # (a glass front edge)
            from panda3d.core import TransparencyAttrib
            gl = box(n, -half - 1, roof_d0 - 6, roof_z, half + 1, roof_d0, roof_z + 0.2, (0.75, 0.85, 0.9, 0.35))
            gl.setTransparency(TransparencyAttrib.MAlpha); gl.setDepthWrite(False)
        _name_board(n, s.get("name", ""), half, roof_d0, roof_z, shirt, trim, dark)
    return {"rows": rows, "half": half, "roof_d0": roof_d0, "roof_z": roof_z, "d_back": d_back}


def _name_board(n, name, half, d, z, shirt, trim, dark):
    """The stand's name in big letters along the front of its roof."""
    from panda3d.core import TextNode
    if not name:
        return
    box(n, -half - 1, d - 0.15, z - 1.6, half + 1, d, z + 0.6, C(shirt if not dark else (32, 32, 36)))
    tn = TextNode("standname"); tn.setText(name.upper()); tn.setAlign(TextNode.ACenter)
    tn.setTextColor(*C(trim if sum(trim) > 300 else (240, 240, 240)))
    t = n.attachNewNode(tn); t.setPos(0, d - 0.2, z - 1.15); t.setScale(1.5); t.setH(180)
    t.setShaderOff(1); t.setLightOff(1)


def _corner(st, a, b, rows, hosts, shirt):
    """Seats across an open corner (between the a and b stands): an angled block of crowd."""
    ca, cb = COMPASS[a], COMPASS[b]
    sx = ca[0] or cb[0]
    sy = ca[1] or cb[1]
    node = st.root.attachNewNode("corner")
    node.setPos(sx * HX, sy * HY, 0)
    node.setH(math.degrees(math.atan2(-sx, sy)))
    w = 16.0
    d0 = 13.0
    st.tier(node, -w, w, d0, 1.2, d0 + rows * 0.8, 1.2 + rows * 0.45, hosts, shirt)
