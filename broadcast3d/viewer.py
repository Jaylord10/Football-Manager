"""
Broadcast-view prototype (Panda3D): plays back a match recorded from our engine,
at Kiln Lane, from a TV gantry camera in the Main Stand.
usage: python viewer.py [first_frame] [n_frames] [out_dir]   (renders frames offscreen)
"""
import sys, json, math, os
from panda3d.core import loadPrcFileData
OFF = "--live" not in sys.argv
CLOSE = "--close" in sys.argv
FOLLOW = next((int(a.split("=", 1)[1]) for a in sys.argv if a.startswith("--follow=")), None)
                                            # (--follow=0: a close camera on one player, e.g. a keeper)
TEAMS = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--teams=")), None)
                                            # (--teams=Penrith,Fernley: show other clubs' kits)
OVERCAST = "--overcast" in sys.argv
NIGHT = "--night" in sys.argv               # (an evening kick-off under the floodlights)
RAIN = "--rain" in sys.argv                 # (Lancashire drizzle: grey light, rain falling, a wet pitch)
if RAIN:
    OVERCAST = True
SUN_AZ, SUN_EL = 200.0, 22.0               # the sun: degrees round from behind the Main Stand, and up
SHADOW_MAP = 4096
ANIM = "--boxes" not in sys.argv          # (animated figures unless --boxes: the old block players)
loadPrcFileData("", ("window-type offscreen\n" if OFF else "") + "win-size 1280 720\naudio-library-name null\n"
                "framebuffer-multisample 1\nmultisamples 4\ntextures-power-2 none\nsync-video 0")
from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
from direct.gui.OnscreenImage import OnscreenImage
from panda3d.core import (AmbientLight, DirectionalLight, Vec4, Vec3, Point3, CardMaker, TextNode, PNMImage, Shader, BitMask32,
                          Filename, Texture, SamplerState, TransparencyAttrib, AntialiasAttrib, Fog)
from geom import Mesh, box, box_into, sphere, prism

HERE = os.path.dirname(os.path.abspath(__file__))       # (this folder: broadcast3d/)
GAME = os.path.dirname(HERE)                             # (the game folder)
sys.path.insert(0, HERE)
T = os.path.join(HERE, "tex") + os.sep
CLUBS = os.path.join(GAME, "data", "world", "clubs") + os.sep
L, WD = 110.0, 70.0
HX, HY = L / 2, WD / 2


NO_SHADOW_BIT = BitMask32.bit(5)           # what the sun's shadow camera sees (hide() a node from it: it casts none)


def no_shadow(np, lit=True):
    """This node casts no shadow (the pitch, the sky...); lit=False: and isn't lit at all (drawn as it is)."""
    np.hide(NO_SHADOW_BIT)
    if not lit:
        np.setShaderOff(1)
    return np


def C(rgb, a=1.0):
    return (rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, a)


def to_world(x, y):
    """engine pixels (0..1100, 0..700, y down) -> Panda metres (centre origin, +Y = far side)"""
    return x / 10.0 - HX, HY - y / 10.0


