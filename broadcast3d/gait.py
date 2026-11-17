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
    "wristy_r": ("hand.r", "y", 1), "wristy_l": ("hand.l", "y", -1),
    "wristz_r": ("hand.r", "z", 1), "wristz_l": ("hand.l", "z", -1),
    "turn": ("pelvis", "z", 1), "tilt": ("pelvis", "y", 1), "pitch": ("pelvis", "x", 1),
    "lean": ("spine_01", "x", 1), "chest": ("spine_02", "x", 1), "twist": ("spine_01", "z", 1),
    "side": ("spine_01", "y", 1),
    "nod": ("neck_01", "x", 1), "head": ("head", "x", 1),
    "toein_r": ("thigh.r", "z", 1), "toein_l": ("thigh.l", "z", -1),
}
AXES = {"x": Vec3(1, 0, 0), "y": Vec3(0, 1, 0), "z": Vec3(0, 0, 1)}
# The order the turns are made in at each joint: forward / back first, then across the body, then out.
ORDER = sorted(MOVES, key=lambda m: (m.startswith("out_"), m.startswith("across_")) and
               (2 if m.startswith("out_") else 1))


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


WALK_SWEEP = 0.26          # (measured: with this the foot on the ground stays put sideways too)


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
    m["toein_r"], m["toein_l"] = -4 * c, 4 * c                    # (...the legs turning back under it: feet stay put)
    m["twist"] = -7 * c                                           # (the shoulders turn against it)
    m["tilt"] = 2 * s
    m["hipout_r"], m["hipout_l"] = -2 * s, 2 * s                  # (the hips dip side to side, the legs don't swing)
    for sd in ("r", "l"):                                         # (the stand's hips are turned a little: the legs
        m["hipout_" + sd] += WALK_SWEEP * (m["hip_" + sd] - 8)    #  swung straight back, not out to the side)
    return m, {"sway": -0.008 * s}                                # (over the right foot in the first half)


# --- the run: our own, from running studies, with the foot on the ground planted ------------------------------
# One cycle = two steps, right foot down at phase 0, left at 0.5.  While a foot is down (the "stance", ~38% of the
# cycle jogging, ~30% running, ~24% sprinting) it stays put on the grass: the hip and knee angles that keep it
# there are worked out from the leg's lengths as the body passes over it (the leg's own geometry, two bones);
# the hips dip a little mid-stance (the knee bending ~35-45 deg to take the landing).  In the air the leg
# swings through: the heel tucks up (knee ~95 deg jogging, ~125 sprinting), the thigh drives forward (~45-65
# deg) and reaches out again for the next landing.  Arms swing against the legs, elbows ~80-90 deg.  Figures:
# Novacheck 1998 (Gait & Posture 7, "The biomechanics of running"); Mann & Hagy 1980; Weyand et al. 2000
# (sprinting: contact ~0.1 s, ~4.5 steps a second); cadence ~2.7 steps/s jogging at 3 m/s, ~3.2 at 5.5 m/s.
# (name: speed m/s, steps a second, stance share, thigh's drive, heel tuck, forward lean, arm swing)
RUNS = {"jog": (3.0, 2.7, 0.38, 42, 95, 9, 20), "run2": (5.5, 3.2, 0.30, 55, 112, 12, 32),
        "sprint": (8.0, 4.4, 0.24, 66, 126, 16, 46)}
LEGS = {"thigh": 0.45, "shin": 0.45, "hip_h": 0.90}     # (set from the skeleton when the runs are built)
RUN_REACH = {"run2": 1.14, "sprint": 1.16}    # (the two-bone sum is a little short at the faster runs: measured)
RUN_SWEEP = 0.5                               # (measured: the planted foot stays put sideways - see WALK_SWEEP)


def _curve(keys, t):
    """A smooth curve through (t, value) keys, t 0..1 (not wrapping)."""
    t = max(keys[0][0], min(keys[-1][0], t))
    for i in range(len(keys) - 1):
        t0, v0 = keys[i]
        t1, v1 = keys[i + 1]
        if t <= t1:
            vm = keys[i - 1][1] if i > 0 else v0 - (v1 - v0)
            vp = keys[i + 2][1] if i + 2 < len(keys) else v1 + (v1 - v0)
            m0, m1 = (v1 - vm) / 2.0, (vp - v0) / 2.0
            u = (t - t0) / max(t1 - t0, 1e-6)
            u2, u3 = u * u, u * u * u
            return (2 * u3 - 3 * u2 + 1) * v0 + (u3 - 2 * u2 + u) * m0 + (-2 * u3 + 3 * u2) * v1 + (u3 - u2) * m1
    return keys[-1][1]


def _leg_ik(x, h):
    """Hip and knee angles (degrees: hip + = thigh forward, knee + = bent) putting the ankle x ahead of the hip
    and h below it."""
    L1, L2 = LEGS["thigh"], LEGS["shin"]
    D = min(L1 + L2 - 1e-4, math.hypot(x, h))
    knee = math.pi - math.acos(max(-1.0, min(1.0, (L1 * L1 + L2 * L2 - D * D) / (2 * L1 * L2))))
    hip = math.atan2(x, h) + math.acos(max(-1.0, min(1.0, (L1 * L1 + D * D - L2 * L2) / (2 * L1 * D))))
    return math.degrees(hip), math.degrees(knee)


def run_cycle(name):
    """(the pose function for this run, the metres one cycle covers, the stance share)."""
    v, steps, beta, drive, tuck, lean, arms = RUNS[name]
    T = 2.0 / steps                         # (seconds a cycle)
    C = v * T                               # (metres a cycle)
    d = C * beta / 2.0 * RUN_REACH.get(name, 1.0)   # (the foot: from d ahead of the hip to d behind, while down)
    H = LEGS["hip_h"]
    sink = 0.035 + 0.01 * (v - 3.0) / 5.0   # (the hips dip mid-stance)
    flight = max(0.0, 0.5 - beta) * T       # (seconds in the air each step)
    rise = 9.81 * flight * flight / 8.0     # (how high he goes: up and down in that time)

    def stance(t):                          # (t 0..1 through the stance)
        x = d - 2 * d * t
        h = H - sink * math.sin(math.pi * t) - 0.02 * (1 - t)       # (a little bent at landing too)
        return _leg_ik(x, h)

    hip_c, knee_c = stance(0.0)
    hip_o, knee_o = stance(1.0)

    def leg(ph):
        ph %= 1.0
        if ph < beta:
            t = ph / beta
            hip, knee = stance(t)
            ankle = _curve([(0, 4), (0.45, 18), (1.0, -22)], t)
            return hip, knee, ankle, 0.0
        s_ = (ph - beta) / (1 - beta)
        hip = _curve([(0, hip_o), (0.35, (hip_o + drive) / 2 + 4), (0.72, drive), (1.0, hip_c)], s_)
        knee = _curve([(0, knee_o), (0.38, tuck), (0.75, 40), (1.0, knee_c)], s_)
        ankle = _curve([(0, -22), (0.4, 8), (0.8, 4), (1.0, 4)], s_)
        return hip, knee, ankle, s_

    def pose(u):
        m = {}
        for sd, off in (("r", 0.0), ("l", 0.5)):
            hip, knee, ankle, _ = leg(u + off)
            m["hip_" + sd], m["knee_" + sd], m["ankle_" + sd] = hip, knee, ankle
        c = math.cos(2 * math.pi * u)
        m["arm_r"], m["arm_l"] = -arms * c - 2, arms * c - 2          # (each arm with the other leg)
        m["elbow_r"], m["elbow_l"] = 82 - 12 * c, 82 + 12 * c
        m["out_r"] = m["out_l"] = 10
        m["across_r"] = m["across_l"] = 6
        m["turn"] = 6 * c                                             # (hips turn with the legs...)
        m["toein_r"], m["toein_l"] = -6 * c, 6 * c                    # (...the legs turning back under them)
        for sd in ("r", "l"):                                         # (legs swung straight back - see WALK_SWEEP)
            m["hipout_" + sd] = RUN_SWEEP * (m["hip_" + sd] - 8)
        m["twist"] = -10 * c                                          # (shoulders against them)
        m["lean"] = lean
        m["nod"] = -lean * 0.6                                        # (head up, eyes on the game)
        # in the air between steps: the body up and down (ballistic)
        ph = u % 0.5
        air = 0.0
        if ph >= beta and flight > 0:
            s_ = (ph - beta) / (0.5 - beta)
            air = 4 * rise * s_ * (1 - s_)
        return m, {"air": air}
    return pose, C, beta


