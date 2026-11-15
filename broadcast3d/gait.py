"""
broadcast3d/gait.py - movements the mannequin model doesn't come with, made here from real-world figures.

The mannequin comes with a standing ("idle") and a running animation only.  Everything else - walking, kicks,
shots, touches, headers, tackles, a keeper's set position, dives, throw-ins, celebrations - is built here as
proper animations (key poses, eased in between), so they blend smoothly with the running and the standing, and
the whole body takes part (arms out for balance, hips and shoulders turning), not just a leg.

Poses are written in plain movements, in degrees (see MOVES): "hip_r" + = right thigh swung forward, "knee_r" +
= bent, "ankle_r" + = toes up, "arm_r" + = right arm swung forward, "out_r" + = right arm lifted out to the side,
"elbow_r" + = bent, "lean" / "chest" + = bending forward, "turn" + = hips turned to his left (right hip forward),
"twist" + = shoulders turned to his left, "nod" + = head forward, "tilt" + = leaning over to his right.
Each is a turn about an axis of the body as it stands (x across him, y front-to-back, z up), fixed to the bone
above - so a knee bends about the thigh's own across-axis wherever the thigh has swung.  The model faces -Y and
his right is -X.  After posing, each frame is "grounded": the body is lowered or raised so the lower foot stays on
the grass (unless the pose says he's off the ground).

The walk, from normal human walking data:
  - hips about 25-30 deg forward at heel strike, 10 deg back at toe-off;  knees nearly straight at heel strike,
    ~15-20 deg as the weight comes on, ~60 deg as the foot swings through;  ankles a little drop after heel
    strike, ~10 deg up at mid-stance, ~15-20 deg pushed down at toe-off  (Winter, "Biomechanics and Motor
    Control of Human Movement", 4th ed. ch. 4;  Perry & Burnfield, "Gait Analysis", 2nd ed.)
  - the body sways ~2-4 cm side to side, the pelvis turns ~+/-4 deg, the chest the other way, the arms swing
    ~+/-15-20 deg against the legs with the elbows bent ~20-40 deg  (Perry & Burnfield; Meyns et al. 2013,
    "How to swing your arms").  One cycle (two steps) is 1 s at 30 frames; the viewer sets the pace.
The kicks, from studies of the instep kick (Lees et al. 2010, "The biomechanics of kicking in soccer: a review",
J Sports Sci 28(8)):  the standing foot is planted beside the ball with the knee bent ~25-40 deg; the kicking hip
goes ~30 deg back with the knee bent ~90-110 deg at the top of the backswing, then whips through - knee
straightening fast just before contact - to ~60-80 deg forward in the follow-through; the pelvis turns ~20-30
deg back and then through towards the target; the arm on the standing-leg side swings out wide for balance.
"""
import math
from panda3d.core import (AnimBundle, AnimGroup, AnimChannelMatrixXfmTable, AnimBundleNode, NodePath, PTA_stdfloat,
                          LMatrix4f, LQuaternionf, LVecBase3f, TransformState, Vec3, LPoint3f)

FPS = 30

# Plain movements -> (joint, axis of the body, sign).
MOVES = {
    "hip_r": ("thigh.r", "x", -1), "hip_l": ("thigh.l", "x", -1),
    "hipout_r": ("thigh.r", "y", 1), "hipout_l": ("thigh.l", "y", -1),
    "knee_r": ("calf.r", "x", 1), "knee_l": ("calf.l", "x", 1),
    "ankle_r": ("foot.r", "x", -1), "ankle_l": ("foot.l", "x", -1),
    "arm_r": ("upperarm.r", "x", -1), "arm_l": ("upperarm.l", "x", -1),
    "out_r": ("upperarm.r", "y", 1), "out_l": ("upperarm.l", "y", -1),
    "elbow_r": ("lowerarm.r", "x", -1), "elbow_l": ("lowerarm.l", "x", -1),
    "across_r": ("upperarm.r", "z", 1), "across_l": ("upperarm.l", "z", -1),
    "turn": ("pelvis", "z", 1), "tilt": ("pelvis", "y", 1),
    "lean": ("spine_01", "x", 1), "chest": ("spine_02", "x", 1), "twist": ("spine_01", "z", 1),
    "side": ("spine_01", "y", 1),
    "nod": ("neck_01", "x", 1),
}
AXES = {"x": Vec3(1, 0, 0), "y": Vec3(0, 1, 0), "z": Vec3(0, 0, 1)}


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


