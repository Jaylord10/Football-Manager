"""
broadcast3d/body.py - a smooth footballer's body for the mannequin's skeleton.

The mannequin figure is made of separate hard pieces (that's what looks robotic at the joints).  This builds
one continuous skin instead, shaped from a set of rounded shapes (hips, chest, shoulders, thighs, calves...)
melted smoothly into each other, then "skinned" to the same skeleton: every point of the skin follows the
bones near it, sharing between two or three bones round a joint - so knees, hips, shoulders and elbows bend
smoothly, like skin over muscle.  All the movements (gait.py) work as before, because the skeleton is the same.

Proportions: an athletic adult male of ~1.80 m - shoulders ~45 cm across, waist ~80 cm round, thigh ~57 cm
round, calf ~38 cm round (in line with anthropometric surveys of professional footballers, e.g. Reilly et al.
2000, "Anthropometric and physiological predispositions for elite soccer", J Sports Sci 18(9)).

  python broadcast3d/body.py        builds models/body.npz (needs numpy, scikit-image and pyfqmr - only here,
                                    when making it; the game just loads the .npz)
"""
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "models", "body.npz")

# The skeleton in its rest pose (the mannequin's, in its own space: he faces -y, his right is -x, metres).
J = {"pelvis": (0.0, -0.01, 0.948), "spine_01": (0.0, -0.035, 1.066), "spine_02": (0.0, -0.027, 1.251),
     "neck_01": (0.0, 0.018, 1.492), "head": (0.0, -0.002, 1.573),
     "thigh.l": (0.102, -0.01, 0.921), "calf.l": (0.136, 0.0, 0.533), "foot.l": (0.181, 0.041, 0.11),
     "ball.l": (0.195, -0.049, 0.02), "clavicle.l": (0.044, -0.018, 1.433), "upperarm.l": (0.174, 0.017, 1.433),
     "lowerarm.l": (0.436, 0.011, 1.43), "hand.l": (0.644, 0.009, 1.43), "thumb_01.l": (0.695, -0.039, 1.427),
     "middle_01.l": (0.73, 0.008, 1.434)}
# The arms are lengthened to real proportions (skeleton.py): x along the arm, from the shoulder out, is
# stretched part by part.  The shapes below are drawn on the mannequin's short arm and stretched with it.
OLD_X = (0.174, 0.436, 0.644)          # shoulder, elbow, wrist on the mannequin's arm
from skeleton import LIMB_SCALE as _LS
NEW_X = (0.174, 0.174 + 0.262 * _LS["lowerarm.l"], 0.174 + 0.262 * _LS["lowerarm.l"] + 0.208 * _LS["hand.l"])
K_HAND = _LS["index_01.l"]


def arm_x(x):
    """Where a point x along the mannequin's arm is on the footballer's (either side)."""
    a, s = np.abs(x), np.sign(x)
    out = np.where(a <= OLD_X[0], a,
          np.where(a <= OLD_X[1], NEW_X[0] + (a - OLD_X[0]) * (NEW_X[1] - NEW_X[0]) / (OLD_X[1] - OLD_X[0]),
          np.where(a <= OLD_X[2], NEW_X[1] + (a - OLD_X[1]) * (NEW_X[2] - NEW_X[1]) / (OLD_X[2] - OLD_X[1]),
                   NEW_X[2] + (a - OLD_X[2]) * K_HAND)))
    return out * s


def arm_x_back(x):
    """The reverse: a point on the footballer's arm -> where it was on the mannequin's."""
    a, s = np.abs(x), np.sign(x)
    out = np.where(a <= NEW_X[0], a,
          np.where(a <= NEW_X[1], OLD_X[0] + (a - NEW_X[0]) * (OLD_X[1] - OLD_X[0]) / (NEW_X[1] - NEW_X[0]),
          np.where(a <= NEW_X[2], OLD_X[1] + (a - NEW_X[1]) * (OLD_X[2] - OLD_X[1]) / (NEW_X[2] - NEW_X[1]),
                   OLD_X[2] + (a - NEW_X[2]) / K_HAND)))
    return out * s