# --- actions: key poses at seconds from the moment (the ball struck, the dive's start...) ---------------------------
# "air": metres he is off the ground (no grounding then).  "hold": the pose stays put (a held stance).
N = {}
ACTIONS = {
    # A pass / clearance with the right instep.
    "kick": [(-0.32, N),
             # the last stride: the left (standing) foot reaching out to plant beside the ball, the right leg
             # drawing back (Lees & Nolan 1998, "The biomechanics of soccer": a long last stride, the plant foot
             # ~0.3 m beside and level with the ball, the knee ~25-40 deg bent at contact, the trunk leaning away
             # from the kicking side, the arm on the standing side out wide)
             (-0.20, {"hip_l": 32, "knee_l": 12, "ankle_l": 10, "hip_r": -18, "knee_r": 70, "ankle_r": -20,
                      "turn": -10, "lean": 4, "tilt": -2, "out_l": 40, "arm_l": 15, "elbow_l": 30, "out_r": 20,
                      "arm_r": -15, "elbow_r": 25}),
             (-0.10, {"hip_r": -30, "knee_r": 100, "ankle_r": -25, "hip_l": 14, "knee_l": 34, "turn": -18,
                      "twist": -8, "lean": 5, "tilt": -4, "side": -3, "out_l": 60, "arm_l": 15, "elbow_l": 30,
                      "out_r": 25, "arm_r": -25, "elbow_r": 25}),
             (0.00, {"hip_r": 24, "knee_r": 32, "ankle_r": -32, "hip_l": 10, "knee_l": 36, "turn": 10, "twist": 8,
                     "lean": 4, "tilt": -5, "side": -4, "out_l": 52, "arm_l": 12, "elbow_l": 25, "out_r": 30,
                     "arm_r": -25, "elbow_r": 20}),
             (0.14, {"hip_r": 55, "knee_r": 10, "ankle_r": -25, "hip_l": 5, "knee_l": 25, "turn": 18, "twist": 10,
                     "lean": -2, "tilt": -2, "out_l": 45, "arm_l": 20, "elbow_l": 30, "out_r": 25, "arm_r": -10,
                     "elbow_r": 25}),
             (0.40, N)],
    # A shot: a longer backswing and a bigger follow-through, over the ball to keep it down, landing on the
    # kicking foot after it (as players do when they strike it hard).
    "shot": [(-0.36, N),
             (-0.24, {"hip_l": 36, "knee_l": 10, "ankle_l": 10, "hip_r": -20, "knee_r": 75, "ankle_r": -20,
                      "turn": -14, "lean": 8, "tilt": -2, "out_l": 45, "arm_l": 20, "elbow_l": 30, "out_r": 25,
                      "arm_r": -20, "elbow_r": 25}),
             (-0.12, {"hip_r": -38, "knee_r": 115, "ankle_r": -28, "hip_l": 16, "knee_l": 36, "turn": -26,
                      "twist": -12, "lean": 10, "tilt": -5, "side": -4, "out_l": 52, "arm_l": 25, "elbow_l": 30,
                      "out_r": 35, "arm_r": -35, "elbow_r": 30}),
             (0.00, {"hip_r": 30, "knee_r": 36, "ankle_r": -35, "hip_l": 12, "knee_l": 38, "turn": 12, "twist": 10,
                     "lean": 14, "chest": 4, "tilt": -6, "side": -4, "out_l": 55, "arm_l": 10, "elbow_l": 25,
                     "out_r": 40, "arm_r": -30, "elbow_r": 20}),
             (0.16, {"hip_r": 78, "knee_r": 12, "ankle_r": -25, "hip_l": 5, "knee_l": 25, "turn": 28, "twist": 14,
                     "lean": 6, "tilt": -3, "out_l": 50, "arm_l": 25, "elbow_l": 35, "out_r": 30, "arm_r": -10,
                     "elbow_r": 30}),
             (0.32, {"hip_r": 30, "knee_r": 34, "ankle_r": -5, "hip_l": -10, "knee_l": 30, "turn": 12, "twist": 6,
                     "lean": 6, "out_l": 30, "arm_l": 15, "elbow_l": 30, "out_r": 20, "elbow_r": 30}),
             (0.50, N)],
    # A short pass with the inside of the right foot: the foot turned out ~40-50 deg so the flat inside of it
    # meets the ball, a shorter backswing than the instep kick and a smooth push through (Levanon & Dapena
    # 1998, "Comparison of the kinematics of the full-instep and pass kicks in soccer", Med Sci Sports Exerc
    # 30(6): the pass kick is slower, with the thigh turned out and a smaller knee swing).
    "pass": [(-0.26, N),
             (-0.14, {"hip_l": 24, "knee_l": 14, "ankle_l": 8, "hip_r": -12, "knee_r": 50, "ankle_r": -5,
                      "toein_r": -30, "turn": -6, "lean": 3, "out_l": 30, "arm_l": 10, "elbow_l": 30, "out_r": 15,
                      "elbow_r": 25}),
             (0.00, {"hip_r": 20, "knee_r": 16, "ankle_r": 2, "toein_r": -45, "hipout_r": 10, "hip_l": 8,
                     "knee_l": 30, "turn": 8, "twist": 4, "lean": 5, "nod": 12, "out_l": 35, "arm_l": 10,
                     "elbow_l": 30, "out_r": 18, "arm_r": -10, "elbow_r": 25}),
             (0.12, {"hip_r": 30, "knee_r": 12, "toein_r": -30, "hipout_r": 6, "hip_l": 5, "knee_l": 24,
                     "turn": 12, "twist": 5, "lean": 3, "nod": 8, "out_l": 28, "elbow_l": 30, "out_r": 15}),
             (0.32, N)],
    # A lofted pass / chip: the instep kick, but leaning back with the foot under the ball, and a high finish.
    "loft": [(-0.32, N),
             (-0.20, {"hip_l": 30, "knee_l": 14, "ankle_l": 10, "hip_r": -18, "knee_r": 70, "ankle_r": -20,
                      "turn": -10, "lean": 0, "out_l": 40, "arm_l": 15, "elbow_l": 30, "out_r": 20, "arm_r": -15}),
             (-0.10, {"hip_r": -28, "knee_r": 100, "ankle_r": -20, "hip_l": 16, "knee_l": 30, "turn": -18,
                      "twist": -8, "lean": -4, "tilt": -4, "out_l": 60, "arm_l": 15, "elbow_l": 30, "out_r": 30,
                      "arm_r": -20}),
             (0.00, {"hip_r": 30, "knee_r": 30, "ankle_r": -15, "hip_l": 12, "knee_l": 34, "turn": 10, "twist": 8,
                     "lean": -10, "chest": -4, "tilt": -5, "out_l": 60, "arm_l": 20, "elbow_l": 25, "out_r": 40,
                     "arm_r": -20}),
             (0.18, {"hip_r": 80, "knee_r": 8, "ankle_r": -20, "hip_l": 4, "knee_l": 26, "turn": 16, "twist": 10,
                     "lean": -12, "chest": -4, "out_l": 55, "arm_l": 25, "elbow_l": 30, "out_r": 35}),
             (0.44, N)],
    # The outside of the right foot: a flick out to his right (and back), the toes turned in, the leg swinging
    # across and then out.
    "flick": [(-0.22, N),
              (-0.10, {"hip_r": 12, "knee_r": 45, "toein_r": 25, "hipout_r": -14, "hip_l": 15, "knee_l": 25,
                       "ankle_l": 6, "out_l": 30, "elbow_l": 30, "tilt": -2}),
              (0.00, {"hip_r": 16, "knee_r": 22, "toein_r": 35, "hipout_r": 20, "ankle_r": -20, "hip_l": 10,
                      "knee_l": 30, "tilt": 4, "twist": -6, "out_l": 38, "elbow_l": 30, "out_r": 12, "nod": 10}),
              (0.12, {"hip_r": 10, "knee_r": 18, "toein_r": 25, "hipout_r": 26, "hip_l": 8, "knee_l": 26,
                      "tilt": 5, "out_l": 32, "elbow_l": 30}),
              (0.30, N)],
    # A back-heel: the right foot lifted forward over the ball, then the heel brought back into it, leaning
    # over it a little, the arms out.
    "backheel": [(-0.26, N),
                 (-0.12, {"hip_r": 30, "knee_r": 55, "ankle_r": 8, "hip_l": 8, "knee_l": 24, "lean": 6, "nod": 12,
                          "out_l": 25, "out_r": 15, "elbow_l": 30, "elbow_r": 30}),
                 (0.00, {"hip_r": -22, "knee_r": 38, "ankle_r": 15, "hip_l": 10, "knee_l": 30, "lean": 10, "nod": 18,
                         "out_l": 30, "out_r": 22, "elbow_l": 30, "elbow_r": 30}),
                 (0.14, {"hip_r": -30, "knee_r": 62, "ankle_r": 5, "hip_l": 8, "knee_l": 28, "lean": 8, "nod": 10,
                         "out_l": 25, "out_r": 18}),
                 (0.36, N)],
    # A touch while dribbling: a little push with the right foot (blended lightly over the running).
    "touch": [(-0.16, N),
              (-0.06, {"hip_r": -8, "knee_r": 45, "ankle_r": -10, "knee_l": 15}),
              (0.00, {"hip_r": 22, "knee_r": 20, "ankle_r": -15, "knee_l": 15, "out_l": 15}),
              (0.16, N)],
    # A header: a quick crouch and spring off both feet, the arms swung up and out (for height, and to hold
    # his space), back arched and the legs tucked behind in the air, then the trunk and neck snap forward
    # through the ball, and he lands on bent knees.  (Jump ~0.4 m for a contested header - e.g. Bobbert & van
    # Ingen Schenau on countermovement jumps; the forehead strike from the arched back.)
    "header": [(-0.40, N),
               (-0.28, {"hip_r": 40, "knee_r": 70, "ankle_r": 25, "hip_l": 40, "knee_l": 70, "ankle_l": 25,
                        "lean": 14, "out_l": 15, "out_r": 15, "arm_l": -35, "arm_r": -35, "elbow_l": 30,
                        "elbow_r": 30}),
               (-0.10, {"lean": -14, "chest": -8, "nod": -16, "out_l": 60, "out_r": 60, "arm_l": 45, "arm_r": 45,
                        "elbow_l": 75, "elbow_r": 75, "hip_r": -6, "knee_r": 75, "hip_l": 6, "knee_l": 60,
                        "ankle_r": -25, "ankle_l": -25}),
               (0.00, {"lean": 18, "chest": 8, "nod": 22, "out_l": 45, "out_r": 45, "arm_l": 15, "arm_r": 15,
                       "elbow_l": 60, "elbow_r": 60, "hip_r": 25, "knee_r": 45, "hip_l": 20, "knee_l": 40,
                       "ankle_r": -15, "ankle_l": -15}),
               (0.30, {"hip_r": 35, "knee_r": 55, "ankle_r": 20, "hip_l": 30, "knee_l": 50, "ankle_l": 18,
                       "lean": 12, "out_l": 30, "out_r": 30, "arm_l": 10, "arm_r": 10, "elbow_l": 40, "elbow_r": 40}),
               (0.50, N)],
    # A block tackle with the left: low, stretching the left leg across, arms out.
    "tackle": [(-0.30, N),
               (-0.06, {"hip_l": 55, "knee_l": 12, "ankle_l": 15, "hipout_l": 20, "hip_r": 30, "knee_r": 55, "ankle_r": 20,
                        "lean": 18, "turn": -14, "out_l": 45, "out_r": 50, "arm_r": 20, "elbow_l": 30, "elbow_r": 30}),
               (0.15, {"hip_l": 62, "knee_l": 8, "ankle_l": 10, "hipout_l": 22, "hip_r": 32, "knee_r": 60, "ankle_r": 22,
                       "lean": 20, "turn": -16, "out_l": 50, "out_r": 55, "arm_r": 25, "elbow_l": 30, "elbow_r": 30}),
               (0.45, N)],
    # A slide tackle (left leg): down on his right hip and thigh, the left leg out straight along the ground,
    # the right tucked under, trunk leaning back, the right arm back to the grass, the left out for balance;
    # then up again.  (The "abs" arms: set, not shifted.)
    "slide": [(-0.30, N),
              (-0.08, {"hip_l": 50, "knee_l": 25, "ankle_l": 5, "hip_r": 40, "knee_r": 70, "ankle_r": 10,
                       "pitch": -15, "lean": 6, "tilt": -6, "out_r": 40, "arm_r": -20, "elbow_r": 20,
                       "out_l": 50, "arm_l": 20, "elbow_l": 30}),
              (0.10, {"hip_l": 42, "knee_l": 4, "ankle_l": 8, "hip_r": 28, "knee_r": 140, "ankle_r": 20,
                      "hipout_r": 10, "pitch": -48, "lean": 22, "tilt": -14, "nod": 10, "out_r": 45, "arm_r": -35,
                      "elbow_r": 10, "out_l": 55, "arm_l": 30, "elbow_l": 30}),
              (0.45, {"hip_l": 40, "knee_l": 8, "ankle_l": 8, "hip_r": 28, "knee_r": 140, "ankle_r": 20,
                      "hipout_r": 10, "pitch": -45, "lean": 24, "tilt": -14, "nod": 10, "out_r": 45, "arm_r": -35,
                      "elbow_r": 15, "out_l": 45, "arm_l": 20, "elbow_l": 35}),
              (0.80, {"hip_l": 60, "knee_l": 100, "hip_r": 40, "knee_r": 120, "ankle_r": 20, "pitch": -10,
                      "lean": 30, "out_r": 30, "arm_r": 10, "elbow_r": 40, "out_l": 30, "arm_l": 15, "elbow_l": 40}),
              (1.10, N)],
    # Shielding the ball: side-on, low, knees bent, backside out towards the man, the left arm out and back
    # to hold him off (the man on his left; mirrored for the right), eyes down on the ball.
    "shield": [(0.0, {"hip_r": 30, "knee_r": 45, "ankle_r": 14, "hip_l": 22, "knee_l": 40, "ankle_l": 12,
                      "hipout_r": 8, "hipout_l": 10, "lean": 22, "side": 6, "turn": 18, "twist": 10, "nod": 18,
                      "out_l": 70, "arm_l": -20, "elbow_l": 25, "out_r": 25, "arm_r": 15, "elbow_r": 40}),
               (1.0, "same")],
    # Fouled: his legs taken, he stumbles, reaches out and goes down - onto his hands and chest - lies there a
    # moment, then pushes up onto a knee and gets up.  About 0.7 s from losing his balance to hitting the ground,
    # as people falling from standing take (Hsiao & Robinovitch 1998, quoted in Frontiers in Neurology 2018,
    # doi 10.3389/fneur.2018.00986: "the pre-impact phase of a fall lasts some 700 ms").
    "fouled": [(-0.10, N),
               (0.22, {"hip_r": -20, "knee_r": 50, "hip_l": 35, "knee_l": 20, "lean": 30, "pitch": 15,
                       "arm_l": 70, "arm_r": 60, "out_l": 30, "out_r": 30, "elbow_l": 20, "elbow_r": 20, "nod": -20}),
               (0.48, {"hip_r": -5, "knee_r": 35, "hip_l": 20, "knee_l": 30, "lean": 18, "pitch": 48, "nod": -35,
                       "arm_l": 85, "arm_r": 80, "out_l": 35, "out_r": 35, "elbow_l": 15, "elbow_r": 15}),
               (0.70, {"hip_r": 0, "knee_r": 20, "hip_l": 5, "knee_l": 25, "pitch": 78, "lean": 5, "nod": -45,
                       "arm_l": 80, "arm_r": 80, "out_l": 40, "out_r": 40, "elbow_l": 70, "elbow_r": 70}),
               (1.60, {"hip_r": 0, "knee_r": 30, "hip_l": 10, "knee_l": 35, "pitch": 82, "lean": 0, "nod": -40,
                       "arm_l": 60, "arm_r": 90, "out_l": 50, "out_r": 35, "elbow_l": 90, "elbow_r": 60}),
               (2.20, {"hip_r": 80, "knee_r": 100, "hip_l": 10, "knee_l": 90, "pitch": 35, "lean": 20, "nod": -10,
                       "arm_l": 40, "arm_r": 40, "out_l": 20, "out_r": 20, "elbow_l": 30, "elbow_r": 30}),
               (2.90, N)],
    # Hurt in the challenge: his standing leg goes, he drops back onto the grass and lies there on his back,
    # holding his right shin with the knee pulled up - then sits up, gets to a crouch and up, gingerly.
    "hurt": [(-0.10, N),
             (0.25, {"hip_r": 40, "knee_r": 70, "hip_l": 20, "knee_l": 60, "lean": 10, "pitch": -20, "nod": 10,
                     "arm_l": 40, "arm_r": 30, "out_l": 50, "out_r": 50, "elbow_l": 30, "elbow_r": 30}),
             (0.55, {"hip_r": 70, "knee_r": 100, "hip_l": 40, "knee_l": 60, "lean": 20, "pitch": -50, "nod": 20,
                     "arm_l": 45, "arm_r": 40, "out_l": 40, "out_r": 40, "elbow_l": 50, "elbow_r": 50}),
             (0.85, {"hip_r": 75, "knee_r": 120, "hip_l": 20, "knee_l": 40, "pitch": -72, "lean": 25, "tilt": 20,
                     "nod": 25, "arm_r": 55, "arm_l": 60, "out_r": 10, "out_l": 15, "elbow_r": 70, "elbow_l": 75,
                     "across_r": 20, "across_l": 25}),
             (3.40, {"hip_r": 85, "knee_r": 125, "hip_l": 25, "knee_l": 45, "pitch": -70, "lean": 30, "tilt": 15,
                     "nod": 30, "arm_r": 60, "arm_l": 62, "out_r": 10, "out_l": 15, "elbow_r": 75, "elbow_l": 75,
                     "across_r": 20, "across_l": 25}),
             (4.10, {"hip_r": 90, "knee_r": 95, "hip_l": 90, "knee_l": 95, "pitch": -35, "lean": 30, "nod": 10,
                     "arm_r": 40, "arm_l": 40, "out_r": 25, "out_l": 25, "elbow_r": 30, "elbow_l": 30}),
             (4.60, {"hip_r": 80, "knee_r": 110, "hip_l": 70, "knee_l": 110, "pitch": 10, "lean": 35, "nod": -5,
                     "arm_r": 30, "arm_l": 30, "out_r": 20, "out_l": 20, "elbow_r": 30, "elbow_l": 30}),
             (5.30, N)],
    # Losing the ball in a tackle: knocked off his stride - a lurch forward, arms flung out, a stumbling step
    # to stay up, then on his way.
    "stumble": [(-0.05, N),
                (0.12, {"lean": 22, "pitch": 6, "hip_r": -12, "knee_r": 35, "hip_l": 32, "knee_l": 45, "out_r": 55,
                        "out_l": 60, "arm_r": 25, "arm_l": -10, "elbow_r": 30, "elbow_l": 30, "nod": -12}),
                (0.36, {"lean": 12, "hip_l": 40, "knee_l": 50, "hip_r": 4, "knee_r": 25, "out_r": 42, "out_l": 45,
                        "arm_r": 10, "elbow_r": 30, "elbow_l": 30, "nod": -6}),
                (0.70, N)],
    # The man who gave the foul away: "I got the ball!" - both hands up, palms out, then a shrug.
    "innocent": [(-0.10, N),
                 (0.35, {"arm_r": 70, "arm_l": 70, "out_r": 35, "out_l": 35, "elbow_r": 70, "elbow_l": 70,
                         "lean": -4, "nod": -8}),
                 (1.20, {"arm_r": 65, "arm_l": 65, "out_r": 38, "out_l": 38, "elbow_r": 65, "elbow_l": 65,
                         "lean": -4, "nod": -4}),
                 (1.60, {"arm_r": 20, "arm_l": 20, "out_r": 50, "out_l": 50, "elbow_r": 40, "elbow_l": 40, "lean": 0,
                         "nod": 6}),
                 (2.20, N)],
    # A sharp cut to his left at speed: the right (outside) foot planted wide, knee bent to take the load, body
    # leaning into the new direction and low, then the push-off (e.g. Besier et al. 2001 on sidestep cutting:
    # the plant foot ~0.3-0.5 m out to the side, knee ~40-60 deg; trunk leaning into the cut).
    "cut": [(-0.16, N),
            (0.00, {"hip_r": 22, "knee_r": 52, "ankle_r": 12, "hipout_r": 22, "hip_l": 40, "knee_l": 75,
                    "ankle_l": 10, "lean": 16, "side": -10, "twist": 14, "turn": 8, "out_r": 30, "out_l": 10,
                    "arm_l": 25, "elbow_l": 70, "arm_r": -20, "elbow_r": 60}),
            (0.12, {"hip_r": -8, "knee_r": 28, "ankle_r": -18, "hipout_r": 14, "hip_l": 48, "knee_l": 70,
                    "lean": 14, "side": -6, "twist": 10, "turn": 10, "out_r": 20, "arm_l": 30, "elbow_l": 70,
                    "arm_r": -25, "elbow_r": 60}),
            (0.30, N)],
    # Stopping dead from a run: the right foot planted out in front, heel first, knees bending to soak it up,
    # body upright to leaning back, arms out forward for balance - then the left comes through and he settles.
    "brake": [(-0.08, N),
              (0.10, {"hip_r": 42, "knee_r": 28, "ankle_r": 16, "hip_l": 6, "knee_l": 52, "ankle_l": -6,
                      "lean": -6, "chest": -4, "arm_r": 32, "arm_l": 26, "out_r": 22, "out_l": 22, "elbow_r": 55,
                      "elbow_l": 55}),
              (0.32, {"hip_r": 30, "knee_r": 46, "ankle_r": 14, "hip_l": 34, "knee_l": 58, "ankle_l": 12,
                      "lean": 6, "arm_r": 18, "arm_l": 18, "out_r": 18, "out_l": 18, "elbow_r": 45, "elbow_l": 45}),
              (0.62, N)],
    # A keeper's set position: weight forward on bent knees, hands out in front at waist height.
    "ready": [(0.0, {"hip_r": 28, "knee_r": 50, "ankle_r": 18, "hip_l": 28, "knee_l": 50, "ankle_l": 18,
                     "hipout_r": 6, "hipout_l": 6, "lean": 18, "chest": 6, "nod": -14, "abs": 1, "arm_r": 22, "arm_l": 22,
                     "out_r": 0, "out_l": 0, "elbow_r": 30, "elbow_l": 30, "across_r": 0, "across_l": 0}),
              (1.0, "same")],
    # A keeper's dive to his right (to his left: mirrored).  0 = he springs.
    "dive": [(0.00, {"hip_r": 28, "knee_r": 50, "ankle_r": 18, "hip_l": 28, "knee_l": 50, "ankle_l": 18,
                     "lean": 18, "abs": 1, "arm_r": 22, "arm_l": 22, "out_r": 0, "out_l": 0, "elbow_r": 30, "elbow_l": 30}),
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
             (-0.06, {"arm_r": 0, "arm_l": 0, "across_r": 30, "across_l": 30, "elbow_r": 80, "elbow_l": 80, "out_r": -10, "out_l": -10, "abs": 1, "lean": 12,
                      "hip_r": -20, "knee_r": 70, "knee_l": 25}),
             (0.06, {"hip_r": 45, "knee_r": 30, "ankle_r": -30, "knee_l": 20, "arm_r": 45, "arm_l": 30, "out_r": 40,
                     "out_l": 55, "elbow_r": 30, "elbow_l": 30, "lean": -6, "turn": 10}),
             (0.26, {"hip_r": 85, "knee_r": 8, "ankle_r": -25, "knee_l": 15, "arm_r": 30, "arm_l": 20, "out_r": 45,
                     "out_l": 60, "elbow_r": 25, "elbow_l": 25, "lean": -14, "turn": 16, "air": 0.10}),
             (0.50, {"hip_r": 30, "knee_r": 30, "knee_l": 10, "arm_r": 10, "out_r": 20, "out_l": 25, "lean": -4}),
             (0.80, N)],
    # A roll / short throw out: down low, the arm swinging through underneath.
    "bowl": [(-0.30, N),
             (-0.06, {"arm_r": 0, "arm_l": 0, "across_r": 30, "across_l": 30, "elbow_r": 80, "elbow_l": 80, "out_r": -10, "out_l": -10, "abs": 1, "lean": 12}),
             (0.00, {"arm_r": -45, "out_r": 15, "elbow_r": 10, "arm_l": 40, "out_l": 30, "elbow_l": 30, "lean": 25,
                     "hip_l": 35, "knee_l": 55, "knee_r": 30, "twist": -14, "turn": -8}),
             (0.18, {"arm_r": 60, "out_r": 10, "elbow_r": 10, "arm_l": 20, "out_l": 35, "elbow_l": 30, "lean": 32,
                     "hip_l": 40, "knee_l": 60, "knee_r": 35, "twist": 14, "turn": 6}),
             (0.45, {"arm_r": 40, "elbow_r": 20, "lean": 18, "hip_l": 15, "knee_l": 25, "knee_r": 10}),
             (0.80, N)],
    # A throw-in: ball held in both hands, taken back behind the head, then thrown from over it - both feet on
    # the ground, as the laws say.  (t = the moment it's thrown.)
    "throwin": [(-1.60, {"arm_r": 0, "arm_l": 0, "across_r": 30, "across_l": 30, "elbow_r": 80, "elbow_l": 80, "out_r": -10, "out_l": -10, "abs": 1}),
                (-0.70, {"arm_r": 0, "arm_l": 0, "across_r": 30, "across_l": 30, "elbow_r": 80, "elbow_l": 80, "out_r": -10, "out_l": -10, "abs": 1}),
                (-0.25, {"arm_r": 135, "arm_l": 135, "across_r": 0, "across_l": 0, "elbow_r": 100, "elbow_l": 100, "out_r": 18, "out_l": 18, "abs": 1,
                         "lean": -16, "chest": -8, "nod": -8, "hip_l": 22, "knee_l": 25, "knee_r": 20}),
                (0.00, {"arm_r": 120, "arm_l": 120, "across_r": -15, "across_l": -15, "elbow_r": 40, "elbow_l": 40, "out_r": 30, "out_l": 30, "abs": 1,
                        "lean": 8, "hip_l": 22, "knee_l": 20, "knee_r": 15}),
                (0.25, {"arm_r": 90, "arm_l": 90, "across_r": 10, "across_l": 10, "elbow_r": 10, "elbow_l": 10, "out_r": 5, "out_l": 5, "abs": 1,
                        "lean": 18, "hip_l": 20, "knee_l": 18, "knee_r": 12}),
                (0.70, N)],
    # An assistant referee's flag straight up (offside); the referee's arm up for an indirect free kick.
    "flag": [(-0.3, N), (0.0, {"arm_r": 170, "out_r": 0, "elbow_r": 0, "abs": 1}), (2.5, {"arm_r": 170, "out_r": 0, "abs": 1}),
             (2.9, N)],
    "signal": [(-0.3, N), (0.0, {"arm_r": 172, "out_r": 0, "elbow_r": 0, "nod": -8, "abs": 1}),
               (2.5, {"arm_r": 172, "out_r": 0, "nod": -8, "abs": 1}), (2.9, N)],
    # So close: hands on his head after a shot that didn't go in.
    "despair": [(-0.3, N),
                (0.1, {"arm_r": 120, "arm_l": 120, "across_r": -15, "across_l": -15, "elbow_r": 100, "elbow_l": 100, "out_r": 46, "out_l": 46, "abs": 1,
                       "lean": -6, "nod": -12}),
                (1.6, {"arm_r": 118, "arm_l": 118, "across_r": -15, "across_l": -15, "elbow_r": 105, "elbow_l": 105, "out_r": 46, "out_l": 46, "abs": 1,
                       "lean": 4, "nod": 14}),
                (2.1, N)],
    # The scorer's knee slide: down on both knees, leaning back, arms out wide - then up again.
    "kneeslide": [(-0.2, N),
                  (0.15, {"hip_r": 10, "hip_l": 10, "knee_r": 110, "knee_l": 110, "ankle_r": -30, "ankle_l": -30,
                          "lean": -20, "chest": -8, "out_r": 95, "out_l": 95, "arm_r": 10, "arm_l": 10, "nod": -25}),
                  (1.3, {"hip_r": 5, "hip_l": 5, "knee_r": 115, "knee_l": 115, "ankle_r": -30, "ankle_l": -30,
                         "lean": -28, "chest": -10, "out_r": 120, "out_l": 120, "arm_r": 15, "arm_l": 15,
                         "elbow_r": 20, "elbow_l": 20, "nod": -30}),
                  (1.9, N)],
    # The referee holding up a card; the player booked, arms out ("what was that for?").
    "card": [(0.0, {"arm_r": 172, "out_r": 0, "elbow_r": 0, "nod": -4, "abs": 1}), (1.0, "same")],
    "protest": [(0.0, {"out_r": 25, "out_l": 25, "arm_r": 50, "arm_l": 50, "elbow_r": 70, "elbow_l": 70,
                       "lean": -4, "nod": -6}), (1.0, "same")],
    # In the wall at a free kick: shoulder to shoulder, hands crossed in front of them.
    "wall": [(0.0, {"arm_r": 15, "arm_l": 15, "across_r": 60, "across_l": 60, "elbow_r": 20, "elbow_l": 20, "out_r": -15, "out_l": -15, "abs": 1,
                    "lean": 4, "nod": -4, "knee_r": 6, "knee_l": 6}), (1.0, "same")],
    # In the wall as the free kick is struck: up off both feet, hands still crossed, knees tucked, head down.
    "walljump": [(-0.30, {"arm_r": 15, "arm_l": 15, "across_r": 60, "across_l": 60, "elbow_r": 20, "elbow_l": 20,
                          "out_r": -15, "out_l": -15, "abs": 1, "lean": 4, "nod": -4, "knee_r": 6, "knee_l": 6}),
                 (-0.12, {"arm_r": 15, "arm_l": 15, "across_r": 60, "across_l": 60, "elbow_r": 20, "elbow_l": 20,
                          "out_r": -15, "out_l": -15, "abs": 1, "lean": 14, "nod": 6, "hip_r": 30, "hip_l": 30,
                          "knee_r": 55, "knee_l": 55, "ankle_r": 20, "ankle_l": 20}),
                 (0.00, {"arm_r": 15, "arm_l": 15, "across_r": 60, "across_l": 60, "elbow_r": 20, "elbow_l": 20,
                         "out_r": -15, "out_l": -15, "abs": 1, "lean": 6, "nod": 18, "hip_r": 25, "hip_l": 25,
                         "knee_r": 50, "knee_l": 50, "ankle_r": -25, "ankle_l": -25}),
                 (0.22, {"arm_r": 15, "arm_l": 15, "across_r": 60, "across_l": 60, "elbow_r": 20, "elbow_l": 20,
                         "out_r": -15, "out_l": -15, "abs": 1, "lean": 10, "nod": 10, "hip_r": 25, "hip_l": 25,
                         "knee_r": 40, "knee_l": 40}),
                 (0.55, N)],
    # Keepers.  The split step: a little hop onto both feet just as the shot is struck, so he's balanced and
    # ready to push off either way (as coaches teach it).
    "splitstep": [(-0.15, {"hip_r": 28, "knee_r": 50, "ankle_r": 18, "hip_l": 28, "knee_l": 50, "ankle_l": 18, "hipout_r": 6, "hipout_l": 6, "lean": 18, "chest": 6, "nod": -14, "abs": 1, "arm_r": 22, "arm_l": 22, "out_r": 0,
                           "out_l": 0, "elbow_r": 30, "elbow_l": 30}),
                  (0.00, {"hip_r": 18, "knee_r": 32, "ankle_r": -10, "hip_l": 18, "knee_l": 32, "ankle_l": -10,
                          "hipout_r": 10, "hipout_l": 10, "lean": 14, "nod": -12, "abs": 1, "arm_r": 28, "arm_l": 28,
                          "out_r": 8, "out_l": 8, "elbow_r": 30, "elbow_l": 30}),
                  (0.15, {"hip_r": 28, "knee_r": 50, "ankle_r": 18, "hip_l": 28, "knee_l": 50, "ankle_l": 18, "hipout_r": 6, "hipout_l": 6, "lean": 18, "chest": 6, "nod": -14, "abs": 1, "arm_r": 22, "arm_l": 22, "out_r": 0,
                          "out_l": 0, "elbow_r": 30, "elbow_l": 30})],
    # Catching it: hands out to meet the ball, fingers up behind it, then pulled into the chest, body over it.
    "catch": [(-0.25, {"abs": 1, "arm_r": 40, "arm_l": 40, "elbow_r": 40, "elbow_l": 40, "lean": 10, "knee_r": 20,
                       "knee_l": 20, "hip_r": 12, "hip_l": 12}),
              (0.00, {"abs": 1, "arm_r": 78, "arm_l": 78, "elbow_r": 18, "elbow_l": 18, "across_r": 10, "across_l": 10,
                      "lean": 8, "knee_r": 25, "knee_l": 25, "hip_r": 14, "hip_l": 14}),
              (0.25, {"abs": 1, "arm_r": 25, "arm_l": 25, "elbow_r": 80, "elbow_l": 80, "across_r": 45, "across_l": 45, "out_r": 0, "out_l": 0, "lean": 18, "nod": 12, "knee_r": 25, "knee_l": 25, "hip_r": 15, "hip_l": 15}),
              (0.60, {"abs": 1, "arm_r": 25, "arm_l": 25, "elbow_r": 80, "elbow_l": 80, "across_r": 45, "across_l": 45, "out_r": 0, "out_l": 0, "lean": 8, "nod": 0})],
    # Holding it: the ball tucked into his chest.
    "cradle": [(0.0, {"abs": 1, "arm_r": 25, "arm_l": 25, "elbow_r": 80, "elbow_l": 80, "across_r": 45, "across_l": 45, "out_r": 0, "out_l": 0}), (1.0, "same")],
    # An overarm throw: the ball back behind his head in his right hand, a step with the left, the arm whipped
    # over the top (like a bowler's), and through.
    "gkthrow": [(-0.55, {"abs": 1, "arm_r": 25, "arm_l": 25, "elbow_r": 80, "elbow_l": 80, "across_r": 45, "across_l": 45, "out_r": 0, "out_l": 0}),
                (-0.25, {"abs": 1, "arm_r": 150, "out_r": 35, "elbow_r": 80, "arm_l": 75, "elbow_l": 20, "out_l": 10,
                         "twist": -25, "turn": -12, "lean": -6, "hip_l": 30, "knee_l": 15, "hip_r": -8, "knee_r": 20}),
                (0.00, {"abs": 1, "arm_r": 125, "out_r": 10, "elbow_r": 10, "arm_l": 25, "elbow_l": 30, "out_l": 15,
                        "twist": 15, "turn": 8, "lean": 14, "hip_l": 20, "knee_l": 30, "hip_r": -15, "knee_r": 25}),
                (0.25, {"abs": 1, "arm_r": 45, "out_r": 5, "elbow_r": 20, "arm_l": 10, "elbow_l": 30, "out_l": 15,
                        "twist": 20, "turn": 10, "lean": 22, "hip_l": 15, "knee_l": 30, "hip_r": -5, "knee_r": 40}),
                (0.60, N)],
    # Beaten: down on his knees, a slap of the grass.
    "slap": [(-0.20, N),
             (0.45, {"hip_r": 5, "hip_l": 5, "knee_r": 100, "knee_l": 100, "ankle_r": -20, "ankle_l": -20, "lean": 30,
                     "nod": 25, "abs": 1, "arm_r": 95, "out_r": 25, "elbow_r": 70, "arm_l": 25, "elbow_l": 30}),
             (0.70, {"hip_r": 5, "hip_l": 5, "knee_r": 100, "knee_l": 100, "ankle_r": -20, "ankle_l": -20, "lean": 42,
                     "nod": 30, "abs": 1, "arm_r": 60, "out_r": 15, "elbow_r": 5, "arm_l": 25, "elbow_l": 30}),
             (1.60, {"hip_r": 5, "hip_l": 5, "knee_r": 100, "knee_l": 100, "ankle_r": -20, "ankle_l": -20, "lean": 38,
                     "nod": 35, "abs": 1, "arm_r": 55, "out_r": 15, "elbow_r": 10, "arm_l": 30, "elbow_l": 30}),
             (2.30, N)],
    # Goal celebrations, standing: kissing the badge (the shirt pulled up to his lips) ...
    "badge": [(-0.3, N),
              (0.3, {"abs": 1, "arm_r": 45, "across_r": 75, "elbow_r": 125, "out_r": 5, "arm_l": 5, "out_l": 12,
                     "elbow_l": 20, "nod": 25, "lean": 4}),
              (2.2, {"abs": 1, "arm_r": 48, "across_r": 75, "elbow_r": 128, "out_r": 5, "arm_l": 5, "out_l": 15,
                     "elbow_l": 20, "nod": 22, "lean": 2}),
              (2.6, N)],
    # ... or a hand cupped to his ear for the away fans, the other arm out wide.
    "ear": [(-0.3, N),
            (0.3, {"abs": 1, "out_r": 60, "arm_r": 40, "elbow_r": 130, "across_r": 20, "out_l": 65, "arm_l": 10,
                   "elbow_l": 10, "lean": -6, "nod": -10, "turn": 10}),
            (2.2, {"abs": 1, "out_r": 62, "arm_r": 40, "elbow_r": 130, "across_r": 20, "out_l": 70, "arm_l": 10,
                   "elbow_l": 10, "lean": -8, "nod": -12, "turn": 12}),
            (2.6, N)],
    # A team-mate applauding a near miss: hands together above his head, a few claps.
    "applaud": [(-0.2, N)] + [(0.1 + 0.16 * j, {"abs": 1, "arm_r": 150, "arm_l": 150, "elbow_r": 30, "elbow_l": 30,
                                                "across_r": 12 if j % 2 else -2, "across_l": 12 if j % 2 else -2,
                                                "out_r": 5, "out_l": 5, "nod": -10})
                                for j in range(8)] + [(1.6, N)],
    # Full time: a handshake - the right hand out, a couple of shakes.
    "shake": [(-0.3, N)] + [(0.1 + 0.18 * j, {"abs": 1, "arm_r": 48 + (6 if j % 2 else 0), "elbow_r": 25,
                                              "across_r": 12, "out_r": 0, "lean": 4, "nod": 6})
                            for j in range(5)] + [(1.3, N)],
    # The referee's whistle: hand to his mouth.
    "whistle": [(-0.15, N),
                (0.05, {"abs": 1, "arm_r": 70, "across_r": 40, "elbow_r": 140, "out_r": 10, "nod": 4}),
                (0.50, {"abs": 1, "arm_r": 72, "across_r": 40, "elbow_r": 140, "out_r": 10, "nod": 4}),
                (0.75, N)],
    # Jockeying: a defender close to the man on the ball - low, knees bent, side-on, one foot forward, arms out
    # a little for balance, eyes on the ball (not diving in).
    "jockey": [(0.0, {"hip_r": 28, "knee_r": 48, "ankle_r": 14, "hip_l": 8, "knee_l": 42, "ankle_l": 12,
                      "hipout_r": 6, "hipout_l": 8, "lean": 18, "turn": 22, "twist": -8, "nod": 18, "out_r": 35,
                      "out_l": 35, "arm_r": 15, "arm_l": -5, "elbow_r": 40, "elbow_l": 40}),
               (1.0, "same")],
    # A tug at the shirt of the man he's chasing: the right arm reaching out after him.
    "tug": [(0.0, {"abs": 1, "arm_r": 72, "out_r": 22, "elbow_r": 12, "across_r": -5, "twist": -12, "lean": 6}),
            (1.0, "same")],
    # A manager on the touchline, arm out, telling them where to go.
    "point": [(-0.4, N),
              (0.0, {"arm_r": 75, "out_r": 30, "elbow_r": 10, "twist": 12, "lean": 4, "nod": -6}),
              (1.2, {"arm_r": 70, "out_r": 35, "elbow_r": 15, "twist": 10, "lean": 4, "nod": -6}),
              (1.6, N)],
}
# The poses above (except those marked "abs") were written on the mannequin's own standing pose, which held
# the arms ~25 degrees further out than our hanging arms: their "out" values are moved up to match.
OUT_SHIFT = 25
for _keys in ACTIONS.values():
    for _t, _p in _keys:
        if isinstance(_p, dict):
            if not _p.pop("abs", 0):
                for _m in ("out_r", "out_l"):
                    if _m in _p:
                        _p[_m] += OUT_SHIFT