# --- the walk -------------------------------------------------------------------------------------------------
# One stride, right heel strike at phase 0, left at 0.5.
HIP = [(0.00, 26), (0.12, 22), (0.30, 6), (0.50, -10), (0.62, -6), (0.75, 14), (0.88, 28)]
KNEE = [(0.00, 4), (0.13, 18), (0.30, 8), (0.42, 5), (0.60, 38), (0.72, 60), (0.85, 30), (0.95, 6)]
ANKLE = [(0.00, 0), (0.07, -6), (0.30, 5), (0.45, 10), (0.62, -18), (0.72, -6), (0.85, 0)]


def walk_pose(ph):
    c, s = math.cos(2 * math.pi * ph), math.sin(2 * math.pi * ph)
    m = {}
    for side, off in (("r", 0.0), ("l", 0.5)):
        m["hip_" + side] = _cyc(HIP, ph + off)
        m["knee_" + side] = _cyc(KNEE, ph + off)
        m["ankle_" + side] = _cyc(ANKLE, ph + off)
    m["arm_r"], m["arm_l"] = -17 * c, 17 * c                      # (each arm forward with the other leg)
    m["elbow_r"], m["elbow_l"] = 10 - 8 * c, 10 + 8 * c
    m["turn"] = 4 * c                                             # (the right hip comes forward with the right leg)
    m["twist"] = -7 * c                                           # (the shoulders turn against it)
    m["tilt"] = 2 * s
    return m, {"sway": -0.018 * s}                                # (over the right foot in the first half)


