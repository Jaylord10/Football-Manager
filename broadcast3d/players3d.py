"""Animated players: a rigged figure (idle / run, and walk where the model has it), painted in the club's kit
by height, with kicks, shots, touches, headers and tackles posed by hand on top.

The figure is the GDQuest "Mannequiny" (CC-BY 4.0, GDQuest and contributors - github.com/GDQuest/godot-3d-mannequin),
a male mannequin.  (The older Xbot, from the three.js examples, is still here as MODELS["xbot"].)"""
import math
from panda3d.core import loadPrcFileData
loadPrcFileData("", "interpolate-frames 1")          # (smooth in-between frames: we set the frames ourselves)
from direct.actor.Actor import Actor
from panda3d.core import (GeomVertexFormat, GeomVertexArrayFormat, GeomVertexWriter, GeomVertexReader, Geom,
                          InternalName, ColorAttrib, TextNode)

import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
# Each model: its file, how tall it is, and for each joint we pose: (its name, which of H/P/R to turn, which way
# is "forward" / "bends").  Both models face -Y in their own frame.
MODELS = {
    "mannequin": {"file": os.path.join(HERE, "models", "mannequin.glb"), "walk": "walk", "make_walk": True,
                  "smooth_file": os.path.join(HERE, "models", "footballer.glb"),
                  "smooth": True,
                  "run_range": (2, 17), "run_offset": 10.5, "scale": 1.02,
                  "joints": {"thigh_r": ("thigh.r", 2, -1), "knee_r": ("calf.r", 1, 1),
                             "thigh_l": ("thigh.l", 2, 1), "knee_l": ("calf.l", 1, 1),
                             "spine": ("spine_01", 1, 1), "neck": ("neck_01", 1, 1),
                             "head_turn": ("head", 0, -1),
                             "arm_r": ("upperarm.r", 2, 1), "arm_l": ("upperarm.l", 2, -1)},
                  "number_joint": "spine_02", "run_steps": 2 / 0.633},
    "xbot": {"file": os.path.join(HERE, "models", "Xbot.glb"), "walk": "walk", "scale": 1.08,
             "joints": {"thigh_r": ("mixamorig:RightUpLeg", 1, -1), "knee_r": ("mixamorig:RightLeg", 1, 1),
                        "thigh_l": ("mixamorig:LeftUpLeg", 1, -1), "knee_l": ("mixamorig:LeftLeg", 1, 1),
                        "spine": ("mixamorig:Spine", 1, 1), "neck": ("mixamorig:Neck", 1, 1),
                        "head_turn": ("mixamorig:Head", 0, 1)},
             "number_joint": "mixamorig:Spine2", "run_steps": 3.0, "run_range": (0, 21), "run_offset": 0.0},
}
MODEL = "mannequin"


def C(rgb):
    return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, 1.0)


def _kit_colour(kit, x, y, z, ax):
    """The shirt's colour at this point of the body (bind pose, metres): its pattern (broadcast3d/kits.py)."""
    shirt, trim = C(kit["shirt"]), C(kit.get("trim", kit["shirt"]))
    pat = kit.get("pattern")
    torso = ax < 0.24
    if pat == "sleeves":
        return shirt if torso else trim
    if not torso:
        return shirt
    if pat == "hoops":
        return trim if int((z - 0.97) / 0.105) % 2 else shirt
    if pat == "stripes":
        return trim if int((x + 0.5) / 0.075) % 2 else shirt
    if pat == "pinstripe":                                              # (too fine for the figure: a hint of it)
        k = 0.22 if ((x + 0.5) % 0.07) < 0.018 else 0.0
        return tuple(shirt[i] * (1 - k) + trim[i] * k for i in range(4))
    if pat == "band":
        return trim if 1.24 < z < 1.33 else shirt
    if pat == "halves":
        return trim if x > 0 else shirt
    if pat == "sash":                                                  # (left shoulder down to the right hip)
        return trim if abs(x * (1 if y < 0 else -1) - (z - 1.18) * 0.85) < 0.07 else shirt
    return shirt