class Stadium:
    def __init__(self, base):
        self.b = base
        self.root = base.render.attachNewNode("stadium")
        self.tex = {}

    def T(self, name, rep=True):
        if name not in self.tex:
            t = self.b.loader.loadTexture(T + name)
            t.setMinfilter(SamplerState.FT_linear_mipmap_linear); t.setAnisotropicDegree(8)
            if rep:
                t.setWrapU(Texture.WM_repeat); t.setWrapV(Texture.WM_repeat)
            self.tex[name] = t
        return self.tex[name]

    def visitors(self):
        """The away fans' end: a crowd in the visitors' colours (made for each match)."""
        try:
            import kits, textures
            away = TEAMS[1] if TEAMS else self.b.m.get("away", "Northwick FC")
            k0 = kits.club_kits(away)[0][0]
            textures.crowd("crowd_visitors.png", [(k0["shirt"], 5), (k0.get("trim", k0["shirt"]), 2),
                                                  ((30, 30, 34), 2), ((70, 70, 90), 1)], seed=4)
            return "crowd_visitors.png"
        except Exception:
            return "crowd_mixed.png"

    def side(self, where):
        n = self.root.attachNewNode(where)
        pos = {"far": ((0, HY, 0), 0), "near": ((0, -HY, 0), 180), "left": ((-HX, 0, 0), 90), "right": ((HX, 0, 0), -90)}[where]
        n.setPos(*pos[0]); n.setH(pos[1])
        return n

    def tier(self, parent, x0, x1, d0, z0, d1, z1, crowd="crowd_home.png", fascia=(200, 40, 45), wall=(70, 72, 78)):
        m = Mesh("crowd")
        rep = (x1 - x0) / 14.0
        m.quad((x0, d0, z0), (x1, d0, z0), (x1, d1, z1), (x0, d1, z1), (1, 1, 1, 1),
               ((0, 0), (rep, 0), (rep, 1), (0, 1)))
        cn = parent.attachNewNode(m.node()); cn.setTexture(self.T(crowd)); cn.setTwoSided(True)
        cn.setShaderInput("crowd_amt", 1.0)
        self.b.crowds.append((cn, crowd))
        s = Mesh("struct")
        s.quad((x0, d0 - 0.05, z0 - 1.2), (x1, d0 - 0.05, z0 - 1.2), (x1, d0 - 0.05, z0 + 0.15), (x0, d0 - 0.05, z0 + 0.15), C(fascia))
        s.quad((x0, d0, z0 - 1.2), (x0, d1, z1), (x0, d1 + 0.01, z0 - 1.2), (x0, d0, z0 - 1.2), C(wall))
        s.quad((x0, d0, z0 - 1.2), (x0, d0, z0), (x0, d1, z1), (x0, d1, z0 - 1.2), C(wall))
        s.quad((x1, d1, z0 - 1.2), (x1, d1, z1), (x1, d0, z0), (x1, d0, z0 - 1.2), C(wall))
        sn = parent.attachNewNode(s.node()); sn.setTwoSided(True)

    def roof(self, parent, x0, x1, d0, d1, z, col=(70, 74, 80), columns=0, truss=None, pitched=0):
        if pitched:
            m = Mesh("roof")
            mid = (d0 + d1) / 2
            m.quad((x0, d0, z), (x1, d0, z), (x1, mid, z + pitched), (x0, mid, z + pitched), C(col))
            m.quad((x0, mid, z + pitched), (x1, mid, z + pitched), (x1, d1, z), (x0, d1, z), C(col))
            m.tri3((x0, d0, z), (x0, mid, z + pitched), (x0, d1, z), C(col))
            m.tri3((x1, d1, z), (x1, mid, z + pitched), (x1, d0, z), C(col))
            n = parent.attachNewNode(m.node()); n.setTwoSided(True)
        else:
            box(parent, x0, d0, z, x1, d1, z + 0.6, C(col))
        if truss:
            box(parent, x0, d0 - 0.4, z - 1.6, x1, d0 + 0.2, z - 1.0, C(truss))
            box(parent, x0, d0 - 0.4, z - 0.2, x1, d0 + 0.2, z + 0.4, C(truss))
            n = int((x1 - x0) / 4)
            for i in range(n + 1):
                x = x0 + i * (x1 - x0) / n
                box(parent, x - 0.12, d0 - 0.3, z - 1.6, x + 0.12, d0 + 0.1, z, C(truss))
        for i in range(columns):
            x = x0 + (i + 0.5) * (x1 - x0) / columns
            box(parent, x - 0.25, d0 + 0.3, 0, x + 0.25, d0 + 0.8, z, C((60, 62, 68)))

    def back_wall(self, parent, x0, x1, d, z0, z1, col=(80, 80, 86), tex=None, rep=(6, 2)):
        m = Mesh("wall")
        m.quad((x1, d, z0), (x0, d, z0), (x0, d, z1), (x1, d, z1), C(col) if not tex else (1, 1, 1, 1),
               ((0, 0), (rep[0], 0), (rep[0], rep[1]), (0, rep[1])))
        n = parent.attachNewNode(m.node()); n.setTwoSided(True)
        if tex:
            n.setTexture(self.T(tex))

    def build(self):
        """The home club's ground: Kiln Lane by hand; any other club's built from its profile (grounds.py)."""
        import kits, grounds
        home = TEAMS[0] if TEAMS else self.b.m.get("home", "Ashvale Rovers")
        prof, slug = kits.profile(home)
        if slug == "ashvale" or not prof or not prof.get("ground", {}).get("stands"):
            self.build_kiln_lane()
        else:
            grounds.build(self, prof, kits.club_kits(home)[0][0])

    def pitch_surround(self):
        cm = CardMaker("pitch"); cm.setFrame(-HX - 8, HX + 8, -HY - 8, HY + 8)
        p = self.root.attachNewNode(cm.generate()); p.setP(-90); p.setTexture(self.T("pitch.png", False)); no_shadow(p)
        from panda3d.core import TextureStage
        p.setTexture(TextureStage("detail"), self.T("grass_detail.png"))    # (close up: blades of grass, not a flat colour)
        p.setShaderInput("detail_amt", 0.7)
        p.setShaderInput("detail_scale", (2 * (HX + 8)) / 1.4, (2 * (HY + 8)) / 1.4)
        cm2 = CardMaker("apron"); cm2.setFrame(-HX - 40, HX + 40, -HY - 40, HY + 40)
        ap = self.root.attachNewNode(cm2.generate()); ap.setP(-90); ap.setZ(-0.02); ap.setColor(C((96, 98, 100))); no_shadow(ap)
        cm3 = CardMaker("outer"); cm3.setFrame(-400, 400, -400, 400)
        ou = self.root.attachNewNode(cm3.generate()); ou.setP(-90); ou.setZ(-0.5); ou.setColor(C((70, 82, 64))); no_shadow(ou)

    def dugouts(self, n):
        for s, x in ((n, -9), (n, 9)):                                       # dugouts: open at the front,
            dk, grey = C((40, 42, 48)), C((70, 72, 78))                      # a bench of seats inside
            box(s, x - 4, 6.6, 0, x + 4, 6.8, 2.2, dk)                       # (the back)
            box(s, x - 4.1, 4.3, 2.1, x + 4.1, 6.8, 2.3, dk)                 # (the roof)
            for e in (-1, 1):                                                # (perspex ends)
                pe = box(s, x + e * 4 - 0.03, 4.4, 0, x + e * 4 + 0.03, 6.8, 2.1, (0.75, 0.82, 0.88, 0.35))
                pe.setTransparency(TransparencyAttrib.MAlpha); pe.setDepthWrite(False)
            box(s, x - 3.8, 5.7, 0, x + 3.8, 6.5, 0.45, grey)                 # (the seats)
            box(s, x - 3.8, 6.35, 0.45, x + 3.8, 6.5, 0.9, grey)

    def sky_and_hills(self, lamps=()):
        cm = CardMaker("moors"); cm.setFrame(-900, 900, 0, 150)
        mo = self.root.attachNewNode(cm.generate()); mo.setPos(0, 650, -10); mo.setTexture(self.T("moors.png", False))
        mo.setTransparency(TransparencyAttrib.MAlpha); mo.setLightOff(); no_shadow(mo, lit=False)
        cm = CardMaker("sky"); cm.setFrame(-2000, 2000, -100, 700)
        sk = self.root.attachNewNode(cm.generate()); sk.setPos(0, 1200, -50); sk.setTexture(self.T("sky.png", False)); sk.setLightOff(); no_shadow(sk, lit=False)
        if NIGHT:                                           # (a dark sky; the floodlights lit)
            sk.setColorScale(0.05, 0.06, 0.11, 1); mo.setColorScale(0.04, 0.04, 0.06, 1)
            lamp = (2.2, 2.2, 2.1, 1)
            for side, x0, x1, d, z in lamps:
                strip = box(self.side(side), x0, d - 0.3, z - 0.4, x1, d, z, lamp)
                strip.setShaderOff(1); strip.setLightOff(1); no_shadow(strip, lit=False)

    def build_kiln_lane(self):
        b = self.b
        self.pitch_surround()
        # Haworth Stand (far side): two tiers, flat roof on columns
        f = self.side("far")
        self.tier(f, -48, 48, 9, 1.4, 25, 11, "crowd_home.png", (200, 40, 45))
        self.tier(f, -48, 48, 22, 14.5, 36, 25, "crowd_home.png", (240, 240, 240))
        box(f, -48, 20, 11, 48, 23, 14.4, C((200, 40, 45)))                  # the fascia between the tiers
        self.back_wall(f, -48, 48, 36, 0, 29)
        self.roof(f, -49, 49, 16, 38, 29, columns=6)
        # Weavers' End (left): one steep tier, truss roof
        w = self.side("left")
        self.tier(w, -30, 30, 8, 1.4, 30, 20, "crowd_home.png", (200, 40, 45))
        self.back_wall(w, -30, 30, 30, 0, 24)
        self.roof(w, -31, 31, 9, 32, 24, truss=(235, 235, 235))
        bn = box(w, -14, 9.5, 5, 14, 9.6, 8.5, C((200, 40, 45)))                # the LABORE ET FIDE banner
        txt = TextNode("banner"); txt.setText("LABORE ET FIDE"); txt.setTextColor(1, 1, 1, 1); txt.setAlign(TextNode.ACenter)
        tn = w.attachNewNode(txt); tn.setPos(0, 9.4, 5.9); tn.setScale(2.4); tn.setH(180)
        # Canal End (right): small, old, pitched roof
        r = self.side("right")
        self.tier(r, -32, 10, 7, 1.2, 19, 7.5, "crowd_mixed.png", (90, 90, 96))
        self.tier(r, 10, 32, 7, 1.2, 19, 7.5, self.visitors(), (90, 90, 96))      # (away fans: the corner by the
                                                                                   #  Main Stand, as the profile says)
        self.back_wall(r, -32, 32, 19, 0, 10, tex="brick.png", rep=(14, 2))
        self.roof(r, -33, 33, 8, 21, 9.5, col=(80, 70, 66), pitched=2.5, columns=4)
        # Main Stand (near, under the camera): front rows only
        n = self.side("near")
        self.tier(n, -50, 50, 8, 1.2, 20, 8, "crowd_home.png", (200, 40, 45))
        self.dugouts(n)
        # ad boards; a brick wall round the outside (the corners are open, old-style)
        self.ad_boards()
        for x0, y0, x1, y1 in ((-HX - 34, HY + 40, HX + 34, HY + 41), (-HX - 34, -HY - 30, HX + 34, -HY - 29),
                               (-HX - 35, -HY - 30, -HX - 34, HY + 41), (HX + 34, -HY - 30, HX + 35, HY + 41)):
            wn = self.root.attachNewNode(self._brick_block(x0, y0, x1, y1, 5)); wn.setTexture(self.T("brick.png"))
        # floodlight pylon (far-left corner) and the mill chimney (behind the Haworth Stand)
        self.pylon(-HX - 12, HY + 14)
        chim = prism(self.root, 2.6, 58, sides=12, taper=0.65, uv_rep=(4, 12)); chim.setPos(22, HY + 70, 0); chim.setTexture(self.T("brick.png"))
        mill = self.root.attachNewNode(self._brick_block(-10, HY + 52, 45, HY + 66, 24)); mill.setTexture(self.T("brick.png"))
        # terraces of houses behind the Weavers' End
        for i in range(10):
            hb = self.root.attachNewNode(self._brick_block(-HX - 52 - i * 0.1, -40 + i * 8.2, -HX - 44, -40 + i * 8.2 + 7.6, 8))
            hb.setTexture(self.T("brick.png"))
        # moors and sky
        self.sky_and_hills((("far", -45, 45, 16.0, 28.6), ("left", -28, 28, 9.0, 23.4), ("right", -30, 30, 8.0, 9.2)))

    def _brick_block(self, x0, y0, x1, y1, h):
        m = Mesh("brick"); box_into(m, x0, y0, 0, x1, y1, h, (1, 1, 1, 1), uvs=4)
        return m.node()

    def pylon(self, x, y):
        n = self.root.attachNewNode("pylon"); n.setPos(x, y, 0)
        col = C((150, 154, 160))
        H = 42
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            m = Mesh("leg")
            b0, b1 = 2.2, 0.7
            p0 = (sx * b0, sy * b0, 0); p1 = (sx * b1, sy * b1, H)
            box(n, min(p0[0], p1[0]) * 0 + p0[0] - 0.12, p0[1] - 0.12, 0, p0[0] + 0.12, p0[1] + 0.12, 0.3, col)
            leg = box(n, -0.12, -0.12, 0, 0.12, 0.12, math.dist(p0, p1), col)
            leg.setPos(*p0); leg.lookAt(n, Point3(*p1)); leg.setP(leg.getP() - 90)
        for k in range(1, 9):
            z = k * H / 9; w = 2.2 - 1.5 * z / H
            for a, bb in (((-w, -w), (w, -w)), ((w, -w), (w, w)), ((w, w), (-w, w)), ((-w, w), (-w, -w))):
                box(n, min(a[0], bb[0]) - 0.06, min(a[1], bb[1]) - 0.06, z, max(a[0], bb[0]) + 0.06, max(a[1], bb[1]) + 0.06, z + 0.12, col)
        head = box(n, -4, -0.5, H, 4, 0.5, H + 5, C((90, 92, 98)))
        if NIGHT:                                           # (the lamps, lit)
            gl = box(n, -3.8, -0.62, H + 0.2, 3.8, -0.5, H + 4.8, (2.4, 2.4, 2.3, 1))
            gl.setShaderOff(1); gl.setLightOff(1)
        for i in range(4):
            for j in range(3):
                box(n, -3.5 + i * 1.9, -0.75, H + 0.5 + j * 1.5, -2.3 + i * 1.9, -0.5, H + 1.6 + j * 1.5, C((255, 250, 225)))
        n.setH(40)

    def ad_boards(self, brands=None):
        from PIL import Image, ImageDraw, ImageFont
        brands = brands or [("PILLING TEXTILES", (200, 40, 45), (255, 255, 255)), ("ASH VALLEY ALES", (20, 60, 40), (240, 210, 120)),
                  ("THE NATIONAL CHRONICLE", (25, 30, 60), (255, 255, 255)), ("KILN LANE MOTORS", (240, 240, 240), (200, 40, 45)),
                  ("ASHVALE EVENING POST", (30, 30, 30), (255, 200, 40)), ("WEAVERS BUILDING SOC.", (10, 90, 160), (255, 255, 255))]
        try:
            font = ImageFont.truetype(os.path.join(HERE, "fonts", "DejaVuSans-Bold.ttf"), 34)
        except OSError:
            font = ImageFont.load_default()
        im = Image.new("RGB", (512 * len(brands), 64))
        d = ImageDraw.Draw(im)
        for i, (t, bg, fg) in enumerate(brands):
            d.rectangle([i * 512, 0, i * 512 + 511, 63], fill=bg)
            w = d.textlength(t, font=font)
            d.text((i * 512 + 256 - w / 2, 12), t, font=font, fill=fg)
        im.save(T + "ads.png")
        tex = self.T("ads.png")
        for where, half, dist in (("far", HX + 2, 4.0), ("near", HX + 2, 4.0), ("left", 22, 3.5), ("right", 22, 3.5)):
            s = self.side(where)
            m = Mesh("ads")
            reps = half * 2 / (8.0 * len(brands))           # (each board 8m wide)
            m.quad((-half, dist, 0), (half, dist, 0), (half, dist, 0.95), (-half, dist, 0.95), (1, 1, 1, 1),
                   ((0, 0), (reps, 0), (reps, 1), (0, 1)))
            n = s.attachNewNode(m.node()); n.setTexture(tex); n.setLightOff(); n.setShaderOff(1)
            self.b.__dict__.setdefault("ad_nodes", []).append((n, len(brands)))
            box(s, -half, dist + 0.02, 0, half, dist + 0.12, 0.95, C((40, 42, 48)))      # (the back of the boards)

    def corner_flags(self):
        """A flag on a 1.5 m post at each corner (the Laws' minimum height), in the home club's colours."""
        self.b.flags = []
        for sx in (-1, 1):
            for sy in (-1, 1):
                n = self.root.attachNewNode("cflag"); n.setPos(sx * HX, sy * HY, 0)
                box(n, -0.02, -0.02, 0, 0.02, 0.02, 1.55, (0.95, 0.95, 0.95, 1))
                f = n.attachNewNode("cloth"); f.setPos(0, 0, 1.55)
                box(f, 0.0, -0.004, -0.32, 0.42, 0.004, 0.0, (0.86, 0.18, 0.2, 1))
                box(f, 0.21, -0.006, -0.32, 0.42, 0.006, -0.16, (0.97, 0.97, 0.97, 1))
                self.b.flags.append(f)

    def goals(self):
        self.corner_flags()
        for sx in (-1, 1):
            n = self.root.attachNewNode("goal"); n.setPos(sx * HX, 0, 0)
            w = 7.32 / 2; h = 2.44; dpt = 2.0
            white = (0.97, 0.97, 0.97, 1)
            box(n, -0.06, -w - 0.06, 0, 0.06, -w + 0.06, h, white)
            box(n, -0.06, w - 0.06, 0, 0.06, w + 0.06, h, white)
            box(n, -0.06, -w - 0.06, h - 0.06, 0.06, w + 0.06, h + 0.06, white)
            self.b.nets.append(Net(n, sx, w, h, dpt, self.T("net.png")))