# How strongly each blends over the running (a dribbling touch stays light).
WEIGHT = {"touch": 0.55, "cut": 0.7, "brake": 0.75, "shield": 0.8, "jockey": 0.7, "tug": 0.6}


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
    return ({"arm_r": 0, "arm_l": 0, "across_r": 52 + 9 * c, "across_l": 52 + 9 * c, "elbow_r": 82,
             "elbow_l": 82, "out_r": -10, "out_l": -10, "nod": -8}, {})


def hips(u):
    """Hands on hips, head down (the other side, after a goal)."""
    b = math.sin(2 * math.pi * u)
    return ({"out_r": 30, "out_l": 30, "arm_r": -45, "arm_l": -45, "across_r": -45, "across_l": -45,
             "elbow_r": 60, "elbow_l": 60, "nod": 22,
             "lean": 4 + 2 * b, "knee_r": 4, "knee_l": 4}, {})


def shift(u):
    """Standing about: the weight on one leg (the other knee eased, that hip dropping a touch), then shifted
    over to the other - every few seconds, as people stand."""
    w = math.sin(2 * math.pi * u)
    k = max(-1.0, min(1.0, 1.6 * w))                               # (mostly on one side or the other)
    return ({"knee_l": 4 + 9 * max(0.0, k), "knee_r": 4 + 9 * max(0.0, -k), "ankle_l": 2 + 4 * max(0.0, k),
             "ankle_r": 2 + 4 * max(0.0, -k), "tilt": -3 * k, "side": 2.5 * k, "hipout_r": 1.5 * k,
             "hipout_l": -1.5 * k, "head": 2 * math.sin(4 * math.pi * u)}, {"sway": -0.025 * k})


