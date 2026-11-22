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
SNOW = "--snow" in sys.argv                 # (a rare snowy day: flakes falling, the pitch white, the lines swept)
DUSK = "--dusk" in sys.argv                 # (a 3 o'clock kick-off in midwinter: darker through the second half)
FOG = "--fog" in sys.argv                   # (a misty winter evening: the far stand softened, the lights hazy)
if RAIN or SNOW:
    OVERCAST = True
SUN_AZ, SUN_EL = 200.0, 22.0               # the sun: degrees round from behind the Main Stand, and up
SHADOW_MAP = 4096
ANIM = "--boxes" not in sys.argv          # (animated figures unless --boxes: the old block players)
MIXAMO = "--mixamo" in sys.argv           # (test, 21 Nov: the Mixamo footballer - broadcast3d/mixamo.py)
# The winter ball (--winterball): from the clocks going back in late October to the spring the Premier League
# plays with a hi-vis ball, easier to follow under floodlights (premierleague.com, "Why does the Premier League
# have a hi-vis ball for winter?").  Ours: yellow panels for white.
WHITE_PANEL = (0.98, 0.86, 0.12, 1) if "--winterball" in sys.argv else (0.97, 0.97, 0.97, 1)
EMBED = "--embedded" in sys.argv          # (drawn inside the game's match screen: broadcast3d/live.py)
_SIZE = os.environ.get("FM3D_SIZE", "1280x720").replace("x", " ")
loadPrcFileData("", ("window-type offscreen\n" if OFF else "") + f"win-size {_SIZE}\naudio-library-name null\n"
                "framebuffer-multisample 1\nmultisamples 4\ntextures-power-2 none\nsync-video 0")
from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenText import OnscreenText
from direct.gui.OnscreenImage import OnscreenImage
from panda3d.core import (ShaderAttrib, AmbientLight, DirectionalLight, Vec4, Vec3, Point3, CardMaker, TextNode, PNMImage, Shader, BitMask32,
                          Filename, Texture, SamplerState, TransparencyAttrib, AntialiasAttrib, Fog)
from geom import Mesh, box, box_into, sphere, prism

HERE = os.path.dirname(os.path.abspath(__file__))       # (this folder: broadcast3d/)
GAME = os.path.dirname(HERE)                             # (the game folder)
sys.path.insert(0, HERE)
T = os.path.join(HERE, "tex") + os.sep


