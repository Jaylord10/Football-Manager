"""Animated players: a Mixamo-rigged figure (idle / walk / run), painted in the club's kit by height."""
import math
from direct.actor.Actor import Actor
from panda3d.core import (GeomVertexFormat, GeomVertexArrayFormat, GeomVertexWriter, GeomVertexReader, Geom,
                          InternalName, ColorAttrib, TextNode)

import os
MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "Xbot.glb")


def C(rgb):
    return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, 1.0)


def paint(actor, kit, skin, hair):
    """Colour each vertex by where it sits on the body (bind pose): boots, socks, skin, shorts, shirt, head."""
    shirt, shorts, socks = C(kit["shirt"]), C(kit["shorts"]), C(kit["socks"])
    sk, hr, boot = C(skin), C(hair), C((22, 22, 24))
    trim = C(kit.get("trim", kit["shirt"]))
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
                elif z < 0.46:
                    c = socks
                elif z < 0.66:
                    c = sk
                elif z < 0.97 and ax < 0.24:
                    c = shorts
                elif z < 1.49 and ax < 0.36:
                    c = trim if (z > 1.43 and ax < 0.09) else shirt
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
        self.root = parent.attachNewNode("player")
        self.a = Actor(model)
        self.a.reparentTo(self.root)
        self.a.setScale(1.08)
        paint(self.a, kit, skin, hair)
        self.a.enableBlend()
        for n in ("idle", "walk", "run"):
            self.a.loop(n)
        self.a.setPlayRate(1.0, "idle")
        tn = TextNode("num"); tn.setText(str(number)); tn.setAlign(TextNode.ACenter)
        tn.setTextColor(*C(kit.get("number", (255, 255, 255))))
        n = self.a.exposeJoint(None, "modelRoot", "mixamorig:Spine2")
        t = n.attachNewNode(tn); t.setScale(0.22); t.setPos(0, -0.16, 0.0); t.setTwoSided(True)
        self.h = None
        self.sp = 0.0

    def update(self, x, y, fx, fy, speed, dt, active=True):
        if not active:
            self.root.hide(); return
        self.root.show()
        self.root.setPos(x, y, 0)
        h = math.degrees(math.atan2(-fx, fy))
        if self.h is None:
            self.h = h
        dh = (h - self.h + 180) % 360 - 180
        self.h += dh * min(1.0, dt * 9)
        self.root.setH(self.h)
        sp = speed / 10.0                                                     # m/s
        self.sp += (sp - self.sp) * min(1.0, dt * 6)
        s = self.sp
        w_idle = max(0.0, 1 - s / 1.0)
        w_run = min(1.0, max(0.0, (s - 2.0) / 2.0))
        w_walk = max(0.0, 1 - w_idle - w_run)
        self.a.setControlEffect("idle", w_idle)
        self.a.setControlEffect("walk", w_walk)
        self.a.setControlEffect("run", w_run)
        self.a.setPlayRate(max(0.6, min(2.2, s / 1.5)), "walk")
        self.a.setPlayRate(max(0.7, min(1.9, s / 4.8)), "run")