class Net:
    """A goal net: a real mesh (~12 cm squares, as nets are made), that bulges where the ball hits it and
    swings back - pegged at the posts, the bar and the ground."""
    CELL = 0.25                                             # (the shape's grid; the mesh pattern is its texture)

    def __init__(self, parent, sx, w, h, dpt, tex):
        from panda3d.core import GeomVertexFormat, GeomVertexData, GeomVertexWriter, GeomTriangles, Geom, GeomNode
        self.sx, self.w, self.h, self.dpt = sx, w, h, dpt
        x = sx * dpt
        # the four panels: (corner, edge u, edge v, which edges are tied: u0 u1 v0 v1) - back, roof, sides
        panels = [((x, -w, 0), (0, 2 * w, 0), (0, 0, h * 0.7), (1, 1, 1, 0)),
                  ((0, -w, h), (0, 2 * w, 0), (x, 0, -h * 0.3), (1, 1, 1, 0)),
                  ((0, -w, 0), (x, 0, 0), (0, 0, h), (1, 0, 1, 0)),
                  ((0, w, 0), (x, 0, 0), (0, 0, h), (1, 0, 1, 0))]
        self.vd = GeomVertexData("net", GeomVertexFormat.getV3n3c4t2(), Geom.UHDynamic)
        vw, nw, cw, tw = (GeomVertexWriter(self.vd, c) for c in ("vertex", "normal", "color", "texcoord"))
        tri = GeomTriangles(Geom.UHStatic)
        self.rest, self.pin = [], []
        base = 0
        for (o, eu, ev, tied) in panels:
            o, eu, ev = Vec3(*o), Vec3(*eu), Vec3(*ev)
            nu, nv = max(2, int(round(eu.length() / self.CELL))), max(2, int(round(ev.length() / self.CELL)))
            nrm = eu.cross(ev); nrm.normalize()
            for j in range(nv + 1):
                for i in range(nu + 1):
                    p = o + eu * (i / nu) + ev * (j / nv)
                    vw.addData3(p); nw.addData3(nrm); cw.addData4(1, 1, 1, 0.9)
                    tw.addData2(eu.length() * i / nu / 0.12, ev.length() * j / nv / 0.12)
                    self.rest.append(Vec3(p))
                    # how free this point is to move: not at all where it's tied (posts, bar, ground)
                    e = [i if tied[0] else 99, nu - i if tied[1] else 99, j if tied[2] else 99, nv - j if tied[3] else 99]
                    self.pin.append(min(1.0, min(e) / 2.0))
            for j in range(nv):
                for i in range(nu):
                    a = base + j * (nu + 1) + i
                    tri.addVertices(a, a + 1, a + nu + 2); tri.addVertices(a, a + nu + 2, a + nu + 1)
            base += (nu + 1) * (nv + 1)
        g = Geom(self.vd); g.addPrimitive(tri)
        gn = GeomNode("net"); gn.addGeom(g)
        self.np = parent.attachNewNode(gn)
        self.np.setTwoSided(True); self.np.setTransparency(TransparencyAttrib.MAlpha); self.np.setTexture(tex)
        self.np.setDepthWrite(False); self.np.setBin("transparent", 10)
        no_shadow(self.np)
        self.hits = []                                      # (where the ball hit it, which way, when)
        self.t = 0.0
        self._moved = False

    def hit(self, local_pt, direction, strength):
        self.hits.append((Vec3(local_pt), Vec3(direction), strength, self.t))

    def step(self, dt):
        from panda3d.core import GeomVertexWriter
        self.t += dt
        self.hits = [hh for hh in self.hits if self.t - hh[3] < 3.0]
        if not self.hits and not self._moved:
            return
        vw = GeomVertexWriter(self.vd, "vertex")
        for p, k in zip(self.rest, self.pin):
            off = Vec3(0, 0, 0)
            for c, d, st, t0 in self.hits:
                age = self.t - t0
                a = st * math.exp(-age / 0.45) * math.cos(2 * math.pi * 1.6 * age)
                r2 = (p - c).lengthSquared()
                off += d * (a * math.exp(-r2 / (2 * 0.75 ** 2)))
            vw.setData3(p + off * k)
        self._moved = bool(self.hits)


class Player:
    SKINS = [(232, 190, 160), (214, 168, 134), (176, 124, 92), (128, 86, 62), (92, 62, 44)]

    def __init__(self, parent, kit, number, skin, hair, keeper=False):
        self.root = parent.attachNewNode("player")
        self.root.setScale(1.15)                                              # (a touch bigger, as TV games do)
        body = self.root.attachNewNode("body")
        shirt, shorts, socks = C(kit["shirt"]), C(kit["shorts"]), C(kit["socks"])
        sk = C(skin)
        box(body, -0.21, -0.12, 0.92, 0.21, 0.12, 1.45, shirt)               # torso
        box(body, -0.2, -0.12, 0.72, 0.2, 0.12, 0.94, shorts)                # shorts
        head = sphere(body, 0.12, sk); head.setPos(0, 0, 1.6)
        hr = sphere(body, 0.125, C(hair), z_from=0.15); hr.setPos(0, -0.01, 1.62)
        box(body, -0.05, -0.05, 1.42, 0.05, 0.05, 1.5, sk)                   # neck
        self.legs, self.arms = [], []
        for sx in (-1, 1):
            hip = body.attachNewNode("hip"); hip.setPos(sx * 0.1, 0, 0.82)
            box(hip, -0.07, -0.07, -0.42, 0.07, 0.07, 0.02, sk if not keeper else shorts)
            box(hip, -0.07, -0.07, -0.8, 0.07, 0.07, -0.42, socks)
            box(hip, -0.07, -0.16, -0.84, 0.07, 0.08, -0.76, C((25, 25, 25)))  # boot
            self.legs.append(hip)
            sh = body.attachNewNode("shoulder"); sh.setPos(sx * 0.27, 0, 1.4)
            box(sh, -0.055, -0.055, -0.2, 0.055, 0.055, 0.03, shirt)
            box(sh, -0.05, -0.05, -0.55, 0.05, 0.05, -0.2, sk if not keeper else shirt)
            self.arms.append(sh)
        tnode = TextNode("num"); tnode.setText(str(number)); tnode.setAlign(TextNode.ACenter)
        tnode.setTextColor(*C(kit.get("number", (255, 255, 255))))
        tn = body.attachNewNode(tnode); tn.setPos(0, 0.125, 1.08); tn.setScale(0.26); tn.setH(180)
        self.body = body
        self.phase = 0.0
        self.h = None

    def update(self, x, y, fx, fy, speed, dt, active=True, **kw):
        if not active:
            self.root.hide(); return
        self.root.show()
        self.root.setPos(x, y, 0)
        h = math.degrees(math.atan2(-fx, fy))
        if self.h is None:
            self.h = h
        dh = (h - self.h + 180) % 360 - 180
        self.h += dh * min(1.0, dt * 10)
        self.root.setH(self.h)
        sp = speed / 10.0                                                     # px/s -> m/s
        self.phase += dt * (2.2 + sp * 0.85) * math.pi
        amp = min(1.0, sp / 6.5)
        sw = math.sin(self.phase) * 38 * amp
        self.legs[0].setP(sw); self.legs[1].setP(-sw)
        self.arms[0].setP(-sw * 0.8); self.arms[1].setP(sw * 0.8)
        self.body.setP(-min(12, sp * 1.6))                                    # lean into the run
        self.body.setZ(abs(math.sin(self.phase)) * 0.05 * amp)

    def act(self, kind, t):
        pass                                                                  # (the block figures don't kick)


