"""
broadcast3d/mhbody.py - the footballer's body from MakeHuman (makehuman.org): a properly modelled man instead of
our own rounded shapes.  The MakeHuman base mesh, its shape targets and its skeleton weights are CC0 (public
domain: see makehuman/LICENSE.ASSETS.md, "explicitly released as CC0 in september 2020").

  python broadcast3d/mhbody.py      (needs the MakeHuman data: MH_DATA, default /tmp/mh/mh/makehuman/data -
                                     git clone https://github.com/makehumancommunity/makehuman, makehuman/data)
writes
  models/mh_body.npz        the body (an athletic young man, ~1.80 m), standing like our skeleton's rest pose
                            (arms straight out), with which bones each point follows
  models/footballer_mh.glb  our skeleton (the mannequin's, every joint) moved to his joints

How: his shape is MakeHuman's own "macro" mix of targets (male, 25, muscular, lean, ideal proportions - as its
sliders do it).  He's scaled to height and his limbs turned about his own joints from MakeHuman's relaxed pose to
our skeleton's (arms out sideways), skinned with MakeHuman's weights.  Then our skeleton's joints are moved onto
his - so his proportions are kept and every movement in gait.py still works (they're turns of the joints).
"""
import json
import os
import struct
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MH = os.environ.get("MH_DATA", "/tmp/mh/mh/makehuman/data")
SRC_GLB = os.path.join(HERE, "models", "footballer.glb")
OUT_GLB = os.path.join(HERE, "models", "footballer_mh.glb")
OUT = os.path.join(HERE, "models", "mh_body.npz")
CROWN = 1.80            # (the top of his head; players3d scales each player to his own height)
# His build (MakeHuman's slider values, 0..1): a young professional footballer - lean and muscular (body fat
# ~10%, e.g. Milanese et al. 2015 on Serie A players), average height, "ideal" proportions.
BUILD = dict(gender=1.0, age=25, muscle=0.72, weight=0.42, height=0.55, prop=0.75)
# ...and a footballer's legs: big, defined thighs (~57-60 cm round mid-thigh) and calves (~38-40 cm) - e.g.
# Hoshikawa et al. 2009 (MRI of soccer players' thigh muscles); MakeHuman's own leg sliders.
LEGS_EXTRA = {"armslegs/{s}-upperleg-muscle-incr.target": 1.0,                  # (calves as MakeHuman has them)
              "measure/measure-thigh-circ-incr.target": 0.8,
              "measure/measure-knee-circ-incr.target": 0.3, "armslegs/{s}-leg-valgus-decr.target": 1.0}


# --- MakeHuman's files ---------------------------------------------------------------------------------------
def load_obj(path=None):
    vs, faces, groups = [], [], []
    g = None
    for ln in open(path or os.path.join(MH, "3dobjs", "base.obj")):
        if ln.startswith("v "):
            vs.append([float(t) for t in ln.split()[1:4]])
        elif ln.startswith("g "):
            g = ln.split()[1]
        elif ln.startswith("f "):
            faces.append([int(t.split("/")[0]) - 1 for t in ln.split()[1:]])
            groups.append(g)
    return np.array(vs, np.float64), faces, groups


def target(rel):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        a = np.loadtxt(os.path.join(MH, "targets", rel), comments="#", ndmin=2)
    if a.size == 0:
        return np.zeros(0, int), np.zeros((0, 3))
    return a[:, 0].astype(int), a[:, 1:4]


def macro(gender=1.0, age=25, muscle=0.5, weight=0.5, height=0.5, prop=0.5, eth=(0.0, 0.0, 1.0)):
    """MakeHuman's macro targets and how much of each (its human.py / humanmodifier.py, the same sums)."""
    a = 0.5 + (age - 25) / 65.0 * 0.5 if age >= 25 else 0.1875 + (age - 10) / 15.0 * 0.3125
    f = {"male": gender, "female": 1 - gender}
    if a < 0.5:
        yv = max(0, (a - 0.1875) * 3.2)
        f.update(old=0, baby=max(0, 1 - a * 5.333), young=yv, child=max(0, min(1, 5.333 * a) - yv))
    else:
        f.update(child=0, baby=0, old=max(0, a * 2 - 1))
        f["young"] = 1 - f["old"]
    for nm, v in (("muscle", muscle), ("weight", weight)):
        mx, mn = max(0, v * 2 - 1), max(0, 1 - v * 2)
        f["max" + nm], f["min" + nm], f["average" + nm] = mx, mn, 1 - mx - mn
    for nm, v, lo, hi in (("height", height, "minheight", "maxheight"),
                          ("prop", prop, "uncommonproportions", "idealproportions")):
        mx, mn = max(0, v * 2 - 1), max(0, 1 - v * 2)
        f[hi], f[lo] = mx, mn
        f["averageheight" if nm == "height" else "regularproportions"] = 1 - max(mx, mn)
    f["african"], f["asian"], f["caucasian"] = eth
    out = {}
    for sub in ("macrodetails", "macrodetails/height", "macrodetails/proportions"):
        for fn in os.listdir(os.path.join(MH, "targets", sub)):
            if not fn.endswith(".target"):
                continue
            toks = fn[:-7].split("-")
            if toks[0] == "universal":
                toks = toks[1:]
            w = 1.0
            for t in toks:
                w *= f[t]
            if w > 1e-4:
                out[sub + "/" + fn] = w
    return out


