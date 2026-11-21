"""
dev/mixamo_posmap.py - TEST (21 Nov): where each pixel of the Mixamo footballer's picture sits on his body.

Runs in Blender's Python (pip "bpy"):  python3.11 dev/mixamo_posmap.py <Soccer Game Pack folder> <out.npz>
For every pixel of his body picture (1024 x 1024) that's on his kit or skin: the point on his body (rest pose,
metres: x across, y front/back, z up) and which part it's on (1 shirt, 2 shorts, 3 socks, 4 skin, 5 boots).
broadcast3d/mixamo.py uses it to paint each club's kit on him - stripes, hoops, numbers on the back - with the
same pattern rules as our own figures (players3d._kit_colour).
"""
import bpy, sys
import numpy as np
U, OUT = sys.argv[-2], sys.argv[-1]
N = 1024
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=f"{U}/Ch38_nonPBR.fbx")
PART = {"Shirt": 1, "Shorts": 2, "Socks": 3, "Body": 4, "Shoes": 5}
pos = np.zeros((N, N, 3), np.float32)
part = np.zeros((N, N), np.uint8)
dg = bpy.context.evaluated_depsgraph_get()
for o in bpy.context.scene.objects:
    if o.type != "MESH":
        continue
    pid = next((v for k, v in PART.items() if k in o.name), 0)
    if not pid:
        continue
    me = o.evaluated_get(dg).to_mesh()
    me.calc_loop_triangles()
    uv = me.uv_layers.active.data
    mw = o.matrix_world
    co = np.array([tuple(mw @ v.co) for v in me.vertices], np.float32)
    print(o.name, len(me.loop_triangles), co.min(0), co.max(0))
    for t in me.loop_triangles:
        uvs = np.array([tuple(uv[l].uv) for l in t.loops], np.float32) % 1.0
        P = co[list(t.vertices)]
        px = uvs[:, 0] * (N - 1); py = (1.0 - uvs[:, 1]) * (N - 1)
        x0, x1 = int(max(0, np.floor(px.min()))), int(min(N - 1, np.ceil(px.max())))
        y0, y1 = int(max(0, np.floor(py.min()))), int(min(N - 1, np.ceil(py.max())))
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        d = (py[1] - py[2]) * (px[0] - px[2]) + (px[2] - px[1]) * (py[0] - py[2])
        if abs(d) < 1e-9:
            continue
        l0 = ((py[1] - py[2]) * (xs - px[2]) + (px[2] - px[1]) * (ys - py[2])) / d
        l1 = ((py[2] - py[0]) * (xs - px[2]) + (px[0] - px[2]) * (ys - py[2])) / d
        l2 = 1 - l0 - l1
        inside = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
        if not inside.any():
            continue
        w = np.stack([l0, l1, l2], -1)[inside]
        p3 = w @ P
        yy, xx = (ys[inside] - 0.5).astype(int), (xs[inside] - 0.5).astype(int)
        pos[yy, xx] = p3
        part[yy, xx] = pid
np.savez_compressed(OUT, pos=pos.astype(np.float16), part=part)
print("WROTE", OUT, {k: int((part == v).sum()) for k, v in PART.items()})
