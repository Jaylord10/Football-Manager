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
HERE = os.path.dirname(os.path.abspath(__file__))
# Each model: its file, how tall it is, and for each joint we pose: (its name, which of H/P/R to turn, which way
# is "forward" / "bends").  Both models face -Y in their own frame.
MODELS = {
    "mannequin": {"file": os.path.join(HERE, "models", "mannequin.glb"), "walk": "walk", "make_walk": True,
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
            while not rd.isAtEnd():
                v = mat.xformPoint(rd.getData3())
                x, y, z = v[0], v[1], v[2] / 1.0
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
        tn = TextNode("num"); tn.setText(str(number)); tn.setAlign(TextNode.ACenter)
        tn.setTextColor(*C(kit.get("number", (255, 255, 255))))
        spine = self.a.exposeJoint(None, "modelRoot", self.cfg["number_joint"])     # (still in the bind pose)
        t = self.a.attachNewNode(tn); t.setScale(0.28); t.setH(180)               # (on his back...)
        t.setPos(0, spine.getY(self.a) + 0.135, spine.getZ(self.a) - 0.1)
        t.wrtReparentTo(spine)                              # (...and it leans and twists with his back)
        self.num = t
        self.action_names = []
        if self.cfg.get("make_walk"):
            import gait
            made = gait.add_all(self.a)                     # (the walk and every action: built from real figures)
            self.action_names = [n for n in made if n != "walk"]
        self.a.enableBlend()
        self.loops = ["idle", "run"] + ([self.cfg["walk"]] if self.cfg["walk"] else [])
        for n in self.loops + self.action_names:
            self.a.pose(n, 0)
            self.a.setControlEffect(n, 0.0)
        self.loco = {"idle": 1.0}
        self.cur = (None, 0.0, 0.0)
        self.ready = 0.0
        self.nf = {n: self.a.getNumFrames(n) for n in self.loops}
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
        for n in self.action_names:
            self.a.setControlEffect(n, w if n == name else 0.0)
        if name:
            self.a.pose(name, frame)
        for n, lw in self.loco.items():
            self.a.setControlEffect(n, lw * (1.0 - w))

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
        self.h += dh * min(1.0, dt * 9)
        self.root.setHpr(self.h, 0, self.roll * self.roll_side)               # (tipped over: a keeper's dive)
        sp = speed / 10.0                                                     # m/s
        self.sp += (sp - self.sp) * min(1.0, dt * 6)
        s = self.sp
        if self.roll > 5:
            sp = s = 0.0                                                      # (in the air: no running)
        back = False
        if vel is not None and s > 0.8:                                       # (moving against the way he faces?)
            hd = math.radians(self.h)
            fwd = (vel[0] * -math.sin(hd) + vel[1] * math.cos(hd)) / max(0.1, math.hypot(*vel))
            back = fwd < -0.35
        # Steps a second, from real players: ~1.75 walking at 1 m/s, ~2.4 jogging at 2.5 m/s, ~4 sprinting at 8 m/s.
        steps = 1.3 + 0.45 * s if s < 2.5 else 1.65 + 0.3 * s
        self.phase = (self.phase + steps / 2.0 * dt * (-1 if back else 1)) % 1.0
        self.t_idle = (self.t_idle + dt * 30) % self.nf["idle"]
        w_run = min(1.0, max(0.0, (s - 1.8) / 2.7)) ** 0.9                    # (a jog: walk and run blended)
        if back:
            w_run *= 0.7                                                      # (backing off: shorter steps)
        if self.cfg["walk"]:
            w_walk = (1 - w_run) * min(1.0, s / 0.6)
        else:
            w_walk = 0.0
        w_idle = max(0.0, 1 - w_run - w_walk)
        self.loco = {"idle": w_idle, "run": w_run}
        self.a.pose("idle", self.t_idle)
        r0, r1 = self.cfg["run_range"]                                        # (the frames that make one stride)
        self.a.pose("run", r0 + (self.phase * (r1 - r0) + self.cfg["run_offset"]) % (r1 - r0))
        if self.cfg["walk"]:
            self.loco[self.cfg["walk"]] = w_walk
            self.a.pose(self.cfg["walk"], self.phase * self.nf[self.cfg["walk"]])
        self._mix()
        if ball is not None:
            self._watch(ball, x, y, dt)

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
            want = (math.degrees(math.atan2(-dx, dy)) - self.h + 180) % 360 - 180
            want = max(-70.0, min(70.0, want))
        self.look += (want - self.look) * min(1.0, dt * 5)
        c, base = self.head
        _, axis, sign = self.cfg["joints"][key]
        hpr = [base[0], base[1], base[2]]
        hpr[axis] += sign * self.look
        c.setHpr(*hpr)
