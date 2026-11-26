"""The team sheets before kick-off, drawn by the match screen while the 3D view gets ready (22 Nov): both XIs in
their clubs' colours and badges, each formation on a little pitch, the numbers and names - as TV shows them before
a match.  Then, with the 3D ready, the camera flies in and the match kicks off."""
import math
import os

import pygame

from config.constants import WIDTH, HEIGHT

_cache = {}


def _font(size, bold=False):
    key = (size, bold)
    if key not in _cache:
        _cache[key] = pygame.font.SysFont("Arial", size, bold=bold)
    return _cache[key]


def _kits(home, away):
    """(home shirt, away shirt, home crest path, away crest path) - the 3D view's choice, so the colours match."""
    if ("kits", home, away) not in _cache:
        try:
            import kits                                   # (broadcast3d/kits.py: on the path once the 3D's started)
            h, a, _g0, _g1, hi, ai = kits.choose(home, away)
            _cache[("kits", home, away)] = (tuple(h["shirt"]), tuple(a["shirt"]), hi.get("crest"), ai.get("crest"))
        except Exception:
            _cache[("kits", home, away)] = ((30, 144, 255), (220, 20, 60), None, None)
    return _cache[("kits", home, away)]


def _crest(path, size):
    if not path:
        return None
    key = ("crest", path, size)
    if key not in _cache:
        try:
            im = pygame.image.load(path).convert_alpha()
            w, h = im.get_size()
            k = size / max(w, h)
            _cache[key] = pygame.transform.smoothscale(im, (max(1, int(w * k)), max(1, int(h * k))))
        except Exception:
            _cache[key] = None
    return _cache[key]


def _formation(team):
    """The team's formation's name ("4-3-3"), or None."""
    try:
        import config.formations as formations
        from config import slots
        mine = formations.formation_slots(team)
        if not mine:
            return "4-4-2"
        mine = sorted(s for s in mine if s != "GK")
        for name, spots in slots.FORMATIONS.items():
            if sorted(spots) == mine:
                return name
    except Exception:
        pass
    return None


def _text_on(rgb):
    return (15, 15, 15) if (rgb[0] * 0.3 + rgb[1] * 0.59 + rgb[2] * 0.11) > 150 else (255, 255, 255)


SHOW_EACH = 5.0          # seconds each team's sheet is up (home, then away, then round again while it loads)