for k in list(J):
    if k.split(".")[0] in ("lowerarm", "hand", "thumb_01", "middle_01"):
        x, y, z = J[k]
        J[k] = (float(arm_x(np.array(x))), y, z)
for k, v in list(J.items()):
    if k.endswith(".l"):
        J[k[:-2] + ".r"] = (-v[0], v[1], v[2])

# Bones for the skin to follow: (joint, from, to) - a segment for each.
BONES = [("pelvis", "pelvis", "spine_01"), ("spine_01", "spine_01", "spine_02"), ("spine_02", "spine_02", "neck_01"),
         ("neck_01", "neck_01", "head"), ("head", "head", (0.0, -0.02, 1.76))]
for s in ("l", "r"):
    sx = 1 if s == "l" else -1
    BONES += [("clavicle." + s, "clavicle." + s, "upperarm." + s), ("upperarm." + s, "upperarm." + s, "lowerarm." + s),
              ("lowerarm." + s, "lowerarm." + s, "hand." + s), ("hand." + s, "hand." + s, (sx * float(arm_x(np.array(0.77))), 0.005, 1.432)),
              ("thigh." + s, "thigh." + s, "calf." + s), ("calf." + s, "calf." + s, "foot." + s),
              ("foot." + s, "foot." + s, "ball." + s), ("ball." + s, "ball." + s, (sx * 0.199, -0.15, 0.02))]

# The fingers (the skeleton has an index, a middle and a ring finger: our ring and little fingers both go with
# its ring finger).  Where their joints are along the footballer's arm:
FINGER_X = {}
for _f, (_a, _b, _c) in (("index", (0.728, 0.758, 0.789)), ("middle", (0.730, 0.758, 0.785)), ("ring", (0.729, 0.751, 0.783))):
    _j1 = float(arm_x(np.array(_a)))
    FINGER_X[_f] = (_j1, _j1 + (_b - _a), _j1 + (_c - _a))
for s in ("l", "r"):
    sx = 1 if s == "l" else -1
    for _f, (_x1, _x2, _x3) in FINGER_X.items():
        _y = {"index": -0.030, "middle": -0.010, "ring": 0.02}[_f]
        BONES += [(f"{_f}_01.{s}", (sx * _x1, _y, 1.43), (sx * _x2, _y, 1.43)),
                  (f"{_f}_02.{s}", (sx * _x2, _y, 1.43), (sx * _x3, _y, 1.43)),
                  (f"{_f}_03.{s}", (sx * _x3, _y, 1.43), (sx * (_x3 + 0.03), _y, 1.43))]


def P(p):
    return np.array(J[p] if isinstance(p, str) else p, np.float32)


# --- the shapes -----------------------------------------------------------------------------------------------
def capsule(q, a, b, ra, rb):
    a, b = P(a), P(b)
    ba = b - a
    t = np.clip(((q - a) @ ba) / (ba @ ba), 0.0, 1.0)
    r = ra + (rb - ra) * t
    return np.linalg.norm(q - (a + t[..., None] * ba), axis=-1) - r


def ellipsoid(q, c, r):
    c, r = P(c), np.array(r, np.float32)
    k0 = np.linalg.norm((q - c) / r, axis=-1)
    k1 = np.linalg.norm((q - c) / (r * r), axis=-1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-6)


def cylinder(q, a, b, ra, rb):
    """A tube from a to b with flat ends (radius ra at a, rb at b) - for loose clothes with a hem."""
    a, b = P(a), P(b)
    ba = b - a
    L = float(np.linalg.norm(ba))
    t = ((q - a) @ ba) / (L * L)
    r = ra + (rb - ra) * np.clip(t, 0.0, 1.0)
    radial = np.linalg.norm(q - (a + t[..., None] * ba), axis=-1) - r
    axial = (np.abs(t - 0.5) - 0.5) * L
    out = np.sqrt(np.maximum(radial, 0) ** 2 + np.maximum(axial, 0) ** 2)
    return out + np.minimum(np.maximum(radial, axial), 0.0)


