"""
career/faces.py
===============
A face for every player, drawn by the game itself (no image files): the same
player always gets the same face (it comes from his id), and his age shows
(grey hair, lines).

How: the portrait is drawn at 4x size with soft, layered shading (light from
the upper left), then smoothly shrunk - pygame only, nothing to install.

    face_surface(player, size)  -> a pygame Surface (cached)
"""

import math
import random

import pygame

SS = 4                       # drawn this many times bigger, then shrunk
_CACHE = {}

SKIN = [  # (base, weight)
    ((236, 200, 172), 3), ((226, 184, 152), 4), ((206, 160, 124), 3), ((186, 136, 100), 2),
    ((158, 108, 74), 2), ((122, 80, 52), 2), ((92, 60, 40), 2), ((70, 46, 32), 1),
]
HAIR = [((22, 18, 16), 5), ((48, 34, 24), 4), ((82, 56, 36), 3), ((120, 86, 54), 2), ((168, 132, 84), 1),
        ((206, 172, 112), 1), ((132, 62, 34), 1)]
EYES = [((72, 46, 28), 5), ((104, 72, 40), 3), ((96, 110, 70), 1), ((70, 110, 150), 2), ((110, 130, 140), 1)]
STYLES = [("short", 5), ("crop", 4), ("buzz", 3), ("side", 3), ("curly", 2), ("slick", 2), ("long", 1)]
BEARDS = [("none", 6), ("stubble", 5), ("short", 2), ("goatee", 1)]


def _pick(rng, items):
    total = sum(w for _, w in items)
    x = rng.random() * total
    for v, w in items:
        x -= w
        if x <= 0:
            return v
    return items[-1][0]


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _shade(c, f):
    """f < 1 darker, > 1 lighter."""
    if f < 1:
        return tuple(int(v * f) for v in c)
    return tuple(int(v + (255 - v) * (f - 1)) for v in c)


def looks(p):
    """His features (the same every time for the same player)."""
    rng = random.Random(f"face:{p['id']}:{p['Name']}")
    skin = _pick(rng, SKIN)
    dark = sum(skin) / 3 < 140
    hair = _pick(rng, HAIR[:3] if dark else HAIR)
    eye = _pick(rng, EYES[:2] if dark else EYES)
    style = _pick(rng, STYLES if not dark else STYLES + [("curly", 6), ("buzz", 4)])
    age = int(p.get("Age", 25))
    grey = max(0.0, min(0.85, (age - 31) * 0.09 + rng.uniform(-0.15, 0.1)))
    return {
        "skin": skin, "hair": hair, "eye": eye, "style": style, "beard": _pick(rng, BEARDS), "grey": grey,
        "age": age,
        "face_w": rng.uniform(0.92, 1.08), "jaw": rng.uniform(0.80, 1.0), "chin": rng.uniform(0.9, 1.1),
        "face_h": rng.uniform(0.95, 1.05), "eye_gap": rng.uniform(0.95, 1.06), "eye_size": rng.uniform(0.9, 1.08),
        "brow": rng.uniform(0.7, 1.3), "brow_tilt": rng.uniform(-0.06, 0.08), "nose_w": rng.uniform(0.85, 1.25),
        "nose_l": rng.uniform(0.92, 1.1), "lips": rng.uniform(0.8, 1.25), "mouth_w": rng.uniform(0.9, 1.1),
        "ears": rng.uniform(0.9, 1.1), "seed": rng.randrange(1 << 30),
        "shirt": tuple(rng.randrange(40, 200) for _ in range(3)),
    }


# ---------------------------------------------------------------------------
# Real photos: the face pool (faces/pool.json) - made-up men, turned into
# photos with ChatGPT and saved as faces/photos/pool_0001.png etc.  A player
# gets one from his age group that nobody else at his club has, and keeps it
# for good (p["face"]).  No photo for him yet: the drawn face.
# ---------------------------------------------------------------------------
import json
import os

PHOTO_DIR = os.path.join("faces", "photos")
POOL_FILE = os.path.join("faces", "pool.json")
BLACK_SHIRT = (26, 26, 28)
PHOTO_SIZE = 256                  # stored this big (bigger files are shrunk once; the original is kept aside)
_PHOTOS = None                    # {"pool_0001": path}
_POOL = None
_PHOTO_CACHE = {}


def band(age):
    return "young" if age < 24 else "prime" if age < 31 else "senior"


def photos(rescan=False):
    """{face id: file} for every photo in faces/photos."""
    global _PHOTOS
    if _PHOTOS is None or rescan:
        _PHOTOS = {}
        if os.path.isdir(PHOTO_DIR):
            for f in sorted(os.listdir(PHOTO_DIR)):
                low = f.lower()
                if low.startswith("pool_") and low.rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "webp"):
                    _PHOTOS.setdefault(low[:9], os.path.join(PHOTO_DIR, f))
    return _PHOTOS


def pool():
    global _POOL
    if _POOL is None:
        try:
            _POOL = {e["face"]: e for e in json.load(open(POOL_FILE))}
        except (OSError, ValueError):
            _POOL = {}
    return _POOL