def pf(path):
    """A file's path the way Panda3D wants it (on Windows "C:\\Users\\..." has to become "/c/Users/...")."""
    from panda3d.core import Filename
    return Filename.fromOsSpecific(path)


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
            t = self.b.loader.loadTexture(pf(T + name))
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
        # One crowd picture = 36 m of stand: ~80 fans across it, so a fan to every ~0.45 m - a real seat is
        # 0.45-0.5 m wide (the Green Guide, Guide to Safety at Sports Grounds, 6th ed., 12.6) - and as wide as
        # he's tall in the picture.  (It was 14 m: thin, stretched people, which showed in close-ups.)
        rep = (x1 - x0) / 36.0
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
        if os.environ.get("FM_3D_GROUND") == "national":       # (the play-off final: a neutral ground)
            grounds.build(self, grounds.NATIONAL, kits.club_kits(home)[0][0])
            return
        if slug == "ashvale" or not prof or not prof.get("ground", {}).get("stands"):
            self.build_kiln_lane()
        else:
            grounds.build(self, prof, kits.club_kits(home)[0][0])

    def pitch_surround(self):
        cm = CardMaker("pitch"); cm.setFrame(-HX - 8, HX + 8, -HY - 8, HY + 8)
        tex_name = "pitch.png"
        try:                                                                # (each ground its own pitch)
            import kits as _kk, textures as _tx
            home = TEAMS[0] if TEAMS else self.b.m.get("home", "Ashvale Rovers")
            prof, slug = _kk.profile(home)
            if os.environ.get("FM_3D_GROUND") == "national":
                import grounds as _gr
                prof, slug = _gr.NATIONAL, "national"
            if slug and slug != "ashvale":
                tex_name = _tx.ground_pitch(slug, prof)
        except Exception as e:
            print("pitch:", e)
        p = self.root.attachNewNode(cm.generate()); p.setP(-90); p.setTexture(self.T(tex_name, False)); no_shadow(p)
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
        if NIGHT or OVERCAST:                               # (a dull November afternoon: the floodlights on too)
            lamp = (2.2, 2.2, 2.1, 1) if NIGHT else (1.6, 1.6, 1.5, 1)
            for side, x0, x1, d, z in lamps:
                strip = box(self.side(side), x0, d - 0.3, z - 0.4, x1, d, z, lamp)
                strip.setShaderOff(1); strip.setLightOff(1); no_shadow(strip, lit=False)
                if NIGHT:                                   # (at night: the light glowing in the damp air)
                    x = x0 + 4.0
                    while x < x1 - 2.0:
                        self._glow(self.side(side), (x, d - 0.5, z - 0.2), 7.0, 0.55)
                        x += 11.0

    def _glow(self, parent, pos, size, strength):
        """A soft glow round a floodlight (at night): a bright blur that adds to whatever's behind it."""
        from panda3d.core import ColorBlendAttrib
        if not os.path.exists(T + "glow.png"):
            from PIL import Image
            g = Image.new("L", (128, 128))
            px = g.load()
            for yy in range(128):
                for xx in range(128):
                    r = math.hypot(xx - 63.5, yy - 63.5) / 63.5
                    px[xx, yy] = int(255 * max(0.0, 1.0 - r) ** 2.2)
            Image.merge("RGBA", (g, g, g, g)).save(T + "glow.png")
        cm = CardMaker("glow"); cm.setFrame(-size / 2, size / 2, -size / 2, size / 2)
        n = parent.attachNewNode(cm.generate())
        n.setPos(*pos)
        n.setBillboardPointEye()
        n.setTexture(self.T("glow.png", False))
        n.setColor(1.0, 0.97, 0.88, 1)
        n.setColorScale(strength, strength, strength, 1)
        n.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.MAdd, ColorBlendAttrib.OIncomingAlpha, ColorBlendAttrib.OOne))
        n.setDepthWrite(False)
        n.setBin("fixed", 20)
        n.setShaderOff(1); n.setLightOff(1)
        no_shadow(n, lit=False)
        return n

    def build_kiln_lane(self):
        b = self.b
        home_tex = "crowd_home.png"
        try:                                            # (a half-empty ground: FM_3D_CROWD, broadcast3d/textures.py)
            if float(os.environ.get("FM_3D_CROWD", "1") or 1) < 0.97:
                import textures
                textures.crowd("crowd_home_live.png", [((200, 40, 45), 6), ((235, 235, 235), 2), ((30, 30, 34), 2)], seed=1)
                home_tex = "crowd_home_live.png"
        except Exception as e:
            print("crowd:", e)
        self.pitch_surround()
        # Haworth Stand (far side): two tiers, flat roof on columns
        f = self.side("far")
        self.tier(f, -48, 48, 9, 1.4, 25, 11, home_tex, (200, 40, 45))
        self.tier(f, -48, 48, 22, 14.5, 36, 25, home_tex, (240, 240, 240))
        box(f, -48, 20, 11, 48, 23, 14.4, C((200, 40, 45)))                  # the fascia between the tiers
        self.back_wall(f, -48, 48, 36, 0, 29)
        self.roof(f, -49, 49, 16, 38, 29, columns=6)
        # Weavers' End (left): one steep tier, truss roof
        w = self.side("left")
        self.tier(w, -30, 30, 8, 1.4, 30, 20, home_tex, (200, 40, 45))
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
        self.tier(n, -50, 50, 8, 1.2, 20, 8, home_tex, (200, 40, 45))
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
        if NIGHT or OVERCAST:                               # (the lamps, lit - at night, or on a dull day)
            gl = box(n, -3.8, -0.62, H + 0.2, 3.8, -0.5, H + 4.8, (2.4, 2.4, 2.3, 1) if NIGHT else (1.7, 1.7, 1.6, 1))
            gl.setShaderOff(1); gl.setLightOff(1)
            if NIGHT:
                self._glow(n, (0, -2.0, H + 2.5), 22.0, 0.75)
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
        self.stadium = st
        self.light_up()
        fog = Fog("haze"); fog.setColor(*((0.62, 0.66, 0.7) if not NIGHT else (0.04, 0.045, 0.07)))
        fog.setExpDensity(0.0012 if not RAIN else 0.0035)
        if FOG:
            fog.setExpDensity(0.0075)
            fog.setColor(*((0.62, 0.64, 0.66) if not NIGHT else (0.11, 0.115, 0.13)))
        self.render.setFog(fog)
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
                                               crest=info.get("crest"), role=role,
                                               captain=(i % 11) == self._captain(match, i // 11)))
                self.players[-1].kit = kit
                if MIXAMO:                                                # (test: the Mixamo footballer -
                    import mixamo                                         #  broadcast3d/mixamo.py)
                    mixamo.attach(self.players[-1], kit, keeper, num or (i % 11) + 1, name, skin, hair)
            else:
                self.players.append(Player(self.render, kit, (i % 11) + 1, skin, hair, keeper))
        self.officials = []
        if ANIM:
            self.officials = make_officials(self, (home, away, gk0, gk1))
        cm = CardMaker("shadow"); cm.setFrame(-0.45, 0.45, -0.3, 0.3)          # soft blob shadows
        from PIL import Image, ImageFilter, ImageDraw
        sh = Image.new("RGBA", (64, 64), (0, 0, 0, 0)); ImageDraw.Draw(sh).ellipse([8, 14, 56, 50], fill=(0, 0, 0, 120))
        sh.filter(ImageFilter.GaussianBlur(5)).save(T + "shadow.png")
        stex = self.loader.loadTexture(pf(T + "shadow.png"))
        self.shadows = []
        self._blob = (cm, stex)
        for p in self.players + [o["p"] for o in self.officials]:
            self._shadow_under(p)
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
        self._shield_left = {}
        self.hud(match)
        self._big_screen()
        if RAIN:
            self.make_rain()
        if SNOW:
            self.make_rain(snow=True)

    def _shadow_under(self, p):
        """The soft dark patch under a player's feet (and at night, the floodlights' four faint shadows)."""
        cm, stex = self._blob
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

    def name_tags(self, on):
        """The players' names over their heads (N in the game), small, always facing the camera."""
        for i, p in enumerate(self.players):
            tag = getattr(p, "tag", None)
            if on and tag is None:
                nm = self.m["names"][i][0] if i < len(self.m["names"]) else ""
                nm = nm.split()[-1] if nm else ""
                tn = TextNode(f"tag{i}")
                tn.setText(nm)
                tn.setAlign(TextNode.ACenter)
                tn.setTextColor(1, 1, 1, 1)
                tn.setShadow(0.06, 0.06)
                tn.setShadowColor(0, 0, 0, 0.9)
                tag = p.root.attachNewNode(tn)
                tag.setPos(0, 0, 2.35)
                tag.setScale(0.42)
                tag.setBillboardPointEye()
                tag.setShaderOff(1)
                tag.setLightOff(1)
                tag.setDepthTest(False)
                tag.setDepthWrite(False)
                tag.setBin("fixed", 50)
                no_shadow(tag, lit=False)
                p.tag = tag
            if tag is not None:
                if on:
                    tag.show()
                else:
                    tag.hide()
        self._tags_on = on

    def lighten(self):
        """Less to draw, for a slower computer (live.py, when the pictures take too long): the stewards and the
        subs warming up go, and the sun's shadow picture is made at half the size (softer shadow edges)."""
        for o in self.officials:
            if o["role"] in ("edge", "warmup"):
                o["skip"] = True
                o["p"].root.hide()
        if getattr(self, "sun_buf", None) is not None:
            import sunshadow
            self.graphicsEngine.removeWindow(self.sun_buf)
            old = self.sun.find("sun camera")
            if not old.isEmpty():
                old.removeNode()
            self.sun_buf = sunshadow.make(self, self.sun, 2048, (250, 170), (10, 600), NO_SHADOW_BIT)
            self.render.setShaderInput("shadow_texel", 1.0 / 2048)

    def replace_player(self, i, name, role, num):
        """A substitute on for player i (live, broadcast3d/live.py): a new man - his own face, build, name and
        number - in the same kit, where the old one was."""
        old = self.players[i]
        team = 0 if i < 11 else 1
        keeper = role == "GK"
        home, away = self.kits
        kit = getattr(old, "kit", None)
        if kit is None:
            kit = home if team == 0 else away
        import random
        rnd = random.Random(f"{name}{num}")
        skin = rnd.choice(Player.SKINS)
        hair = rnd.choice([(40, 28, 20), (25, 20, 18), (120, 80, 40), (200, 170, 110), (15, 12, 10)])
        info = self.home_info if team == 0 else self.away_info
        p = AnimPlayer(self.render, kit, num, skin, hair, keeper, name=name, crest=info.get("crest"), role=role)
        p.kit = kit
        if MIXAMO:
            import mixamo
            mixamo.attach(p, kit, keeper, num, name, skin, hair)
        p.root.setPos(old.root.getPos()); p.root.setH(old.root.getH())
        self._shadow_under(p)
        if getattr(old, "flood", None) is not None:
            old.flood.removeNode()
        # The man coming off walks to the nearest touchline, clapping the fans, and is gone once he's off.
        ox, oy = old.root.getX(), old.root.getY()
        self.__dict__.setdefault("_leaving", []).append({"p": old, "to": (ox, (HY + 2.5) if oy > 0 else -(HY + 2.5)),
                                                         "t": 0.0})
        self.players[i] = p
        self.m["names"][i] = [name, role, num]
        # The man coming on comes on at the halfway line, from the benches' side, and jogs to his place (the law:
        # the substitute enters at the halfway line; the man off leaves by the nearest point - above)
        if not keeper:
            sx, sy = (-1.2 if team == 0 else 1.2), -HY - 0.6
            p.root.setPos(sx, sy, 0)
            self.__dict__.setdefault("_arriving", {})[i] = [sx, sy, 0.0]
        if getattr(old, "captain", False):              # (the captain's off: the armband to a team-mate - the
            lo = 0 if team == 0 else 11                 #  first defender, or whoever's next)
            for j in list(range(lo + 1, lo + 11)) + [lo]:
                if j != i and not getattr(self.players[j], "keeper", False):
                    self.players[j].root.setShaderInput("kit_cap", 1.0)
                    self.players[j].captain = True
                    break
        if getattr(self, "_tags_on", False):
            self.name_tags(True)

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
            self._day_lights = (al, tuple(al.getColor()), dl, tuple(dl.getColor()))   # (dusk: dimmed as it goes on)
            sun = self.render.attachNewNode(dl); sun.setPos(-40, -60, 120); sun.lookAt(0, 0, 0)
            self.render.setLight(sun)
            self._shader_inputs()
            return
        al = AmbientLight("amb"); al.setColor(Vec4(0.50, 0.53, 0.60, 1) if not NIGHT else Vec4(0.30, 0.32, 0.38, 1))
        self.render.setLight(self.render.attachNewNode(al))
        dl = DirectionalLight("sun"); dl.setColor(Vec4(1.25, 1.12, 0.92, 1) if not NIGHT else Vec4(1.0, 1.0, 1.05, 1))
        sun = self.render.attachNewNode(dl)
        az, el = math.radians(SUN_AZ), math.radians(SUN_EL)
        sun.setPos(-math.sin(az) * math.cos(el) * 300, -math.cos(az) * math.cos(el) * 300, math.sin(el) * 300)
        sun.lookAt(0, 0, 0)
        self.render.setLight(sun)
        self.sun = sun
        self._shader_inputs()
        import sunshadow                                   # (the sun's shadows: our own depth picture from the sun;
        self.sun_buf = sunshadow.make(self, sun, SHADOW_MAP, (250, 170), (10, 600), NO_SHADOW_BIT)  # no_shadow())

    def _shader_inputs(self):
        sh = Shader.load(Shader.SL_GLSL, pf(os.path.join(HERE, "shaders", "lit.vert")), pf(os.path.join(HERE, "shaders", "lit.frag")))
        self.render.setShader(sh)
        import sunshadow as _ss
        if _ss.GPU_SKIN:                                   # (the players bent onto their skeletons by the graphics card)
            self.render.setAttrib(self.render.getAttrib(ShaderAttrib).setFlag(ShaderAttrib.F_hardware_skinning, True))
        self.render.setShaderInput("skin_on", 0.0)
        if ANIM:
            from players3d import shader_defaults
            shader_defaults(self.render)
            if RAIN:
                self.render.setShaderInput("mud_amt", 1.0)
        import sunshadow
        sunshadow.no_sun(self.render)                       # (until the sun's own is made: light_up)
        self.render.setShaderInput("clip_y", -1.0e6)
        self.render.setShaderInput("snow_amt", 0.85 if SNOW else 0.0)
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
        hp = self.hud_np = self.aspect2d.attachNewNode("scoreboard")
        DirectFrame(parent=hp, frameColor=(0.06, 0.07, 0.09, 0.88), frameSize=(0, 0.92, -0.11, 0), pos=(-1.72, 0, 0.94))
        for info, kit, x in ((self.home_info, self.kits[0], -1.66), (self.away_info, self.kits[1], -1.04)):
            if info.get("crest"):
                img = OnscreenImage(parent=hp, image=self.loader.loadTexture(Filename.fromOsSpecific(info["crest"])),
                                    pos=(x, 0, 0.885), scale=(0.042, 1, 0.044))
                img.setTransparency(TransparencyAttrib.MAlpha)
            else:                                                       # (no crest yet: a patch of the shirt colour)
                DirectFrame(parent=hp, frameColor=C(kit["shirt"]), frameSize=(-0.03, 0.03, -0.03, 0.03), pos=(x, 0, 0.885))
        self.labels = (self.home_info["short"][:3].upper(), self.away_info["short"][:3].upper())
        self.score_t = OnscreenText(parent=hp, text="", pos=(-1.35, 0.87), scale=0.055, fg=(1, 1, 1, 1), align=TextNode.ACenter,
                                    mayChange=True)
        self.clock_t = OnscreenText(parent=hp, text="", pos=(-0.88, 0.87), scale=0.05, fg=(0.85, 0.9, 0.85, 1), align=TextNode.ACenter,
                                    mayChange=True)
        if EMBED:                                       # (in the game: its own score bar is above the picture)
            hp.hide()

    def lineups(self, match):
        """The team sheets, as TV shows them before kick-off: both XIs, numbers and names, in the clubs' colours.
        Shown for the first few seconds (live, or --lineups when making pictures)."""
        from direct.gui.DirectGui import DirectFrame
        names = match.get("names", [])
        if len(names) < 22:
            return None
        root = self.aspect2d.attachNewNode("lineups")
        for side, (info, kit, x0) in enumerate(((self.home_info, self.kits[0], -0.98), (self.away_info, self.kits[1], 0.06))):
            DirectFrame(parent=root, frameColor=(0.06, 0.07, 0.09, 0.9), frameSize=(0, 0.92, -1.12, 0),
                        pos=(x0, 0, 0.62))
            DirectFrame(parent=root, frameColor=C(kit["shirt"]), frameSize=(0, 0.92, -0.11, 0), pos=(x0, 0, 0.62))
            sh = kit["shirt"]
            dark = (sh[0] * 0.3 + sh[1] * 0.59 + sh[2] * 0.11) > 150
            OnscreenText(parent=root, text=(match.get("home") if side == 0 else match.get("away") or "")[:24].upper(), pos=(x0 + 0.46, 0.545), scale=0.05,
                         fg=(0.05, 0.05, 0.05, 1) if dark else (1, 1, 1, 1), align=TextNode.ACenter)
            for j in range(11):
                nm, role, num = names[side * 11 + j][:3]
                y = 0.44 - j * 0.088
                OnscreenText(parent=root, text=str(num), pos=(x0 + 0.1, y), scale=0.045, fg=(0.98, 0.85, 0.3, 1),
                             align=TextNode.ARight)
                OnscreenText(parent=root, text=nm, pos=(x0 + 0.15, y), scale=0.045, fg=(1, 1, 1, 1),
                             align=TextNode.ALeft)
                OnscreenText(parent=root, text=role, pos=(x0 + 0.86, y), scale=0.038, fg=(0.7, 0.75, 0.8, 1),
                             align=TextNode.ARight)
        return root

    def stats_panel(self, k, title=None):
        """The TV stats card (key S live, --stats for pictures): possession, shots, passes... up to frame k,
        worked out from the recording.  title ("HALF-TIME"): a band on top with it and the score (the live
        view puts this up at half-time, behind the game's half-time screen)."""
        from direct.gui.DirectGui import DirectFrame
        F = self.m["frames"]
        own = [0, 0]
        if hasattr(F, "own"):                                   # (live: counted as the frames came in)
            own = list(F.own)
        else:
            for fr in F[:k + 1]:
                o = fr["o"]
                if o is not None and o >= 0:
                    own[0 if o < 11 else 1] += 1
        tot = max(1, own[0] + own[1])
        poss = [round(100 * own[0] / tot), 100 - round(100 * own[0] / tot)]
        cnt = {kind: [0, 0] for kind in ("shot", "kick", "tackle", "fouled", "header")}
        alias = {k: "kick" for k in KICKS}
        alias["hurt"] = "fouled"
        alias["finish"] = alias["dink"] = "shot"
        alias["flickhead"] = "header"
        alias["volley"] = "kick"
        for i, l in self.events.by_player.items():
            for ke, kind in l:
                kind = alias.get(kind, kind)
                if ke <= k and kind in cnt:
                    cnt[kind][0 if i < 11 else 1] += 1
        rows = [("Possession", f"{poss[0]}%", f"{poss[1]}%"), ("Shots", *map(str, cnt["shot"])),
                ("Passes", *map(str, cnt["kick"])), ("Tackles won", *map(str, cnt["tackle"])),
                ("Headers", *map(str, cnt["header"])), ("Fouls suffered", *map(str, cnt["fouled"]))]
        root = self.aspect2d.attachNewNode("stats")
        DirectFrame(parent=root, frameColor=(0.06, 0.07, 0.09, 0.9), frameSize=(-0.62, 0.62, -0.54, 0.42))
        for side, (kit, x) in enumerate(((self.kits[0], -0.45), (self.kits[1], 0.45))):
            bar = kit["shirt"] if sum(kit["shirt"]) > 160 else kit.get("trim", kit["shirt"])   # (a black shirt:
            DirectFrame(parent=root, frameColor=C(bar), frameSize=(-0.15, 0.15, -0.012, 0.012),     #  its trim shows)
                        pos=(x, 0, 0.25))
        OnscreenText(parent=root, text=self.labels[0], pos=(-0.45, 0.3), scale=0.055, fg=(1, 1, 1, 1))
        OnscreenText(parent=root, text=self.labels[1], pos=(0.45, 0.3), scale=0.055, fg=(1, 1, 1, 1))
        OnscreenText(parent=root, text="MATCH STATS", pos=(0, 0.3), scale=0.045, fg=(0.98, 0.85, 0.3, 1))
        for j, (lab, a, b) in enumerate(rows):
            y = 0.13 - j * 0.12
            OnscreenText(parent=root, text=lab, pos=(0, y), scale=0.045, fg=(0.8, 0.85, 0.9, 1))
            OnscreenText(parent=root, text=a, pos=(-0.45, y), scale=0.055, fg=(1, 1, 1, 1))
            OnscreenText(parent=root, text=b, pos=(0.45, y), scale=0.055, fg=(1, 1, 1, 1))
        if title:
            sc = F[min(k, len(F) - 1)].get("s", [0, 0]) if F else [0, 0]
            DirectFrame(parent=root, frameColor=(0.98, 0.85, 0.3, 0.95), frameSize=(-0.62, 0.62, 0.42, 0.56))
            OnscreenText(parent=root, text=f"{title}    {self.labels[0]}  {sc[0]} - {sc[1]}  {self.labels[1]}",
                         pos=(0, 0.47), scale=0.06, fg=(0.06, 0.07, 0.09, 1))
        root.setBin("fixed", 20)
        if EMBED and title:                             # (in the game: to the right, clear of the game's own
            root.setScale(0.85)                         #  HALF TIME and score in the middle of the picture)
            root.setPos(min(0.97, self.getAspectRatio() - 0.56), 0, 0.0)
        return root

    def _captain(self, match, team):
        """Who wears the armband (the recording doesn't say): a centre-back, else a central midfielder."""
        names = match.get("names", [])[team * 11: team * 11 + 11]
        for want in (("LCB", "CB", "RCB"), ("DM", "LCM", "CM", "RCM")):
            for j, nm in enumerate(names):
                if len(nm) > 1 and nm[1] in want:
                    return j
        return 1

    def _scarves(self, kind):
        """The home crowd's picture with their scarves held up (textures.crowd scarves_up), or None."""
        c = self.__dict__.setdefault("_scarf_tex", {})
        if kind not in c:
            up = kind.replace(".png", "_up.png")
            try:
                if kind in ("crowd_home.png", "crowd_home_live.png"):           # (Kiln Lane: Ashvale's red and white)
                    import textures
                    textures.crowd("crowd_home_up.png", [((200, 40, 45), 6), ((235, 235, 235), 2), ((30, 30, 34), 2)],
                                   seed=1, scarves_up=True)
                    up = "crowd_home_up.png"
                c[kind] = self.stadium.T(up) if os.path.exists(T + up) else None
            except Exception as e:
                print("scarves:", e)
                c[kind] = None
        return c[kind]

    def _big_screen(self):
        """The ground's big screen, up in a corner on its frame, with the score and the minute on it (a ground
        that has its own - grounds.py, from its profile - gets the score on that one)."""
        own = self.stadium.root.find("**/screen")
        if not own.isEmpty():
            tn = TextNode("screen text")
            tn.setAlign(TextNode.ACenter)
            tn.setTextColor(1.0, 0.92, 0.55, 1)
            t = own.attachNewNode(tn)
            t.setPos(0, -0.8, 13.6)
            t.setScale(2.0)
            t.setShaderOff(1); t.setLightOff(1)
            no_shadow(t, lit=False)
            self.screen_text = tn
            return
        root = self.render.attachNewNode("big screen")
        root.setPos(-(HX + 4.5), HY + 4.5, 0.0)
        root.lookAt(0, 0, 0)
        root.setH(root.getH() + 180)                            # (its face to the pitch)
        root.setP(0); root.setR(0)
        cm = CardMaker("screen frame"); cm.setFrame(-4.2, 4.2, 5.2, 9.6)
        fr = root.attachNewNode(cm.generate()); fr.setColor(0.08, 0.08, 0.09, 1); fr.setTwoSided(True)
        for x in (-3.0, 3.0):                                   # (its two legs)
            cm2 = CardMaker("leg"); cm2.setFrame(x - 0.16, x + 0.16, 0.0, 5.2)
            leg = root.attachNewNode(cm2.generate()); leg.setColor(0.25, 0.25, 0.27, 1); leg.setTwoSided(True)
        tn = TextNode("screen text")
        tn.setAlign(TextNode.ACenter)
        tn.setTextColor(1.0, 0.92, 0.55, 1)
        tn.setText("")
        t = root.attachNewNode(tn)
        t.setPos(0, -0.06, 7.7)
        t.setScale(1.3)
        t.setShaderOff(1); t.setLightOff(1)
        self.screen_text = tn
        no_shadow(t, lit=False)

    def _swipe(self, replaying):
        """Into and out of a replay, as TV does: a band in the home colours with the crest sweeps across."""
        import time as _t
        if not hasattr(self, "_sw"):
            from direct.gui.DirectGui import DirectFrame
            col = C(self.kits[0]["shirt"])
            band = DirectFrame(frameColor=col, frameSize=(-0.55, 0.55, -1.2, 1.2), pos=(-3, 0, 0))
            DirectFrame(parent=band, frameColor=C(self.kits[0].get("trim", (240, 240, 240))),
                        frameSize=(0.5, 0.55, -1.2, 1.2))
            if self.home_info.get("crest"):
                img = OnscreenImage(parent=band, image=self.loader.loadTexture(
                    Filename.fromOsSpecific(self.home_info["crest"])), scale=(0.28, 1, 0.3))
                img.setTransparency(TransparencyAttrib.MAlpha)
            band.setBin("fixed", 100)
            band.hide()
            self._sw = {"band": band, "was": replaying, "t0": None}
        sw = self._sw
        if replaying != sw["was"]:
            sw["was"] = replaying
            sw["t0"] = _t.perf_counter()
        if sw["t0"] is None:
            return
        u = (_t.perf_counter() - sw["t0"]) / 0.55
        if u >= 1.0:
            sw["t0"] = None
            sw["band"].hide()
            return
        sw["band"].show()
        sw["band"].setX(-2.6 + 5.2 * u)

    def make_rain(self, snow=False):
        """Rain over the picture: two layers of streaks drifting down at different speeds (near and far).
        snow=True: soft flakes instead, falling slowly and drifting sideways."""
        from panda3d.core import TextureStage
        if snow:
            if not os.path.exists(T + "snow.png"):
                from PIL import Image, ImageDraw, ImageFilter
                import random as _r
                rnd = _r.Random(7)
                im = Image.new("RGBA", (512, 512), (255, 255, 255, 0))
                dr = ImageDraw.Draw(im)
                for _ in range(420):
                    x, y, r = rnd.uniform(0, 512), rnd.uniform(0, 512), rnd.choice((1.2, 1.6, 2.2, 3.0))
                    dr.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rnd.randint(150, 240)))
                im.filter(ImageFilter.GaussianBlur(0.8)).save(T + "snow.png")
            tex = self.loader.loadTexture(pf(T + "snow.png"))
        else:
            tex = self.loader.loadTexture(pf(T + "rain.png"))
        tex.setWrapU(Texture.WM_repeat); tex.setWrapV(Texture.WM_repeat)
        self.rain = []
        layers = ((1.0, 0.55, 1.9), (2.2, 0.35, 1.1)) if not snow else ((1.0, 0.9, 0.22), (2.0, 0.7, 0.12))
        self.snow_on = snow
        for scale, alpha, speed in layers:
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
            self.cap_club = DirectFrame(parent=self.cap, frameColor=(1, 1, 1, 1), frameSize=(0.72, 0.75, -0.075, 0.075))
            self.cap.hide()
        k = fr.get("k", 0)
        if getattr(self, "replay", None):                  # (no captions over a replay)
            self.cap.hide()
            return
        extra = getattr(self, "extra_caption", None)       # (live.py: a sub, the attendance, man of the match)
        if card and 0 <= card[1] < len(self.m.get("names", [])):
            nm = self.m["names"][card[1]][0]
            short = (nm.split()[0][0] + ". " + nm.split()[-1]) if " " in nm else nm
            team = 0 if card[1] < 11 else 1
            red = card[0] in ("red", "second_yellow")
            self.cap_bar["frameColor"] = (0.85, 0.1, 0.1, 1) if red else (0.98, 0.85, 0.1, 1)
            self.cap_t.setText("")
            word = "RED CARD" if red else "BOOKED"
            self.cap_n.setText(f"{word}   {short}   {self.home_name if team == 0 else self.away_name}")
            self.cap_club["frameColor"] = C(self.kits[team]["shirt"])           # (the club's colour, at the end)
            self.cap.show()
            return
        if cel and k - self._restart_id(k) < 30 * 9:                        # (the first 9 seconds of it)
            team, scorer = cel
            names = self.m.get("names", [])
            nm = names[scorer][0] if scorer < len(names) else ""
            short = (nm.split()[0][0] + ". " + nm.split()[-1]) if nm and " " in nm else nm
            club = self.home_name if team == 0 else self.away_name
            mins = fr.get("m") or int(fr["t"] / 600.0 * 45) + 1           # (live: the engine's own minute)
            kit = self.kits[team]
            bar = kit["shirt"] if sum(kit["shirt"]) / 765 > 0.2 else kit.get("trim", (240, 240, 240))
            self.cap_bar["frameColor"] = C(bar)
            self.cap_t.setText("GOAL")
            lum = sum(bar) / 765
            self.cap_t["fg"] = (0.06, 0.07, 0.09, 1) if lum > 0.5 else (1, 1, 1, 1)
            sc = fr.get("s", [0, 0])
            self.cap_n.setText(f"{short}  {mins}'      {club}      {self.labels[0]} {sc[0]}-{sc[1]} {self.labels[1]}")
            self.cap_club["frameColor"] = C(kit["shirt"])
            self.cap.show()
        elif extra:
            word, text, col = extra
            self.cap_bar["frameColor"] = C(col)
            self.cap_t.setText("")
            self.cap_n.setText(f"{word}   {text}")
            self.cap_club["frameColor"] = C(col)
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
            fans = {"crowd_home.png": 0, "crowd_home_live.png": 0, "crowd_hosts.png": 0, "crowd_away.png": 1, "crowd_visitors.png": 1}.get(kind, -1)
            ooh = getattr(self, "_ooh", None)                               # (a shot that just missed: up they get)
            near = ooh is not None and 0 <= k - ooh[1] < 45 and fans == ooh[0]
            want = (4.0 if near else 1.0) if not cel else (7.0 if fans == cel[0] else 0.4 if fans >= 0 else 3.0)
            if fans == 0:                                                   # (the home fans: scarves up for the
                up = k < 600 or (cel is not None and cel[0] == 0)           #  kick-off, and after a home goal)
                ups = self.__dict__.setdefault("_ups", {})
                if up != ups.get(n, False):
                    tx = self._scarves(kind) if up else self.stadium.T(kind)
                    if tx is not None:
                        cn.setTexture(tx, 1)
                    ups[n] = up
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
            if fr.get("st") == "full_time" and act and not getattr(self, "replay", None):
                # Full time: they walk in towards the centre circle, the winners happy, the losers heads down
                # (a draw: neither) - as they come together to shake hands
                ft = self.__dict__.setdefault("_ft", {})
                if i not in ft:
                    a = 2 * math.pi * ((i % 11) + (0.5 if i >= 11 else 0.0)) / 11.0
                    ft[i] = [wx, wy, math.cos(a) * 8.5, math.sin(a) * 6.5]
                w = ft[i]
                dx, dy = w[2] - w[0], w[3] - w[1]
                dd = math.hypot(dx, dy)
                if dd > 0.4:
                    step = min(dd, 1.4 * dt)
                    w[0] += dx / dd * step; w[1] += dy / dd * step
                    fx, fy, sp = dx / dd, -dy / dd, 14.0
                else:
                    fx, fy, sp = -w[0] / max(0.1, math.hypot(w[0], w[1])), w[1] / max(0.1, math.hypot(w[0], w[1])), 0.0
                    opp = [(math.hypot(q[0] - w[0], q[1] - w[1]), q) for j, q in ft.items() if (j < 11) != (i < 11)]
                    near = min(opp, default=None, key=lambda e: e[0])
                    if near is not None and near[0] < 3.2:                   # (shaking hands with the man next
                        q = near[1]                                          #  to him)
                        dd2 = max(0.1, near[0])
                        fx, fy = (q[0] - w[0]) / dd2, -(q[1] - w[1]) / dd2
                        self.__dict__.setdefault("_shake", {})[i] = True
                wx, wy = w[0], w[1]
                s0, s1 = fr["s"]
                won = (s0 > s1 and i < 11) or (s1 > s0 and i >= 11)
                lost = (s0 > s1 and i >= 11) or (s1 > s0 and i < 11)
                p.mood = "joy" if won else "sad" if lost else None
            elif fr.get("st") != "full_time":
                self.__dict__.pop("_ft", None) if i == 0 else None
            if not act:                                                     # (sent off: the engine takes him
                was = self.__dict__.setdefault("_was_on", {})               #  straight off; on TV he walks off,
                off = self.__dict__.setdefault("_walk_off", {})             #  head down, to the tunnel)
                if i not in off and was.get(i, False) and not getattr(self, "replay", None) and i in prev:
                    off[i] = [prev[i][0], prev[i][1], 0.0]
                w = off.get(i)
                if w is not None and w[2] < 22.0 and not getattr(self, "replay", None):
                    dx, dy = 0.0 - w[0], -HY - 4.0 - w[1]
                    dd = math.hypot(dx, dy)
                    if dd > 0.3:
                        w[0] += dx / dd * min(dd, 1.5 * dt); w[1] += dy / dd * min(dd, 1.5 * dt)
                        fx, fy = dx / dd, -dy / dd
                    w[2] += dt
                    wx, wy, sp, act = w[0], w[1], 15.0 if dd > 0.3 else 0.0, 1
            self.__dict__.setdefault("_was_on", {})[i] = bool(fr["p"][i][6])
            wx, wy, sp2 = self._gather(i, fr, cel, wx, wy, dt)                  # (team-mates mob the scorer)
            if sp2 is not None:
                sp = sp2
            dn = self._down(i, fr, k, wx, wy, fx, fy)                           # (fouled: he stays where he fell)
            if dn is not None:
                wx, wy, fx, fy, sp = dn
            arr = getattr(self, "_arriving", {}).get(i)                        # (a substitute jogging on)
            if arr is not None:
                dx, dy = wx - arr[0], wy - arr[1]
                dd = math.hypot(dx, dy)
                arr[2] += dt
                if dd < 0.4 or arr[2] > 15.0:
                    del self._arriving[i]
                else:
                    jog = arr[3] if len(arr) > 3 else SUB_JOG
                    if len(arr) > 3 and not fr.get("r"):                        # (play's going on: he hurries)
                        jog = max(jog, DOWN_HURRY)
                    stp = min(dd, jog * dt)
                    arr[0] += dx / dd * stp; arr[1] += dy / dd * stp
                    wx, wy, sp = arr[0], arr[1], jog * 10.0
                    fx, fy = dx / dd, -dy / dd
            lie = self._lier(fr, k)                                              # (behind the wall, lying down)
            if lie is not None and lie[0] == i:
                wx, wy, sp = lie[1][0], lie[1][1], 0.0
            hb = self._handbags(i, fr, wx, wy, dt, k)                            # (a bad foul: handbags)
            if hb is not None:
                wx, wy, sp2, hb_kind = hb
                sp = sp2 if sp2 is not None else sp
            wx, wy, fx, fy, sp, sp_pose = self._run_up(i, fr, wx, wy, fx, fy, sp, k, dt)   # (set pieces)
            px, py = prev.get(i, (wx, wy))
            vel = ((wx - px) / max(dt, 1e-3), (wy - py) / max(dt, 1e-3))
            prev[i] = (wx, wy)
            if sp2 is not None and math.hypot(*vel) > 0.3:
                fx, fy = vel[0] / math.hypot(*vel), -vel[1] / math.hypot(*vel)
            p.calling = self._calling(i, fr, wx, wy, sp, k)
            p.late = fr.get("st") in ("second_half", "et_second_half")         # (tired: hands on hips more)
            r_ = fr.get("r")                                                     # (late on, at a dead ball: some
            p.force_stand = ("knees" if r_ and r_[0] != "kick_off" and (fr.get("m") or 0) >= LATE_KNEES_FROM  #  stand
                             and i != r_[1] and not getattr(p, "keeper", False) and (i * 5) % 4 == 0      #  hands
                             and math.hypot(wx - rbx, wy - rby) > 12.0 else None)                   #  on knees)
            p.wide = fr["o"] == i and sp > 55                                    # (on the ball at speed)
            o_ = fr["o"]                                                         # (defending close to the ball in
            p.defending = (not fr.get("r") and o_ >= 0 and (o_ < 11) != (i < 11)  #  open play: side-steps and
                           and math.hypot(wx - rbx, wy - rby) < 15.0)            #  backing off are right)
            p.scan = self._scan(i, k)                                           # (a look over his shoulder)
            kind, t = self.events.action(i, k)
            p.mx_var = self.events.variant(i) if kind is not None else None
            p.mx_place = self._placing(i, fr, wx, wy, rbx, rby, sp, dt) if getattr(p, "keeper", False) else None
            if kind is None and sp_pose is not None:
                kind, t = sp_pose
            if kind is None and getattr(self, "_shake", {}).get(i) and fr.get("st") == "full_time":
                kind, t = "shake", ((k + i * 17) % 120) / 30.0 - 0.3
            if kind in ("shot", "finish", "dink") and 0.0 <= t < 0.1 and not cel:
                self._ooh = (0 if i < 11 else 1, k)
            if cel and i == cel[1]:
                kind, t = self._scorer_slide(i, sp, k, kind, t)
            card = fr.get("card")
            if card and card[1] == i and kind is None and sp < 25:
                kind, t = "protest", 0.5
            if kind == "despair" and sp > 30:                               # (not while he's still running hard)
                kind = None
            if kind == "throwin":                                           # (facing the way he throws it)
                fx, fy = self._throw_dir(i, k, t, fx, fy)
                wy = self._throw_spot(wy, t)                                # (feet on or behind the line)
            p.update(wx, wy, fx, -fy, sp, dt, act, vel=vel, ball=(rbx, rby))
            dv = fr["p"][i][7] if len(fr["p"][i]) > 7 else ""
            if dv in ("diving", "down", "recover") and getattr(p, "keeper", False):    # (a keeper's dive)
                self._keeper_dive(i, p, dv, k)
                continue
            if kind == "smother" and getattr(p, "keeper", False):              # (down at a man's feet)
                self._smother(i, p, t, k)
                continue
            if lie is not None and lie[0] == i:                                  # (lying behind the wall)
                p.lie(1)
                p.h = lie[2]
                p.root.setPos(p.root.getX(), p.root.getY(), p.lift)
                p.root.setHpr(p.h, 0, p.roll * p.roll_side)
                continue
            if kind is None and fr["o"] == i and sp < 22:                   # (on the ball, a man tight on him:
                near = self._shield_side(i, fr, wx, wy, fx, -fy)              #  he shields it)
                if near:
                    kind, t = "shield", 0.5
                    self._shield_left[i] = near > 0           # (the pose has the man on his left)
            if kind is None and fr["o"] == i:
                kind, t = self._dragback(i, p, fr, fx, fy, k)                    # (turning back with it)
            if kind is None and fr["o"] == i:
                kind, t = self._stepover(i, p, fr, fx, fy, k)                    # (a man in front: a trick)
            if kind is None and fr["o"] == i:
                kind, t = self._dribble_touch(i, p, dt)
            r = fr.get("r")
            if kind is None and r and r[0] == "free_kick" and 0 <= r[1] < len(fr["p"]) and sp < 15 \
                    and (i < 11) != (r[1] < 11) and not getattr(p, "keeper", False):
                if 8.0 < math.hypot(wx - rbx, wy - rby) < 11.5:                 # (in the wall)
                    kind, t = "wall", 0.5
                    self.__dict__.setdefault("_wall", {})[i] = k
            if kind is None and r and r[0] in ("free_kick", "offside", "penalty") and 0 <= r[1] < len(fr["p"]) \
                    and not getattr(p, "keeper", False) and sp < 40:
                kind, t = self._appeal(i, fr, wx, wy, rbx, rby, r, k)            # (claiming it / it's ours, ref)
            if kind is None and not getattr(p, "keeper", False):
                kind, t = self._contact(i, p, fr, wx, wy, fx, fy, sp, r)        # (jockeying, tugging, barging)
            else:
                p.barge = 0.0
            if kind is None and getattr(p, "keeper", False) and fr["o"] == i and fr.get("gf") != i:   # (in his hands)
                kind, t = "cradle", 0.5
            if kind is None and getattr(p, "keeper", False) and r and r[0] == "free_kick" and (i < 11) != (r[1] < 11):
                gx = -HX if i < 11 else HX                                          # (a free kick near his goal:
                if math.hypot(rbx - gx, rby) < 32:                                   #  setting up the wall)
                    kind, t = "point", (k % 150) / 30.0 - 0.4
                    if t > 1.6:
                        kind = None
            if kind is None and getattr(p, "keeper", False) and r and r[0] == "penalty" \
                    and 0 <= r[1] < len(fr["p"]) and (i < 11) != (r[1] < 11):
                kind, t = "penwait", ((k - self._restart_id(k)) / 30.0) % 1.6    # (on his line: arms out, swaying)
            if kind is None and r and r[0] == "offside" and 0 <= r[1] < len(fr["p"]) and (i < 11) != (r[1] < 11) \
                    and i == self._offside_man(fr, r, k):
                t0 = (k - self._restart_id(k)) / 30.0                              # (the man caught offside: arms out,
                if t0 < 1.8:                                                       #  "never!")
                    kind, t = "protest", 0.5
            if kind is None and getattr(p, "keeper", False) and sp < 25:          # (a keeper, set for a shot)
                gx = -HX if wx < 0 else HX
                if math.hypot(rbx - gx, rby) < 30 and fr["o"] not in (range(0, 11) if i < 11 else range(11, 22)):
                    kind, t = "ready", 0.0
            if kind is None and not getattr(p, "keeper", False):              # (the back line stepping up:
                su = self._stepping_up(fr, k)                                  #  the centre-back calls them
                if su.get(i) is not None:                                      #  out, pointing up the pitch)
                    kind, t = "point", su[i]
            hbk = getattr(self, "_hb_kind", {}).get(i)
            if hbk is not None and kind in (None, "protest"):
                kind, t = hbk
            p.act(kind, t, self._left_foot(i, p, kind, t, k))
        self._prev_pos = prev
        self._walk_offs(dt, rbx, rby)
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
        # The TV camera: it pans with the play, a little ahead of the ball the way it's going (as a TV director
        # does, leaving space in front of the attack), on a smooth spring - no jerks when the ball's hit - and
        # zooms out a touch when the ball's travelling fast or play's spread, in when it's tight.  After a
        # goal it finds the scorer and moves in on him.
        if not all(math.isfinite(q) for q in (getattr(self, "cx", 0.0), getattr(self, "cy", 0.0),
                                              getattr(self, "cam_fov", 36.0), getattr(self, "cam_tilt", 0.0))):
            self.cx, self.cy, self.cam_fov, self.cam_tilt = bx, by, 36.0, 0.0       # (never lose the camera)
            self.cam_v = [0.0, 0.0]
        if fr.get("st") in ("halftime", "full_time", "et_break", "et_halftime"):
            self._cam_tv(fr, 0.0, 0.0, dt)                                   # (a break: the whole pitch, not the ball)
        else:
            self._cam_tv(fr, bx, by, dt)
        orbit = getattr(self, "orbit", None)
        intro = getattr(self, "intro", None)
        if intro is not None and intro < 1.0:                               # (kick-off: down from the sky outside
            u = intro * intro * (3 - 2 * intro)                             #  the ground to the TV gantry)
            a = math.radians(135 + 135 * u)                                 # (round from the far corner,
            R = 150 - (150 - (HY + 62)) * u                                 #  high over the roofs, to the
            px_, py_, pz_ = R * math.cos(a), R * math.sin(a), 120 - 87 * u  #  gantry)
            px_ += self.cx * 0.8 * u
            self.cam.setPos(px_, py_, pz_)
            self.cam.lookAt(self.cx * u, (self.cy * 0.35 + 9) * u, 0.0)
            self.camLens.setFov(34 + 10 * (1 - u))
        elif fr.get("st") in ("halftime", "full_time", "et_break", "et_halftime") and \
                getattr(self, "break_a", None) is not None and getattr(self, "cam_mode", 0) == 0 and not CLOSE:
            a = self.break_a                                                # (a break: slowly round the ground,
            self.cam.setPos(118 * math.cos(a), 118 * math.sin(a), 52)       #  high up)
            self.cam.lookAt(0, 0, 0)
            self.camLens.setFov(42)
        elif orbit is not None and not getattr(self, "replay", None):         # (paused: the camera circles the ball)
            ox, oy = max(-HX + 2, min(HX - 2, bx)), max(-HY + 2, min(HY - 2, by))
            self.cam.setPos(ox + 15.0 * math.cos(orbit), oy + 15.0 * math.sin(orbit), 5.5)
            self.cam.lookAt(ox, oy, 0.8)
            self.camLens.setFov(45)
        elif "--top" in sys.argv:                                             # (a check: the whole ground from above)
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
                zf = float(os.environ.get("FM3D_FOLLOW_ZOOM", "1"))    # (a check: closer in, e.g. 0.5)
                self.cam.setPos(fx_ + sx * 9 * zf, (fy_ - 7 * zf) if fy_ > -HY + 1 else (fy_ + 9 * zf), 0.8 + 2.4 * zf)
            self.cam.lookAt(fx_, fy_, 0.8)
        elif getattr(self, "replay", None):                                 # (a replay: see _replay_cam)
            self._replay_cam(bx, by, bz, dt)
        elif fr.get("st") == "penalties" and not CLOSE and getattr(self, "cam_mode", 0) == 0:
            self._pens_cam(bx, by, dt)                                      # (a shoot-out: behind the taker)
        elif CLOSE or getattr(self, "cam_mode", 0) == 1:                    # (a close camera, for checking)
            self.cam.setPos(bx - 6, by - 14, 4.5)
            self.cam.lookAt(bx, by, 0.9)
        else:
            self.cam.setPos(self.cx * 0.8, -HY - 62, 33)
            yw = 0.35 + 0.6 * self.cam_tilt                                 # (close in: right on him)
            ht = getattr(self, "_flag_t", 0.0)                              # (close in, a cameraman's hand: the
            hx = self.cam_tilt * (0.22 * math.sin(ht * 0.71) + 0.09 * math.sin(ht * 1.93))   # picture drifts a
            hz = self.cam_tilt * (0.12 * math.sin(ht * 0.53 + 1.0) + 0.05 * math.sin(ht * 2.3))  # touch)
            self.cam.lookAt(self.cx + hx, self.cy * yw + 9 * (1 - self.cam_tilt), 0.8 * self.cam_tilt + hz)
            self.camLens.setFov(self.cam_fov)
            sp = self._set_piece_cam(fr, bx, by, dt)                        # (a free kick near the box, a corner:
            if sp is not None:                                              #  cut to a closer camera, as TV does)
                (px_, py_, pz_), (lx_, ly_, lz_), f_ = sp
                self.cam.setPos(px_, py_, pz_)
                self.cam.lookAt(lx_, ly_, lz_)
                self.camLens.setFov(f_)
        # A close-up from the gantry (a scorer by the near corner flag, say): the near side of the ground would
        # be in the way - leave it out of the picture while it is
        tv = not getattr(self, "replay", None) and not CLOSE and getattr(self, "cam_mode", 0) == 0 \
            and FOLLOW is None and "--top" not in sys.argv
        self.stadium.root.setShaderInput("clip_y", (-HY - 7.5) if tv and getattr(self, "cam_tilt", 0.0) > 0.4 else -1.0e6)
        if not hasattr(self, "rp_t"):
            self.rp_t = OnscreenText(text="REPLAY", pos=(1.15, 0.88), scale=0.07, fg=(1, 1, 1, 1),
                                     shadow=(0, 0, 0, 0.8), align=TextNode.ARight, mayChange=False)
        if getattr(self, "replay", None):
            self.rp_t.show()
        else:
            self.rp_t.hide()
        self._swipe(bool(getattr(self, "replay", None)))
        gone = fr["m"] / 90.0 if fr.get("m") else fr["t"] / 1200.0         # (how far into the match)
        self.render.setShaderInput("sweat", min(1.0, 0.25 + gone * 0.6 + (0.3 if RAIN else 0.0)))
        if DUSK and getattr(self, "_day_lights", None):                     # (dusk: from about 40 minutes the
            dk = max(0.0, min(1.0, (gone - 0.45) / 0.55))                   #  daylight goes, the floodlights
            f = 1.0 - 0.38 * dk                                             #  take over)
            al, ac, dl, dc = self._day_lights
            al.setColor(Vec4(ac[0] * f, ac[1] * f, ac[2] * (f + 0.04 * dk), 1))
            dl.setColor(Vec4(dc[0] * f, dc[1] * f, dc[2] * f, 1))
            bg = (0.55, 0.58, 0.62) if RAIN else (0.62, 0.66, 0.7)
            self.setBackgroundColor(bg[0] * f * 0.9, bg[1] * f * 0.92, bg[2] * f, 1)
            if self.render.hasFog():
                self.render.getFog().setColor(bg[0] * f * 0.9, bg[1] * f * 0.92, bg[2] * f)
        if RAIN:                                                            # (a wet day: the pitch cuts up,
            self.render.setShaderInput("pitch_churn", min(1.0, 0.25 + gone * 0.75))     # and the kits get
            self.render.setShaderInput("mud_amt", min(1.0, 0.3 + gone * 0.7))          # muddier as it goes on)
        s = fr["s"]
        self.score_t.setText(f"{self.labels[0]}  {s[0]} - {s[1]}  {self.labels[1]}")
        if getattr(self, "screen_text", None) is not None:                 # (the big screen in the corner)
            mins = fr.get("m") or int(fr["t"] / 600.0 * 45) + 1
            txt = f"{self.labels[0]} {s[0]}-{s[1]} {self.labels[1]}\n{mins}'"
            if txt != getattr(self, "_screen_was", None):
                self.screen_text.setText(txt)
                self._screen_was = txt
        self._goal_caption(fr)
        if RAIN or SNOW:
            self.rain_t += dt
            from panda3d.core import TextureStage
            for n, speed in self.rain:
                side = (0.06 * self.rain_t * speed) if not SNOW else 0.15 * math.sin(self.rain_t * 0.4 + speed * 9) * speed
                n.setTexOffset(TextureStage.getDefault(), side, self.rain_t * speed)
        mins = int(fr["t"] / 600.0 * 45)
        self.clock_t.setText(f"{mins:02d}:{int((fr['t'] / 600.0 * 45 * 60) % 60):02d}")