def draw(screen, engine, note=None, t=0.0):
    """One team's sheet at a time over the screen (the pitch area): home for SHOW_EACH seconds, then away...
    t: seconds since the sheets went up.  note: a line along the bottom ("Getting the 3D view ready...")."""
    W, H = screen.get_size()
    screen.fill((14, 17, 22))
    home, away = engine._team_name(0), engine._team_name(1)
    s0, s1, c0, c1 = _kits(home, away)
    team = int(t / SHOW_EACH) % 2
    players, name, shirt, crest = ((engine.team0, home, s0, c0), (engine.team1, away, s1, c1))[team]
    pad = max(16, W // 50)
    pw, top = W - 2 * pad, pad
    ph = H - top - pad - 40
    x0 = pad
    hb = max(56, ph // 9)                                  # (the band on top: crest, name, formation)
    pygame.draw.rect(screen, (24, 28, 35), (x0, top, pw, ph), border_radius=12)
    pygame.draw.rect(screen, shirt, (x0, top, pw, hb), border_top_left_radius=12, border_top_right_radius=12)
    fg = _text_on(shirt)
    cr = _crest(crest, hb - 12)
    tx = x0 + 18
    if cr is not None:
        screen.blit(cr, (x0 + 14, top + (hb - cr.get_height()) // 2))
        tx = x0 + 28 + cr.get_width()
    t_ = _font(max(22, hb // 2), True).render(name.upper(), True, fg)
    screen.blit(t_, (tx, top + (hb - t_.get_height()) // 2))
    form = _formation(team)
    lab = _font(max(16, hb * 2 // 7), True).render(("HOME" if team == 0 else "AWAY") + ("   " + form if form else ""),
                                                   True, fg)
    screen.blit(lab, (x0 + pw - lab.get_width() - 18, top + (hb - lab.get_height()) // 2))
    # The formation on his own half, in its real shape (68 m across, 52.5 deep), the names beside it
    by = top + hb + 16
    bh = ph - hb - 32
    mw = int(min(bh * 68.0 / 52.5, pw * 0.56))
    mh = int(mw * 52.5 / 68.0)
    mx = x0 + 18
    my = by + (bh - mh) // 2
    _mini_pitch(screen, (mx, my, mw, mh), players, team, shirt)
    lx = mx + mw + 30
    rows = max(1, len(players[:11]))
    rh = bh / rows
    fs = max(14, min(28, int(rh * 0.52)))
    for j, p in enumerate(players[:11]):
        y = by + j * rh + rh / 2
        num = getattr(p, "number", None) or (j + 1)
        a = _font(fs, True).render(str(num), True, (250, 215, 80))
        screen.blit(a, (lx + 30 - a.get_width(), y - a.get_height() / 2))
        nm = _font(fs).render(str(getattr(p, "name", "")), True, (240, 240, 240))
        screen.blit(nm, (lx + 44, y - nm.get_height() / 2))
        role = _position_label(p)
        if role:
            r = _font(max(12, fs - 6)).render(role, True, (150, 160, 175))
            screen.blit(r, (x0 + pw - r.get_width() - 18, y - r.get_height() / 2))
    # Two little marks: which of the two sheets this is
    for i in range(2):
        pygame.draw.circle(screen, (230, 230, 230) if i == team else (80, 86, 96),
                           (W // 2 - 10 + 20 * i, top + ph + 12), 5)
    if note:
        dots = "." * (1 + int(pygame.time.get_ticks() / 400) % 3)
        t_ = _font(20, True).render(note.rstrip(".") + dots, True, (210, 215, 225))
        screen.blit(t_, (W // 2 - t_.get_width() // 2, H - pad - 22))


# The formation as a line-up graphic: each player at his spot in the formation (config/slots.py GRID - row from
# the back line to the strikers, lane from left to right), not where he's standing for kick-off (which squeezes
# everyone into his own half - centre-backs ahead of the full-backs, the strikers on top of each other).
ROW_DEPTH = {0: 0.20, 1: 0.38, 2: 0.55, 3: 0.72, 4: 0.90}      # (0 = his goal line, 1 = halfway)
LANE_ACROSS = 0.2                                              # (lane -2..2 -> 0.1..0.9 across)


def _position_label(p):
    """His position as the game names it elsewhere (config/slots.py LABEL: CB, DM, AM, ST...) - not the engine's
    stand-in role (a holding midfielder plays as a "LCM" underneath)."""
    s = str(getattr(p, "slot", None) or getattr(p, "role", "") or "")
    try:
        from config import slots
        return slots.LABEL.get(s, s)
    except Exception:
        return s


def _shape_spot(p, team):
    """(depth 0..1 up his half, across 0..1 left to right) for the line-up picture."""
    if p.role == "GK" or getattr(p, "slot", None) == "GK":
        return 0.04, 0.5
    try:
        from config import slots
        s = getattr(p, "slot", None) or p.role
        if s in slots.GRID:
            row, lane = slots.GRID[s]
            return ROW_DEPTH.get(row, 0.5), 0.5 + LANE_ACROSS * lane
    except Exception:
        pass
    px, py = p.pos.x, p.pos.y                           # (anything unknown: where he is)
    if team == 0:
        depth, lat = px / (WIDTH / 2), py / HEIGHT
    else:
        depth, lat = (WIDTH - px) / (WIDTH / 2), 1.0 - py / HEIGHT
    return max(0.0, min(1.0, depth)), max(0.0, min(1.0, lat))


def _mini_pitch(screen, rect, players, team, shirt):
    x, y, w, h = rect
    pygame.draw.rect(screen, (34, 92, 46), rect, border_radius=6)
    line = (200, 225, 205)
    pygame.draw.rect(screen, line, rect, 2, border_radius=6)
    pygame.draw.line(screen, line, (x, y + 2), (x + w, y + 2), 2)                  # (halfway, along the top)
    pygame.draw.arc(screen, line, (x + w / 2 - w * 0.17, y - w * 0.17, w * 0.34, w * 0.34), math.pi, 2 * math.pi, 2)
    bw, bd = w * 0.6, h * 0.3                                                      # (his own box at the bottom)
    pygame.draw.rect(screen, line, (x + (w - bw) / 2, y + h - bd, bw, bd), 2)
    pygame.draw.rect(screen, line, (x + (w - bw * 0.45) / 2, y + h - bd * 0.36, bw * 0.45, bd * 0.36), 2)
    fg = _text_on(shirt)
    r = max(10, int(w / 22))
    f = _font(max(11, int(r * 1.1)), True)
    for j, p in enumerate(players[:11]):
        depth, lat = _shape_spot(p, team)
        cx = x + r + lat * (w - 2 * r)
        cy = y + h - r - depth * (h - 2 * r)
        pygame.draw.circle(screen, (10, 10, 10), (int(cx) + 1, int(cy) + 2), r)
        pygame.draw.circle(screen, shirt, (int(cx), int(cy)), r)
        pygame.draw.circle(screen, (235, 235, 235), (int(cx), int(cy)), r, 2)
        num = getattr(p, "number", None) or (j + 1)
        t = f.render(str(num), True, fg)
        screen.blit(t, (cx - t.get_width() / 2, cy - t.get_height() / 2))
