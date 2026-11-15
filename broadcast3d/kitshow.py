"""
broadcast3d/kitshow.py - a picture of both sides' kits for a match (outfield front and back, and the keeper),
in the same sunlight as the 3D view.

usage: python broadcast3d/kitshow.py "Home Club" "Away Club" out.png
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from panda3d.core import loadPrcFileData
loadPrcFileData("", "window-type offscreen\naudio-library-name null\nwin-size 1280 560\nframebuffer-multisample 1\n"
                    "multisamples 4\n")
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (AmbientLight, DirectionalLight, Vec4, CardMaker, PNMImage, Filename, Shader, TextNode,
                          Fog, AntialiasAttrib)
import kits
import players3d

home_name, away_name, out = sys.argv[1], sys.argv[2], sys.argv[3]
b = ShowBase()
b.disableMouse()
b.setBackgroundColor(0.55, 0.68, 0.82, 1)
b.render.setAntialias(AntialiasAttrib.MMultisample)
al = AmbientLight("a"); al.setColor(Vec4(0.5, 0.53, 0.6, 1)); b.render.setLight(b.render.attachNewNode(al))
dl = DirectionalLight("sun"); dl.setColor(Vec4(1.2, 1.1, 0.92, 1)); dl.setShadowCaster(True, 2048, 2048)
dl.getLens().setFilmSize(30, 20); dl.getLens().setNearFar(1, 100)
sun = b.render.attachNewNode(dl); sun.setPos(-12, -25, 30); sun.lookAt(0, 0, 0); b.render.setLight(sun)
b.render.setShader(Shader.load(Shader.SL_GLSL, os.path.join(HERE, "shaders", "lit.vert"),
                               os.path.join(HERE, "shaders", "lit.frag")))
b.render.setShaderInput("shadow_bias", 0.0005)
b.render.setShaderInput("shadow_texel", 1.0 / 2048)
b.render.setShaderInput("detail_amt", 0.0)
b.render.setShaderInput("crowd_amt", 0.0)
b.render.setShaderInput("night_on", 0.0)
b.render.setShaderInput("detail_scale", 1.0, 1.0)
players3d.shader_defaults(b.render)
f = Fog("none"); f.setExpDensity(0.0); b.render.setFog(f)
cm = CardMaker("grass"); cm.setFrame(-30, 30, -30, 30)
g = b.render.attachNewNode(cm.generate()); g.setP(-90); g.setColor(0.25, 0.55, 0.22, 1)

hk, ak, g0, g1, hi, ai = kits.choose(home_name, away_name)
ps = []
row = [(hk, 10, 0), (hk, 7, 180), (g0, 1, 20), (ak, 9, 0), (ak, 4, 180), (g1, 1, -20)]
for i, (kit, num, turn) in enumerate(row):
    info = hi if i < 3 else ai
    p = players3d.AnimPlayer(b.render, kit, num, (214, 168, 134), (40, 28, 20), name="Player Smith",
                             crest=info.get("crest"))
    x = -5.6 + i * 2.25 + (0.6 if i >= 3 else 0)
    p.update(x, 0, 0, -1, 0, 0.5)                                       # (facing the camera...)
    p.h = 180 + turn; p.root.setH(p.h)                                  # (...or turned to show his back)
    ps.append(p)
for p in ps:                                                            # (just standing - once they're all made)
    p.loco = {n: 0.0 for n in p.loco_names}; p.loco["idle"] = 1.0
    p.cur = (None, 0.0, 0.0); p._mix(); p.a.pose("idle", 20)
for name, info, x in ((home_name, hi, -3.3), (away_name, ai, 3.9)):
    tn = TextNode("t"); tn.setText(name); tn.setAlign(TextNode.ACenter); tn.setTextColor(1, 1, 1, 1)
    t = b.render.attachNewNode(tn); t.setPos(x, 0, 2.35); t.setScale(0.32); t.setShaderOff(1); t.setLightOff(1)
b.cam.setPos(0.3, -15, 2.2)
b.cam.lookAt(0.3, 0, 1.05)
b.camLens.setFov(48)
for _ in range(3):
    b.taskMgr.step()
img = PNMImage(); b.win.getScreenshot(img); img.write(Filename.fromOsSpecific(out))
print("kits", home_name, hk["shirt"], hk["pattern"], "|", away_name, ak["shirt"], ak["pattern"])
