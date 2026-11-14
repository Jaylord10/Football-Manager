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

    def build_kiln_lane(self):
        b = self.b
        # the pitch and its surround
        cm = CardMaker("pitch"); cm.setFrame(-HX - 8, HX + 8, -HY - 8, HY + 8)
        p = self.root.attachNewNode(cm.generate()); p.setP(-90); p.setTexture(self.T("pitch.png", False)); no_shadow(p)
        cm2 = CardMaker("apron"); cm2.setFrame(-HX - 40, HX + 40, -HY - 40, HY + 40)
        ap = self.root.attachNewNode(cm2.generate()); ap.setP(-90); ap.setZ(-0.02); ap.setColor(C((96, 98, 100))); no_shadow(ap)
        cm3 = CardMaker("outer"); cm3.setFrame(-400, 400, -400, 400)
        ou = self.root.attachNewNode(cm3.generate()); ou.setP(-90); ou.setZ(-0.5); ou.setColor(C((70, 82, 64))); no_shadow(ou)
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
        self.tier(r, -32, 32, 7, 1.2, 19, 7.5, "crowd_mixed.png", (90, 90, 96))
        self.back_wall(r, -32, 32, 19, 0, 10, tex="brick.png", rep=(14, 2))
        self.roof(r, -33, 33, 8, 21, 9.5, col=(80, 70, 66), pitched=2.5, columns=4)
        # Main Stand (near, under the camera): front rows only
        n = self.side("near")
        self.tier(n, -50, 50, 8, 1.2, 20, 8, "crowd_home.png", (200, 40, 45))
        for s, x in ((n, -9), (n, 9)):                                       # dugouts
            box(s, x - 4, 3.2, 0, x + 4, 5.5, 2.2, C((40, 42, 48)))
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
        cm = CardMaker("moors"); cm.setFrame(-900, 900, 0, 150)
        mo = self.root.attachNewNode(cm.generate()); mo.setPos(0, 650, -10); mo.setTexture(self.T("moors.png", False))
        mo.setTransparency(TransparencyAttrib.MAlpha); mo.setLightOff(); no_shadow(mo, lit=False)
        cm = CardMaker("sky"); cm.setFrame(-2000, 2000, -100, 700)
        sk = self.root.attachNewNode(cm.generate()); sk.setPos(0, 1200, -50); sk.setTexture(self.T("sky.png", False)); sk.setLightOff(); no_shadow(sk, lit=False)

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
        for i in range(4):
            for j in range(3):
                box(n, -3.5 + i * 1.9, -0.75, H + 0.5 + j * 1.5, -2.3 + i * 1.9, -0.5, H + 1.6 + j * 1.5, C((255, 250, 225)))
        n.setH(40)

    def ad_boards(self):
        from PIL import Image, ImageDraw, ImageFont
        brands = [("PILLING TEXTILES", (200, 40, 45), (255, 255, 255)), ("ASH VALLEY ALES", (20, 60, 40), (240, 210, 120)),
                  ("THE NATIONAL CHRONICLE", (25, 30, 60), (255, 255, 255)), ("KILN LANE MOTORS", (240, 240, 240), (200, 40, 45)),
                  ("ASHVALE EVENING POST", (30, 30, 30), (255, 200, 40)), ("WEAVERS BUILDING SOC.", (10, 90, 160), (255, 255, 255))]
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
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
            box(s, -half, dist + 0.02, 0, half, dist + 0.12, 0.95, C((40, 42, 48)))      # (the back of the boards)

    def goals(self):
        for sx in (-1, 1):
            n = self.root.attachNewNode("goal"); n.setPos(sx * HX, 0, 0)
            w = 7.32 / 2; h = 2.44; dpt = 2.0
            white = (0.97, 0.97, 0.97, 1)
            box(n, -0.06, -w - 0.06, 0, 0.06, -w + 0.06, h, white)
            box(n, -0.06, w - 0.06, 0, 0.06, w + 0.06, h, white)
            box(n, -0.06, -w - 0.06, h - 0.06, 0.06, w + 0.06, h + 0.06, white)
            m = Mesh("net")
            x = sx * dpt
            netc = (1, 1, 1, 0.35)
            m.quad((0, -w, h), (0, w, h), (x, w, h * 0.7), (x, -w, h * 0.7), netc)
            m.quad((x, -w, 0), (x, w, 0), (x, w, h * 0.7), (x, -w, h * 0.7), netc)
            m.quad((0, -w, 0), (x, -w, 0), (x, -w, h * 0.7), (0, -w, h), netc)
            m.quad((0, w, 0), (x, w, 0), (x, w, h * 0.7), (0, w, h), netc)
            nn = n.attachNewNode(m.node()); nn.setTwoSided(True); nn.setTransparency(TransparencyAttrib.MAlpha)


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
        self.setBackgroundColor(0.62, 0.66, 0.70, 1)
        self.render.setAntialias(AntialiasAttrib.MMultisample)
        self.m = match
        st = Stadium(self); st.build_kiln_lane(); st.goals()
        self.light_up()
        fog = Fog("haze"); fog.setColor(0.62, 0.66, 0.7); fog.setExpDensity(0.0012); self.render.setFog(fog)
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
                self.players.append(AnimPlayer(self.render, kit, (i % 11) + 1, skin, hair, keeper))
            else:
                self.players.append(Player(self.render, kit, (i % 11) + 1, skin, hair, keeper))
        cm = CardMaker("shadow"); cm.setFrame(-0.45, 0.45, -0.3, 0.3)          # soft blob shadows
        from PIL import Image, ImageFilter, ImageDraw
        sh = Image.new("RGBA", (64, 64), (0, 0, 0, 0)); ImageDraw.Draw(sh).ellipse([8, 14, 56, 50], fill=(0, 0, 0, 120))
        sh.filter(ImageFilter.GaussianBlur(5)).save(T + "shadow.png")
        stex = self.loader.loadTexture(T + "shadow.png")
        self.shadows = []
        for p in self.players:
            n = p.root.attachNewNode(cm.generate()); n.setP(-90); n.setPos(0.25, 0.25, 0.02); n.setTexture(stex)
            n.setTransparency(TransparencyAttrib.MAlpha); n.setLightOff(); n.setDepthWrite(False); n.setBin("fixed", 0)
            no_shadow(n, lit=False)
            if not OVERCAST:
                n.hide()                                    # (the sun casts real shadows now)
        self.ball = sphere(self.render, BALL_R, (0.98, 0.98, 0.98, 1), seg=20, ring=14)
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
        self.events = find_events(match["frames"])
        self.dives = {}
        self.ball_off = Vec3(0, 0, 0)
        self.ball_mode = None
        self.last_ball = None
        self.dribble = {}
        self.hud(match)

    def light_up(self):
        """The light.  Default: a bright autumn afternoon - a low sun from behind the Main Stand (the camera's side),
        real shadows (each player's, the ball's, the stands' and the goal frames') stretching away up the pitch.
        --overcast: the old grey Lancashire afternoon, no sun shadows."""
        if OVERCAST:
            al = AmbientLight("amb"); al.setColor(Vec4(0.52, 0.53, 0.56, 1))
            self.render.setLight(self.render.attachNewNode(al))
            dl = DirectionalLight("sun"); dl.setColor(Vec4(0.62, 0.6, 0.56, 1))
            sun = self.render.attachNewNode(dl); sun.setPos(-40, -60, 120); sun.lookAt(0, 0, 0)
            self.render.setLight(sun)
            return
        al = AmbientLight("amb"); al.setColor(Vec4(0.50, 0.53, 0.60, 1))               # (blue-ish sky fill)
        self.render.setLight(self.render.attachNewNode(al))
        dl = DirectionalLight("sun"); dl.setColor(Vec4(1.25, 1.12, 0.92, 1))             # (warm low sun)
        dl.setShadowCaster(True, SHADOW_MAP, SHADOW_MAP)
        lens = dl.getLens(); lens.setFilmSize(250, 170); lens.setNearFar(10, 600)
        sun = self.render.attachNewNode(dl)
        az, el = math.radians(SUN_AZ), math.radians(SUN_EL)
        sun.setPos(-math.sin(az) * math.cos(el) * 300, -math.cos(az) * math.cos(el) * 300, math.sin(el) * 300)
        sun.lookAt(0, 0, 0)
        self.render.setLight(sun)
        self.sun = sun
        dl.setCameraMask(NO_SHADOW_BIT)                    # (the sun's shadow camera: see no_shadow())
        sh = Shader.load(Shader.SL_GLSL, os.path.join(HERE, "shaders", "lit.vert"), os.path.join(HERE, "shaders", "lit.frag"))
        self.render.setShader(sh)
        self.render.setShaderInput("shadow_bias", 0.0004)
        self.render.setShaderInput("shadow_texel", 1.0 / SHADOW_MAP)
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

    def show(self, fr, dt):
        k = fr.get("k", 0)
        rbx, rby = to_world(fr["b"][0], fr["b"][1])
        prev = getattr(self, "_prev_pos", {})
        for i, (p, (x, y, fx, fy, sp, state, act, *_)) in enumerate(zip(self.players, fr["p"])):
            wx, wy = to_world(x, y)
            px, py = prev.get(i, (wx, wy))
            vel = ((wx - px) / max(dt, 1e-3), (wy - py) / max(dt, 1e-3))
            prev[i] = (wx, wy)
            p.update(wx, wy, fx, -fy, sp, dt, act, vel=vel, ball=(rbx, rby))
            kind, t = self.events.action(i, k)
            dv = fr["p"][i][7] if len(fr["p"][i]) > 7 else ""
            if dv in ("diving", "recover") and getattr(p, "keeper", False):    # (a keeper's dive)
                self._keeper_dive(i, p, dv, k)
                continue
            if kind is None and fr["o"] == i:
                kind, t = self._dribble_touch(i, p, dt)
            if kind is None and getattr(p, "keeper", False) and sp < 25:          # (a keeper, set for a shot)
                gx = -HX if wx < 0 else HX
                if math.hypot(rbx - gx, rby) < 30 and fr["o"] not in (range(0, 11) if i < 11 else range(11, 22)):
                    kind, t = "ready", 0.0
            p.act(kind, t, self._left_foot(i, p, kind, t, k))
        self._prev_pos = prev
        bx, by, bz = self._ball(fr, dt)
        self.ball.setPos(bx, by, bz)
        self.bsh.setPos(bx, by, 0.02)
        # the camera pans with the ball (smoothly), a little zoom when it's near the far side
        k = min(1.0, dt * 2.2)
        self.cx += (max(-34, min(34, bx)) - self.cx) * k
        self.cy += (by - self.cy) * k
        if FOLLOW is not None:                                              # (a close camera on one player)
            fx_, fy_ = to_world(fr["p"][FOLLOW][0], fr["p"][FOLLOW][1])
            sx = 1 if fx_ < 0 else -1                                       # (from out on the pitch, looking at him)
            if "--side" in sys.argv:                                        # (or side-on to him, to check his gait)
                hd = math.radians(self.players[FOLLOW].h or 0.0)
                self._sv = getattr(self, "_sv", (math.cos(hd), math.sin(hd)))
                k2 = min(1.0, dt * 1.5)
                self._sv = (self._sv[0] + (math.cos(hd) - self._sv[0]) * k2, self._sv[1] + (math.sin(hd) - self._sv[1]) * k2)
                self.cam.setPos(fx_ + self._sv[0] * 11, fy_ + self._sv[1] * 11, 2.0)
            else:
                self.cam.setPos(fx_ + sx * 9, fy_ - 7, 3.2)
            self.cam.lookAt(fx_, fy_, 0.8)
        elif CLOSE:                                                         # (a close camera, for checking)
            self.cam.setPos(bx - 6, by - 14, 4.5)
            self.cam.lookAt(bx, by, 0.9)
        else:
            self.cam.setPos(self.cx * 0.8, -HY - 62, 33)
            self.cam.lookAt(self.cx, self.cy * 0.35 + 9, 0)
        s = fr["s"]
        self.score_t.setText(f"{self.labels[0]}  {s[0]} - {s[1]}  {self.labels[1]}")
        mins = int(fr["t"] / 600.0 * 45)
        self.clock_t.setText(f"{mins:02d}:{int((fr['t'] / 600.0 * 45 * 60) % 60):02d}")