class Viewer(ShowBase):
    def __init__(self, match):
        ShowBase.__init__(self)
        self.disableMouse()
        self.setBackgroundColor(*((0.62, 0.66, 0.70, 1) if not NIGHT else (0.03, 0.035, 0.06, 1)))
        self.render.setAntialias(AntialiasAttrib.MMultisample)
        self.m = match
        self.nets = []
        self.crowds = []                                    # (the crowd in each stand, to liven up after a goal)
        st = Stadium(self); st.build(); st.goals()
        self.light_up()
        fog = Fog("haze"); fog.setColor(*((0.62, 0.66, 0.7) if not NIGHT else (0.04, 0.045, 0.07)))
        fog.setExpDensity(0.0012 if not RAIN else 0.0035); self.render.setFog(fog)
        if RAIN:
            self.setBackgroundColor(0.55, 0.58, 0.62, 1)
        # kits (Ashvale home v Northwick home)
        import kits                                                       # (the clubs' own kits, from their profiles)
        self.home_name = TEAMS[0] if TEAMS else match.get("home", "Ashvale Rovers")
        self.away_name = TEAMS[1] if TEAMS else match.get("away", "Northwick FC")
        home, away, gk0, gk1, self.home_info, self.away_info = kits.choose(self.home_name, self.away_name)
        self.kits = (home, away)
        import random
        rnd = random.Random(11)
        self.players = []
        for i, (name, role, num) in enumerate(match["names"]):
            team = 0 if i < 11 else 1
            keeper = role in ("GK",)
            kit = (gk0 if team == 0 else gk1) if keeper else (home if team == 0 else away)
            skin = rnd.choice(Player.SKINS)
            hair = rnd.choice([(40, 28, 20), (25, 20, 18), (120, 80, 40), (200, 170, 110), (15, 12, 10)])
            if ANIM:
                info = self.home_info if team == 0 else self.away_info
                self.players.append(AnimPlayer(self.render, kit, num or (i % 11) + 1, skin, hair, keeper, name=name,
                                               crest=info.get("crest"), role=role))
            else:
                self.players.append(Player(self.render, kit, (i % 11) + 1, skin, hair, keeper))
        self.officials = []
        if ANIM:
            self.officials = make_officials(self, (home, away, gk0, gk1))
        cm = CardMaker("shadow"); cm.setFrame(-0.45, 0.45, -0.3, 0.3)          # soft blob shadows
        from PIL import Image, ImageFilter, ImageDraw
        sh = Image.new("RGBA", (64, 64), (0, 0, 0, 0)); ImageDraw.Draw(sh).ellipse([8, 14, 56, 50], fill=(0, 0, 0, 120))
        sh.filter(ImageFilter.GaussianBlur(5)).save(T + "shadow.png")
        stex = self.loader.loadTexture(T + "shadow.png")
        self.shadows = []
        for p in self.players + [o["p"] for o in self.officials]:
            n = p.root.attachNewNode(cm.generate()); n.setP(-90); n.setPos(0.25, 0.25, 0.02); n.setTexture(stex)
            n.setTransparency(TransparencyAttrib.MAlpha); n.setLightOff(); n.setDepthWrite(False); n.setBin("fixed", 0)
            no_shadow(n, lit=False)
            if not OVERCAST:                                # (sunshine: the sun casts the real shadow - this is just
                n.setPos(0, 0, 0.02); n.setScale(0.75, 1, 0.9); n.setAlphaScale(0.55)    # the darkening under his feet)
            if NIGHT:                                       # (floodlights: four faint shadows, one to each corner)
                fl = self.render.attachNewNode("floodshadows")
                for a in (45, 135, 225, 315):
                    s4 = fl.attachNewNode(cm.generate()); s4.setP(-90); s4.setTexture(stex)
                    s4.setH(a); s4.setScale(0.55, 1, 2.2); s4.setPos(fl, math.cos(math.radians(a + 90)) * -0.6,
                                                                     math.sin(math.radians(a + 90)) * -0.6, 0.015)
                    s4.setTransparency(TransparencyAttrib.MAlpha); s4.setAlphaScale(0.35)
                fl.setLightOff(1); fl.setDepthWrite(False); fl.setBin("fixed", 0); no_shadow(fl, lit=False)
                p.flood = fl
        self.ball = football(self.render, BALL_R)
        cm = CardMaker("bshadow"); cm.setFrame(-0.22, 0.22, -0.22, 0.22)          # (a soft round shadow)
        self.bsh = self.render.attachNewNode(cm.generate()); self.bsh.setP(-90); self.bsh.setTexture(stex)
        self.bsh.setTransparency(TransparencyAttrib.MAlpha); self.bsh.setLightOff(); self.bsh.setDepthWrite(False)
        no_shadow(self.bsh, lit=False)
        if not OVERCAST:
            self.bsh.hide()
        self.bsh.setBin("fixed", 0)
        # camera: the TV gantry in the Main Stand
        self.camLens.setFov(36)
        self.camLens.setNearFar(1, 3000)
        self.cx, self.cy = 0.0, 0.0
        gks = tuple(i for i, nm in enumerate(match.get("names", [])) if len(nm) > 1 and nm[1] == "GK") or (0, 11)
        self.events = find_events(match["frames"], gks)
        self.dives = {}
        self.ball_off = Vec3(0, 0, 0)
        self.ball_mode = None
        self.last_ball = None
        self.dribble = {}
        self.hud(match)
        if RAIN:
            self.make_rain()

    def light_up(self):
        """The light.  Default: a bright autumn afternoon - a low sun from behind the Main Stand (the camera's side),
        real shadows (each player's, the ball's, the stands' and the goal frames') stretching away up the pitch.
        --overcast: the old grey Lancashire afternoon, no sun shadows."""
        if NIGHT:                                           # (floodlights: from high up, white, a darker fill)
            global SUN_AZ, SUN_EL
            SUN_AZ, SUN_EL = 200.0, 60.0
        if OVERCAST:
            al = AmbientLight("amb"); al.setColor(Vec4(0.52, 0.53, 0.56, 1) if not RAIN else Vec4(0.46, 0.48, 0.52, 1))
            self.render.setLight(self.render.attachNewNode(al))
            dl = DirectionalLight("sun"); dl.setColor(Vec4(0.62, 0.6, 0.56, 1) if not RAIN else Vec4(0.42, 0.42, 0.42, 1))
            sun = self.render.attachNewNode(dl); sun.setPos(-40, -60, 120); sun.lookAt(0, 0, 0)
            self.render.setLight(sun)
            self._shader_inputs()
            return
        al = AmbientLight("amb"); al.setColor(Vec4(0.50, 0.53, 0.60, 1) if not NIGHT else Vec4(0.30, 0.32, 0.38, 1))
        self.render.setLight(self.render.attachNewNode(al))
        dl = DirectionalLight("sun"); dl.setColor(Vec4(1.25, 1.12, 0.92, 1) if not NIGHT else Vec4(1.0, 1.0, 1.05, 1))
        dl.setShadowCaster(True, SHADOW_MAP, SHADOW_MAP)
        lens = dl.getLens(); lens.setFilmSize(250, 170); lens.setNearFar(10, 600)
        sun = self.render.attachNewNode(dl)
        az, el = math.radians(SUN_AZ), math.radians(SUN_EL)
        sun.setPos(-math.sin(az) * math.cos(el) * 300, -math.cos(az) * math.cos(el) * 300, math.sin(el) * 300)
        sun.lookAt(0, 0, 0)
        self.render.setLight(sun)
        self.sun = sun
        dl.setCameraMask(NO_SHADOW_BIT)                    # (the sun's shadow camera: see no_shadow())
        self._shader_inputs()

    def _shader_inputs(self):
        sh = Shader.load(Shader.SL_GLSL, os.path.join(HERE, "shaders", "lit.vert"), os.path.join(HERE, "shaders", "lit.frag"))
        self.render.setShader(sh)
        if ANIM:
            from players3d import shader_defaults
            shader_defaults(self.render)
            if RAIN:
                self.render.setShaderInput("mud_amt", 1.0)
        self.render.setShaderInput("shadow_bias", 0.0004)
        self.render.setShaderInput("shadow_texel", 1.0 / SHADOW_MAP)
        self.render.setShaderInput("detail_amt", 0.0)
        self.render.setShaderInput("crowd_amt", 0.0)
        self.render.setShaderInput("night_on", 1.0 if NIGHT else 0.0)
        self.render.setShaderInput("detail_scale", 1.0, 1.0)
        if not self.render.hasFog():
            f = Fog("none"); f.setExpDensity(0.0); self.render.setFog(f)

    def hud(self, match):
        from direct.gui.DirectGui import DirectFrame
        DirectFrame(frameColor=(0.06, 0.07, 0.09, 0.88), frameSize=(0, 0.92, -0.11, 0), pos=(-1.72, 0, 0.94))
        for info, kit, x in ((self.home_info, self.kits[0], -1.66), (self.away_info, self.kits[1], -1.04)):
            if info.get("crest"):
                img = OnscreenImage(image=self.loader.loadTexture(Filename.fromOsSpecific(info["crest"])),
                                    pos=(x, 0, 0.885), scale=(0.042, 1, 0.044))
                img.setTransparency(TransparencyAttrib.MAlpha)
            else:                                                       # (no crest yet: a patch of the shirt colour)
                DirectFrame(frameColor=C(kit["shirt"]), frameSize=(-0.03, 0.03, -0.03, 0.03), pos=(x, 0, 0.885))
        self.labels = (self.home_info["short"][:3].upper(), self.away_info["short"][:3].upper())
        self.score_t = OnscreenText(text="", pos=(-1.35, 0.87), scale=0.055, fg=(1, 1, 1, 1), align=TextNode.ACenter,
                                    mayChange=True)
        self.clock_t = OnscreenText(text="", pos=(-0.88, 0.87), scale=0.05, fg=(0.85, 0.9, 0.85, 1), align=TextNode.ACenter,
                                    mayChange=True)
        DirectFrame(frameColor=(0.06, 0.07, 0.09, 0.0), frameSize=(0, 0.1, -0.1, 0), pos=(-1.7, 0, 0.94))

    def make_rain(self):
        """Rain over the picture: two layers of streaks drifting down at different speeds (near and far)."""
        from panda3d.core import TextureStage
        tex = self.loader.loadTexture(T + "rain.png")
        tex.setWrapU(Texture.WM_repeat); tex.setWrapV(Texture.WM_repeat)
        self.rain = []
        for scale, alpha, speed in ((1.0, 0.55, 1.9), (2.2, 0.35, 1.1)):
            cm = CardMaker("rain"); cm.setFrame(-1.9, 1.9, -1, 1); cm.setUvRange((0, 0), (3.8 / scale, 2 / scale))
            n = self.render2d.attachNewNode(cm.generate()) if False else self.aspect2d.attachNewNode(cm.generate())
            n.setTexture(tex); n.setTransparency(TransparencyAttrib.MAlpha); n.setAlphaScale(alpha)
            n.setBin("fixed", 5); n.setDepthTest(False); n.setDepthWrite(False)
            self.rain.append((n, speed))
        self.rain_t = 0.0

    def _goal_caption(self, fr):
        """After a goal, the TV caption along the bottom: GOAL, the minute, the scorer and his club."""
        cel = fr.get("c")
        card = fr.get("card")
        if not hasattr(self, "cap"):
            from direct.gui.DirectGui import DirectFrame
            self.cap = DirectFrame(frameColor=(0.06, 0.07, 0.09, 0.9), frameSize=(-0.75, 0.75, -0.075, 0.075),
                                   pos=(0, 0, -0.78))
            self.cap_bar = DirectFrame(parent=self.cap, frameColor=(1, 1, 1, 1), frameSize=(-0.75, -0.6, -0.075, 0.075))
            self.cap_t = OnscreenText(parent=self.cap, text="", pos=(-0.675, -0.022), scale=0.055, fg=(0.06, 0.07, 0.09, 1),
                                      mayChange=True)
            self.cap_n = OnscreenText(parent=self.cap, text="", pos=(-0.56, -0.02), scale=0.05, fg=(1, 1, 1, 1),
                                      align=TextNode.ALeft, mayChange=True)
            self.cap.hide()
        k = fr.get("k", 0)
        if card and 0 <= card[1] < len(self.m.get("names", [])):
            nm = self.m["names"][card[1]][0]
            short = (nm.split()[0][0] + ". " + nm.split()[-1]) if " " in nm else nm
            team = 0 if card[1] < 11 else 1
            red = card[0] in ("red", "second_yellow")
            self.cap_bar["frameColor"] = (0.85, 0.1, 0.1, 1) if red else (0.98, 0.85, 0.1, 1)
            self.cap_t.setText("")
            word = "RED CARD" if red else "BOOKED"
            self.cap_n.setText(f"{word}   {short}   {self.home_name if team == 0 else self.away_name}")
            self.cap.show()
            return
        if cel and k - self._restart_id(k) < 30 * 9:                        # (the first 9 seconds of it)
            team, scorer = cel
            names = self.m.get("names", [])
            nm = names[scorer][0] if scorer < len(names) else ""
            short = (nm.split()[0][0] + ". " + nm.split()[-1]) if nm and " " in nm else nm
            club = self.home_name if team == 0 else self.away_name
            mins = int(fr["t"] / 600.0 * 45) + 1
            kit = self.kits[team]
            bar = kit["shirt"] if sum(kit["shirt"]) / 765 > 0.2 else kit.get("trim", (240, 240, 240))
            self.cap_bar["frameColor"] = C(bar)
            self.cap_t.setText("GOAL")
            lum = sum(bar) / 765
            self.cap_t["fg"] = (0.06, 0.07, 0.09, 1) if lum > 0.5 else (1, 1, 1, 1)
            self.cap_n.setText(f"{short}  {mins}'      {club}")
            self.cap.show()
        else:
            self.cap.hide()

    def show(self, fr, dt):
        k = fr.get("k", 0)
        rbx, rby = to_world(fr["b"][0], fr["b"][1])
        prev = getattr(self, "_prev_pos", {})
        cel = fr.get("c")                                                   # (a goal celebration: who scored)
        amts = getattr(self, "_crowd_amts", {})
        for n, (cn, kind) in enumerate(self.crowds):                        # (their fans go up; the others sit)
            fans = {"crowd_home.png": 0, "crowd_hosts.png": 0, "crowd_away.png": 1, "crowd_visitors.png": 1}.get(kind, -1)
            want = 1.0 if not cel else (7.0 if fans == cel[0] else 0.4 if fans >= 0 else 3.0)
            cur = amts.get(n, 1.0)
            cur += (want - cur) * min(1.0, dt * 2.0)
            amts[n] = cur
            cn.setShaderInput("crowd_amt", cur)
        self._crowd_amts = amts
        for i, (p, (x, y, fx, fy, sp, state, act, *_)) in enumerate(zip(self.players, fr["p"])):
            if cel:
                mine = (i < 11) == (cel[0] == 0)
                p.mood = "scorer" if i == cel[1] else ("joy" if mine else "sad") if not getattr(p, "keeper", False) else None
            else:
                p.mood = None
            wx, wy = to_world(x, y)
            px, py = prev.get(i, (wx, wy))
            vel = ((wx - px) / max(dt, 1e-3), (wy - py) / max(dt, 1e-3))
            prev[i] = (wx, wy)
            p.calling = self._calling(i, fr, wx, wy, sp, k)
            kind, t = self.events.action(i, k)
            if cel and i == cel[1]:
                kind, t = self._scorer_slide(i, sp, k, kind, t)
            card = fr.get("card")
            if card and card[1] == i and kind is None and sp < 25:
                kind, t = "protest", 0.5
            if kind == "despair" and sp > 30:                               # (not while he's still running hard)
                kind = None
            if kind == "throwin":                                           # (facing the way he throws it)
                fx, fy = self._throw_dir(i, k, t, fx, fy)
            p.update(wx, wy, fx, -fy, sp, dt, act, vel=vel, ball=(rbx, rby))
            dv = fr["p"][i][7] if len(fr["p"][i]) > 7 else ""
            if dv in ("diving", "recover") and getattr(p, "keeper", False):    # (a keeper's dive)
                self._keeper_dive(i, p, dv, k)
                continue
            if kind is None and fr["o"] == i:
                kind, t = self._dribble_touch(i, p, dt)
            r = fr.get("r")
            if kind is None and r and r[0] == "free_kick" and 0 <= r[1] < len(fr["p"]) and sp < 15 \
                    and (i < 11) != (r[1] < 11) and not getattr(p, "keeper", False):
                if 8.0 < math.hypot(wx - rbx, wy - rby) < 11.5:                 # (in the wall)
                    kind, t = "wall", 0.5
            if kind is None and getattr(p, "keeper", False) and sp < 25:          # (a keeper, set for a shot)
                gx = -HX if wx < 0 else HX
                if math.hypot(rbx - gx, rby) < 30 and fr["o"] not in (range(0, 11) if i < 11 else range(11, 22)):
                    kind, t = "ready", 0.0
            p.act(kind, t, self._left_foot(i, p, kind, t, k))
        self._prev_pos = prev
        self._officiate(fr, dt, rbx, rby)
        if NIGHT:
            for p in self.players + [o["p"] for o in self.officials]:
                if hasattr(p, "flood"):
                    p.flood.setPos(p.root.getX(), p.root.getY(), 0)
                    if p.root.isHidden():
                        p.flood.hide()
                    else:
                        p.flood.show()
        for net in self.nets:
            net.step(dt)
        if getattr(self, "led_ads", False):                                  # (LED boards: a new advert every
            from panda3d.core import TextureStage                            #  12 seconds, sliding along)
            tt = getattr(self, "_flag_t", 0.0)
            step, frac = divmod(tt, 12.0)
            slide = step + min(1.0, frac / 0.6)
            for n, nb in getattr(self, "ad_nodes", []):
                n.setTexOffset(TextureStage.getDefault(), slide / nb, 0)
        self._flag_t = getattr(self, "_flag_t", 0.0) + dt                     # (the corner flags in the breeze)
        for j, f in enumerate(getattr(self, "flags", [])):
            f.setH(200 + 18 * math.sin(self._flag_t * 2.3 + j) + 8 * math.sin(self._flag_t * 5.1 + j * 2))
        bx, by, bz = self._ball(fr, dt)
        self._spin_ball(bx, by, bz, dt)
        self.ball.setPos(bx, by, bz)
        self.bsh.setPos(bx, by, 0.02)
        # the camera pans with the ball (smoothly), a little zoom when it's near the far side
        k = min(1.0, dt * 2.2)
        self.cx += (max(-34, min(34, bx)) - self.cx) * k
        self.cy += (by - self.cy) * k
        if "--top" in sys.argv:                                             # (a check: the whole ground from above)
            self.cam.setPos(0, -330, 230); self.cam.lookAt(0, 40, 0)
        elif FOLLOW is not None:                                            # (a close camera on one player)
            if FOLLOW < len(fr["p"]):
                fx_, fy_ = to_world(fr["p"][FOLLOW][0], fr["p"][FOLLOW][1])
            else:                                                           # (22 on: the referee, assistants, managers)
                fx_, fy_ = self.officials[FOLLOW - len(fr["p"])]["pos"]
            sx = 1 if fx_ < 0 else -1                                       # (from out on the pitch, looking at him)
            if "--side" in sys.argv:                                        # (or side-on to him, to check his gait)
                hd = math.radians((self.players + [o["p"] for o in self.officials])[FOLLOW].h or 0.0)
                self._sv = getattr(self, "_sv", (math.cos(hd), math.sin(hd)))
                k2 = min(1.0, dt * 1.5)
                self._sv = (self._sv[0] + (math.cos(hd) - self._sv[0]) * k2, self._sv[1] + (math.sin(hd) - self._sv[1]) * k2)
                d_ = 11 if "--near" not in sys.argv else 6.5
                self.cam.setPos(fx_ + self._sv[0] * d_, fy_ + self._sv[1] * d_, 2.0 if d_ > 7 else 1.2)
            else:
                self.cam.setPos(fx_ + sx * 9, fy_ - 7 if fy_ > -HY + 1 else fy_ + 9, 3.2)
            self.cam.lookAt(fx_, fy_, 0.8)
        elif CLOSE or getattr(self, "cam_mode", 0) == 1:                    # (a close camera, for checking)
            self.cam.setPos(bx - 6, by - 14, 4.5)
            self.cam.lookAt(bx, by, 0.9)
        else:
            self.cam.setPos(self.cx * 0.8, -HY - 62, 33)
            self.cam.lookAt(self.cx, self.cy * 0.35 + 9, 0)
        s = fr["s"]
        self.score_t.setText(f"{self.labels[0]}  {s[0]} - {s[1]}  {self.labels[1]}")
        self._goal_caption(fr)
        if RAIN:
            self.rain_t += dt
            from panda3d.core import TextureStage
            for n, speed in self.rain:
                n.setTexOffset(TextureStage.getDefault(), 0.06 * self.rain_t * speed, self.rain_t * speed)
        mins = int(fr["t"] / 600.0 * 45)
        self.clock_t.setText(f"{mins:02d}:{int((fr['t'] / 600.0 * 45 * 60) % 60):02d}")


