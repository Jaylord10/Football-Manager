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
for k, v in list(J.items()):
    if k.endswith(".l"):
        J[k[:-2] + ".r"] = (-v[0], v[1], v[2])

# Bones for the skin to follow: (joint, from, to) - a segment for each.
BONES = [("pelvis", "pelvis", "spine_01"), ("spine_01", "spine_01", "spine_02"), ("spine_02", "spine_02", "neck_01"),
         ("neck_01", "neck_01", "head"), ("head", "head", (0.0, -0.02, 1.76))]
for s in ("l", "r"):
    sx = 1 if s == "l" else -1
    BONES += [("clavicle." + s, "clavicle." + s, "upperarm." + s), ("upperarm." + s, "upperarm." + s, "lowerarm." + s),
              ("lowerarm." + s, "lowerarm." + s, "hand." + s), ("hand." + s, "hand." + s, (sx * 0.77, 0.005, 1.432)),
              ("thigh." + s, "thigh." + s, "calf." + s), ("calf." + s, "calf." + s, "foot." + s),
              ("foot." + s, "foot." + s, "ball." + s), ("ball." + s, "ball." + s, (sx * 0.199, -0.15, 0.02))]


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


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def shapes():
    """(name, field function, blend) - in the order they're melted together."""
    out = []
    add = lambda f, k=0.03: out.append((f, k))
    # trunk: a V from broad shoulders to a narrower waist, flat across the front
    add(lambda q: ellipsoid(q, (0.0, 0.005, 0.95), (0.148, 0.105, 0.115)))                    # hips
    add(lambda q: ellipsoid(q, (0.0, -0.005, 1.11), (0.135, 0.092, 0.16)), 0.08)               # waist
    add(lambda q: ellipsoid(q, (0.0, 0.0, 1.30), (0.172, 0.096, 0.165)), 0.08)                 # chest
    add(lambda q: ellipsoid(q, (0.0, -0.035, 1.305), (0.13, 0.07, 0.085)), 0.04)               # pecs (flat)
    add(lambda q: ellipsoid(q, (0.0, 0.025, 1.30), (0.165, 0.09, 0.14)), 0.06)                 # back (lats)
    add(lambda q: capsule(q, (-0.15, 0.01, 1.41), (0.15, 0.01, 1.41), 0.06, 0.06), 0.06)       # shoulder line
    add(lambda q: capsule(q, (0.0, 0.012, 1.38), (0.0, 0.0, 1.57), 0.057, 0.052), 0.04)       # neck
    # head
    add(lambda q: ellipsoid(q, (0.0, -0.018, 1.668), (0.084, 0.104, 0.108)), 0.035)
    add(lambda q: ellipsoid(q, (0.0, -0.05, 1.585), (0.062, 0.07, 0.05)), 0.03)               # jaw
    add(lambda q: ellipsoid(q, (0.0, -0.124, 1.618), (0.013, 0.02, 0.026)), 0.01)             # nose
    for sx in (-1, 1):
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.079, -0.012, 1.655), (0.012, 0.024, 0.03)), 0.01)   # ears
        # glutes
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.068, 0.05, 0.895), (0.075, 0.058, 0.085)), 0.05)
        # shoulders (deltoids) and arms
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.19, 0.008, 1.415), (0.07, 0.062, 0.062)), 0.05)
        add(lambda q, sx=sx: capsule(q, (sx * 0.19, 0.015, 1.425), (sx * 0.436, 0.011, 1.43), 0.052, 0.040), 0.03)
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.31, -0.012, 1.428), (0.075, 0.045, 0.043)), 0.025)   # biceps
        add(lambda q, sx=sx: capsule(q, (sx * 0.436, 0.011, 1.43), (sx * 0.644, 0.009, 1.43), 0.040, 0.028), 0.025)
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.50, 0.0, 1.43), (0.06, 0.04, 0.036)), 0.02)       # forearm
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.705, -0.004, 1.429), (0.068, 0.043, 0.02)), 0.02)  # hand
        add(lambda q, sx=sx: capsule(q, (sx * 0.665, -0.03, 1.425), (sx * 0.712, -0.085, 1.414), 0.012, 0.010), 0.012)
        # legs
        add(lambda q, sx=sx: capsule(q, (sx * 0.095, -0.006, 0.90), (sx * 0.136, 0.0, 0.533), 0.083, 0.055), 0.05)
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.112, -0.03, 0.75), (0.072, 0.07, 0.16)), 0.035)   # quads
        add(lambda q, sx=sx: capsule(q, (sx * 0.136, 0.0, 0.533), (sx * 0.178, 0.036, 0.115), 0.052, 0.034), 0.03)
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.145, 0.028, 0.40), (0.05, 0.052, 0.105)), 0.03)   # calf
        add(lambda q, sx=sx: ellipsoid(q, (sx * 0.19, -0.04, 0.052), (0.048, 0.135, 0.052)), 0.03)   # boot
    return out


def field(q):
    d = None
    for f, k in shapes():
        v = f(q)
        d = v if d is None else smin(d, v, k)
    return d


# --- building it ----------------------------------------------------------------------------------------------
def build(step=0.007, target=11000):
    from skimage.measure import marching_cubes
    import pyfqmr
    lo = np.array([-0.84, -0.22, -0.005], np.float32)
    hi = np.array([0.84, 0.20, 1.80], np.float32)
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
    s.simplify_mesh(target_count=target, aggressiveness=5, preserve_border=True, verbose=0)
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
    arm = np.clip((ax - 0.15) / 0.09, 0.0, 1.0)                    # (0 on the trunk, 1 out along the arm)
    for j, nm in enumerate(names):
        if nm.startswith("upperarm"):
            w[:, j] *= np.where(z > 1.25, arm ** 2, 0.0)
        elif nm.startswith(("lowerarm", "hand")):
            w[:, j] *= np.where(ax > 0.3, 1.0, 0.0)
        elif nm.startswith(("spine", "neck", "pelvis")):
            w[:, j] *= np.where(z > 1.25, (1.0 - arm) ** 2 + 0.02, 1.0)
        elif nm.startswith("clavicle"):
            w[:, j] *= 0.6
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
