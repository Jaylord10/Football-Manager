"""
broadcast3d/gait.py - movements the mannequin model doesn't come with, made here from real-world figures.

The mannequin has a standing ("idle") and a running animation, but no walk - so at walking pace it used to do a
slow-motion jog.  make_walk() builds a proper walk cycle, joint by joint, from normal human walking data:

  - hips: about 25-30 deg forward at heel strike, 10 deg back at toe-off;  knees: nearly straight at heel strike,
    ~15-20 deg as the weight comes on, ~60 deg as the foot swings through;  ankles: a little drop after heel
    strike, ~10 deg up at mid-stance, ~15-20 deg pushed down at toe-off  (Winter, "Biomechanics and Motor
    Control of Human Movement", 4th ed. ch. 4 / Perry & Burnfield, "Gait Analysis" 2nd ed.)
  - the body rises and falls ~4-5 cm a stride (lowest when both feet are down), sways ~2-4 cm side to side,
    the pelvis turns ~+/-4 deg, the chest turns the other way, the arms swing ~+/-15-20 deg against the legs
    with the elbows bent ~20-40 deg  (Perry & Burnfield; Meyns et al. 2013 "How to swing your arms").
  - one cycle (two steps) is 1 second at 30 frames; the viewer speeds it up or slows it to suit the pace
    (people walk ~1.6 steps a second at 1 m/s, ~1.9 at 1.4 m/s).

How a joint is turned: about an axis of the body as it stands (x = across him, z = up), fixed to the bone above
it - so a knee bends about the thigh's own across-axis wherever the thigh has swung.  The model faces -Y, his
right is -X.
"""
import math
from panda3d.core import (AnimBundle, AnimGroup, AnimChannelMatrixXfmTable, AnimBundleNode, NodePath, PTA_stdfloat,
                          LMatrix4f, LQuaternionf, LVecBase3f, TransformState, Vec3)

FPS = 30


def _cyc(keys, ph):
    """A smooth repeating curve through (phase, value) keys (phase 0..1): Catmull-Rom, wrapping round."""
    ph %= 1.0
    n = len(keys)
    for i in range(n):
        p0, v0 = keys[i]
        p1, v1 = keys[(i + 1) % n]
        span = (p1 - p0) % 1.0 or 1.0
        if (ph - p0) % 1.0 <= span:
            t = ((ph - p0) % 1.0) / span
            vm = keys[(i - 1) % n][1]
            vp = keys[(i + 2) % n][1]
            m0 = (v1 - vm) / 2.0
            m1 = (vp - v0) / 2.0
            t2, t3 = t * t, t * t * t
            return (2 * t3 - 3 * t2 + 1) * v0 + (t3 - 2 * t2 + t) * m0 + (-2 * t3 + 3 * t2) * v1 + (t3 - t2) * m1
    return keys[0][1]


# One stride, right heel strike at phase 0, left at 0.5.  Degrees; + = forward / bent / toes up.
HIP = [(0.00, 26), (0.12, 22), (0.30, 6), (0.50, -10), (0.62, -6), (0.75, 14), (0.88, 28)]
KNEE = [(0.00, 4), (0.13, 18), (0.30, 8), (0.42, 5), (0.60, 38), (0.72, 60), (0.85, 30), (0.95, 6)]
ANKLE = [(0.00, 0), (0.07, -6), (0.30, 5), (0.45, 10), (0.62, -18), (0.72, -6), (0.85, 0)]


def walk_pose(ph):
    """{joint: [(model axis, degrees), ...]} and the body's (x, y, z) shift (metres) at this point of the stride."""
    c, s = math.cos(2 * math.pi * ph), math.sin(2 * math.pi * ph)
    out = {}
    for side, off, sx in (("r", 0.0, -1), ("l", 0.5, 1)):
        p = ph + off
        out["thigh." + side] = [("x", -_cyc(HIP, p))]            # (forward is a turn of -x: the model faces -Y)
        out["calf." + side] = [("x", _cyc(KNEE, p))]
        out["foot." + side] = [("x", -_cyc(ANKLE, p))]
    swing = 17 * c                                                # right arm forward when the left leg is
    out["upperarm.r"] = [("x", swing)]
    out["upperarm.l"] = [("x", -swing)]
    out["lowerarm.r"] = [("x", -(10 + 8 * -c))]
    out["lowerarm.l"] = [("x", -(10 + 8 * c))]
    out["pelvis"] = [("z", -4 * c)]                               # (the right hip comes forward with the right leg)
    out["spine_01"] = [("z", 6 * c)]                              # (the chest turns against it)
    out["spine_02"] = [("z", 2 * c)]
    bob = -0.022 * math.cos(4 * math.pi * ph)                     # (lowest with both feet down)
    sway = -0.018 * s                                             # (over the right foot in the first half)
    return out, (sway, 0.0, bob)