def shaped(base, weights):
    v = base.copy()
    for rel, w in weights.items():
        i, d = target(rel)
        v[i] += w * d
    return v


def to_ours(v):
    """MakeHuman (decimetres, y up, facing +z) -> ours (metres, z up, facing -y; his left is +x in both)."""
    return np.stack([v[..., 0], -v[..., 2], v[..., 1]], -1) / 10.0


# --- our skeleton --------------------------------------------------------------------------------------------
def read_glb(path):
    b = open(path, "rb").read()
    jl = struct.unpack("<I", b[12:16])[0]
    js = json.loads(b[20:20 + jl])
    rest = b[20 + jl:]
    bl = struct.unpack("<I", rest[0:4])[0]
    binbuf = bytearray(rest[8:8 + bl])
    sk = js["skins"][0]
    acc = js["accessors"][sk["inverseBindMatrices"]]
    bv = js["bufferViews"][acc["bufferView"]]
    off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    ibm = np.frombuffer(bytes(binbuf[off:off + 64 * len(sk["joints"])]), np.float32).reshape(-1, 4, 4)
    G = {js["nodes"][ni]["name"]: np.linalg.inv(ibm[j].T.astype(np.float64)) for j, ni in enumerate(sk["joints"])}
    parent = {}
    for i, n in enumerate(js["nodes"]):
        for c in n.get("children", []):
            parent[js["nodes"][c]["name"]] = n["name"]
    return js, binbuf, off, G, parent


GL2P = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], np.float64)       # glTF (y up) -> Panda (z up)


def write_glb(js, binbuf, off, G, parent, pos):
    """Our skeleton with each joint moved to pos[name] (Panda space), its turn at rest kept."""
    nodes = js["nodes"]
    by = {n.get("name"): n for n in nodes}
    sk = js["skins"][0]
    newG = {}
    for nm, g in G.items():
        m = g.copy()
        if nm in pos:
            m[:3, 3] = GL2P.T @ pos[nm]
        newG[nm] = m
    for nm in G:
        p = parent.get(nm)
        local = np.linalg.inv(newG[p]) @ newG[nm] if p in newG else newG[nm]
        by[nm]["translation"] = [float(x) for x in local[:3, 3]]
    for j, ni in enumerate(sk["joints"]):
        ibm = np.linalg.inv(newG[nodes[ni]["name"]])
        binbuf[off + 64 * j: off + 64 * (j + 1)] = ibm.T.astype(np.float32).tobytes()
    js_b = json.dumps(js, separators=(",", ":")).encode()
    js_b += b" " * ((4 - len(js_b) % 4) % 4)
    out = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js_b) + 8 + len(binbuf))
    out += struct.pack("<I", len(js_b)) + b"JSON" + js_b + struct.pack("<I", len(binbuf)) + b"BIN\x00" + bytes(binbuf)
    open(OUT_GLB, "wb").write(out)


# --- MakeHuman's bones -> ours ---------------------------------------------------------------------------------
def our_bone(mh):
    """Which of our bones the skin on a MakeHuman bone follows."""
    side = "." + mh[-1].lower() if mh[-2:] in (".L", ".R") else ""
    n = mh[:-2] if side else mh
    if n in ("root", "spine05", "pelvis"):
        return "pelvis"
    if n in ("spine04", "spine03"):
        return "spine_01"
    if n in ("spine02", "spine01", "breast"):
        return "spine_02"
    if n.startswith("neck"):
        return "neck_01"
    if n in ("clavicle", "shoulder01"):
        return "clavicle" + side
    if n.startswith("upperarm"):
        return "upperarm" + side
    if n.startswith("lowerarm"):
        return "lowerarm" + side
    if n == "wrist" or n.startswith("metacarpal"):
        return "hand" + side
    if n.startswith("finger"):
        return {"1": "thumb", "2": "index", "3": "middle", "4": "ring", "5": "ring"}[n[6]] + f"_0{n[8]}" + side
    if n.startswith("upperleg"):
        return "thigh" + side
    if n.startswith("lowerleg"):
        return "calf" + side
    if n == "foot":
        return "foot" + side
    if n.startswith("toe"):
        return "ball" + side
    return "head"


def mh_joint(name, side, J):
    """Where our joint goes on him (J: MakeHuman's joint points, by bone: head)."""
    S = side.upper()
    if name == "pelvis":
        return (J["upperleg01.L"] + J["upperleg01.R"]) / 2 + np.array([0, 0, 0.027])
    m = {"spine_01": "spine04", "spine_02": "spine02", "neck_01": "neck01", "head": "head",
         "clavicle": f"clavicle.{S}", "upperarm": f"upperarm01.{S}", "lowerarm": f"lowerarm01.{S}",
         "hand": f"wrist.{S}", "thigh": f"upperleg01.{S}", "calf": f"lowerleg01.{S}", "foot": f"foot.{S}",
         "ball": f"toe3-1.{S}"}
    if name in m:
        return J[m[name]]
    f, k = name.split("_")
    return J[f"finger{ {'thumb': 1, 'index': 2, 'middle': 3, 'ring': 4}[f] }-{int(k)}.{S}"]