# --- actions: key poses at seconds from the moment (the ball struck, the dive's start...) ---------------------------
# "air": metres he is off the ground (no grounding then).  "hold": the pose stays put (a held stance).
N = {}
ACTIONS = {
    # A pass / clearance with the right instep.
    "kick": [(-0.32, N),
             (-0.14, {"hip_r": -28, "knee_r": 95, "ankle_r": -20, "hip_l": 12, "knee_l": 30, "turn": -16, "twist": -6,
                      "lean": 4, "out_l": 50, "arm_l": 15, "elbow_l": 30, "out_r": 25, "arm_r": -20, "elbow_r": 25}),
             (0.00, {"hip_r": 24, "knee_r": 35, "ankle_r": -30, "hip_l": 10, "knee_l": 32, "turn": 8, "twist": 6,
                     "lean": 2, "out_l": 60, "arm_l": 10, "elbow_l": 25, "out_r": 30, "arm_r": -25, "elbow_r": 20}),
             (0.14, {"hip_r": 55, "knee_r": 10, "ankle_r": -25, "hip_l": 5, "knee_l": 25, "turn": 18, "twist": 10,
                     "lean": -2, "out_l": 45, "arm_l": 20, "elbow_l": 30, "out_r": 25, "arm_r": -10, "elbow_r": 25}),
             (0.40, N)],
    # A shot: a longer backswing and a bigger follow-through, over the ball to keep it down.
    "shot": [(-0.36, N),
             (-0.14, {"hip_r": -35, "knee_r": 110, "ankle_r": -25, "hip_l": 15, "knee_l": 35, "turn": -24, "twist": -10,
                      "lean": 8, "out_l": 60, "arm_l": 25, "elbow_l": 30, "out_r": 35, "arm_r": -35, "elbow_r": 30}),
             (0.00, {"hip_r": 30, "knee_r": 40, "ankle_r": -35, "hip_l": 12, "knee_l": 35, "turn": 10, "twist": 8,
                     "lean": 12, "chest": 4, "out_l": 70, "arm_l": 10, "elbow_l": 25, "out_r": 40, "arm_r": -30,
                     "elbow_r": 20}),
             (0.16, {"hip_r": 75, "knee_r": 12, "ankle_r": -25, "hip_l": 5, "knee_l": 25, "turn": 26, "twist": 14,
                     "lean": 6, "out_l": 50, "arm_l": 25, "elbow_l": 35, "out_r": 30, "arm_r": -10, "elbow_r": 30}),
             (0.30, {"hip_r": 35, "knee_r": 30, "ankle_r": -10, "knee_l": 15, "turn": 12, "twist": 6, "lean": 4,
                     "out_l": 30, "arm_l": 15, "elbow_l": 30, "out_r": 20, "elbow_r": 30}),
             (0.48, N)],
    # A touch while dribbling: a little push with the right foot (blended lightly over the running).
    "touch": [(-0.16, N),
              (-0.06, {"hip_r": -8, "knee_r": 45, "ankle_r": -10, "knee_l": 15}),
              (0.00, {"hip_r": 22, "knee_r": 20, "ankle_r": -15, "knee_l": 15, "out_l": 15}),
              (0.16, N)],
    # A header: arms up for balance and leverage, back arched, then the neck and trunk snap forward.
    "header": [(-0.30, N),
               (-0.10, {"lean": -14, "chest": -6, "nod": -14, "out_l": 60, "out_r": 60, "arm_l": 40, "arm_r": 40,
                        "elbow_l": 70, "elbow_r": 70, "hip_r": 25, "knee_r": 55, "hip_l": 10, "knee_l": 40}),
               (0.00, {"lean": 16, "chest": 6, "nod": 20, "out_l": 45, "out_r": 45, "arm_l": 15, "arm_r": 15,
                       "elbow_l": 60, "elbow_r": 60, "hip_r": 20, "knee_r": 45, "hip_l": 15, "knee_l": 35}),
               (0.30, N)],
    # A block tackle with the left: low, stretching the left leg across, arms out.
    "tackle": [(-0.30, N),
               (-0.06, {"hip_l": 55, "knee_l": 12, "ankle_l": 15, "hipout_l": 20, "hip_r": 30, "knee_r": 55, "ankle_r": 20,
                        "lean": 18, "turn": -14, "out_l": 45, "out_r": 50, "arm_r": 20, "elbow_l": 30, "elbow_r": 30}),
               (0.15, {"hip_l": 62, "knee_l": 8, "ankle_l": 10, "hipout_l": 22, "hip_r": 32, "knee_r": 60, "ankle_r": 22,
                       "lean": 20, "turn": -16, "out_l": 50, "out_r": 55, "arm_r": 25, "elbow_l": 30, "elbow_r": 30}),
               (0.45, N)],
    # A keeper's set position: weight forward on bent knees, hands out in front at waist height.
    "ready": [(0.0, {"hip_r": 28, "knee_r": 50, "ankle_r": 18, "hip_l": 28, "knee_l": 50, "ankle_l": 18,
                     "hipout_r": 6, "hipout_l": 6, "lean": 18, "chest": 6, "nod": -14, "arm_r": 35, "arm_l": 35,
                     "out_r": 22, "out_l": 22, "elbow_r": 55, "elbow_l": 55}),
              (1.0, "same")],
    # A keeper's dive to his right (to his left: mirrored).  0 = he springs.
    "dive": [(0.00, {"hip_r": 28, "knee_r": 50, "ankle_r": 18, "hip_l": 28, "knee_l": 50, "ankle_l": 18,
                     "lean": 18, "arm_r": 35, "arm_l": 35, "out_r": 22, "out_l": 22, "elbow_r": 55, "elbow_l": 55}),
             (0.12, {"hip_r": 15, "knee_r": 25, "hip_l": 5, "knee_l": 10, "ankle_l": -30, "lean": 5, "side": 10,
                     "out_r": 120, "out_l": 150, "arm_r": 20, "arm_l": 20, "elbow_r": 15, "elbow_l": 15, "nod": -10}),
             (0.32, {"hip_r": 15, "knee_r": 30, "hip_l": 20, "knee_l": 45, "lean": 0, "side": 12,
                     "out_r": 165, "out_l": 170, "arm_r": 10, "arm_l": 10, "elbow_r": 5, "elbow_l": 5, "nod": -15}),
             (0.60, {"hip_r": 10, "knee_r": 35, "hip_l": 30, "knee_l": 60, "lean": 8, "side": 6,
                     "out_r": 150, "out_l": 150, "arm_r": 40, "arm_l": 40, "elbow_r": 30, "elbow_l": 30, "nod": 5})],
    # Getting back up after a dive: onto a knee, then up.
    "recover": [(0.00, {"hip_r": 10, "knee_r": 35, "hip_l": 30, "knee_l": 60, "lean": 8, "side": 6,
                        "out_r": 150, "out_l": 150, "arm_r": 40, "arm_l": 40, "elbow_r": 30, "elbow_l": 30, "nod": 5}),
                (0.40, {"hip_r": 70, "knee_r": 110, "hip_l": 20, "knee_l": 95, "ankle_l": -20, "lean": 30,
                        "out_r": 30, "out_l": 30, "arm_r": 40, "arm_l": 40, "elbow_r": 60, "elbow_l": 60}),
                (0.85, {"hip_r": 30, "knee_r": 45, "hip_l": 15, "knee_l": 30, "lean": 18, "arm_r": 25, "arm_l": 25,
                        "out_r": 15, "out_l": 15, "elbow_r": 40, "elbow_l": 40}),
                (1.20, N)],
    # --- the keeper with the ball (the match engine has him release it straight away, so these run on) ---------
    # A punt: the ball taken in his hands, dropped, and volleyed upfield.
    "punt": [(-0.30, N),
             (-0.06, {"arm_r": 40, "arm_l": 40, "across_r": 28, "across_l": 28, "elbow_r": 75, "elbow_l": 75, "lean": 12,
                      "hip_r": -20, "knee_r": 70, "knee_l": 25}),
             (0.06, {"hip_r": 45, "knee_r": 30, "ankle_r": -30, "knee_l": 20, "arm_r": 45, "arm_l": 30, "out_r": 40,
                     "out_l": 55, "elbow_r": 30, "elbow_l": 30, "lean": -6, "turn": 10}),
             (0.26, {"hip_r": 85, "knee_r": 8, "ankle_r": -25, "knee_l": 15, "arm_r": 30, "arm_l": 20, "out_r": 45,
                     "out_l": 60, "elbow_r": 25, "elbow_l": 25, "lean": -14, "turn": 16, "air": 0.10}),
             (0.50, {"hip_r": 30, "knee_r": 30, "knee_l": 10, "arm_r": 10, "out_r": 20, "out_l": 25, "lean": -4}),
             (0.80, N)],
    # A roll / short throw out: down low, the arm swinging through underneath.
    "bowl": [(-0.30, N),
             (-0.06, {"arm_r": 40, "arm_l": 40, "across_r": 28, "across_l": 28, "elbow_r": 75, "elbow_l": 75, "lean": 12}),
             (0.00, {"arm_r": -45, "out_r": 15, "elbow_r": 10, "arm_l": 40, "out_l": 30, "elbow_l": 30, "lean": 25,
                     "hip_l": 35, "knee_l": 55, "knee_r": 30, "twist": -14, "turn": -8}),
             (0.18, {"arm_r": 60, "out_r": 10, "elbow_r": 10, "arm_l": 20, "out_l": 35, "elbow_l": 30, "lean": 32,
                     "hip_l": 40, "knee_l": 60, "knee_r": 35, "twist": 14, "turn": 6}),
             (0.45, {"arm_r": 40, "elbow_r": 20, "lean": 18, "hip_l": 15, "knee_l": 25, "knee_r": 10}),
             (0.80, N)],
    # A throw-in: ball held in both hands, taken back behind the head, then thrown from over it - both feet on
    # the ground, as the laws say.  (t = the moment it's thrown.)
    "throwin": [(-1.60, {"arm_r": 30, "arm_l": 30, "across_r": 28, "across_l": 28, "elbow_r": 85, "elbow_l": 85}),
                (-0.70, {"arm_r": 30, "arm_l": 30, "across_r": 28, "across_l": 28, "elbow_r": 85, "elbow_l": 85}),
                (-0.25, {"arm_r": 170, "arm_l": 170, "out_r": 22, "out_l": 22, "elbow_r": 110, "elbow_l": 110,
                         "lean": -16, "chest": -8, "nod": -8, "hip_l": 22, "knee_l": 25, "knee_r": 20}),
                (0.00, {"arm_r": 150, "arm_l": 150, "out_r": 16, "out_l": 16, "elbow_r": 15, "elbow_l": 15,
                        "lean": 8, "hip_l": 22, "knee_l": 20, "knee_r": 15}),
                (0.25, {"arm_r": 100, "arm_l": 100, "across_r": 15, "across_l": 15, "elbow_r": 10, "elbow_l": 10,
                        "lean": 18, "hip_l": 20, "knee_l": 18, "knee_r": 12}),
                (0.70, N)],
    # An assistant referee's flag straight up (offside); the referee's arm up for an indirect free kick.
    "flag": [(-0.3, N), (0.0, {"arm_r": 170, "out_r": 8, "elbow_r": 0}), (2.5, {"arm_r": 170, "out_r": 8}),
             (2.9, N)],
    "signal": [(-0.3, N), (0.0, {"arm_r": 172, "out_r": 5, "elbow_r": 0, "nod": -8}),
               (2.5, {"arm_r": 172, "out_r": 5, "nod": -8}), (2.9, N)],
    # In the wall at a free kick: shoulder to shoulder, hands crossed in front of them.
    "wall": [(0.0, {"arm_r": 22, "arm_l": 22, "across_r": 34, "across_l": 34, "elbow_r": 25, "elbow_l": 25,
                    "lean": 4, "nod": -4, "knee_r": 6, "knee_l": 6}), (1.0, "same")],
    # A manager on the touchline, arm out, telling them where to go.
    "point": [(-0.4, N),
              (0.0, {"arm_r": 75, "out_r": 30, "elbow_r": 10, "twist": 12, "lean": 4, "nod": -6}),
              (1.2, {"arm_r": 70, "out_r": 35, "elbow_r": 15, "twist": 10, "lean": 4, "nod": -6}),
              (1.6, N)],
}
# How strongly each blends over the running (a dribbling touch stays light).
WEIGHT = {"touch": 0.55}