def _local_mats(bundle, frame):
    """{joint: (its channel, its local matrix at this frame)} and the joint tree, from an animation."""
    mats, parent = {}, {}

    def walk(g, par):
        for i in range(g.getNumChildren()):
            ch = g.getChild(i)
            if isinstance(ch, AnimChannelMatrixXfmTable):
                m = LMatrix4f()
                ch.getValue(frame % max(1, bundle.getNumFrames()), m)
                mats[ch.getName()] = (ch, m)
                parent[ch.getName()] = par
                walk(ch, ch.getName())
            else:
                walk(ch, par)
    walk(bundle, None)
    return mats, parent


def _quat(m):
    q = LQuaternionf()
    ts = TransformState.makeMat(m)
    q.setHpr(ts.getHpr())
    return q, ts


def build(actor, name, pose_fn, frames, base_anim="idle", base_frame=0):
    """A new animation for the actor: each frame, the base animation's pose (one frame of it) with pose_fn(phase)
    turned on top.  Returns a NodePath holding it, for Actor.loadAnims({name: it})."""
    base = actor.getAnimControl(base_anim).getAnim()
    mats, parent = _local_mats(base, base_frame)
    # Each joint's whole turn (from the model) in the base pose: an axis of the body, fixed to the bone above.
    net = {}

    def net_q(j):
        if j is None:
            return LQuaternionf.identQuat()
        if j not in net:
            net[j] = _quat(mats[j][1])[0] * net_q(parent[j])
        return net[j]
    tables = {j: {k: [] for k in "hprxyz"} for j in mats}
    for f in range(frames):
        pose, shift = pose_fn(f / float(frames))
        for j, (ch, m) in mats.items():
            q, ts = _quat(m)
            pos = ts.getPos()
            for ax, deg in pose.get(j, ()):
                a = {"x": Vec3(1, 0, 0), "y": Vec3(0, 1, 0), "z": Vec3(0, 0, 1)}[ax]
                r = LQuaternionf()
                r.setFromAxisAngle(deg, a)
                pq = net_q(parent[j])
                q = q * (pq * r * pq.conjugate())
            if j == "pelvis":
                pos = pos + LVecBase3f(*shift)
            hpr = q.getHpr()
            t = tables[j]
            for k, v in zip("hpr", hpr):
                t[k].append(v)
            for k, v in zip("xyz", pos):
                t[k].append(v)
    nb = AnimBundle(name, FPS, frames)

    def copy(src, dst):
        for i in range(src.getNumChildren()):
            ch = src.getChild(i)
            if isinstance(ch, AnimChannelMatrixXfmTable):
                n = AnimChannelMatrixXfmTable(dst, ch.getName())
                for k in "ijkabc":                                       # (scale / shear: as in the base frame)
                    tb = ch.getTable(k)
                    if len(tb):
                        val = tb[base_frame % len(tb)] if len(tb) > 1 else tb[0]
                        n.setTable(k, _pta([val]))
                for k in "hprxyz":
                    n.setTable(k, _pta(tables[ch.getName()][k]))
                copy(ch, n)
            else:
                copy(ch, AnimGroup(dst, ch.getName()))
    copy(base, nb)
    return NodePath(AnimBundleNode(name, nb))


def _pta(vals):
    a = PTA_stdfloat.emptyArray(len(vals))
    for i, v in enumerate(vals):
        a[i] = v
    return a


_CACHE = {}


def add_walk(actor):
    """Give this actor (the mannequin) a "walk" animation (built once, shared by every player)."""
    if "walk" not in _CACHE:
        _CACHE["walk"] = build(actor, "walk", walk_pose, 30)
    actor.loadAnims({"walk": _CACHE["walk"]})
