"""
career/office.py
================
The home screen: your office (office/office.png - Jay's picture, cropped and
scaled to the window).  Click what you need:

    door        -> Continue / Go to match      trophy shelf -> the Board
    whiteboard  -> Tactics (your XI on it)      calendar     -> Calendar (next match circled)
    window      -> Training                     newspaper    -> League table (last result's headline)
    laptop      -> Transfers (window open?)     coffee mug   -> Overview (the old home screen)
    phone       -> Inbox (unread badge)         clipboard    -> Squad (team sheet)
    folders     -> Finances

Hover: the object glows and says what it is.  The bar along the bottom keeps
the next match, your position and Continue.

Spots are in the ORIGINAL picture's pixels (1536 x 1024; CROP_X cut off each
side): a new picture = re-mark these.
"""

import os
import pygame

from career import league, calendar as cal, transfers as trf, clubs as clubs_mod, availability as avail
from config import slots

IMAGE = os.path.join("office", "office.png")
SRC_W, SRC_H, CROP_X = 1536, 1024, 56            # (the picture as generated; office.png = the middle 1424 px)

SPOTS = [  # key, (x1, y1, x2, y2) in the original picture, screen, label
    ("door", (25, 75, 265, 620), None, "Door"),
    ("trophies", (300, 118, 480, 370), "club", "The club"),
    ("board", (518, 86, 948, 380), "tactics", "Tactics"),
    ("calendar", (992, 130, 1166, 312), "calendar", "Calendar"),
    ("window", (1292, 0, 1478, 440), "training", "Training"),
    ("paper", (48, 640, 355, 768), "papers", "The papers"),
    ("laptop", (438, 470, 750, 730), "transfers", "Transfers & social media"),
    ("mug", (782, 620, 880, 720), "overview", "Overview"),
    ("phone", (820, 525, 1022, 640), "inbox", "Inbox"),
    ("folders", (1228, 532, 1488, 692), "finances", "Finances"),
    ("clipboard", (1072, 644, 1344, 784), "squad", "Squad"),
]
PITCH = (542, 106, 924, 360)       # the whiteboard's pitch (own goal on the left)
CAL_GRID = (1000, 177, 1158, 303)  # the calendar's empty grid (7 x 5) - measured from the printed lines
PAPER_QUAD = ((128, 655), (334, 654), (330, 693), (110, 697))   # the headline block in the picture
LAPTOP_QUAD = ((444, 490), (681, 484), (695, 635), (451, 641))   # the laptop display: TL TR BR BL
CLIP_QUAD = ((1089, 673), (1245, 673), (1327, 770), (1137, 771))   # the clipboard's paper: TL TR BR BL
PHONE_BADGE = (1010, 535)

_cache = {}


def _img(size):
    key = ("img", size)
    if key not in _cache:
        if not os.path.exists(IMAGE):
            _cache[key] = None
        else:
            im = pygame.image.load(IMAGE).convert()
            _cache[key] = pygame.transform.smoothscale(im, size) if im.get_size() != size else im
    return _cache[key]


def available(size):
    return _img(size) is not None


def _r(rect, W, H):
    """Original-picture rect -> screen rect."""
    sx, sy = W / (SRC_W - 2 * CROP_X), H / SRC_H
    x1, y1, x2, y2 = rect
    return pygame.Rect(int((x1 - CROP_X) * sx), int(y1 * sy), int((x2 - x1) * sx), int((y2 - y1) * sy))


def _pt(p, W, H):
    sx, sy = W / (SRC_W - 2 * CROP_X), H / SRC_H
    return int((p[0] - CROP_X) * sx), int(p[1] * sy)


def _font(name, size, bold=False):
    key = ("font", name, size, bold)
    if key not in _cache:
        _cache[key] = pygame.font.SysFont(name, size, bold=bold)
    return _cache[key]