# --- moods: other ways of standing, walking and running (goal celebrations) -----------------------------------
def cheer(u):
    """Arms up, punching the air, little hops - the scorer and his team-mates when they get together."""
    c = math.cos(2 * math.pi * u)
    return ({"out_r": 150 + 18 * c, "out_l": 150 - 18 * c, "arm_r": 25, "arm_l": 25, "elbow_r": 35 - 25 * c,
             "elbow_l": 35 + 25 * c, "lean": -10, "chest": -6, "nod": -18, "knee_r": 12, "knee_l": 12},
            {"air": 0.07 * abs(math.sin(2 * math.pi * u))})


def clap(u):
    """Applauding the fans (two claps a second)."""
    c = math.cos(4 * math.pi * u)
    return ({"arm_r": 45, "arm_l": 45, "across_r": 27 + 10 * c, "across_l": 27 + 10 * c, "elbow_r": 70,
             "elbow_l": 70, "nod": -8}, {})


def hips(u):
    """Hands on hips, head down (the other side, after a goal)."""
    b = math.sin(2 * math.pi * u)
    return ({"out_r": 38, "out_l": 38, "arm_r": -18, "arm_l": -18, "elbow_r": 105, "elbow_l": 105, "nod": 22,
             "lean": 4 + 2 * b, "knee_r": 4, "knee_l": 4}, {})