# --- The ball at the players' feet, and what each player is doing with it ------------------------------------
DRIBBLE_TOUCH = 0.7          # seconds between touches when running with the ball
BALL_R = 0.15                # (a real ball is 0.11 m across the middle: drawn a touch big, as TV games do)


def _viewer_goal_ball(self, fr, dt):
    """A goal: the match engine puts the ball straight back on the centre spot, so here it carries on into the
    net - which bulges - drops, and lies there while they celebrate.  None when there's no goal going on."""
    F = self.m["frames"]
    k = fr.get("k", 0)
    g = getattr(self, "gball", None)
    if g is None:
        if k >= 3 and fr["s"] != F[k - 1]["s"] and self.last_ball is not None and abs(self.last_ball[0]) > HX - 4:
            a, b = F[k - 2]["b"], F[k - 1]["b"]
            (ax, ay), (bx, by) = to_world(a[0], a[1]), to_world(b[0], b[1])
            vel = Vec3((bx - ax) * 30, (by - ay) * 30, (b[2] - a[2]) / 10.0 * 30)
            if vel.length() < 4:
                vel = Vec3(8 * (1 if self.last_ball[0] > 0 else -1), 0, 0)
            g = self.gball = {"pos": Vec3(*self.last_ball), "vel": vel, "start": k,
                              "sx": 1 if self.last_ball[0] > 0 else -1}
        else:
            return None
    if "c" not in fr and k - g["start"] > 45:                               # (the celebration's over)
        self.gball = None
        return None
    pos, vel, sx = g["pos"], g["vel"], g["sx"]
    net = next((n for n in self.nets if n.sx == sx), None)
    w, h, dpt = 7.32 / 2, 2.44, 2.0
    for _ in range(3):                                                      # (three small steps a frame)
        st = dt / 3
        if pos.z > BALL_R + 1e-3 or vel.z > 0:
            vel.z -= 9.81 * st
        pos += vel * st
        if pos.z < BALL_R:
            pos.z = BALL_R; vel.z = -vel.z * 0.35
            vel.x *= 0.92; vel.y *= 0.92
        lx = (pos.x - sx * HX) * sx                                         # (how far behind the goal line)
        if lx > 0 and net is not None:
            roof = h - 0.3 * h * min(1.0, lx / dpt)
            speed = vel.length()
            if lx > dpt - BALL_R and pos.z < 0.7 * h:                       # (the back of the net)
                if vel.x * sx > 0:
                    net.hit((sx * dpt, pos.y, pos.z), Vec3(sx, 0, 0), min(0.7, 0.045 * speed))
                    vel.x = -vel.x * 0.12; vel.y *= 0.4
                pos.x = sx * (HX + dpt - BALL_R)
            if abs(pos.y) > w - BALL_R:                                      # (a side netting)
                side = 1 if pos.y > 0 else -1
                if vel.y * side > 0:
                    net.hit((sx * lx, side * w, pos.z), Vec3(0, side, 0), min(0.5, 0.04 * speed))
                    vel.y = -vel.y * 0.15
                pos.y = side * (w - BALL_R)
            if pos.z > roof - BALL_R:                                       # (the roof of the net)
                if vel.z > 0:
                    net.hit((sx * lx, pos.y, roof), Vec3(0, 0, 1), min(0.5, 0.04 * speed))
                    vel.z = -vel.z * 0.2
                pos.z = roof - BALL_R
    g["pos"], g["vel"] = pos, vel
    return (pos.x, pos.y, pos.z)


def _viewer_ball(self, fr, dt):
    """Where to draw the ball.  Loose: where the engine has it.  At a player's feet: just in front of him,
    pushed ahead with each touch when he's running with it.  Switching between the two eases over ~0.1 s."""
    import math as _m
    gb = self._goal_ball(fr, dt)
    if gb is not None:
        self.ball_mode = "goal"; self.ball_off = Vec3(0, 0, 0); self.last_ball = gb
        return gb
    o = fr["o"]
    bx, by = to_world(fr["b"][0], fr["b"][1])
    bz = fr["b"][2] / 10.0 + BALL_R
    mode = o if (o >= 0 and fr["p"][o][6]) else None
    if mode is not None:
        p = self.players[o]
        hd = _m.radians(p.h or 0.0)
        fx, fy = -_m.sin(hd), _m.cos(hd)
        ph = self.dribble.get(o, 0.0)
        push = min(1.0, max(0.0, (p.sp - 1.0) / 4.0))                    # (standing: at his feet; running: pushed on)
        dist = 0.42 + 0.65 * push * _m.sin(_m.pi * ph)
        kind, t = self.events.action(o, fr.get("k", 0))
        if kind in ("kick", "shot") and t < 0:                              # (setting it up for the kick)
            dist = 0.38 + (dist - 0.38) * min(1.0, -t / 0.3)
        px, py = p.root.getX(), p.root.getY()
        bx, by, bz = px + fx * dist + fy * 0.09, py + fy * dist - fx * 0.09, BALL_R
        if getattr(p, "keeper", False):                                     # (a keeper: in his hands)
            bx, by, bz = p.hands()
    r = fr.get("r")
    if r and r[0] == "throw_in" and r[1] >= 0:                              # (a throw-in: in his hands)
        p = self.players[r[1]]
        kind, t = self.events.action(r[1], fr.get("k", 0))
        px, py = p.root.getX(), p.root.getY()
        if kind == "throwin" and t >= -1.5 and _m.hypot(px - bx, py - by) < 2.5:
            bx, by, bz = p.hands()                                          # (between his hands, wherever they are)
            mode = ("throw", r[1])
    if mode != self.ball_mode:
        if self.last_ball is not None:
            self.ball_off = Vec3(*self.last_ball) - Vec3(bx, by, bz)        # (ease from where it was drawn)
        # (out of someone's hands - a throw-in, a keeper's throw - it comes down over a longer flight)
        held = isinstance(self.ball_mode, tuple) or (self.ball_mode is not None and
                                                     getattr(self.players[self.ball_mode], "keeper", False))
        self.ball_tau = 0.28 if held else 0.09
        self.ball_mode = mode
    self.ball_off *= _m.exp(-dt / getattr(self, "ball_tau", 0.09))
    out = (bx + self.ball_off.x, by + self.ball_off.y, max(BALL_R, bz + self.ball_off.z))
    self.last_ball = out
    return out