def _viewer_replay_cam(self, bx, by, bz, dt):
    """The replay camera.  From the middle: behind the goal, up on a gantry over the crowd, looking back down
    the pitch at the shooter.  From wide: side-on, a camera on the near touchline level with the edge of the
    box, panning with the ball (a long lens, so the players fill the picture)."""
    sd = self.replay
    kind = getattr(self, "replay_kind", "goal")
    rc = getattr(self, "_rp_cam", None)
    if rc is None:                                     # (start where the ball is: no swing in from the last shot)
        rc = self._rp_cam = [bx, by]
    k = min(1.0, dt * (2.2 if kind == "side" else 3.0))
    rc[0] += (bx - rc[0]) * k
    rc[1] += (by - rc[1]) * k
    if kind == "side":
        # level with the 18-yard line on the near side, 7 m up (a TV platform at the front of the stand)
        cx = sd * (HX - 16.5)
        self.cam.setPos(cx, -HY - 9.0, 7.0)
        tx = rc[0] * 0.75 + sd * (HX - 6.0) * 0.25          # (lean towards the goal: the finish is the point)
        ty = rc[1]
        self.cam.lookAt(tx, ty, 0.9 + min(2.0, bz * 0.3))
        dist = math.hypot(tx - cx, ty + HY + 9.0)
        self.camLens.setFov(max(26.0, min(48.0, 2 * math.degrees(math.atan2(14.0, dist)))))   # (~28 m of pitch across)
    else:
        self.cam.setPos(sd * (HX + 6.0), rc[1] * 0.4, 9.0)
        self.cam.lookAt(sd * (HX - 9), rc[1] * 0.6, 0.0)
        self.camLens.setFov(62)