def shirt_tube(q, z0, z1, rx0, ry0, rx1, ry1, cy=0.0):
    """The shirt hanging loose from the chest: an oval tube, straight down, with a flat hem at z0."""
    z = q[..., 2]
    t = np.clip((z - z0) / (z1 - z0), 0.0, 1.0)
    rx, ry = rx0 + (rx1 - rx0) * t, ry0 + (ry1 - ry0) * t
    k = np.sqrt((q[..., 0] / rx) ** 2 + ((q[..., 1] - cy) / ry) ** 2)
    radial = (k - 1.0) * np.minimum(rx, ry)
    axial = np.maximum(z0 - z, z - z1)
    out = np.sqrt(np.maximum(radial, 0) ** 2 + np.maximum(axial, 0) ** 2)
    return out + np.minimum(np.maximum(radial, axial), 0.0)


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def shapes():
    """(name, field function, blend) - in the order they're melted together."""
    out = []
    add = lambda f, k=0.03, mode="add": out.append((f, k, mode))
    # trunk: a V from broad shoulders to a narrower waist, flat across the front
    add(lambda q: ellipsoid(q, (0.0, 0.005, 0.95), (0.128, 0.098, 0.11)))                     # hips
    add(lambda q: ellipsoid(q, (0.0, -0.005, 1.11), (0.128, 0.088, 0.16)), 0.08)               # waist
    add(lambda q: ellipsoid(q, (0.0, 0.0, 1.30), (0.162, 0.094, 0.165)), 0.08)                 # chest
    add(lambda q: ellipsoid(q, (0.0, -0.035, 1.305), (0.125, 0.068, 0.085)), 0.04)             # pecs (flat)
    add(lambda q: ellipsoid(q, (0.0, 0.022, 1.30), (0.146, 0.08, 0.13)), 0.06)                 # back (lats)
    for sx in (-1, 1):                                                                          # shoulders,
        add(lambda q, sx=sx: capsule(q, (sx * 0.03, 0.012, 1.43), (sx * 0.16, 0.01, 1.385), 0.058, 0.054), 0.06)  # sloping
    add(lambda q: capsule(q, (0.0, 0.016, 1.38), (0.0, 0.012, 1.58), 0.060, 0.056), 0.04)       # neck
    for sx in (-1, 1):
        # glutes
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.062, 0.045, 0.895), (0.065, 0.055, 0.08)), 0.05)
        # shoulders (deltoids) and arms
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.19, 0.008, 1.402), (0.064, 0.06, 0.054)), 0.05)
        add(lambda q, sx=sx: capsule(q, (sx * 0.19, 0.015, 1.425), (sx * 0.436, 0.011, 1.43), 0.052, 0.040), 0.03)
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.31, -0.012, 1.428), (0.075, 0.045, 0.043)), 0.025)   # biceps
        add(lambda q, sx=sx: capsule(q, (sx * 0.436, 0.011, 1.43), (sx * 0.644, 0.009, 1.43), 0.040, 0.0245), 0.025)
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.50, 0.0, 1.43), (0.06, 0.04, 0.036)), 0.02)       # forearm
        # The hand, to real sizes (a man's hand: ~19 cm long, ~8.7 cm across the knuckles, ~2.8 cm thick, the
        # middle finger ~8.3 cm, fingers ~1.7 cm thick - NASA / US Army ANSUR hand survey figures).  Drawn on the
        # mannequin's short arm (x is stretched 1.28 times past the wrist).  A palm narrowing to the wrist, the
        # pad at the base of the thumb, four fingers of different lengths in three parts each, curling a
        # little more at each joint (a relaxed hand), and a two-part thumb.
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.692, 0.001, 1.43), (0.044, 0.037, 0.0135)), 0.014)
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.662, 0.004, 1.43), (0.03, 0.028, 0.016)), 0.014)
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.668, -0.024, 1.424), (0.022, 0.015, 0.012)), 0.01)   # thumb pad
        for fy, ln, x0 in ((-0.030, 0.92, 0.726), (-0.010, 1.0, 0.729), (0.011, 0.94, 0.726), (0.030, 0.76, 0.718)):
            k0, k1 = (sx * x0, fy, 1.431), (sx * (x0 + 0.027 * ln), fy, 1.426)
            k2, k3 = (sx * (x0 + 0.046 * ln), fy, 1.415), (sx * (x0 + 0.060 * ln), fy, 1.399)
            add(lambda q, a=k0, b=k1: capsule(q, a, b, 0.0088, 0.0083), 0.007)
            add(lambda q, a=k1, b=k2: capsule(q, a, b, 0.0083, 0.0076), 0.005)
            add(lambda q, a=k2, b=k3: capsule(q, a, b, 0.0076, 0.0068), 0.005)
        add(lambda q, sx=sx: capsule(q, (sx * 0.674, -0.034, 1.422), (sx * 0.700, -0.049, 1.413), 0.0105, 0.0092), 0.008)
        add(lambda q, sx=sx: capsule(q, (sx * 0.700, -0.049, 1.413), (sx * 0.720, -0.054, 1.402), 0.0092, 0.0078), 0.005)
        # legs
        add(lambda q, sx=sx: capsule(q, (sx * 0.092, -0.006, 0.90), (sx * 0.136, 0.0, 0.533), 0.076, 0.053), 0.05)
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.112, -0.03, 0.75), (0.07, 0.068, 0.16)), 0.035)    # quads
        # above the knee: the inner "teardrop" (vastus medialis) and the outer quad, the kneecap, the hamstring
        # tendons behind the knee
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.106, -0.028, 0.605), (0.038, 0.04, 0.062)), 0.02)
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.166, -0.012, 0.655), (0.032, 0.042, 0.09)), 0.02)
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.137, -0.05, 0.532), (0.024, 0.016, 0.03)), 0.012)
        for tx in (0.118, 0.16):
            add(lambda q, sx=sx, tx=tx: capsule(q, (sx * tx, 0.035, 0.63), (sx * (tx - 0.002), 0.03, 0.50), 0.013, 0.011), 0.012)
        # the lower leg: a slim shin and ankle, the calf's two heads (the inner one bigger and lower)
        add(lambda q, sx=sx: capsule(q, (sx * 0.136, 0.0, 0.533), (sx * 0.178, 0.036, 0.115), 0.046, 0.03), 0.03)
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.128, 0.032, 0.405), (0.040, 0.046, 0.088)), 0.025)
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.163, 0.03, 0.425), (0.034, 0.041, 0.075)), 0.025)
        add(lambda q, sx=sx: capsule(q, (sx * 0.155, 0.045, 0.33), (sx * 0.178, 0.068, 0.13), 0.016, 0.011), 0.02)  # Achilles
        # shin pads under the socks
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.156, -0.005, 0.33), (0.03, 0.024, 0.10)), 0.02)
        # A football boot (a UK 9 is ~28 cm long, ~10 cm across the ball of the foot): a snug heel cup, a low
        # instep, widest at the ball of the foot, a low rounded toe, a flat sole.
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.182, 0.045, 0.048), (0.034, 0.042, 0.046)), 0.02)      # heel
        add(lambda q, sx=sx: capsule(q, (sx * 0.184, 0.03, 0.05), (sx * 0.192, -0.085, 0.037), 0.04, 0.034), 0.02)
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.193, -0.085, 0.033), (0.047, 0.05, 0.031)), 0.025)     # ball of foot
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.195, -0.127, 0.03), (0.037, 0.04, 0.027)), 0.025)   # toe
        add(lambda q: q[..., 2] - 0.007, 0.004, "cut")                                                   # flat sole
    # the head: skull, face, cheekbones, brow, jaw and chin, eye sockets with eyes in, nose, lips, ears
    add(lambda q: ellipsoid(q, (0.0, 0.006, 1.688), (0.077, 0.098, 0.092)), 0.03)              # skull
    add(lambda q: ellipsoid(q, (0.0, -0.035, 1.628), (0.067, 0.076, 0.082)), 0.03)            # face
    add(lambda q: ellipsoid(q, (0.0, -0.045, 1.583), (0.056, 0.068, 0.042)), 0.03)            # jaw
    add(lambda q: ellipsoid(q, (0.0, -0.098, 1.562), (0.026, 0.02, 0.024)), 0.02)             # chin
    add(lambda q: capsule(q, (-0.044, -0.104, 1.674), (0.044, -0.104, 1.674), 0.011, 0.011), 0.014)  # brow
    for sx in (-1, 1):
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.044, -0.076, 1.636), (0.016, 0.012, 0.011)), 0.02)   # cheekbone
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.077, 0.004, 1.643), (0.009, 0.021, 0.029)), 0.008)  # ear
    for sx in (-1, 1):                                                                          # eye sockets
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.033, -0.113, 1.655), (0.019, 0.016, 0.013)), 0.008, "cut")
    for sx in (-1, 1):                                                                          # eyes
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.033, -0.097, 1.655), (0.0125, 0.011, 0.0105)), 0.003)
    add(lambda q: capsule(q, (0.0, -0.107, 1.666), (0.0, -0.132, 1.619), 0.0065, 0.0098), 0.008)   # nose
    add(lambda q: ellipsoid(q, (0.0, -0.121, 1.613), (0.017, 0.012, 0.008)), 0.008)           # (its end)
    add(lambda q: ellipsoid(q, (0.0, -0.107, 1.588), (0.022, 0.009, 0.008)), 0.006)           # lips
    # the kit, hanging loose: the shirt straight down from the chest (untucked, over the top of the shorts),
    # short sleeves standing off the arm, and wide shorts down to a hand above the knee
    add(lambda q: shirt_tube(q, 0.928, 1.30, 0.172, 0.114, 0.166, 0.104, cy=-0.004), 0.012)
    for sx in (-1, 1):
        add(lambda q, sx=sx: cylinder(q, (sx * 0.225, 0.012, 1.414), (sx * 0.372, 0.011, 1.428), 0.058, 0.056), 0.05,
            "nowarp")
        add(lambda q, sx=sx: cylinder(q, (sx * 0.084, 0.0, 0.955), (sx * 0.112, -0.004, 0.622), 0.092, 0.087), 0.01)
    return out


