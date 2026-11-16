"""Check of the gantry close-up by the near corner flag: moves the sample goal's celebration to the near
corner (L or R).  usage: python dev/corner_celebration.py out.json [L|R]  (from the game folder), then
  python broadcast3d/viewer.py 13570 1 outdir --match=out.json"""
import json, gzip, sys
d = json.load(gzip.open("broadcast3d/match.json.gz", "rt"))
F = d["frames"]
HX, HY = 55.0, 35.0
side = sys.argv[2] if len(sys.argv) > 2 else "L"
cx = -HX + 1.5 if side == "L" else HX - 1.5
for k in range(13506, 13700):
    fr = F[k]
    if "c" not in fr:
        continue
    sc = fr["c"][1]
    team = 0 if sc < 11 else 1
    for j in range(22):
        if (j < 11) == (team == 0) and j != 0 and j != 11:
            off = (j % 11) * 0.7
            wx, wy = cx + (off if side == "L" else -off) * 0.6, -HY + 1.2 + off * 0.5
            if j == sc:
                wx, wy = cx, -HY + 1.0
            fr["p"][j][0] = round((wx + HX) * 10, 1)
            fr["p"][j][1] = round((HY - wy) * 10, 1)
            fr["p"][j][4] = 0.0
json.dump(d, open(sys.argv[1], "w"))