Viewer._replay_cam = _viewer_replay_cam


def _viewer_pens_cam(self, bx, by, dt):
    """A penalty shoot-out: the camera behind the taker, low, looking down the line of the kick at the keeper
    and the goal - the shot every TV shoot-out lives on.  The spot's 11 m out (Law 14); the camera 15 m behind
    it, a little off the middle and 3.2 m up on a platform, so the taker, the ball on the spot, the keeper and the
    whole goal are in the picture (the goal about two-thirds of its width)."""
    sd = 1 if bx > 0 else -1                            # (the end they're shooting at: the ball's always in that half)
    self._pen_t = getattr(self, "_pen_t", 0.0) + dt
    t = self._pen_t
    sway = (0.06 * math.sin(t * 0.7), 0.04 * math.sin(t * 0.53 + 1.0))   # (a hand on the camera: it breathes a little)
    spot = sd * (HX - 11.0)
    self.cam.setPos(spot - sd * 15.0, -1.2 + sway[0], 3.2 + sway[1])
    self.cam.lookAt(sd * (HX - 4.0), 0.0, 0.2)       # (the spot low in the picture, the bar near the top)
    self.camLens.setFov(30)


Viewer._pens_cam = _viewer_pens_cam


def _viewer_set_piece_cam(self, fr, bx, by, dt):
    """A free kick within shooting range: behind the taker, looking over the wall at the goal.  A corner: high
    over the corner of the pitch, looking across the box.  The TV director cuts to it while the kick's set up and
    holds it a moment after (the ball on its way), then cuts back to the gantry.  -> (pos, look at, fov) or None"""
    r = fr.get("r")
    st = getattr(self, "_sp", None)
    if r and r[0] in ("free_kick", "corner") and not fr.get("c"):
        if st is None or st["kind"] != r[0] or st.get("done"):
            sx = 1 if bx > 0 else -1
            gx = sx * HX
            if r[0] == "corner":
                sy = 1 if by > 0 else -1
                st = {"kind": "corner", "t": 0.0, "after": 0.0,
                      "pos": (sx * (HX - 1.5), sy * (HY - 1.5), 9.0), "look": (sx * (HX - 13.0), -sy * 2.0, 0.0),
                      "fov": 40.0}
            else:
                d = math.hypot(gx - bx, by)
                if d > 32.0 or d < 9.0:
                    self._sp = None
                    return None
                ux, uy = (bx - gx) / d, by / d
                px_ = max(-HX + 0.5, min(HX - 0.5, bx + ux * 8.5))
                py_ = max(-HY + 0.5, min(HY - 0.5, by + uy * 8.5))
                st = {"kind": "free_kick", "t": 0.0, "after": 0.0, "pos": (px_, py_, 2.6),
                      "look": (gx, 0.0, 1.1), "fov": 42.0}
            self._sp = st
        st["t"] += dt
        return (st["pos"], st["look"], st["fov"]) if st["t"] > 1.2 else None
    if st is not None and not st.get("done"):
        if st["t"] > 1.2 and st["after"] < 0.8 and not fr.get("c"):       # (the kick's taken: a moment more)
            st["after"] += dt
            return st["pos"], st["look"], st["fov"]
        st["done"] = True
    return None


TV_FOV = 30.0       # degrees: the TV camera's picture (was 34: a touch closer in - the players bigger, easier to
TV_WIDER = 4.5      #  follow), and up to this much wider while the ball's flying about