def _viewer_dribble(self, i, p, dt):
    """Running with the ball: a touch every DRIBBLE_TOUCH seconds - the pose either side of it."""
    if p.sp < 1.2:
        return None, 0.0
    cyc = getattr(p, "cyc", 0.0)
    if cyc > 0.3 and getattr(p, "phase", None) is not None:
        # in step with his stride: the right foot reaching the ball as it comes through (phase 0), every
        # second stride at speed (a touch every ~4 steps, as players push it on), every stride when slower
        ph = p.phase
        t = (ph - (1.0 if ph > 0.5 else 0.0)) / cyc
        n = 2 if p.sp > 4.5 else 1
        k = int(getattr(p, "strides", 0))
        if n == 2 and k % 2 and t < 0:                  # (the in-between stride: no touch)
            return None, 0.0
        if n == 2 and not k % 2 and t >= 0:
            return None, 0.0
        return "touch", t
    ph = (self.dribble.get(i, 0.0) + dt / DRIBBLE_TOUCH) % 1.0
    self.dribble[i] = ph
    t = ph * DRIBBLE_TOUCH
    if t > DRIBBLE_TOUCH - 0.16:
        t -= DRIBBLE_TOUCH
    return "touch", t


def _viewer_keeper_dive(self, i, p, stage, k):
    """Which way he's diving (from where the engine moves him next), and how far into it he is."""
    import math as _m
    F = self.m["frames"]
    st = self.dives.setdefault(i, {})
    if st.get("stage") != stage:
        st.update(stage=stage, start=k)
        if stage == "diving" or "h" not in st:
            st["h"] = p.h or 0.0                                            # (he keeps facing the shot through it)
            a, b = F[k]["p"][i], F[min(len(F) - 1, k + 8)]["p"][i]
            mx, my = to_world(b[0], b[1])
            ox, oy = to_world(a[0], a[1])
            hd = _m.radians(st["h"])
            right = (_m.cos(hd), _m.sin(hd))                               # (his right, facing +Y at h = 0)
            st["side"] = 1 if (mx - ox) * right[0] + (my - oy) * right[1] >= 0 else -1
    p.dive(stage, (k - st["start"]) / 30.0, st.get("side", 1))
    p.h = st["h"]
    p.root.setPos(p.root.getX(), p.root.getY(), p.lift)
    p.root.setHpr(p.h, 0, p.roll * p.roll_side)


def _viewer_left_foot(self, i, p, kind, t, k):
    """Which foot he plays it with: the one on the ball's side - or, if it's straight in front of him, his
    stronger foot (about 1 in 5 players are left-footed)."""
    if kind not in ("kick", "shot", "touch", "tackle"):
        return False
    F = self.m["frames"]
    fe = F[max(0, min(len(F) - 1, int(round(k - t * 30))))]
    x, y, fx, fy = fe["p"][i][:4]
    px, py = to_world(x, y)
    bx, by = to_world(fe["b"][0], fe["b"][1])
    fwx, fwy = fx, -fy
    side = (bx - px) * fwy - (by - py) * fwx                        # (+ = the ball is on his right)
    if kind == "tackle":
        side = -side                                                # (a tackle: the leg stretched across)
    lefty = (i * 7 + 3) % 5 == 0
    return side < -0.12 or (lefty and side < 0.12)


def _viewer_throw_dir(self, i, k, t, fx, fy):
    """A throw-in: he faces the way the ball goes (engine directions)."""
    F = self.m["frames"]
    ke = int(round(k - t * 30))
    a, b = F[max(0, min(len(F) - 1, ke))]["b"], F[max(0, min(len(F) - 1, ke + 6))]["b"]
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    return (dx / d, dy / d) if d > 1e-3 else (fx, fy)


def football(parent, r):
    """The ball: white with the classic twelve dark pentagons (so you can see it roll)."""
    from geom import Mesh
    m = Mesh("ball")
    t = (1 + 5 ** 0.5) / 2                                                  # (an icosahedron's corners = the
    ico = [(0, 1, t), (0, -1, t), (0, 1, -t), (0, -1, -t), (1, t, 0), (-1, t, 0), (1, -t, 0), (-1, -t, 0),
           (t, 0, 1), (-t, 0, 1), (t, 0, -1), (-t, 0, -1)]                  #  pentagons' middles)
    ico = [Vec3(*v).normalized() for v in ico]
    seg, ring = 36, 24

    def P(i, j):
        th = math.pi * j / ring; ph = 2 * math.pi * i / seg
        return (math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th))
    for j in range(ring):
        for i in range(seg):
            a, b, c, d = P(i, j), P(i + 1, j), P(i + 1, j + 1), P(i, j + 1)
            mid = Vec3(*[(a[k] + b[k] + c[k] + d[k]) / 4 for k in range(3)]).normalized()
            dark = max(mid.dot(v) for v in ico) > 0.945                    # (~19 degrees round each)
            col = (0.12, 0.12, 0.14, 1) if dark else (0.97, 0.97, 0.97, 1)
            m.quad(*[(x * r, y * r, z * r) for (x, y, z) in (d, c, b, a)], col)
    return parent.attachNewNode(m.node())


def _viewer_spin_ball(self, bx, by, bz, dt):
    """Roll the ball the distance it's moved (on the ground); in the air it keeps the spin it had."""
    from panda3d.core import LQuaternionf
    last = getattr(self, "_ball_last", None)
    self._ball_last = (bx, by)
    if last is None:
        return
    dx, dy = bx - last[0], by - last[1]
    d = math.hypot(dx, dy)
    if d > 3.0:                                                             # (a jump: a new scene)
        return
    if bz < BALL_R + 0.05 and d > 1e-4:
        axis, ang = Vec3(-dy / d, dx / d, 0), math.degrees(d / BALL_R)
        self._ball_spin = (axis, ang / max(dt, 1e-3))
    else:
        axis, rate = getattr(self, "_ball_spin", (Vec3(1, 0, 0), 0.0))
        self._ball_spin = (axis, rate * math.exp(-dt / 2.0))
        ang = rate * dt
    q = LQuaternionf(); q.setFromAxisAngle(ang, axis)
    self.ball.setQuat(self.ball.getQuat() * q)


# --- the referee and his assistants ------------------------------------------------------------------------
# Not in the match engine: placed here the way officials work a real match (IFAB Laws of the Game, "Practical
# Guidelines for Match Officials"): the referee runs the diagonal, keeping play between himself and an
# assistant, 10-20 m from the ball; each assistant runs one half of a touchline, level with the second-last
# defender (or the ball, if it's nearer the goal line).  Referees run ~10-12 km a game and sprint like players.
REF_COLOURS = [(25, 25, 28), (235, 215, 40), (60, 190, 90), (220, 60, 140), (40, 90, 200), (220, 60, 40)]


def make_officials(v, kits_in_use):
    import kits as _k
    taken = [k["shirt"] for k in kits_in_use] + [k["shorts"] for k in kits_in_use[:2]]
    c = max(REF_COLOURS, key=lambda g: min(_k._dist(g, t) for t in taken))
    dark = sum(c) < 200
    kit = {"shirt": c, "trim": (240, 240, 240) if dark else (25, 25, 28), "shorts": (25, 25, 28),
           "socks": (25, 25, 28), "socktop": c, "pattern": "sleeves" if not dark else None,
           "number": (240, 240, 240)}
    if not dark:
        kit["trim"] = (25, 25, 28)
    out = []
    for role, x, y in (("ref", -8.0, -6.0), ("ar_near", 20.0, -HY - 1.2), ("ar_far", -20.0, HY + 1.2)):
        p = AnimPlayer(v.render, kit, "", (205, 160, 125) if role != "ar_far" else (150, 105, 75), (40, 30, 25))
        if role != "ref":                                                   # (an assistant's flag)
            hand = p.a.exposeJoint(None, "modelRoot", "hand.r")
            flag = box(hand, -0.01, -0.01, 0.0, 0.01, 0.01, 0.55, (0.15, 0.15, 0.15, 1))
            cloth = box(hand, -0.005, 0.0, 0.32, 0.005, 0.30, 0.55, (0.95, 0.85, 0.1, 1))
            for n in (flag, cloth):
                n.setShaderInput("kit_on", 0.0); n.setTextureOff(3)
        out.append({"p": p, "role": role, "pos": [x, y], "vel": [0.0, 0.0]})
    # The two managers in their technical areas, in front of the dugouts (the near touchline, 9 m either side
    # of halfway): the home one in a dark coat, the visitors' in a club tracksuit top.
    for team, x, kit in ((0, -9.0, kits_in_use[0]), (1, 9.0, kits_in_use[1])):
        suit = {"shirt": (32, 34, 44), "trim": (32, 34, 44), "shorts": (28, 28, 34), "socks": (28, 28, 34),
                "socktop": (28, 28, 34), "pattern": None, "number": (240, 240, 240), "trousers": True,
                "long_sleeves": True}
        if team == 1:
            suit.update(shirt=kit["shirt"], trim=kit.get("trim", kit["shirt"]), pattern="sleeves" if False else None)
        p = AnimPlayer(v.render, suit, "", (214, 168, 134) if team == 0 else (176, 124, 92), (60, 55, 50),
                       height=1.78)
        out.append({"p": p, "role": "manager", "team": team, "home_x": x, "pos": [x, -HY - 2.2], "vel": [0.0, 0.0],
                    "next_point": 4.0 + 5 * team, "t": 0.0})
    # Stewards in hi-vis round the edge, facing the crowd, and ball boys / girls by the corner flags and behind
    # the goals (both are at every English league ground).
    vis = {"shirt": (226, 236, 48), "trim": (200, 200, 200), "shorts": (30, 30, 36), "socks": (30, 30, 36),
           "socktop": (30, 30, 36), "pattern": None, "number": (40, 40, 40), "trousers": True, "long_sleeves": True}
    kid = {"shirt": (40, 44, 60), "trim": (200, 40, 45), "shorts": (40, 44, 60), "socks": (40, 44, 60),
           "socktop": (40, 44, 60), "pattern": None, "number": (240, 240, 240), "trousers": True, "long_sleeves": True}
    spots = [(x, HY + 5.6, 0.0, 1.0, vis, 1.78) for x in (-36, -12, 12, 36)] + \
            [(x, -HY - 7.4, 0.0, -1.0, vis, 1.78) for x in (-40, -24, 24, 40)] + \
            [(-HX - 4.2, y, -1.0, 0.0, vis, 1.78) for y in (-14, 14)] + [(HX + 4.0, y, 1.0, 0.0, vis, 1.78) for y in (-14, 14)] + \
            [(sx * (HX + 2.0), sy * (HY + 2.0), -sx * 0.7, -sy * 0.7, kid, 1.45) for sx in (-1, 1) for sy in (-1, 1)] + \
            [(sx * (HX + 3.0), 6.0, -sx, 0.0, kid, 1.45) for sx in (-1, 1)]
    for j, (x, y, fx, fy, outfit, ht) in enumerate(spots):
        p = AnimPlayer(v.render, outfit, "", Player.SKINS[(j * 2) % 5], (40, 32, 25), name=f"steward{j}", height=ht)
        out.append({"p": p, "role": "edge", "pos": [x, y], "vel": [0.0, 0.0], "face": (fx, fy)})
    # Two subs from each side warming up in bibs, jogging up and down behind the boards on the far side.
    for team, x0, bib in ((0, 24.0, (240, 120, 30)), (1, 41.0, (90, 200, 80))):     # (the half the far
                                                                                        #  assistant isn't in)
        for j in range(2):
            top = {"shirt": bib, "trim": bib, "shorts": (30, 30, 34), "socks": (30, 30, 34), "socktop": (30, 30, 34),
                   "pattern": None, "number": (240, 240, 240), "trousers": True, "long_sleeves": True}
            p = AnimPlayer(v.render, top, 20 + j, Player.SKINS[(j * 2 + team + 1) % 5], (30, 25, 20), name=f"warm{team}{j}")
            out.append({"p": p, "role": "warmup", "team": team, "pos": [x0 + j * 2.0, HY + 2.3 + j * 0.7],
                        "vel": [0.0, 0.0], "x0": x0, "phase": j * 0.37})
    # Five substitutes on each bench, in training tops.
    for team, x0, kit in ((0, -9.0, kits_in_use[0]), (1, 9.0, kits_in_use[1])):
        for j in range(5):
            top = {"shirt": tuple(int(c * 0.75) for c in kit["shirt"]), "trim": kit.get("trim", kit["shirt"]),
                   "shorts": (30, 30, 34), "socks": (30, 30, 34), "socktop": (30, 30, 34), "pattern": None,
                   "number": (240, 240, 240), "trousers": True, "long_sleeves": True}
            p = AnimPlayer(v.render, top, 12 + j, Player.SKINS[(j * 3 + team) % 5], (30, 25, 20), name=f"sub{team}{j}")
            p.force_stand = "sit"
            out.append({"p": p, "role": "sub", "team": team, "pos": [x0 - 2.6 + j * 1.3, -HY - 5.85],
                        "vel": [0.0, 0.0]})
    return out


