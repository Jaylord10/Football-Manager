"""
rendering/debug_overlay.py
==========================
Positioning debug overlay - press D in the match window to cycle:
    off -> both teams -> Blue only -> Red only -> off

For every player it draws:
  - a line from the player to where he's trying to get to (his target),
    coloured by how hard he's working: green = easing / walking,
    yellow = purposeful, red = flat out
  - a dot on the target
  - a short label saying WHY he's going there ("press the ball",
    "run in behind", "receive pass", "role RB_blue", ...)

Works while paused too (SPACE), which is the best way to study a moment.
"""

import pygame
from config.constants import FIELD_MARGIN, PLAYER_RADIUS

MODES = ("off", "both", "blue", "red")
TEAM_TINT = {0: (140, 190, 255), 1: (255, 150, 160)}

_font = None


def _get_font():
    global _font
    if _font is None:
        pygame.font.init()
        _font = pygame.font.SysFont("arial", 12)
    return _font


def _effort_colour(e):
    e = max(0.0, min(1.0, e))
    if e < 0.5:                                   # green -> yellow
        t = e / 0.5
        return (int(60 + 180 * t), int(200 + 20 * t), 60)
    t = (e - 0.5) / 0.5                           # yellow -> red
    return (240, int(220 - 170 * t), 50)


def next_mode(mode):
    return MODES[(MODES.index(mode) + 1) % len(MODES)] if mode in MODES else "both"


def draw(surface, players, mode):
    if mode == "off":
        return
    font = _get_font()
    for p in players:
        if not getattr(p, "is_active", True):
            continue
        if mode == "blue" and p.team != 0:
            continue
        if mode == "red" and p.team != 1:
            continue
        x, y = int(p.pos.x) + FIELD_MARGIN, int(p.pos.y) + FIELD_MARGIN

        if p.has_ball:
            text = f"{p.role}: on the ball ({p.state})"
            colour = (255, 255, 255)
        else:
            tx, ty = int(p.target.x) + FIELD_MARGIN, int(p.target.y) + FIELD_MARGIN
            colour = _effort_colour(getattr(p, "effort", 0.4))
            if (tx - x) ** 2 + (ty - y) ** 2 > 9:
                pygame.draw.line(surface, colour, (x, y), (tx, ty), 2)
                pygame.draw.circle(surface, colour, (tx, ty), 4)
                pygame.draw.circle(surface, (20, 20, 20), (tx, ty), 4, 1)
            reason = getattr(p, "pos_reason", None) or ("keeper" if p.role == "GK" else p.state)
            text = f"{p.role}: {reason}"

        label = font.render(text, True, TEAM_TINT.get(p.team, (255, 255, 255)))
        shadow = font.render(text, True, (0, 0, 0))
        rect = label.get_rect(center=(x, y + PLAYER_RADIUS + 22))
        surface.blit(shadow, (rect.x + 1, rect.y + 1))
        surface.blit(label, rect)

    # Key
    key = f"Overlay: {mode}  (D to change)   line colour = effort: green easy / yellow / red flat out"
    k = font.render(key, True, (255, 255, 255))
    ks = font.render(key, True, (0, 0, 0))
    surface.blit(ks, (FIELD_MARGIN + 6, FIELD_MARGIN + 5))
    surface.blit(k, (FIELD_MARGIN + 5, FIELD_MARGIN + 4))