def _viewer_cam_tv(self, fr, bx, by, dt):
    """Where the TV camera points (self.cx, self.cy) and how wide (self.cam_fov)."""
    if not hasattr(self, "cam_v"):
        self.cam_v = [0.0, 0.0]
        self.cam_fov, self.cam_tilt = 36.0, 0.0
        self.bv = [0.0, 0.0]
        self.prev_b = (bx, by)
    dt = max(dt, 1e-3)
    vx, vy = (bx - self.prev_b[0]) / dt, (by - self.prev_b[1]) / dt
    self.prev_b = (bx, by)
    if abs(vx) > 60 or abs(vy) > 60:                    # (a jump: the ball put back on the spot)
        vx = vy = 0.0
    k = min(1.0, dt * 1.5)
    self.bv = [self.bv[0] + (vx - self.bv[0]) * k, self.bv[1] + (vy - self.bv[1]) * k]
    tx = bx + max(-9.0, min(9.0, self.bv[0] * 0.7))     # (a little ahead of the play)
    ty = by + max(-5.0, min(5.0, self.bv[1] * 0.4))
    fov = TV_FOV + min(TV_WIDER, math.hypot(*self.bv) * 0.35)  # (wider while the ball's flying about)
    tilt = 0.0
    cel = fr.get("c")
    r = fr.get("r")
    if r and r[0] != "offside" and 0 <= r[1] < len(fr["p"]) and not cel:
        self.r_t = getattr(self, "r_t", 0.0) + dt         # (a dead ball: a close look at the taker as he
    else:                                               #  sets it up, then back out before he takes it)
        self.r_t = 0.0
    if 0.5 < self.r_t < 3.0 and to_world(fr["p"][r[1]][0], fr["p"][r[1]][1])[1] > -HY + 10:
        tx, ty = to_world(fr["p"][r[1]][0], fr["p"][r[1]][1])          # (not right under the gantry: the
        fov, tilt = 21.0, 1.0                                           #  dugout roofs are in the way)
    if cel and 0 <= cel[1] < len(fr["p"]):              # (a goal: on to the scorer, closer)
        sx_, sy_ = to_world(fr["p"][cel[1]][0], fr["p"][cel[1]][1])
        tx, ty, fov, tilt = sx_, sy_, 17.0, 1.0
    tx = max(-36.0, min(36.0, tx)) if not cel else max(-(HX - 2.0), min(HX - 2.0, tx))   # (a scorer by the corner flag: right on him)
    # a critically damped spring: smooth to start and to stop
    w = 1.7
    n = max(1, int(math.ceil(dt / 0.05)))               # (in small steps, however long the frame: steady)
    for i, t in ((0, tx), (1, ty)):
        c = self.cx if i == 0 else self.cy
        for _ in range(n):
            a = (t - c) * w * w - 2 * w * self.cam_v[i]
            self.cam_v[i] += a * dt / n
            c += self.cam_v[i] * dt / n
        if i == 0:
            self.cx = c
        else:
            self.cy = c
    self.cam_fov += (fov - self.cam_fov) * min(1.0, dt * (1.3 if cel or 0.5 < self.r_t < 3.0 else 0.9))
    self.cam_tilt += (tilt - self.cam_tilt) * min(1.0, dt * 1.2)


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
        if pos.z < BALL_R + 0.01:                                           # (rolling on the grass: it slows
            f = math.exp(-2.0 * st)                                         #  and stops, in the net)
            vel.x *= f; vel.y *= f
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
        lat = 0.09                                                          # (a touch to his right)
        if (kind in KICKS or kind in SHOTS) and t < 0:                     # (setting it up for the kick)
            dist = 0.38 + (dist - 0.38) * min(1.0, -t / 0.3)
            if kind in ("backheel", "flick"):                               # (under his heel / by the outside
                u = min(1.0, -t / 0.25)                                     #  of his foot as he plays it)
                sd = -1.0 if self._left_foot(o, p, kind, t, fr.get("k", 0)) else 1.0
                d0, s0 = (-0.10, 0.13) if kind == "backheel" else (0.22, 0.24)
                dist = d0 + (dist - d0) * u
                lat = s0 * sd + (lat - s0 * sd) * u
        px, py = p.root.getX(), p.root.getY()
        bx, by, bz = px + fx * dist + fy * lat, py + fy * dist - fx * lat, BALL_R
        if getattr(p, "keeper", False) and fr.get("gf") != o:               # (a keeper: in his hands - not a
                                                                            #  back-pass, that's at his feet)
            bx, by, bz = p.hand() if (kind == "gkthrow" and t > -0.45) else p.hands()
            gk_ = getattr(self.events, "_gained", {}).get(o)
            held = (fr.get("k", 0) - gk_[0]) / 30.0 if gk_ else 0.0
            if kind in (None, "cradle") and p.sp < 8 and held > BOUNCE_AFTER:  # (waiting for his team to get
                u = ((held - BOUNCE_AFTER) % BOUNCE_EVERY) / BOUNCE_EVERY    #  out: bouncing the ball)
                if u < 0.32:
                    bz = BALL_R + (bz - BALL_R) * abs(_m.cos(_m.pi * u / 0.32))
    r = fr.get("r")
    if r and r[0] == "throw_in" and r[1] >= 0:                              # (a throw-in: in his hands)
        p = self.players[r[1]]
        kind, t = self.events.action(r[1], fr.get("k", 0))
        px, py = p.root.getX(), p.root.getY()
        if kind == "throwin" and t >= -1.5 and _m.hypot(px - bx, py - by) < 2.5:
            bx, by, bz = p.hands()                                          # (between his hands, wherever they are)
            mode = ("throw", r[1])
    # Thrown: the engine rolls a throw-in along the grass from his feet, so here it flies - out of his hands over
    # his head, in an arc, down onto the engine's path (about a 10-15 m throw's flight) - unless someone gets to
    # it first.
    k_now = fr.get("k", 0)
    fl = getattr(self, "_flight", None)
    if isinstance(self.ball_mode, tuple) and self.ball_mode[0] == "throw" and mode != self.ball_mode \
            and self.last_ball is not None and not r:
        fl = self._flight = {"i": self.ball_mode[1], "t": 0.0, "k": k_now, "from": tuple(self.last_ball),
                             "eng": (bx, by)}
    if fl is not None:
        fl["t"] += dt
        u = fl["t"] / self.THROW_FLIGHT
        if u >= 1.0 or r or (o >= 0 and o != fl["i"]) or k_now < fl["k"] - 1:
            self._flight = None                                             # (landed, or taken, or a replay)
        else:
            (hx, hy, hz), (ex, ey) = fl["from"], fl["eng"]
            out = (bx + (hx - ex) * (1 - u), by + (hy - ey) * (1 - u),
                   hz * (1 - u) + BALL_R * u + 4 * self.THROW_ARC * u * (1 - u))
            self.ball_mode, self.ball_off, self.last_ball = ("flight", fl["i"]), Vec3(0, 0, 0), out
            return out
    if mode != self.ball_mode:
        if self.last_ball is not None:
            self.ball_off = Vec3(*self.last_ball) - Vec3(bx, by, bz)        # (ease from where it was drawn)
        # (out of someone's hands - a throw-in, a keeper's throw - it comes down over a longer flight)
        held = isinstance(self.ball_mode, tuple) or (isinstance(self.ball_mode, int) and
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
    if stage == "down":
        stage = "diving"                    # (landed: the dive's last pose - lying there - until he gets up)
    if stage == "recover" and st.get("stage") == "diving" and (k - st["start"]) / 30.0 * st.get("pace", 1.0) < 0.62:
        stage = "diving"                    # (saved in mid-air: he still flies and lands first)
    if st.get("stage") != stage:
        st.update(stage=stage, start=k)
        if stage == "diving":               # (the engine's flight - till he lands - sets the animation's pace:
            e = k                           #  a short dive is quicker than one at full stretch)
            while e + 1 < len(F) and e - k < 30 and (F[e + 1]["p"][i][7] if len(F[e + 1]["p"][i]) > 7 else "") \
                    == "diving":
                e += 1
            fl = (e + 1 - k) / 30.0
            st["pace"] = max(0.85, min(1.8, 0.6 / fl)) if e + 1 < len(F) and fl > 0.15 else 1.0
        if stage == "recover":              # (how long till he's up: the Mixamo keeper gets up in that time)
            e = k
            while e + 1 < len(F) and e - k < 90 and (F[e + 1]["p"][i][7] if len(F[e + 1]["p"][i]) > 7 else "") \
                    == "recover":
                e += 1
            p.mx_up = (e + 1 - k) / 30.0
        if stage == "diving" or "h" not in st:
            st["h"] = p.h or 0.0                                            # (he keeps facing the shot through it)
            a, b = F[k]["p"][i], F[min(len(F) - 1, k + 8)]["p"][i]
            mx, my = to_world(b[0], b[1])
            ox, oy = to_world(a[0], a[1])
            hd = _m.radians(st["h"])
            right = (_m.cos(hd), _m.sin(hd))                               # (his right, facing +Y at h = 0)
            st["side"] = 1 if (mx - ox) * right[0] + (my - oy) * right[1] >= 0 else -1
    p.dive(stage, (k - st["start"]) / 30.0 * (st.get("pace", 1.0) if stage == "diving" else 1.0), st.get("side", 1))
    p.h = st["h"]
    p.root.setPos(p.root.getX(), p.root.getY(), p.lift)
    p.root.setHpr(p.h, 0, p.roll * p.roll_side)


BOUNCE_AFTER = 1.6       # s holding it (standing about): a keeper bounces the ball...
BOUNCE_EVERY = 1.5       # ...once every this many seconds
LATE_KNEES_FROM = 75     # minute: from here, at a dead ball, about a quarter stand bent over, hands on knees
APPEAL_WITHIN = 18.0     # m from the ball: the side given the free kick appeals for it (some of them)...
APPEAL_FOR = 1.45        # s from the whistle


SUB_JOG = 4.0            # m/s: a substitute jogging on to his place
HANDBAGS = (0.3, 3.8)    # s after a booking: team-mates of the man fouled go for the fouler; one of his pulls
HANDBAGS_NEAR = 18.0     # them apart (m: those within this of it)


def _viewer_handbags(self, i, fr, wx, wy, dt, k):
    """A booking (a bad foul): up to two of the fouled side's men within 18 m rush in at the fouler - the nearest
    shoves him - and one of his own team-mates gets between them, arms out; then they drift back to where the
    engine has them.  Drawn only.  -> (x, y, speed or None, (kind, t) or None) or None."""
    hb = self.__dict__.setdefault("_hb", {})
    kinds = self.__dict__.setdefault("_hb_kind", {})
    kinds.pop(i, None)
    card = fr.get("card")
    F = self.m["frames"]
    cur = hb.get(("pos", i))
    target = None
    if card and card[0] in ("yellow", "red", "second_yellow") and 0 <= card[1] < len(fr["p"]):
        cs = k
        while cs > 0 and F[cs - 1].get("card") == card:
            cs -= 1
        t = (k - cs) / 30.0
        plan = hb.get(cs)
        if plan is None:
            f0 = F[cs]["p"]
            f = card[1]
            fx_, fy_ = f0[f][0], f0[f][1]
            near = lambda team: sorted((math.hypot(q[0] - fx_, q[1] - fy_) / 10.0, j) for j, q in enumerate(f0)
                                       if (j < 11) == team and j != f and q[6] and j not in (0, 11))
            theirs = [j for d, j in near(not (f < 11)) if d < HANDBAGS_NEAR][:2]
            ours = [j for d, j in near(f < 11) if d < HANDBAGS_NEAR][:1]
            plan = hb[cs] = {"f": f, "in": theirs, "sep": ours}
        if HANDBAGS[0] <= t <= HANDBAGS[1] and (i in plan["in"] or i in plan["sep"]):
            g = fr["p"][plan["f"]]
            gx, gy = to_world(g[0], g[1])
            if i in plan["in"]:
                n = plan["in"].index(i)
                a = math.atan2(wy - gy, wx - gx) + (0.5 if n else 0.0)
                target = (gx + 0.85 * math.cos(a), gy + 0.85 * math.sin(a))
                if n == 0 and t > 1.0:
                    kinds[i] = ("shove", min(0.8, t - 1.0))
                elif t > 0.9:
                    kinds[i] = ("protest", 0.5)
            else:
                a = math.atan2(wy - gy, wx - gx)
                target = (gx + 0.6 * math.cos(a), gy + 0.6 * math.sin(a))
                if t > 0.8:
                    kinds[i] = ("separate", min(2.2, t - 0.8))
    if target is None:
        if cur is None:
            return None
        target = (wx, wy)
        if math.hypot(cur[0] - wx, cur[1] - wy) < 0.3:
            del hb[("pos", i)]
            return None
    if cur is None:
        cur = (wx, wy)
    dx, dy = target[0] - cur[0], target[1] - cur[1]
    d = math.hypot(dx, dy)
    v = min(6.5, d * 2.5)
    step = min(d, v * dt)
    if d > 1e-6:
        cur = (cur[0] + dx / d * step, cur[1] + dy / d * step)
    hb[("pos", i)] = cur
    return cur[0], cur[1], v * 10.0, kinds.get(i)


STEP_UP_SPEED = 2.5      # m/s: the whole back four moving up the pitch at least this fast...
STEP_UP_GAP = 20.0       # s: (once in this long, per team)


def _viewer_stepping_up(self, fr, k):
    """The back four pushing up together (after the ball's cleared): the most central of them points up the
    pitch, calling them out, for a second or so.  -> {player: seconds into it}."""
    c = self.__dict__.setdefault("_su", {"k": None, "out": {}, "last": {0: -999, 1: -999}, "go": {}})
    if c["k"] == k:
        return c["out"]
    c["k"] = k
    out = {}
    F = self.m["frames"]
    if k >= 6 and not fr.get("r") and not fr.get("c"):
        P0, P1 = F[k - 6]["p"], fr["p"]
        for team in (0, 1):
            ids = range(1, 11) if team == 0 else range(12, 22)
            gk = 0 if team == 0 else 11
            own = P1[gk][0]
            ups = 1.0 if own < 550 else -1.0                                   # (which way is up the pitch)
            line = sorted((abs(P1[j][0] - own), j) for j in ids if P1[j][6])[:4]
            if len(line) < 4:
                continue
            vs = [(P1[j][0] - P0[j][0]) * ups / 10.0 * 5.0 for _, j in line]   # (m/s over the last 0.2 s)
            g = c["go"].get(team)
            if g is not None and (k - g[1]) / 30.0 < 1.4:
                out[g[0]] = (k - g[1]) / 30.0
            elif min(vs) > STEP_UP_SPEED and (k - c["last"][team]) / 30.0 > STEP_UP_GAP:
                who = min(line, key=lambda d: abs(P1[d[1]][1] - 340.0))[1]
                c["go"][team] = (who, k)
                c["last"][team] = k
                out[who] = 0.0
    c["out"] = out
    return out


DOWN_JOG = 3.0           # m/s: up again after being fouled, he jogs to where the engine has him
DOWN_HURRY = 7.5         # m/s: ...or runs, if the free kick's been taken


def _viewer_down(self, i, fr, k, wx, wy, fx, fy):
    """Fouled: he goes down where it happened and stays there (the engine is already walking him to his place
    for the free kick - drawn there, a man lying on the grass slid along it).  Once he's up - or the free kick's
    taken - he jogs over to where the engine has him.  -> (x, y, fx, fy, speed) while he's down, else None."""
    kind, t = self.events.action(i, k)
    st = self.__dict__.setdefault("_down_at", {})
    d = st.get(i)
    if d is not None and not 0 <= k - d[4] <= 3:                        # (a replay, a jump: start again)
        st.pop(i)
        d = None
    r = fr.get("r")
    fk = bool(r and r[0] == "free_kick")
    if kind in ("fouled", "hurt") and (fk or (d is not None and not d[5])):
        if d is None:
            d = st[i] = [wx, wy, fx, fy, k, fk and r[1] == i]          # (...the taker: up when it's taken)
        d[4] = k
        return d[0], d[1], d[2], d[3], 0.0
    if d is not None:
        st.pop(i)
        if not getattr(self, "replay", None) and math.hypot(wx - d[0], wy - d[1]) > 0.4:
            self.__dict__.setdefault("_arriving", {})[i] = [d[0], d[1], 0.0, DOWN_JOG]
    return None


LIE_FROM_GOAL = 30.0     # m: a free kick this close to goal, a wall of 3 or more: one of them lies behind it


def _viewer_lier(self, fr, k):
    """A free kick within shooting range: one of the wall lies down behind it (to stop a shot under the jumping
    wall - most Premier League sides do it now).  The last man of the wall to get there; until a moment after
    it's struck.  -> (player, (x, y), heading) or None."""
    r = fr.get("r")
    if not r or r[0] != "free_kick" or not 0 <= r[1] < len(fr["p"]):
        return None
    c = self.__dict__.setdefault("_lie", {})
    rid = self._restart_id(k)
    if rid in c and c[rid] is not None and c[rid][3] == k:
        return c[rid][:3]
    bx, by = to_world(fr["b"][0], fr["b"][1])
    ok_ = fr["p"][11 if r[1] < 11 else 0]                               # (the goal they're shooting at: where
    gx = HX if to_world(ok_[0], ok_[1])[0] > 0 else -HX                  #  the other keeper is)
    if math.hypot(bx - gx, by) > LIE_FROM_GOAL:
        c[rid] = None
        return None
    wall = []
    for j, q in enumerate(fr["p"]):
        if (j < 11) == (r[1] < 11) or not q[6] or j in (0, 11):
            continue
        x, y = to_world(q[0], q[1])
        d1, d2 = math.hypot(x - bx, y - by), math.hypot(gx - bx, -by)
        if 8.0 < d1 < 11.5 and ((x - bx) * (gx - bx) + (y - by) * (-by)) / max(1e-6, d1 * d2) > 0.82:
            wall.append((j, x, y))
    if len(wall) < 3:
        c[rid] = None
        return None
    who = max(wall)[0] if c.get(rid) is None else c[rid][0]
    cx, cy = sum(w[1] for w in wall) / len(wall), sum(w[2] for w in wall) / len(wall)
    dx, dy = cx - bx, cy - by
    d = math.hypot(dx, dy) or 1.0
    spot = (cx + dx / d * 1.1, cy + dy / d * 1.1)
    head = math.degrees(math.atan2(-dx, dy))                          # (facing the ball: lying across its path)
    c[rid] = (who, spot, head, k)
    return who, spot, head


def _viewer_offside_man(self, fr, r, k):
    """The man caught offside: the free kick's taken where he was - the attacker nearest the spot when it's
    given."""
    cache = self.__dict__.setdefault("_offm", {})
    rid = self._restart_id(k)
    if rid not in cache:
        F = self.m["frames"]
        f0 = F[rid]
        b = f0["b"]
        cand = [(math.hypot(q[0] - b[0], q[1] - b[1]), j) for j, q in enumerate(f0["p"])
                if (j < 11) != (r[1] < 11) and q[6] and j not in (0, 11)]
        cache[rid] = min(cand)[1] if cand else -1
    return cache[rid]


def _viewer_adv_id(self, k):
    """The frame this spell of advantage started on."""
    F = self.m["frames"]
    j = k
    while j > 0 and F[j - 1].get("adv") is not None:
        j -= 1
    return j


def _viewer_appeal(self, i, fr, wx, wy, rbx, rby, r, k):
    """A free kick / offside / penalty given: about two in three of the side it's given to, near the ball, put
    an arm up to the referee as the whistle goes."""
    start = self._restart_id(k)
    t = (k - start) / 30.0
    if t > APPEAL_FOR:
        return None, 0.0
    ours = (i < 11) == (r[1] < 11)
    if not ours or i == r[1] or math.hypot(wx - rbx, wy - rby) > APPEAL_WITHIN or (i * 7 + start) % 3 == 0:
        return None, 0.0
    return "appeal", t - 0.05 * ((i * 3) % 4)                                # (not all at once)


def _viewer_smother(self, i, p, t, k):
    """Down at the man's feet: to whichever side of him the ball was, facing the way he came out."""
    import math as _m
    st = self.__dict__.setdefault("_smo", {}).get(i)
    if st is None or abs(st["k"] - (k - t * 30.0)) > 3:
        F = self.m["frames"]
        hd = _m.radians(p.h or 0.0)
        g, b = F[k]["p"][i], F[k]["b"]
        gx, gy = to_world(g[0], g[1])
        bx, by = to_world(b[0], b[1])
        side = 1 if (bx - gx) * _m.cos(hd) + (by - gy) * _m.sin(hd) >= 0 else -1
        st = self._smo[i] = {"k": k - t * 30.0, "side": side, "h": p.h or 0.0}
    p.smother(t, st["side"])
    p.h = st["h"]
    p.root.setPos(p.root.getX(), p.root.getY(), p.lift)
    p.root.setHpr(p.h, 0, p.roll * p.roll_side)


def _viewer_gather(self, i, fr, cel, wx, wy, dt):
    """After a goal the engine walks everyone back for the kick-off; on TV the scorer's team-mates run to him
    first and mob him.  For a team-mate within 35 m, a second into the celebration: he runs (up to 7 m/s) to a
    place round the scorer, and when it's over, back to where the engine has him.  -> (x, y, speed or None)."""
    g = getattr(self, "_gp", None)
    if g is None:
        g = self._gp = {}
        self._cel_t = 0.0
    if i == 0:
        self._cel_t = self._cel_t + dt if cel else 0.0
    cur = g.get(i)
    target = None
    if cel and 0 <= cel[1] < len(fr["p"]) and i != cel[1] and ((i < 11) == (cel[0] == 0)) \
            and not getattr(self.players[i], "keeper", False) and self._cel_t > 1.0:
        sx, sy = to_world(fr["p"][cel[1]][0], fr["p"][cel[1]][1])
        if cur is not None or math.hypot(wx - sx, wy - sy) < 35:
            a = (i * 2.399) % (2 * math.pi)                     # (each his own place round him)
            r = 0.75 + 0.35 * ((i * 7) % 3)
            target = (sx + r * math.cos(a), sy + r * math.sin(a))
    if target is None:
        if cur is None:
            return wx, wy, None
        target = (wx, wy)
        if math.hypot(cur[0] - wx, cur[1] - wy) < 0.3:          # (back where the engine has him)
            del g[i]
            return wx, wy, None
    if cur is None:
        cur = (wx, wy)
    dx, dy = target[0] - cur[0], target[1] - cur[1]
    d = math.hypot(dx, dy)
    v = min(7.0, d * 2.5)
    step = min(d, v * dt)
    if d > 1e-6:
        cur = (cur[0] + dx / d * step, cur[1] + dy / d * step)
    g[i] = cur
    return cur[0], cur[1], v * 10.0


def _viewer_shield_side(self, i, fr, wx, wy, fwx, fwy):
    """An opponent within 1.6 m: +1 if he's on this player's right, -1 his left (None if no one's that close)."""
    import math as _m
    best, side = 1.6, None
    for j, q in enumerate(fr["p"]):
        if (j < 11) == (i < 11):
            continue
        ox, oy = to_world(q[0], q[1])
        d = _m.hypot(ox - wx, oy - wy)
        if d < best:
            best = d
            side = 1 if (ox - wx) * fwy - (oy - wy) * fwx > 0 else -1
    return side


def _viewer_left_foot(self, i, p, kind, t, k):
    """Which foot he plays it with: the one on the ball's side - or, if it's straight in front of him, his
    stronger foot (about 1 in 5 players are left-footed)."""
    if kind == "shield":                                            # (the arm out on the man's side)
        return self._shield_left.get(i, True)
    if kind not in KICKS + SHOTS + ("touch", "tackle", "volley"):
        return False
    F = self.m["frames"]
    ke = max(0, min(len(F) - 1, int(round(k - t * 30))))
    fe = F[ke]
    x, y, fx, fy = fe["p"][i][:4]
    if kind in ("pass", "flick", "backheel"):                       # (which way the ball went, against his facing)
        f3 = F[min(len(F) - 1, ke + 3)]
        dx, dy = f3["b"][0] - fe["b"][0], f3["b"][1] - fe["b"][1]
        across = fx * dy - fy * dx                                  # (engine y down: + = to his right)
        if math.hypot(dx, dy) > 0.1 and abs(_kick_angle(fx, fy, dx, dy)) > 60:
            # across his body with the inside of the other foot; a flick / back-heel with the foot on that side
            return across > 0 if kind == "pass" else across < 0
    px, py = to_world(x, y)
    bx, by = to_world(fe["b"][0], fe["b"][1])
    fwx, fwy = fx, -fy
    side = (bx - px) * fwy - (by - py) * fwx                        # (+ = the ball is on his right)
    if kind == "tackle":
        side = -side                                                # (a tackle: the leg stretched across)
    lefty = (i * 7 + 3) % 5 == 0
    return side < -0.12 or (lefty and side < 0.12)


RUNUP = {"free_kick": 2.4, "corner_kick": 2.0, "penalty": 2.6, "goal_kick": 3.0}   # (m he steps back from it)


PLACE_GK = 2.6           # s: a keeper putting the ball down for a goal kick before he walks back for his run-up


def _viewer_run_up(self, i, fr, wx, wy, fx, fy, sp, k, dt):
    """Set pieces.  The engine keeps the taker standing on the ball until he kicks it; here, once he's put it
    down, he walks back a few paces (facing where it's going), and runs up to it as he takes it - a penalty
    with a stutter in the run-up.  Taking a corner or a free kick out wide, he puts an arm up first.  The men
    in the wall jump as the free kick is struck.  Returns the place to draw him, his facing and speed, and a
    pose for him (or None)."""
    r = fr.get("r")
    st = self.__dict__.setdefault("_runup", {})
    pose = None
    wall = getattr(self, "_wall", {})
    if i in wall and not r:                                                # (the wall: jump as it's struck)
        tk = (k - wall[i]) / 30.0
        if tk < 0.9:
            pose = ("walljump", tk - 0.3)
        else:
            del wall[i]
    elif i in wall and r and r[0] != "free_kick":
        del wall[i]
    if i in getattr(self, "_down_at", {}) or i in getattr(self, "_arriving", {}):   # (fouled, he's down - or up
        st.pop(i, None)                                                          #  and on his way back to it)
        return wx, wy, fx, fy, sp, pose
    if not r or r[1] != i or r[0] not in RUNUP:
        s = st.get(i)
        if s is not None and s.get("off") is not None:                     # (just taken: ease the last bit)
            s["tail"] = s.get("tail", 0.0) + dt
            f = max(0.0, 1.0 - s["tail"] / 0.2)
            if f <= 0.0:
                del st[i]
            else:
                return wx + s["off"][0] * f, wy + s["off"][1] * f, fx, fy, sp, pose
        else:
            st.pop(i, None)
        return wx, wy, fx, fy, sp, pose
    bx, by = to_world(fr["b"][0], fr["b"][1])
    if math.hypot(wx - bx, wy - by) > 1.5:                                 # (still on his way to it)
        st.pop(i, None)
        return wx, wy, fx, fy, sp, pose
    s = st.setdefault(i, {"at": 0.0, "w": 0.0, "go": None})
    s["at"] += dt
    sx = 1.0 if i < 11 else -1.0                                           # (the way his team attacks)
    tx, ty = {"corner_kick": (sx * (HX - 11.0), 0.0), "goal_kick": (0.0, 0.0)}.get(r[0], (sx * HX, 0.0))
    dx, dy = tx - bx, ty - by
    d = max(1e-3, math.hypot(dx, dy))
    dx, dy = dx / d, dy / d
    D = RUNUP[r[0]]
    kind, t = self.events.action(i, k)
    if kind in KICKS + SHOTS and t < 0:                                     # (running up to it)
        if s["go"] is None:
            s["go"] = (t, s["w"])
        t0, w0 = s["go"]
        u = max(0.0, min(1.0, t / t0)) if t0 < 0 else 0.0                  # (1 -> 0 as he gets there)
        if r[0] == "penalty":                                              # (the stutter: most of the way,
            g = 1.0 - u                                                    #  a check, then the last strides)
            g = 0.6 * min(1.0, g / 0.45) if g < 0.7 else 0.6 + 0.4 * (g - 0.7) / 0.3
            u = 1.0 - g
        w = w0 * u
    else:
        put = PLACE_GK if r[0] == "goal_kick" else 0.8                      # (put it down, then walk back - a
        want = min(1.0, max(0.0, (s["at"] - put) / 0.8))                   #  keeper takes his time over it)
        w = s["w"] + (want - s["w"]) * min(1.0, dt * 2.0)
        if r[0] == "corner_kick" or (r[0] == "free_kick" and d > 22.0):    # (an arm up: it's coming in)
            if 1.6 < s["at"] < 4.4:
                pose = ("signal", s["at"] - 1.9)
    moved = abs(w - s["w"]) * D / max(dt, 1e-3)
    s["w"] = w
    back = 0.45 + D * w
    nx, ny = bx - dx * back, by - dy * back
    s["off"] = (nx - wx, ny - wy)
    return nx, ny, dx, -dy, max(sp, moved * 10.0), pose


def _viewer_scan(self, i, k):
    """Players check over their shoulder before the ball reaches them (top players scan several times in the
    seconds before receiving - Jordet et al., e.g. 2013 "Scanning, contextual factors and association with
    performance in English Premier League footballers"): a glance round, 1.2-0.7 s before his next touch."""
    nxt = None
    l = self.events.by_player.get(i, ())
    import bisect
    at = bisect.bisect_right(l, k, key=lambda e: e[0])                     # (they're kept in time order, more
    for j in range(max(0, at - 6), min(len(l), at + 6)):                   #  or less: look around there)
        ke, kd = l[j]
        if ke > k and kd in ("touch", "chest", "thigh"):
            nxt = ke if nxt is None else min(nxt, ke)
    if nxt is None:
        return 0.0
    t = (nxt - k) / 30.0
    if 0.7 <= t <= 1.2:
        u = math.sin(math.pi * (t - 0.7) / 0.5)
        return u * (60.0 if (i + nxt) % 2 else -60.0)
    return 0.0


def _viewer_dragback(self, i, p, fr, fx, fy, k):
    """On the ball and turning right round (more than ~110 degrees in under half a second, not at speed): a
    drag-back, the sole rolling it back as he pivots."""
    st = self.__dict__.setdefault("_db", {})
    s = st.setdefault(i, {"hist": [], "at": None})
    if s["at"] is not None and 0 <= (k - s["at"]) / 30.0 <= 0.55:
        return "dragback", (k - s["at"]) / 30.0
    a = math.atan2(fy, fx)
    s["hist"] = [(k2, a2) for (k2, a2) in s["hist"] if k - k2 <= 14] + [(k, a)]
    if p.sp < 4.0 and len(s["hist"]) > 3:
        d = abs((math.degrees(a - s["hist"][0][1]) + 180) % 360 - 180)
        if d > 110 and (s["at"] is None or k - s["at"] > 45):
            s["at"] = k
            s["hist"] = []
            return "dragback", 0.0
    return None, 0.0


def _viewer_walk_offs(self, dt, bx, by):
    """Substituted players walking off, clapping the fans (see replace_player)."""
    for w in list(getattr(self, "_leaving", [])):
        p, (tx, ty) = w["p"], w["to"]
        x, y = p.root.getX(), p.root.getY()
        dx, dy = tx - x, ty - y
        d = math.hypot(dx, dy)
        w["t"] += dt
        if d < 0.3 or w["t"] > 40.0:
            p.root.removeNode()
            self._leaving.remove(w)
            continue
        st = min(d, 1.3 * dt)                                              # (a walk: ~1.3 m/s)
        p.update(x + dx / d * st, y + dy / d * st, dx / d, dy / d, 13.0, dt, True, vel=(dx / d * 1.3, dy / d * 1.3),
                 ball=(bx, by))
        p.act("clapwalk", 0.1 + w["t"] % 1.65 if w["t"] < 6.0 else 99.0)      # (clapping for the first few s)


def _viewer_stepover(self, i, p, fr, fx, fy, k):
    """Running at a defender with the ball, the trickier players (about half) throw in a step-over when he's 2-4
    m in front - one every few seconds at most."""
    st = self.__dict__.setdefault("_so", {})
    s = st.get(i)
    if s is not None:
        t = (k - s) / 30.0
        if t <= 0.46:
            return "stepover", t
        if t < 3.0:
            return None, 0.0
    if p.seed % 2 or p.sp < 2.0:
        return None, 0.0
    P = fr["p"]
    for j in (range(11, 22) if i < 11 else range(0, 11)):
        q = P[j]
        dx, dy = q[0] - P[i][0], q[1] - P[i][1]
        d = math.hypot(dx, dy) / 10.0
        if 2.0 < d < 4.0 and (dx * fx + dy * fy) / (d * 10.0) > 0.7 and q[6]:
            st[i] = k
            return "stepover", 0.0
    return None, 0.0


def _viewer_contact(self, i, p, fr, wx, wy, fx, fy, sp, r):
    """Off the ball, close to an opponent: a defender near the man on the ball jockeys (low, side-on, not diving
    in); running shoulder to shoulder with a man, they lean into each other; chasing a man from just behind,
    some reach out for his shirt; at a corner, they jostle in the box (arms out, holding their ground).
    -> (pose, t) or (None, 0)."""
    P = fr["p"]
    o = fr["o"]
    best, bj = 99.0, -1
    for j in (range(11, 22) if i < 11 else range(0, 11)):
        q = P[j] if j < len(P) else None
        if q is None or not q[6]:
            continue
        d = math.hypot(q[0] - P[i][0], q[1] - P[i][1]) / 10.0
        if d < best:
            best, bj = d, j
    p.barge = 0.0
    if bj < 0 or best > 3.5 or o == i:
        return None, 0.0
    q = P[bj]
    dx, dy = (q[0] - P[i][0]) / 10.0, -(q[1] - P[i][1]) / 10.0               # (to him, world-way-up)
    dd = max(0.05, math.hypot(dx, dy))
    ahead = (dx * fx - dy * fy) / dd                                         # (fx, fy: engine facing, y down)
    ms, ms_q = sp / 10.0, q[4] / 10.0
    if r and r[0] == "corner_kick" and best < 1.3 and ms < 2.5:              # (a corner: jostling in the box)
        bx, by = to_world(fr["b"][0], fr["b"][1])
        if math.hypot(wx - bx, wy - by) > 6.0:
            return "shield", 0.5
    if o == bj and best < 3.5 and ms < 4.5 and ahead > 0.5:                   # (closing the man on the ball down)
        return "jockey", 0.5
    if best < 1.1 and ms > 4.0 and ms_q > 4.0 and abs(ahead) < 0.55:          # (side by side: leaning in)
        side = -(dx * fy + dy * fx)                                          # (+ = he's on my right)
        p.barge = 7.0 if side > 0 else -7.0
        return None, 0.0
    if best < 1.4 and ms > 4.5 and ahead > 0.8 and p.seed % 3 == 1:          # (just behind him: a tug)
        return "tug", 0.5
    return None, 0.0


def _viewer_throw_dir(self, i, k, t, fx, fy):
    """A throw-in: he faces the way the ball goes (engine directions)."""
    F = self.m["frames"]
    ke = int(round(k - t * 30))
    a, b = F[max(0, min(len(F) - 1, ke))]["b"], F[max(0, min(len(F) - 1, ke + 6))]["b"]
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    return (dx / d, dy / d) if d > 1e-3 else (fx, fy)


def _viewer_throw_spot(self, wy, t):
    """A throw-in: the engine has the thrower's middle exactly on the touchline (the line is painted just inside
    the pitch's edge), so with his step forward in the throw his front foot landed on the grass.  The laws
    (Law 15: part of each foot on the touchline or on the ground outside it): he stands a step back for it -
    eased in as he picks the ball up, and out again once it's gone."""
    side = 1.0 if wy > 0 else -1.0
    if abs(abs(wy) - HY) > 1.5:                                            # (not by a touchline: leave him be)
        return wy
    w = min(1.0, max(0.0, (t + 1.6) / 0.4)) * min(1.0, max(0.0, (0.7 - t) / 0.45))
    w = w * w * (3 - 2 * w)
    return wy + side * self.THROW_BACK * w


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
            col = (0.12, 0.12, 0.14, 1) if dark else WHITE_PANEL
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


def _mixamo_too(p, kit, number, name, skin, hair):
    """(test, --mixamo) The referee, his assistants, the managers and the subs warming up as Mixamo men too.  The
    stewards, ball boys and the subs sitting on the bench stay as our figures - small, at the edge, and each Mixamo
    man costs more to draw."""
    if MIXAMO:
        import mixamo
        mixamo.attach(p, kit, False, number, name, skin, hair)


def _hand_node(p):
    """Where to hang something in his right hand (a flag, a card): our figure's hand, or the Mixamo man's."""
    if getattr(p, "mix", None) is not None:
        return p.mix.holder("hand.r")
    return p.a.exposeJoint(None, "modelRoot", "hand.r")


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
        _mixamo_too(p, kit, "", None, (205, 160, 125) if role != "ar_far" else (150, 105, 75), (40, 30, 25))
        if role != "ref":                                                   # (an assistant's flag)
            hand = _hand_node(p)
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
        _mixamo_too(p, suit, "", None, (214, 168, 134) if team == 0 else (176, 124, 92), (60, 55, 50))
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
            _mixamo_too(p, top, 20 + j, f"warm{team}{j}", Player.SKINS[(j * 2 + team + 1) % 5], (30, 25, 20))
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
        if o.get("skip"):                               # (left out: lighten())
            continue
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
                kind = "whistle" if t < 0.75 else "point"               # (the whistle, then which way)
                if kind == "point":
                    t -= 0.75
        if fr.get("adv") is not None and o["role"] == "ref":              # (advantage: arms out, play on)
            start = o.setdefault("adv_start", {}).setdefault(self._adv_id(k), k)
            kind, t = "advantage", (k - start) / 30.0
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
    if not s["yes"] and s.get("sig") is None and s["top"] > 50 and sp < 20:   # (the others: his own - kissing
        s["sig"] = k                                                           #  the badge, or a hand to his ear)
    if s.get("sig") is not None and 0 <= (k - s["sig"]) / 30.0 <= 2.6 and kind is None:
        return ("badge" if (rid + i) % 2 else "ear"), (k - s["sig"]) / 30.0
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
    if ((k + i * 37) // 36) % 5 != 0:                                       # (about a second in every six)
        return False
    return "run_point" if ((k + i * 37) // 180 + i) % 2 else "run_call"     # (arm up - or pointing into space)


def _viewer_card_in_hand(self, p, kind):
    """The card in the referee's raised hand (yellow, or red)."""
    if not hasattr(p, "card_np"):
        hand = _hand_node(p)
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
Viewer._run_up = _viewer_run_up
Viewer._contact = _viewer_contact
Viewer._stepover = _viewer_stepover
Viewer._walk_offs = _viewer_walk_offs
Viewer._scan = _viewer_scan
Viewer._dragback = _viewer_dragback
Viewer._throw_spot = _viewer_throw_spot
Viewer.THROW_BACK = 0.35           # m: the thrower's middle this far outside the pitch while he throws
Viewer._left_foot = _viewer_left_foot
Viewer._shield_side = _viewer_shield_side


def _viewer_placing(self, i, fr, wx, wy, rbx, rby, sp, dt):
    """A keeper taking a goal kick: seconds since he got to the ball - he puts it down (the Mixamo men play the
    pack's "placing ball"); None otherwise.  (His walk back for the run-up waits for it: _run_up, PLACE_GK.)"""
    r = fr.get("r")
    if not (r and r[0] == "goal_kick" and r[1] == i):
        return None
    s = getattr(self, "_runup", {}).get(i)
    return s["at"] if s is not None and s.get("go") is None else None


Viewer._placing = _viewer_placing
Viewer._gather = _viewer_gather
Viewer._cam_tv = _viewer_cam_tv
Viewer._set_piece_cam = _viewer_set_piece_cam
Viewer._keeper_dive = _viewer_keeper_dive
Viewer._smother = _viewer_smother
Viewer._appeal = _viewer_appeal
Viewer._adv_id = _viewer_adv_id
Viewer._offside_man = _viewer_offside_man
Viewer._handbags = _viewer_handbags
Viewer._stepping_up = _viewer_stepping_up
Viewer._lier = _viewer_lier
Viewer._down = _viewer_down
Viewer._ball = _viewer_ball
Viewer.THROW_FLIGHT = 0.8      # s: a throw-in in the air (a 10-15 m throw at ~13-15 m/s)
Viewer.THROW_ARC = 0.8         # m: how far it rises above a straight line from his hands to the grass
Viewer._dribble_touch = _viewer_dribble


class Events:
    """Kicks, shots, first touches, headers and tackles, found from the recording (who had the ball, how fast
    it moved), so each player can be posed around the moment he plays it."""
    WINDOW = 0.45

    def __init__(self, frames):
        self.by_player = {}
        self.fps = 30.0
        self.var = {}            # (player, frame) -> how it was (a catch: "low" / "high" / "scoop"; "pen") - for the
        self.last = None         #  Mixamo men's own moves (broadcast3d/mixamo.py); last: the event action() chose

    RANK = {"fouled": 8, "despair": 0, "kneeslide": 7, "throwin": 6, "punt": 5, "bowl": 5, "shot": 4, "header": 3, "tackle": 3,
            "kick": 2, "pass": 2, "loft": 2, "flick": 2, "backheel": 2, "touch": 1, "hurt": 8, "stumble": 3,
            "innocent": 5, "catch": 4, "gkthrow": 5, "splitstep": 3, "slap": 6, "applaud": 1, "contest": 3,
            "flickhead": 3, "volley": 2, "chest": 1, "thigh": 1, "stepover": 1, "spread": 4, "reachup": 4,
            "smother": 6, "finish": 4, "dink": 4}

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
            down, bdown = kind in ("fouled", "hurt"), best is not None and best[0] in ("fouled", "hurt")
            if lo <= t <= hi and (best is None or down > bdown or (down == bdown and abs(t) < abs(best[1]))):
                best = (kind, t)                                    # (a fall beats anything else at that moment)
                self.last = (i, ke)
        if best is None:
            self.last = None
        return best if best else (None, 0.0)

    def variant(self, i):
        """How the move action() just found for player i was (or None)."""
        return self.var.get(self.last) if self.last and self.last[0] == i else None


KICKS = ("kick", "pass", "loft", "flick", "backheel")
SHOTS = ("shot", "finish", "dink")


def _kick_angle(fx, fy, dx, dy):
    """Degrees between the way he faces (fx, fy) and the way the ball went (dx, dy)."""
    a, b = math.hypot(fx, fy), math.hypot(dx, dy)
    if a < 1e-6 or b < 1e-6:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (fx * dx + fy * dy) / (a * b)))))