def smax(a, b, k):
    h = np.clip(0.5 - 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h + k * h * (1 - h)


def field(q):
    d = None
    qa = q.copy()                                                  # (the arms: drawn on the short arm, stretched)
    arm = (q[..., 2] > 1.3) & (np.abs(q[..., 0]) > OLD_X[0])
    qa[..., 0] = np.where(arm, arm_x_back(q[..., 0]), q[..., 0])
    for f, k, mode in shapes():
        v = f(q if mode == "nowarp" else qa)
        mode = "add" if mode == "nowarp" else mode
        if mode == "cut":
            d = smax(d, -v, k)
        else:
            d = v if d is None else smin(d, v, k)
    return d


# --- building it ----------------------------------------------------------------------------------------------
def build(step=0.0036, target=16000):
    from skimage.measure import marching_cubes
    import pyfqmr
    lo = np.array([-1.02, -0.22, -0.005], np.float32)
    hi = np.array([1.02, 0.20, 1.80], np.float32)
    n = np.ceil((hi - lo) / step).astype(int) + 1
    xs, ys, zs = (lo[i] + np.arange(n[i]) * step for i in range(3))
    vol = np.empty(n, np.float32)
    for i, x in enumerate(xs):                                     # (a slice at a time, to keep memory down)
        g = np.stack(np.meshgrid([x], ys, zs, indexing="ij"), -1)[0]
        vol[i] = field(g.reshape(-1, 3).astype(np.float32)).reshape(len(ys), len(zs))
    verts, faces, _, _ = marching_cubes(vol, 0.0, spacing=(step, step, step))
    verts += lo
    s = pyfqmr.Simplify()
    s.setMesh(verts, faces)
    s.simplify_mesh(target_count=target + 4000, aggressiveness=5, preserve_border=True, verbose=0)
    verts, faces, _ = s.getMesh()
    verts = verts.astype(np.float32)
    faces = faces.astype(np.int32)
    # smooth normals from the field itself (its slope), which are better than the triangles'
    e = 0.002
    nrm = np.stack([field(verts + d) - field(verts - d) for d in np.eye(3, dtype=np.float32) * e], -1)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=-1, keepdims=True), 1e-9)
    # make sure the triangles face outwards (marching cubes' winding vs the normals)
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    fn = np.cross(b - a, c - a)
    if (np.einsum("ij,ij->i", fn, nrm[faces[:, 0]]) < 0).mean() > 0.5:
        faces = faces[:, ::-1].copy()
    idx, w = weights(verts)
    np.savez_compressed(OUT, verts=verts, normals=nrm.astype(np.float32), faces=faces, bone_idx=idx, bone_w=w,
                        bones=np.array([b[0] for b in BONES]))
    print(f"body: {len(verts)} points, {len(faces)} triangles -> {OUT}")


