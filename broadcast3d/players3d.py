"""Animated players: a rigged figure (idle / run, and walk where the model has it), painted in the club's kit
by height, with kicks, shots, touches, headers and tackles posed by hand on top.

The figure is the GDQuest "Mannequiny" (CC-BY 4.0, GDQuest and contributors - github.com/GDQuest/godot-3d-mannequin),
a male mannequin.  (The older Xbot, from the three.js examples, is still here as MODELS["xbot"].)"""
import math
from direct.actor.Actor import Actor
from panda3d.core import (GeomVertexFormat, GeomVertexArrayFormat, GeomVertexWriter, GeomVertexReader, Geom,
                          InternalName, ColorAttrib, TextNode)

import os
HERE = os.path.dirname(os.path.abspath(__file__))
# Each model: its file, how tall it is, and for each joint we pose: (its name, which of H/P/R to turn, which way
# is "forward" / "bends").  Both models face -Y in their own frame.
MODELS = {
    "mannequin": {"file": os.path.join(HERE, "models", "mannequin.glb"), "walk": None, "scale": 1.02,
                  "joints": {"thigh_r": ("thigh.r", 2, -1), "knee_r": ("calf.r", 1, 1),
                             "thigh_l": ("thigh.l", 2, 1), "knee_l": ("calf.l", 1, 1),
                             "spine": ("spine_01", 1, 1), "neck": ("neck_01", 1, 1)},
                  "number_joint": "spine_02"},
    "xbot": {"file": os.path.join(HERE, "models", "Xbot.glb"), "walk": "walk", "scale": 1.08,
             "joints": {"thigh_r": ("mixamorig:RightUpLeg", 1, -1), "knee_r": ("mixamorig:RightLeg", 1, 1),
                        "thigh_l": ("mixamorig:LeftUpLeg", 1, -1), "knee_l": ("mixamorig:LeftLeg", 1, 1),
                        "spine": ("mixamorig:Spine", 1, 1), "neck": ("mixamorig:Neck", 1, 1)},
             "number_joint": "mixamorig:Spine2"},
}
MODEL = "mannequin"


def C(rgb):
    return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, 1.0)


def paint(actor, kit, skin, hair):
    """Colour each vertex by where it sits on the body (bind pose): boots, socks, skin, shorts, shirt, head."""
    shirt, shorts, socks = C(kit["shirt"]), C(kit["shorts"]), C(kit["socks"])
    sk, hr, boot = C(skin), C(hair), C((22, 22, 24))
    trim = C(kit.get("trim", kit["shirt"]))
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
            while not rd.isAtEnd():
                v = mat.xformPoint(rd.getData3())
                x, y, z = v[0], v[1], v[2] / 1.0
                ax = abs(x)
                if z < 0.075:
                    c = boot
                elif z < 0.46:
                    c = socks
                elif z < 0.66:
                    c = sk
                elif z < 0.97 and ax < 0.24:
                    c = shorts
                elif z < 1.49 and ax < 0.36:
                    c = trim if (z > 1.43 and ax < 0.09) else shirt
                elif z < 1.49 and ax < 0.40:
                    c = trim                                       # the sleeve hem
                elif z >= 1.72 or (z > 1.62 and y > 0.02):
                    c = hr
                else:
                    c = sk
                cw.setData4(*c)
        np.setAttrib(ColorAttrib.makeVertex(), 1)
        np.setMaterialOff(1)
        np.setTextureOff(1)