def rot_between(a, b):
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(a @ b)
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx / (1 + c)


def frame(d, side):
    d = d / np.linalg.norm(d)
    s = side - d * (side @ d)
    s /= np.linalg.norm(s)
    return np.stack([d, s, np.cross(d, s)], 1)


CHAINS = ["clavicle", "upperarm", "lowerarm", "hand"] + [f"{f}_0{k}" for f in ("thumb", "index", "middle", "ring")
                                                         for k in "123"]
LEGS = ["thigh", "calf", "foot", "ball"]


def build(eth=(0.0, 0.0, 1.0), build_=None):
    base, faces, groups = load_obj()
    tw = macro(eth=eth, **(build_ or BUILD))
    for k, w in LEGS_EXTRA.items():
        for sd in (("l", "r") if "{s}" in k else ("",)):
            tw[k.format(s=sd)] = w
    P = to_ours(shaped(base, tw))
    body_f = [q for q, g in zip(faces, groups) if g == "body"]
    used = np.unique(np.concatenate(body_f))
    P[:, 2] -= P[used, 2].min()
    global SCALE, MACRO
    SCALE = CROWN / P[used, 2].max()
    MACRO = tw
    P *= SCALE
    sk = json.load(open(os.path.join(MH, "rigs", "default.mhskel")))
    jp = {k: P[idx].mean(0) for k, idx in sk["joints"].items()}
    J = {b: jp[d["head"]] for b, d in sk["bones"].items()}
    T = {b: jp[d["tail"]] for b, d in sk["bones"].items()}
    js, binbuf, off, G, parent = read_glb(SRC_GLB)
    ours = {nm: GL2P @ g[:3, 3] for nm, g in G.items()}             # our joints at rest (Panda space)

    def our_tail(b):
        nm, sd = b.split(".")
        s = "." + sd
        nxt = {"clavicle": "upperarm", "upperarm": "lowerarm", "lowerarm": "hand", "hand": "middle_01",
               "thigh": "calf", "calf": "foot", "foot": "ball"}
        if nm in nxt:
            return ours[nxt[nm] + s]
        if nm == "ball":
            return ours[b] + np.array([0, -0.10, 0])
        f, k = nm.split("_")
        if k == "03":
            return ours[b] + (ours[b] - ours[f"{f}_02" + s])
        return ours[f"{f}_0{int(k) + 1}" + s]

    # MakeHuman's weights, gathered onto our bones
    W = json.load(open(os.path.join(MH, "rigs", "default_weights.mhw")))["weights"]
    names = sorted(G)
    col = {b: i for i, b in enumerate(names)}
    Wt = np.zeros((len(P), len(names)))
    for m, lst in W.items():
        if lst:
            a = np.array(lst)
            Wt[a[:, 0].astype(int), col[our_bone(m)]] += a[:, 1]
    Wt /= np.maximum(Wt.sum(1, keepdims=True), 1e-9)
    # His limbs turned from his relaxed pose to our rest pose, joint by joint down each chain (a turn about each
    # joint, taking the bones below with it); the trunk and head as they are.
    R = {b: np.eye(3) for b in names}
    piv = {b: np.zeros(3) for b in names}           # (where each bone's joint was, and goes)
    new = {}
    for sd in ("l", "r"):
        S = sd.upper()
        sgn = 1 if sd == "l" else -1
        side_mh = J[f"finger2-1.{S}"] - J[f"finger4-1.{S}"]
        side_ou = ours[f"index_01.{sd}"] - ours[f"ring_01.{sd}"]
        for chain in (CHAINS, LEGS):
            for nm in chain:
                b = f"{nm}.{sd}"
                if nm in ("clavicle",):
                    pb = None
                elif nm == "hand" or nm in ("upperarm", "lowerarm"):
                    pb = {"upperarm": "clavicle", "lowerarm": "upperarm", "hand": "lowerarm"}[nm] + "." + sd
                elif chain is LEGS:
                    pb = None if nm == "thigh" else LEGS[LEGS.index(nm) - 1] + "." + sd
                else:
                    f, k = nm.split("_")
                    pb = ("hand." + sd) if k == "01" else f"{f}_0{int(k) - 1}.{sd}"
                A = mh_joint(nm, sd, J)
                if nm == "ball":
                    B = A + (T[f"toe3-1.{S}"] - A) * 3.0
                elif nm == "hand":
                    B = J[f"finger3-1.{S}"]
                elif nm == "foot":
                    B = J[f"toe3-1.{S}"]
                elif "_0" in nm and nm.endswith("3"):
                    B = T[{"thumb": "finger1", "index": "finger2", "middle": "finger3", "ring": "finger4"}[nm[:-3]]
                          + f"-3.{S}"]
                else:
                    nb = {"clavicle": f"upperarm01.{S}", "upperarm": f"lowerarm01.{S}", "lowerarm": f"wrist.{S}",
                          "thigh": f"lowerleg01.{S}", "calf": f"foot.{S}"}.get(nm)
                    if nb is None:
                        f, k = nm.split("_")
                        nb = f"finger{ {'thumb': 1, 'index': 2, 'middle': 3, 'ring': 4}[f] }-{int(k) + 1}.{S}"
                    B = J[nb]
                Rp = R[pb] if pb else np.eye(3)
                a_new = new[pb] + Rp @ (A - mh_joint(pb.split(".")[0], sd, J)) if pb else A
                d_now = Rp @ (B - A)
                if nm in ("clavicle", "foot", "ball"):
                    Rl = np.eye(3)                       # (his shoulders and feet as MakeHuman made them)
                elif nm.startswith("thumb"):             # (the thumb lying along the hand, a little forward
                    td = np.array([sgn * 0.06, -0.026, -0.016])          #  and down - as a hand hangs)
                    if nm != "thumb_01":
                        td = np.array([sgn * 0.06, -0.018, -0.022])
                    Rl = rot_between(d_now, td)
                elif nm == "hand" or "_0" in nm:
                    Rh = frame(our_tail(b) - ours[b], side_ou) @ frame(d_now, Rp @ side_mh).T
                    Rl = Rh
                else:
                    Rl = rot_between(d_now, our_tail(b) - ours[b])
                R[b] = Rl @ Rp
                new[b] = a_new
                piv[b] = A
    # the skin: each point turned with its bones (linear blend skinning)
    out = np.zeros_like(P)
    for b in names:
        w = Wt[:, col[b]]
        m = w > 0
        if not m.any():
            continue
        out[m] += w[m, None] * ((P[m] - piv[b]) @ R[b].T + new.get(b, piv[b]))
    # our skeleton's joints, on him
    pos = {}
    for nm in names:
        base_nm, sd = (nm.split(".") + [""])[:2]
        p = mh_joint(base_nm, sd, J)
        pos[nm] = new.get(nm, p)
    return P, out, faces, groups, Wt, names, pos, (js, binbuf, off, G, parent)


