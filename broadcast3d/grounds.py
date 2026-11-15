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
    st.sky_and_hills(lamps)


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