def _photo(fid):
    """The photo as a square PHOTO_SIZE surface (shrinking the file the first time if it's big)."""
    if fid in _PHOTO_CACHE:
        return _PHOTO_CACHE[fid]
    path = photos().get(fid)
    img = None
    if path:
        try:
            img = pygame.image.load(path)
            w, h = img.get_size()
            m = min(w, h)
            img = img.subsurface(((w - m) // 2, (h - m) // 2, m, m)).copy()
            if m > PHOTO_SIZE * 1.5:
                img = pygame.transform.smoothscale(img, (PHOTO_SIZE, PHOTO_SIZE))
                try:                                          # keep the big original aside, save the small one
                    keep = os.path.join(PHOTO_DIR, "originals")
                    os.makedirs(keep, exist_ok=True)
                    os.replace(path, os.path.join(keep, os.path.basename(path)))
                    small = os.path.join(PHOTO_DIR, fid + ".png")
                    pygame.image.save(img, small)
                    _PHOTOS[fid] = small
                except OSError:
                    pass
            if img.get_width() != PHOTO_SIZE:
                img = pygame.transform.smoothscale(img, (PHOTO_SIZE, PHOTO_SIZE))
            img = _head_and_neck(img)                         # (framing done in memory; the file stays as made)
        except (pygame.error, OSError, ValueError):
            img = None
    _PHOTO_CACHE[fid] = img
    return img


def _head_and_neck(img):
    """Every photo framed the same way - head and neck, black shirt - so a face suits any club.
    A photo showing shoulders in a coloured shirt (the early ones) is cropped in a little and the
    shirt recoloured black (pixels near the shirt's colour, below the chin); a tight one with a
    black collar is left alone."""
    m = img.get_width()
    band = pygame.transform.smoothscale(img.subsurface((int(m * 0.25), int(m * 0.92), int(m * 0.5), int(m * 0.07))), (1, 1))
    shirt = band.get_at((0, 0))[:3]
    if max(shirt) < 38 and max(shirt) - min(shirt) < 14:
        return img                                         # (already a dark collar at the bottom)
    img = img.convert(24) if img.get_bitsize() not in (24, 32) else img.copy()
    sr, sg, sb = shirt
    st = float(sr + sg + sb) or 1.0
    hr, hg, hb = sr / st, sg / st, sb / st                # the shirt's hue (colour, not brightness)
    for y in range(int(m * 0.78), m):                     # below the chin: shirt-coloured pixels go black
        for x in range(m):
            r, g, b = img.get_at((x, y))[:3]
            t = float(r + g + b) or 1.0
            near_hue = (r / t - hr) ** 2 + (g / t - hg) ** 2 + (b / t - hb) ** 2 < 0.08 ** 2
            if near_hue and (r - sr) ** 2 + (g - sg) ** 2 + (b - sb) ** 2 < 130 ** 2:
                v = int((r + g + b) / 3 * 0.22) + 8          # (keeping the folds' light and shade, faintly)
                img.set_at((x, y), (v, v, v + 2))
            elif y > m * 0.85:                               # (whatever's left of the shirt: darkened, greyed)
                k = min(1.0, (y - m * 0.85) / (m * 0.05))
                v = (r + g + b) / 3
                f = 1 - 0.75 * k
                img.set_at((x, y), tuple(int((c * (1 - k) + v * k) * f) for c in (r, g, b)))
    x, y, size = int(m * 0.075), int(m * 0.05), int(m * 0.85)
    return img.subsurface((x, y, size, size)).copy()


def assign(p, club_players=()):
    """His place in the face pool (for good): one from his age group that nobody else at his club has.
    Until that face's photo exists, he's shown as its drawing - so adding the photo just turns it real."""
    if p.get("face") in pool():
        return p["face"]
    if not pool():
        return None
    taken = {q.get("face") for q in club_players if q is not p}
    b = band(int(p.get("Age", 25)))
    free = [f for f, e in pool().items() if e["band"] == b and f not in taken] or [f for f in pool() if f not in taken]
    if not free:
        return None
    free.sort(key=lambda f: random.Random(f"{p['id']}:{p['Name']}:{f}").random())
    p["face"] = free[0]
    return p["face"]


# ---------------------------------------------------------------------------
# NewGAN faces (faces/newgan): 3,000 made-up footballers picked from the NewGAN
# facepack, shrunk to 128px, sorted by region (faces/newgan/faces.json - which
# ones look 30-plus is listed there too, and broken ones are left out).
#
# A player gets one for good (p["face"] = "ng:<region>:<number>"): the region
# from where he's from - English league: a mix like the real EFL (about a third
# of EFL players are Black - Black Footballers Partnership, 2023); Spain: Spanish
# faces for Spanish names, Italian / Central European / Balkan for the other EU
# names, South American and African for the non-EU men - and an older-looking
# face if he's 30 or over when he gets it.  Nobody in the world shares one
# (bind() learns who has what when a career is loaded).  Local non-league sides
# (friendlies) borrow faces without keeping them.  No faces/newgan folder: the
# old pool photos / drawings, as before.
# ---------------------------------------------------------------------------
NG_DIR = os.path.join("faces", "newgan")
NG_FILE = os.path.join(NG_DIR, "faces.json")
OLD_AGE = 30
MIX = {
    "england": {"Caucasian": 56, "African": 32, "CentralEuropean": 3, "Scandinavian": 2, "Italmed": 2, "MENA": 2,
                "SAMed": 1.5, "MESA": 1, "Asian": 0.5},
    "spain": {"SpanMed": 88, "African": 5, "SAMed": 4, "SouthAmerican": 3},
    "spain_eu": {"Italmed": 45, "CentralEuropean": 25, "YugoGreek": 20, "EECA": 10},
    "spain_non_eu": {"SouthAmerican": 60, "African": 30, "SAMed": 10},
    "germany": {"CentralEuropean": 62, "Caucasian": 12, "African": 12, "EECA": 8, "YugoGreek": 6},
    "italy": {"Italmed": 72, "CentralEuropean": 8, "African": 10, "SouthAmerican": 6, "YugoGreek": 4},
}
_NG = None
_USED = set()
_BACKDROP = {}


def ng():
    """The NewGAN set: {"regions": {region: [numbers]}, "old": {region: set}} - or None if it's not there."""
    global _NG
    if _NG is None:
        try:
            d = json.load(open(NG_FILE))
            _NG = {"regions": d["regions"], "old": {r: set(v) for r, v in d.get("old", {}).items()}}
        except (OSError, ValueError, KeyError):
            _NG = False
    return _NG or None


def _group(p, club):
    cid = club.get("id") if club else None
    from career import spain, friendlies, foreign
    cfg = foreign.league_of_id(cid) if cid is not None else None
    if cfg is not None:
        return "germany" if cfg.key == "de" else "italy"
    if cid is not None and spain.is_spanish(cid) and cid < friendlies.LOCAL_ID:
        if p.get("non_eu"):
            return "spain_non_eu"
        return "spain_eu" if p["Name"].split(" ")[0] in spain.FIRST_EU else "spain"
    return "england"


def _ng_pick(p, club, reserve=True):
    """Choose his NewGAN face (stable for him: seeded by who he is)."""
    data = ng()
    rng = random.Random(f"ng:{p['Name']}:{p.get('id')}:{p.get('Age')}")
    mix = MIX[_group(p, club)]
    regions = list(mix)
    order = sorted(regions, key=lambda r: -rng.random() ** (1.0 / mix[r]))   # (a weighted draw, the rest as fallbacks)
    old = int(p.get("Age", 25)) >= OLD_AGE
    for r in order:
        nums = data["regions"].get(r, [])
        olds = data["old"].get(r, set())
        for want_old in ((True, False) if old else (False,)):
            free = [n for n in nums if (n in olds) == want_old and (not reserve or f"ng:{r}:{n}" not in _USED)]
            if free:
                key = f"ng:{r}:{rng.choice(free)}"
                if reserve:
                    _USED.add(key)
                return key
    if reserve:                                  # (all 3,000 taken - years in: share one, it's a big world)
        return _ng_pick(p, club, reserve=False)
    return None


def _all_players(career):
    for c in career.get("clubs", []):
        for p in c.get("players", []):
            yield p, c
    for c in (career.get("spain") or {}).get("clubs", []):
        for p in c.get("players", []):
            yield p, c
    for d in (career.get("leagues") or {}).values():          # (Germany, Italy - career/foreign.py)
        for c in d.get("clubs", []):
            for p in c.get("players", []):
                yield p, c
    for k in ("free_agents", "abroad"):
        c = career.get(k)
        if isinstance(c, dict):
            for p in c.get("players", []):
                yield p, c


def bind(career):
    """A career is loaded: note every face in use, then give everyone without a NewGAN face one."""
    if not ng() or not career:
        return 0
    _USED.clear()
    everyone = list(_all_players(career))
    for p, c in everyone:
        if str(p.get("face", "")).startswith("ng:"):
            _USED.add(p["face"])
    n = 0
    for p, c in everyone:
        if not str(p.get("face", "")).startswith("ng:"):
            key = _ng_pick(p, c)
            if key:
                p["face"] = key
                n += 1
    return n


def _ng_image(key):
    if key in _PHOTO_CACHE:
        return _PHOTO_CACHE[key]
    img = None
    try:
        _, r, n = key.split(":")
        img = pygame.image.load(os.path.join(NG_DIR, r, f"{n}.png"))
        img = img.convert_alpha() if pygame.display.get_surface() else img
    except (ValueError, pygame.error, OSError):
        img = None
    _PHOTO_CACHE[key] = img
    return img


def _backdrop(size):
    """The square behind a NewGAN face (they come cut out): a dark, softly lit tile."""
    if size not in _BACKDROP:
        s = pygame.Surface((size, size))
        for y in range(size):
            t = y / max(1, size - 1)
            s.fill((int(58 - 22 * t), int(64 - 22 * t), int(70 - 22 * t)), (0, y, size, 1))
        _BACKDROP[size] = s
    return _BACKDROP[size]


def _ng_surface(p, size, club):
    key = p.get("face") if str(p.get("face", "")).startswith("ng:") else None
    if key is None:
        local = club is not None and club.get("id", 0) >= 900          # (a local side: borrowed, not kept)
        key = _ng_pick(p, club, reserve=not local)
        if key and not local:
            p["face"] = key
    if key is None:
        return None
    ck = (key, size)
    if ck not in _CACHE:
        img = _ng_image(key)
        if img is None:
            return None
        out = _backdrop(size).copy()
        out.blit(pygame.transform.smoothscale(img, (size, size)), (0, 0))
        _CACHE[ck] = out
    return _CACHE[ck]


def face_surface(p, size=128, shirt=None, club=None):
    """His face: his NewGAN face (faces/newgan) - or, without that folder, the photo of his pool
    face if it's been made, else that face's drawing; a player outside the pool (no club given)
    gets his own drawing.  club: so no two team-mates share a face."""
    if ng():
        img = _ng_surface(p, size, club)
        if img is not None:
            return img
    fid = p.get("face") if p.get("face") in pool() else (assign(p, club["players"]) if club else None)
    if fid and fid in photos():
        key = (fid, size)
        if key not in _CACHE:
            img = _photo(fid)
            if img is not None:
                _CACHE[key] = pygame.transform.smoothscale(img, (size, size))
        if key in _CACHE:
            return _CACHE[key]
    shirt = BLACK_SHIRT                                    # (one look for every face: it suits any club)
    if fid:
        e = pool()[fid]
        return drawn_face({"id": e["seed_id"], "Name": e["seed_name"], "Age": e["age"]}, size, shirt)
    return drawn_face(p, size, shirt)


def drawn_face(p, size=128, shirt=None):
    key = (p["id"], p["Name"], int(p.get("Age", 25)) // 2, size, shirt)
    if key not in _CACHE:
        lk = looks(p)
        if shirt:
            lk["shirt"] = shirt
        big = draw(lk, size * SS)
        _CACHE[key] = pygame.transform.smoothscale(big, (size, size))
    return _CACHE[key]


# ---------------------------------------------------------------------------
# Drawing (everything in units of S, the canvas size: 1000 = the full width)
# ---------------------------------------------------------------------------
BLUR = {2: 4, 3: 8, 4: 12, 5: 26, 6: 34, 7: 40, 8: 46, 10: 60}     # softness -> blur size (1000 = full width)


def _soft(S, k, fn):
    """Draw `fn(surface, P, u)`, then blur it (k = how soft): shrink in halves to a tiny size and
    grow back in doubles - each step is a smooth (bilinear) resize, so edges melt away."""
    blur = BLUR.get(k, k * 6)
    s0 = min(S, 500)
    small = pygame.Surface((s0, s0), pygame.SRCALPHA)
    us = s0 / 1000.0
    fn(small, lambda x, y: (int(x * us), int(y * us)), us)
    tiny = max(6, int(1000 / blur))
    cur = small
    size = s0
    while size // 2 >= tiny:
        size //= 2
        cur = pygame.transform.smoothscale(cur, (size, size))
    if size != tiny and tiny < size:
        size = tiny
        cur = pygame.transform.smoothscale(cur, (size, size))
    while size * 2 < S:
        size *= 2
        cur = pygame.transform.smoothscale(cur, (size, size))
    return pygame.transform.smoothscale(cur, (S, S))


def _clip(layer, mask):
    layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return layer


def draw(lk, S):
    rng = random.Random(lk["seed"])
    surf = pygame.Surface((S, S), pygame.SRCALPHA)
    u = S / 1000.0
    skin = lk["skin"]
    lightness = sum(skin) / 765

    def P(x, y):
        return (int(x * u), int(y * u))

    # background: a soft studio backdrop
    surf.blit(_soft(S, 10, lambda s_, Q, us: [
        s_.fill((52, 60, 72)),
        pygame.draw.circle(s_, (128, 138, 152), Q(400, 330), int(380 * us)),
        pygame.draw.circle(s_, (150, 160, 172), Q(380, 300), int(200 * us))]), (0, 0))

    # geometry
    cx = 500
    fw = 190 * lk["face_w"]                 # half width at the cheekbones
    top = 150 - 20 * (lk["face_h"] - 1)
    chin = 790 + 30 * (lk["chin"] - 1)
    H = chin - top
    eye_y = top + 0.50 * H
    brow_y = eye_y - 0.08 * H
    nose_y = eye_y + 0.205 * H * lk["nose_l"]
    mouth_y = eye_y + 0.32 * H
    hairline = top + 0.155 * H

    # shoulders and shirt (lit from the left)
    sh = lk["shirt"]
    body = [P(60, 1000), P(130, 880), P(290, 812), P(420, 786), P(580, 786), P(710, 812), P(870, 880), P(940, 1000)]
    pygame.draw.polygon(surf, _shade(sh, 0.85), body)
    bl = pygame.Surface((S, S), pygame.SRCALPHA)
    pygame.draw.polygon(bl, (255, 255, 255, 255), body)
    surf.blit(_clip(_soft(S, 6, lambda s_, Q, us: [
        pygame.draw.ellipse(s_, (*_shade(sh, 1.3), 150), pygame.Rect(Q(120, 820), Q(330, 300))),
        pygame.draw.ellipse(s_, (*_shade(sh, 0.55), 160), pygame.Rect(Q(620, 840), Q(330, 260))),
        pygame.draw.ellipse(s_, (0, 0, 0, 120), pygame.Rect(Q(380, 770), Q(240, 90)))]), bl), (0, 0))
    collar = [P(392, 790), P(500, 900), P(608, 790), P(572, 786), P(500, 858), P(428, 786)]
    pygame.draw.polygon(surf, _shade(sh, 0.62), collar)

    # neck (shadowed under the jaw)
    nw = 0.56 * fw
    neck = [P(cx - nw, chin - 140), P(cx + nw, chin - 140), P(cx + nw * 1.06, 820), P(500, 860), P(cx - nw * 1.06, 820)]
    pygame.draw.polygon(surf, _shade(skin, 0.9), neck)
    nm = pygame.Surface((S, S), pygame.SRCALPHA)
    pygame.draw.polygon(nm, (255, 255, 255, 255), neck)
    surf.blit(_clip(_soft(S, 8, lambda s_, Q, us: [
        pygame.draw.ellipse(s_, (*_shade(skin, 0.45), 200), pygame.Rect(Q(cx - nw * 1.3, chin - 120), Q(nw * 2.6, 150))),
        pygame.draw.rect(s_, (*_shade(skin, 0.6), 120), pygame.Rect(Q(cx + nw * 0.3, chin - 140), Q(nw, 300)))]), nm), (0, 0))

    # ears
    ear_h = 0.17 * H * lk["ears"]
    for side in (-1, 1):
        r = pygame.Rect(0, 0, int(56 * u), int(ear_h * u))
        r.center = P(cx + side * (fw + 6), eye_y + 0.07 * H)
        pygame.draw.ellipse(surf, _shade(skin, 0.92 if side < 0 else 0.78), r)
        r2 = r.inflate(-int(24 * u), -int(30 * u))
        r2.x += int(side * 3 * u)
        pygame.draw.ellipse(surf, _shade(skin, 0.68), r2)

    # the head: skull + cheeks + jaw, narrowing to the chin
    outline = []
    for i in range(180):
        t = 2 * math.pi * i / 180
        x, y = math.cos(t), math.sin(t)
        if y < 0:
            px = cx + fw * 1.02 * x
            py = eye_y + (eye_y - top) * y
        else:
            narrow = 1 - 0.20 * (2.0 - lk["jaw"]) * (y ** 1.3) - 0.36 * (y ** 5.5)
            px = cx + fw * math.copysign(abs(x) ** 0.75, x) * narrow
            py = eye_y + (chin - eye_y) * (abs(y) ** 0.9)
        outline.append((px, py))
    head = [P(x, y) for x, y in outline]
    mask = pygame.Surface((S, S), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), head)
    face = pygame.Surface((S, S), pygame.SRCALPHA)
    face.fill((*skin, 255))

    eg = 0.43 * fw * lk["eye_gap"]
    ew, eh = 0.36 * fw * lk["eye_size"], 0.13 * fw * lk["eye_size"]
    nwid = 0.23 * fw * lk["nose_w"]
    mw = 0.36 * fw * lk["mouth_w"]
    dark, light = _shade(skin, 0.55), _shade(skin, 1.22)

    # broad light and shade (light from the upper left)
    def broad(s_, Q, us):
        pygame.draw.polygon(s_, (*dark, 150), [Q(cx + fw * 0.55, top), Q(cx + fw * 1.4, top), Q(cx + fw * 1.4, chin + 50),
                                              Q(cx + fw * 0.15, chin + 50), Q(cx + fw * 0.35, eye_y)])
        pygame.draw.ellipse(s_, (*light, 120), pygame.Rect(Q(cx - fw * 0.95, top + 30), Q(fw * 1.2, H * 0.55)))
        for i in range(0, 180, 2):                                  # the edges turn away from the light
            x, y = outline[i]
            pygame.draw.circle(s_, (*_shade(skin, 0.62), 60), Q(x, y), int(55 * us))
        pygame.draw.ellipse(s_, (*_shade(skin, 0.6), 110), pygame.Rect(Q(cx - fw * 0.9, chin - 90), Q(fw * 1.8, 140)))
    face.blit(_soft(S, 7, broad), (0, 0))

    # structure: temples, cheekbones, eye sockets, nose, mouth, chin
    def structure(s_, Q, us):
        for side in (-1, 1):
            k = 1.0 if side > 0 else 0.6
            pygame.draw.ellipse(s_, (*_shade(skin, 0.6), int(90 * k)),
                                pygame.Rect(Q(cx + side * fw * 0.78 - 50, eye_y + 0.13 * H), Q(100, 0.16 * H)))  # under cheekbone
            pygame.draw.ellipse(s_, (*_shade(skin, 1.25), int(70 / k)),
                                pygame.Rect(Q(cx + side * fw * 0.55 - 55, eye_y + 0.05 * H), Q(110, 50)))         # cheekbone light
            pygame.draw.ellipse(s_, (*_shade(skin, 0.55), 140),
                                pygame.Rect(Q(cx + side * eg - ew * 0.75, eye_y - eh * 2.6), Q(ew * 1.5, eh * 3.6)))  # socket
            pygame.draw.ellipse(s_, (*_shade(skin, 0.65), int(80 * k)),
                                pygame.Rect(Q(cx + side * fw * 0.85 - 40, top + 0.2 * H), Q(80, 0.22 * H)))      # temple
        pygame.draw.ellipse(s_, (*_shade(skin, 1.25), 110), pygame.Rect(Q(cx - 90, top + 0.1 * H), Q(160, 0.22 * H)))  # brow ridge
        pygame.draw.ellipse(s_, (*_shade(skin, 0.5), 130), pygame.Rect(Q(cx - nwid * 1.05, nose_y - 14), Q(nwid * 2.1, 34)))  # under the nose
        pygame.draw.ellipse(s_, (*_shade(skin, 0.62), 110), pygame.Rect(Q(cx - 18, nose_y + 10), Q(36, mouth_y - nose_y - 22)))  # philtrum
        pygame.draw.ellipse(s_, (*_shade(skin, 0.5), 140), pygame.Rect(Q(cx - mw * 0.7, mouth_y + 18 * lk["lips"] + 8), Q(mw * 1.4, 40)))  # under lip
        pygame.draw.ellipse(s_, (*_shade(skin, 1.22), 110), pygame.Rect(Q(cx - 60, chin - 85), Q(95, 50)))       # chin light
        for side in (-1, 1):                                                                                    # beside the mouth
            pygame.draw.ellipse(s_, (*_shade(skin, 0.68), 70), pygame.Rect(Q(cx + side * (mw + 18) - 16, mouth_y - 40), Q(32, 70)))
        pygame.draw.ellipse(s_, (190, 90, 80, 30), pygame.Rect(Q(cx - fw * 0.75, eye_y + 0.1 * H), Q(110, 70)))  # warmth
        pygame.draw.ellipse(s_, (190, 90, 80, 22), pygame.Rect(Q(cx + fw * 0.35, eye_y + 0.1 * H), Q(110, 70)))
    face.blit(_soft(S, 5, structure), (0, 0))

    # the nose: its shadowed side, the light down the bridge and on the tip, the shadow beneath
    def nose(s_, Q, us):
        pygame.draw.polygon(s_, (*_shade(skin, 0.5), 190), [Q(cx + 14, eye_y - 10), Q(cx + nwid * 0.75, nose_y - 34),
                                                            Q(cx + nwid * 1.05, nose_y - 4), Q(cx + nwid * 0.5, nose_y + 2),
                                                            Q(cx + 22, nose_y - 46)])
        pygame.draw.polygon(s_, (*_shade(skin, 0.7), 110), [Q(cx - 16, eye_y - 6), Q(cx - nwid * 0.7, nose_y - 34),
                                                            Q(cx - nwid * 0.95, nose_y - 6), Q(cx - 20, nose_y - 46)])
        pygame.draw.line(s_, (*_shade(skin, 1.3), 190), Q(cx - 4, eye_y + 2), Q(cx - 8, nose_y - 44), max(1, int(16 * us)))
        pygame.draw.ellipse(s_, (*_shade(skin, 1.32), 200), pygame.Rect(Q(cx - 28, nose_y - 60), Q(46, 38)))
        pygame.draw.ellipse(s_, (*_shade(skin, 0.42), 200), pygame.Rect(Q(cx - nwid * 0.8, nose_y - 6), Q(nwid * 1.6, 20)))
    face.blit(_soft(S, 4, nose), (0, 0))

    # nostrils and wings (soft but more defined)
    def nostrils(s_, Q, us):
        for side in (-1, 1):
            pygame.draw.ellipse(s_, (*_shade(skin, 0.3), 200), pygame.Rect(Q(cx + side * nwid * 0.48 - 15, nose_y - 14), Q(30, 13)))
            pygame.draw.arc(s_, (*_shade(skin, 0.5), 110), pygame.Rect(Q(cx + side * nwid - 22, nose_y - 40), Q(44, 44)),
                            math.pi * (0.85 if side < 0 else -0.55), math.pi * (1.35 if side < 0 else 0.15), max(1, int(8 * us)))
    face.blit(_soft(S, 3, nostrils), (0, 0))

    # eyes
    for side in (-1, 1):
        _eye(face, u, cx + side * eg, eye_y, ew, eh, side, lk, skin)

    # brows: a soft tapered shape, then fine hairs
    bc = _shade(_mix(lk["hair"], (150, 150, 150), lk["grey"] * 0.5), 0.8)
    bt = lk["brow"]
    for side in (-1, 1):
        x0, x1 = cx + side * (eg - ew * 0.62), cx + side * (eg + ew * 0.72)
        pts_top, pts_bot = [], []
        for i in range(21):
            t = i / 20
            x = x0 + (x1 - x0) * t
            arch = math.sin(math.pi * min(1.0, t * 1.1)) * 18 - t * 40 * lk["brow_tilt"]
            thick = (1 - t) * 15 * bt + 6
            pts_top.append((x, brow_y - arch - thick))
            pts_bot.append((x, brow_y - arch + thick * 0.5))
        poly = pts_top + pts_bot[::-1]
        face.blit(_soft(S, 3, lambda s_, Q, us, poly=poly: pygame.draw.polygon(s_, (*bc, int(150 + 40 * bt)), [Q(x, y) for x, y in poly])), (0, 0))
        hairs = pygame.Surface((S, S), pygame.SRCALPHA)
        for _ in range(int(90 * bt)):
            t = rng.random()
            i = int(t * 20)
            xa, ya = pts_top[i]
            xb, yb = pts_bot[i]
            k = rng.random()
            x, y = xa + (xb - xa) * k, ya + (yb - ya) * k
            L = rng.uniform(10, 18)
            ang = (0.25 + rng.uniform(-0.2, 0.2)) * (1 - t)
            pygame.draw.line(hairs, (*_shade(bc, 0.8), 200), P(x, y), P(x + side * L * math.cos(ang), y - L * math.sin(ang)),
                             max(1, int(3 * u)))
        face.blit(hairs, (0, 0))

    # mouth
    lipc = _shade(_mix(skin, (160, 72, 72), 0.38 if lightness > 0.55 else 0.18), 0.92)
    lu, ll = 9 * lk["lips"], 15 * lk["lips"]
    upper = [P(cx - mw, mouth_y)]
    for i in range(1, 30):
        t = i / 30
        bow = math.sin(math.pi * t) ** 0.7 * lu - (5 if abs(t - 0.5) < 0.06 else 0)
        upper.append(P(cx - mw + 2 * mw * t, mouth_y - bow))
    upper.append(P(cx + mw, mouth_y))
    lower = [P(cx - mw, mouth_y)] + [P(cx - mw + 2 * mw * i / 30, mouth_y + math.sin(math.pi * i / 30) ** 0.7 * ll)
                                      for i in range(1, 30)] + [P(cx + mw, mouth_y)]
    face.blit(_soft(S, 2, lambda s_, Q, us: [
        pygame.draw.polygon(s_, (*_shade(lipc, 0.82), 235), [(int(x / u * us), int(y / u * us)) for x, y in upper]),
        pygame.draw.polygon(s_, (*lipc, 225), [(int(x / u * us), int(y / u * us)) for x, y in lower])]), (0, 0))
    face.blit(_soft(S, 3, lambda s_, Q, us: [
        pygame.draw.ellipse(s_, (255, 255, 255, 55), pygame.Rect(Q(cx - mw * 0.4, mouth_y + ll * 0.25), Q(mw * 0.55, ll * 0.35))),
        pygame.draw.lines(s_, (*_shade(lipc, 0.4), 230), False,
                          [Q(cx - mw - 6, mouth_y - 3)] + [Q(cx - mw + 2 * mw * i / 10, mouth_y + math.sin(math.pi * i / 10) * 3)
                                                          for i in range(11)] + [Q(cx + mw + 6, mouth_y - 3)], max(1, int(7 * us)))]), (0, 0))

    # age: lines
    if lk["age"] >= 29:
        k = min(1.0, (lk["age"] - 28) / 8)
        face.blit(_soft(S, 3, lambda s_, Q, us: [
            [pygame.draw.arc(s_, (*_shade(skin, 0.55), int(120 * k)),
                             pygame.Rect(Q(cx + side * nwid * 1.5 - 70, nose_y - 40), Q(140, 170)),
                             math.pi * (0.55 if side < 0 else -0.05), math.pi * (1.05 if side < 0 else 0.45), max(1, int(6 * us)))
             for side in (-1, 1)],
            [pygame.draw.arc(s_, (*_shade(skin, 0.65), int(90 * k)), pygame.Rect(Q(cx - fw * 0.5, brow_y - 80 - j * 26), Q(fw, 60)),
                             0.35, math.pi - 0.35, max(1, int(5 * us))) for j in range(2)]]), (0, 0))

    # stubble / beard
    beard = lk["beard"]
    if beard != "none":
        hc = _mix(lk["hair"], (170, 170, 170), lk["grey"])

        def zone(x, y):
            if beard == "goatee":
                return abs(x - cx) < mw * 1.1 and y > nose_y + 10
            if y < mouth_y - 35 and abs(x - cx) < fw * 0.6:
                return False
            if y < nose_y + 15:
                return False
            return y > eye_y + 0.18 * H
        shadow = _soft(S, 5, lambda s_, Q, us: [pygame.draw.circle(s_, (*hc, {"stubble": 45, "short": 110, "goatee": 100}[beard]), Q(x, y), int(24 * us))
                                                for x in range(int(cx - fw), int(cx + fw), 14) for y in range(int(nose_y), int(chin + 20), 14)
                                                if zone(x, y)])
        face.blit(shadow, (0, 0))
        dots = pygame.Surface((S, S), pygame.SRCALPHA)
        n = {"stubble": 2200, "short": 4200, "goatee": 1800}[beard]
        for _ in range(n):
            x, y = rng.uniform(cx - fw, cx + fw), rng.uniform(nose_y, chin + 15)
            if not zone(x, y) or (abs(x - cx) < mw and abs(y - mouth_y) < ll * 0.8):
                continue
            pygame.draw.circle(dots, (*_shade(hc, 0.8), 150 if beard != "stubble" else 90), P(x, y), max(1, int(rng.uniform(2, 3.5) * u)))
        face.blit(dots, (0, 0))

    surf.blit(_clip(face, mask), (0, 0))
    _hair(surf, u, rng, lk, cx, fw, top, hairline, eye_y, outline, mask)
    return surf


def _eye(face, u, ex, ey, ew, eh, side, lk, skin):
    S = face.get_width()

    def P(x, y):
        return (int(x * u), int(y * u))
    almond = []
    for i in range(41):
        t = i / 40
        lift = 0.2 * side * (t - 0.5)
        almond.append((ex - ew / 2 + ew * t, ey - math.sin(math.pi * t) ** 0.85 * eh - lift * eh))
    for i in range(40, -1, -1):
        t = i / 40
        almond.append((ex - ew / 2 + ew * t, ey + math.sin(math.pi * t) ** 1.2 * eh * 0.6))
    ap = [P(x, y) for x, y in almond]
    e = pygame.Surface((S, S), pygame.SRCALPHA)
    pygame.draw.polygon(e, _mix((228, 222, 214), skin, 0.15), ap)
    ir = eh * 0.98
    ic = lk["eye"]
    iy = ey - eh * 0.08
    for i in range(12, 0, -1):
        pygame.draw.circle(e, _mix(_shade(ic, 0.55), _shade(ic, 1.3), (i / 12) * 0.8), P(ex, iy), int(ir * i / 12 * u))
    pygame.draw.circle(e, _shade(ic, 0.4), P(ex, iy), int(ir * u), max(1, int(4 * u)))
    pygame.draw.circle(e, (10, 8, 8), P(ex, iy), int(ir * 0.42 * u))
    e.blit(_soft(S, 4, lambda s_, Q, us: pygame.draw.ellipse(s_, (0, 0, 0, 150), pygame.Rect(Q(ex - ew / 2, ey - eh * 1.4), Q(ew, eh * 1.1)))), (0, 0))
    pygame.draw.circle(e, (255, 255, 255), P(ex - ir * 0.32, iy - ir * 0.32), max(1, int(ir * 0.17 * u)))
    m = pygame.Surface((S, S), pygame.SRCALPHA)
    pygame.draw.polygon(m, (255, 255, 255, 255), ap)
    face.blit(_clip(e, m), (0, 0))
    up = ap[:41]
    face.blit(_soft(S, 2, lambda s_, Q, us: [
        pygame.draw.lines(s_, (26, 20, 18, 255), False, [(int(x / u * us), int(y / u * us)) for x, y in up], max(1, int(9 * us))),
        pygame.draw.lines(s_, (*_shade(skin, 0.6), 160), False,
                          [(int(x / u * us), int(y / u * us)) for x, y in ap[41:]], max(1, int(4 * us))),
        pygame.draw.lines(s_, (*_shade(skin, 0.62), 170), False,
                          [(int(x / u * us), int(y / u * us) - int(eh * 0.6 * us)) for x, y in up[5:37]], max(1, int(6 * us)))]), (0, 0))


def _hair(surf, u, rng, lk, cx, fw, top, hairline, eye_y, outline, head_mask):
    S = surf.get_width()

    def P(x, y):
        return (int(x * u), int(y * u))
    style = lk["style"]
    hc = _mix(lk["hair"], (180, 178, 174), lk["grey"])
    temple_y = eye_y - 0.32 * (eye_y - top)
    vol = {"buzz": 4, "crop": 20, "short": 28, "side": 36, "slick": 26, "curly": 62, "long": 46}[style]
    recede = lk["age"] >= 33
    mass = []
    for i in range(91):
        t = math.pi + math.pi * i / 90
        side_k = abs(math.cos(t))                      # (less volume at the sides than on top)
        v = vol * (1 - 0.65 * side_k ** 2)
        x = cx + (fw * 1.02 + v) * math.cos(t)
        y = eye_y + (eye_y - top + vol) * math.sin(t)
        mass.append((x, min(y, temple_y + (150 if style == "long" else 0))))
    front = []
    for i in range(41):
        t = i / 40
        x = cx + fw * 1.03 - 2 * fw * 1.03 * t
        y = hairline + 70 * (abs(t - 0.5) * 2) ** 1.8 + (22 * math.sin(math.pi * t * 2) ** 2 if recede else 0)
        if style == "side" and x < cx - fw * 0.2:
            y -= 14
        front.append((x, min(y, temple_y)))
    poly = mass + front
    hm = _soft(S, 3 if style != "buzz" else 2, lambda s_, Q, us: pygame.draw.polygon(s_, (255, 255, 255, 255), [Q(x, y) for x, y in poly]))
    # the cast shadow on the forehead
    fs = _soft(S, 6, lambda s_, Q, us: pygame.draw.lines(s_, (0, 0, 0, 90), False, [Q(x, y + 14) for x, y in front], max(1, int(30 * us))))
    surf.blit(_clip(fs, head_mask), (0, 0))
    layer = pygame.Surface((S, S), pygame.SRCALPHA)
    if style == "buzz":                                 # clipped to the skull: a shadow of hair, not a cap
        layer.blit(_soft(S, 3, lambda s_, Q, us: pygame.draw.polygon(s_, (*_shade(hc, 0.9), 225), [Q(x, y) for x, y in poly])), (0, 0))
        layer.blit(_soft(S, 6, lambda s_, Q, us: pygame.draw.ellipse(s_, (*_shade(hc, 1.5), 90),
                                                                    pygame.Rect(Q(cx - fw * 0.9, top), Q(fw, (eye_y - top) * 0.5)))), (0, 0))
        for _ in range(12000):
            x, y = rng.uniform(cx - fw - vol, cx + fw + vol), rng.uniform(top - vol, temple_y)
            pygame.draw.circle(layer, (*_shade(hc, 0.7), 160), P(x, y), max(1, int(2.5 * u)))
        surf.blit(_clip(_clip(layer, hm), head_mask), (0, 0))
        return
    base = _shade(hc, 0.8)
    layer.fill((*base, 255))
    layer.blit(_soft(S, 6, lambda s_, Q, us: [
        pygame.draw.ellipse(s_, (*_shade(hc, 1.25), 170), pygame.Rect(Q(cx - fw * 0.95, top - vol), Q(fw * 1.1, (eye_y - top) * 0.6))),
        pygame.draw.ellipse(s_, (*_shade(hc, 0.45), 170), pygame.Rect(Q(cx + fw * 0.35, top), Q(fw * 0.9, eye_y - top))),
        pygame.draw.lines(s_, (*_shade(hc, 0.5), 150), False, [Q(x, y - 8) for x, y in front], max(1, int(24 * us)))]), (0, 0))
    if style == "curly":
        for _ in range(1600):
            x, y = rng.uniform(cx - fw - vol, cx + fw + vol), rng.uniform(top - vol, temple_y)
            c = _shade(hc, rng.uniform(0.6, 1.0) + 0.5 * max(0, (cx - x) / fw) * max(0, (eye_y - y) / (eye_y - top)))
            pygame.draw.circle(layer, c, P(x, y), int(rng.uniform(7, 13) * u), max(1, int(3.5 * u)))
    else:
        n = {"crop": 3500, "short": 3500, "side": 3500, "slick": 3000, "long": 4000}[style]
        for _ in range(n):
            x = rng.uniform(cx - fw - vol, cx + fw + vol)
            y = rng.uniform(top - vol, temple_y + (150 if style == "long" else 0))
            if style == "slick":
                dx, dy = (x - cx) * 0.25, -1.0
            elif style == "side":
                dx, dy = -1.0, 0.35
            elif style == "long":
                dx, dy = (x - cx) * 0.2, 1.0
            else:                                    # crop / short: brushed forward and down
                dx, dy = (x - cx) * 0.012, 1.0
            L = math.hypot(dx, dy) or 1
            L2 = rng.uniform(14, 34) if style != "long" else rng.uniform(40, 90)
            lt = 0.75 + 0.6 * max(0, (cx - x) / fw + 0.3) * max(0, (eye_y - y) / (eye_y - top)) + rng.uniform(-0.15, 0.15)
            c = _shade(hc, lt) if lt != 1 else hc
            pygame.draw.line(layer, (*c, 200), P(x, y), P(x + dx / L * L2, y + dy / L * L2), max(1, int(rng.uniform(2, 4) * u)))
    surf.blit(_clip(layer, hm), (0, 0))