def draw(app):
    """The office (returns False if there's no picture - then the old home screen is used)."""
    from career.ui import Button, _Invisible, TEXT, MUTED, ACCENT, LOSS
    W, H = app.size
    im = _img((W, H))
    if im is None:
        return False
    win = app.win
    c = app.career
    mc = c["my_club"]
    club = c["clubs"][mc]
    win.blit(im, (0, 0))
    _whiteboard(app, club, _r(PITCH, W, H))
    _calendar(app, c, _r(CAL_GRID, W, H))
    _newspaper(app, c, mc, [_pt(p, W, H) for p in PAPER_QUAD])
    _laptop(app, c, [_pt(p, W, H) for p in LAPTOP_QUAD])
    _clipboard(app, c, club, [_pt(p, W, H) for p in CLIP_QUAD])
    n = trf.unread(c)
    if n:
        x, y = _pt(PHONE_BADGE, W, H)
        pygame.draw.circle(win, (200, 40, 40), (x, y), 13)
        pygame.draw.circle(win, (255, 255, 255), (x, y), 13, 2)
        t = _font("arial", 15, True).render(str(n) if n < 100 else "99", True, (255, 255, 255))
        win.blit(t, t.get_rect(center=(x, y)))
    # hover + clicks
    mouse = pygame.mouse.get_pos()
    hover = None
    for key, rect, screen, label in SPOTS:
        r = _r(rect, W, H)
        r = r.clip(pygame.Rect(0, 0, W, H - 64))
        action = (app.continue_to_match if key == "door" else
                  (lambda s=screen: app._menu(s)))
        app.buttons.append(_Invisible(r, action))
        if r.collidepoint(mouse) and hover is None:
            hover = (key, r, label)
    if hover:
        key, r, label = hover
        glow = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(glow, (255, 230, 150, 38), glow.get_rect(), border_radius=10)
        pygame.draw.rect(glow, (255, 230, 150, 170), glow.get_rect(), 2, border_radius=10)
        win.blit(glow, r.topleft)
        if key == "door":
            label = _door_label(c)
        detail = _detail(app, c, club, key)
        _tooltip(app, label, detail, mouse, W, H)
    _bottom_bar(app, c, mc, W, H)
    return True


# -- the live bits ------------------------------------------------------------
def _whiteboard(app, club, r):
    """Your XI as magnets (our goal on the left)."""
    lineup = club.get("lineup") or {}
    col = tuple(club.get("colour", (200, 40, 40)))
    f = _font("arial", 10, True)
    for s, pid in lineup.items():
        row, lane = slots.GRID.get(s, (-1, 0))
        x = r.x + (0.05 + (row + 1) * 0.165) * r.w if row >= 0 else r.x + 0.045 * r.w
        y = r.y + (0.5 + lane * 0.19) * r.h
        pygame.draw.circle(app.win, (20, 20, 20), (int(x) + 1, int(y) + 2), 7)
        pygame.draw.circle(app.win, col if s != "GK" else (230, 200, 40), (int(x), int(y)), 7)
        pygame.draw.circle(app.win, (250, 250, 250), (int(x), int(y)), 7, 1)
        p = clubs_mod.player_by_id(club, pid)
        if p is not None:
            t = f.render(p["Name"].split(" ")[-1][:9], True, (250, 250, 250))
            app.win.blit(t, t.get_rect(midtop=(int(x), int(y) + 8)))


