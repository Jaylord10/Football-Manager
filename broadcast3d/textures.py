"""Procedural textures for the prototype (PIL): pitch, crowd, brick, sky, moors."""
from PIL import Image, ImageDraw, ImageFilter
import random, math
import os
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tex") + os.sep
PX = 20                                     # texture pixels per metre (pitch)
L, Wd = 110, 70                             # the engine's pitch (metres)
SUR = 8                                     # grass beyond the lines


MOWING = ("stripes", "wide", "checks", "diagonal", "lengthways")


def _save(im, name):
    """Save a texture whole or not at all (a half-written picture - the game closed mid-way - can't be read)."""
    tmp = OUT + name + ".part.png"
    im.save(tmp)
    os.replace(tmp, OUT + name)


def pitch(name="pitch.png", mowing="stripes", wear_amt=1.0, green=(52, 112, 46), seed=1):
    """The pitch.  mowing: the groundsman's pattern - stripes across (the usual), wide stripes, checks,
    diagonals, or lengthways; wear_amt: how worn the goalmouths and the middle are (0 a perfect new hybrid
    pitch, 1 a lower-league pitch in November)."""
    w, h = (L + 2 * SUR) * PX, (Wd + 2 * SUR) * PX
    im = Image.new("RGB", (w, h), green)
    d = ImageDraw.Draw(im)
    light = (green[0] + 8, green[1] + 16, green[2] + 6)
    import numpy as np
    ys, xs = np.mgrid[0:h, 0:w]
    st = 5.5 * PX
    if mowing == "wide":
        band = (xs // (st * 2)) % 2
    elif mowing == "checks":
        band = ((xs // st) + (ys // st)) % 2
    elif mowing == "diagonal":
        band = ((xs + ys) // (st * 1.2)) % 2
    elif mowing == "lengthways":
        band = (ys // (st * 0.9)) % 2
    else:
        band = (xs // st) % 2
    a = np.where(band[..., None] == 1, np.array(light, np.float32), np.array(green, np.float32))
    im = Image.fromarray(a.astype(np.uint8))
    d = ImageDraw.Draw(im)
    # subtle noise
    rnd = random.Random(seed)
    px = im.load()
    for _ in range(w * h // 6):
        x, y = rnd.randrange(w), rnd.randrange(h)
        r, g, b = px[x, y]; k = rnd.randint(-9, 9)
        px[x, y] = (max(0, r + k), max(0, g + k), max(0, b + k))
    im = im.filter(ImageFilter.GaussianBlur(0.6))
    if wear_amt > 0:
        im = Image.blend(im, wear(im), min(1.0, wear_amt))
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
    _save(im, name)


def ground_pitch(slug, prof):
    """This club's own pitch (made once, kept in tex/): its groundsman's mowing pattern, and as worn as its
    profile says (a "perfect" hybrid pitch hardly at all, an old pitch a lot)."""
    import zlib
    name = f"pitch_{slug}.png"
    if os.path.exists(OUT + name):
        return name
    surf = str(((prof or {}).get("ground") or {}).get("pitch", {}).get("surface", "")).lower()
    h = zlib.crc32(slug.encode())
    mowing = MOWING[h % len(MOWING)]
    wear_amt = 0.25 if ("perfect" in surf or "hybrid" in surf) else 1.0 if ("heavy" in surf or "worn" in surf
                                                                               or "mud" in surf) else 0.65
    tint = (h // 7) % 3
    green = ((50, 114, 44), (54, 110, 48), (48, 116, 50))[tint]
    pitch(name, mowing, wear_amt, green, seed=h % 1000)
    return name


def wear(im):
    """A November pitch at a lower-league ground: the goalmouths worn to mud (worst on the keeper's line and the
    six-yard box), the penalty spots, a thinner strip down the middle where most of the game is played, the
    assistants' runs along the touchlines, the centre circle - with the edges broken up, as real wear is."""
    import numpy as np
    a = np.asarray(im).astype(np.float32)
    h, w = a.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    mx, my = xs / PX - SUR, ys / PX - SUR                       # (metres from the corner of the lines)
    rng = np.random.default_rng(5)

    def noise(scale):
        small = rng.random((h // scale + 2, w // scale + 2)).astype(np.float32)
        img = Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        return np.asarray(img).astype(np.float32) / 255.0
    n = 0.55 * noise(40) + 0.3 * noise(12) + 0.15 * noise(4)
    m = np.zeros((h, w), np.float32)
    for x0 in (0.0, float(L)):
        dx = np.abs(mx - x0)
        gm = np.exp(-(dx / 5.0) ** 2 - ((my - Wd / 2) / 5.5) ** 2)              # (the goalmouth)
        line = np.exp(-(dx / 1.3) ** 2 - ((my - Wd / 2) / 3.8) ** 2)            # (the keeper's line)
        spot = np.exp(-((dx - 11) / 1.2) ** 2 - ((my - Wd / 2) / 1.2) ** 2)     # (the penalty spot)
        m = np.maximum(m, np.maximum(0.9 * gm, np.maximum(line, 0.75 * spot)))
    mid = np.exp(-((my - Wd / 2) / 9.0) ** 2) * (1 - np.exp(-((mx - L / 2) / 40.0) ** 2) * 0.2) * 0.42
    centre = np.exp(-((np.hypot(mx - L / 2, my - Wd / 2)) / 4.0) ** 2) * 0.4
    runs = (np.exp(-((my + 1.5) / 0.8) ** 2) + np.exp(-((my - Wd - 1.5) / 0.8) ** 2)) * 0.45
    m = np.maximum(m, np.maximum(mid, np.maximum(centre, runs)))
    m = np.clip((m - 0.3 * n + 0.08) * 1.4, 0, 1)                    # (broken up)
    mud = np.array([96, 82, 58], np.float32)
    worn = np.array([92, 118, 60], np.float32)                   # (thin, yellowing grass on the way to mud)
    k1 = np.clip(m * 2.0, 0, 1)[..., None]
    k2 = np.clip(m * 2.0 - 1.0, 0, 1)[..., None]
    out = a * (1 - k1) + (a * 0.5 + worn * 0.5) * k1
    out = out * (1 - k2) + (mud * (0.85 + 0.3 * n[..., None])) * k2
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def sorted_rect(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]


def crowd(name, cols, density=0.93, seed=0, seat=(60, 30, 30)):
    """Rows of fans - tiles across a stand.  Each fan: shoulders and a body in a colour (mostly the club's), a
    head (skin tones, hair, a woolly hat on some - it's November), some with a scarf in the club's colours,
    a few smaller (children); empty seats here and there."""
    rnd = random.Random(seed)
    S = 2                                       # (drawn at twice the old size: sharper close up)
    w, h = 1024 * S, 512 * S
    im = Image.new("RGB", (w, h), seat)
    d = ImageDraw.Draw(im)
    rows = 32
    rh = h / rows
    main = [k for k, _ in cols]
    skins = [(232, 192, 162), (214, 168, 134), (196, 146, 112), (150, 104, 76), (104, 70, 50), (78, 52, 38)]
    hairs = [(30, 22, 18), (60, 42, 30), (110, 80, 50), (170, 140, 100), (140, 140, 140), (20, 18, 16)]
    for r in range(rows):
        y = r * rh
        d.rectangle([0, y + rh - 3 * S, w, y + rh], fill=tuple(max(0, v - 25) for v in seat))   # (the seat backs)
        x = rnd.uniform(0, 6 * S)
        while x < w:
            if rnd.random() < density:
                c = rnd.choices(main, [wt for _, wt in cols])[0]
                c = tuple(max(0, min(255, v + rnd.randint(-18, 18))) for v in c)
                kid = rnd.random() < 0.08
                k = 0.75 if kid else 1.0
                bw, top = 10 * S * k, y + rh * (0.42 if kid else 0.30)
                d.rounded_rectangle([x, top, x + bw, y + rh - 2 * S], radius=int(3 * S * k), fill=c)   # (body)
                if rnd.random() < 0.3:                                        # (a scarf)
                    sc = rnd.choice(main)
                    d.rectangle([x + 1 * S, top, x + bw - 1 * S, top + 2 * S], fill=sc)
                    d.rectangle([x + bw * 0.55, top, x + bw * 0.55 + 2 * S, top + 6 * S], fill=sc)
                sk = rnd.choice(skins)
                hx, hy, hr = x + bw / 2, top - 3.0 * S * k, 3.2 * S * k
                d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=sk)                         # (head)
                hat = rnd.random()
                if hat < 0.18:                                                # (a woolly hat)
                    d.chord([hx - hr - 0.5, hy - hr - 1.0 * S, hx + hr + 0.5, hy + hr * 0.6], 180, 360,
                            fill=rnd.choice(main))
                elif hat < 0.85:                                              # (hair)
                    d.chord([hx - hr, hy - hr, hx + hr, hy + hr * 0.4], 180, 360, fill=rnd.choice(hairs))
            x += rnd.uniform(11, 14) * S
    _save(im, name)


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
    _save(im, "brick.png")


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
    _save(im, "sky.png")


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
    _save(im, "moors.png")


if __name__ == "__main__":
    pitch(); brick(); sky(); moors()
    crowd("crowd_home.png", [((200, 40, 45), 6), ((235, 235, 235), 2), ((30, 30, 34), 2)], seed=1)
    crowd("crowd_away.png", [((30, 30, 32), 5), ((212, 170, 60), 2), ((200, 40, 45), 1)], seed=2)
    crowd("crowd_mixed.png", [((200, 40, 45), 5), ((235, 235, 235), 2), ((30, 30, 34), 3), ((70, 70, 90), 2)], seed=3)
    print("ok")