def weights(verts, keep=3):
    """Which bones each point of the skin follows, and how much: the nearest few, the nearer the more."""
    d = np.stack([np.linalg.norm(verts - _closest(verts, P(a), P(b)), axis=-1) for _, a, b in BONES], -1)
    # the head goes with the head and the neck only; points on one side never follow the other side's limbs
    names = [b[0] for b in BONES]
    for j, nm in enumerate(names):
        if nm.endswith(".l"):
            d[verts[:, 0] < -0.02, j] = 9.0
        if nm.endswith(".r"):
            d[verts[:, 0] > 0.02, j] = 9.0
    w = 1.0 / np.maximum(d, 0.004) ** 5
    ax, z = np.abs(verts[:, 0]), verts[:, 2]
    arm = np.clip((ax - 0.135) / 0.115, 0.0, 1.0)                    # (0 on the trunk, 1 out along the arm)
    for j, nm in enumerate(names):
        if nm.startswith("upperarm"):
            w[:, j] *= np.where(z > 1.25, arm ** 2, 0.0)
        elif nm.startswith(("lowerarm", "hand")):
            w[:, j] *= np.where(ax > float(arm_x(np.array(0.3))), 1.0, 0.0)
        elif nm.startswith(("spine", "neck", "pelvis")):
            w[:, j] *= np.where(z > 1.25, (1.0 - arm) ** 2 + 0.02, 1.0)
        elif nm.startswith("clavicle"):
            w[:, j] *= 0.6
    # the shorts: each leg of them goes with its thigh (blending into the hips at the top), so a kick swings
    # the leg of the shorts with it instead of the leg poking through
    y = verts[:, 1]
    legs = (z > 0.60) & (z < 0.97) & (ax > 0.012)
    for side, sg in (("l", 1), ("r", -1)):
        m = legs & (np.sign(verts[:, 0]) == sg)
        if not m.any():
            continue
        jt, jp = names.index("thigh." + side), names.index("pelvis")
        f = np.clip((0.95 - z[m]) / 0.16, 0.0, 1.0)
        w[m] = 0.0
        w[m, jt] = 0.05 + f
        w[m, jp] = (1.0 - f) * 0.6 + 1e-4
    # the fingers: each goes with its own finger's bones, part by part (blending over each joint), so the hand
    # can close; the thumb stays with the hand
    xs_, ys_ = verts[:, 0], verts[:, 1]
    for j, nm in enumerate(names):
        if nm.split("_")[0] in ("index", "middle", "ring"):
            w[:, j] = 0.0
    for side, sg in (("l", 1), ("r", -1)):
        for f, lo_y, hi_y in (("index", -9.0, -0.0205), ("middle", -0.0205, 0.0005), ("ring", 0.0005, 9.0)):
            x1, x2, x3 = FINGER_X[f]
            m = (np.sign(xs_) == sg) & (z > 1.3) & (ax > x1 - 0.005) & (ys_ >= lo_y) & (ys_ < hi_y) \
                & ~((ys_ < -0.042) & (ax < x1 + 0.014))
            if not m.any():
                continue
            a_ = ax[m]
            t1 = np.clip((a_ - (x1 - 0.005)) / 0.010, 0, 1)
            t2 = np.clip((a_ - (x2 - 0.005)) / 0.010, 0, 1)
            t3 = np.clip((a_ - (x3 - 0.005)) / 0.010, 0, 1)
            w[m] = 0.0
            w[m, names.index("hand." + side)] = 1 - t1
            w[m, names.index(f"{f}_01.{side}")] = t1 * (1 - t2)
            w[m, names.index(f"{f}_02.{side}")] = t2 * (1 - t3)
            w[m, names.index(f"{f}_03.{side}")] = t3
    order = np.argsort(-w, axis=1)[:, :keep]
    ww = np.take_along_axis(w, order, 1)
    ww /= ww.sum(1, keepdims=True)
    ww[ww < 0.04] = 0.0
    ww /= ww.sum(1, keepdims=True)
    q = np.round(ww * 16) / 16.0                                   # (in sixteenths: fewer different mixes)
    q[:, 0] += 1.0 - q.sum(1)
    return order.astype(np.int16), q.astype(np.float32)