def paint(actor, kit, skin, hair):
    """Colour each vertex by where it sits on the body (bind pose): boots, socks (and their tops), skin, shorts,
    shirt (with its pattern, collar and cuffs), head.  Keepers: long sleeves and gloves."""
    shorts, socks = C(kit["shorts"]), C(kit["socks"])
    sk, hr, boot = C(skin), C(hair), C((22, 22, 24))
    trim = C(kit.get("trim", kit["shirt"]))
    socktop = C(kit["socktop"]) if kit.get("socktop") else socks
    keeper = kit.get("keeper", False)
    gloves = C((235, 235, 235)) if sum(kit["shirt"]) < 600 else C((40, 40, 44))
    for np in actor.findAllMatches("**/+GeomNode"):
        gn = np.node()
        mat = np.getMat(actor)
        for gi in range(gn.getNumGeoms()):
            geom = gn.modifyGeom(gi)
            vd = geom.modifyVertexData()
            if not vd.hasColumn(InternalName.getColor()):
                fmt = GeomVertexFormat(vd.getFormat())
                arr = GeomVertexArrayFormat()
                arr.addColumn(InternalName.getColor(), 4, Geom.NT_float32, Geom.C_color)
                fmt.addArray(arr)
                vd = vd.convertTo(GeomVertexFormat.registerFormat(fmt))
                geom.setVertexData(vd)
                vd = geom.modifyVertexData()
            rd = GeomVertexReader(vd, "vertex")
            cw = GeomVertexWriter(vd, "color")
            uw0 = GeomVertexWriter(vd, "texcoord.0")                       # (where each point is on the standing
            uw1 = GeomVertexWriter(vd, "texcoord.1")                       #  body: the shader draws the kit from it)
            while not rd.isAtEnd():
                v = mat.xformPoint(rd.getData3())
                x, y, z = v[0], v[1], v[2] / 1.0
                uw0.setData2(x, z)
                uw1.setData2(y, 0.0)
                ax = abs(x)
                if z < 0.075:
                    c = boot
                elif z < 0.40:
                    c = socks
                elif z < 0.46:
                    c = socktop
                elif z < 0.66:
                    c = sk
                elif z < 0.97 and ax < 0.24:
                    c = shorts
                elif z < 1.49 and ax < 0.36:
                    c = trim if (z > 1.43 and ax < 0.09) else _kit_colour(kit, x, y, z, ax)
                elif keeper and z < 1.49 and ax < 0.70:
                    c = _kit_colour(kit, x, y, z, ax)              # (a keeper's long sleeves...)
                elif keeper and z < 1.49:
                    c = gloves                                     # (...and gloves)
                elif z < 1.49 and ax < 0.40:
                    c = trim                                       # the sleeve hem
                elif z >= 1.72 or (z > 1.62 and y > 0.02):
                    c = hr
                else:
                    c = sk
                cw.setData4(*c)
        np.setAttrib(ColorAttrib.makeVertex(), 1)
        np.setMaterialOff(1)
        np.clearTexture()


SMOOTH = "--pieces" not in sys.argv              # (--pieces: the old mannequin, to compare)
# The body: MakeHuman's (mhbody.py: a properly modelled man, on our skeleton moved to his joints), or our own
# rounded one (body.py) with --oldbody.
MHBODY = SMOOTH and "--oldbody" not in sys.argv and os.environ.get("FM_BODY", "mh") == "mh" and \
    os.path.exists(os.path.join(HERE, "models", "mh_body.npz"))
if MHBODY:
    MODELS["mannequin"]["smooth_file"] = os.path.join(HERE, "models", "footballer_mh.glb")
PATTERNS = {None: 0, "hoops": 1, "stripes": 2, "pinstripe": 3, "band": 4, "halves": 5, "sash": 6, "sleeves": 7}


def shader_defaults(render):
    """The kit inputs the lighting shader needs everywhere (off, except on the players)."""
    for k in ("detail_amt", "crowd_amt", "night_on", "mud_amt"):
        render.setShaderInput(k, 0.0)
    render.setShaderInput("detail_scale", 1.0, 1.0)
    render.setShaderInput("kit_on", 0.0)
    for k in ("shirt", "trim", "shorts", "socks", "socktop", "skin", "hair", "gloves"):
        render.setShaderInput("kit_" + k, (1.0, 1.0, 1.0, 1.0))
    render.setShaderInput("kit_boots", (0.09, 0.09, 0.10, 0.0))
    render.setShaderInput("kit_info", (0.0, 0.0, 0.0, 0.0))
    render.setShaderInput("kit_extra", (0.0, 0.0, 0.0, 0.0))


def _back_texture(name, number, colour, outline):
    """His name and number, as printed on the back of his shirt (a texture, read by the shader)."""
    from PIL import Image, ImageDraw, ImageFont
    from panda3d.core import Texture, PNMImage, StringStream
    import io
    W, H = 256, 290
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fdir = os.path.join(HERE, "fonts")
    def font(sz, bold=True):
        for f in ("DejaVuSansCondensed-Bold.ttf", "DejaVuSans-Bold.ttf"):
            for root in (fdir, "/usr/share/fonts/truetype/dejavu"):
                p = os.path.join(root, f)
                if os.path.exists(p):
                    return ImageFont.truetype(p, sz)
        return ImageFont.load_default()
    col = tuple(int(c) for c in colour) + (255,)
    if name:
        sur = name.split()[-1].upper()
        f = font(44)
        while d.textlength(sur, font=f) > W - 20 and f.size > 20:
            f = font(f.size - 2)
        d.text((W / 2, 30), sur, font=f, fill=col, anchor="mm")
    f = font(200)
    d.text((W / 2, 175), str(number), font=f, fill=col, anchor="mm")
    buf = io.BytesIO(); im.save(buf, "PNG")
    t = Texture("back"); pi = PNMImage(); pi.read(StringStream(buf.getvalue()), "back.png"); t.load(pi)
    return t