# --- The ball at the players' feet, and what each player is doing with it ------------------------------------
DRIBBLE_TOUCH = 0.7          # seconds between touches when running with the ball
BALL_R = 0.15                # (a real ball is 0.11 m across the middle: drawn a touch big, as TV games do)


def _viewer_ball(self, fr, dt):
    """Where to draw the ball.  Loose: where the engine has it.  At a player's feet: just in front of him,
    pushed ahead with each touch when he's running with it.  Switching between the two eases over ~0.1 s."""
    import math as _m
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
        if getattr(p, "keeper", False):                                     # (a keeper holds it to his chest)
            bx, by, bz = px + fx * 0.32, py + fy * 0.32, 1.05
    if mode != self.ball_mode:
        if self.last_ball is not None:
            self.ball_off = Vec3(*self.last_ball) - Vec3(bx, by, bz)        # (ease from where it was drawn)
        self.ball_mode = mode
    self.ball_off *= _m.exp(-dt / 0.09)
    out = (bx + self.ball_off.x, by + self.ball_off.y, max(BALL_R, bz + self.ball_off.z))
    self.last_ball = out
    return out


def _viewer_dribble(self, i, p, dt):
    """Running with the ball: a touch every DRIBBLE_TOUCH seconds - the pose either side of it."""
    if p.sp < 1.2:
        return None, 0.0
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

    RANK = {"shot": 4, "header": 3, "tackle": 3, "kick": 2, "touch": 1}

    def add(self, i, k, kind):
        l = self.by_player.setdefault(i, [])
        for n, (k2, kind2) in enumerate(l):
            if abs(k2 - k) <= 8:                                            # (the same moment, seen twice)
                if self.RANK[kind] > self.RANK[kind2]:
                    l[n] = (k, kind)
                return
        l.append((k, kind))

    def action(self, i, k):
        best = None
        for (ke, kind) in self.by_player.get(i, ()):
            t = (k - ke) / self.fps
            if -self.WINDOW <= t <= self.WINDOW and (best is None or abs(t) < abs(best[1])):
                best = (kind, t)
        return best if best else (None, 0.0)