def knees(u):
    """Bent over, hands on knees."""
    b = math.sin(2 * math.pi * u)
    return ({"hip_r": 35, "hip_l": 35, "knee_r": 28, "knee_l": 28, "ankle_r": 8, "ankle_l": 8, "lean": 45 + 3 * b,
             "chest": 8, "arm_r": 55, "arm_l": 55, "out_r": 12, "out_l": 12, "elbow_r": 15, "elbow_l": 15,
             "nod": -5}, {})


def walk_sad(u):
    m, extra = walk_pose(u)
    for k in ("arm_r", "arm_l", "elbow_r", "elbow_l", "twist"):
        m[k] *= 0.4
    m.update(nod=26, lean=8, chest=6)
    return m, extra


def run_arms(u):
    """Running away with his arms out wide - the scorer's celebration."""
    return ({"out_r": 80, "out_l": 80, "arm_r": -10, "arm_l": -10, "elbow_r": -20, "elbow_l": -20, "nod": -12,
             "lean": -6}, {})


def sit(u):
    """Sitting on the bench (a substitute)."""
    b = math.sin(2 * math.pi * u)
    return ({"hip_r": 88, "hip_l": 84, "knee_r": 92, "knee_l": 86, "ankle_r": 5, "lean": 6 + 2 * b, "arm_r": 30,
             "arm_l": 30, "elbow_r": 40, "elbow_l": 40, "across_r": 10, "across_l": 10, "nod": -4}, {})