def _calendar(app, c, r):
    """The month, its days, the next match circled."""
    if not c.get("date"):
        return
    import datetime
    today = cal.parse(c["date"])
    nxt = league.match_date(c)
    nd = cal.parse(nxt) if nxt else None
    from career import friendlies
    fr_days = {cal.parse(x["date"]) for x in friendlies.all_(c)}
    first = today.replace(day=1)
    f = _font("arial", 10)
    fb = _font("arial", 11, True)
    month = fb.render(today.strftime("%B %Y").upper(), True, (60, 50, 45))
    app.win.blit(month, month.get_rect(midbottom=(r.centerx, r.y - 5)))
    W, H = app.size                                         # (the printed grid, unrounded)
    sx, sy = W / (SRC_W - 2 * CROP_X), H / SRC_H
    gx, gy = (CAL_GRID[0] - CROP_X) * sx, CAL_GRID[1] * sy
    cw, ch = (CAL_GRID[2] - CAL_GRID[0]) * sx / 7, (CAL_GRID[3] - CAL_GRID[1]) * sy / 5
    offset = first.weekday()
    ndays = (first.replace(month=first.month % 12 + 1, year=first.year + first.month // 12) - first).days
    split = {i - 7 for i in range(35, offset + ndays)}      # 6-week month: 24/31 share a box, as on a real calendar
    small = _font("arial", 8)
    for day in range(1, ndays + 1):
        d = first.replace(day=day)
        i = offset + day - 1
        cell = i - 7 if i >= 35 else i
        bx, by = gx + (cell % 7) * cw, gy + (cell // 7) * ch      # the box's top-left
        colr = (150, 140, 130) if d < today else (60, 50, 45)
        if cell in split:                                   # the shared box: one top-left, one bottom-right
            t = small.render(str(day), True, colr)
            if i >= 35:
                cx, cy = bx + cw * 0.70, by + ch * 0.70
            else:
                cx, cy = bx + cw * 0.30, by + ch * 0.32
                pygame.draw.line(app.win, (120, 110, 100), (int(bx + cw - 3), int(by + 3)), (int(bx + 3), int(by + ch - 3)))
            rx, ry = cw / 2, ch / 2
        else:
            t = f.render(str(day), True, colr)
            cx, cy = bx + cw / 2, by + ch / 2
            rx, ry = cw / 2, ch / 2
        app.win.blit(t, t.get_rect(center=(round(cx), round(cy))))
        box = pygame.Rect(round(bx) + 1, round(by) + 1, round(bx + cw) - round(bx) - 1, round(by + ch) - round(by) - 1)
        ring = pygame.Rect(round(cx - rx * 0.9), round(cy - ry * 0.85), round(rx * 1.8), round(ry * 1.7))
        if cell in split:
            ring = pygame.Rect(round(cx - rx * 0.55), round(cy - ry * 0.55), round(rx * 1.1), round(ry * 1.1))
        if d == today:
            pygame.draw.rect(app.win, (40, 110, 200), box, 1)
        if nd and d == nd:
            pygame.draw.ellipse(app.win, (200, 40, 40), ring, 2)
        elif d in fr_days:                                  # friendlies: pencilled in, blue ink
            pygame.draw.ellipse(app.win, (40, 80, 170), ring, 2)
    nf = league.next_fixture(c)
    fr = friendlies.next_one(c)
    txt = None
    if fr:
        txt = f"{cal.fmt(fr['date'])[:10].strip()}: friendly v {fr['name']} ({'H' if fr['home'] else 'A'})"
    elif nf and nd:
        _, h, a = nf
        opp = a if h == c["my_club"] else h
        txt = f"{cal.fmt(nxt)[:10].strip()}: v {app.name(opp, True)} ({'H' if h == c['my_club'] else 'A'})"
    if txt:
        t = _font("arial", 12, True).render(txt, True, (240, 235, 225))
        bg = t.get_rect(midtop=(r.centerx, r.bottom + 12)).inflate(10, 4)
        pygame.draw.rect(app.win, (40, 30, 25), bg, border_radius=4)
        app.win.blit(t, t.get_rect(center=bg.center))


def _headline(app, c, mc):
    last = None
    for day in reversed(list(c.get("results", {}).values())):
        for m in day:
            if mc in (m["home"], m["away"]):
                last = m
                break
        if last:
            break
    if not last:
        return "NEW SEASON", "Big expectations as the campaign kicks off"
    home = mc == last["home"]
    gf, ga = (last["hg"], last["ag"]) if home else (last["ag"], last["hg"])
    opp = last["away"] if home else last["home"]
    me, them = app.name(mc, True).upper(), app.name(opp, True).upper()
    if gf > ga:
        head = f"{me} SEE OFF {them}" if gf - ga >= 2 else f"{me} EDGE {them}"
    elif gf == ga:
        head = f"HONOURS EVEN FOR {me}"
    else:
        head = f"{me} BEATEN BY {them}" if ga - gf >= 2 else f"{me} PIPPED BY {them}"
    pos = league.position_of(c, mc)
    sub = f"{gf}-{ga}  ·  now {pos}{'th' if 10 <= pos % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(pos % 10, 'th')} in the table"
    return head, sub


def _newspaper(app, c, mc, quad):
    head, sub = _headline(app, c, mc)
    key = ("paper", tuple(quad), head, sub)
    if key not in _cache:
        k = 3
        w = (quad[1][0] - quad[0][0]) * k * 0.86          # (fit the narrow top edge)
        size = 17
        while size > 9 and _font("georgia,timesnewroman,serif", size * k, True).size(head)[0] > w:
            size -= 1
        _cache[key] = _written(quad, [(head, size, True, (22, 20, 18)), (sub, 9, False, (55, 50, 45))],
                               top=0.04, left=0.05, k=k, font="georgia,timesnewroman,serif",
                               fill=(228, 222, 208, 242))
    surf, pos = _cache[key]
    app.win.blit(surf, pos)


def _laptop(app, c, quad):
    """The laptop's screen: switched on, the transfer window."""
    if not c.get("date"):
        return
    from career import finance as fin
    open_ = trf.in_window(c["date"])
    text = trf.window_text(c["date"])
    budget = f"Budget {fin.money(c['clubs'][c['my_club']]['finance'].get('transfer_budget', 0))}"
    key = ("laptop", tuple(quad), text, budget)
    if key not in _cache:
        col = (110, 220, 140) if open_ else (220, 150, 120)
        _cache[key] = _written(quad, [("TRANSFERS", 15, True, (205, 215, 225)), ("", 6, False, col),
                                      (text, 11, False, col), (budget, 11, False, (170, 185, 200))],
                               top=0.16, left=0.5, k=3, fill=(18, 30, 46, 235), centre=True)
    surf, pos = _cache[key]
    app.win.blit(surf, pos)


def _clipboard(app, c, club, quad):
    """The team sheet, written on the paper (warped to its angle on the desk)."""
    today = c.get("date") or ""
    out = [p for p in club["players"] if today and not avail.available(p, today)]
    lines = [("TEAM SHEET", 13, True, (40, 40, 40)),
             (clubs_mod.formation_name(club), 12, False, (60, 60, 60)),
             (f"{len(out)} unavailable" if out else "Everyone fit", 12, True, (150, 25, 25) if out else (30, 100, 50))]
    key = ("clip", tuple(quad), tuple(l[0] for l in lines))
    if key not in _cache:
        _cache[key] = _written(quad, lines, top=0.30, left=0.14)
    surf, pos = _cache[key]
    app.win.blit(surf, pos)


def _written(quad, lines, top, left, k=3, font="arial", fill=None, centre=False):
    """Text on a sheet seen at an angle: drawn flat at k x size, warped onto the four corners (TL TR BR BL) and
    scaled down (smooth edges).  Returns (surface, where to blit it)."""
    xs, ys = [p[0] for p in quad], [p[1] for p in quad]
    bx, by = min(xs), min(ys)
    bw, bh = max(xs) - bx + 1, max(ys) - by + 1
    TL, TR, BR, BL = [((x - bx) * k, (y - by) * k) for x, y in quad]
    w = int(max(TR[0] - TL[0], BR[0] - BL[0]))
    h = int(max(BL[1] - TL[1], BR[1] - TR[1]))
    flat = pygame.Surface((w, h), pygame.SRCALPHA)
    if fill:
        flat.fill(fill)
    y = int(h * top)
    for text, size, bold, col in lines:
        t = _font(font, size * k, bold).render(text, True, col)
        x = int(w * left - t.get_width() / 2) if centre else int(w * left)
        flat.blit(t, (x, y))
        y += t.get_height() + k
    big = pygame.Surface((bw * k, bh * k), pygame.SRCALPHA)
    pieces = 12                                            # (each row in short pieces, so it can follow a tilt)
    for yy in range(h):
        f = yy / h
        lx, ly = TL[0] + (BL[0] - TL[0]) * f, TL[1] + (BL[1] - TL[1]) * f
        rx, ry = TR[0] + (BR[0] - TR[0]) * f, TR[1] + (BR[1] - TR[1]) * f
        for i in range(pieces):
            a, b = i / pieces, (i + 1) / pieces
            sx0, sx1 = int(w * a), int(w * b)
            dx0, dx1 = lx + (rx - lx) * a, lx + (rx - lx) * b
            dy = ly + (ry - ly) * (a + b) / 2
            seg = pygame.transform.smoothscale(flat.subsurface((sx0, yy, max(1, sx1 - sx0), 1)),
                                               (max(1, int(round(dx1)) - int(round(dx0))), 1))
            big.blit(seg, (int(round(dx0)), int(round(dy))))
    return pygame.transform.smoothscale(big, (bw, bh)), (bx, by)


# -- hover text, bottom bar ---------------------------------------------------
def _door_label(c):
    d = league.match_date(c)
    return "Go to match" if not d or cal.days_between(c["date"], d) <= 0 else "Continue to the next match"


def _detail(app, c, club, key):
    from career import finance as fin, morale, training
    try:
        if key == "phone":
            n = trf.unread(c)
            return f"{n} unread message{'s' if n != 1 else ''}" if n else "No new messages"
        if key == "board":
            return f"{clubs_mod.formation_name(club)} - click to change"
        if key == "folders":
            return f"Transfer budget {fin.money(club['finance'].get('transfer_budget', 0))}"
        if key == "clipboard":
            avg = sum(morale.level(p) for p in club["players"]) / max(1, len(club["players"]))
            return f"{len(club['players'])} players"
        if key == "window":
            return f"Training: {training.settings(club)['intensity']}"
        if key == "mug":
            return "Put the kettle on - everything at a glance"
        if key == "laptop":
            from career import media
            return f"Fans: {media.mood_word(media.mood(c)).lower()}"
        if key == "paper":
            from career import media
            arts = media.articles(c)
            return arts[0]["head"] if arts else ""
        if key == "trophies":
            from career import board as brd
            return f"Board confidence {round(brd.state(c)['confidence'])}/100"
        if key == "calendar":
            d = league.match_date(c)
            return f"Next match {cal.fmt(d)}" if d else ""
    except Exception:
        return ""
    return ""


def _tooltip(app, label, detail, mouse, W, H):
    fb = app.fonts["h3"]
    fs = app.fonts["small"]
    t1 = fb.render(label, True, (255, 255, 255))
    t2 = fs.render(detail, True, (220, 220, 210)) if detail else None
    w = max(t1.get_width(), t2.get_width() if t2 else 0) + 20
    h = t1.get_height() + (t2.get_height() + 4 if t2 else 0) + 14
    x = min(mouse[0] + 16, W - w - 8)
    y = min(mouse[1] + 18, H - 64 - h - 6)
    box = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(box, (15, 15, 18, 220), box.get_rect(), border_radius=8)
    app.win.blit(box, (x, y))
    app.win.blit(t1, (x + 10, y + 7))
    if t2:
        app.win.blit(t2, (x + 10, y + 9 + t1.get_height()))


def _bottom_bar(app, c, mc, W, H):
    from career.ui import Button, TEXT, MUTED, ACCENT, _ordinal
    bar = pygame.Surface((W, 64), pygame.SRCALPHA)
    bar.fill((14, 16, 20, 215))
    app.win.blit(bar, (0, H - 64))
    y = H - 64
    app.text(app.name(mc), "h3", TEXT, (18, y + 8))
    pos = league.position_of(c, mc)
    me = next(row for row in league.table(c) if row["club"] == mc)
    when = cal.fmt(c["date"]) if c.get("date") else f"Season {c['season']}"
    app.text(f"{when}  ·  " + (f"{_ordinal(pos)}, {me['pts']} pts" if me["p"] else "pre-season"), "small", MUTED,
             (18, y + 36))
    nf = league.next_fixture(c)
    x = 360
    from career import friendlies
    fr = friendlies.next_one(c)
    if fr:
        days = cal.days_between(c["date"], fr["date"])
        whn = "Today" if days <= 0 else "Tomorrow" if days == 1 else f"in {days} days"
        app.text(f"Next: Friendly v {fr['name']} ({'H' if fr['home'] else 'A'})", "body", TEXT, (x, y + 10))
        app.text(f"{cal.fmt(fr['date'])}  ·  {whn}", "small", MUTED, (x, y + 36))
        app.buttons.append(Button((W - 196, y + 9, 180, 46), "Go to friendly" if days <= 0 else "Continue",
                                  app.continue_to_match, primary=True))
        nf = None
    if nf:
        _, h, a = nf
        d = league.match_date(c)
        days = cal.days_between(c["date"], d) if d else 0
        whn = "Today" if days <= 0 else "Tomorrow" if days == 1 else f"in {days} days"
        app.text(f"Next: {app.name(h, True)} v {app.name(a, True)}", "body", TEXT, (x, y + 10))
        app.text(f"{cal.fmt(d)}, {cal.kick_off(d)}  ·  {whn}" if d else "", "small", MUTED, (x, y + 36))
        label = "Go to match" if not d or days <= 0 else "Continue"
        app.buttons.append(Button((W - 196, y + 9, 180, 46), label, app.continue_to_match, primary=True))
    app.buttons.append(Button((W - 330, y + 9, 124, 46), "Save & quit", app.save_and_quit, font="btn_s"))
    app.buttons.append(Button((W - 464, y + 9, 124, 46), "Overview", lambda: app._menu("overview"), font="btn_s"))
