"""
broadcast3d/mixamo.py
=====================
TEST (Jay, 21 Nov): the Mixamo footballer and his motion-captured moves in place of our hand-made figures.

    python viewer.py ... --mixamo

Every match player keeps his ordinary figure underneath (it still works out everything the viewer asks of it -
where his hands are, his card, his shadow...), but it's hidden and the Mixamo footballer is drawn in its place:

  - standing, jogging, running and sprinting blend into each other by how fast the engine has him going, and
    each move is played at the pace that matches that speed (from how far the motion-capture actor travelled
    in one stride), so his feet grip the grass instead of sliding
  - moving sideways or backwards against the way he faces: the strafes and the backward run
  - striking the ball: the kick
  - anything the pack hasn't got yet (dives, falls, tackles, headers, throws...): the old figure shows instead,
    for now - so this test also shows what's still missing

His kit is his shirt, shorts and socks tinted the club's colours (the model's kit is white).

The model and moves are built by dev/mixamo_build.py from Jay's "Soccer Game Pack" folder into
broadcast3d/models/mixamo_footballer.glb (+ .json: each move's length and how far it travels).
"""

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(HERE, "models", "mixamo_footballer.glb")

# Locomotion: (move, its own speed in m/s) - worked out from the motion capture in build (json)
FORWARD = ["jog_forward", "Standard_Run", "Sprint"]
IDLES = ["Idle", "Idle_1", "Breathing_Idle", "offensive_idle"]   # (each man has his own way of standing)
KICKS = ("kick", "shot", "finish", "pass", "cross", "clear", "dink", "volley", "lob", "chip", "drive")
# Our figure's ways of standing and moving that the motion capture covers itself (standing about, side-steps,
# backpedalling) - anything else of ours (celebrating, clapping, hands on hips / knees, calling for it) is copied
OWN_LOOPS = {"shift", "rest", "shuffle", "shuffle_m", "backpedal", "backwalk", "turnstep"}
CM = 100.0                                   # (the capture is in centimetres)
BRIGHT = 1.5

_info = None

# Our hand-made moves (gait.py: dives, headers, tackles, throw-ins, appeals, celebrations...) are made for our own
# skeleton.  For anything the Mixamo pack hasn't got, his skeleton copies ours, bone by bone (retargeting): each
# bone of his is turned to point the way ours does.  Ours -> his:
MAP = [("pelvis", "Hips"), ("spine_01", "Spine"), ("spine_02", "Spine2"), ("neck_01", "Neck"), ("head", "Head"),
       ("clavicle.l", "LeftShoulder"), ("upperarm.l", "LeftArm"), ("lowerarm.l", "LeftForeArm"), ("hand.l", "LeftHand"),
       ("clavicle.r", "RightShoulder"), ("upperarm.r", "RightArm"), ("lowerarm.r", "RightForeArm"),
       ("hand.r", "RightHand"),
       ("thigh.l", "LeftUpLeg"), ("calf.l", "LeftLeg"), ("foot.l", "LeftFoot"), ("ball.l", "LeftToeBase"),
       ("thigh.r", "RightUpLeg"), ("calf.r", "RightLeg"), ("foot.r", "RightFoot"), ("ball.r", "RightToeBase")]
# Each bone points at its child (ours, his) - which way it points is what's copied
AIM = {"pelvis": ("spine_01", "Spine"), "spine_01": ("spine_02", "Spine2"), "spine_02": ("neck_01", "Neck"),
       "neck_01": ("head", "Head"), "clavicle.l": ("upperarm.l", "LeftArm"), "upperarm.l": ("lowerarm.l", "LeftForeArm"),
       "lowerarm.l": ("hand.l", "LeftHand"), "hand.l": ("middle_01.l", "LeftHandMiddle1"),
       "clavicle.r": ("upperarm.r", "RightArm"), "upperarm.r": ("lowerarm.r", "RightForeArm"),
       "lowerarm.r": ("hand.r", "RightHand"), "hand.r": ("middle_01.r", "RightHandMiddle1"),
       "thigh.l": ("calf.l", "LeftLeg"), "calf.l": ("foot.l", "LeftFoot"), "foot.l": ("ball.l", "LeftToeBase"),
       "thigh.r": ("calf.r", "RightLeg"), "calf.r": ("foot.r", "RightFoot"), "foot.r": ("ball.r", "RightToeBase")}