def _face(name, number, skin):
    """His own face (MakeHuman's face sliders, mhbody.py FACE_SLIDERS), picked from his name - most features
    near average, a few strong ones - and how much of MakeHuman's African / Asian face shape, from his skin tone
    (with some spread: faces and skin tones don't match one to one)."""
    import random
    import zlib
    r = random.Random(zlib.crc32(f"face-{name}-{number}".encode()))
    sliders = [max(-1.0, min(1.0, r.gauss(0.0, 0.6))) for _ in range(21)]
    sliders[19] *= 0.6                                  # (head shape: gently - his hair sits on it)
    lum = (0.30 * skin[0] + 0.59 * skin[1] + 0.11 * skin[2]) / 255.0
    af = max(0.0, min(1.0, (0.62 - lum) / 0.30)) * (0.65 + 0.3 * r.random())
    asn = 0.25 * r.random() if 0.45 < lum < 0.75 else 0.0
    return sliders, (af, asn)


# Metres a stride cycle (two steps) covers: the walk's measured on him; the run's a compromise - its foot on
# the ground goes back at a speed that would need ~4.5 m a cycle (far too slow a cadence), so 3.6.
WALK_CYCLE, RUN_CYCLE = 1.05, 3.6


# Height and breadth by position: Big-5 league squads average ~1.89 m for keepers, ~1.86 centre-backs, ~1.80
# full-backs, ~1.80 midfielders, ~1.77 wingers, ~1.83 strikers (CIES Football Observatory, "Player height by
# position"); centre-backs and target men a little broader, wingers slighter.
POSITION_BUILD = {"gk": (1.895, 1.03), "cb": (1.86, 1.04), "fb": (1.795, 0.98), "dm": (1.82, 1.02),
                  "cm": (1.80, 1.0), "am": (1.775, 0.97), "w": (1.765, 0.96), "st": (1.83, 1.02)}


def _pos_group(role, keeper):
    if keeper or role == "GK":
        return "gk"
    r = (role or "").upper()
    if r.endswith("CB") or r == "SW":
        return "cb"
    if r in ("LB", "RB", "LWB", "RWB"):
        return "fb"
    if r in ("DM", "CDM", "LDM", "RDM"):
        return "dm"
    if r in ("AM", "CAM", "LAM", "RAM"):
        return "am"
    if r in ("LW", "RW", "LM", "RM"):
        return "w"
    if r.rstrip("0123456789") in ("ST", "CF", "LS", "RS", "LF", "RF", "FW"):
        return "st"
    return "cm" if r else None


OWN_RUNS = "--oldrun" not in sys.argv          # (--oldrun: the mannequin's own run, to compare)
SPEEDS = [("walk", 1.4), ("jog", 3.0), ("run2", 5.5), ("sprint", 8.0)]


def _speed_weights(s):
    """How much of each gait at this speed (m/s): all walk up to 1.4, all jog at 3, ... blended between."""
    if s <= SPEEDS[0][1]:
        return {"walk": 1.0}
    for (a, sa), (b, sb) in zip(SPEEDS, SPEEDS[1:]):
        if s <= sb:
            t = (s - sa) / (sb - sa)
            t = t * t * (3 - 2 * t)
            return {a: 1 - t, b: t}
    return {SPEEDS[-1][0]: 1.0}