LOOPS = {"sit": (sit, 90, "idle"), "cheer": (cheer, 30, "idle"), "clap": (clap, 30, "idle"), "hips": (hips, 60, "idle"), "knees": (knees, 60, "idle"),
         "walk_sad": (walk_sad, 30, "idle"), "run_arms": (run_arms, 15, "run")}


def action_pose(keys):
    """A pose function over time for a key-posed action."""
    keys = [(t, (keys[i - 1][1] if p == "same" else p)) for i, (t, p) in enumerate(keys)]

    def at(t):
        if t <= keys[0][0]:
            return dict(keys[0][1]), {}
        for (t0, a), (t1, b) in zip(keys, keys[1:]):
            if t <= t1:
                k = (t - t0) / max(1e-6, t1 - t0)
                k = k * k * (3 - 2 * k)
                return {m: a.get(m, 0) + (b.get(m, 0) - a.get(m, 0)) * k for m in set(a) | set(b)}, {}
        return dict(keys[-1][1]), {}
    return at, keys[0][0], keys[-1][0]


def mirror(pose):
    """The same pose done to the other side (a dive to his left, a kick with the left foot)."""
    out = {}
    for m, v in pose.items():
        if m.endswith("_r"):
            out[m[:-2] + "_l"] = v
        elif m.endswith("_l"):
            out[m[:-2] + "_r"] = v
        elif m in ("turn", "twist", "tilt", "side"):
            out[m] = -v
        else:
            out[m] = v
    return out


# --- building an animation --------------------------------------------------------------------------------
def _local_mats(bundle, frame):
    mats, parent, order = {}, {}, []

    def walk(g, par):
        for i in range(g.getNumChildren()):
            ch = g.getChild(i)
            if isinstance(ch, AnimChannelMatrixXfmTable):
                m = LMatrix4f()
                ch.getValue(frame % max(1, bundle.getNumFrames()), m)
                mats[ch.getName()] = (ch, m)
                parent[ch.getName()] = par
                order.append(ch.getName())
                walk(ch, ch.getName())
            else:
                walk(ch, par)
    walk(bundle, None)
    return mats, parent, order


FEET = ("foot.r", "foot.l", "ball.r", "ball.l")


