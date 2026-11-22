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
  - striking the ball with his right foot (passes, shots, chips), headers, throw-ins, a keeper's throws and kicks
    from his hands: the motion-captured move, lined up so the ball's struck at the moment ours is (CLIPS)
  - everything else (dives, falls, tackles, appeals, celebrations, left-footed kicks...): he copies our figure's
    move, bone by bone (Retarget), easing in and out of it

His kit is his own picture, painted with the club's kit (pattern, collar, sleeves), his name and number, his skin.

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
RUN_THROUGH = {"cut", "brake"}          # (our figure's sharp cuts and stops: the motion capture just runs on)
# Our moves with the ball that the motion capture has itself: played straight from it, lined up so its moment (the
# ball struck, headed, thrown - "moment" in the .json) falls on ours.  (move, on the run?) -> his move; on the run =
# going faster than SWING_FROM m/s.  Left-footed: the same move mirrored ("_M", made in dev/mixamo_build.py) where
# there is one.  Anything else: he copies our figure (Retarget).
CLIPS = {("kick", False): "kick_soccerball_2", ("pass", False): "kick_soccerball_2",
         ("kick", True): "strike_foward_jog", ("pass", True): "strike_foward_jog",
         ("shot", False): "strike_foward_jog", ("shot", True): "strike_foward_jog",
         ("finish", False): "strike_foward_jog", ("finish", True): "strike_foward_jog",
         ("dink", False): "Chip", ("dink", True): "Chip", ("loft", False): "Chip", ("loft", True): "Chip",
         ("header", False): "header_soccerball", ("header", True): "header_soccerball",
         ("throwin", False): "throw_in", ("throwin", True): "throw_in",
         ("gkthrow", False): "goalkeeper_overhand_throw", ("gkthrow", True): "goalkeeper_overhand_throw",
         ("punt", False): "goalkeeper_drop_kick", ("punt", True): "goalkeeper_drop_kick"}
SWING_FROM = 2.5
OWN_LOOPS = {"shift", "rest", "shuffle", "shuffle_m", "backpedal", "backwalk", "turnstep"}
CM = 100.0                                   # (the capture is in centimetres)
BRIGHT = 1.2
SLEEVE_END = 0.34          # (how far a short sleeve reaches along his arm, from the middle of him, in metres - in
                           #  his rest pose, arms out: shoulder about 0.18, elbow about 0.45)

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
            _info[nm] = {"dur": dur, "dist": dist, "speed": dist / dur, "frames": int(f1 - f0) + 1,
                         "moment": d.get("moment")}
    return _info


_base = None


def _base_maps(actor):
    """His body picture (as numbers, 0-1) and where each pixel sits on him (dev/mixamo_posmap.py)."""
    global _base
    if _base is None:
        import numpy as np
        tex = None
        for t in actor.findAllTextures():
            if t.getXSize() >= 512 and "Diffuse" in t.getName() and "1002" not in t.getName():
                tex = t
                break
        if tex is None:
            tex = max(actor.findAllTextures(), key=lambda t: t.getXSize())
        w, h = tex.getXSize(), tex.getYSize()
        raw = np.frombuffer(bytes(tex.getRamImageAs("RGB")), np.uint8).reshape(h, w, 3)[::-1].astype(np.float32) / 255
        pm = np.load(os.path.join(HERE, "models", "mixamo_posmap.npz"))
        pos, part = pm["pos"].astype(np.float32), pm["part"]
        if pos.shape[0] != h:
            raise RuntimeError("posmap size")
        L = raw.mean(axis=2)
        shade = np.ones_like(L)
        for pid in (1, 2, 3):
            m = part == pid
            if m.any():
                shade[m] = np.clip(L[m] / max(1e-3, float(np.median(L[m]))), 0.55, 1.25)
        x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
        # (the model's own number 7 on his back and badge on his chest: smoothed away - we print our own)
        flat = (part == 1) & (np.abs(x) < 0.2) & (z > 1.02) & (z < 1.5) & (y > 0.0)
        flat |= (part == 1) & (np.abs(x) < 0.2) & (z > 1.25) & (z < 1.45) & (y < 0.0)
        shade[flat] = np.clip(shade[flat], 0.92, 1.05)
        skin = part == 4
        skin_ref = np.median(raw[skin & (np.abs(x) < 0.4)], axis=0) if skin.any() else np.array([0.8, 0.6, 0.5])
        _base = {"raw": raw, "pos": pos, "part": part, "shade": shade, "skin_ref": skin_ref, "w": w, "h": h, "tex": tex}
    return _base