def find_events(F):
    import math as _m
    ev = Events(F)
    for k, fr in enumerate(F):
        fr["k"] = k
    sp = lambda a, b: _m.dist(a[:2], b[:2]) / 10.0 * 30.0                  # m/s, from two frames
    for k in range(2, len(F) - 4):
        a, b = F[k - 1]["o"], F[k]["o"]
        if a >= 0 and b < 0:                                                # he's played it
            v = sp(F[k]["b"], F[k + 3]["b"]) / 3.0
            z = F[k - 1]["b"][2] / 10.0
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


def main():
    if ANIM:
        sys.path.insert(0, HERE)
        global AnimPlayer
        from players3d import AnimPlayer
        from panda3d.core import ClockObject
        c = ClockObject.getGlobalClock(); c.setMode(ClockObject.MNonRealTime); c.setFrameRate(30)
    mj = os.path.join(HERE, "match.json")
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
    # warm the camera up on the first frame
    for _ in range(40):
        v.show(F[first], 1 / 30.0); tick()
    k = intro(v, F, first, 120, out, 0) if "--intro" in sys.argv else 0
    for _ in range(40):
        v.show(F[first], 1 / 30.0)
    for i in range(n):
        v.show(F[first + i], 1 / 30.0)
        v.taskMgr.step()   # (this also moves the clock on one frame - don't tick() as well)   # (runs the lighting tasks, then draws)
        img = PNMImage(); v.win.getScreenshot(img); img.write(Filename(f"{out}/f{k + i:05d}.png"))
    print("rendered", n)


if __name__ == "__main__":
    main()
