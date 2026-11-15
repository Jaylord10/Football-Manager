"""
broadcast3d/skeleton.py - the footballer's skeleton: the mannequin's, with arms of real length.

The mannequin is a stylised figure with short arms: standing straight, its fingertips only reach its hips.  A
real man's reach to the middle of his thigh: upper arm ~0.186 x his height, forearm ~0.146, hand ~0.108
(Drillis & Contini 1966, "Body segment parameters", the standard table - also in Winter, "Biomechanics and Motor
Control of Human Movement", ch. 4).  For this 1.78 m skeleton that's 33 / 26 / 19 cm, against the mannequin's
26 / 21 / 15 - so each part of the arm is lengthened ~26%.

  python broadcast3d/skeleton.py     writes models/footballer.glb (the mannequin's file, with the longer arms:
                                     the bones' rest lengths and the skin's bind matrices)
The animations (built in gait.py) lengthen the same bones with LIMB_SCALE.
"""
import json
import os
import struct

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "models", "mannequin.glb")
OUT = os.path.join(HERE, "models", "footballer.glb")
HEIGHT = 1.78
# bone -> how much longer its offset from its parent gets (the parent's length, in effect)
LIMB_SCALE = {}
for s in ("l", "r"):
    LIMB_SCALE["lowerarm." + s] = 0.186 * HEIGHT / 0.26198       # (the upper arm's length)
    LIMB_SCALE["hand." + s] = 0.146 * HEIGHT / 0.20732           # (the forearm's)
    for f in ("thumb", "index", "middle", "ring"):          # (the hand's: the knuckles moved out; the fingers'
        LIMB_SCALE[f"{f}_01.{s}"] = 0.108 * HEIGHT / 0.150  #  own joints stay as far apart as they were - the
                                                            #  mannequin's fingers are long already)


def _mat(n):
    t = np.array(n.get("translation", [0, 0, 0]), np.float64)
    x, y, z, w = n.get("rotation", [0, 0, 0, 1])
    s = np.array(n.get("scale", [1, 1, 1]), np.float64)
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M = np.eye(4)
    M[:3, :3] = R * s
    M[:3, 3] = t
    return M


def build():
    b = open(SRC, "rb").read()
    jl = struct.unpack("<I", b[12:16])[0]
    js = json.loads(b[20:20 + jl])
    rest = b[20 + jl:]
    bl = struct.unpack("<I", rest[0:4])[0]
    binbuf = bytearray(rest[8:8 + bl])
    nodes = js["nodes"]
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    for n in nodes:
        k = LIMB_SCALE.get(n.get("name"))
        if k:
            n["translation"] = [v * k for v in n.get("translation", [0, 0, 0])]

    def glob(i):
        M = _mat(nodes[i])
        while i in parent:
            i = parent[i]
            M = _mat(nodes[i]) @ M
        return M
    sk = js["skins"][0]
    acc = js["accessors"][sk["inverseBindMatrices"]]
    bv = js["bufferViews"][acc["bufferView"]]
    off = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    old = np.frombuffer(bytes(binbuf[off:off + 64 * len(sk["joints"])]), np.float32).reshape(-1, 4, 4)
    # The bind pose (what the skin was made in) from the old bind matrices (column-major), each bone's place
    # relative to its parent there, the lengthened bones moved along, and the new bind matrices from that.
    G = {ni: np.linalg.inv(old[j].T.astype(np.float64)) for j, ni in enumerate(sk["joints"])}
    local = {ni: (np.linalg.inv(G[parent[ni]]) @ G[ni] if parent.get(ni) in G else G[ni]) for ni in G}
    for ni in G:
        k = LIMB_SCALE.get(nodes[ni].get("name"))
        if k:
            local[ni] = local[ni].copy()
            local[ni][:3, 3] *= k
    new = {}

    def bind(ni):
        if ni not in new:
            new[ni] = bind(parent[ni]) @ local[ni] if parent.get(ni) in G else local[ni]
        return new[ni]
    for j, ni in enumerate(sk["joints"]):
        ibm = np.linalg.inv(bind(ni))
        binbuf[off + 64 * j: off + 64 * (j + 1)] = ibm.T.astype(np.float32).tobytes()
    js_b = json.dumps(js, separators=(",", ":")).encode()
    js_b += b" " * ((4 - len(js_b) % 4) % 4)
    out = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js_b) + 8 + len(binbuf))
    out += struct.pack("<I", len(js_b)) + b"JSON" + js_b + struct.pack("<I", len(binbuf)) + b"BIN\x00" + bytes(binbuf)
    open(OUT, "wb").write(out)
    # how far the old bind matrices were from the rest pose (should be ~0 for the bones we didn't touch)
    print("footballer.glb written; arms x", round(LIMB_SCALE["lowerarm.l"], 3), round(LIMB_SCALE["hand.l"], 3),
          round(LIMB_SCALE["index_01.l"], 3))
    return old


if __name__ == "__main__":
    build()