class AnimPlayer:
    def __init__(self, parent, kit, number, skin, hair, keeper=False, model=MODEL):
        self.cfg = MODELS[model]
        self.root = parent.attachNewNode("player")
        self.a = Actor(self.cfg["file"])
        self.a.reparentTo(self.root)
        self.a.setScale(self.cfg["scale"])
        self.a.setH(180)                    # (the model faces -Y; the root faces the way he's running, +Y)
        paint(self.a, kit, skin, hair)
        self.a.enableBlend()
        self.loops = ["idle", "run"] + ([self.cfg["walk"]] if self.cfg["walk"] else [])
        for n in self.loops:
            self.a.loop(n)
        tn = TextNode("num"); tn.setText(str(number)); tn.setAlign(TextNode.ACenter)
        tn.setTextColor(*C(kit.get("number", (255, 255, 255))))
        t = self.a.attachNewNode(tn); t.setScale(0.3); t.setPos(0, 0.16, 1.17); t.setH(180)   # (on his back)
        t.setDepthOffset(1)
        self.num = t
        self.h = None
        self.sp = 0.0
        self.ctl = {}                       # joints we're posing by hand (kicks, headers), while we do
        self.lift = 0.0

    # --- kicks, headers, tackles: posed by hand on top of the running animation -------------------------
    # Degrees: thigh + = swung forward, knee + = bent, spine / neck + = leaning forward.  Each pose is a list of
    # (seconds from the moment the ball is struck, {joint: angle}); in between we ease.
    POSES = {
        "kick":   [(-0.30, {"thigh_r": 0, "knee_r": 0, "spine": 0}),
                   (-0.12, {"thigh_r": -28, "knee_r": 95, "spine": 4}),
                   (0.00, {"thigh_r": 38, "knee_r": 12, "spine": 6}),
                   (0.13, {"thigh_r": 48, "knee_r": 8, "spine": 4}),
                   (0.36, {"thigh_r": 0, "knee_r": 0, "spine": 0})],
        "shot":   [(-0.32, {"thigh_r": 0, "knee_r": 0, "spine": 0}),
                   (-0.13, {"thigh_r": -35, "knee_r": 110, "spine": 6}),
                   (0.00, {"thigh_r": 42, "knee_r": 10, "spine": 8}),
                   (0.15, {"thigh_r": 55, "knee_r": 6, "spine": 5}),
                   (0.42, {"thigh_r": 0, "knee_r": 0, "spine": 0})],
        "touch":  [(-0.16, {"thigh_r": 0, "knee_r": 0}),
                   (-0.06, {"thigh_r": -6, "knee_r": 40}),
                   (0.00, {"thigh_r": 18, "knee_r": 18}),
                   (0.16, {"thigh_r": 0, "knee_r": 0})],
        "header": [(-0.28, {"spine": 0, "neck": 0}),
                   (-0.10, {"spine": -16, "neck": -12}),
                   (0.00, {"spine": 18, "neck": 22}),
                   (0.28, {"spine": 0, "neck": 0})],
        "tackle": [(-0.30, {"thigh_l": 0, "knee_l": 0, "spine": 0}),
                   (-0.05, {"thigh_l": 55, "knee_l": 15, "spine": 12}),
                   (0.15, {"thigh_l": 60, "knee_l": 10, "spine": 14}),
                   (0.45, {"thigh_l": 0, "knee_l": 0, "spine": 0})],
    }
    JUMP = {"header": (0.30, 0.30), "tackle": (-0.18, 0.40)}      # (height m, how long either side of the moment)

    def _joint(self, key):
        if key not in self.ctl:
            name = self.cfg["joints"][key][0]
            c = self.a.controlJoint(None, "modelRoot", name)
            self.ctl[key] = (c, c.getHpr())                              # (its resting turn: we add to it)
        return self.ctl[key]

    def act(self, kind, t):
        """Pose an action: kind = "kick" / "shot" / "touch" / "header" / "tackle", t = seconds from the moment
        the ball is struck (negative = the wind-up).  kind None: back to the plain animation."""
        keys = self.POSES.get(kind)
        if keys is None or t < keys[0][0] or t > keys[-1][0]:
            for key in list(self.ctl):
                self.a.releaseJoint("modelRoot", self.cfg["joints"][key][0])
                self.ctl.pop(key)[0].removeNode()
            self.lift = 0.0
            return
        for (t0, a), (t1, b) in zip(keys, keys[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / max(1e-6, t1 - t0)
                k = k * k * (3 - 2 * k)                                         # (ease in and out)
                for j in a:
                    c, base = self._joint(j)
                    _, axis, sign = self.cfg["joints"][j]
                    hpr = [base[0], base[1], base[2]]
                    hpr[axis] += sign * (a[j] + (b[j] - a[j]) * k)
                    c.setHpr(*hpr)
                break
        h, w = self.JUMP.get(kind, (0.0, 1.0))
        self.lift = h * max(0.0, math.cos(min(1.0, abs(t) / w) * math.pi / 2)) if h > 0 else h * max(0.0, 1 - abs(t) / w)

    def update(self, x, y, fx, fy, speed, dt, active=True):
        if not active:
            self.root.hide(); return
        self.root.show()
        self.root.setPos(x, y, self.lift)
        h = math.degrees(math.atan2(-fx, fy))
        if self.h is None:
            self.h = h
        dh = (h - self.h + 180) % 360 - 180
        self.h += dh * min(1.0, dt * 9)
        self.root.setH(self.h)
        sp = speed / 10.0                                                     # m/s
        self.sp += (sp - self.sp) * min(1.0, dt * 6)
        s = self.sp
        if self.cfg["walk"]:
            w_idle = max(0.0, 1 - s / 1.0)
            w_run = min(1.0, max(0.0, (s - 2.0) / 2.0))
            w_walk = max(0.0, 1 - w_idle - w_run)
            self.a.setControlEffect(self.cfg["walk"], w_walk)
            self.a.setPlayRate(max(0.6, min(2.2, s / 1.5)), self.cfg["walk"])
        else:                                                                 # (no walk: a slow run is a jog)
            w_idle = max(0.0, 1 - s / 1.2)
            w_run = 1 - w_idle
        self.a.setControlEffect("idle", w_idle)
        self.a.setControlEffect("run", w_run)
        self.a.setPlayRate(max(0.45, min(1.3, s / 6.5)), "run")