# Leaves (no child to aim at): they take the turn their parent took
LEAF_FROM = {"head": "neck_01", "ball.l": "foot.l", "ball.r": "foot.r"}
# His chain, parents first (the joints we pose while retargeting)
CHAIN = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head",
         "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand", "RightShoulder", "RightArm", "RightForeArm", "RightHand",
         "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase", "RightUpLeg", "RightLeg", "RightFoot", "RightToeBase"]
PARENT = {"Spine": "Hips", "Spine1": "Spine", "Spine2": "Spine1", "Neck": "Spine2", "Head": "Neck",
          "LeftShoulder": "Spine2", "LeftArm": "LeftShoulder", "LeftForeArm": "LeftArm", "LeftHand": "LeftForeArm",
          "RightShoulder": "Spine2", "RightArm": "RightShoulder", "RightForeArm": "RightArm", "RightHand": "RightForeArm",
          "LeftUpLeg": "Hips", "LeftLeg": "LeftUpLeg", "LeftFoot": "LeftLeg", "LeftToeBase": "LeftFoot",
          "RightUpLeg": "Hips", "RightLeg": "RightUpLeg", "RightFoot": "RightLeg", "RightToeBase": "RightFoot"}


def info():
    global _info
    if _info is None:
        raw = json.load(open(MODEL.replace(".glb", ".json")))
        _info = {}
        for nm, d in raw.items():
            f0, f1 = d["frames"]
            dur = max(0.1, (f1 - f0) / 30.0)
            dist = max(abs(v) for v in d["drift"].values()) / CM if d["drift"] else 0.0
            _info[nm] = {"dur": dur, "dist": dist, "speed": dist / dur, "frames": int(f1 - f0) + 1}
    return _info


class Retarget:
    """His skeleton copying ours (see MAP).  Worked out once, in both skeletons' rest poses: for each bone, the turn
    that makes ours point the way his does (R), and so the fixed difference between his bone's axes and ours (F).
    Then every frame: his bone's orientation = F x ours.  All in the player's own frame (ap.root)."""

    def __init__(self, mix):
        from panda3d.core import LQuaternionf, LMatrix4f
        self.mix = mix
        ap, a = mix.ap, mix.a
        root = ap.root
        P = "mixamorig5:"
        srcs = set(s for s, _ in MAP) | set(v[0] for v in AIM.values())
        self.sx = {n: ap.a.exposeJoint(None, "modelRoot", n) for n in srcs}
        dsts = set(CHAIN) | set(v[1] for v in AIM.values())
        dx = {n: a.exposeJoint(None, "modelRoot", P + n) for n in dsts}
        ap.a.getPartBundle("modelRoot").forceUpdate()
        a.getPartBundle("modelRoot").forceUpdate()
        qs0 = {n: self.sx[n].getQuat(root) for n in srcs}
        ps0 = {n: self.sx[n].getPos(root) for n in srcs}
        qd0 = {n: dx[n].getQuat(root) for n in dsts}
        pd0 = {n: dx[n].getPos(root) for n in dsts}
        self.R = {}
        self.F = {}
        for s, d in MAP:
            if s in AIM:
                cs, cd = AIM[s]
                vs = ps0[cs] - ps0[s]
                vd = pd0[cd] - pd0[d]
                self.R[s] = _arc(vs, vd)
        for s, d in MAP:
            r = self.R.get(s) or self.R.get(LEAF_FROM.get(s)) or LQuaternionf()
            qt = qs0[s] * r                                   # (ours, turned to point the way his does)
            inv = LQuaternionf(qt); inv.invertInPlace()
            self.F[d] = qd0[d] * inv
        self.src_of = {d: s for s, d in MAP}
        # His hips' parent (the skeleton's root): fixed, from his rest pose
        self.dx = dx
        self.ps0 = ps0["pelvis"]
        self.pd0 = pd0["Hips"]
        self.k = pd0["Hips"].z / max(0.1, ps0["pelvis"].z)  # (his hips are higher or lower than ours)
        self.ctrl = None
        self.rest_local = {}
        self.pw_mat = None
        self.pw_q = None
        for gn in []:
            pass
        for d in dx.values():
            d.removeNode()
        self.dx = None

    def _control(self):
        from panda3d.core import LMatrix4f
        a = self.mix.a
        P = "mixamorig5:"
        root = self.mix.ap.root
        self.ctrl = {}
        for d in CHAIN:
            c = a.controlJoint(None, "modelRoot", P + d)
            self.ctrl[d] = c
            if d not in self.rest_local:
                self.rest_local[d] = (c.getQuat(), c.getMat())
        if self.pw_q is None:
            # The hips' parent, in the player's frame: his rest hips (world) = rest local x parent
            hx = a.exposeJoint(None, "modelRoot", P + "Hips")
            a.getPartBundle("modelRoot").forceUpdate()
            from panda3d.core import LQuaternionf
            lq = LQuaternionf(self.rest_local["Hips"][0]); lq.invertInPlace()
            # (not posed yet: the controlled hips still has its rest value, so the exposed node is the rest pose)
            self.pw_q = lq * hx.getQuat(root)
            m = LMatrix4f(self.rest_local["Hips"][1]); m.invertInPlace()
            self.pw_mat = m * hx.getMat(root)
            self.pw_inv = LMatrix4f(self.pw_mat); self.pw_inv.invertInPlace()
            hx.removeNode()

    def release(self):
        if self.ctrl is None:
            return
        a = self.mix.a
        for d in CHAIN:
            a.releaseJoint("modelRoot", "mixamorig5:" + d)
        for c in self.ctrl.values():
            c.removeNode()
        self.ctrl = None

    def apply(self):
        """Pose him as our figure is posed right now."""
        from panda3d.core import LQuaternionf, Point3
        if self.ctrl is None:
            self._control()
        ap = self.mix.ap
        root = ap.root
        ap.a.getPartBundle("modelRoot").forceUpdate()
        world = {}
        for d in CHAIN:
            parent_q = world[PARENT[d]] if d in PARENT else self.pw_q
            s = self.src_of.get(d)
            if s is None:                                         # (a joint of his we don't have: as at rest)
                lq = self.rest_local[d][0]
                world[d] = lq * parent_q
                self.ctrl[d].setQuat(lq)
                continue
            wq = self.F[d] * self.sx[s].getQuat(root)
            inv = LQuaternionf(parent_q); inv.invertInPlace()
            lq = wq * inv
            self.ctrl[d].setQuat(lq)
            world[d] = wq
        # His hips go where ours go (scaled to his height): crouching, diving, lying on the grass
        ps = self.sx["pelvis"].getPos(root)
        want = self.pd0 + (ps - self.ps0) * self.k
        self.ctrl["Hips"].setPos(self.pw_inv.xformPoint(Point3(want)))