def rest(u):
    """Hands on hips, getting his breath back while play's at the other end - head up, watching."""
    b = math.sin(2 * math.pi * u)
    m, e = shift(u * 0.5)
    m.update({"out_r": 30, "out_l": 30, "arm_r": -45, "arm_l": -45, "across_r": -45, "across_l": -45,
              "elbow_r": 60, "elbow_l": 60, "nod": -2, "lean": 3 + 1.5 * b})
    return m, e


def knees(u):
    """Bent over, hands on knees."""
    b = math.sin(2 * math.pi * u)
    return ({"hip_r": 35, "hip_l": 35, "knee_r": 28, "knee_l": 28, "ankle_r": 8, "ankle_l": 8, "lean": 45 + 3 * b,
             "chest": 8, "arm_r": 22, "arm_l": 22, "out_r": 0, "out_l": 0, "elbow_r": 10, "elbow_l": 10,
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


def run_sky(u):
    """Running off pointing both arms to the sky - another scorer's celebration."""
    return ({"arm_r": 165, "arm_l": 165, "out_r": 15, "out_l": 15, "elbow_r": 5, "elbow_l": 5, "nod": -25,
             "lean": -8}, {})


def run_fist(u):
    """Running off pumping his fist, the other arm out - another."""
    c = math.cos(2 * math.pi * u * 2)
    return ({"arm_r": 115 + 20 * c, "out_r": 35, "elbow_r": 95 - 20 * c, "out_l": 70, "arm_l": -5, "elbow_l": 10,
             "nod": -10, "lean": -4}, {})


def sit(u):
    """Sitting on the bench (a substitute)."""
    b = math.sin(2 * math.pi * u)
    return ({"hip_r": 88, "hip_l": 84, "knee_r": 92, "knee_l": 86, "ankle_r": 5, "lean": 6 + 2 * b, "arm_r": 30,
             "arm_l": 30, "elbow_r": 40, "elbow_l": 40, "across_r": 10, "across_l": 10, "nod": -4}, {})


# --- stepping sideways and backwards, with the feet planted -----------------------------------------------
# Each foot is either on the ground (and, as he moves, goes back under him at exactly his speed - so it stays
# put on the grass) or stepping (lifted, brought through to where it goes down next).  Laid out on a cycle of
# two steps; players3d runs the cycle at his speed / CYCLE_* metres, so the planted foot never slides.
# Real figures: a defender's side-shuffle ~0.4-0.5 m a cycle, about 3 cycles a second at a jockeying 1.5 m/s,
# feet never crossing, low (knees ~40 deg); backpedalling, short quick steps (e.g. Sheppard & Young 2006 on
# agility; McGill on athletic stance).
LEG = 0.80                      # (hip to ankle, knees bent: how far a turn of the hip moves the foot sideways)
LEG_FWD = 1.0                   # (...and forwards / back, with the knee bent and the foot flat - measured on him)
SIDE_A, SIDE_DUTY = 0.11, 0.6   # (each foot: half its travel under him, and the part of the cycle it's down)
BACK_A, BACK_DUTY = 0.13, 0.6
CYCLE_SIDE = 2 * SIDE_A / SIDE_DUTY
CYCLE_BACK = 2 * BACK_A / BACK_DUTY


def _foot(ph, a, duty):
    """(where the foot is along the way he moves - +a ahead .. -a behind, lifted 0..1) at this point of its
    cycle: down (going back under him, evenly) for the first part, then stepping (eased, up and over)."""
    ph %= 1.0
    if ph < duty:
        return a - 2 * a * ph / duty, 0.0
    t = (ph - duty) / (1 - duty)
    e = 0.5 - 0.5 * math.cos(math.pi * t)
    return -a + 2 * a * e, math.sin(math.pi * t)


def shuffle(u):
    """Side-stepping to his right (a defender jockeying): low, the right foot leading out, the left closing up
    behind it - never crossing - each foot planted while it's down; arms a little out for balance."""
    o_r, l_r = _foot(u, SIDE_A, SIDE_DUTY)
    o_l, l_l = _foot(u + 0.5, SIDE_A, SIDE_DUTY)
    deg = lambda o: math.degrees(math.asin(max(-0.9, min(0.9, o / LEG))))
    m = {"hipout_r": 11 + deg(o_r), "hipout_l": 11 - deg(o_l),
         "hip_r": 26 + 16 * l_r, "hip_l": 26 + 16 * l_l,
         "knee_r": 42 + 34 * l_r, "knee_l": 42 + 34 * l_l, "ankle_r": 12 + 6 * l_r, "ankle_l": 12 + 6 * l_l,
         "lean": 15, "out_r": 32, "out_l": 32, "arm_r": 18, "arm_l": 18, "elbow_r": 50, "elbow_l": 50,
         "tilt": 2.5 * (l_l - l_r), "nod": -6}
    return m, {"sway": 0.012 * (l_l - l_r)}


def shuffle_m(u):
    m, e = shuffle(u)
    return mirror(m), {"sway": -e["sway"]}


def backpedal(u):
    """Backing off (a defender backpedalling): low, short quick steps backwards, weight forward, each foot
    planted while it's down."""
    o_r, l_r = _foot(u, BACK_A, BACK_DUTY)
    o_l, l_l = _foot(u + 0.5, BACK_A, BACK_DUTY)
    # (backwards: a planted foot goes from behind him to in front as he moves away from it)
    deg = lambda o: math.degrees(math.asin(max(-0.9, min(0.9, -o / LEG_FWD))))
    c = math.cos(2 * math.pi * u)
    m = {"hip_r": 24 + deg(o_r) + 14 * l_r, "hip_l": 24 + deg(o_l) + 14 * l_l,
         "knee_r": 36 + 40 * l_r, "knee_l": 36 + 40 * l_l, "ankle_r": 10 + 8 * l_r, "ankle_l": 10 + 8 * l_l,
         "hipout_r": 7, "hipout_l": 7, "lean": 14, "nod": -6,
         "arm_r": 10 + 12 * c, "arm_l": 10 - 12 * c, "out_r": 14, "out_l": 14, "elbow_r": 55, "elbow_l": 55,
         "turn": -3 * c}
    return m, {"sway": 0.008 * (l_l - l_r)}


def turnstep(u):
    """Turning on the spot: little steps, one foot then the other, instead of spinning on the spot."""
    m = {}
    for sd, off in (("r", 0.0), ("l", 0.5)):
        l = max(0.0, math.sin(2 * math.pi * (u + off)))
        m["hip_" + sd], m["knee_" + sd], m["ankle_" + sd] = 4 + 14 * l, 8 + 30 * l, 4 + 8 * l
    m["knee_r"] += 4
    m["knee_l"] += 4
    return m, {"sway": 0.012 * math.sin(2 * math.pi * u)}


def run_call(u):
    """Running and calling for the ball: right arm up."""
    return ({"arm_r": 150, "out_r": 20, "elbow_r": 15, "nod": -8}, {})


LOOPS = {"run_call": (run_call, 15, "run"), "shuffle": (shuffle, 30, "idle"), "shuffle_m": (shuffle_m, 30, "idle"),
         "backpedal": (backpedal, 30, "idle"), "turnstep": (turnstep, 30, "idle"),
         "shift": (shift, 240, "idle"), "rest": (rest, 240, "idle"), "sit": (sit, 90, "idle"), "cheer": (cheer, 30, "idle"), "clap": (clap, 30, "idle"), "hips": (hips, 60, "idle"), "knees": (knees, 60, "idle"),
         "walk_sad": (walk_sad, 30, "idle"), "run_arms": (run_arms, 15, "run"), "run_sky": (run_sky, 15, "run"),
         "run_fist": (run_fist, 15, "run")}


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

    char = actor.find("**/+Character").node()
    rest_pos = {j: TransformState.makeMat(char.findJoint(j).getDefaultValue()).getPos() for j in order
                if char.findJoint(j)}
    pelvis_lift = rest_pos["pelvis"] - LVecBase3f(*MANNEQUIN_PELVIS)

    def pose_at(bundle, fr):
        mats, _, _ = _local_mats(bundle, fr)
        out = {j: TransformState.makeMat(mats[j][1]) for j in order}
        if BIND_POS:                                    # (his own bones' lengths)
            for j in order:
                if j == "pelvis":
                    out[j] = out[j].setPos(out[j].getPos() + pelvis_lift)
                elif j in rest_pos:
                    out[j] = out[j].setPos(rest_pos[j])
        return out

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
        """The lowest point of the soles, in the model, for these local transforms - or of his knees or his
        backside, if he's down on the ground (a slide, a knee slide): as if those were soles."""
        nm = nets(local)
        z = min(nm[j].xformPoint(pt)[2] for j, pt in soles)
        for j, r in (("calf.r", 0.03), ("calf.l", 0.03), ("pelvis", 0.09), ("spine_02", 0.11), ("head", 0.10)):
            if j in nm:
                z = min(z, nm[j].xformPoint(LPoint3f(0, 0, 0))[2] - r)
        return z
    rest = feet_z(pose_at(idle, 0))
    tables = {j: {k: [] for k in "hprxyz"} for j in order}
    fixed = None if callable(base_frame) else pose_at(base, base_frame)
    # On the standing pose, the arms start from the skeleton's rest (straight out) and are hung by our sides
    # (HANG) - the mannequin's own standing pose holds them out, shoulders hunched.
    hang = base_anim == "idle"
    char = actor.find("**/+Character").node()
    bind = {j: TransformState.makeMat(char.findJoint(j).getDefaultValue()) for j in ARM_CHAIN + FINGERS
            if char.findJoint(j)}                       # (fingers too: relaxed and open, not the mannequin's fists)
    for f in range(frames):
        u = f / float(frames)
        base_ts = dict(fixed or pose_at(base, int(round(base_frame(u)))))
        if hang:
            base_ts.update(bind)
        net = {}                                         # (each joint's whole turn, after the turns above it)

        def net_q(j):
            return LQuaternionf.identQuat() if j is None else net[j]
        moves, extra = pose_fn(u)
        moves = dict(moves)
        for m, v in POSTURE.get(base_anim, {}).items():     # (the mannequin's posture put right)
            moves[m] = moves.get(m, 0.0) + v
        turns = {}
        if hang:                                        # (the arms hung first; the movement's turns after)
            for m, deg in HANG.items():
                deg += HANG_MH.get(m, 0.0) if BIND_POS else 0.0
                j, ax, sign = MOVES[m]
                turns.setdefault(j, []).append((ax, deg * sign))
        elif ARM_DOWN:                                  # (the mannequin's running arms are out a bit: bring them in)
            for m in ("out_r", "out_l"):
                moves[m] = moves.get(m, 0.0) - ARM_DOWN
        for sd in ("r", "l"):                           # (closing the hand: every finger joint curls)
            g = moves.pop("grip_" + sd, 0.0) + (RELAX_GRIP if BIND_POS and hang else 0.0)
            if g:
                for fg in ("index", "middle", "ring"):
                    for k, part in (("01", 1.0), ("02", 1.1), ("03", 0.7)):
                        turns.setdefault(f"{fg}_{k}.{sd}", []).append((GRIP_AXIS[0], g * part * GRIP_AXIS[1][sd]))
        for m in ORDER:                                 # (always in the same order: turns don't commute)
            deg = moves.get(m, 0.0)
            if deg:
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
            net[j] = q * net_q(parent[j])
        shift = LVecBase3f(extra.get("sway", 0.0), 0, 0)
        if ground:
            shift[2] = rest - feet_z(local) + extra.get("air", 0.0)
        local["pelvis"] = local["pelvis"].setPos(local["pelvis"].getPos() + shift)
        if not BIND_POS:
            for j, k in LIMB_SCALE.items():             # (longer bones: the footballer's arms)
                if j in local and not (hang and j in bind):
                    local[j] = local[j].setPos(local[j].getPos() * k)
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


# The mannequin's own standing and running animations hold the arms ~15 degrees further out from the body
# than a footballer does (it makes the shoulders look hunched up); every movement here brings them in.
ARM_DOWN = 11.0
LIMB_SCALE = {}         # (bones made longer than the mannequin's - set by players3d from skeleton.py)
# With MakeHuman's body the skeleton's joints are moved to his (mhbody.py): every bone takes its length from the
# skeleton itself, and the hips go up or down by as much as his are higher or lower than the mannequin's.
BIND_POS = False
HANG_MH = {"out_r": -6.0, "out_l": -6.0, "arm_r": -9.0, "arm_l": -9.0, "elbow_r": -4.0, "elbow_l": -4.0}   # (his shoulders are broader: the arms in a little more, by his sides)
RELAX_GRIP = 22.0       # (MakeHuman's hand rests open, fingers spread: curled in a little, as a hand hangs)
MANNEQUIN_PELVIS = (0.0, -0.0104, 0.9477)
# The mannequin stands and runs with its neck craned forward (and sprints bent over like a sprinter leaving
# the blocks).  Footballers run fairly upright - trunk ~10-15 degrees forward at speed, head up to see the game
# (e.g. Novacheck 1998, "The biomechanics of running", Gait & Posture 7) - so each base pose is corrected.
# It also stands duck-footed, feet 35 cm apart and turned out 30-40 degrees: brought to about hip width and
# ~10 degrees.  And its running arms come up to face height: lowered, elbows a little more open.
POSTURE = {"idle": {"nod": -13.0, "head": 6.0, "hipout_r": -4.0, "hipout_l": -4.0, "toein_r": 17.0, "toein_l": 27.0},
           "run": {"chest": -18.0, "nod": -14.0, "head": 16.0, "arm_r": -18.0, "arm_l": -18.0,
                   "elbow_r": -16.0, "elbow_l": -16.0}}
FINGERS = tuple(f"{f}_{k}.{sd}" for f in ("index", "middle", "ring", "thumb") for k in ("01", "02", "03") for sd in "lr")
GRIP_AXIS = ("y", {"l": 1, "r": -1})        # (which way a finger curls towards the palm)
ARM_CHAIN = ("clavicle.l", "upperarm.l", "lowerarm.l", "hand.l", "clavicle.r", "upperarm.r", "lowerarm.r", "hand.r")
# Arms hanging naturally from the rest pose (straight out sideways): down by the sides, a little out and
# forward, elbows slightly bent, so the fingertips reach about halfway down the thigh.
HANG = {"out_r": -80, "out_l": -80, "arm_r": 5, "arm_l": 5, "elbow_r": 12, "elbow_l": 12}


RUN_CYCLES = {}          # (name -> metres a cycle covers, at the skeleton's own size)


def _measure_legs(actor):
    char = actor.find("**/+Character").node()
    nm = {}
    for j in ("thigh.l", "calf.l", "foot.l"):
        jn = char.findJoint(j)
        nm[j] = actor.exposeJoint(None, "modelRoot", j).getPos(actor)
    LEGS["thigh"] = (nm["thigh.l"] - nm["calf.l"]).length()
    LEGS["shin"] = (nm["calf.l"] - nm["foot.l"]).length()
    LEGS["hip_h"] = 0.985 * (LEGS["thigh"] + LEGS["shin"])


def _make(actor):
    _CACHE["walk"] = build(actor, "walk", walk_pose, 30)
    _measure_legs(actor)
    for name in RUNS:
        fn, C, beta = run_cycle(name)
        RUN_CYCLES[name] = C
        _CACHE[name] = build(actor, name, fn, 24)
    for name, (fn, n, base) in LOOPS.items():
        if base == "run":                                               # (on top of the run: its stride, frames 2-17)
            _CACHE[name] = build(actor, name, fn, n, ground=False, base_anim="run", base_frame=lambda u: 2 + u * 15)
        else:
            _CACHE[name] = build(actor, name, fn, n)
    for name, keys in ACTIONS.items():
        variants = [(name, keys)]
        if name in ("dive", "recover", "kick", "shot", "touch", "tackle", "punt", "cut", "brake", "slide", "shield", "fouled",
                    "pass", "loft", "flick", "backheel", "hurt", "stumble"):
            variants.append((name + "_m", [(t, mirror(p) if isinstance(p, dict) else p) for t, p in keys]))
        for vn, vk in variants:
            fn, t0, t1 = action_pose(vk)
            n = max(2, int(round((t1 - t0) * FPS)) + 1)
            _CACHE[vn] = build(actor, vn, lambda u, fn=fn, t0=t0, t1=t1, n=n: fn(t0 + u * n / FPS), n)
            SPANS[vn] = (t0, t1)
    # last (the others are built from them): the standing and running, arms brought in
    ni, nr = actor.getNumFrames("idle"), actor.getNumFrames("run")
    _CACHE["idle"] = build(actor, "idle", lambda u: ({}, {}), ni, ground=False, base_anim="idle",
                           base_frame=lambda u: u * ni)
    _CACHE["run"] = build(actor, "run", lambda u: ({}, {}), nr, ground=False, base_anim="run",
                          base_frame=lambda u: u * nr)


def add_all(actor):
    """Give this actor (the mannequin) the walk and every action (built once, shared by every player)."""
    if not _CACHE:
        _make(actor)
    actor.loadAnims(dict(_CACHE))
    return list(_CACHE)