def _kick_kind(F, k, i, v):
    """Which kick it was, from how the ball left him (v m/s): behind him - a back-heel; back and out to the
    side - a flick with the outside of the foot; across him or a short one - a side-foot pass; rising fast - a
    lofted ball; otherwise the instep."""
    f0, f3 = F[k - 1], F[min(len(F) - 1, k + 3)]
    p = f0["p"][i]
    dx, dy = f3["b"][0] - F[k]["b"][0], f3["b"][1] - F[k]["b"][1]
    ang = _kick_angle(p[2], p[3], dx, dy) if math.hypot(dx, dy) > 0.1 else 0.0
    vz = (f3["b"][2] - F[k]["b"][2]) / 10.0 * 10.0                          # (m/s up)
    if ang > 150:
        return "backheel"
    if ang > 115:
        return "flick"
    if ang > 60 or v < 13.0:
        return "pass"
    return "loft" if vz > 3.0 else "kick"


def _goal_dist(F, k, i, keepers):
    """Metres from him to the goal he's attacking (the end the other keeper is at)."""
    if len(keepers) < 2:
        return 99.0
    gk = keepers[1] if i < 11 else keepers[0]
    gx = 1100.0 if F[k]["p"][gk][0] > 550.0 else 0.0
    p = F[k - 1]["p"][i]
    return math.hypot(p[0] - gx, p[1] - 340.0) / 10.0


