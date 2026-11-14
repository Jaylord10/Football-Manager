"""Procedural textures for the prototype (PIL): pitch, crowd, brick, sky, moors."""
from PIL import Image, ImageDraw, ImageFilter
import random, math
import os
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tex") + os.sep
PX = 20                                     # texture pixels per metre (pitch)
L, Wd = 110, 70                             # the engine's pitch (metres)
SUR = 8                                     # grass beyond the lines


def pitch():
    w, h = (L + 2 * SUR) * PX, (Wd + 2 * SUR) * PX
    im = Image.new("RGB", (w, h), (52, 112, 46))
    d = ImageDraw.Draw(im)
    stripe = 5.5 * PX                        # mowing stripes across the length
    for i in range(int(w / stripe) + 1):
        if i % 2:
            d.rectangle([i * stripe, 0, (i + 1) * stripe, h], fill=(60, 128, 52))
    # subtle noise
    rnd = random.Random(1)
    px = im.load()
    for _ in range(w * h // 6):
        x, y = rnd.randrange(w), rnd.randrange(h)
        r, g, b = px[x, y]; k = rnd.randint(-9, 9)
        px[x, y] = (max(0, r + k), max(0, g + k), max(0, b + k))
    im = im.filter(ImageFilter.GaussianBlur(0.6))
    d = ImageDraw.Draw(im)
    o = SUR * PX
    def P(xm, ym): return (o + xm * PX, o + ym * PX)
    lw = max(2, int(0.12 * PX))
    white = (238, 240, 236)
    d.rectangle([P(0, 0), P(L, Wd)], outline=white, width=lw)
    d.line([P(L / 2, 0), P(L / 2, Wd)], fill=white, width=lw)
    def circ(cx, cy, r, a0=0, a1=360):
        pts = [P(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in range(int(a0), int(a1) + 1, 2)]
        d.line(pts, fill=white, width=lw)
    circ(L / 2, Wd / 2, 9.15)
    d.ellipse([P(L / 2 - .3, Wd / 2 - .3), P(L / 2 + .3, Wd / 2 + .3)], fill=white)
    for side in (0, 1):
        x0 = 0 if side == 0 else L
        s = 1 if side == 0 else -1
        d.rectangle(sorted_rect(P(x0, Wd / 2 - 20.16), P(x0 + s * 16.5, Wd / 2 + 20.16)), outline=white, width=lw)
        d.rectangle(sorted_rect(P(x0, Wd / 2 - 9.16), P(x0 + s * 5.5, Wd / 2 + 9.16)), outline=white, width=lw)
        sx = x0 + s * 11
        d.ellipse([P(sx - .25, Wd / 2 - .25), P(sx + .25, Wd / 2 + .25)], fill=white)
        a = math.degrees(math.acos(5.5 / 9.15))
        circ(sx, Wd / 2, 9.15, -a if side == 0 else 180 - a, a if side == 0 else 180 + a)
        # worn goalmouth
        for _ in range(350):
            gx = x0 + s * abs(rnd.gauss(0, 2.2)); gy = Wd / 2 + rnd.gauss(0, 2.2)
            xx, yy = P(gx, gy)
            d.ellipse([xx - 2, yy - 2, xx + 2, yy + 2], fill=(74, 112, 52))
    for cx, cy, a0 in ((0, 0, 0), (L, 0, 90), (L, Wd, 180), (0, Wd, 270)):
        circ(cx, cy, 1, a0, a0 + 90)
    im.save(OUT + "pitch.png")


def sorted_rect(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]


def crowd(name, cols, density=0.93, seed=0, seat=(60, 30, 30)):
    """Rows of fans (dots of colour) - tiles across a stand."""
    rnd = random.Random(seed)
    w, h = 1024, 512
    im = Image.new("RGB", (w, h), seat)
    d = ImageDraw.Draw(im)
    rows = 32
    rh = h / rows
    for r in range(rows):
        y = r * rh
        d.line([(0, y + rh - 1), (w, y + rh - 1)], fill=(25, 25, 28), width=2)
        x = rnd.uniform(0, 6)
        while x < w:
            if rnd.random() < density:
                c = rnd.choices([k for k, _ in cols], [wt for _, wt in cols])[0]
                c = tuple(max(0, min(255, v + rnd.randint(-18, 18))) for v in c)
                d.rectangle([x, y + rh * 0.25, x + 9, y + rh - 3], fill=c)            # body
                sk = rnd.choice([(230, 190, 160), (200, 150, 120), (140, 95, 70), (90, 60, 45)])
                d.ellipse([x + 2, y + 1, x + 7, y + rh * 0.45], fill=sk)              # head
            x += rnd.uniform(11, 14)
    im.save(OUT + name)


def brick():
    rnd = random.Random(3)
    im = Image.new("RGB", (512, 512), (120, 60, 45))
    d = ImageDraw.Draw(im)
    bh, bw = 16, 48
    for r in range(512 // bh):
        off = (r % 2) * bw // 2
        for c in range(-1, 512 // bw + 1):
            x = c * bw + off
            col = (rnd.randint(120, 160), rnd.randint(50, 70), rnd.randint(38, 52))
            d.rectangle([x + 1, r * bh + 1, x + bw - 2, r * bh + bh - 2], fill=col)
    im.save(OUT + "brick.png")


def sky():
    w, h = 1024, 512
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        t = y / h
        c = (int(150 + 40 * t), int(158 + 38 * t), int(168 + 30 * t))
        for x in range(w):
            px[x, y] = c
    d = ImageDraw.Draw(im)
    rnd = random.Random(5)
    for _ in range(60):                            # low grey cloud
        x, y, r = rnd.randrange(w), rnd.randrange(int(h * 0.7)), rnd.randint(40, 120)
        g = rnd.randint(120, 175)
        d.ellipse([x - r * 2, y - r * 0.5, x + r * 2, y + r * 0.5], fill=(g, g + 4, g + 10))
    im = im.filter(ImageFilter.GaussianBlur(18))
    im.save(OUT + "sky.png")


def moors():
    w, h = 2048, 256
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rnd = random.Random(9)
    pts = [(0, h)]
    y = 140
    for x in range(0, w + 16, 16):
        y += rnd.uniform(-6, 6) + (130 - y) * 0.03
        pts.append((x, y + 40 * math.sin(x / 300.0)))
    pts.append((w, h))
    d.polygon(pts, fill=(88, 98, 82, 255))
    im.save(OUT + "moors.png")


if __name__ == "__main__":
    pitch(); brick(); sky(); moors()
    crowd("crowd_home.png", [((200, 40, 45), 6), ((235, 235, 235), 2), ((30, 30, 34), 2)], seed=1)
    crowd("crowd_away.png", [((30, 30, 32), 5), ((212, 170, 60), 2), ((200, 40, 45), 1)], seed=2)
    crowd("crowd_mixed.png", [((200, 40, 45), 5), ((235, 235, 235), 2), ((30, 30, 34), 3), ((70, 70, 90), 2)], seed=3)
    print("ok")