def _arc(a, b):
    """The shortest turn (a quaternion) that takes direction a to direction b."""
    from panda3d.core import LQuaternionf, Vec3
    import math as m
    a = Vec3(a); b = Vec3(b)
    if a.length() < 1e-6 or b.length() < 1e-6:
        return LQuaternionf()
    a.normalize(); b.normalize()
    ax = a.cross(b)
    d = max(-1.0, min(1.0, a.dot(b)))
    q = LQuaternionf()
    if ax.length() < 1e-6:
        if d > 0:
            return q
        ax = a.cross(Vec3(1, 0, 0)) if abs(a.x) < 0.9 else a.cross(Vec3(0, 1, 0))
    ax.normalize()
    q.setFromAxisAngle(m.degrees(m.acos(d)), ax)
    return q


class Mix:
    def __init__(self, ap, kit, keeper=False):
        from direct.actor.Actor import Actor
        from panda3d.core import Filename, OmniBoundingVolume
        self.ap = ap
        self.a = Actor(Filename.fromOsSpecific(MODEL).getFullpath())
        self.a.reparentTo(ap.root)
        b1, b2 = self.a.getTightBounds()
        h = getattr(ap, "height", 1.81)
        k = h / max(0.5, (b2 - b1).z)
        self.a.setScale(k)
        self.a.setH(180)                                       # (the model faces -Y; his root faces +Y)
        for gn in self.a.findAllMatches("**/+GeomNode"):
            gn.node().setBounds(OmniBoundingVolume()); gn.node().setFinal(True)
        self.a.setShaderInput("kit_on", 0.0, priority=10)      # (our lighting shader, but his own pictures - not
                                                               #  our painted kits; skinned on the graphics card)
        self.a.setColorScale(BRIGHT, BRIGHT, BRIGHT, 1.0)      # (our lighting is set up for our painted kits,
        self._kit(kit, keeper)                                 #  which it wraps light round - his pictures need
        self.a.enableBlend()                                   #  a lift to sit alongside)
        self.anims = self.a.getAnimNames()
        self.w = {n: 0.0 for n in self.anims}
        self.phase = 0.0
        self.idle_t = (ap.seed % 97) / 10.0
        idles = [n for n in IDLES if n in self.anims] or [self.anims[0]]
        self.idle = idles[(ap.seed // 3) % len(idles)]
        self.still = set(IDLES) | {"kick_soccerball", "Victory"}
        self.rt = None                                         # (Retarget: made the first time it's needed)
        self.in_rt = False
        ap.a.hide()

    def _kit(self, kit, keeper):
        def c(rgb):
            return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, 1.0)
        for part, key in (("Shirt", "shirt"), ("Shorts", "shorts"), ("Socks", "socks")):
            for np_ in self.a.findAllMatches(f"**/*{part}*"):
                np_.setColorScale(*c(kit.get(key, (230, 230, 230))))

    def update(self, dt, vel):
        ap = self.ap
        cur = getattr(ap, "cur", (None, 0.0, 0.0))
        name, wgt, frame = cur
        import gait
        moods = sum(w for n, w in getattr(ap, "loco", {}).items() if n in gait.LOOPS and n not in OWN_LOOPS)
        special = (name is not None and wgt > 0.2) or getattr(ap, "roll", 0.0) > 1.0 \
            or getattr(ap, "lift", 0.0) > 0.05 or moods > 0.3 or getattr(ap, "force_stand", None)
        ap.a.hide(); self.a.show()
        if special:                                            # (one of our own moves: he copies our figure)
            if self.rt is None:
                self.rt = Retarget(self)
            self.rt.apply()
            self.in_rt = True
            return
        if self.in_rt:
            self.rt.release()                                  # (back to the motion capture)
            self.in_rt = False
        I = info()
        target = {n: 0.0 for n in self.anims}
        sp = ap.sp
        # Which way is he moving against the way he faces?
        fwd, rgt = 1.0, 0.0
        if vel is not None and sp > 0.3:
            hd = math.radians(ap.h or 0.0)
            vl = max(0.1, math.hypot(*vel))
            fwd = (vel[0] * -math.sin(hd) + vel[1] * math.cos(hd)) / vl
            rgt = (vel[0] * math.cos(hd) + vel[1] * math.sin(hd)) / vl
        ang = math.degrees(math.atan2(rgt, fwd))
        moving = min(1.0, max(0.0, (sp - 0.4) / 0.8))
        target[self.idle] = 1.0 - moving
        if abs(ang) <= 55:
            speeds = [I[n]["speed"] for n in FORWARD]
            if sp <= speeds[0]:
                target[FORWARD[0]] = moving
            elif sp >= speeds[-1]:
                target[FORWARD[-1]] = moving
            else:
                for i in range(len(FORWARD) - 1):
                    if speeds[i] <= sp <= speeds[i + 1]:
                        u = (sp - speeds[i]) / (speeds[i + 1] - speeds[i])
                        target[FORWARD[i]] = moving * (1 - u)
                        target[FORWARD[i + 1]] = moving * u
        elif abs(ang) >= 125:
            target["Running_Backward"] = moving
        else:
            target["Right_Strafe" if ang > 0 else "Left_Strafe"] = moving
        self._blend(target, dt)
        # One shared stride phase: every running move is at the same point in its stride, and the phase moves on
        # by how far he's gone (his speed) over how far a stride of the blend travels - his feet stay planted
        loco = [n for n in self.anims if n not in self.still and self.w.get(n, 0) > 0.001]
        tot = sum(self.w[n] for n in loco)
        if tot > 0.001:
            stride = sum(self.w[n] * I[n]["dist"] for n in loco) / tot * self.a.getScale().z
            self.phase = (self.phase + sp * dt / max(0.3, stride)) % 1.0
        self.idle_t += dt
        for n in self.anims:
            if self.w[n] <= 0.001:
                continue
            nf = I[n]["frames"]
            if n in self.still:
                f = int(self.idle_t * 30.0) % max(1, nf - 1)
            else:
                f = int(self.phase * (nf - 1)) % max(1, nf - 1)
            self.a.pose(n, f)

    def _blend(self, target, dt, fast=False):
        k = min(1.0, dt * (14.0 if fast else 7.0))
        for n in self.anims:
            self.w[n] += (target.get(n, 0.0) - self.w[n]) * k
            self.a.setControlEffect(n, max(0.0, self.w[n]))


def attach(ap, kit, keeper=False):
    """Give an AnimPlayer the Mixamo body: wraps his update so the new body follows it."""
    m = Mix(ap, kit, keeper)
    orig = ap.update

    def update(x, y, fx, fy, speed, dt, active=True, vel=None, ball=None):
        orig(x, y, fx, fy, speed, dt, active, vel=vel, ball=ball)
        if active:
            m.update(dt, vel)
    ap.update = update
    ap.mix = m
    return m