class AnimPlayer:
    def __init__(self, parent, kit, number, skin, hair, keeper=False, model=MODEL, name=None, crest=None,
                 height=None, role=None):
        self.cfg = MODELS[model]
        self.root = parent.attachNewNode("player")
        self.a = Actor(self.cfg["file"] if not (self.cfg.get("smooth") and SMOOTH) else self.cfg["smooth_file"])
        self.a.reparentTo(self.root)
        # His height (the model stands ~1.82 m) and build: real squads average ~1.81 m (outfield, s.d. ~6.5 cm),
        # keepers ~1.90 m (CIES Football Observatory, Big-5 league squads).  Given, or picked from his name.
        import zlib
        seed = zlib.crc32(f"{name}-{number}".encode())
        self.seed = seed
        if height is None:
            z = ((seed % 1000) / 1000.0 + ((seed // 1000) % 1000) / 1000.0 + ((seed // 10 ** 6) % 1000) / 1000.0 - 1.5) * 2.0
            mean, broad = POSITION_BUILD.get(_pos_group(role, keeper), (1.81, 1.0))
            height = mean + (0.04 if keeper else 0.055) * z
        else:
            broad = POSITION_BUILD.get(_pos_group(role, keeper), (1.81, 1.0))[1]
        build = (0.96 + 0.08 * (((seed // 7) % 100) / 100.0)) * broad
        k = self.cfg["scale"] * height / 1.82
        self.a.setScale(k * build, k * build, k)
        self.stride_k = k                           # (his strides are as long as he's tall)
        self.height = height
        self.a.setH(180)                    # (the model faces -Y; the root faces the way he's running, +Y)
        paint(self.a, kit, skin, hair)
        if self.cfg.get("smooth") and SMOOTH:                # (a smooth body instead of the mannequin's pieces)
            import body
            body.attach(self.a, "mh" if MHBODY else None,
                        _face(name, number, skin) if MHBODY and os.environ.get("FM_FACES") != "0" else None)
        # The kit is drawn by the lighting shader, pixel by pixel (crisp stripes, hoops, sock tops), with his
        # name and number on his back and the club crest on his chest.
        r = self.root
        r.setShaderInput("kit_on", 1.0)
        for k, c in (("shirt", kit["shirt"]), ("trim", kit.get("trim", kit["shirt"])), ("shorts", kit["shorts"]),
                     ("socks", kit["socks"]), ("socktop", kit.get("socktop") or kit["socks"]), ("skin", skin),
                     ("hair", hair), ("gloves", (235, 235, 235) if sum(kit["shirt"]) < 600 else (40, 40, 44))):
            r.setShaderInput("kit_" + k, C(c))
        from panda3d.core import TextureStage, Texture
        st0 = TextureStage("back"); st0.setTexcoordName("0")              # (the shader reads the body positions
        self.a.setTexture(st0, _back_texture(name, number, kit.get("number", (255, 255, 255)),
                                                              None), 2)
        ct = None
        if crest and os.path.exists(crest):
            from panda3d.core import Filename
            ct = Texture("crest"); ct.read(Filename.fromOsSpecific(crest))
        if ct is None:
            ct = Texture("none"); ct.setup2dTexture(1, 1, Texture.T_unsigned_byte, Texture.F_rgba)
            ct.setRamImage(b"\x00\x00\x00\x00")
        st1 = TextureStage("crest"); st1.setSort(1); st1.setTexcoordName("1")   #  through these two stages)
        self.a.setTexture(st1, ct, 2)
        hs = zlib.crc32(f"hair{name}{number}".encode())
        # Boots: about half the players in black, the rest in white or a bright colour (as on any pitch now);
        # officials, managers and the bench in black.
        bs = zlib.crc32(f"boots{name}{number}".encode()) % 20
        bright = [(240, 240, 240), (240, 240, 240), (255, 120, 30), (40, 200, 190), (190, 240, 60), (230, 50, 60),
                  (60, 120, 240), (250, 220, 50), (245, 90, 170), (240, 240, 240)]
        if bs < 10 or kit.get("trousers") or not name:
            r.setShaderInput("kit_boots", (0.09, 0.09, 0.10, 0.0))
        else:
            r.setShaderInput("kit_boots", C(bright[bs - 10])[:3] + (1.0,))
        # His haircut (0 a crop, 1 a buzz cut, 2 longer, 3 short sides and a quiff, 4 curls, 5 bald) and his
        # beard (0 clean-shaven, 1 stubble, 2 a full beard).
        h100 = hs % 100
        cut = 0 if h100 < 30 else 3 if h100 < 55 else 1 if h100 < 70 else 4 if h100 < 82 else 2 if h100 < 92 else 5
        bd = (hs // 100) % 10
        style = cut + 8 * (0 if bd < 5 else 1 if bd < 8 else 2)
        if self.cfg.get("smooth") and SMOOTH and cut in (0, 2, 3, 4):
            import body
            body.attach_hair(self.a, {0: "crop", 2: "long", 3: "quiff", 4: "curls"}[cut], "mh" if MHBODY else None)
        r.setShaderInput("kit_info", (PATTERNS.get(kit.get("pattern"), 0), 1.0 if kit.get("keeper") else 0.0,
                                      1.0 if crest else 0.0, float(style)))
        # A November game: about a third of outfield players in long sleeves, a few in black gloves too.
        ls = kit.get("long_sleeves")
        gl = 0.0
        if ls is None and not kit.get("keeper") and name and not str(name).startswith(("sub", "steward")):
            ls = (hs // 100) % 10 < 3
            gl = 1.0 if (hs // 1000) % 10 < 1 or (ls and (hs // 1000) % 10 < 4) else 0.0
        if gl:
            r.setShaderInput("kit_gloves", C((28, 28, 30)))
        r.setShaderInput("kit_extra", (float(kit.get("collar", 0)), 1.0 if kit.get("trousers") else 0.0,
                                       1.0 if ls else 0.0, gl))
        self.num = None
        self.action_names = []
        if self.cfg.get("make_walk"):
            import gait
            if MHBODY:                                      # (his own bone lengths, in every movement)
                gait.BIND_POS = True
            elif self.cfg.get("smooth") and SMOOTH:          # (the footballer's longer arms, in every movement)
                from skeleton import LIMB_SCALE
                gait.LIMB_SCALE = LIMB_SCALE
            made = gait.add_all(self.a)                     # (the walk and every action: built from real figures)
            self.action_names = [n for n in made if n not in ("walk", "idle", "run") and n not in gait.LOOPS and n not in gait.RUNS]
        self.loco_names = [n for n in ["idle", "run"] + ([self.cfg["walk"]] if self.cfg["walk"] else [])]
        if self.cfg.get("make_walk"):
            import gait
            self.loco_names += list(gait.LOOPS) + list(gait.RUNS)
        self.mood = None                    # (after a goal: "scorer", "joy" or "sad")
        self.still_t = 0.0                  # (how long he's been standing still)
        self.sad_pose = "hips" if sum(map(ord, str(number))) % 2 else "knees"
        self.a.enableBlend()
        self.loops = ["idle", "run"] + ([self.cfg["walk"]] if self.cfg["walk"] else [])
        for n in self.loco_names + self.action_names:
            self.a.pose(n, 0)
            self.a.setControlEffect(n, 0.0)
        self.loco = {"idle": 1.0}
        self.cur = (None, 0.0, 0.0)
        self.ready = 0.0
        self.nf = {n: self.a.getNumFrames(n) for n in self.loco_names}
        self.phase = 0.0                    # where he is in his stride (0..1 = two steps), walk and run in step
        self.t_idle = 0.0
        self.h = None
        self.sp = 0.0
        self.ctl = {}                       # joints we're posing by hand (kicks, headers), while we do
        self.lift = 0.0
        self.keeper = keeper
        self.head = None                    # (the head, turned to watch the ball)
        self.look = 0.0
        self.roll = 0.0                     # (a keeper's dive: tipped over sideways...)
        self.roll_side = 1

    # --- kicks, shots, touches, headers, tackles, a keeper's set position and dives -------------------------
    # Each is a whole-body animation built in gait.py (from real kicking / gait figures), blended over the
    # running: act() picks it and how far into it he is; the keeper's dive also tips his whole body over.
    JUMP = {"header": (0.30, 0.30)}          # (a header: off the ground - height m, and how long either side)
    # The dive: (seconds, degrees tipped over, metres off the ground) - he springs, flies, lands on his side.
    DIVE_ROOT = [(0.00, 0, 0.00), (0.12, 22, 0.28), (0.32, 70, 0.50), (0.50, 84, 0.30), (0.60, 86, 0.06)]
    RECOVER_ROOT = [(0.00, 86, 0.06), (0.25, 70, 0.0), (0.45, 25, 0.0), (0.85, 0, 0.0), (1.20, 0, 0.0)]

    def _mix(self):
        """Set the blend: the action (if any) at its weight, the walk / run / stand sharing the rest."""
        name, w, frame = self.cur
        want = {n: 0.0 for n in self.action_names}
        if name:
            want[name] = w
            self.a.pose(name, frame)
        for n, lw in self.loco.items():
            want[n] = lw * (1.0 - w)
        last = getattr(self, "_weights", {})
        for n, wt in want.items():                                            # (only tell Panda what's changed)
            if abs(last.get(n, -1.0) - wt) > 1e-4:
                self.a.setControlEffect(n, wt)
        self._weights = want

    def _curve(self, keys, t):
        t = max(keys[0][0], min(keys[-1][0], t))
        for (t0, r0, l0), (t1, r1, l1) in zip(keys, keys[1:]):
            if t <= t1:
                k = (t - t0) / max(1e-6, t1 - t0)
                k = k * k * (3 - 2 * k)
                return r0 + (r1 - r0) * k, l0 + (l1 - l0) * k
        return keys[-1][1], keys[-1][2]

    def dive(self, stage, t, side):
        """A keeper's dive: stage "diving" / "recover", t seconds into it, side +1 = to his right, -1 = left."""
        import gait
        name = ("dive" if stage == "diving" else "recover") + ("" if side > 0 else "_m")
        t0, t1 = gait.SPANS[name]
        self.roll, self.lift = self._curve(self.DIVE_ROOT if stage == "diving" else self.RECOVER_ROOT, t)
        self.roll_side = side
        self.ready = 0.0
        self.cur = (name, 1.0, max(0.0, min(t1 - t0, t - t0)) * 30.0)
        self._mix()

    def _moves(self, vel, sp, dt):
        """Sharp cuts and stopping dead, seen from how he's moving (the last ~0.3 s): played as short actions
        (gait "cut" / "brake") over his running, when nothing else is happening."""
        self.clock = getattr(self, "clock", 0.0) + dt
        hist = getattr(self, "_hist", None)
        if hist is None:
            hist = self._hist = []
        hd = math.atan2(vel[1], vel[0]) if vel is not None and sp > 0.5 else None
        hist.append((self.clock, sp, hd))
        while hist and hist[0][0] < self.clock - 0.45:
            hist.pop(0)
        auto = getattr(self, "auto", None)
        if auto and self.clock - auto[1] > 0.9:
            self.auto = auto = None
        if auto or len(hist) < 4 or not self.cfg.get("make_walk"):
            return
        old = [h for h in hist if h[0] <= self.clock - 0.25]
        if not old:
            return
        _, sp0, hd0 = old[-1]
        if hd is not None and hd0 is not None and sp > 3.0 and sp0 > 3.0:
            turn = (math.degrees(hd - hd0) + 180) % 360 - 180
            if abs(turn) > 40:                                                # (a cut: the outside foot plants)
                self.auto = ("cut" if turn > 0 else "cut_m", self.clock)
                return
        if sp0 > 4.0 and (sp0 - sp) / 0.25 > 6.0:                            # (stopping dead: braking hard)
            self.auto = ("brake" if int(self.clock * 7) % 2 else "brake_m", self.clock)

    def act(self, kind, t, left=False):
        """Pose an action: kind = "kick" / "shot" / "touch" / "header" / "tackle" / "ready", t = seconds from the
        moment the ball is struck (negative = the wind-up); left = with his left foot.  None: just running."""
        import gait
        self.roll = 0.0
        self.lift = 0.0
        if kind == "ready":                                                 # (a keeper's set position: eases in)
            self.ready = min(1.0, self.ready + 0.06)
        else:
            self.ready = max(0.0, self.ready - 0.08)                        # (...and out)
        name = kind + ("_m" if left and (kind + "_m") in gait.SPANS else "") if kind else None
        if kind == "ready" or (name not in gait.SPANS and self.ready > 0):
            self.cur = ("ready", self.ready * 0.9, 0.0)
        elif name in gait.SPANS and gait.SPANS[name][0] <= t <= gait.SPANS[name][1]:
            t0, t1 = gait.SPANS[name]
            w = max(0.0, min(1.0, (t - t0) / 0.08, (t1 - t) / 0.12)) * gait.WEIGHT.get(kind, 1.0)
            self.cur = (name, w, (t - t0) * 30.0)
            h, wd = self.JUMP.get(kind, (0.0, 1.0))
            if h > 0:
                self.lift = h * max(0.0, math.cos(min(1.0, abs(t) / wd) * math.pi / 2))
        elif kind is None and getattr(self, "auto", None) and self.auto[0] in gait.SPANS:
            nm, t_start = self.auto                                         # (a cut or a stop he's making)
            t0, t1 = gait.SPANS[nm]
            ta = t0 + 0.08 + (self.clock - t_start)
            if ta > t1:
                self.auto = None
                self.cur = (None, 0.0, 0.0)
            else:
                w = max(0.0, min(1.0, (ta - t0) / 0.08, (t1 - ta) / 0.15)) * gait.WEIGHT.get(nm.split("_")[0], 1.0)
                self.cur = (nm, w, (ta - t0) * 30.0)
        else:
            self.cur = (None, 0.0, 0.0)
        self._mix()
        self.root.setZ(self.lift)

    def update(self, x, y, fx, fy, speed, dt, active=True, vel=None, ball=None):
        """Place him, face him the way he's facing, and pick his gait from how fast (and which way) he's moving:
        standing, walking, jogging, sprinting - blending the standing and running animations, at a stride rate
        that suits the speed (real players: about 2 steps a second walking, 3 jogging, 4-4.5 sprinting) - and
        running backwards when he's backing off.  ball: (x, y) - he turns his head to watch it."""
        if not active:
            self.root.hide(); return
        self.root.show()
        self.root.setPos(x, y, self.lift)
        h = math.degrees(math.atan2(-fx, fy))
        if self.h is None:
            self.h = h
        dh = (h - self.h + 180) % 360 - 180
        turn = dh * min(1.0, dt * 9)
        self.h += turn
        sp = speed / 10.0                                                     # m/s
        # Leaning: into a turn (as a cyclist does: tan(lean) = speed x turning rate / g) and forward as he
        # speeds up, back as he brakes.  Eased, and kept to what players actually do (~15-20 deg at most).
        w = math.radians(turn) / max(dt, 1e-3)
        lean_r = -math.degrees(math.atan(self.sp * w / 9.81))
        acc = (sp - self.sp) / max(dt, 1e-3) * min(1.0, dt * 6)
        lean_p = -max(-8.0, min(13.0, acc * 2.4))                          # (driving away: low; braking: back)
        self.lean_r = getattr(self, "lean_r", 0.0) + (max(-18.0, min(18.0, lean_r)) - getattr(self, "lean_r", 0.0)) * min(1.0, dt * 6)
        self.lean_p = getattr(self, "lean_p", 0.0) + (lean_p - getattr(self, "lean_p", 0.0)) * min(1.0, dt * 5)
        if self.roll > 1:                                                     # (a dive: that tips him over instead)
            self.lean_r = self.lean_p = 0.0
        self.root.setHpr(self.h, self.lean_p, self.roll * self.roll_side + self.lean_r)
        self.sp += (sp - self.sp) * min(1.0, dt * 6)
        s = self.sp
        self._moves(vel, sp, dt)
        if self.roll > 5:
            sp = s = 0.0                                                      # (in the air: no running)
        # Which way he's moving against the way he faces: forwards (walk / run), sideways (side-steps), or
        # backwards (backpedalling).  Moving fast across or away from the way he faces, a real player turns
        # his hips and runs (and looks back over his shoulder) - so the body turns towards the way he's going.
        fwd, rgt = 1.0, 0.0
        if vel is not None and s > 0.3 and self.cfg.get("make_walk"):
            hd = math.radians(self.h)
            vl = max(0.1, math.hypot(*vel))
            fwd = (vel[0] * -math.sin(hd) + vel[1] * math.cos(hd)) / vl
            rgt = (vel[0] * math.cos(hd) + vel[1] * math.sin(hd)) / vl
        ang = math.degrees(math.atan2(rgt, fwd))                             # (0 ahead, +90 to his right)
        lim = 2.0 if abs(ang) > 120 else 2.4                                  # (faster than a backpedal or a
        self.turned = s > lim - (0.3 if getattr(self, "turned", False) else 0.0)  #  jockey: he turns and runs)
        want_off = ang if (self.turned and abs(ang) > 30) else 0.0
        self.off = getattr(self, "off", 0.0)
        self.off += ((want_off - self.off + 180) % 360 - 180) * min(1.0, dt * 5)
        if abs(self.off) > 0.5:
            self.root.setH(self.h - self.off)                                 # (Panda turns anticlockwise)
        res = math.radians(ang - self.off)                                    # (what's left: stepped)
        f2, r2 = math.cos(res), math.sin(res)
        w_side, w_back = r2 * r2, max(0.0, -f2) ** 2
        w_fwd = max(0.0, 1.0 - w_side - w_back)
        sm = getattr(self, "_dirw", None) or [w_fwd, w_side, w_back]
        a_ = min(1.0, dt * 8)
        sm = [sm[i] + ([w_fwd, w_side, w_back][i] - sm[i]) * a_ for i in range(3)]
        self._dirw = sm
        w_fwd, w_side, w_back = sm
        side = 1 if r2 > 0 else -1
        # Steps a second, from real players: ~1.75 walking at 1 m/s, ~2.4 jogging at 2.5 m/s, ~4 sprinting at 8 m/s.
        import gait as _g
        self.ph_side = (getattr(self, "ph_side", 0.0) + dt * s / _g.CYCLE_SIDE) % 1.0      # (feet planted:
        self.ph_back = (getattr(self, "ph_back", 0.0) + dt * s / _g.CYCLE_BACK) % 1.0      #  cycles at his speed)
        self.t_idle = (self.t_idle + dt * 30) % 1800.0
        self.still_t = self.still_t + dt if s < 1.0 else 0.0
        own_runs = self.cfg.get("make_walk") and OWN_RUNS
        if own_runs:
            # walking, jogging, running, sprinting (gait.RUNS - our own, feet planted), each blended into the
            # next by speed, and the standing pose below a slow walk
            ws = _speed_weights(s)
            w_walk = ws.get("walk", 0.0) * min(1.0, s / 0.6)
            w_run = 0.0
        else:
            ws = {}
            w_run = min(1.0, max(0.0, (s - 1.8) / 2.7)) ** 0.9                # (a jog: walk and run blended)
            w_walk = (1 - w_run) * min(1.0, s / 0.6) if self.cfg["walk"] else 0.0
        w_runs = {k: ws.get(k, 0.0) for k in ("jog", "run2", "sprint")}
        w_move = w_walk + w_run + sum(w_runs.values())
        # The stride cycle (two steps) run at his speed over the length of a stride, so the foot on the ground
        # stays put (each gait's cycle length measured on him, blended by how much of each he's doing).
        if self.cfg.get("make_walk"):
            import gait as _g
            stride = self.stride_k * (w_walk * WALK_CYCLE + w_run * RUN_CYCLE +
                                      sum(w * _g.RUN_CYCLES.get(k, 3.0) for k, w in w_runs.items()))
            cyc = min(2.4, s / stride) if stride > 0.05 else 0.6
        else:
            cyc = (1.3 + 0.45 * s if s < 2.5 else 1.65 + 0.3 * s) / 2.0
        self.phase = (self.phase + cyc * dt) % 1.0
        w_idle = max(0.0, 1 - w_move)
        # turning on the spot (or nearly): little steps round, not a spin on the spot
        rate = abs(turn) / max(dt, 1e-3)
        w_turn = 0.0
        if self.cfg.get("make_walk"):
            want_t = min(1.0, max(0.0, (rate - 35.0) / 110.0)) * max(0.0, 1.0 - s / 1.2)
            self.w_turn = getattr(self, "w_turn", 0.0) + (want_t - getattr(self, "w_turn", 0.0)) * min(1.0, dt * 8)
            w_turn = self.w_turn * w_idle
            w_idle -= w_turn
            self.ph_turn = (getattr(self, "ph_turn", 0.0) + dt * 1.7) % 1.0
        r0, r1 = self.cfg["run_range"]                                        # (the frames that make one stride)
        run_f = (self.phase * (r1 - r0) + self.cfg["run_offset"]) % (r1 - r0)
        stand, walk, run = getattr(self, "force_stand", None) or "idle", self.cfg["walk"], "run"
        special = None
        if self.mood and self.cfg.get("make_walk"):                           # (after a goal: celebrating, or not)
            happy = "cheer" if self.still_t < 3.5 else "clap"                 # (then he applauds the fans)
            stand = {"scorer": happy, "joy": happy, "sad": self.sad_pose}.get(self.mood, "idle")
            walk = "walk_sad" if self.mood == "sad" else walk
            special = "run_arms" if self.mood == "scorer" else None
            w_fwd, w_side, w_back = 1.0, 0.0, 0.0
        if getattr(self, "calling", False) and self.cfg.get("make_walk"):
            special = "run_call"
        if special:                                                           # (the mannequin's run, arms busy)
            run = special
            w_run += sum(w_runs.values())
            w_runs = {k: 0.0 for k in w_runs}
        self.loco = {n: 0.0 for n in self.loco_names}
        self.loco[stand] = w_idle
        if stand == "idle" and self.cfg.get("make_walk") and w_idle > 0.0:
            # standing about: shifting his weight now and then; and with play far off and nothing to do for a
            # while, some players put their hands on their hips
            far = ball is not None and math.hypot(ball[0] - x, ball[1] - y) > 35.0
            rester = (self.seed % 3) == 0
            want_r = 1.0 if (far and rester and self.still_t > 4.0) else 0.0
            self.w_rest = getattr(self, "w_rest", 0.0) + (want_r - getattr(self, "w_rest", 0.0)) * min(1.0, dt * 1.5)
            t_sh = (self.t_idle + (self.seed % 240)) % 240
            self.loco["shift"] = w_idle * 0.65 * (1 - self.w_rest)
            self.loco["rest"] = w_idle * self.w_rest
            self.loco[stand] = w_idle * 0.35 * (1 - self.w_rest)
            self.a.pose("shift", t_sh)
            self.a.pose("rest", t_sh)
        if w_turn > 0.0:
            self.loco["turnstep"] = w_turn
            self.a.pose("turnstep", self.ph_turn * self.nf["turnstep"])
        self.loco[run] = w_run * w_fwd
        self.a.pose(stand, self.t_idle % self.nf[stand])
        self.a.pose(run, (r0 + run_f) if run == "run" else run_f)
        for k, w in w_runs.items():
            if w > 0.0:
                self.loco[k] = w * w_fwd
                self.a.pose(k, self.phase * self.nf[k])
        if walk:
            self.loco[walk] = w_walk * w_fwd
            self.a.pose(walk, self.phase * self.nf[walk])
        if self.cfg.get("make_walk"):
            sh = "shuffle" if side > 0 else "shuffle_m"
            self.loco[sh] = w_move * w_side
            self.a.pose(sh, self.ph_side * self.nf[sh])
            self.loco["backpedal"] = w_move * w_back
            self.a.pose("backpedal", self.ph_back * self.nf["backpedal"])
        else:
            self.loco[run] += w_run * (w_side + w_back)
        self._mix()
        if ball is not None:
            self._watch(ball, x, y, dt)

    def hands(self):
        """Where the ball sits when he holds it in both hands: between his palms (in the world)."""
        if not hasattr(self, "_hj"):
            self._hj = (self.a.exposeJoint(None, "modelRoot", "hand.r"), self.a.exposeJoint(None, "modelRoot", "hand.l"))
        r = self.root.getParent()
        a, b = self._hj[0].getPos(r), self._hj[1].getPos(r)
        hd = math.radians(self.h or 0.0)
        mid = (a + b) * 0.5
        return mid[0] - math.sin(hd) * 0.06, mid[1] + math.cos(hd) * 0.06, mid[2] + 0.04

    def _watch(self, ball, x, y, dt):
        """Turn his head towards the ball (as far as a neck goes)."""
        key = "head_turn"
        if key not in self.cfg["joints"]:
            return
        if self.head is None:
            name = self.cfg["joints"][key][0]
            c = self.a.controlJoint(None, "modelRoot", name)
            self.head = (c, c.getHpr())
        dx, dy = ball[0] - x, ball[1] - y
        if dx * dx + dy * dy < 0.5:
            want = 0.0
        else:
            want = (math.degrees(math.atan2(-dx, dy)) - self.h + getattr(self, "off", 0.0) + 180) % 360 - 180
            want = max(-70.0, min(70.0, want))
        self.look += (want - self.look) * min(1.0, dt * 5)
        c, base = self.head
        _, axis, sign = self.cfg["joints"][key]
        hpr = [base[0], base[1], base[2]]
        hpr[axis] += sign * self.look
        c.setHpr(*hpr)