# --- where the kit and face are painted ---------------------------------------------------------------------
# The shader paints the kit, face and hair from where each point is on the body (shaders/lit.frag), with its
# measurements made on our own body (body.py).  So each of his points is given the place on our body that
# matches it (feet, knees, hips, shoulders, elbows, wrists, chin, mouth, eyes, crown), and painted as that.
FACE = dict(chin=1.560, mouth=1.600, eye=1.690, eye_x=0.0298, eye_y=-0.1325, back_y=0.045)
OLD = dict(chin=1.538, mouth=1.5883, eye=1.6555, eye_x=0.033, eye_y=-0.098, back_y=0.104, crown=1.78)


def paint_map(pos):
    """Functions to and from 'painting' space for this skeleton (pos: his joints)."""
    kz = pos["calf.l"][2]
    zs = [(0.0, 0.0), (pos["foot.l"][2], 0.11), (kz - 0.035, 0.5335),           # (socks to below his calf's top,
          (kz + 0.115, 0.622), (pos["thigh.l"][2], 0.921),                       #  shorts a hand above the knee)
          (pos["upperarm.l"][2], 1.433), (1.515, 1.49), (FACE["chin"], OLD["chin"]), (FACE["mouth"], OLD["mouth"]),
          (FACE["eye"], OLD["eye"]), (CROWN, OLD["crown"]), (CROWN + 1.0, OLD["crown"] + 1.0)]
    zm, zo = np.array([a for a, _ in zs]), np.array([b for _, b in zs])
    xs = [(0.0, 0.0), (0.15, 0.15), (pos["upperarm.l"][0], 0.1744), (pos["lowerarm.l"][0], 0.5054),
          (pos["hand.l"][0], 0.7653), (pos["middle_01.l"][0], 0.8765), (pos["middle_01.l"][0] + 1.0, 1.8765)]
    xm, xo = np.array([a for a, _ in xs]), np.array([b for _, b in xs])
    ky = (OLD["back_y"] - OLD["eye_y"]) / (FACE["back_y"] - FACE["eye_y"])
    kx = OLD["eye_x"] / FACE["eye_x"]

    def head_w(z):
        return np.clip((z - 1.50) / 0.05, 0.0, 1.0)

    def fwd(v):
        x, y, z = v[:, 0], v[:, 1], v[:, 2]
        h = head_w(z)
        arm = np.clip((z - 1.15) / 0.1, 0.0, 1.0) * (1 - h)
        ax = np.abs(x)
        xa = np.sign(x) * np.interp(ax, xm, xo)
        x2 = x * (1 - arm) + xa * arm
        x2 = x2 * (1 - h) + x * kx * h
        y2 = y * (1 - h) + (OLD["eye_y"] + (y - FACE["eye_y"]) * ky) * h
        z2 = np.interp(z, zm, zo)
        # the shorts come up higher at the back, over his glutes (painted lower there: the shorts' top is 0.927)
        sy = np.clip((y + 0.01) / 0.03, 0, 1)
        sy = sy * sy * (3 - 2 * sy)
        hat = np.clip((z2 - 0.80) / 0.08, 0, 1) * np.clip((1.06 - z2) / 0.10, 0, 1)
        z2 = z2 - 0.045 * sy * hat * (np.abs(x) < 0.25)
        return np.stack([x2, y2, z2], 1)

    def back(v):
        """(for things made on our body - the haircuts - put onto his head)"""
        x, y, z0 = v[:, 0], v[:, 1], v[:, 2]
        z = np.interp(z0, zo, zm)
        h = head_w(z)
        x2 = x / (1 - h + h * kx)
        y2 = (y - h * (OLD["eye_y"] - FACE["eye_y"] * ky)) / (1 - h + h * ky)
        return np.stack([x2, y2, z], 1)
    return fwd, back