FINISH_WITHIN = 17.0    # m: a shot from closer than this, not struck flat out, is a side-foot placed finish
FINISH_SPEED = 27.0     # m/s: ...harder than this is the laces


def _shot_kind(F, k, i, v, keepers):
    """Which shot: struck behind him (not turned) - a back-heel or a flick; close in and not flat out - a
    side-foot placed finish; otherwise a drive with the laces."""
    kind = _kick_kind(F, k, i, v)
    if kind in ("backheel", "flick"):
        return kind
    return "finish" if v < FINISH_SPEED and _goal_dist(F, k, i, keepers) < FINISH_WITHIN else "shot"


def _dink(F, k, i, v, keepers):
    """A dink: a soft one (9-20 m/s) rising steeply, towards goal from inside 25 m."""
    if not 9.0 <= v <= 20.0 or _goal_dist(F, k, i, keepers) > 25.0:
        return None
    f3 = F[min(len(F) - 1, k + 3)]
    vz = (f3["b"][2] - F[k]["b"][2]) / 10.0 * 10.0
    if vz < 4.0:
        return None
    gk = keepers[1] if i < 11 else keepers[0]
    gx = 1100.0 if F[k]["p"][gk][0] > 550.0 else 0.0
    dx = f3["b"][0] - F[k]["b"][0]
    return "dink" if dx * (gx - F[k]["b"][0]) > 0 else None


def _head_kind(F, k, i, ev):
    """A header - glanced on behind him (a flick-on) or met properly; and the nearest opponent within 2 m goes
    up with him."""
    f0, f3 = F[k - 1], F[min(len(F) - 1, k + 3)]
    p = f0["p"][i]
    dx, dy = f3["b"][0] - F[k]["b"][0], f3["b"][1] - F[k]["b"][1]
    near = min(((math.hypot(q[0] - p[0], q[1] - p[1]), j) for j, q in enumerate(f0["p"])
                if (j < 11) != (i < 11) and q[6] and j not in (0, 11)), default=(99, -1))
    if near[0] < 20 and near[1] >= 0:
        ev.add(near[1], k, "contest")
    if math.hypot(dx, dy) > 0.1 and _kick_angle(p[2], p[3], dx, dy) > 100:
        return "flickhead"
    return "header"


SPREAD_WITHIN = 6.0     # m: the shooter this close to the keeper as he strikes it - the starfish
SMOTHER_NEAR = 2.5      # m: the keeper gets the ball with an opponent this close - down at his feet


def _opp_near(F, k, gk, within):
    g = F[k]["p"][gk]
    return any(math.hypot(q[0] - g[0], q[1] - g[1]) / 10.0 < within
               for j, q in enumerate(F[k]["p"]) if (j < 11) != (gk < 11) and q[6])


