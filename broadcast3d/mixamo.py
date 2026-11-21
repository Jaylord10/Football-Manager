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
CM = 100.0                                   # (the capture is in centimetres)
BRIGHT = 1.5

_info = None


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
        special = name is not None and wgt > 0.25 or getattr(ap, "roll", 0.0) > 1.0 or getattr(ap, "lift", 0.0) > 0.05
        is_kick = special and name and name.split("_")[0] in KICKS
        if special and not is_kick:                            # (no move for this yet: the old figure)
            ap.a.show(); self.a.hide()
            return
        ap.a.hide(); self.a.show()
        I = info()
        target = {n: 0.0 for n in self.anims}
        if is_kick and "kick_soccerball" in self.anims:
            target["kick_soccerball"] = 1.0
            self._blend(target, dt, fast=True)
            n = I["kick_soccerball"]["frames"]
            # (our kicks are timed from the strike - frame 30 x the share of the wind-up; the capture strikes
            #  about 40% of the way through)
            f = max(0, min(n - 1, int(n * 0.4 + frame * 0.5)))
            self.a.pose("kick_soccerball", f)
            return
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