# --- the kit: loose, and boots ---------------------------------------------------------------------------------
def _boot_sdf(q):
    """Our football boot (body.py's: snug heel, low instep, widest at the ball of the foot, flat sole), put
    on his foot: q his points (one side, x > 0)."""
    import body as ob
    o = np.stack([q[:, 0] - 0.205 + 0.19, (q[:, 1] + 0.0095) / 1.08 - 0.04, q[:, 2]], 1).astype(np.float32)
    d = ob.ellipsoid(o, (0.182, 0.045, 0.048), (0.034, 0.042, 0.046))
    for f in (lambda o: ob.capsule(o, (0.184, 0.03, 0.05), (0.192, -0.085, 0.037), 0.04, 0.034),
              lambda o: ob.ellipsoid(o, (0.193, -0.085, 0.033), (0.047, 0.05, 0.031)),
              lambda o: ob.ellipsoid(o, (0.195, -0.127, 0.03), (0.037, 0.04, 0.027))):
        d = ob.smin(d, f(o), 0.02)
    return np.maximum(d, 0.004 - o[:, 2])


def boot_mesh(step=0.003, target=900):
    """The boot as its own mesh (left foot; mirrored for the right): points, normals, faces, painting places."""
    from skimage.measure import marching_cubes
    import pyfqmr
    lo, hi = np.array([0.13, -0.18, -0.01]), np.array([0.28, 0.15, 0.13])
    n = np.ceil((hi - lo) / step).astype(int) + 1
    g = np.stack(np.meshgrid(*[lo[i] + np.arange(n[i]) * step for i in range(3)], indexing="ij"), -1)
    f = _boot_sdf(g.reshape(-1, 3)).reshape(g.shape[:3])
    v, fc, _, _ = marching_cubes(f, 0.0, spacing=(step,) * 3)
    v += lo
    sm = pyfqmr.Simplify(); sm.setMesh(v, fc)
    sm.simplify_mesh(target_count=target, aggressiveness=5, preserve_border=True, verbose=0)
    v, fc, _ = sm.getMesh()
    f0 = _boot_sdf(v)
    nrm = np.stack([(_boot_sdf(v + np.eye(3)[i] * 1e-3) - f0) / 1e-3 for i in range(3)], 1)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    a, b, c = v[fc[:, 0]], v[fc[:, 1]], v[fc[:, 2]]
    if (np.einsum("ij,ij->i", np.cross(b - a, c - a), nrm[fc[:, 0]]) < 0).mean() > 0.5:
        fc = fc[:, ::-1].copy()
    paint = np.stack([v[:, 0] - 0.205 + 0.19, (v[:, 1] + 0.0095) / 1.08 - 0.04, v[:, 2]], 1)
    return v, nrm, fc, paint


# A footballer's legs, defined: the kneecap, the inner "teardrop" above the knee (vastus medialis), the outer
# quad, the calf's two heads (the inner one bigger and lower) - raised a little on MakeHuman's smooth legs.
# (offset from the knee joint: out, forward(-)/back(+), up; size; height of the bump - metres)
# (which way from the knee - out, forward(-)/back(+) - and how high; size; height of the bump, metres: each put
#  on the skin that way)
LEG_BUMPS = [((0.0, -1.0), 0.012, 0.020, 0.006),            # kneecap
             ((-0.8, -0.7), 0.075, 0.026, 0.010),           # teardrop
             ((0.9, -0.5), 0.13, 0.038, 0.007)]             # outer quad


def define_legs(V, N, pos):
    V = V.copy()
    for sd, sg in (("l", 1), ("r", -1)):
        K = pos["calf." + sd]
        side = np.sign(V[:, 0]) == sg
        for (o, f), u, sig, amp in LEG_BUMPS:
            d = np.array([sg * o, f]) / np.hypot(o, f)
            ring = side & (np.abs(V[:, 2] - K[2] - u) < 0.008) & (np.hypot(*(V[:, :2] - K[:2]).T) < 0.09)
            c = V[ring][np.argmax((V[ring, :2] - K[:2]) @ d)]
            g = np.exp(-((V - c) ** 2).sum(1) / (2 * sig * sig)) * side
            V += (amp * g)[:, None] * N
    return V