def build(actor, name, pose_fn, frames, ground=True, base_anim="idle", base_frame=0):
    """A new animation: each frame, the base pose (a frame of the base animation - base_frame can be a function
    of the time 0..1, to follow a moving base such as the run) with pose_fn(i / frames) (-> ({move: degrees},
    {"sway": m, "air": m})) turned on top, grounded.  Returns a NodePath holding it."""
    base = actor.getAnimControl(base_anim).getAnim()
    idle = actor.getAnimControl("idle").getAnim()
    _, parent, order = _local_mats(base, 0)

    def pose_at(bundle, fr):
        mats, _, _ = _local_mats(bundle, fr)
        return {j: TransformState.makeMat(mats[j][1]) for j in order}

    def nets(local):
        nm = {}
        for j in order:
            m = local[j].getMat()
            nm[j] = m * nm[parent[j]] if parent[j] else m
        return nm
    # Points under each foot: the heel (a little behind the ankle, at the sole) and the ball of the foot.
    nm0 = nets(pose_at(idle, 0))
    soles = []
    for sd in ("r", "l"):
        a = nm0["foot." + sd].xformPoint(LPoint3f(0, 0, 0))
        b = nm0["ball." + sd].xformPoint(LPoint3f(0, 0, 0))
        heel = LPoint3f(a[0], a[1] + 0.045, b[2])
        inv = LMatrix4f(nm0["foot." + sd]); inv.invertInPlace()
        soles.append(("foot." + sd, inv.xformPoint(heel)))
        soles.append(("ball." + sd, LPoint3f(0, 0, 0)))

    def feet_z(local):
        """The lowest point of the soles, in the model, for these local transforms."""
        nm = nets(local)
        return min(nm[j].xformPoint(pt)[2] for j, pt in soles)
    rest = feet_z(pose_at(idle, 0))
    tables = {j: {k: [] for k in "hprxyz"} for j in order}
    fixed = None if callable(base_frame) else pose_at(base, base_frame)
    for f in range(frames):
        u = f / float(frames)
        base_ts = fixed or pose_at(base, int(round(base_frame(u))))
        net = {}

        def net_q(j):
            if j is None:
                return LQuaternionf.identQuat()
            if j not in net:
                net[j] = base_ts[j].getQuat() * net_q(parent[j])
            return net[j]
        moves, extra = pose_fn(u)
        turns = {}
        for m, deg in moves.items():
            if m in MOVES and deg:
                j, ax, sign = MOVES[m]
                turns.setdefault(j, []).append((ax, deg * sign))
        local = {}
        for j in order:
            ts = base_ts[j]
            q = ts.getQuat()
            for ax, deg in turns.get(j, ()):
                r = LQuaternionf()
                r.setFromAxisAngle(deg, AXES[ax])
                pq = net_q(parent[j])
                q = q * (pq * r * pq.conjugate())
            local[j] = TransformState.makePosQuatScale(ts.getPos(), q, ts.getScale())
        shift = LVecBase3f(extra.get("sway", 0.0), 0, 0)
        if ground:
            shift[2] = rest - feet_z(local) + extra.get("air", 0.0)
        local["pelvis"] = local["pelvis"].setPos(local["pelvis"].getPos() + shift)
        for j in order:
            t = tables[j]
            for k, v in zip("hpr", local[j].getHpr()):
                t[k].append(v)
            for k, v in zip("xyz", local[j].getPos()):
                t[k].append(v)
    base_frame = 0 if callable(base_frame) else base_frame
    nb = AnimBundle(name, FPS, frames)

    def copy(src, dst):
        for i in range(src.getNumChildren()):
            ch = src.getChild(i)
            if isinstance(ch, AnimChannelMatrixXfmTable):
                n = AnimChannelMatrixXfmTable(dst, ch.getName())
                for k in "ijkabc":                                       # (scale / shear: as in the base frame)
                    tb = ch.getTable(k)
                    if len(tb):
                        n.setTable(k, _pta([tb[base_frame % len(tb)]]))
                for k in "hprxyz":
                    vals = tables[ch.getName()][k]
                    n.setTable(k, _pta(vals if max(vals) - min(vals) > 1e-5 else vals[:1]))
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
SPANS = {}          # action -> (first second, last second)


def _make(actor):
    _CACHE["walk"] = build(actor, "walk", walk_pose, 30)
    for name, (fn, n, base) in LOOPS.items():
        if base == "run":                                               # (on top of the run: its stride, frames 2-17)
            _CACHE[name] = build(actor, name, fn, n, ground=False, base_anim="run", base_frame=lambda u: 2 + u * 15)
        else:
            _CACHE[name] = build(actor, name, fn, n)
    for name, keys in ACTIONS.items():
        variants = [(name, keys)]
        if name in ("dive", "recover", "kick", "shot", "touch", "tackle", "punt"):
            variants.append((name + "_m", [(t, mirror(p) if isinstance(p, dict) else p) for t, p in keys]))
        for vn, vk in variants:
            fn, t0, t1 = action_pose(vk)
            n = max(2, int(round((t1 - t0) * FPS)) + 1)
            _CACHE[vn] = build(actor, vn, lambda u, fn=fn, t0=t0, t1=t1, n=n: fn(t0 + u * n / FPS), n)
            SPANS[vn] = (t0, t1)


def add_all(actor):
    """Give this actor (the mannequin) the walk and every action (built once, shared by every player)."""
    if not _CACHE:
        _make(actor)
    actor.loadAnims(dict(_CACHE))
    return list(_CACHE)