def _viewer_officiate(self, fr, dt, bx, by):
    if not self.officials:
        return
    import math as _m
    P = fr["p"]
    # which team defends the left end: the one whose keeper is there
    k0 = to_world(P[0][0], P[0][1])[0] if P else -1
    left = range(0, 11) if k0 < 0 else range(11, 22)
    right = range(11, 22) if k0 < 0 else range(0, 11)
    xs_l = sorted(to_world(P[i][0], P[i][1])[0] for i in left if P[i][6])
    xs_r = sorted((to_world(P[i][0], P[i][1])[0] for i in right if P[i][6]), reverse=True)
    for o in self.officials:
        x, y = o["pos"]
        if o["role"] == "manager":
            self._manage(o, fr, dt, bx, by)
            continue
        if o["role"] == "warmup":                                           # (jogging up and down, ~12 m each way)
            o["phase"] = o.get("phase", 0.0) + dt / 9.0
            tx = o["x0"] + 5.0 * math.sin(o["phase"] * 2 * math.pi)
            vx = (tx - x) / max(dt, 1e-3)
            vx = max(-3.0, min(3.0, vx))
            x += vx * dt
            o["pos"] = [x, y]
            cel = fr.get("c")
            o["p"].mood = None if not cel else ("joy" if cel[0] == o["team"] else None)
            o["p"].update(x, y, 1.0 if vx >= 0 else -1.0, 0.0, abs(vx) * 10, dt, True, vel=(vx, 0.0), ball=(bx, by))
            o["p"].act(None, 0.0)
            continue
        if o["role"] == "edge":                                             # (stewards, ball boys: stand and watch)
            fx0, fy0 = o["face"]
            o["p"].update(x, y, fx0, fy0, 0.0, dt, True, ball=(bx, by) if fy0 * (by - y) + fx0 * (bx - x) > 0 else None)
            o["p"].act(None, 0.0)
            continue
        if o["role"] == "sub":                                              # (on the bench - up if they score)
            cel = fr.get("c")
            o["p"].force_stand = "cheer" if cel and cel[0] == o["team"] else "sit"
            o["p"].update(x, y, 0.0, 1.0, 0.0, dt, True, ball=(bx, by))
            o["p"].act(None, 0.0)
            continue
        if o["role"] == "ref":
            # the diagonal (from his left of the near half to the far right), 12-18 m from the ball
            tx = max(-38.0, min(38.0, bx - 9.0 * (1 if bx > -20 else -1)))
            ty = tx * (24.0 / 40.0) - 6.0
            d = _m.hypot(tx - bx, ty - by)
            if d < 11.0:
                tx += (tx - bx) / max(d, 0.1) * (11.0 - d); ty += (ty - by) / max(d, 0.1) * (11.0 - d)
        elif o["role"] == "ar_near":                                         # (the right half, near side)
            line = xs_r[1] if len(xs_r) > 1 else HX - 16
            tx, ty = max(0.0, min(HX, max(line, bx))), -HY - 1.2
        else:                                                                # (the left half, far side)
            line = xs_l[1] if len(xs_l) > 1 else -HX + 16
            tx, ty = min(0.0, max(-HX, min(line, bx))), HY + 1.2
        card = fr.get("card")
        if card and o["role"] == "ref" and 0 <= card[1] < len(P):            # (a booking: over to the player)
            px_, py_ = to_world(P[card[1]][0], P[card[1]][1])
            dd = math.hypot(px_ - x, py_ - y) or 1.0
            tx, ty = px_ + (x - px_) / dd * 2.2, py_ + (y - py_) / dd * 2.2
        if fr.get("c"):                                                      # (a goal: back to the halfway line)
            tx = 0.0 if o["role"] != "ref" else -6.0
            ty = ty if o["role"] != "ref" else 4.0
        # move like a person: speed up / slow down, no faster than a sprint
        want = [(tx - x) * 0.9, (ty - y) * 0.9]
        sp = _m.hypot(*want)
        top = 7.0 if o["role"] == "ref" else 6.5
        if sp > top:
            want = [want[0] / sp * top, want[1] / sp * top]
        vx, vy = o["vel"]
        ax, ay = want[0] - vx, want[1] - vy
        a = _m.hypot(ax, ay)
        lim = 4.0 * dt
        if a > lim:
            ax, ay = ax / a * lim, ay / a * lim
        vx, vy = vx + ax, vy + ay
        x, y = x + vx * dt, y + vy * dt
        o["pos"], o["vel"] = [x, y], [vx, vy]
        speed = _m.hypot(vx, vy)
        fx, fy = (bx - x, by - y)                                           # (watching the ball)
        fl = _m.hypot(fx, fy) or 1.0
        if o["role"] != "ref" and speed > 3.0:                               # (an assistant sprinting: along the line)
            fx, fy = vx, vy; fl = speed
        o["p"].update(x, y, fx / fl, fy / fl, speed * 10.0, dt, True, vel=(vx, vy), ball=(bx, by))
        # Offside: the assistant on that side puts his flag up, the referee raises his arm (an indirect free
        # kick); a free kick: the referee points the way it's going.
        r = fr.get("r")
        k = fr.get("k", 0)
        kind, t = None, 0.0
        if r and r[0] in ("offside", "free_kick"):
            start = o.setdefault("r_start", {}).setdefault((r[0], self._restart_id(k)), k)
            t = (k - start) / 30.0
            if r[0] == "offside":
                mine = (o["role"] == "ar_near" and bx > 0) or (o["role"] == "ar_far" and bx <= 0)
                kind = "flag" if mine else ("signal" if o["role"] == "ref" else None)
            elif o["role"] == "ref":
                kind = "point"
        if card and o["role"] == "ref":
            kind, t = "card", 0.5
            self._card_in_hand(o["p"], card[0])
        elif o["role"] == "ref":
            self._card_in_hand(o["p"], None)
        o["p"].act(kind, t - 0.3 if kind == "point" else t)


def _viewer_manage(self, o, fr, dt, bx, by):
    """A manager: up and down his technical area following play, pointing now and then; after a goal, one
    celebrates and the other stands with his hands on his hips."""
    import math as _m
    p = o["p"]
    o["t"] += dt
    tx = o["home_x"] + max(-2.0, min(2.0, (bx - o["home_x"]) * 0.08))
    x, y = o["pos"]
    vx = max(-1.6, min(1.6, (tx - x) * 1.2))
    x += vx * dt
    o["pos"] = [x, y]
    cel = fr.get("c")
    p.mood = None if not cel else ("joy" if cel[0] == o["team"] else "sad")
    fx, fy = bx - x, by - y
    fl = _m.hypot(fx, fy) or 1.0
    p.update(x, y, fx / fl, fy / fl, abs(vx) * 10.0, dt, True, vel=(vx, 0.0), ball=(bx, by))
    if o["t"] > o["next_point"] and not cel:
        o["point_t"] = o["t"]
        o["next_point"] = o["t"] + 9.0 + 11.0 * ((int(o["t"] * 7) % 10) / 10.0)
    pt = o["t"] - o.get("point_t", -99)
    p.act("point" if pt < 1.6 and not cel else None, pt - 0.4)


def _viewer_restart_id(self, k):
    """Which dead ball this frame belongs to (the frame it started on)."""
    F = self.m["frames"]
    cache = self.__dict__.setdefault("_rid", {})
    if k in cache:
        return cache[k]
    j = k
    while j > 0 and "r" in F[j - 1]:
        j -= 1
    cache[k] = j
    return j