def dress(V, paint, pos):
    """His shirt and shorts hanging loose (as our own body's did), sleeves standing off the arm, boots on."""
    V = V.copy()
    px, pz = np.abs(paint[:, 0]), paint[:, 2]
    x, y, z = V[:, 0], V[:, 1], V[:, 2]
    ss = lambda a, b, t: np.clip((t - a) / (b - a), 0, 1) ** 2 * (3 - 2 * np.clip((t - a) / (b - a), 0, 1))
    # the shirt: an oval tube hanging straight down from the chest (untucked), a little off the skin all over
    w = ss(0.915, 0.928, pz) * (1 - ss(1.30, 1.36, z)) * (1 - ss(0.15, 0.19, px))
    cy = -0.038
    hang = 1 - ss(0.93, 1.25, pz)                       # (fuller towards the hem, as a shirt hangs over the hips)
    rx, ry = 0.168 + 0.006 * hang, 0.112 + 0.012 * hang
    rho = np.sqrt((x / rx) ** 2 + ((y - cy) / ry) ** 2)
    k = np.where(rho < 1, 1 / np.maximum(rho, 1e-6), 1.0)
    V[:, 0] += w * (x * k - x)
    V[:, 1] += w * ((y - cy) * k + cy - y)
    # the shorts: wide legs down to a hand above the knee
    for sd, sg in (("l", 1), ("r", -1)):
        a, b = pos["thigh." + sd].copy(), pos["calf." + sd].copy()
        a[0] -= sg * 0.035                              # (the legs of the shorts hang from under the hips, closer
        b[0] -= sg * 0.032                              #  together - loose down the middle, no gap between)
        m = (np.sign(x) == sg) | (np.abs(x) < 0.01)
        w = ss(0.612, 0.622, pz) * (1 - ss(0.95, 0.99, pz)) * m          # (a sharp hem: the leg of the shorts)
        ab = b - a
        t = ((V - a) @ ab) / (ab @ ab)
        c = a + t[:, None] * ab
        r = 0.098 + 0.004 * np.clip(t, 0, 1)
        d = V - c
        dl = np.linalg.norm(d * np.array([1.0, 1.12, 1.0]), axis=1)        # (a little flatter front to back)
        tube = 1 - ss(0.86, 0.93, pz)                   # (lower down: the tube itself, like a real pair -
        k = np.where(dl < r, r / np.maximum(dl, 1e-6), 1.0)    #  over the thigh's muscles; higher: over the hips)
        k = k * (1 - tube) + (r / np.maximum(dl, 1e-6)) * tube
        V += (w * (k - 1))[:, None] * d
    # the sleeves: standing off the upper arm, down to half way
    for sd, sg in (("l", 1), ("r", -1)):
        a, b = pos["upperarm." + sd], pos["lowerarm." + sd]
        m = (np.sign(V[:, 0]) == sg) & (z > 1.2)
        w = ss(0.16, 0.24, px) * (1 - ss(0.352, 0.36, px)) * m
        ab = b - a
        t = ((V - a) @ ab) / (ab @ ab)
        c = a + t[:, None] * ab
        r = 0.058 - 0.004 * np.clip(t * 2, 0, 1)
        d = V - c
        dl = np.linalg.norm(d, axis=1)
        k = np.where(dl < r, r / np.maximum(dl, 1e-6), 1.0)
        V += (w * (k - 1))[:, None] * d
    # boots: the foot's points moved onto the boot's surface (the toes go)
    for sg in (1, -1):
        m = (np.sign(V[:, 0]) == sg) & (V[:, 2] < 0.13)
        q = V[m] * np.array([sg, 1, 1])
        w = 1 - ss(0.08, 0.115, q[:, 2])
        for _ in range(8):
            f = _boot_sdf(q) + 0.003                     # (just inside it: the boot itself is its own mesh)
            e = 1e-3
            g = np.stack([(_boot_sdf(q + np.eye(3)[i] * e) - f + 0.003) / e for i in range(3)], 1)
            f = np.maximum(f, 0.0)
            q = q - (w * f)[:, None] * g / np.maximum((g * g).sum(1, keepdims=True), 1e-9)
        V[m] = q * np.array([sg, 1, 1])
    return V


def cover_cleft(V, F):
    """The shirt (and the top of the shorts) don't go into the cleft of his backside: across the middle the cloth
    spans from one side to the other, smoothed."""
    V = V.copy()
    x, y, z = V[:, 0], V[:, 1], V[:, 2]
    zone = (z > 0.80) & (z < 1.06) & (np.abs(x) < 0.10)
    span = np.zeros(len(V), bool)
    for zc in np.arange(0.80, 1.06, 0.01):
        sl = zone & (np.abs(z - zc) < 0.006)
        for side in (1,):                                    # (the back)
            near = sl & (side * y > 0) & (np.abs(x) > 0.035) & (np.abs(x) < 0.10)
            if not near.any():
                continue
            peak = (side * y[near]).max()
            fade = np.clip((zc - 0.80) / 0.06, 0, 1) * np.clip((1.06 - zc) / 0.05, 0, 1)
            mid = sl & (side * y > 0) & (np.abs(x) < 0.07)
            want = side * (peak - 0.006 - 0.004 * (np.abs(x[mid]) / 0.07) ** 2)
            low = side * y[mid] < side * want
            idx = np.where(mid)[0][low]
            y[idx] = y[idx] + (want[low] - y[idx]) * fade
            span[idx] = True
    V[:, 1] = y
    # a few rounds of smoothing over what was moved (and round it), so the cloth is even
    nb = [[] for _ in range(len(V))]
    for a, b, c in F:
        nb[a] += [b, c]; nb[b] += [a, c]; nb[c] += [a, b]
    grow = span.copy()
    for a, b, c in F:
        if span[a] or span[b] or span[c]:
            grow[[a, b, c]] = True
    idx = np.where(grow & ((V[:, 2] > 0.965) | (V[:, 2] < 0.90)))[0]     # (not across the shirt's hem)
    for _ in range(6):
        avg = np.array([V[nb[i]].mean(0) for i in idx])
        V[idx] = V[idx] * 0.5 + avg * 0.5
    return V


