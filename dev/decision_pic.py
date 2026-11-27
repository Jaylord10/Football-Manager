"""Pictures of "what was he thinking" (26 Nov, the decision scoreboard): one moment from a dev/decisions.py log -
the man on the ball (yellow), his team-mates (blue), their players (red), and his options as arrows labelled with
what each was worth (the chance his team scores from it, in %), the one he chose in white.
usage: python dev/decision_pic.py <log.json> <out.png> <moment index> [<moment index> ...]   (several -> stacked)"""
import json, sys
from PIL import Image, ImageDraw, ImageFont

S, M = 8, 20
W, H = 110 * S + 2 * M, 70 * S + 2 * M + 46
F = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
FS = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
COL = {"pass": (120, 200, 255), "through": (120, 255, 230), "cross": (255, 170, 60), "shoot": (255, 90, 90),
       "carry": (200, 255, 120), "take_on": (255, 120, 220), "hold": (230, 230, 230), "clear": (180, 180, 180)}


def moment(d):
    img = Image.new("RGB", (W, H), (20, 24, 28))
    dr = ImageDraw.Draw(img)
    P = lambda a, l: (M + a * S, M + 46 + (l + 35) * S)
    dr.rectangle([P(0, -35), P(110, 35)], fill=(44, 104, 52), outline=(230, 230, 230), width=2)
    dr.line([P(55, -35), P(55, 35)], fill=(230, 230, 230), width=2)
    for a0, a1 in ((0, 16.5), (93.5, 110)):
        dr.rectangle([P(a0, -20.16), P(a1, 20.16)], outline=(230, 230, 230), width=2)
    for a, l in d["opps"]:
        x, y = P(a, l); dr.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(220, 60, 60), outline=(255, 255, 255))
    for a, l, role in d["mates"]:
        x, y = P(a, l); dr.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(60, 110, 230), outline=(255, 255, 255))
        dr.text((x + 7, y - 6), role, font=FS, fill=(220, 230, 255))
    cx, cy = P(d["a"], d["l"])
    shown = 0
    for o in sorted(d["options"], key=lambda o: -o["value"]):
        if o["at"] is None or shown >= 7:
            continue
        chosen = o["kind"] == d["chose"] and o["target"] == d["target"]
        x, y = P(*o["at"])
        dr.line([cx, cy, x, y], fill=(255, 255, 255) if chosen else COL.get(o["kind"], (200, 200, 200)),
                width=4 if chosen else 2)
        what = f"take on their {o['target']}" if o["kind"] == "take_on" else o["kind"]
        dr.text((x + 4, y + 4), f"{what} {100 * o['value']:.2f}%", font=FS,
                fill=(255, 255, 255) if chosen else COL.get(o["kind"], (200, 200, 200)))
        shown += 1
    if d.get("facing") is not None:                   # which way he's facing: a short black arrow
        import math
        r = math.radians(d["facing"])
        fx, fy = P(d["a"] + 5 * math.cos(r), d["l"] + 5 * math.sin(r))
        dr.line([cx, cy, fx, fy], fill=(0, 0, 0), width=5)
        dr.ellipse([fx - 4, fy - 4, fx + 4, fy + 4], fill=(0, 0, 0))
    dr.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=(255, 220, 40), outline=(0, 0, 0), width=2)
    rest = [o for o in d["options"] if o["at"] is None]
    extra = "   ".join(f"{o['kind']} {100 * o['value']:.2f}%" for o in rest)
    dr.text((M, 6), f"{d['role']} on the ball, nearest man {d['nearest']} m - chose {d['chose']} {d['target']} "
                    f"(worth {100 * d['value']:.2f}%)", font=F, fill=(255, 255, 255))
    dr.text((M, 26), f"attacking left to right; black arrow = which way he's facing.  {extra}", font=FS,
            fill=(210, 210, 210))
    return img


if __name__ == "__main__":
    log = json.load(open(sys.argv[1]))["log"]
    ims = [moment(log[int(i)]) for i in sys.argv[3:]]
    out = Image.new("RGB", (W, H * len(ims)), (0, 0, 0))
    for k, im in enumerate(ims):
        out.paste(im, (0, k * H))
    out.save(sys.argv[2]); print("saved")