def _viewer_scorer_slide(self, i, sp, k, kind, t):
    """Half of scorers finish their run with a knee slide (the other half jump about): when he slows from a
    sprint, down he goes."""
    st = self.__dict__.setdefault("_slide", {})
    rid = self._restart_id(k)
    s = st.setdefault(rid, {"top": 0.0, "at": None, "yes": (rid // 2 + i) % 2 == 0})
    s["top"] = max(s["top"], sp)
    if s["at"] is None and s["yes"] and s["top"] > 50 and sp < 38:
        s["at"] = k
    if s["at"] is not None and 0 <= (k - s["at"]) / 30.0 <= 1.9:
        return "kneeslide", (k - s["at"]) / 30.0
    return kind, t


def _viewer_calling(self, i, fr, wx, wy, sp, k):
    """A team-mate making a run calls for it: arm up for a second or so, now and then - when his side has the
    ball, he's sprinting, and he's 12-35 m away from it."""
    o = fr["o"]
    if o < 0 or o == i or (o < 11) != (i < 11) or sp < 45 or (i in (0, 11)):
        return False
    ox, oy = to_world(fr["p"][o][0], fr["p"][o][1])
    d = math.hypot(wx - ox, wy - oy)
    if not 12 < d < 35:
        return False
    return ((k + i * 37) // 36) % 5 == 0                                    # (about a second in every six)


def _viewer_card_in_hand(self, p, kind):
    """The card in the referee's raised hand (yellow, or red)."""
    if not hasattr(p, "card_np"):
        hand = p.a.exposeJoint(None, "modelRoot", "hand.r")
        p.card_np = box(hand, -0.04, -0.005, 0.05, 0.04, 0.005, 0.17, (1, 1, 1, 1))
        p.card_np.setShaderInput("kit_on", 0.0); p.card_np.setTextureOff(3)
    if kind is None:
        p.card_np.hide()
        return
    p.card_np.show()
    p.card_np.setColor((0.98, 0.85, 0.1, 1) if kind == "yellow" else (0.85, 0.1, 0.1, 1))


Viewer._card_in_hand = _viewer_card_in_hand
Viewer._calling = _viewer_calling
Viewer._scorer_slide = _viewer_scorer_slide
Viewer._restart_id = _viewer_restart_id
Viewer._manage = _viewer_manage
Viewer._officiate = _viewer_officiate
Viewer._goal_ball = _viewer_goal_ball
Viewer._spin_ball = _viewer_spin_ball
Viewer._throw_dir = _viewer_throw_dir
Viewer._left_foot = _viewer_left_foot
Viewer._keeper_dive = _viewer_keeper_dive
Viewer._ball = _viewer_ball
Viewer._dribble_touch = _viewer_dribble


class Events:
    """Kicks, shots, first touches, headers and tackles, found from the recording (who had the ball, how fast
    it moved), so each player can be posed around the moment he plays it."""
    WINDOW = 0.45

    def __init__(self, frames):
        self.by_player = {}
        self.fps = 30.0

    RANK = {"despair": 0, "kneeslide": 7, "throwin": 6, "punt": 5, "bowl": 5, "shot": 4, "header": 3, "tackle": 3, "kick": 2, "touch": 1}

    def add(self, i, k, kind):
        l = self.by_player.setdefault(i, [])
        for n, (k2, kind2) in enumerate(l):
            if abs(k2 - k) <= 8:                                            # (the same moment, seen twice)
                if self.RANK[kind] > self.RANK[kind2]:
                    l[n] = (k, kind)
                return
        l.append((k, kind))

    def action(self, i, k):
        import gait
        best = None
        for (ke, kind) in self.by_player.get(i, ()):
            t = (k - ke) / self.fps
            lo, hi = gait.SPANS.get(kind, (-self.WINDOW, self.WINDOW))
            if lo <= t <= hi and (best is None or abs(t) < abs(best[1])):
                best = (kind, t)
        return best if best else (None, 0.0)


def find_events(F, keepers=(0, 11)):
    import math as _m
    ev = Events(F)
    for k, fr in enumerate(F):
        fr["k"] = k
    sp = lambda a, b: _m.dist(a[:2], b[:2]) / 10.0 * 30.0                  # m/s, from two frames
    gained = {}
    for k in range(2, len(F) - 4):
        a, b = F[k - 1]["o"], F[k]["o"]
        if b >= 0 and a != b:
            gained[b] = (k, "r" in F[k - 1] or "r" in F[k - 2])            # (when he got it - from a dead ball?)
        if a >= 0 and b < 0:                                                # he's played it
            v = sp(F[k]["b"], F[k + 3]["b"]) / 3.0
            z = F[k - 1]["b"][2] / 10.0
            gk, dead = gained.get(a, (-99, False))
            if a in keepers and k - gk <= 15 and not dead and z < 2.5:      # (a keeper, ball just caught: out of his hands)
                ev.add(a, k, "punt" if v > 17 else "bowl")
                continue
            ev.add(a, k, "header" if z > 1.3 else "shot" if v > 21 else "kick")
        elif a < 0 and b >= 0:
            z = F[k]["b"][2] / 10.0
            ev.add(b, k, "header" if z > 1.3 else "touch")                  # (the first touch)
        elif a >= 0 and b >= 0 and a != b:
            if (a < 11) != (b < 11):
                ev.add(b, k, "tackle")
        elif a < 0 and b < 0:                                               # a loose ball changes course
            v0 = [(F[k - 1]["b"][j] - F[k - 2]["b"][j]) * 3.0 for j in range(3)]
            v1 = [(F[k]["b"][j] - F[k - 1]["b"][j]) * 3.0 for j in range(3)]
            if _m.dist(v0, v1) > 5.0:
                bx, by = F[k]["b"][0], F[k]["b"][1]
                near = min(((_m.hypot(p[0] - bx, p[1] - by) / 10.0, i) for i, p in enumerate(F[k]["p"]) if p[6]),
                           default=(99, -1))
                if near[0] < 2.0:
                    z = F[k]["b"][2] / 10.0
                    ev.add(near[1], k, "header" if z > 1.3 else "kick")
    for i, l in list(ev.by_player.items()):                                  # a shot that didn't go in: hands
        for (ke, kind) in list(l):                                           # on head a moment later
            if kind == "shot" and ke + 75 < len(F) and F[ke + 75]["s"] == F[ke]["s"]:
                l.append((ke + 24, "despair"))
    for k in range(1, len(F) - 4):                                           # dead balls: who took it, and how
        r = F[k - 1].get("r")
        if r and "r" not in F[k] and r[1] >= 0:
            v = sp(F[k]["b"], F[k + 3]["b"]) / 3.0
            kind = {"throw_in": "throwin", "kick_off": "touch", "penalty": "shot"}.get(r[0], "shot" if v > 21 else "kick")
            l = ev.by_player.setdefault(r[1], [])
            l[:] = [(k2, kd) for (k2, kd) in l if abs(k2 - k) > 8]
            l.append((k, kind))
    return ev


def intro(v, F, first, n, out, start_idx):
    """An establishing shot: the camera swings round Kiln Lane from high above the Canal End."""
    for i in range(n):
        a = math.radians(-60 + 70 * i / n)
        v.show(F[first], 1 / 30.0)
        v.cam.setPos(150 * math.sin(a) + 20, -150 * math.cos(a), 70 - 25 * i / n)
        v.cam.lookAt(0, 8, 0)
        v.taskMgr.step()   # (runs the lighting tasks, then draws)
        img = PNMImage(); v.win.getScreenshot(img); img.write(Filename(f"{out}/f{start_idx + i:05d}.png"))
    return n


def tick():
    from panda3d.core import ClockObject
    ClockObject.getGlobalClock().tick()


def play(v, F, first):
    """Watch it in a window, in real time: space = pause, left / right = back / on 10 seconds, [ / ] = slower /
    faster, 1 = TV camera, 2 = close camera, Esc = quit."""
    from panda3d.core import ClockObject
    st = {"t": float(first), "speed": 1.0, "paused": False}

    def key(name, fn):
        v.accept(name, fn); v.accept(name + "-repeat", fn)
    key("space", lambda: st.update(paused=not st["paused"]))
    key("arrow_left", lambda: st.update(t=max(0.0, st["t"] - 300)))
    key("arrow_right", lambda: st.update(t=min(len(F) - 2.0, st["t"] + 300)))
    key("[", lambda: st.update(speed=max(0.25, st["speed"] / 2)))
    key("]", lambda: st.update(speed=min(4.0, st["speed"] * 2)))
    key("1", lambda: setattr(v, "cam_mode", 0))
    key("2", lambda: setattr(v, "cam_mode", 1))
    v.accept("escape", sys.exit)
    help_t = OnscreenText(text="space pause   <- -> 10 s   [ ] speed   1 TV   2 close   Esc quit", pos=(0, -0.95),
                          scale=0.04, fg=(1, 1, 1, 0.8), mayChange=False)

    def tick_task(task):
        dt = min(0.1, ClockObject.getGlobalClock().getDt())
        if not st["paused"]:
            st["t"] = min(len(F) - 1.0, st["t"] + dt * 30.0 * st["speed"])
        v.show(F[int(st["t"])], dt * (0 if st["paused"] else st["speed"]) or 1e-3)
        return task.cont
    v.taskMgr.add(tick_task, "play")
    if "--test" in sys.argv:                              # (a check without a screen: 60 frames, then a picture)
        c = ClockObject.getGlobalClock(); c.setMode(ClockObject.MNonRealTime); c.setFrameRate(30)
        import time
        n = 240 if "--time" in sys.argv else 60           # (--time: how long each frame takes)
        t0 = time.perf_counter()
        for i in range(n):
            if i == 30:
                t0 = time.perf_counter()
            v.taskMgr.step()
        if "--time" in sys.argv:
            ms = (time.perf_counter() - t0) / (n - 30) * 1000
            print(f"frame time {ms:.1f} ms ({1000 / ms:.0f} frames a second, offscreen, software drawing)")
        img = PNMImage(); v.win.getScreenshot(img); img.write(Filename(os.path.join(HERE, "frames", "live_test.png")))
        print("live test ok, frame", int(st["t"]))
        return
    v.run()


def main():
    if ANIM and not OFF:                                  # (watching live: the real clock)
        sys.path.insert(0, HERE)
        global AnimPlayer
        from players3d import AnimPlayer
    elif ANIM:
        sys.path.insert(0, HERE)
        global AnimPlayer
        from players3d import AnimPlayer
        from panda3d.core import ClockObject
        c = ClockObject.getGlobalClock(); c.setMode(ClockObject.MNonRealTime); c.setFrameRate(30)
    mj = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--match=")), os.path.join(HERE, "match.json"))
    if os.path.exists(mj):
        d = json.load(open(mj))
    else:                                                 # (the sample match that comes with it)
        import gzip
        d = json.load(gzip.open(mj + ".gz", "rt"))
    first = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 5700
    n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 1
    out = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else os.path.join(HERE, "frames")
    os.makedirs(out, exist_ok=True)
    v = Viewer(d)
    F = d["frames"]
    if not OFF or "--test" in sys.argv:
        return play(v, F, first)
    # warm the camera up on the first frame
    for _ in range(40):
        v.show(F[first], 1 / 30.0); tick()
    k = intro(v, F, first, 120, out, 0) if "--intro" in sys.argv else 0
    for _ in range(40):
        v.show(F[first], 1 / 30.0)
    for _ in range(2):
        v.taskMgr.step()                                  # (draw twice first: the sun's shadow map is a frame behind)
    for i in range(n):
        v.show(F[first + i], 1 / 30.0)
        v.taskMgr.step()   # (this also moves the clock on one frame - don't tick() as well)   # (runs the lighting tasks, then draws)
        img = PNMImage(); v.win.getScreenshot(img); img.write(Filename(f"{out}/f{k + i:05d}.png"))
    print("rendered", n)


if __name__ == "__main__":
    main()