# --- every player his own face ------------------------------------------------------------------------------
# MakeHuman's face sliders (each from its "decrease" to its "increase" target, both sides together), stored as
# how far each point of the head moves; players3d picks each player's settings from his name (and skin), and
# the mix of MakeHuman's African / Asian / European face shapes from his skin tone.
FACE_SLIDERS = [
    ("nose_width", ["nose/nose-scale-horiz-decr"], ["nose/nose-scale-horiz-incr"]),
    ("nose_length", ["nose/nose-scale-vert-decr"], ["nose/nose-scale-vert-incr"]),
    ("nose_hump", ["nose/nose-hump-decr"], ["nose/nose-hump-incr"]),
    ("nose_tip", ["nose/nose-point-down"], ["nose/nose-point-up"]),
    ("nostrils", ["nose/nose-flaring-decr"], ["nose/nose-flaring-incr"]),
    ("chin", ["chin/chin-prominent-decr"], ["chin/chin-prominent-incr"]),
    ("chin_width", ["chin/chin-width-decr"], ["chin/chin-width-incr"]),
    ("jaw", ["chin/chin-bones-decr"], ["chin/chin-bones-incr"]),
    ("mouth_width", ["mouth/mouth-scale-horiz-decr"], ["mouth/mouth-scale-horiz-incr"]),
    ("lips", ["mouth/mouth-lowerlip-volume-decr", "mouth/mouth-upperlip-volume-decr"],
     ["mouth/mouth-lowerlip-volume-incr", "mouth/mouth-upperlip-volume-incr"]),
    ("cheekbones", ["cheek/l-cheek-bones-decr", "cheek/r-cheek-bones-decr"],
     ["cheek/l-cheek-bones-incr", "cheek/r-cheek-bones-incr"]),
    ("cheeks", ["cheek/l-cheek-volume-decr", "cheek/r-cheek-volume-decr"],
     ["cheek/l-cheek-volume-incr", "cheek/r-cheek-volume-incr"]),
    ("eye_size", ["eyes/l-eye-scale-decr", "eyes/r-eye-scale-decr"], ["eyes/l-eye-scale-incr", "eyes/r-eye-scale-incr"]),
    ("eye_height", ["eyes/l-eye-trans-down", "eyes/r-eye-trans-down"], ["eyes/l-eye-trans-up", "eyes/r-eye-trans-up"]),
    ("brows", ["eyebrows/eyebrows-trans-down"], ["eyebrows/eyebrows-trans-up"]),
    ("brow_angle", ["eyebrows/eyebrows-angle-down"], ["eyebrows/eyebrows-angle-up"]),
    ("forehead", ["forehead/forehead-trans-backward"], ["forehead/forehead-trans-forward"]),
    ("ears", ["ears/l-ear-scale-decr", "ears/r-ear-scale-decr"], ["ears/l-ear-scale-incr", "ears/r-ear-scale-incr"]),
    ("ears_out", ["ears/l-ear-wing-decr", "ears/r-ear-wing-decr"], ["ears/l-ear-wing-incr", "ears/r-ear-wing-incr"]),
    ("face_shape", ["head/head-oval"], ["head/head-square"]),
    ("neck", ["neck/neck-scale-horiz-decr"], ["neck/neck-scale-horiz-incr"]),
]


def face_morphs(nbase, used, Vb):
    """(which points, [slider: (towards -1, towards +1)] point moves, in our space) for the head and neck."""
    def delta(rels):
        d = np.zeros((nbase, 3))
        for rel in rels:
            i, dd = target(rel + ".target")
            d[i] += dd
        return to_ours(d)[used] * SCALE
    head = Vb[:, 2] > 1.40
    out = []
    for nm, neg, pos_ in FACE_SLIDERS:
        out.append((delta(neg), delta(pos_)))
    # the face shapes MakeHuman has for African, Asian and European men (the head only, fading out down the neck)
    def macro_delta(eth):
        a, b = macro(eth=eth, **BUILD), MACRO
        d = np.zeros((nbase, 3))
        for rel in set(a) | set(b):
            if not rel.startswith("macrodetails/") or "/height/" in rel or "/proportions/" in rel:
                continue
            w = a.get(rel, 0.0) - b.get(rel, 0.0)
            if w:
                i, dd = target(rel)
                d[i] += w * dd
        d = to_ours(d)[used] * SCALE
        ring = (Vb[:, 2] > 1.50) & (Vb[:, 2] < 1.56) & (np.abs(Vb[:, 0]) < 0.07)
        return d - d[ring].mean(0)              # (his face's shape, not how much taller or shorter he'd be)
    fade = np.clip((Vb[:, 2] - 1.47) / 0.06, 0, 1)[:, None]
    eth = [macro_delta((1.0, 0.0, 0.0)) * fade, macro_delta((0.0, 1.0, 0.0)) * fade]
    moved = head & (np.abs(np.stack([a for p in out for a in p] + eth)).max((0, 2)) > 1e-5)
    idx = np.where(moved)[0]
    M = np.stack([np.stack([p[0][idx], p[1][idx]]) for p in out]).astype(np.float16)
    E = np.stack([e[idx] for e in eth]).astype(np.float16)
    return idx, M, E