def find_events(F, keepers=(0, 11), ev=None, lo=0):
    """ev=None: the whole recording.  Live (broadcast3d/live.py): ev = the Events so far, lo = where the last
    look got up to - the frames since are looked at and added (each frame's "k" is already set)."""
    import math as _m
    live = ev is not None
    if not live:
        ev = Events(F)
        for k, fr in enumerate(F):
            fr["k"] = k
    sp = lambda a, b: _m.dist(a[:2], b[:2]) / 10.0 * 30.0                  # m/s, from two frames
    gained = ev.__dict__.setdefault("_gained", {})
    for k in range(max(2, lo), len(F) - 4):
        a, b = F[k - 1]["o"], F[k]["o"]
        if b >= 0 and a != b:
            gained[b] = (k, "r" in F[k - 1] or "r" in F[k - 2])            # (when he got it - from a dead ball?)
        if a >= 0 and b < 0:                                                # he's played it
            v = sp(F[k]["b"], F[k + 3]["b"]) / 3.0
            z = F[k - 1]["b"][2] / 10.0
            gk, dead = gained.get(a, (-99, False))
            if a in keepers and not dead and z < 2.5 and F[k - 1].get("gf") != a:   # (a keeper, ball in his hands:
                                                                            #  out of his hands - however long he
                                                                            #  held it; not a back-pass at his feet)
                ev.add(a, k, "punt" if v > 17 else "gkthrow" if v > 12 else "bowl")   # (overarm for a long one)
                continue
            ev.add(a, k, _head_kind(F, k, a, ev) if z > 1.3 else _shot_kind(F, k, a, v, keepers) if v > 21 else
                   "volley" if z > 0.35 else _dink(F, k, a, v, keepers) or _kick_kind(F, k, a, v))
            if v > 21 and z <= 1.3 and len(keepers) > 1:                   # (their keeper: a split step -
                gk = keepers[1] if a < 11 else keepers[0]                       #  or, rushed out to him, the starfish)
                pa, pg = F[k - 1]["p"][a], F[k - 1]["p"][gk]
                close = _m.hypot(pa[0] - pg[0], pa[1] - pg[1]) / 10.0 < SPREAD_WITHIN
                ev.add(gk, k - (1 if close else 4), "spread" if close else "splitstep")
        elif a < 0 and b >= 0:
            z = F[k]["b"][2] / 10.0
            if b in keepers and z < 0.6 and _opp_near(F, k, b, SMOTHER_NEAR) and F[k].get("gf") != b:   # (a keeper going down at a
                ev.add(b, k, "smother")                                          #  man's feet for it)
            elif b in keepers and sp(F[k - 2]["b"], F[k - 1]["b"]) > 9.0 and F[k].get("gf") != b:   # (a keeper takes
                                                                            #  a shot / a cross - not a back-pass)
                ev.add(b, k, "catch")
                ev.var[(b, k)] = "low" if z < 0.5 else "high" if z > 1.7 else None
            elif b in keepers and z < 0.5 and F[k].get("gf") != b and sp(F[k - 2]["b"], F[k - 1]["b"]) > 1.0:
                ev.add(b, k, "catch")                                       # (a keeper gathers a rolling ball:
                ev.var[(b, k)] = "scoop"                                    #  scoops it up)
            else:
                ev.add(b, k, _head_kind(F, k, b, ev) if z > 1.3 else "chest" if z > 1.0 else "thigh" if z > 0.45
                       else "touch")                                        # (the first touch)
        elif a >= 0 and b >= 0 and a != b:
            if (a < 11) != (b < 11) and b in keepers:
                ev.add(b, k, "smother")                                     # (the keeper takes it off his toe)
            elif (a < 11) != (b < 11):
                ev.add(b, k, "tackle")
                if a not in keepers:
                    ev.add(a, k, "stumble")                                 # (knocked off his stride)
        elif a < 0 and b < 0:                                               # a loose ball changes course
            v0 = [(F[k - 1]["b"][j] - F[k - 2]["b"][j]) * 3.0 for j in range(3)]
            v1 = [(F[k]["b"][j] - F[k - 1]["b"][j]) * 3.0 for j in range(3)]
            if _m.dist(v0, v1) > 5.0:
                bx, by = F[k]["b"][0], F[k]["b"][1]
                near = min(((_m.hypot(p[0] - bx, p[1] - by) / 10.0, i) for i, p in enumerate(F[k]["p"]) if p[6]),
                           default=(99, -1))
                if near[0] < 2.0:
                    z = F[k]["b"][2] / 10.0
                    ev.add(near[1], k, _head_kind(F, k, near[1], ev) if z > 1.3 else "kick")
    for k in range(max(2, lo), len(F) - 1):                                  # a dink looping over a keeper: he
        if F[k]["o"] >= 0 or "r" in F[k]:                                    #  stretches up for it
            continue
        bx, by, bz = F[k]["b"][0], F[k]["b"][1], F[k]["b"][2] / 10.0
        if not 1.9 < bz < 3.6:
            continue
        for gk in keepers:
            g = F[k]["p"][gk]
            if _m.hypot(g[0] - bx, g[1] - by) / 10.0 < 1.6 and (len(g) < 8 or g[7] not in ("diving", "recover")):
                last = ev.__dict__.setdefault("_reach", {}).get(gk, -99)
                if k - last > 45:
                    ev._reach[gk] = k
                    ev.add(gk, k, "reachup")
    for k in range(max(2, lo), len(F)):                                      # a goal: the keeper beaten, on his
        if F[k]["s"] != F[k - 1]["s"] and len(keepers) > 1:                  #  knees, slaps the grass
            who = 1 if F[k]["s"][0] > F[k - 1]["s"][0] else 0                 # (the side that let it in)
            ev.add(keepers[who], k + 50, "slap")
    seen = ev.__dict__.setdefault("_despair_seen", set())
    for i, l in list(ev.by_player.items()):                                  # a shot that didn't go in: hands
        for (ke, kind) in list(l):                                           # on head a moment later
            if kind in SHOTS and ke + 75 < len(F) and (i, ke) not in seen:
                seen.add((i, ke))
                if F[ke + 75]["s"] == F[ke]["s"]:
                    l.append((ke + 24, "despair"))
                    sx_, sy_ = F[ke + 24]["p"][i][:2]                       # (a team-mate applauds the effort)
                    mates = [(_m.hypot(p[0] - sx_, p[1] - sy_), j) for j, p in enumerate(F[ke + 24]["p"])
                             if (j < 11) == (i < 11) and j != i and j not in keepers and p[6]]
                    near = min(mates, default=(999, -1))
                    if near[0] < 250 and (ke + i) % 2 == 0:
                        ev.add(near[1], ke + 30, "applaud")
    for k in range(max(2, lo), len(F)):                                      # a free kick: the man fouled goes
        r = F[k].get("r")                                                    #  down (the taker's team-mate
        if r and r[0] == "free_kick" and F[k - 1].get("r", [None])[0] != "free_kick" and r[1] >= 0:   # nearest
            bx, by = F[k - 1]["b"][0], F[k - 1]["b"][1]                                               # the ball)
            team = r[1] < 11
            near = min(((_m.hypot(p[0] - bx, p[1] - by), j) for j, p in enumerate(F[k - 1]["p"])
                        if (j < 11) == team and j not in keepers and j != r[1]), default=(99, -1))
            j = near[1]                                                      # (not the taker: he's up, on the ball)
            if F[k].get("fd") is not None:                                   # (who was really fouled, when the
                j = F[k]["fd"]                                               #  frames say)
                near = (0.0, j)
            quick = j == r[1] and k + 150 < len(F) and (F[k + 150].get("r") or [None])[0] != "free_kick"
            if near[0] < 30 and j >= 0 and not quick and (k, "fouled") not in ev.by_player.get(j, []) \
                    and (k, "hurt") not in ev.by_player.get(j, []):     # (a quick free kick by the man fouled:
                l = ev.by_player.setdefault(j, [])                           #  he didn't stay down)
                l[:] = [(k2, kd) for (k2, kd) in l if abs(k2 - k) > 8 or kd not in KICKS + ("touch", "stumble")]
                l.append((k, "hurt" if (k + j) % 3 == 0 and j != r[1] else "fouled"))   # (not a "kick" too: the ball was
                                                                             #  taken off him, he didn't play it;
                                                                             #  about 1 in 3 stay down, hurt)
                px, py = F[k - 1]["p"][j][:2]                               # (the man who fouled him: hands up)
                fl = min(((_m.hypot(p[0] - px, p[1] - py), q) for q, p in enumerate(F[k - 1]["p"])
                          if (q < 11) != team and q not in keepers and p[6]), default=(99, -1))
                if fl[0] < 40 and fl[1] >= 0:
                    ev.add(fl[1], k + 6, "innocent")
    for k in range(max(1, lo), len(F) - 4):                                  # dead balls: who took it, and how
        r = F[k - 1].get("r")
        if r and "r" not in F[k] and r[1] >= 0:
            v = sp(F[k]["b"], F[k + 3]["b"]) / 3.0
            kind = {"throw_in": "throwin", "kick_off": "touch", "penalty": "shot"}.get(r[0], "shot" if v > 21 else
                                                                                         _kick_kind(F, k, r[1], v))
            l = ev.by_player.setdefault(r[1], [])
            l[:] = [(k2, kd) for (k2, kd) in l if abs(k2 - k) > 8]
            l.append((k, kind))
            if r[0] == "penalty":
                ev.var[(r[1], k)] = "pen"
    return ev


def intro(v, F, first, n, out, start_idx):
    """An establishing shot: the camera swings round Kiln Lane from high above the Canal End."""
    for i in range(n):
        a = math.radians(-60 + 70 * i / n)
        v.show(F[first], 1 / 30.0)
        v.cam.setPos(150 * math.sin(a) + 20, -150 * math.cos(a), 70 - 25 * i / n)
        v.cam.lookAt(0, 8, 0)
        v.taskMgr.step()   # (runs the lighting tasks, then draws)
        img = PNMImage(); v.win.getScreenshot(img); img.write(pf(os.path.join(out, f"f{start_idx + i:05d}.png")))
    return n


def replay_angle(F, g):
    """Which camera for the replay of the goal at frame g (the first frame of the celebration):
    -> (end: +1 / -1 which goal, "goal" or "side", where the shot was hit (x, y) in metres).
    The way TV does it: a goal from out wide (an angled shot, or a cross) is best seen side-on, from the
    touchline level with the edge of the box - you see the ball come across and the finish; a shot from the
    middle is best from behind the goal, looking back at the shooter.  (--replay=side / --replay=goal forces one.)"""
    b = lambda k: to_world(F[k]["b"][0], F[k]["b"][1])
    k = max(1, g - 3)
    end = 1 if b(max(0, g - 5))[0] > 0 else -1
    # back from the goal while the ball was flying in (moving, getting nearer the goal): where it was hit from
    while k > max(1, g - 90):
        (x0, y0), (x1, y1) = b(k - 1), b(k)
        if math.hypot(x1 - x0, y1 - y0) * 30.0 < 7.0 or (x1 - x0) * end < -0.05:
            break
        k -= 1
    sx, sy = b(k)
    wx, wy = b(max(0, k - 45))                              # (a second and a half before: a cross from the wing?)
    kind = "side" if abs(sy) > 12.0 or abs(wy) > 22.0 else "goal"
    force = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--replay=")), None)
    if force in ("side", "goal"):
        kind = force
    return end, kind, (sx, sy)


def tick():
    from panda3d.core import ClockObject
    ClockObject.getGlobalClock().tick()


class Director:
    """The TV director: plays the match on, and after a goal - once they've celebrated a few seconds - shows a
    replay: the last five seconds before it, slowed down, from behind the goal.  frame(step) -> which recorded
    frame to show next (and v.replay is set while a replay's on)."""
    BEFORE, AFTER, WAIT, SLOW = 150, 18, 150, 0.55

    def __init__(self, v, F, first):
        self.v, self.F = v, F
        self.t = float(first)
        self.goals = [k for k in range(1, len(F)) if "c" in F[k] and "c" not in F[k - 1]]
        self.done = {g for g in self.goals if g < first}
        self.rp = None
        v.replay = None

    def frame(self, step):
        """step: recorded frames to move on (1 a frame, at normal speed)."""
        F = self.F
        if self.rp is not None:
            g, pos = self.rp
            pos += step * self.SLOW
            if pos >= g + self.AFTER:
                self.rp = None
                self.v.replay = None
                self.v._gp = {}
            else:
                self.rp = (g, pos)
                return F[int(pos)]
        self.t = min(len(F) - 1.0, self.t + step)
        for g in self.goals:
            if g not in self.done and self.t >= g + self.WAIT:
                self.done.add(g)
                if "--noreplay" not in sys.argv and g - self.BEFORE >= 0:
                    self.rp = (g, float(g - self.BEFORE))
                    side, self.v.replay_kind, self.v.replay_from = replay_angle(F, g)
                    self.v.replay = side
                    self.v._gp = {}                         # (the replay shows them where they were)
                    self.v.gball = None                     # (and the ball where it was, not in the net)
                    self.v._rp_cam = None
                    return F[g - self.BEFORE]
        return F[int(self.t)]


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
    def toggle_stats():
        if getattr(v, "_stats", None) is not None:
            v._stats.removeNode(); v._stats = None
        else:
            v._stats = v.stats_panel(int(st["t"]))
    v.accept("s", toggle_stats)
    key("1", lambda: setattr(v, "cam_mode", 0))
    key("2", lambda: setattr(v, "cam_mode", 1))
    v.accept("escape", sys.exit)
    help_t = OnscreenText(text="space pause   <- -> 10 s   [ ] speed   1 TV   2 close   S stats   Esc quit", pos=(0, -0.95),
                          scale=0.04, fg=(1, 1, 1, 0.8), mayChange=False)

    try:                                                  # (for the log: which graphics chip is drawing it)
        g = v.win.getGsg()
        print("graphics:", g.getDriverVendor(), "|", g.getDriverRenderer(), "|", g.getDriverVersion(), flush=True)
    except Exception:
        pass
    d = Director(v, F, first)
    end_t = {"n": None}
    sheet = {"n": v.lineups(v.m) if "--nolineups" not in sys.argv else None, "t": 0.0}

    def tick_task(task):
        dt = min(0.1, ClockObject.getGlobalClock().getDt())
        if sheet["n"] is not None:                          # (the team sheets for the first few seconds)
            sheet["t"] += dt
            if sheet["t"] > 6.0:
                sheet["n"].removeNode()
                sheet["n"] = None
        if abs(d.t - st["t"]) > 2:                         # (skipped with the arrow keys)
            d.t, d.rp, v.replay = st["t"], None, None
            d.done = {g for g in d.goals if g < st["t"]}
            v.gball = None
        at_end = d.t >= len(F) - 1 and v.replay is None     # (the recording's run out: say so)
        if at_end and end_t["n"] is None:
            end_t["n"] = OnscreenText(text="End of the recording   (<- to go back, Esc to quit)", pos=(0, 0.55),
                                      scale=0.06, fg=(1, 1, 1, 1), shadow=(0, 0, 0, 0.9), mayChange=False)
        elif not at_end and end_t["n"] is not None:
            end_t["n"].destroy()
            end_t["n"] = None
        step = 0.0 if st["paused"] else dt * 30.0 * st["speed"]
        fr = d.frame(step)
        st["t"] = d.t
        v.show(fr, dt * (0 if st["paused"] else st["speed"] * (Director.SLOW if v.replay else 1)) or 1e-3)
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
        img = PNMImage(); v.win.getScreenshot(img); img.write(pf(os.path.join(HERE, "frames", "live_test.png")))
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
    d = Director(v, F, first)
    sheet = v.lineups(v.m) if "--lineups" in sys.argv else (v.stats_panel(first, "HALF-TIME" if "--ht" in sys.argv else None) if "--stats" in sys.argv else None)
    for i in range(n):
        if sheet is not None and i == 150:
            sheet.removeNode()
            sheet = None
        fr = d.frame(1.0 if i else 0.0)
        v.show(fr, 1 / 30.0 * (Director.SLOW if v.replay else 1.0))
        v.taskMgr.step()   # (this also moves the clock on one frame - don't tick() as well)   # (runs the lighting tasks, then draws)
        img = PNMImage(); v.win.getScreenshot(img); img.write(pf(os.path.join(out, f"f{k + i:05d}.png")))
    print("rendered", n)


if __name__ == "__main__":
    main()