def kit_texture(actor, kit, number, name, keeper, skin):
    """His own picture: the club's kit (with its pattern - the same rules as our figures), his name and number on
    his back, his skin tone, a keeper's gloves."""
    import numpy as np
    from panda3d.core import Texture
    import players3d
    b = _base_maps(actor)
    raw, pos, part, shade = b["raw"], b["pos"], b["part"], b["shade"]
    out = raw.copy()
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    ax = np.abs(x)
    C = lambda c: np.array(c[:3], np.float32) / 255.0
    shirt, trim = C(kit["shirt"]), C(kit.get("trim", kit["shirt"]))
    m = part == 1
    col = np.empty((int(m.sum()), 3), np.float32)
    col[:] = shirt
    pat = kit.get("pattern")
    xs, ys, zs, axs = x[m], y[m], z[m], ax[m]
    torso = axs < 0.24
    if pat == "sleeves":
        col[~torso] = trim
    elif pat == "hoops":
        col[torso & ((((zs - 0.97) / 0.105).astype(int) % 2) == 1)] = trim
    elif pat == "stripes":
        col[torso & ((((xs + 0.5) / 0.075).astype(int) % 2) == 1)] = trim
    elif pat == "pinstripe":
        k = (torso & (((xs + 0.5) % 0.07) < 0.018))[:, None] * 0.22
        col = col * (1 - k) + trim * k
    elif pat == "band":
        col[torso & (zs > 1.24) & (zs < 1.33)] = trim
    elif pat == "halves":
        col[torso & (xs > 0)] = trim
    elif pat == "sash":
        sgn = np.where(ys < 0, 1.0, -1.0)
        col[torso & (np.abs(xs * sgn - (zs - 1.18) * 0.85) < 0.07)] = trim
    collar = torso & (zs > 1.47) & (axs < 0.11)
    col[collar] = trim
    out[m] = col * shade[m][:, None]
    # Sleeves: the same November choice as our figures (players3d.py) - about a third of outfield players in long
    # sleeves (and a few of them in gloves); the rest short-sleeved, a hem in the trim colour, bare arms below.
    import zlib
    hs = zlib.crc32(f"hair{name}{number}".encode())
    ls, gl = kit.get("long_sleeves"), False
    if ls is None:
        ls = keeper or not name or str(name).startswith(("sub", "steward")) or (hs // 100) % 10 < 3
        gl = (not keeper and bool(name) and not str(name).startswith(("sub", "steward"))
              and ((hs // 1000) % 10 < 1 or (ls and (hs // 1000) % 10 < 4)))
    if not ls:
        hem = m & (ax > SLEEVE_END - 0.03) & (ax <= SLEEVE_END)
        out[hem] = trim * shade[hem][:, None]
        arm = m & (ax > SLEEVE_END)
        out[arm] = C(skin) * np.clip(shade[arm], 0.8, 1.1)[:, None]
    for pid, key in ((2, "shorts"), (3, "socks")):
        mm = part == pid
        out[mm] = C(kit.get(key, kit["shirt"])) * shade[mm][:, None]
    if kit.get("socktop"):
        mm = (part == 3) & (z > 0.30)
        out[mm] = C(kit["socktop"]) * shade[mm][:, None]
    # Skin: his own tone, keeping the model's shading and features
    sk = part == 4
    tone = C(skin) / np.maximum(1e-3, b["skin_ref"])
    out[sk] = np.clip(raw[sk] * tone, 0, 1)
    if kit.get("trousers"):                                      # (a manager's or a warming-up sub's: down to
        legs = ((part == 2) | (part == 3) | (sk & (z < 0.97) & (ax < 0.30))) & (z > 0.07)  # his shoes)
        L = raw[legs].mean(axis=1)
        out[legs] = C(kit.get("shorts", (30, 30, 34))) * np.clip(L / max(1e-3, float(np.median(L))), 0.7, 1.2)[:, None]
    if keeper or gl:                                             # (gloves: a keeper's, or a cold outfielder's)
        g = sk & (ax > 0.60)
        gc = C((28, 28, 30)) if not keeper else C((235, 235, 235) if sum(kit["shirt"]) < 600 else (40, 40, 44))
        out[g] = gc * np.clip(raw[g].mean(axis=1) / max(1e-3, float(np.median(raw[g].mean(axis=1)))), 0.6, 1.2)[:, None]
    # Boots: the same choice as our figures (players3d.py) - half in black, the rest white or a bright colour
    bs = zlib.crc32(f"boots{name}{number}".encode()) % 20
    bright = [(240, 240, 240), (240, 240, 240), (255, 120, 30), (40, 200, 190), (190, 240, 60), (230, 50, 60),
              (60, 120, 240), (250, 220, 50), (245, 90, 170), (240, 240, 240)]
    bt_col = C((22, 22, 24)) if bs < 10 or not name else C(bright[bs - 10])
    bm = part == 5
    if bm.any():
        Lb = raw[bm].mean(axis=1)
        sole = Lb > 0.75                                          # (studs and soles stay as they are)
        sh = np.clip(Lb / max(1e-3, float(np.median(Lb))), 0.5, 1.4)[:, None]
        newc = bt_col * sh
        cur = out[bm]
        cur[~sole] = newc[~sole]
        out[bm] = cur
    # Name and number on his back (the same picture our figures use, the same place)
    num_col = kit.get("number", (255, 255, 255))
    bt = players3d._back_texture(name, number, num_col, None)
    from PIL import Image
    import io
    from panda3d.core import StringStream, PNMImage
    pi = PNMImage(); bt.store(pi)
    ss = StringStream(); pi.write(ss, "x.png")
    img = np.asarray(Image.open(io.BytesIO(ss.getData())).convert("RGBA"), np.float32) / 255.0
    H, W = img.shape[:2]
    back = (part == 1) & (y > 0.0) & (ax < 0.15) & (z > 1.10) & (z < 1.44)
    u = np.clip(((0.15 - x[back]) / 0.30 * (W - 1)).astype(int), 0, W - 1)
    v = np.clip(((1.0 - (z[back] - 1.10) / 0.34) * (H - 1)).astype(int), 0, H - 1)
    a = img[v, u, 3:4]
    out[back] = out[back] * (1 - a) + img[v, u, :3] * a * shade[back][:, None]
    data = (np.clip(out, 0, 1)[::-1] * 255).astype(np.uint8)
    t = Texture(f"kit{number}")
    t.setup2dTexture(b["w"], b["h"], Texture.T_unsigned_byte, Texture.F_rgb)
    t.setRamImageAs(data.tobytes(), "RGB")
    t.setMinfilter(Texture.FT_linear_mipmap_linear)
    t.setMagfilter(Texture.FT_linear)
    t.setAnisotropicDegree(4)
    return t


_hair = {}


def hair_texture(actor, colour):
    """His hair in his own colour (the model's is dark brown): the same strands, re-coloured."""
    import numpy as np
    from panda3d.core import Texture
    key = tuple(colour)
    if key in _hair:
        return _hair[key]
    src = next((t for t in actor.findAllTextures() if "1002" in t.getName() and "Diffuse" in t.getName()), None)
    if src is None:
        return None
    w, h = src.getXSize(), src.getYSize()
    raw = np.frombuffer(bytes(src.getRamImageAs("RGBA")), np.uint8).reshape(h, w, 4).astype(np.float32) / 255
    L = raw[..., :3].mean(axis=2)
    ref = max(1e-3, float(np.median(L[raw[..., 3] > 0.5]))) if (raw[..., 3] > 0.5).any() else 0.2
    c = np.array(colour[:3], np.float32) / 255.0
    out = raw.copy()
    out[..., :3] = np.clip(c * np.clip(L / ref, 0.35, 1.8)[..., None], 0, 1)
    t = Texture("hair")
    t.setup2dTexture(w, h, Texture.T_unsigned_byte, Texture.F_rgba)
    t.setRamImageAs((out * 255).astype(np.uint8).tobytes(), "RGBA")
    t.setMinfilter(Texture.FT_linear_mipmap_linear)
    _hair[key] = t
    return t


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
        """Take charge of his main joints for good: every frame they're set from the motion capture (played on a
        hidden twin, self.mix.m), our figure's pose, or a blend of the two - so he moves smoothly from one to the
        other."""
        from panda3d.core import LMatrix4f, LQuaternionf
        a, m = self.mix.a, self.mix.m
        P = "mixamorig5:"
        root = self.mix.ap.root
        if self.pw_q is not None:                       # (taking charge again: the rest is worked out already)
            self.ctrl = {d: a.controlJoint(None, "modelRoot", P + d) for d in CHAIN}
            return
        hx = a.exposeJoint(None, "modelRoot", P + "Hips")
        a.getPartBundle("modelRoot").forceUpdate()
        self.ctrl = {}
        for d in CHAIN:
            c = a.controlJoint(None, "modelRoot", P + d)
            self.ctrl[d] = c
            self.rest_local[d] = (c.getQuat(), c.getMat())
        # The hips' parent (the skeleton's root), in the player's frame: rest hips (world) = rest local x parent
        lq = LQuaternionf(self.rest_local["Hips"][0]); lq.invertInPlace()
        self.pw_q = lq * hx.getQuat(root)
        mm = LMatrix4f(self.rest_local["Hips"][1]); mm.invertInPlace()
        self.pw_mat = mm * hx.getMat(root)
        self.pw_inv = LMatrix4f(self.pw_mat); self.pw_inv.invertInPlace()
        hx.removeNode()
        self.mx = {d: m.exposeJoint(None, "modelRoot", P + d) for d in CHAIN}

    def release(self):
        """Let go of his joints: he plays the motion capture himself, exactly as his twin does (no copying -
        much less work while he's just running about)."""
        if self.ctrl is not None:
            for d, c in self.ctrl.items():
                self.mix.a.releaseJoint("modelRoot", "mixamorig5:" + d)
                c.removeNode()
            self.ctrl = None

    def apply(self, w):
        """Pose him: the motion capture (from his twin), blended towards our figure's pose by w (0-1)."""
        from panda3d.core import LQuaternionf, Point3
        if self.ctrl is None:
            self._control()
        ap = self.mix.ap
        root = ap.root
        self.mix.m.getPartBundle("modelRoot").forceUpdate()
        if w > 0.001:
            ap.a.getPartBundle("modelRoot").forceUpdate()
        world = {}
        for d in CHAIN:
            parent_q = world[PARENT[d]] if d in PARENT else self.pw_q
            q = self.mx[d].getQuat(root)
            if w > 0.001:
                s = self.src_of.get(d)
                rq = self.F[d] * self.sx[s].getQuat(root) if s is not None else self.rest_local[d][0] * parent_q
                q = _nlerp(q, rq, w)
            inv = LQuaternionf(parent_q); inv.invertInPlace()
            self.ctrl[d].setQuat(q * inv)
            world[d] = q
        hp = self.mx["Hips"].getPos(root)
        if w > 0.001:                       # (his hips go where ours go, scaled to his height: crouching, diving...)
            ps = self.sx["pelvis"].getPos(root)
            hp = hp * (1.0 - w) + (self.pd0 + (ps - self.ps0) * self.k) * w
        self.ctrl["Hips"].setPos(self.pw_inv.xformPoint(Point3(hp)))


def _nlerp(a, b, t):
    from panda3d.core import LQuaternionf
    if a.dot(b) < 0:
        b = LQuaternionf(-b[0], -b[1], -b[2], -b[3])
    q = LQuaternionf(a[0] * (1 - t) + b[0] * t, a[1] * (1 - t) + b[1] * t, a[2] * (1 - t) + b[2] * t,
                     a[3] * (1 - t) + b[3] * t)
    q.normalize()
    return q


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
    def __init__(self, ap, kit, keeper=False, number="", name=None, skin=None, hair=None):
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
        try:                                                   #  which it wraps light round - his pictures need
            tex = kit_texture(self.a, kit, number, name, keeper, skin or (200, 150, 120))
            ts = self.a.findTextureStage("Base Color")         #  a lift to sit alongside)
            for np_ in self.a.findAllMatches("**/Ch38_*"):
                if "Hair" not in np_.getName() and "Eyelash" not in np_.getName():
                    if ts is not None:
                        np_.setTexture(ts, tex, 1)
                    else:
                        np_.setTexture(tex, 1)
            if hair is not None:
                ht = hair_texture(self.a, hair)
                if ht is not None:
                    for np_ in self.a.findAllMatches("**/Ch38_Hair*"):
                        np_.setTexture(ts, ht, 1) if ts is not None else np_.setTexture(ht, 1)
        except Exception as ex:                                # (no position map: just the colours)
            print("mixamo kit picture:", ex)
            self._kit(kit, keeper)
        self.a.enableBlend()
        # His twin: the same body, hidden, playing the motion capture - what he does when he's just moving about
        self.m = Actor(Filename.fromOsSpecific(MODEL).getFullpath())
        self.m.reparentTo(ap.root)
        self.m.setScale(k)
        self.m.setH(180)
        self.m.hide()
        self.m.enableBlend()
        self.actors = (self.a, self.m)
        self.live = self.actors                                # (the ones being moved this frame)
        self.eff = ({}, {})                                    # (each one's move weights, as last set)
        self.anims = self.a.getAnimNames()
        self.w = {n: 0.0 for n in self.anims}
        self.phase = 0.0
        self.idle_t = (ap.seed % 97) / 10.0
        idles = [n for n in IDLES if n in self.anims] or [self.anims[0]]
        self.idle = idles[(ap.seed // 3) % len(idles)]
        self.still = set(IDLES) | {"kick_soccerball", "Victory"}
        self.clips = set(CLIPS.values()) | set(c + "_M" for c in CLIPS.values())
        self.clip_for = None
        self.rt = Retarget(self)                               # (in the rest pose: before anything moves)
        self.w_rt = 0.0                                        # (how much he's copying our figure: 0-1)
        self.holders = {}
        ap.a.hide()

    def holder(self, joint):
        """Somewhere to hang a thing he holds (an assistant's flag, the referee's card) on his hand, lined up the
        way our figure's hand is - so anything made for our figure's hand fits his."""
        if joint not in self.holders:
            h = self.ap.root.attachNewNode("hold_" + joint)
            src = self.ap.a.exposeJoint(None, "modelRoot", joint)
            dst = self.a.exposeJoint(None, "modelRoot", "mixamorig5:" + dict(MAP)[joint])
            self.holders[joint] = (h, src, dst, dict(MAP)[joint])
        return self.holders[joint][0]

    def _hold(self):
        from panda3d.core import LQuaternionf
        if not self.holders:
            return
        self.a.getPartBundle("modelRoot").forceUpdate()
        root = self.ap.root
        for h, src, dst, d in self.holders.values():
            inv = LQuaternionf(self.rt.F[d]); inv.invertInPlace()  # (his hand = F x ours, so ours = F' x his)
            h.setPos(root, dst.getPos(root))
            h.setQuat(root, inv * dst.getQuat(root))
            h.setScale(root, src.getScale(root))

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
        base = name.split("_")[0] if name else None
        # A move with the ball the motion capture has (right foot, header, throw): his own, lined up on ours
        act = None
        if name is not None and wgt > 0.02:
            if self.clip_for is None or self.clip_for[0] != name or frame < self.clip_for[1]:
                left = name.endswith("_m")                      # (left-footed: the move mirrored, if we have it)
                clip = CLIPS.get((name[:-2] if left else name, ap.sp > SWING_FROM))
                if left:
                    clip = clip + "_M" if clip and clip + "_M" in self.anims else None
                self.clip_for = (name, frame, clip)             # (chosen as it starts)
            clip = self.clip_for[2]
            if clip in self.anims and info()[clip]["moment"] is not None:
                import gait
                t = (gait.SPANS[name][0] + frame / 30.0) if name in gait.SPANS else 0.0  # (seconds from the moment)
                f = info()[clip]["moment"] + t * 30.0
                act = (clip, max(0, min(info()[clip]["frames"] - 1, int(round(f)))), wgt)
                if LOG and self.clip_for[1] == frame:
                    print("MXCLIP", _tick[0], ap.seed, name, clip, round(ap.sp, 1), round(frame, 1), round(wgt, 2), act[1], flush=True)
        else:
            self.clip_for = None
        special = act is None and ((name is not None and wgt > 0.2 and base not in RUN_THROUGH)
                                   or getattr(ap, "roll", 0.0) > 1.0 or getattr(ap, "lift", 0.0) > 0.05
                                   or moods > 0.3 or getattr(ap, "force_stand", None))
        ap.a.hide(); self.a.show()
        # One of our own moves: he copies our figure - easing in and out of it over a tenth of a second or so
        self.w_rt += ((1.0 if special else 0.0) - self.w_rt) * min(1.0, dt * 12.0)
        # His twin only needs moving while he's copying our figure (or easing in or out of it)
        self.live = self.actors if (special or self.w_rt >= 0.002 or self.rt.ctrl is not None) else (self.a,)
        self._mocap(dt, vel, act)
        if self.w_rt < 0.002 and not special:
            self.rt.release()                                  # (just the motion capture: he plays it himself)
        else:
            self.rt.apply(self.w_rt)
        self._hold()

    def _mocap(self, dt, vel, act=None):
        ap = self.ap
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
        self._blend(target, dt, act=act)
        # One shared stride phase: every running move is at the same point in its stride, and the phase moves on
        # by how far he's gone (his speed) over how far a stride of the blend travels - his feet stay planted
        loco = [n for n in self.anims if n not in self.still and n not in self.clips and self.w.get(n, 0) > 0.001]
        tot = sum(self.w[n] for n in loco)
        if tot > 0.001:
            stride = sum(self.w[n] * I[n]["dist"] for n in loco) / tot * self.a.getScale().z
            self.phase = (self.phase + sp * dt / max(0.3, stride)) % 1.0
        self.idle_t += dt
        for n in self.anims:
            if n in self.clips:
                if act is not None and n == act[0]:
                    for a_ in self.live:
                        a_.pose(n, act[1])
                continue
            if self.w[n] <= 0.001:
                continue
            nf = I[n]["frames"]
            if n in self.still:
                f = int(self.idle_t * 30.0) % max(1, nf - 1)
            else:
                f = int(self.phase * (nf - 1)) % max(1, nf - 1)
            for a_ in self.live:
                a_.pose(n, f)

    def _blend(self, target, dt, fast=False, act=None):
        """Ease the moving-about moves' weights to where they should be; a move with the ball goes straight in at
        its own weight (it eases in and out with ours), on top of them."""
        k = min(1.0, dt * (14.0 if fast else 7.0))
        aw = act[2] if act is not None else 0.0
        for n in self.anims:
            if n in self.clips:
                e = aw if act is not None and n == act[0] else 0.0
            else:
                self.w[n] += (target.get(n, 0.0) - self.w[n]) * k
                e = max(0.0, self.w[n]) * (1.0 - aw)
            for i, a_ in enumerate(self.live):                # (only when it's changed: fewer calls)
                if abs(self.eff[i].get(n, -1.0) - e) > 1e-4:
                    a_.setControlEffect(n, e)
                    self.eff[i][n] = e


LOG = os.environ.get("FM_MX_LOG") == "1"      # (testing: print each motion-captured move as it starts)
_tick = [0]
TIME = os.environ.get("FM_MX_TIME") == "1"    # (testing: how long the Mixamo men take, per frame)
_spent = [0.0]
if TIME:
    import atexit
    atexit.register(lambda: print("MXTIME total %.2f s over %d frames = %.1f ms a frame"
                                  % (_spent[0], _tick[0], 1000 * _spent[0] / max(1, _tick[0])), flush=True))
_first = []


def attach(ap, kit, keeper=False, number="", name=None, skin=None, hair=None):
    """Give an AnimPlayer the Mixamo body: wraps his update so the new body follows it."""
    m = Mix(ap, kit, keeper, number, name, skin, hair)
    orig = ap.update
    if not _first:
        _first.append(ap)

    def update(x, y, fx, fy, speed, dt, active=True, vel=None, ball=None):
        if ap is _first[0]:
            _tick[0] += 1
        orig(x, y, fx, fy, speed, dt, active, vel=vel, ball=ball)
        if active:
            if TIME:
                import time
                t0 = time.perf_counter()
                m.update(dt, vel)
                _spent[0] += time.perf_counter() - t0
            else:
                m.update(dt, vel)
    ap.update = update
    ap.mix = m
    return m