def main():
    P, V, faces, groups, Wt, names, pos, glb = build()
    write_glb(*glb, pos)
    body_f = [q for q, g in zip(faces, groups) if g == "body"]
    F = np.array([[q[0], q[1], q[2]] for q in body_f] + [[q[0], q[2], q[3]] for q in body_f], np.int64)
    used = np.unique(F)
    remap = -np.ones(len(V), np.int64)
    remap[used] = np.arange(len(used))
    Vb, Fb, Wb = V[used], remap[F], Wt[used]
    fwd, back = paint_map(pos)
    paint = fwd(Vb)
    n0 = np.zeros_like(Vb)
    fn0 = np.cross(Vb[Fb[:, 1]] - Vb[Fb[:, 0]], Vb[Fb[:, 2]] - Vb[Fb[:, 0]])
    for k in range(3):
        np.add.at(n0, Fb[:, k], fn0)
    n0 /= np.maximum(np.linalg.norm(n0, axis=1, keepdims=True), 1e-12)
    Vb = define_legs(Vb, n0, pos)
    Vb = dress(Vb, paint, pos)
    Vb = cover_cleft(Vb, Fb)
    # (where the shirt meets the shorts across the middle of his back, the line between them evened out)
    seam = np.where((np.abs(Vb[:, 0]) < 0.06) & (Vb[:, 1] > 0) & (Vb[:, 2] > 0.85) & (Vb[:, 2] < 1.02))[0]
    nb = {}
    for a, b, c in Fb:
        for i, j, k in ((a, b, c), (b, a, c), (c, a, b)):
            nb.setdefault(i, []).extend((j, k))
    for _ in range(12):
        paint[seam, 2] = 0.5 * paint[seam, 2] + 0.5 * np.array([paint[nb[i], 2].mean() for i in seam])
    nrm = np.zeros_like(Vb)
    fn = np.cross(Vb[Fb[:, 1]] - Vb[Fb[:, 0]], Vb[Fb[:, 2]] - Vb[Fb[:, 0]])
    for k in range(3):
        np.add.at(nrm, Fb[:, k], fn)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    # the boots: their own meshes, the left and the right, going with the foot (the toes with the ball joint)
    bv, bn, bf, bp = boot_mesh()
    for sg, sd in ((1, "l"), (-1, "r")):
        M = np.array([sg, 1, 1])
        wb = np.zeros((len(bv), len(names)))
        t = np.clip((pos["ball." + sd][1] + 0.01 - bv[:, 1]) / 0.03, 0, 1)      # (ahead of the ball of the foot)
        wb[:, names.index("foot." + sd)] = 1 - t
        wb[:, names.index("ball." + sd)] = t
        fc = bf if sg > 0 else bf[:, ::-1]
        Fb = np.concatenate([Fb, fc + len(Vb)])
        Vb = np.concatenate([Vb, bv * M])
        nrm = np.concatenate([nrm, bn * M])
        Wb = np.concatenate([Wb, wb])
        paint = np.concatenate([paint, bp * M])
    keep = 4
    order = np.argsort(-Wb, axis=1)[:, :keep]
    ww = np.take_along_axis(Wb, order, 1)
    ww /= ww.sum(1, keepdims=True)
    extra = {}
    # the haircuts made for our own head (body.py), put onto his
    import body as _ob
    if os.path.exists(_ob.OUT):
        D = np.load(_ob.OUT)
        for k in D.files:
            if k.startswith("hair_") and k.endswith("_verts"):
                nm = k[:-6]
                extra[k] = back(D[k].astype(np.float64)).astype(np.float32)
                extra[nm + "_paint"] = D[k]
                extra[nm + "_normals"] = D[nm + "_normals"]
                extra[nm + "_faces"] = D[nm + "_faces"]
    fi, fm, fe = face_morphs(len(V), used, Vb[:len(used)])
    extra.update(face_idx=fi.astype(np.int32), face_morph=fm, face_eth=fe,
                 face_names=np.array([f[0] for f in FACE_SLIDERS]))
    np.savez_compressed(OUT, verts=Vb.astype(np.float32), normals=nrm.astype(np.float32), faces=Fb.astype(np.int32),
                        bone_idx=order.astype(np.int16), bone_w=ww.astype(np.float32), bones=np.array(names),
                        paint=paint.astype(np.float32), **extra)
    print(f"mh body: {len(Vb)} points, {len(Fb)} triangles -> {OUT}; skeleton -> {OUT_GLB}")


if __name__ == "__main__":
    main()