def _closest(q, a, b):
    ba = b - a
    t = np.clip(((q - a) @ ba) / (ba @ ba), 0.0, 1.0)
    return a + t[:, None] * ba


# --- putting it on a player -------------------------------------------------------------------------------
_DATA = None


def attach(actor):
    """Swap the mannequin's pieces for the smooth body (skinned to this actor's own skeleton).  Returns the new
    node (None if there's no body.npz yet)."""
    global _DATA
    from panda3d.core import (GeomVertexArrayFormat, GeomVertexFormat, GeomVertexData, GeomVertexWriter, Geom,
                              GeomTriangles, GeomNode, InternalName, GeomVertexAnimationSpec, TransformBlendTable,
                              TransformBlend, JointVertexTransform, SparseArray)
    if _DATA is None:
        if not os.path.exists(OUT):
            return None
        _DATA = dict(np.load(OUT))
    D = _DATA
    ch = actor.find("**/+Character")
    char = ch.node()
    joints = {}
    for b in D["bones"]:
        j = char.findJoint(str(b))
        joints[str(b)] = JointVertexTransform(j)
    names = [str(b) for b in D["bones"]]
    arr = GeomVertexArrayFormat()
    arr.addColumn(InternalName.getVertex(), 3, Geom.NT_float32, Geom.C_point)
    arr.addColumn(InternalName.getNormal(), 3, Geom.NT_float32, Geom.C_normal)
    arr.addColumn(InternalName.make("texcoord.0"), 2, Geom.NT_float32, Geom.C_texcoord)
    arr.addColumn(InternalName.make("texcoord.1"), 2, Geom.NT_float32, Geom.C_texcoord)
    arr.addColumn(InternalName.getTransformBlend(), 1, Geom.NT_uint16, Geom.C_index)
    fmt = GeomVertexFormat()
    fmt.addArray(arr)
    spec = GeomVertexAnimationSpec(); spec.setPanda()
    fmt.setAnimation(spec)
    fmt = GeomVertexFormat.registerFormat(fmt)
    vd = GeomVertexData("body", fmt, Geom.UHDynamic)
    table = TransformBlendTable()
    cache = {}
    V, N, BI, BW = D["verts"], D["normals"], D["bone_idx"], D["bone_w"]
    vd.uncleanSetNumRows(len(V))
    vw, nw, t0, t1, bw = (GeomVertexWriter(vd, c) for c in ("vertex", "normal", "texcoord.0", "texcoord.1",
                                                             InternalName.getTransformBlend()))
    for i in range(len(V)):
        key = tuple((int(BI[i, k]), float(BW[i, k])) for k in range(BI.shape[1]) if BW[i, k] > 0)
        bi = cache.get(key)
        if bi is None:
            tb = TransformBlend()
            for j, wgt in key:
                tb.addTransform(joints[names[j]], wgt)
            bi = cache[key] = table.addBlend(tb)
        x, y, z = V[i]
        vw.setData3(x, y, z); nw.setData3(*N[i]); t0.setData2(x, z); t1.setData2(y, 0.0); bw.setData1i(bi)
    table.setRows(SparseArray.lowerOn(vd.getNumRows()))
    vd.setTransformBlendTable(table)
    tri = GeomTriangles(Geom.UHStatic)
    tri.setIndexType(Geom.NT_uint32)
    F = D["faces"]
    for a, b, c in F:
        tri.addVertices(int(a), int(b), int(c))
    g = Geom(vd); g.addPrimitive(tri)
    gn = GeomNode("smooth_body"); gn.addGeom(g)
    for old in actor.findAllMatches("**/+GeomNode"):
        old.detachNode()
    return ch.attachNewNode(gn)


if __name__ == "__main__":
    build()
