"""
career/ui.py
============
The manager game's screens (pygame, same window as the match).

  Title          - continue your career, start a new one, or a friendly (Blue v Red)
  Choose club    - the ten clubs, their strength and style
  Home           - next match, league position, form, mini table
  Squad          - your players and their ratings
  League table   - the full table
  Fixtures       - every matchday, results and what's to come
  Match day      - watch your match or simulate it; the other matches are
                   played by the full engine in the background
  Results        - the matchday's results and scorers, then the table moves on
  Season end     - the champions, where you finished, start the next season

The career is saved after every matchday (saves/career.json).
"""

import os
import random
import time
import pygame

from career import clubs as clubs_mod
from career import league
from career import matches
from career import world
from career import calendar as cal
from career import availability as avail
from career import training
from career import finance as fin
from career import contracts as con
from career import transfers as trf
from career import morale, chats, faces, captains, teamtalk, media, fitness, friendlies, clubinfo
from career import playoffs
from career import registration as reg
from career import board as brd
from career import spain
from career import loans as lns

# ---------------------------------------------------------------------------
# Look
# ---------------------------------------------------------------------------
BG        = (16, 22, 28)
PANEL     = (28, 36, 46)
PANEL_2   = (36, 46, 58)
LINE      = (52, 64, 78)
TEXT      = (232, 236, 240)
MUTED     = (140, 152, 166)
ACCENT    = (64, 184, 112)
ACCENT_HI = (90, 210, 140)
WIN, DRAW, LOSS = (64, 184, 112), (200, 170, 60), (200, 70, 70)
HIGHLIGHT = (44, 70, 58)


def _font(size, bold=False):
    return pygame.font.SysFont("segoeui,arial,helvetica,dejavusans", size, bold=bold)


class Button:
    def __init__(self, rect, label, action, primary=False, enabled=True, font="btn"):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.action = action
        self.primary = primary
        self.enabled = enabled
        self.font = font

    def draw(self, surf, fonts, mouse):
        hover = self.enabled and self.rect.collidepoint(mouse)
        if not self.enabled:
            col = PANEL
        elif self.primary:
            col = ACCENT_HI if hover else ACCENT
        else:
            col = LINE if hover else PANEL_2
        pygame.draw.rect(surf, col, self.rect, border_radius=8)
        txt = fonts[self.font].render(self.label, True, (16, 22, 28) if self.primary and self.enabled
                                  else (TEXT if self.enabled else MUTED))
        surf.blit(txt, txt.get_rect(center=self.rect.center))

    def hit(self, pos):
        return self.enabled and self.rect.collidepoint(pos)


def _badge(surf, colour, center, r=14, club=None):
    """The club's crest (career/clubinfo.py) - or, until it has one, a circle in its colour."""
    if club is not None:
        from career import clubinfo
        img = clubinfo.image(club, "crest", (int(r * 2.3), int(r * 2.3)))
        if img is not None:
            surf.blit(img, img.get_rect(center=center))
            return
    pygame.draw.circle(surf, colour, center, r)
    pygame.draw.circle(surf, (230, 230, 230), center, r, 2)


def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _expect(pos, n, div="pl"):
    if div == "d1":
        return ("Promotion favourites" if pos <= 2 else "Play-off hopefuls" if pos <= 6 else "Top half"
                if pos <= n // 2 else "Mid-table" if pos <= n - 5 else "Lower half")
    return ("Title favourites" if pos == 1 else "Title challengers" if pos <= 3 else "Top-four hopefuls" if pos <= 5
            else "Chasing Europe" if pos <= 8 else "Mid-table" if pos <= n - 6 else "Lower half" if pos <= n - 3
            else "Bottom three")


def _star(surf, center, r, filled, colour=(230, 190, 60)):
    import math
    cx, cy = center
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    if filled:
        pygame.draw.polygon(surf, colour, pts)
    else:
        pygame.draw.polygon(surf, colour, pts, 2)


POS_NAMES = {"GK": "Goalkeeper", "LB": "Left-back", "RB": "Right-back", "CB": "Centre-back",
             "CM": "Central midfielder", "LM": "Left midfielder", "RM": "Right midfielder", "ST": "Striker",
             "DM": "Defensive midfielder", "AM": "Attacking midfielder", "LW": "Left winger", "RW": "Right winger",
             "LWB": "Left wing-back", "RWB": "Right wing-back"}


def _attr20(raw):
    """Squad files use 0-100; players' attributes are shown (and used by the engine) on 1-20."""
    return max(1, int(raw / 5))


def _attr_colour(v):
    if v >= 16:
        return ACCENT_HI
    if v >= 11:
        return (150, 210, 160)
    if v >= 6:
        return TEXT
    return LOSS


def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


SHORT_ROLE = {"Cautious full-back": "Cautious FB", "Attacking full-back": "Attacking FB",
              "Holding midfielder": "Holding mid", "Central midfielder": "Central mid",
              "Box-to-box midfielder": "Box-to-box", "Wide midfielder": "Wide mid", "Inside forward": "Inside fwd",
              "Advanced forward": "Advanced fwd", "Deep-lying forward": "Deep-lying fwd"}

MORALE_COLOUR = {"good": (110, 200, 130), "ok": (200, 200, 205), "bad": (225, 110, 100)}

PITCH_ROLE = {"Advanced forward": "Adv. forward", "Deep-lying forward": "Deep forward"}   # (the Tactics pitch)

STYLE_TEXT = {"low_block": "sits deep", "mid_block": "mid block", "press": "presses",
              "high_press": "presses high"}
BUILD_TEXT = {"play_out": "plays out from the back", "mixed": "mixed build-up", "clear": "gets it forward early"}


def _stars(strength):
    lo = min(clubs_mod.STRENGTHS + clubs_mod.STRENGTHS_10)
    hi = max(clubs_mod.STRENGTHS + clubs_mod.STRENGTHS_10)
    return 1 + round(4 * (strength - lo) / max(1, hi - lo))


# ---------------------------------------------------------------------------
# The app
# ---------------------------------------------------------------------------
class App:
    def __init__(self):
        pygame.init()
        from config.constants import WIDTH, HEIGHT, FIELD_MARGIN
        from rendering.ui_renderer import TOP_UI, BOTTOM_UI
        self.size = (WIDTH + FIELD_MARGIN * 2, HEIGHT + FIELD_MARGIN * 2 + TOP_UI + BOTTOM_UI)
        self._window()
        self.fonts = {"h1": _font(40, True), "h2": _font(26, True), "h3": _font(20, True),
                      "body": _font(17), "small": _font(14), "btn": _font(18, True), "big": _font(56, True),
                      "btn_s": _font(15, True), "tiny": _font(12)}
        self.clock = pygame.time.Clock()
        self.career = league.load()
        faces.bind(self.career)
        from career import stadium
        if self.career:                                 # (no save yet: a fresh install)
            stadium.sync(self.career)                   # (the ground's real capacity - career/stadium.py)
        self.screen = "title"
        self.buttons = []
        self.running = True
        self.fixtures_md = 1
        self.bg = None                 # BackgroundMatches: the matchday's other matches
        self.my_bg = None              # ...and yours, when you simulate it
        self.my_result = None
        self.matchday_results = None
        self.message = None

    def _window(self):
        self.win = pygame.display.set_mode(self.size)
        pygame.display.set_caption("Football Manager")

    # -- helpers ------------------------------------------------------------
    def text(self, s, font, col, pos, anchor="topleft"):
        surf = self.fonts[font].render(str(s), True, col)
        r = surf.get_rect(**{anchor: pos})
        self.win.blit(surf, r)
        return r

    def club(self, cid):
        """A club - or the free agent pool (id -1)."""
        if cid == -2:
            return trf.abroad(self.career)
        if cid >= spain.ID_BASE:
            return spain.club(self.career, cid)
        return con.free_agents(self.career) if cid == -1 else self.career["clubs"][cid]

    def name(self, cid, short=False):
        c = self.club(cid)
        return c["short"] if short else c["name"]

    def colour(self, cid):
        return tuple(self.club(cid)["colour"])

    def _club_of(self, cid):
        """The club dict for an id (league, Spain, free agents, abroad) - or None."""
        try:
            return self.club(cid)
        except Exception:
            return None

    def _face(self, p, cid, size, pos, border=True):
        """A player's face (career/faces.py) - any club, abroad or a free agent."""
        try:
            club = trf.seller(self.career, cid)
        except Exception:
            club = None
        shirt = self.colour(cid) if cid is not None and cid >= 0 else None
        self.win.blit(faces.face_surface(p, size, shirt, club), pos)
        if border:
            pygame.draw.rect(self.win, LINE, (pos[0], pos[1], size, size), 1, border_radius=3)

    # -- main loop ----------------------------------------------------------
    def run(self):
        while self.running:
            mouse = pygame.mouse.get_pos()
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.quit()
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    for b in list(self.buttons):
                        if b.hit(e.pos):
                            b.action()
                            break
                elif e.type == pygame.KEYDOWN:
                    self.key(e.key)
            if not self.running:
                break
            self._keep_running()
            self.win.fill(BG)
            self.buttons = []
            getattr(self, "draw_" + self.screen)()
            for b in self.buttons:
                b.draw(self.win, self.fonts, mouse)
            pygame.display.flip()
            self.clock.tick(30)
        pygame.quit()

    def key(self, k):
        if self.screen == "fixtures":
            if k in (pygame.K_LEFT, pygame.K_a):
                self.fixtures_md = max(1, self.fixtures_md - 1)
            elif k in (pygame.K_RIGHT, pygame.K_d):
                self.fixtures_md = min(len(self.career["fixtures"]), self.fixtures_md + 1)
        if self.screen == "calendar" and k in (pygame.K_LEFT, pygame.K_RIGHT):
            self._cal_move(-1 if k == pygame.K_LEFT else 1)
        if k == pygame.K_ESCAPE and self.screen == "player":
            self.go(getattr(self, "player_back", "squad"))
        elif k == pygame.K_ESCAPE and self.screen in ("squad", "table", "fixtures", "prematch", "tactics",
                                                     "calendar", "training", "finances", "transfers",
                                                     "freeagents", "bid", "inbox", "board", "spain", "loan"):
            self.go("home")

    def quit(self):
        for bg in (self.bg, self.my_bg):
            if bg is not None:
                bg.stop()
        self.running = False

    # -- shared layout --------------------------------------------------------
    def sidebar(self, active):
        W, H = self.size
        pygame.draw.rect(self.win, PANEL, (0, 0, 220, H))
        mc = self.career["my_club"]
        _badge(self.win, self.colour(mc), (36, 40), 16, self._club_of(mc))
        self.text(self.name(mc, short=True), "h3", TEXT, (62, 28))
        c = self.career
        if c.get("date"):
            self.text(cal.fmt(c["date"]), "small", MUTED, (62, 52))
        else:
            self.text(f"Season {c['season']}", "small", MUTED, (62, 52))
        # Everything else is reached from your office (career/office.py): back there to go somewhere new
        self.buttons.append(Button((14, 100, 192, 56), "Office", lambda: self._menu("home"), primary=True))
        y = 172
        for line in self._lines("Back to your office to go anywhere else.", "small", 186):
            self.text(line, "small", MUTED, (18, y))
            y += 20
        self.buttons.append(Button((14, H - 66, 192, 42), "Save & quit", self.save_and_quit))

    def _menu(self, screen):
        if screen == "squad":
            self.squad_club = self.career["my_club"]
        if screen == "table":
            self.table_div = None                       # (your own division first)
            self.table_scorers = False
        if screen == "club":
            self.club_view = None                       # (your own club)
            self.stadium_reply = None
        self.go(screen)

    def save_and_quit(self):
        league.save(self.career)
        self.quit()

    def panel(self, rect, title=None):
        pygame.draw.rect(self.win, PANEL, rect, border_radius=10)
        if title:
            self.text(title, "h3", TEXT, (rect[0] + 16, rect[1] + 12))

    # -- title --------------------------------------------------------------
    def draw_title(self):
        W, H = self.size
        self.text("FOOTBALL MANAGER", "big", TEXT, (W // 2, H // 3 - 30), "center")
        self.text("Take charge of a club. Win the league.", "body", MUTED, (W // 2, H // 3 + 24), "center")
        y = H // 2
        if self.career:
            c = self.career
            label = f"Continue  -  {self.name(c['my_club'])}, season {c['season']}"
            self.buttons.append(Button((W // 2 - 220, y, 440, 52), label, lambda: self.go("home"), primary=True))
            y += 66
        self.buttons.append(Button((W // 2 - 220, y, 440, 52), "New career", self.new_career_screen,
                                   primary=not self.career))
        y += 66
        self.buttons.append(Button((W // 2 - 220, y, 440, 52), "Friendly: Blue v Red (the match engine on its own)",
                                   self.friendly))
        y += 66
        self.buttons.append(Button((W // 2 - 220, y, 440, 52), "Quit", self.quit))
        if self.message:
            self.text(self.message, "small", LOSS, (W // 2, H - 40), "center")

    def friendly(self):
        os.environ.pop("FM_MATCH_CONFIG", None)
        import config.formations as formations
        from core.database import PlayerDatabase
        formations.db = PlayerDatabase("match_config.json")
        from gameplay.match_engine import MatchEngine
        m = MatchEngine(career=True)
        m.run()
        if m.quit_requested:
            self.quit()
            return
        self._window()

    # -- choose club --------------------------------------------------------
    def new_career_screen(self):
        seed = random.randrange(1 << 30)          # (the fixture list - the clubs and players are the world's)
        self.pending_clubs = world.load()
        from career import divisions
        self.pending_d1 = divisions.load_world()
        self.choose_div = "pl"
        self.pending_seed = seed
        self.go("choose")

    def draw_choose(self):
        W, H = self.size
        from career import divisions
        div = getattr(self, "choose_div", "pl")
        self.text("Choose your club", "h1", TEXT, (40, 24))
        for i, d in enumerate(divisions.ORDER):
            self.buttons.append(Button((W - 40 - (2 - i) * 186, 28, 178, 36), divisions.name(d),
                                       lambda d=d: setattr(self, "choose_div", d), primary=d == div, font="btn_s"))
        pool = self.pending_clubs if div == "pl" else getattr(self, "pending_d1", None) or divisions.load_world()
        blurb = ("the top flight: the bottom three go down" if div == "pl" else
                 "the second tier: two go up automatically, 3rd to 6th play off for the third place")
        self.text(f"{divisions.name(div)} - {len(pool)} clubs, {blurb}. Where the papers predict each will finish:",
                  "body", MUTED, (40, 72))
        clubs = sorted(pool, key=lambda c: c["name"])
        ranked = sorted(clubs, key=lambda c: (-c["strength"], -sum(sorted((clubs_mod.overall(p) for p in c["players"]),
                                                                          reverse=True)[:11])))
        predicted = {c["id"]: i + 1 for i, c in enumerate(ranked)}
        rows = (len(clubs) + 1) // 2
        col_w = (W - 100) // 2
        row_h = min(108, (H - 112 - 86) // rows - 6)
        big = row_h >= 90
        mouse = pygame.mouse.get_pos()
        for i, c in enumerate(clubs):
            x = 40 + (i // rows) * (col_w + 20)
            y = 108 + (i % rows) * (row_h + 6)
            rect = pygame.Rect(x, y, col_w, row_h)
            b = Button(rect, "", lambda c=c: self.start_career(c["id"]))
            pygame.draw.rect(self.win, PANEL_2 if rect.collidepoint(mouse) else PANEL, rect, border_radius=10)
            _badge(self.win, tuple(c["colour"]), (x + 30, y + row_h // 2), 16 if not big else 20, c)
            pos = predicted[c["id"]]
            ex = self.fonts["small"].render(_expect(pos, len(clubs), div), True, MUTED)
            px = x + col_w - 16 - ex.get_width()
            self.win.blit(ex, (px, y + (22 if big else 10)))
            self.text(_ordinal(pos), "h3", ACCENT_HI if pos <= (4 if div == "pl" else 2) else TEXT,
                      (px - 12, y + (16 if big else 5)), "topright")
            style = f"{STYLE_TEXT[c['tactics']['defence']].capitalize()}, {BUILD_TEXT[c['tactics']['build_up']]}"
            best = max(c["players"], key=clubs_mod.overall)
            if big:
                self.text(c["name"], "h3", TEXT, (x + 70, y + 18))
                self.text(style, "small", MUTED, (x + 70, y + 50))
                self.text(f"Best player: {best['Name']} ({best['Pos']}, {clubs_mod.overall(best)})", "small", MUTED,
                          (x + 70, y + 72))
            else:
                self.text(c["name"], "h3", TEXT, (x + 58, y + 5))
                self.text(f"{style}  ·  best: {best['Name']} ({best['Pos']}, {clubs_mod.overall(best)})", "small",
                          MUTED, (x + 58, y + row_h - 22))
            self.buttons.append(_Invisible(rect, b.action))
        self.buttons.append(Button((40, H - 70, 160, 46), "Back", lambda: self.go("title")))

    def start_career(self, cid):
        for bg in (self.bg, self.my_bg):               # (anything left from another career)
            if bg is not None:
                bg.stop()
        self.bg = self.my_bg = None
        self.my_result = None
        self.career = league.new_career(self.pending_clubs, cid, self.pending_seed)
        faces.bind(self.career)
        from career import stadium
        stadium.sync(self.career)
        self._menu_roles(self.career["clubs"][cid])
        league.save(self.career)
        self.go("home")

    # -- home ---------------------------------------------------------------
    def draw_home(self):
        """Home: your office (career/office.py) - or the overview if there's no picture."""
        if brd.state(self.career).get("sacked"):
            self.go("sacked")
            return self.draw_sacked()
        if league.season_over(self.career):
            if playoffs.my_next(self.career):            # (Division 1: your play-offs first)
                self.go("playoff")
                return self.draw_playoff()
            self.go("season_end")
            return self.draw_season_end()
        from career import office
        if not office.draw(self):
            self.draw_overview()

    def draw_overview(self):
        """Everything at a glance (the coffee mug in the office)."""
        if brd.state(self.career).get("sacked"):
            self.go("sacked")
            return self.draw_sacked()
        if league.season_over(self.career):
            if playoffs.my_next(self.career):
                self.go("playoff")
                return self.draw_playoff()
            self.go("season_end")
            return self.draw_season_end()
        W, H = self.size
        self.sidebar("home")
        c = self.career
        mc = c["my_club"]
        x0 = 250
        self.text(self.name(mc), "h1", TEXT, (x0, 24))
        md = c["matchday"]
        label = cal.season_label(c["year"]) if c.get("year") else f"Season {c['season']}"
        today = f"{cal.fmt(c['date'])}  ·  " if c.get("date") else ""
        self.text(f"{today}{label}  ·  Matchday {md} of {len(c['fixtures'])}", "body", MUTED, (x0, 76))
        if c.get("date") and "abroad" in c:
            self.text(trf.window_text(c["date"]), "small", ACCENT if trf.in_window(c["date"]) else MUTED,
                      (W - 30, 30), "topright")

        # Next match
        nf = league.next_fixture(c)
        r = pygame.Rect(x0, 116, W - x0 - 30, 170)
        self.panel(r, "Next match")
        if nf:
            _, home, away = nf
            opp = away if home == mc else home
            venue = "Home" if home == mc else "Away"
            pos = league.position_of(c, opp)
            row = next(t for t in league.table(c) if t["club"] == opp)
            cy = r.y + 74
            mid = r.x + (r.w - 250) // 2 + 10
            _badge(self.win, self.colour(home), (mid - 40, cy + 14), 16, self._club_of(home))
            short = len(self.name(home)) + len(self.name(away)) > 30     # long names: the short ones
            self.text(self.name(home, short), "h2", TEXT, (mid - 64, cy), "topright")
            self.text("v", "h2", MUTED, (mid, cy), "midtop")
            _badge(self.win, self.colour(away), (mid + 40, cy + 14), 16, self._club_of(away))
            self.text(self.name(away, short), "h2", TEXT, (mid + 64, cy))
            played = row["p"] > 0
            info = f"{venue}  ·  {self.name(opp, True)}: " + (
                f"{_ordinal(pos)}, form {' '.join(row['form'])}" if played else "first game of the season")
            self.text(info, "body", MUTED, (mid, cy + 50), "midtop")
            d = league.match_date(c)
            if d:
                days = cal.days_between(c["date"], d)
                when = "Today" if days <= 0 else "Tomorrow" if days == 1 else f"In {days} days"
                self.text(f"{cal.fmt(d)}, {cal.kick_off(d)}  ·  {when}", "small", MUTED, (r.x + 16, r.y + 40))
            label = "Go to match" if not d or cal.days_between(c["date"], d) <= 0 else "Continue"
            self.buttons.append(Button((r.right - 236, r.y + 70, 216, 50), label, self.continue_to_match,
                                       primary=True))

        # Your season so far
        t = league.table(c)
        me = next(row for row in t if row["club"] == mc)
        pos = league.position_of(c, mc)
        r2 = pygame.Rect(x0, 306, 360, 280)
        self.panel(r2, "Your season")
        self.text(_ordinal(pos) if me["p"] else "-", "big", ACCENT, (r2.x + 20, r2.y + 44))
        self.text(f"{me['pts']} pts", "h2", TEXT, (r2.x + 170, r2.y + 54))
        self.text(f"P{me['p']}  W{me['w']}  D{me['d']}  L{me['l']}  ·  GD {me['gd']:+d}", "body", MUTED,
                  (r2.x + 20, r2.y + 124))
        x = r2.x + 20
        self.text("Form", "small", MUTED, (x, r2.y + 160))
        for i, f in enumerate(me["form"] or []):
            col = {"W": WIN, "D": DRAW, "L": LOSS}[f]
            pygame.draw.rect(self.win, col, (x + 50 + i * 34, r2.y + 156, 28, 24), border_radius=5)
            self.text(f, "small", (16, 22, 28), (x + 64 + i * 34, r2.y + 159), "midtop")
        b = brd.state(c)
        conf = b["confidence"]
        col = ACCENT if conf >= 60 else DRAW if conf >= brd.WARN_AT else LOSS
        self.text(f"Board: {(b.get('objective') or '').lower()}", "small", MUTED, (x, r2.y + 200))
        bar = pygame.Rect(x, r2.y + 230, r2.w - 140, 12)
        pygame.draw.rect(self.win, PANEL_2, bar, border_radius=6)
        pygame.draw.rect(self.win, col, (bar.x, bar.y, int(bar.w * conf / 100), bar.h), border_radius=6)
        self.text(f"{round(conf)}/100", "small", col, (bar.right + 10, bar.y - 5))
        self.buttons.append(_Invisible(pygame.Rect(x, r2.y + 196, r2.w - 40, 50), lambda: self.go("board")))

        # Mini table
        r3 = pygame.Rect(x0 + 380, 306, W - x0 - 410, 280)
        self.panel(r3, "League table")
        me_i = next(i for i, row in enumerate(t) if row["club"] == mc)
        start = max(0, min(len(t) - 8, me_i - 3))
        self._table_rows(t, r3.x + 14, r3.y + 46, r3.w - 28, compact=True, limit=8, start=start)

        # Last result and team news
        r4 = pygame.Rect(x0, 600, W - x0 - 30, H - 600 - 20)
        self.panel(r4, "Team news")
        last = self._last_result(mc)
        self.text(f"Last result: {last}" if last else "The season hasn't started yet.", "body",
                  TEXT if last else MUTED, (r4.x + 16, r4.y + 44))
        club = c["clubs"][mc]
        today = c.get("date") or ""
        problems = reg.check(club) if "registered" in club else []
        if problems:
            self.text("Squad registration: " + problems[0] + " (Squad > Registration)", "small", LOSS,
                      (r4.right - 16, r4.y + 16), "topright")
        out = [p for p in club["players"] if today and not avail.available(p, today)]
        if out:
            txt = "Unavailable: " + ", ".join(f"{p['Name']} ({avail.status(p, today)})" for p in out)
            self.text(txt[:150], "small", LOSS, (r4.x + 16, r4.y + 72))
        y = r4.y + 98
        for n in avail.club_news(c, mc, 5):
            if y > r4.bottom - 22:
                break
            self.text(f"{cal.fmt(n['date'], False)}   {n['text']}"[:140], "small",
                      {"injury": LOSS, "ban": DRAW}.get(n["kind"], MUTED), (r4.x + 16, y))
            y += 22

    def continue_to_match(self):
        """Continue: on to the day of the next match - unless something needs you
        on the way (an offer for one of your players: it stops there).  A friendly
        before the next league match comes first (career/friendlies.py)."""
        f = friendlies.next_one(self.career)
        if f:
            if f["date"] > self.career["date"]:
                from career import training
                halted = training.run_all(self.career, f["date"], stop=True)
                if halted:
                    self.career["date"] = halted
                    league.save(self.career)
                    self.inbox_sel = None
                    self.inbox_reply = None
                    self.go("inbox")
                    return
                self.career["date"] = f["date"]
                avail.fix_lineups(self.career, f["date"])
            league.save(self.career)
            self.friendly_id = f["id"]
            self.go("friendly")
            return
        reached = league.advance_to_match(self.career, stop=True)
        league.save(self.career)
        if brd.state(self.career).get("sacked"):
            self.go("sacked")
            return
        if not reached:
            self.inbox_sel = None
            self.inbox_reply = None
            self.go("inbox")
            return
        self.go("prematch")

    def _last_result(self, cid):
        for md in sorted(self.career["results"], key=int, reverse=True):
            for r in self.career["results"][md]:
                if cid in (r["home"], r["away"]):
                    return f"{self.name(r['home'], True)} {r['hg']} - {r['ag']} {self.name(r['away'], True)}"
        return None

    def _table_rows(self, t, x, y, w, compact=False, limit=None, start=0):
        mc = self.career["my_club"]
        cols = [("", 0), ("Club", 40), ("P", w - 300), ("W", w - 260), ("D", w - 220), ("L", w - 180),
                ("GD", w - 130), ("Pts", w - 60)]
        if compact:
            cols = [("", 0), ("Club", 34), ("P", w - 140), ("GD", w - 96), ("Pts", w - 44)]
        for label, cx in cols:
            self.text(label, "small", MUTED, (x + cx, y))
        y += 26
        rh = 26 if compact else (36 if len(t) <= 10 else 27)
        shown = t[start:start + limit] if limit else t
        from career import divisions
        zone = {}                                   # promotion / play-offs / relegation (career/divisions.py)
        if divisions.exists(self.career) and t and len(t) == 20 and 0 <= t[0]["club"] < len(self.career["clubs"]):
            if divisions.div_of(self.career["clubs"][t[0]["club"]]) == "pl":
                zone = {p: LOSS for p in range(20 - divisions.DOWN + 1, 21)}
            else:
                zone = {**{p: ACCENT for p in range(1, divisions.UP + 1)}, **{p: DRAW for p in playoffs.SEEDS}}
        for i, row in enumerate(shown, start=start):
            if row["club"] == mc:
                pygame.draw.rect(self.win, HIGHLIGHT, (x - 8, y - 4, w + 16, rh), border_radius=6)
            if i + 1 in zone:
                pygame.draw.rect(self.win, zone[i + 1], (x - 8, y - 2, 4, rh - 4), border_radius=2)
            vals = {"": str(i + 1), "Club": None, "P": row["p"], "W": row["w"], "D": row["d"], "L": row["l"],
                    "GD": f"{row['gd']:+d}", "Pts": row["pts"]}
            row_rect = pygame.Rect(x - 8, y - 4, w + 16, rh)
            if self.screen != "season_end" and row_rect.collidepoint(pygame.mouse.get_pos()) and row["club"] != mc:
                pygame.draw.rect(self.win, PANEL_2, row_rect, border_radius=6)
            for label, cx in cols:
                if label == "Club":
                    _badge(self.win, self.colour(row["club"]), (x + cx + 8, y + 11), 7, self._club_of(row["club"]))
                    self.text(self.name(row["club"], short=compact), "body", TEXT, (x + cx + 22, y))
                else:
                    self.text(vals[label], "body", TEXT if label != "" else MUTED, (x + cx, y))
            if self.screen != "season_end":
                self.buttons.append(_Invisible(row_rect, lambda cid=row["club"]: self.view_squad(cid)))
            y += rh

    # -- squad --------------------------------------------------------------
    def view_squad(self, club_id):
        self.squad_club = club_id
        self.go("squad")

    def view_player(self, club_id, pid):
        self.player_view = (club_id, pid)
        self.player_back = self.screen
        self.go("player")

    def go(self, screen):
        if screen != self.screen:
            self.flash = None
        self.screen = screen
        if screen == "fixtures" and self.career:
            self.fixtures_md = min(self.career["matchday"], len(self.career["fixtures"]))
            self.fixtures_div = None
        if screen == "calendar" and self.career and self.career.get("date"):
            d = cal.parse(self.career["date"])
            self.cal_ym = (d.year, d.month)

    def draw_squad(self):
        W, H = self.size
        cid = getattr(self, "squad_club", None)
        if cid is None:
            cid = self.career["my_club"]
        mine = cid == self.career["my_club"]
        es = cid >= spain.ID_BASE
        self.sidebar("squad" if mine else "spain" if es else "table")
        c = self.club(cid)
        x0 = 250
        if mine:
            self.text("Squad", "h1", TEXT, (x0, 24))
            self.text(f"Your {len(c['players'])} players - click one to see his profile. Pick the XI on the "
                      f"Tactics screen; SUB = on the bench (9).", "body", MUTED, (x0, 76))
        else:
            _badge(self.win, self.colour(cid), (x0 + 18, 48), 18, self._club_of(cid))
            self.text(c["name"], "h1", TEXT, (x0 + 48, 24))
            if 0 <= cid < len(self.career["clubs"]):          # (their history, honours and ground)
                self.buttons.append(Button((W - 30 - 170, 72, 170, 32), "About the club",
                                           lambda: self.open_club_page(cid), font="btn_s"))
            pos = spain.position_of(self.career, cid) if es else league.position_of(self.career, cid)
            from career import divisions
            where = f"the {spain.NAME}" if es else divisions.name(divisions.div_of(c))
            self.text(f"{_ordinal(pos)} in {where}  ·  {STYLE_TEXT[c['tactics']['defence']]}, "
                      f"{BUILD_TEXT[c['tactics']['build_up']]}  ·  click a player to scout him", "body", MUTED,
                      (x0, 76))
        view = getattr(self, "squad_view", "attributes")
        views = (("attributes", "Attributes"), ("contracts", "Contracts"), ("registration", "Registration"))
        if mine:
            views += (("room", "Dressing room"),)
        for i, (key, label) in enumerate(views):
            self.buttons.append(Button((W - 30 - len(views) * 130 + i * 130, 24, 124, 34), label,
                                       lambda k=key: setattr(self, "squad_view", k), primary=view == key,
                                       font="btn_s"))
        if view == "contracts" and "finance" in c:
            return self._squad_contracts(c, x0)
        if view == "room" and mine:
            return self._squad_room(c, x0)
        if view == "registration" and "registered" in c:
            return self._squad_registration(c, x0)
        r = pygame.Rect(x0, 112, W - x0 - 30, H - 132)
        self.panel(r)
        cols = [("Pos", 0), ("Name", 50), ("Age", 270), ("Rating", 316), ("Pace", 386), ("Passing", 446),
                ("Finishing", 521), ("Tackling", 601), ("Heading", 676), ("Fit", 742), ("XI", 798)]
        if mine:                                 # (your own players: how they're feeling - career/morale.py)
            cols = [("Pos", 0), ("Name", 50), ("Age", 266), ("Rating", 308), ("Pace", 368), ("Passing", 420),
                    ("Finishing", 488), ("Tackling", 560), ("Heading", 628), ("Fit", 692), ("Morale", 752),
                    ("XI", 828)]
        y = r.y + 12
        for label, cx in cols:
            self.text(label, "small", MUTED, (r.x + 20 + cx, y))
        y += 26
        in_xi = {pid: slot for slot, pid in c["lineup"].items()}
        today = self.career.get("date") or ""
        out = avail.unavailable_ids(c, today) if today else set()
        bench_ids = {b["id"] for b in clubs_mod.bench(c, out)}
        order = {p: i for i, p in enumerate(["GK", "LB", "LWB", "CB", "RB", "RWB", "DM", "CM", "AM", "LM", "LW",
                                                "RM", "RW", "ST"])}
        mouse = pygame.mouse.get_pos()
        step = min(33, (r.bottom - y - 6) // max(1, len(c["players"])))
        for p in sorted(c["players"], key=lambda p: (order.get(p["Pos"], 99), -clubs_mod.overall(p))):
            row = pygame.Rect(r.x + 10, y - 3, r.w - 20, step - 3)
            if row.collidepoint(mouse):
                pygame.draw.rect(self.win, PANEL_2, row, border_radius=6)
            elif p["id"] in in_xi:
                pygame.draw.rect(self.win, HIGHLIGHT, row, border_radius=6)
            pace = _attr20((p["Acceleration"] + p["Top Speed"]) / 2)
            vals = [p["Pos"], p["Name"], p.get("Age", ""), clubs_mod.overall(p), pace, _attr20(p["Passing"]),
                    _attr20(p["Finishing"]), _attr20(p["Tackling"]), _attr20(p["Heading"]),
                    f"{round(100 * training.condition(p))}%",
                    in_xi.get(p["id"], "SUB" if p["id"] in bench_ids else "")]
            if mine:
                vals.insert(10, morale.label(p))
            st_tag = (avail.status(p, today) if today else "") or ("LOAN" if p.get("loan") else "")
            fs = max(16, step - 6)
            self.win.blit(faces.face_surface(p, fs, self.colour(c["id"]), c), (r.x + 20 + 46, y - 1))
            for (label, cx), v in zip(cols, vals):
                col = TEXT
                if label == "Name":
                    cx += fs + 8
                    nxt = next(x_ for l_, x_ in cols if l_ == "Age")
                    tag_w = self.fonts["small"].size(st_tag)[0] + 10 if st_tag else 0
                    v = self._fit_text(v, "body", nxt - cx - 8 - tag_w)
                if label == "Rating":
                    col = ACCENT if v >= 70 else TEXT if v >= 55 else MUTED
                elif label == "XI":
                    col = ACCENT if v != "SUB" else MUTED
                elif label == "Morale":
                    col = MORALE_COLOUR[morale.colour_key(p)]
                elif label == "Fit":
                    cnd = training.condition(p)
                    col = TEXT if cnd >= 0.95 else DRAW if cnd >= training.FIT_TO_PLAY else LOSS
                elif label in ("Pace", "Passing", "Finishing", "Tackling", "Heading"):
                    col = _attr_colour(v)
                self.text(v, "body", col, (r.x + 20 + cx, y))
            st = avail.status(p, today) if today else ""
            if p.get("loan"):
                st = "LOAN" if not st else st
            if st:
                age_x = next(x_ for l_, x_ in cols if l_ == "Age")
                self.text(st, "small", LOSS if st.startswith("INJ") else DRAW, (r.x + 20 + age_x - 10, y + 2), "topright")
            self.buttons.append(_Invisible(row, lambda pid=p["id"]: self.view_player(cid, pid)))
            y += step

    def _toggle_reg(self, c, p):
        regd = reg.registered_ids(c)
        if p["id"] in regd:
            c["registered"].remove(p["id"])
            self.flash = None
        else:
            ok, why = reg.can_register(c, p)
            if ok:
                c.setdefault("registered", []).append(p["id"])
                self.flash = None
            else:
                self.flash = why
        league.save(self.career)

    def _squad_registration(self, c, x0):
        W, H = self.size
        today = self.career["date"]
        open_ = trf.in_window(today)
        mine = c["id"] == self.career["my_club"]
        n, non_hg = reg.counts(c)
        r = pygame.Rect(x0, 112, W - x0 - 30, H - 132)
        self.panel(r)
        es = c.get("league") == "es"
        head = (f"Registered {n} / {reg.MAX_SQUAD}   ·   {reg.foreign_label(c)} {non_hg} / {reg.max_foreign(c)}   ·   "
                + ("22 and under play from the B team" if es else "under-21s don't need registering"))
        self.text(head, "body", TEXT, (r.x + 20, r.y + 12))
        rule = ("The window is open - click a player to add him to or take him off the list." if open_ and mine else
                "The list is fixed until the next transfer window." if mine else "")
        self.text(rule, "small", ACCENT if open_ else MUTED, (r.x + 20, r.y + 38))
        if getattr(self, "flash", None):
            self.text(self.flash, "small", LOSS, (r.x + 560, r.y + 38))
        cols = [("Pos", 0), ("Name", 50), ("Age", 270), ("Rating", 320), ("Non-EU" if es else "Homegrown", 400),
                ("Status", 520)]
        y = r.y + 66
        for label, cx in cols:
            self.text(label, "small", MUTED, (r.x + 20 + cx, y))
        y += 24
        order = {p: i for i, p in enumerate(["GK", "LB", "LWB", "CB", "RB", "RWB", "DM", "CM", "AM", "LM", "LW",
                                                "RM", "RW", "ST"])}
        step = min(30, (r.bottom - y - 6) // max(1, len(c["players"])))
        regd = reg.registered_ids(c)
        mouse = pygame.mouse.get_pos()
        for p in sorted(c["players"], key=lambda p: (order.get(p["Pos"], 99), -clubs_mod.overall(p))):
            row = pygame.Rect(r.x + 10, y - 3, r.w - 20, step - 3)
            if row.collidepoint(mouse) and open_ and mine and not reg.is_u21(p):
                pygame.draw.rect(self.win, PANEL_2, row, border_radius=6)
            if reg.is_u21(p, c):
                st, col = ("B team - can play" if es else "Under-21 - can play"), MUTED
            elif p["id"] in regd:
                st, col = "Registered", ACCENT
            else:
                st, col = "Not registered - can't play", LOSS
            flag = p.get("non_eu") if es else reg.homegrown(p)
            vals = [p["Pos"], p["Name"], p.get("Age", ""), clubs_mod.overall(p), "Yes" if flag else "-", st]
            for (label, cx), v in zip(cols, vals):
                self.text(v, "body" if label != "Status" else "small", col if label == "Status" else TEXT,
                          (r.x + 20 + cx, y + (2 if label == "Status" else 0)))
            if open_ and mine and not reg.is_u21(p):
                self.buttons.append(_Invisible(row, lambda p=p: self._toggle_reg(c, p)))
            y += step

    def _squad_contracts(self, c, x0):
        W, H = self.size
        r = pygame.Rect(x0, 112, W - x0 - 30, H - 132)
        self.panel(r)
        today = self.career.get("date")
        cols = [("Pos", 0), ("Name", 50), ("Age", 270), ("Rating", 320), ("Value", 400), ("Wage", 510),
                ("Contract until", 630), ("Status", 750)]
        y = r.y + 12
        for label, cx in cols:
            self.text(label, "small", MUTED, (r.x + 20 + cx, y))
        y += 26
        order = {p: i for i, p in enumerate(["GK", "LB", "LWB", "CB", "RB", "RWB", "DM", "CM", "AM", "LM", "LW",
                                                "RM", "RW", "ST"])}
        mouse = pygame.mouse.get_pos()
        step = min(33, (r.bottom - y - 6) // max(1, len(c["players"])))
        for p in sorted(c["players"], key=lambda p: (order.get(p["Pos"], 99), -clubs_mod.overall(p))):
            row = pygame.Rect(r.x + 10, y - 3, r.w - 20, step - 3)
            if row.collidepoint(mouse):
                pygame.draw.rect(self.win, PANEL_2, row, border_radius=6)
            left = fin.contract_years_left(p, today) if today else 3
            end = p.get("contract_end")
            vals = [p["Pos"], p["Name"], p.get("Age", ""), clubs_mod.overall(p), fin.money(fin.value(p, today)),
                    fin.weekly(p.get("wage", 0)), cal.fmt(end)[4:] if end else "-",
                    "Ending" if left < 1 else ""]
            for (label, cx), v in zip(cols, vals):
                col = LOSS if label == "Status" or (label == "Contract until" and left < 1) else TEXT
                self.text(v, "body" if label != "Status" else "small", col, (r.x + 20 + cx, y + (2 if label == "Status" else 0)))
            self.buttons.append(_Invisible(row, lambda pid=p["id"]: self.view_player(c["id"], pid)))
            y += step

    # -- contract talks ----------------------------------------------------
    def open_talks(self, cid, pid):
        club = self.club(cid)
        p = clubs_mod.player_by_id(club, pid)
        me = self._my_club()
        renewal = cid == self.career["my_club"] or bool(p.get("loan") and p["loan"]["from"] == self.career["my_club"])
        if not renewal:
            ok, why = trf.will_talk(self.career, cid, p)
            if not ok:
                self.flash = why
                return
            if cid >= 0 or cid == -2:
                p["_from_rank"] = fin.stature(self.career, club) if cid >= 0 else 10
        # Opening offer: what he's asking for
        target = (me if p.get("loan") else club) if renewal else me
        want, rounds, counter, _ = con.talk_state(self.career, target, p, renewal)
        offer = dict(counter) if counter else con.asking(want)
        if not counter:                                 # (start a little under what he's asking)
            offer["wage"] = fin._round_wage(want["wage"] * 0.9)
            offer["agent_fee"] = con._round_money(want["agent_fee"] * 0.8)
        self.talk = {"cid": cid, "pid": pid, "renewal": renewal, "reply": None, "done": False, "offer": offer,
                     "counter": counter}
        self.talk_back = self.screen
        self.go("talks")

    def _talk_adjust(self, key, delta):
        o = self.talk["offer"]
        if key == "wage":
            step = 5000 if o["wage"] >= 50000 else 1000 if o["wage"] >= 10000 else 250
            o["wage"] = max(500, o["wage"] + delta * step)
        elif key in ("signing_fee", "agent_fee"):
            v = o.get(key, 0)
            step = 1_000_000 if v >= 10_000_000 else 250_000 if v >= 2_000_000 else 50_000 if v >= 250_000 else 10_000
            if delta < 0 and v <= step:
                step = v
            o[key] = max(0, v + delta * step)
        elif key in ("appearance", "goal_bonus"):
            v = o.get(key, 0)
            step = 5000 if v >= 20_000 else 1000 if v >= 5000 else 500
            if delta < 0 and v <= step:
                step = v
            o[key] = max(0, v + delta * step)
        elif key == "release_clause":
            o["release_clause"] = max(0, o["release_clause"] + delta * 5_000_000)

    def _talk_propose(self):
        tk = self.talk
        me = self._my_club()
        club = self.club(tk["cid"])
        p = clubs_mod.player_by_id(club, tk["pid"])
        o = dict(tk["offer"])
        if not o.get("release_clause"):
            o.pop("release_clause", None)
        extra = (o["wage"] - (p.get("wage", 0) if tk["renewal"] else 0)) 
        room = con.wage_room(self.career, me)
        if extra > room:
            tk["reply"] = (f"The board won't allow it: that's {fin.weekly(extra)} more than now, and the wage "
                           f"budget has {fin.weekly(room)} left.")
            return
        if o.get("signing_fee", 0) + o.get("agent_fee", 0) > me["finance"]["balance"]:
            tk["reply"] = "The club can't afford those fees."
            return
        # Free agents negotiate against your club (where they'd be going)
        target = (me if p.get("loan") else club) if tk["renewal"] else me
        ok, reply = con.make_offer(self.career, target, p, o, tk["renewal"])
        tk["reply"] = reply
        if ok:
            if tk["renewal"]:
                con.sign(self.career, me, p, o)
            else:
                bid = trf.agreed_bid(self.career, tk["cid"], p) or {"fee": 0}
                if bid["fee"] > me["finance"]["balance"] + 50 * fin.M and bid["fee"] > 0:
                    tk["reply"] = "The club hasn't the money in the bank to complete the deal."
                    return
                trf.complete(self.career, tk["cid"], p, bid, o)
                tk["reply"] = "Deal done - he's signed! " + (tk["reply"] or "")
            tk["done"] = True
            league.save(self.career)
        else:
            t = self.career.get("talks", {}).get(con._key(target, p))
            if t and t.get("counter"):
                tk["counter"] = t["counter"]

    def draw_talks(self):
        W, H = self.size
        tk = self.talk
        me = self._my_club()
        club = self.club(tk["cid"])
        p = clubs_mod.player_by_id(club, tk["pid"])
        self.sidebar("squad" if tk["renewal"] else "freeagents")
        x0 = 250
        if p is None:
            return self.go("home")
        self._face(p, tk["cid"], 80, (x0, 16))
        self.text(f"Contract talks: {p['Name']}", "h1", TEXT, (x0 + 96, 18))
        cur = (f"Now on {fin.weekly(p.get('wage', 0))} until {cal.fmt(p['contract_end'])[4:]}" if tk["renewal"]
               and p.get("contract_end") else f"Free agent, last at {p.get('_from_club', '?')}")
        self.text(f"{p['Pos']}, {p['Age']}  ·  rated {clubs_mod.overall(p)}  ·  {cur}", "body", MUTED, (x0 + 96, 70))
        o = tk["offer"]
        for k_ in ("signing_fee", "agent_fee", "appearance", "goal_bonus", "rise", "release_clause"):
            o.setdefault(k_, 0)
        up_top = fin.league_of(me) == "pl"
        if up_top:
            o.setdefault("relegation_cut", fin.club_clause(me))      # (the club's standard clause to start with)
        else:
            o.pop("relegation_cut", None)
        r = pygame.Rect(x0, 106, 600, 600)
        self.panel(r, "Your offer")
        y = r.y + 50
        RH = 42
        def row(label, value, key=None):
            nonlocal y
            self.text(label, "body", MUTED, (r.x + 16, y + 8))
            self.text(value, "h3", TEXT, (r.x + 200, y + 6))
            if key:
                self.buttons.append(Button((r.right - 116, y, 44, 36), "-", lambda: self._talk_adjust(key, -1)))
                self.buttons.append(Button((r.right - 64, y, 44, 36), "+", lambda: self._talk_adjust(key, 1)))
            y += RH
        row("Wage", fin.weekly(o["wage"]), "wage")
        self.text("Length", "body", MUTED, (r.x + 16, y + 8))
        for i in range(1, 6):
            self.buttons.append(Button((r.x + 200 + (i - 1) * 64, y, 58, 36), f"{i} yr",
                                       lambda i=i: o.__setitem__("years", i), primary=o["years"] == i, font="btn_s"))
        y += RH
        self.text("Squad status", "body", MUTED, (r.x + 16, y + 8))
        for i, st in enumerate(con.STATUSES):
            bx = r.x + 200 + (i % 3) * 112
            by = y + (i // 3) * 40
            self.buttons.append(Button((bx, by, 106, 34), st, lambda st=st: o.__setitem__("status", st),
                                       primary=o["status"] == st, font="btn_s"))
        y += 80
        row("Signing-on fee", fin.money(o["signing_fee"]) if o["signing_fee"] else "none", "signing_fee")
        row("Agent's fee", fin.money(o["agent_fee"]) if o["agent_fee"] else "none", "agent_fee")
        row("Appearance fee", f"{fin.money(o['appearance'])} a game" if o["appearance"] else "none", "appearance")
        gk = con.bonus_kind(p) == "goal"
        row("Goal bonus" if gk else "Clean-sheet bonus",
            f"{fin.money(o['goal_bonus'])} a {'goal' if gk else 'clean sheet'}" if o["goal_bonus"] else "none",
            "goal_bonus")
        self.text("Yearly pay rise", "body", MUTED, (r.x + 16, y + 8))
        for i, pct in enumerate((0, 5, 10, 15)):
            self.buttons.append(Button((r.x + 200 + i * 70, y, 64, 36), "none" if pct == 0 else f"{pct}%",
                                       lambda pct=pct: o.__setitem__("rise", pct), primary=o["rise"] == pct,
                                       font="btn_s"))
        y += RH
        row("Release clause", fin.money(o["release_clause"]) if o["release_clause"] else "none", "release_clause")
        if up_top:
            self.text("If we go down", "body", MUTED, (r.x + 16, y + 8))
            for i, pct in enumerate((0, 25, 40, 50)):
                self.buttons.append(Button((r.x + 200 + i * 86, y, 80, 36), "no cut" if pct == 0 else f"-{pct}%",
                                           lambda pct=pct: o.__setitem__("relegation_cut", pct),
                                           primary=o.get("relegation_cut") == pct, font="btn_s"))
            self.text("His wage is cut by this if we're relegated - the likelier that looks, the more he'll want for it.",
                      "tiny", MUTED, (r.x + 16, y + 42))
            y += RH
        if not tk["done"]:
            self.buttons.append(Button((r.x + 16, r.bottom - 58, 200, 46), "Make offer", self._talk_propose,
                                       primary=True))
            if tk.get("counter"):
                self.buttons.append(Button((r.x + 230, r.bottom - 58, 200, 46), "Use his terms",
                                           lambda: self.talk.__setitem__("offer", dict(self.talk["counter"]))))
        # The other side: his agent
        r2 = pygame.Rect(r.right + 16, 106, W - r.right - 46, 600)
        self.panel(r2, "His agent")
        y = r2.y + 50
        target = (me if p.get("loan") else club) if tk["renewal"] else me
        want, rounds, _, t = con.talk_state(self.career, target, p, tk["renewal"])
        lines = [(f"Asking for around {fin.weekly(want['wage'])}, {want['years']} years, "
                  f"as {con.STATUS_AS[want['status']]}.", TEXT)]
        extra = []
        if want.get("signing_fee"):
            extra.append(f"a {fin.money(want['signing_fee'])} signing-on fee")
        extra.append(f"{fin.money(want['agent_fee'])} for the agent")
        lines.append(("Plus " + " and ".join(extra) + ".", TEXT))
        lines.append((f"What matters most to him: {con.CONCERN_TEXT[want['concern']]}.", ACCENT_HI))
        for txt, col in lines:
            y = self._wrap(txt, "body", col, r2.x + 16, y, r2.w - 32) + 8
        y += 6
        if t is not None and not tk["done"]:
            self.text(f"Mood: {con.mood(t)}", "body", DRAW if t["want"]["patience"] - t["rounds"] > 1 else LOSS,
                      (r2.x + 16, y)); y += 34
        if tk.get("reply"):
            y = self._wrap(tk["reply"], "body", ACCENT if tk["done"] else LOSS, r2.x + 16, y, r2.w - 32) + 10
        c_ = tk.get("counter")
        if c_ and not tk["done"]:
            bits = [f"{fin.weekly(c_['wage'])}", f"{c_['years']} yrs", c_["status"].lower()]
            if c_.get("signing_fee"):
                bits.append(f"{fin.money(c_['signing_fee'])} signing-on")
            if c_.get("agent_fee"):
                bits.append(f"{fin.money(c_['agent_fee'])} agent")
            if c_.get("appearance") or c_.get("goal_bonus") or c_.get("rise"):
                bits.append("with your bonuses")
            y = self._wrap("He'd sign for: " + ", ".join(bits) + ".", "body", TEXT, r2.x + 16, y, r2.w - 32) + 8
        self.text(f"Value: {fin.money(fin.value(p, self.career.get('date')))}", "small", MUTED,
                  (r2.x + 16, r2.bottom - 30))
        # Budget
        room = con.wage_room(self.career, me)
        self.text(f"Wage budget left: {fin.weekly(room)}  ·  bank {fin.money(me['finance']['balance'])}  ·  "
                  f"bonuses are paid as they happen; pay rises each 1 July", "small", MUTED, (x0, r.bottom + 10))
        back = getattr(self, "talk_back", "squad")
        self.buttons.append(Button((x0, H - 66, 160, 46), "Back", lambda: self.go(back)))

    # -- free agents ------------------------------------------------------
    # -- selling and the inbox ---------------------------------------------
    def _list_player(self, p, on):
        if on:
            p["listed"] = True
            p["asking"] = fin.value(p, self.career["date"])
        else:
            p.pop("listed", None)
            p.pop("asking", None)
        league.save(self.career)

    def _asking(self, p, delta):
        a = p.get("asking", 0)
        step = 5 * fin.M if a >= 50 * fin.M else fin.M if a >= 10 * fin.M else 250_000
        p["asking"] = max(step, a + delta * step)

    def _loan_answer(self, mid, action):
        self.inbox_reply = lns.respond(self.career, mid, action)
        league.save(self.career)

    def _loan_list(self, p):
        p["loan_listed"] = not p.get("loan_listed")
        league.save(self.career)

    def _loan_buy(self, p):
        me = self._my_club()
        fee = p["loan"]["option"]
        if fee > me["finance"].get("transfer_budget", 0):
            self.flash = f"The board won't allow it: the transfer budget is {fin.money(me['finance'].get('transfer_budget', 0))}."
            return
        lns.end(self.career, me, p, buy=True)
        league.save(self.career)

    def _loan_recall(self, p, club):
        lns.recall(self.career, p, club)
        league.save(self.career)
        self.go(getattr(self, "player_back", "squad"))

    def open_loan(self, cid, pid):
        club = self.club(cid)
        p = clubs_mod.player_by_id(club, pid)
        self.loan = {"cid": cid, "pid": pid, "reply": None, "done": False,
                     "terms": {"fee": 0, "share": 0.5, "half": False, "option": None, "obligation": False,
                               "recall": False}}
        self.loan_back = self.screen
        self.go("loan")

    def _loan_send(self):
        L = self.loan
        club = self.club(L["cid"])
        p = clubs_mod.player_by_id(club, L["pid"])
        t = dict(L["terms"])
        t["until"] = lns.half_end(self.career["date"]) if t.pop("half") else lns.default_end(self.career["date"])
        ok, reply = lns.ask(self.career, L["cid"], p, t)
        L["reply"], L["done"] = reply, ok
        league.save(self.career)

    def _to_room(self):
        self.squad_club = self.career["my_club"]
        self.squad_view = "room"
        self.go("squad")

    def open_chat(self, pid, back="player"):
        self.chat = {"pid": pid, "conv": None, "back": back}
        self.go("chat")

    # -- the dressing room at a glance (Squad screen) ---------------------------
    def _squad_room(self, club, x0):
        W, H = self.size
        c = self.career
        today = c["date"]
        here = [p for p in club["players"] if p.get("loan", {}).get("to") in (None, club["id"])]
        # left: the mood, the armband, the last talks
        r = pygame.Rect(x0, 110, 330, H - 140)
        self.panel(r, "The mood")
        y = r.y + 54
        avg = sum(morale.level(p) for p in here) / max(1, len(here))
        read = ("Buzzing - the lads are flying." if avg >= 70 else "In good spirits." if avg >= 58 else
                "Mostly fine, a few grumbles." if avg >= 48 else "Flat - heads are down." if avg >= 38 else
                "Poor. The dressing room is unhappy.")
        y = self._wrap(f"Your assistant: \u201c{read}\u201d", "body", TEXT, r.x + 16, y, r.w - 32) + 10
        for cut, name in morale.LABELS:
            n = sum(1 for p in here if morale.label(p) == name)
            key = "good" if cut >= 65 else "ok" if cut >= 45 else "bad"
            self.text(name, "body", MORALE_COLOUR[key], (r.x + 16, y))
            bw = int((r.w - 150) * n / max(1, len(here)))
            pygame.draw.rect(self.win, MORALE_COLOUR[key], (r.x + 110, y + 6, max(2, bw), 12), border_radius=3)
            self.text(str(n), "small", MUTED, (r.x + 118 + bw, y + 2))
            y += 28
        y += 10
        cap, vice = captains.armband(club)
        for label, p in (("Captain", cap), ("Vice-captain", vice)):
            self.text(label, "small", MUTED, (r.x + 16, y))
            if p is not None:
                self.text(self._fit_text(f"{p['Name']}  ·  {morale.label(p)}", "body", r.w - 130), "body", TEXT,
                          (r.x + 120, y - 3))
            else:
                self.text("none - pick one on Tactics", "small", MUTED, (r.x + 120, y))
            y += 28
        y += 10
        talks = club.get("talks") or {}
        last = talks.get("last")
        if last:
            words = dict(teamtalk.PRE + teamtalk.POST).get(last["key"], "")
            when = "Before the last game" if last["phase"] == "pre" else "After the last game"
            self.text(when + ":", "small", MUTED, (r.x + 16, y)); y += 20
            y = self._wrap(f"\u201c{words}\u201d - {self._talk_summary(club, last)}", "small", TEXT, r.x + 16, y,
                           r.w - 32) + 8
        hl = talks.get("half_last")
        if hl:
            who = "you" if hl.get("by") == "you" else "your assistant"
            self.text(f"Half-time, last game ({who}):", "small", MUTED, (r.x + 16, y)); y += 20
            self._wrap(f"\u201c{dict(teamtalk.HALF).get(hl['key'], '')}\u201d", "small", TEXT, r.x + 16, y, r.w - 32)
        # right: who needs you
        r2 = pygame.Rect(r.right + 16, 110, W - r.right - 46, H - 140)
        self.panel(r2, "Who needs a word")
        y = r2.y + 50
        def flags(p):
            out = []
            if p.get("wants_out"):
                out.append(("Wants to leave", LOSS))
            elif p.get("listed"):
                out.append(("Transfer listed", MUTED))
            pr = p.get("promise")
            if pr:
                out.append((f"Promised games ({cal.fmt(pr['check'])[4:10].strip()})", ACCENT_HI))
            return out
        worry = sorted((p for p in here if morale.level(p) < 45 or p.get("wants_out") or p.get("promise")),
                       key=morale.level)
        if not worry:
            self._wrap("Nobody - everyone's at least OK. Enjoy it while it lasts.", "body", MUTED, r2.x + 16, y, r2.w - 32)
        rowh = 58
        room = max(1, (r2.bottom - y - 150) // rowh)
        for p in worry[:room]:
            self._face(p, club["id"], 44, (r2.x + 16, y))
            nm = self._fit_text(p["Name"], "body", 190)
            self.text(nm, "body", TEXT, (r2.x + 70, y))
            lx = r2.x + 70 + self.fonts["body"].size(nm)[0] + 12
            self.text(morale.label(p), "body", MORALE_COLOUR[morale.colour_key(p)], (lx, y))
            lx += self.fonts["body"].size(morale.label(p))[0] + 14
            told = p.get("told") or {}
            note = morale.assistant_note(p)
            if note:
                why = note
            elif told and cal.days_between(told["date"], today) <= 30:
                why = f"He told you he's {told['text']}."
            else:
                why = "Keeps it to himself - talk to him to find out why."
            fl = flags(p)
            self.text(self._fit_text(why, "small", r2.w - 196), "small", MUTED, (r2.x + 70, y + 24))
            for text, col in fl[:1]:
                self.text(self._fit_text(text, "small", r2.right - lx - 120), "small", col, (lx, y + 3))
            ok, _ = chats.can_talk(c, p)
            self.buttons.append(Button((r2.right - 106, y + 4, 90, 36), "Talk", lambda pid=p["id"]: self.open_chat(pid, "squad"),
                                       enabled=ok, font="btn_s"))
            y += rowh
        if len(worry) > room:
            self.text(f"...and {len(worry) - room} more.", "small", MUTED, (r2.x + 16, y)); y += 24
        y = max(y, r2.bottom - 130)
        pygame.draw.line(self.win, LINE, (r2.x + 16, y), (r2.right - 16, y))
        y += 12
        self.text("Flying", "small", MUTED, (r2.x + 16, y)); y += 22
        best = sorted((p for p in here if morale.level(p) >= 80), key=lambda p: -morale.level(p))
        if not best:
            self.text("Nobody's Superb right now.", "small", MUTED, (r2.x + 16, y))
        x = r2.x + 16
        for p in best[:max(1, (r2.w - 32) // 84)]:
            self._face(p, club["id"], 40, (x, y))
            self.text(self._fit_text(p["Name"].split(" ")[-1], "small", 76), "small", TEXT, (x - 2, y + 44))
            self.buttons.append(_Invisible(pygame.Rect(x, y, 70, 64), lambda pid=p["id"]: self.view_player(club["id"], pid)))
            x += 84

    def _chat_from_inbox(self, m, topic):
        """He asked to see you / his transfer request: straight into the conversation (career/dialogue.py)."""
        from career import dialogue
        club = self._my_club()
        p = clubs_mod.player_by_id(club, m["data"]["pid"])
        if p is None:
            return
        if m["data"].get("talked"):
            return
        m["data"]["talked"] = True                         # (one go at talking him round)
        self.chat = {"pid": p["id"], "back": "inbox", "conv": dialogue.start(self.career, club, p, topic, mid=m["id"])}
        p["last_chat"] = self.career["date"]
        self.inbox_reply = None
        self.go("chat")
        self._chat_after()

    def draw_chat(self):
        """Talking to one of your players: a back-and-forth (career/dialogue.py)."""
        from career import dialogue
        W, H = self.size
        self.sidebar("squad")
        x0 = 250
        club = self._my_club()
        p = clubs_mod.player_by_id(club, self.chat["pid"])
        if p is None:
            return self.go("squad")
        self.win.blit(faces.face_surface(p, 88, self.colour(club["id"]), club), (x0, 12))
        pygame.draw.rect(self.win, LINE, (x0, 12, 88, 88), 1, border_radius=4)
        self.text(f"Talk to {p['Name']}", "h1", TEXT, (x0 + 104, 18))
        self.text(f"{p['Pos']}, {p['Age']}  ·  morale ", "body", MUTED, (x0 + 104, 70))
        lw = self.fonts["body"].size(f"{p['Pos']}, {p['Age']}  ·  morale ")[0]
        self.text(morale.label(p), "body", MORALE_COLOUR[morale.colour_key(p)], (x0 + 104 + lw, 70))
        conv = self.chat.get("conv")
        back = self.chat.get("back", "player")
        self.buttons.append(Button((x0, H - 66, 200 if back == "inbox" else 160, 46), "Back to inbox" if back == "inbox" else "Back",
                                   lambda: self.go(back)))
        if conv is None:                                   # pick what to talk about
            r = pygame.Rect(x0, 110, 420, H - 196)
            self.panel(r, "What do you want to talk about?")
            ok, why = dialogue.can_talk(self.career, p)
            y = r.y + 56
            if not ok:
                for line in self._lines(why, "body", r.w - 32):
                    self.text(line, "body", MUTED, (r.x + 16, y)); y += 24
            else:
                for key, label, allowed, why_not in dialogue.topics(self.career, club, p):
                    self.buttons.append(Button((r.x + 16, y, r.w - 32, 40), label, lambda k=key: self._chat_start(k),
                                               enabled=allowed, font="btn_s"))
                    if not allowed:
                        self.text(why_not, "small", MUTED, (r.x + 20, y + 42))
                        y += 18
                    y += 50
            r2 = pygame.Rect(r.right + 16, 110, W - r.right - 46, H - 196)
            self.panel(r2, "Before you start")
            y = r2.y + 56
            tips = ["Every player is different: some want it straight, some need an arm round them, "
                    "and a hot-head won't take criticism well.",
                    "How he answers tells you about him - and his mood will move as you talk.",
                    "One chat per player a week."]
            note = chats.character_note(p)
            if note:
                tips.insert(0, note)
            for tip in tips:
                for line in self._lines(tip, "body", r2.w - 40):
                    self.text(line, "body", MUTED, (r2.x + 20, y)); y += 24
                y += 12
            return
        # the conversation so far
        r = pygame.Rect(x0, 110, W - x0 - 30, H - 196)
        pygame.draw.rect(self.win, PANEL, r, border_radius=10)
        first = p["Name"].split(" ")[0]
        bw = int(r.w * 0.68)
        bubbles = []
        for who, line in conv["log"]:
            font = "body"
            rows = self._lines(line if who == "you" else f"\u201c{line}\u201d", font, bw - 28)
            bubbles.append((who, rows))
        # choices / the end, at the bottom of the panel
        foot = []
        if conv["done"]:
            foot = [(o, ACCENT_HI) for o in conv["outcome"]]
            d = conv["delta"]
            if abs(d) >= 1.0:
                foot.append(("He's " + ("happier" if d > 0 else "less happy") + f" for that chat - morale now {morale.label(p)}.",
                             MORALE_COLOUR["good" if d > 0 else "bad"]))
            else:
                foot.append((f"No real change - morale {morale.label(p)}.", MUTED))
        foot_h = (len(conv["choices"]) * 46 + 14) if conv["choices"] else (len(foot) * 24 + 20)
        # fit as many bubbles as we can above the footer (newest at the bottom)
        avail_h = r.h - foot_h - 24
        heights = [len(rows) * 24 + 18 + (20 if who == "him" else 0) for who, rows in bubbles]
        start, used = len(bubbles), 0
        while start > 0 and used + heights[start - 1] + 8 <= avail_h:
            start -= 1
            used += heights[start] + 8
        y = r.y + 12
        for (who, rows), h in zip(bubbles[start:], heights[start:]):
            w = max(self.fonts["body"].size(row)[0] for row in rows) + 28
            if who == "him":
                bx = r.x + 16
                self.text(first, "small", MUTED, (bx + 4, y))
                y += 20
                box = pygame.Rect(bx, y, max(w, 60), h - 20)
                pygame.draw.rect(self.win, PANEL_2, box, border_radius=10)
                col = TEXT
            else:
                box = pygame.Rect(r.right - 16 - w, y, w, h)
                pygame.draw.rect(self.win, HIGHLIGHT, box, border_radius=10)
                col = ACCENT_HI
            ty = box.y + 9
            for row in rows:
                self.text(row, "body", col, (box.x + 14, ty)); ty += 24
            y = box.bottom + 8
        fy = r.bottom - foot_h
        pygame.draw.line(self.win, LINE, (r.x + 12, fy - 6), (r.right - 12, fy - 6))
        if conv["choices"]:
            for i, (label, _) in enumerate(conv["choices"]):
                self.buttons.append(Button((r.x + 16, fy + 4 + 46 * i, r.w - 32, 40), label,
                                           lambda i=i: self._chat_pick(i), font="btn_s"))
        else:
            fy += 8
            for text, col in foot:
                self.text(self._fit_text(text, "body", r.w - 40), "body", col, (r.x + 20, fy)); fy += 24

    # -- team talks (career/teamtalk.py) ---------------------------------------
    def open_talk(self, phase):
        self.talk_phase = phase
        self.talk_out = None
        self.go("teamtalk")

    def _talk_ctx(self):
        me = self._my_club()
        phase = getattr(self, "talk_phase", "pre")
        if phase == "post" and not getattr(self, "my_result", None):
            phase = self.talk_phase = "pre"
        return teamtalk.context(self.career, me, phase, self.my_result if phase == "post" else None)

    def _talk_summary(self, me, last):
        out = [(clubs_mod.player_by_id(me, pid), d, w) for pid, d, w in last.get("reactions", [])]
        return teamtalk.summary([x for x in out if x[0] is not None], last.get("thin"))

    def _give_talk(self, key):
        me = self._my_club()
        if teamtalk.done(self.career, me, self.talk_phase):
            return
        self.talk_out = teamtalk.give(self.career, me, self._talk_ctx(), key)
        league.save(self.career)

    def draw_teamtalk(self):
        W, H = self.size
        phase = getattr(self, "talk_phase", "pre")
        back = "prematch" if phase == "pre" else "results"
        x0 = 250 if phase == "pre" else 40
        if phase == "pre":
            self.sidebar("home")
        me = self._my_club()
        ctx = self._talk_ctx()
        self.text("Team talk" if phase == "pre" else "Full-time team talk", "h1", TEXT, (x0, 18))
        self.text(teamtalk.situation(ctx), "body", MUTED, (x0, 72))
        r = pygame.Rect(x0, 110, 470, H - 196)
        self.panel(r, "What do you tell them?")
        last = (me.get("talks") or {}).get("last") or {}
        given = teamtalk.done(self.career, me, phase) and last.get("phase") == phase
        y = r.y + 54
        for key, words, ok, why in teamtalk.options(self.career, me, ctx):
            chosen = given and last.get("key") == key
            self.buttons.append(Button((r.x + 16, y, r.w - 32, 44), words, lambda k=key: self._give_talk(k),
                                       enabled=chosen or (ok and not given), primary=chosen, font="btn_s"))
            if not ok:
                self.text(why, "small", MUTED, (r.x + 20, y + 46))
                y += 18
            y += 54
        r2 = pygame.Rect(r.right + 16, 110, W - r.right - 46, H - 196)
        self.panel(r2, "How they took it")
        y = r2.y + 54
        if not given:
            tips = ["Read the situation: what fires up underdogs can make favourites complacent.",
                    "Every player takes it his own way - some need calming, some need a kick.",
                    "Say the same thing every week and they stop listening."]
            for tip in tips:
                y = self._wrap(tip, "body", MUTED, r2.x + 20, y, r2.w - 40) + 10
        else:
            y = self._wrap(self._talk_summary(me, last), "body", TEXT, r2.x + 20, y, r2.w - 40) + 12
            rows = [(clubs_mod.player_by_id(me, pid), d, w) for pid, d, w in last["reactions"]]
            rows = [x for x in rows if x[0] is not None]
            rows.sort(key=lambda x: -x[1])
            surnames = [p["Name"].split(" ")[-1] for p, _, _ in rows]
            per = max(1, (r2.bottom - y - 10) // 24)
            colw = (r2.w - 40) // (1 if len(rows) <= per else 2)
            for i, (p, d, w) in enumerate(rows[:per * 2]):
                cx, cy = r2.x + 20 + (i // per) * colw, y + (i % per) * 24
                col = MORALE_COLOUR["good" if d >= 0.8 else "bad" if d <= -0.6 else "ok"]
                sn = p["Name"].split(" ")[-1]
                label = f"{p['Name'][0]}. {sn}" if surnames.count(sn) > 1 else sn
                self._face(p, me["id"], 20, (cx, cy - 1), border=False)
                self.text(self._fit_text(label, "small", colw - 146), "small", TEXT, (cx + 26, cy))
                self.text(w, "small", col, (cx + colw - 12, cy), "topright")
        self.buttons.append(Button((x0, H - 66, 200, 46), "Back to the match" if phase == "pre" else "Back to results",
                                   lambda: self.go(back)))

    def _chat_start(self, key):
        from career import dialogue
        club = self._my_club()
        p = clubs_mod.player_by_id(club, self.chat["pid"])
        if not dialogue.can_talk(self.career, p)[0]:
            return
        self.chat["conv"] = dialogue.start(self.career, club, p, key)
        p["last_chat"] = self.career["date"]             # (walking out halfway still counts as this week's chat)
        self._chat_after()

    def _chat_pick(self, i):
        from career import dialogue
        conv = self.chat.get("conv")
        if conv and not conv["done"] and i < len(conv["choices"]):
            dialogue.choose(conv, i)
            self._chat_after()

    def _chat_after(self):
        conv = self.chat["conv"]
        club = self._my_club()
        p = clubs_mod.player_by_id(club, self.chat["pid"])
        if conv.get("rested") and not conv.get("swapped"):  # someone else takes his place in the XI
            conv["swapped"] = True
            slot = next((s_ for s_, pid in club["lineup"].items() if pid == p["id"]), None)
            if slot:
                out = avail.unavailable_ids(club, self.career["date"])
                used = set(club["lineup"].values())
                cands = [q for q in club["players"] if q["id"] not in used and q["id"] not in out
                         and not q.get("rest_for")]
                if cands:
                    club["lineup"][slot] = max(cands, key=lambda q: clubs_mod.overall(q, slot))["id"]
        league.save(self.career)

    def draw_loan(self):
        W, H = self.size
        L = self.loan
        club = self.club(L["cid"])
        p = clubs_mod.player_by_id(club, L["pid"])
        self.sidebar("transfers")
        x0 = 250
        if p is None:                                   # (he's ours now)
            me = self._my_club()
            p = next((q for q in me["players"] if q.get("loan") and q["loan"]["from"] == L["cid"]), None)
            if p is None:
                return self.go("transfers")
        self.text(f"Loan: {p['Name']}", "h1", TEXT, (x0, 18))
        self.text(f"{p['Pos']}, {p['Age']}  ·  rated {clubs_mod.overall(p)}  ·  {club['name']}  ·  wage "
                  f"{fin.weekly(p.get('wage', 0))}  ·  contract until "
                  f"{cal.fmt(p['contract_end'])[4:] if p.get('contract_end') else '-'}", "body", MUTED, (x0, 70))
        t = L["terms"]
        r = pygame.Rect(x0, 110, 560, 470)
        self.panel(r, "Your loan offer")
        y = r.y + 56
        summer = cal.parse(self.career["date"]).month >= 7
        self.text("Length", "body", MUTED, (r.x + 16, y + 8))
        opts = (("season", "Rest of season"), ("half", "Until 1 January")) if summer else (("season", "Rest of season"),)
        for i, (k, label) in enumerate(opts):
            self.buttons.append(Button((r.x + 180 + i * 170, y, 164, 38), label,
                                       lambda k=k: t.__setitem__("half", k == "half"),
                                       primary=(k == "half") == t["half"], font="btn_s"))
        y += 54
        self.text("Loan fee", "body", MUTED, (r.x + 16, y + 8))
        self.text(fin.money(t["fee"]) if t["fee"] else "none", "h3", TEXT, (r.x + 180, y + 6))
        def fee(k):
            step = fin.M if t["fee"] >= 5 * fin.M or (k > 0 and t["fee"] >= 5 * fin.M) else 250_000
            t["fee"] = max(0, t["fee"] + k * step)
        self.buttons.append(Button((r.right - 120, y, 46, 38), "-", lambda: fee(-1)))
        self.buttons.append(Button((r.right - 66, y, 46, 38), "+", lambda: fee(1)))
        y += 54
        self.text("You pay", "body", MUTED, (r.x + 16, y + 8))
        for i, sh in enumerate(lns.WAGE_SHARES):
            self.buttons.append(Button((r.x + 180 + i * 61, y, 56, 38), f"{round(sh * 100)}%",
                                       lambda sh=sh: t.__setitem__("share", sh), primary=t["share"] == sh,
                                       font="btn_s"))
        y += 54
        self.text("Buy clause", "body", MUTED, (r.x + 16, y + 8))
        kind = "obligation" if t["obligation"] else "option" if t["option"] else "none"
        val = fin.value(p, self.career["date"])
        for i, (k, label) in enumerate((("none", "None"), ("option", "Option"), ("obligation", "Obligation"))):
            def setk(k=k):
                if k == "none":
                    t["option"], t["obligation"] = None, False
                else:
                    t["option"] = t["option"] or int(round(val * 1.1 / 500_000) * 500_000)
                    t["obligation"] = k == "obligation"
            self.buttons.append(Button((r.x + 180 + i * 116, y, 110, 38), label, setk, primary=kind == k,
                                       font="btn_s"))
        y += 54
        if t["option"]:
            self.text("...at", "body", MUTED, (r.x + 16, y + 8))
            self.text(fin.money(t["option"]), "h3", TEXT, (r.x + 180, y + 6))
            def opt(k):
                step = fin.M if t["option"] >= 10 * fin.M else 500_000
                t["option"] = max(step, t["option"] + k * step)
            self.buttons.append(Button((r.right - 120, y, 46, 38), "-", lambda: opt(-1)))
            self.buttons.append(Button((r.right - 66, y, 46, 38), "+", lambda: opt(1)))
            y += 54
        self.text("Recall clause", "body", MUTED, (r.x + 16, y + 8))
        for i, (v, label) in enumerate(((False, "No"), (True, "Yes"))):
            self.buttons.append(Button((r.x + 180 + i * 86, y, 80, 38), label,
                                       lambda v=v: t.__setitem__("recall", v), primary=t["recall"] == v,
                                       font="btn_s"))
        y += 54
        if not L["done"]:
            self.buttons.append(Button((r.x + 16, r.bottom - 62, 220, 48), "Ask", self._loan_send, primary=True))
        # The other side
        r2 = pygame.Rect(r.right + 16, 110, W - r.right - 46, 470)
        self.panel(r2, "Their answer")
        y = r2.y + 56
        me = self._my_club()
        y = self._wrap(f"You'd pay {fin.weekly(p.get('wage', 0) * t['share'])} of his "
                       f"{fin.weekly(p.get('wage', 0))} a week; {club['short']} pay the rest.", "body", TEXT,
                       r2.x + 16, y, r2.w - 32) + 8
        y = self._wrap(f"Transfer budget: {fin.money(me['finance'].get('transfer_budget', 0))}  ·  value "
                       f"{fin.money(val)}", "small", MUTED, r2.x + 16, y, r2.w - 32) + 8
        ok, why = lns.allowed(self.career, club, me, p) if not p.get("loan") else (True, "")
        if not ok:
            y = self._wrap(why, "small", LOSS, r2.x + 16, y, r2.w - 32) + 8
        if L.get("reply"):
            self._wrap(L["reply"], "body", ACCENT if L["done"] else LOSS, r2.x + 16, y + 8, r2.w - 32)
        self.text("Loans: at most 2 at once from league clubs (4 a season), 6 over-21s in and out (FIFA). "
                  "He can't play against his parent club.", "small", MUTED, (x0, 596))
        back = getattr(self, "loan_back", "transfers")
        self.buttons.append(Button((x0, H - 66, 160, 46), "Back", lambda: self.go(back)))

    def _offer_answer(self, mid, action):
        m = next((x for x in trf.inbox(self.career) if x["id"] == mid), None)
        counter = getattr(self, "counter_fee", None) if action == "counter" else None
        self.inbox_reply = trf.respond(self.career, mid, action, counter)
        league.save(self.career)

    def _request_answer(self, mid, key):
        self.inbox_reply = chats.answer_request(self.career, mid, key)
        league.save(self.career)

    def draw_inbox(self):
        W, H = self.size
        self.sidebar("inbox")
        x0 = 250
        c = self.career
        self.text("Inbox", "h1", TEXT, (x0, 18))
        self.text(trf.window_text(c["date"]), "small", ACCENT if trf.in_window(c["date"]) else MUTED,
                  (W - 30, 30), "topright")
        box = list(reversed(trf.inbox(c)))
        sel = getattr(self, "inbox_sel", None)
        if sel is None and box:
            sel = next((m["id"] for m in box if m["state"] == "open"), box[0]["id"])
            self.inbox_sel = sel
        r = pygame.Rect(x0, 78, 340, H - 98)
        self.panel(r)
        y = r.y + 10
        mouse = pygame.mouse.get_pos()
        for m in box[: (r.h - 20) // 52]:
            row = pygame.Rect(r.x + 8, y, r.w - 16, 48)
            if m["id"] == sel:
                pygame.draw.rect(self.win, HIGHLIGHT, row, border_radius=8)
            elif row.collidepoint(mouse):
                pygame.draw.rect(self.win, PANEL_2, row, border_radius=8)
            state = {"open": "Waiting for you", "accepted": "Accepted", "rejected": "Rejected",
                     "withdrawn": "Withdrawn", "expired": "Expired", "refused": "He refused", "gone": "-",
                     "info": "News", "answered": "You saw him"}
            self.text(m["text"][:42] + ("..." if len(m["text"]) > 42 else ""), "small",
                      TEXT if not m.get("read") else MUTED, (row.x + 10, row.y + 6))
            self.text(f"{cal.fmt(m['date'], False)}  ·  {state.get(m['state'], m['state'])}", "small",
                      ACCENT if m["state"] == "open" else MUTED, (row.x + 10, row.y + 26))
            self.buttons.append(_Invisible(row, lambda mid=m["id"]: self._inbox_pick(mid)))
            y += 52
        if not box:
            self.text("Nothing yet. Offers for your players arrive here during transfer windows.", "small", MUTED,
                      (r.x + 16, y + 10))
            return
        m = next((x for x in box if x["id"] == sel), None)
        if m is None:
            return
        m["read"] = True
        r2 = pygame.Rect(r.right + 16, 78, W - r.right - 46, H - 98)
        self.panel(r2)
        y = r2.y + 20
        words, line = m["text"].split(" "), ""
        for w_ in words:
            if self.fonts["h3"].size(line + w_)[0] > r2.w - 40:
                self.text(line, "h3", TEXT, (r2.x + 20, y)); y += 32; line = ""
            line += w_ + " "
        self.text(line, "h3", TEXT, (r2.x + 20, y)); y += 44
        d = m["data"]
        if m["kind"] == "report":                                # your assistant's weekly report
            for head, lines in d.get("sections", []):
                self.text(head, "body", ACCENT_HI, (r2.x + 20, y)); y += 26
                for line in lines:
                    y = self._wrap(line, "body", MUTED, r2.x + 20, y, r2.w - 40) + 4
                y += 10
            self.buttons.append(Button((r2.x + 20, min(y + 6, r2.bottom - 66), 240, 46), "Go to the dressing room",
                                       self._to_room, font="btn_s"))
        if m["kind"] == "offer":
            me = self._my_club()
            p = clubs_mod.player_by_id(me, d.get("pid"))
            if p is not None and p["Name"] == d["player"]:
                y = self._wrap(f"{p['Name']}: rated {clubs_mod.overall(p)}, age {p['Age']}, value "
                               f"{fin.money(fin.value(p, c['date']))}, contract until "
                               f"{cal.fmt(p['contract_end'])[4:] if p.get('contract_end') else '-'}.", "body", MUTED,
                               r2.x + 20, y, r2.w - 40) + 6
                if p.get("sell_on"):
                    y = self._wrap(f"Note: {p['sell_on']['pct']}% of any profit goes to his old club (sell-on "
                                   f"clause).", "small", DRAW, r2.x + 20, y, r2.w - 40) + 4
            y = self._wrap(f"Offer open until {cal.fmt(d['expires'], False)}. Half of any fee goes into your "
                           f"transfer budget.", "small", MUTED, r2.x + 20, y, r2.w - 40) + 20
            if m["state"] == "open":
                if getattr(self, "counter_for", None) != m["id"]:
                    self.counter_for = m["id"]
                    self.counter_fee = int(d["fee"] * 1.2)
                self.buttons.append(Button((r2.x + 20, y, 150, 46), "Accept",
                                           lambda: self._offer_answer(m["id"], "accept"), primary=True))
                self.buttons.append(Button((r2.x + 184, y, 150, 46), "Reject",
                                           lambda: self._offer_answer(m["id"], "reject")))
                y += 66
                self.text("Or ask for more:", "body", MUTED, (r2.x + 20, y + 10))
                self.text(fin.money(self.counter_fee), "h3", TEXT, (r2.x + 180, y + 8))
                def adj(k):
                    f_ = self.counter_fee
                    step = 5 * fin.M if f_ >= 50 * fin.M else fin.M if f_ >= 10 * fin.M else 250_000
                    self.counter_fee = max(step, f_ + k * step)
                self.buttons.append(Button((r2.x + 290, y, 46, 40), "-", lambda: adj(-1)))
                self.buttons.append(Button((r2.x + 342, y, 46, 40), "+", lambda: adj(1)))
                y += 52
                self.buttons.append(Button((r2.x + 20, y, 150, 40), "Counter",
                                           lambda: self._offer_answer(m["id"], "counter")))
                y += 60
        if m["kind"] == "bid_reply" and d.get("pid") is not None:     # their answer to your bid
            if d.get("agreed"):
                self.buttons.append(Button((r2.x + 20, y, 260, 46), "Agree personal terms",
                                           lambda: self.open_talks(d["cid"], d["pid"]), primary=True))
            else:
                self.buttons.append(Button((r2.x + 20, y, 220, 46), "Back to the talks",
                                           lambda: self.open_bid(d["cid"], d["pid"]), primary=True))
            y += 66
        if m["kind"] == "loan":
            me = self._my_club()
            p = clubs_mod.player_by_id(me, d.get("pid"))
            if p is not None and p["Name"] == d["player"]:
                y = self._wrap(f"{p['Name']}: rated {clubs_mod.overall(p)}, age {p['Age']}, "
                               f"{round(p.get('mins_avg', 0))} minutes a game lately. His wage "
                               f"{fin.weekly(p.get('wage', 0))} - you'd still pay "
                               f"{fin.weekly(p.get('wage', 0) * (1 - d['terms']['share']))}.", "body", MUTED,
                               r2.x + 20, y, r2.w - 40) + 20
            if m["state"] == "open":
                self.buttons.append(Button((r2.x + 20, y, 150, 46), "Accept",
                                           lambda: self._loan_answer(m["id"], "accept"), primary=True))
                self.buttons.append(Button((r2.x + 184, y, 150, 46), "Reject",
                                           lambda: self._loan_answer(m["id"], "reject")))
                y += 66
        if m["kind"] in ("chat", "request"):              # an unhappy player (career/chats.py)
            me = self._my_club()
            p = clubs_mod.player_by_id(me, d.get("pid"))
            if p is not None:
                self._face(p, me["id"], 56, (r2.x + 20, y))
                y0_ = y
                y = self._wrap(f"{p['Name']}: {p['Pos']}, {p['Age']}, rated {clubs_mod.overall(p)}  ·  morale "
                               f"{morale.label(p)}.", "body", MUTED, r2.x + 92, y + 4, r2.w - 112) + 6
                y = max(y, y0_ + 66)
                if m["kind"] == "chat" and m["state"] == "open":
                    y = self._wrap(f"See him by {cal.fmt(d['expires'], False)}, or he'll feel ignored.", "small",
                                   MUTED, r2.x + 20, y, r2.w - 40) + 14
                    self.buttons.append(Button((r2.x + 20, y, 200, 46), "See him",
                                               lambda: self._chat_from_inbox(m, "asked"), primary=True))
                    y += 66
                elif m["kind"] == "request" and m["state"] == "open":
                    y = self._wrap("Talk to him - you might change his mind. Or just accept (he goes on the transfer "
                                   "list) or refuse (he'll sulk).", "small", MUTED, r2.x + 20, y, r2.w - 40) + 14
                    self.buttons.append(Button((r2.x + 20, y, 170, 46), "Talk to him",
                                               lambda: self._chat_from_inbox(m, "request"), primary=True,
                                               enabled=not d.get("talked")))
                    self.buttons.append(Button((r2.x + 204, y, 130, 46), "Accept",
                                               lambda: self._request_answer(m["id"], "accept")))
                    self.buttons.append(Button((r2.x + 348, y, 130, 46), "Refuse",
                                               lambda: self._request_answer(m["id"], "refuse")))
                    y += 66
        if getattr(self, "inbox_reply", None):
            self._wrap(self.inbox_reply, "body", ACCENT, r2.x + 20, y, r2.w - 40)
        if self.career.get("date") and league.match_date(c) and cal.days_between(c["date"], league.match_date(c)) > 0:
            self.buttons.append(Button((r2.right - 220, r2.bottom - 62, 200, 46), "Continue",
                                       self.continue_to_match, primary=True))

    def _wrap(self, text, font, colour, x, y, width):
        """Text over as many lines as it needs; returns the y below it."""
        words, line = str(text).split(" "), ""
        h = self.fonts[font].get_linesize()
        for w_ in words:
            if line and self.fonts[font].size(line + w_)[0] > width:
                self.text(line.rstrip(), font, colour, (x, y)); y += h; line = ""
            line += w_ + " "
        if line:
            self.text(line.rstrip(), font, colour, (x, y)); y += h
        return y

    def _inbox_pick(self, mid):
        self.inbox_sel = mid
        self.inbox_reply = None

    # -- transfers --------------------------------------------------------
    def open_bid(self, cid, pid):
        club = self.club(cid)
        p = clubs_mod.player_by_id(club, pid)
        if p is None:
            self.flash = "He's not at that club any more."
            return
        price, _ = trf.asking_price(self.career, cid, p)
        t = trf.talks_for(self.career, cid, p) or {}
        last = (t.get("pending") or {}).get("bid") or t.get("last_bid")
        offer = dict(last) if last else {"fee": int(price * 0.8 // 250_000 * 250_000), "years": 1, "addon": 0,
                                         "addon_apps": 20, "sell_on": 0}
        self.bid = {"cid": cid, "pid": pid, "reply": None, "agreed": bool(t.get("agreed")), "offer": offer}
        self.bid_back = self.screen
        self.go("bid")

    def _bid_adjust(self, key, delta):
        o = self.bid["offer"]
        if key == "fee":
            step = 5 * fin.M if o["fee"] >= 50 * fin.M else fin.M if o["fee"] >= 10 * fin.M else 250_000
            o["fee"] = max(0, o["fee"] + delta * step)
        elif key == "addon":
            o["addon"] = max(0, o["addon"] + delta * fin.M)

    def _bid_send(self):
        b = self.bid
        club = self.club(b["cid"])
        p = clubs_mod.player_by_id(club, b["pid"])
        ok, reply = trf.make_bid(self.career, b["cid"], p, dict(b["offer"]))
        b["reply"] = reply
        b["agreed"] = bool(ok)
        b["sent"] = ok is None                      # (gone off - they answer in a day or few)
        league.save(self.career)

    def draw_bid(self):
        W, H = self.size
        b = self.bid
        club = self.club(b["cid"])
        p = clubs_mod.player_by_id(club, b["pid"])
        self.sidebar("transfers")
        x0 = 250
        if p is None:
            return self.go("transfers")
        cname = trf.club_name_of(self.career, b["cid"], p)
        self._face(p, b["cid"], 80, (x0, 16))
        self.text(f"Bid for {p['Name']}", "h1", TEXT, (x0 + 96, 18))
        self.text(self._fit_text(f"{p['Pos']}, {p['Age']}  ·  rated {clubs_mod.overall(p)}  ·  {cname}  ·  value "
                  f"{fin.money(fin.value(p, self.career['date']))}  ·  contract until "
                  f"{cal.fmt(p['contract_end'])[4:] if p.get('contract_end') else '-'}", "body", W - x0 - 126),
                  "body", MUTED, (x0 + 96, 70))
        o = b["offer"]
        r = pygame.Rect(x0, 110, 560, 470)
        self.panel(r, "Your bid")
        y = r.y + 56

        def pm(label, value, key):
            nonlocal y
            self.text(label, "body", MUTED, (r.x + 16, y + 8))
            self.text(value, "h3", TEXT, (r.x + 200, y + 6))
            self.buttons.append(Button((r.right - 120, y, 46, 38), "-", lambda: self._bid_adjust(key, -1)))
            self.buttons.append(Button((r.right - 66, y, 46, 38), "+", lambda: self._bid_adjust(key, 1)))
            y += 54

        pm("Fee", fin.money(o["fee"]), "fee")
        self.text("Paid", "body", MUTED, (r.x + 16, y + 8))
        for i, (yrs, label) in enumerate(((1, "Up front"), (2, "2 years"), (3, "3 years"), (4, "4 years"))):
            self.buttons.append(Button((r.x + 200 + i * 86, y, 80, 38), label,
                                       lambda yrs=yrs: o.__setitem__("years", yrs), primary=o["years"] == yrs,
                                       font="btn_s"))
        y += 54
        pm("Add-on", fin.money(o["addon"]) if o["addon"] else "none", "addon")
        self.text("...after", "body", MUTED, (r.x + 16, y + 8))
        for i, n in enumerate((10, 20, 30, 50)):
            self.buttons.append(Button((r.x + 200 + i * 86, y, 80, 38), f"{n} games",
                                       lambda n=n: o.__setitem__("addon_apps", n), primary=o["addon_apps"] == n,
                                       font="btn_s"))
        y += 54
        self.text("Sell-on clause", "body", MUTED, (r.x + 16, y + 8))
        for i, pct in enumerate((0, 10, 15, 20, 30)):
            self.buttons.append(Button((r.x + 200 + i * 68, y, 62, 38), "none" if pct == 0 else f"{pct}%",
                                       lambda pct=pct: o.__setitem__("sell_on", pct), primary=o["sell_on"] == pct,
                                       font="btn_s"))
        y += 54
        # A player of yours as part of the deal
        me_ = self._my_club()
        mine_ = [q for q in sorted(me_["players"], key=lambda q: -fin.value(q, self.career["date"]))
                 if not q.get("loan")]
        sw = trf.swap_player(self.career, o)
        self.text("Plus player", "body", MUTED, (r.x + 16, y + 8))
        if sw is not None:
            self.text(f"{sw['Name']} ({sw['Pos']}, {clubs_mod.overall(sw)})", "body", TEXT, (r.x + 140, y + 8))
        else:
            self.text("none", "h3", TEXT, (r.x + 140, y + 6))
        def cyc(k):
            ids = [None] + [q["id"] for q in mine_]
            cur = sw["id"] if sw is not None else None
            nxt = ids[(ids.index(cur) + k) % len(ids)] if cur in ids else None
            q = clubs_mod.player_by_id(me_, nxt) if nxt is not None else None
            o["swap"] = {"pid": q["id"], "name": q["Name"]} if q else None
        self.buttons.append(Button((r.right - 120, y, 46, 38), "<", lambda: cyc(-1)))
        self.buttons.append(Button((r.right - 66, y, 46, 38), ">", lambda: cyc(1)))
        y += 48
        if p.get("release_clause"):
            self.text(f"Release clause: {fin.money(p['release_clause'])} (pay it up front and they must accept)",
                      "small", ACCENT, (r.x + 16, y + 6))
        t = trf.talks_for(self.career, b["cid"], p) or {}
        if t.get("agreed"):
            b["agreed"] = True
        if b["agreed"]:
            self.buttons.append(Button((r.x + 16, r.bottom - 62, 280, 48), "Agree personal terms",
                                       lambda: self.open_talks(b["cid"], b["pid"]), primary=True))
        elif t.get("pending"):
            self.buttons.append(Button((r.x + 16, r.bottom - 62, 260, 48), "Waiting for their answer", None,
                                       enabled=False))
        else:
            self.buttons.append(Button((r.x + 16, r.bottom - 62, 220, 48), "Make bid", self._bid_send,
                                       primary=True))
            co = t.get("counter_offer")
            if co:
                def match(co=co):
                    o.update({k_: v_ for k_, v_ in co.items()})
                    o["swap"] = None
                self.buttons.append(Button((r.x + 250, r.bottom - 62, 220, 48), "Use their terms", match))
        # Their side
        r2 = pygame.Rect(r.right + 16, 110, W - r.right - 46, 470)
        self.panel(r2, "Their answer")
        y = r2.y + 56
        me = self._my_club()
        self.text(f"Your transfer budget: {fin.money(me['finance'].get('transfer_budget', 0))}", "body", TEXT,
                  (r2.x + 16, y)); y += 28
        self.text(f"Bid worth now: {fin.money(trf.bid_worth(o))}", "body", MUTED, (r2.x + 16, y)); y += 28
        sw = trf.swap_player(self.career, o)
        if sw is not None:
            self.text(f"+ {sw['Name']}: they'd count him at ~{fin.money(lns.swap_value(self.career, b['cid'], sw))}",
                      "small", MUTED, (r2.x + 16, y))
            y += 24
        y += 12
        t = trf.talks_for(self.career, b["cid"], p) or {}
        if t.get("pending"):
            pd = t["pending"]
            y = self._wrap(f"You bid {trf.counter_text(pd['bid'])} on {cal.fmt(pd['made'], False)}. Waiting for "
                           f"{cname} to answer - it'll be in your inbox.", "body", TEXT, r2.x + 16, y, r2.w - 32) + 10
        else:
            said = t.get("last_reply") or b.get("reply")
            if said:
                col = ACCENT if b["agreed"] else LOSS if t.get("closed_until") or "out of hand" in said else DRAW
                y = self._wrap(said, "body", col, r2.x + 16, y, r2.w - 32) + 10
        if not t.get("agreed") and t.get("bids"):
            left = trf.BID_PATIENCE - t["bids"]
            if not t.get("closed_until") and left > 0:
                self.text(f"They'll listen to {left} more bid{'s' if left > 1 else ''}.", "small", MUTED,
                          (r2.x + 16, y)); y += 22
        self.text("Instalments are paid each 1 July; money later is worth a little less to them. Add-ons and "
                  "sell-ons count for something too.", "small", MUTED, (x0, 596))
        back = getattr(self, "bid_back", "transfers")
        self.buttons.append(Button((x0, H - 66, 160, 46), "Back", lambda: self.go(back)))

    def draw_transfers(self):
        W, H = self.size
        self.sidebar("transfers")
        x0 = 250
        c = self.career
        self.text("Transfers", "h1", TEXT, (x0, 18))
        self._laptop_tabs("transfers", x0 + 210)
        self.text(trf.window_text(c["date"]), "body", ACCENT if trf.in_window(c["date"]) else MUTED,
                  (W - 30, 32), "topright")
        tab = getattr(self, "tr_tab", "search")
        for i, (key, label) in enumerate((("search", "Find players"), ("free", "Free agents"), ("bids", "Your bids"),
                                          ("loans", "Loans"))):
            self.buttons.append(Button((x0 + i * 150, 70, 144, 34), label, lambda k=key: setattr(self, "tr_tab", k),
                                       primary=tab == key, font="btn_s"))
        if tab == "free":
            return self._free_agent_list(x0, 116)
        if tab == "bids":
            return self._bid_list(x0, 116)
        if tab == "loans":
            return self._loan_lists(x0, 116)
        # Filters
        f = getattr(self, "tr_filter", {})
        for k_, v_ in (("pos", None), ("age", None), ("fee", None), ("src", "all"), ("sale", True), ("sort", "rating")):
            f.setdefault(k_, v_)
        self.tr_filter = f
        y = 116
        budget = self._my_club()["finance"].get("transfer_budget", 0)
        opts = [("pos", [None, "GK", "LB", "CB", "RB", "LM", "CM", "RM", "ST"]),
                ("age", [None, 21, 25, 29]), ("fee", [None, "budget", 5 * fin.M, 15 * fin.M, 30 * fin.M, 60 * fin.M]),
                ("src", ["all", "league", "spain", "abroad"]), ("sale", [True, False]), ("sort", ["rating", "price", "age"])]
        labels = {"pos": lambda v: v or "Any pos", "age": lambda v: f"Age <= {v}" if v else "Any age",
                  "fee": lambda v: "Within budget" if v == "budget" else f"<= {fin.money(v)}" if v else "Any fee",
                  "src": lambda v: {"all": "Everywhere", "league": "Our league", "spain": "Spain",
                                    "abroad": "Rest of world"}[v],
                  "sale": lambda v: "For sale only" if v else "Incl. not for sale",
                  "sort": lambda v: {"rating": "Best first", "price": "Cheapest first", "age": "Youngest first"}[v]}
        x = x0
        for key, vals in opts:
            cur = f[key]
            nxt = vals[(vals.index(cur) + 1) % len(vals)]
            w = 136 if key in ("sale", "sort", "fee") else 116
            self.buttons.append(Button((x, y, w, 32), labels[key](cur), lambda k=key, v=nxt: f.__setitem__(k, v),
                                       font="btn_s", primary=key == "sale" and not cur))
            x += w + 8
        r = pygame.Rect(x0, 158, W - x0 - 30, H - 178)
        self.panel(r)
        cols = [("Pos", 0), ("Name", 46), ("Age", 252), ("Rating", 292), ("Club", 358), ("Value", 540),
                ("Asking", 630), ("Wage", 730)]
        yy = r.y + 12
        for label, cx in cols:
            self.text(label, "small", MUTED, (r.x + 16 + cx, yy))
        yy += 24
        rows = (r.bottom - yy - 6) // 26
        fee = budget if f["fee"] == "budget" else f["fee"]
        res = trf.search(c, f["pos"], f["age"], fee, f["src"], limit=rows, for_sale=f["sale"], sort=f["sort"])
        mouse = pygame.mouse.get_pos()
        if not res:
            self.text("Nobody matches - try changing the filters.", "body", MUTED, (r.x + 16, yy))
        for cid, p, price, nfs in res:
            row = pygame.Rect(r.x + 8, yy - 3, r.w - 16, 25)
            if row.collidepoint(mouse):
                pygame.draw.rect(self.win, PANEL_2, row, border_radius=6)
            vals = [p["Pos"], p["Name"], p.get("Age", ""), clubs_mod.overall(p),
                    trf.club_name_of(c, cid, p), fin.money(fin.value(p, c["date"])), fin.money(price),
                    fin.weekly(p.get("wage", 0))]
            self._face(p, cid, 22, (r.x + 16 + 46, yy - 1), border=False)
            for (label, cx), v in zip(cols, vals):
                if label == "Name":
                    cx += 28
                    v = self._fit_text(v, "body", 252 - cx - 8)
                if label == "Asking" and nfs:
                    self.text("Not for sale", "small", LOSS, (r.x + 16 + cx, yy + 2))
                    continue
                col = MUTED if label == "Club" else LOSS if label == "Asking" and price > budget else TEXT
                self.text(v, "small" if label in ("Club", "Wage") else "body", col,
                          (r.x + 16 + cx, yy + (2 if label in ("Club", "Wage") else 0)))
            self.buttons.append(_Invisible(row, lambda cid=cid, pid=p["id"]: self.view_player(cid, pid)))
            yy += 26

    def _loan_lists(self, x0, y0):
        W, H = self.size
        me = self._my_club()
        c = self.career
        half = (W - x0 - 44) // 2
        groups = (("On loan here", [(p, me) for p in lns.loans_in(c, me)], pygame.Rect(x0, y0, half, H - y0 - 20)),
                  ("Out on loan", lns.loans_out(c, me), pygame.Rect(x0 + half + 14, y0, half, H - y0 - 20)))
        for title, rows, r in groups:
            self.panel(r, title)
            y = r.y + 48
            for p, club in rows:
                loan = p["loan"]
                cid = club["id"]
                line = (f"{p['Name']} ({p['Pos']}, {p['Age']}, {clubs_mod.overall(p)})  -  " +
                        (f"from {loan['from_name']}" if club is me else f"at {club['name']}"))
                self.text(line, "body", TEXT, (r.x + 16, y))
                y = self._wrap(f"{loan.get('apps', 0)} games, rating {loan.get('start_rating', '?')} -> "
                               f"{clubs_mod.overall(p)}  ·  {lns.describe(loan)}", "small", MUTED, r.x + 16, y + 24,
                               r.w - 32) + 10
                self.buttons.append(_Invisible(pygame.Rect(r.x + 8, y - 60, r.w - 16, 56),
                                               lambda cid=cid, pid=p["id"]: self.view_player(cid, pid)))
            if not rows:
                self.text("Nobody." if title == "Out on loan" else "Nobody - ask about a loan from a player's "
                          "profile.", "small", MUTED, (r.x + 16, y))
                y += 30
            if title == "Out on loan":
                listed = [p for p in me["players"] if p.get("loan_listed")]
                y += 16
                self.text("On your loan list:", "body", TEXT, (r.x + 16, y)); y += 28
                for p in listed:
                    self.text(f"{p['Name']} ({p['Pos']}, {p['Age']})", "small", MUTED, (r.x + 16, y))
                    self.buttons.append(_Invisible(pygame.Rect(r.x + 8, y - 3, r.w - 16, 24),
                                                   lambda pid=p["id"]: self.view_player(me["id"], pid)))
                    y += 24
                if not listed:
                    self.text("Nobody - put a player on it from his profile.", "small", MUTED, (r.x + 16, y))

    def _bid_list(self, x0, y0):
        W, H = self.size
        r = pygame.Rect(x0, y0, W - x0 - 30, H - y0 - 20)
        self.panel(r)
        y = r.y + 16
        bids = self.career.get("bids", {})
        any_ = False
        for k, t in bids.items():
            cid, pid, name = k.split(":", 2)
            cid, pid = int(cid), int(pid)
            club = self.club(cid)
            p = clubs_mod.player_by_id(club, pid)
            if p is None or p["Name"] != name:
                continue
            any_ = True
            if t.get("agreed"):
                state, col = f"Fee agreed ({fin.money(t['agreed']['fee'])}) - agree personal terms", ACCENT
            elif t.get("closed_until"):
                state, col = f"They've stopped talking until {cal.fmt(t['closed_until'], False)}", LOSS
            elif t.get("pending"):
                state, col = "Bid sent - waiting for their answer", MUTED
            elif t.get("counter_offer"):
                state, col = f"They want {trf.counter_text(t['counter_offer'])}", TEXT
                if t.get("rival"):
                    state += f"  ·  {t['rival']['name']} are in too"
            else:
                state, col = "Talks open", TEXT
            self.text(f"{p['Name']} ({p['Pos']}, {trf.club_name_of(self.career, cid, p)})", "body", TEXT, (r.x + 16, y))
            self.text(state, "small", col, (r.x + 420, y + 3))
            self.buttons.append(_Invisible(pygame.Rect(r.x + 8, y - 4, r.w - 16, 28),
                                           lambda cid=cid, pid=pid: self.open_bid(cid, pid)))
            y += 32
        if not any_:
            self.text("No bids yet - find a player and make an offer from his profile.", "body", MUTED, (r.x + 16, y))

    def draw_freeagents(self):
        self.tr_tab = "free"
        self.go("transfers")

    def _free_agent_list(self, x0, y0):
        W, H = self.size
        fa = con.free_agents(self.career)
        self.text("No transfer fee - just agree a contract, any time of year.", "small", MUTED, (x0 + 610, y0 - 36))
        pos_f = getattr(self, "fa_pos", "All")
        for i, pos in enumerate(["All", "GK", "LB", "CB", "RB", "LM", "CM", "RM", "ST"]):
            self.buttons.append(Button((x0 + i * 72, y0, 66, 32), pos, lambda pos=pos: setattr(self, "fa_pos", pos),
                                       primary=pos_f == pos, font="btn_s"))
        r = pygame.Rect(x0, y0 + 42, W - x0 - 30, H - y0 - 62)
        self.panel(r)
        cols = [("Pos", 0), ("Name", 50), ("Age", 270), ("Rating", 320), ("Value", 400), ("Asking", 510),
                ("Last club", 640)]
        y = r.y + 12
        for label, cx in cols:
            self.text(label, "small", MUTED, (r.x + 20 + cx, y))
        y += 26
        me = self._my_club()
        players = [p for p in fa["players"] if pos_f == "All" or clubs_mod.family(p["Pos"]) == pos_f]
        players.sort(key=lambda p: -clubs_mod.overall(p))
        mouse = pygame.mouse.get_pos()
        for p in players[: (r.bottom - y - 6) // 28]:
            row = pygame.Rect(r.x + 10, y - 3, r.w - 20, 26)
            if row.collidepoint(mouse):
                pygame.draw.rect(self.win, PANEL_2, row, border_radius=6)
            want = con.demands(self.career, me, p, False)
            vals = [p["Pos"], p["Name"], p.get("Age", ""), clubs_mod.overall(p), fin.money(fin.value(p)),
                    fin.weekly(want["wage"]), p.get("_from_club", "")]
            self._face(p, -1, 24, (r.x + 20 + 50, y - 2), border=False)
            for (label, cx), v in zip(cols, vals):
                if label == "Name":
                    cx += 30
                    v = self._fit_text(v, "body", 270 - cx - 8)
                self.text(v, "body" if label != "Last club" else "small", TEXT if label != "Last club" else MUTED,
                          (r.x + 20 + cx, y + (2 if label == "Last club" else 0)))
            self.buttons.append(_Invisible(row, lambda pid=p["id"]: self.view_player(-1, pid)))
            y += 28
        if not players:
            self.text("Nobody - a new batch of players from outside the league arrives every summer.", "body",
                      MUTED, (r.x + 20, y))

    # -- finances -----------------------------------------------------------
    def draw_finances(self):
        W, H = self.size
        self.sidebar("finances")
        c = self.career
        club = self._my_club()
        x0 = 250
        self.text("Finances", "h1", TEXT, (x0, 18))
        f = club.get("finance")
        if not f:
            self.text("No finances in this save.", "body", MUTED, (x0, 80))
            return
        bill = fin.wage_bill(club)
        cards = [("Bank balance", fin.money(f["balance"]), TEXT),
                 ("Transfer budget", fin.money(f.get("transfer_budget", 0)), ACCENT),
                 ("Wage budget", f"{fin.money(f.get('wage_budget', 0))} a year", TEXT),
                 ("Wage bill", f"{fin.money(bill)} a year", LOSS if bill > f.get("wage_budget", bill) else TEXT)]
        cw = (W - x0 - 30 - 3 * 14) // 4
        for i, (label, v, col) in enumerate(cards):
            r = pygame.Rect(x0 + i * (cw + 14), 78, cw, 92)
            self.panel(r)
            self.text(label, "small", MUTED, (r.x + 16, r.y + 14))
            self.text(v, "h2", col, (r.x + 16, r.y + 42))
        # This season
        s = f["season"]
        r = pygame.Rect(x0, 186, (W - x0 - 44) // 2, H - 206)
        self.panel(r, "This season so far")
        y = r.y + 50
        income = [("TV and central payments", s["tv"]), ("Matchday", s["matchday"]), ("Commercial", s["commercial"]),
                  ("Prize money (end of season)", s["prize"]), ("Players sold", s["transfers_in"])]
        spend = [("Player wages", s["wages"]), ("Running the club", s["other"]), ("Players bought", s["transfers_out"])]
        self.text("Income", "h3", ACCENT, (r.x + 16, y)); y += 32
        for label, v in income:
            self.text(label, "body", TEXT, (r.x + 16, y)); self.text(fin.money(v), "body", TEXT, (r.right - 20, y), "topright")
            y += 28
        y += 8
        self.text("Spending", "h3", LOSS, (r.x + 16, y)); y += 32
        for label, v in spend:
            self.text(label, "body", TEXT, (r.x + 16, y)); self.text(fin.money(v), "body", TEXT, (r.right - 20, y), "topright")
            y += 28
        net = sum(v for _, v in income) - sum(v for _, v in spend)
        y += 8
        self.text("Profit / loss", "h3", TEXT, (r.x + 16, y))
        self.text(fin.money(net), "h3", ACCENT if net >= 0 else LOSS, (r.right - 20, y), "topright")
        # Club and top earners
        owed = trf.owed(c, club["id"])
        if owed:
            self.text(f"Transfer instalments still to pay: {fin.money(owed)}", "small", DRAW, (x0, 172))
        r2 = pygame.Rect(r.right + 14, 186, W - r.right - 44, 150)
        self.panel(r2, "The club")
        self.text(f"Stadium: {f['capacity']:,} seats  ·  average ticket £{f['ticket']}", "body", TEXT, (r2.x + 16, r2.y + 50))
        self.text(f"Commercial deals: {fin.money(f['commercial'])} a year", "body", TEXT, (r2.x + 16, r2.y + 78))
        hist = f.get("history") or []
        if hist:
            h = hist[-1]
            self.text(f"Last season: {_ordinal(h['position'])}, profit {fin.money(h['profit'])}", "body", MUTED,
                      (r2.x + 16, r2.y + 106))
        r3 = pygame.Rect(r2.x, r2.bottom + 14, r2.w, H - r2.bottom - 34)
        self.panel(r3, "Top earners")
        y = r3.y + 50
        for p in sorted(club["players"], key=lambda p: -p.get("wage", 0))[:8]:
            self.text(f"{p['Name']} ({p['Pos']})", "body", TEXT, (r3.x + 16, y))
            self.text(fin.weekly(p.get("wage", 0)), "body", TEXT, (r3.right - 20, y), "topright")
            y += 28

    # -- player profile -------------------------------------------------------
    ATTR_GROUPS = [
        ("Technical", ["Crossing", "Dribbling", "Finishing", "Control", "Heading", "Long Shots", "Marking",
                       "Passing", "Penalties", "Tackling"]),
        ("Mental", ["Aggression", "Anticipation", "Composure", "Decisions", "Off The Ball",
                    "Defensive Positioning", "Teamwork", "Work Rate"]),
        ("Physical", ["Acceleration", "Agility", "Jumping", "Top Speed", "Stamina", "Strength"]),
    ]

    def draw_player(self):
        W, H = self.size
        cid, pid = self.player_view
        club = self.club(cid)
        p = clubs_mod.player_by_id(club, pid)
        if p is None:                                   # (he's moved on)
            return self.go(getattr(self, "player_back", "squad"))
        mine = cid == self.career["my_club"]
        self.sidebar("squad" if mine else "transfers" if cid < 0 else "spain" if cid >= spain.ID_BASE else "table")
        x0 = 250
        face = faces.face_surface(p, 88, self.colour(cid) if cid >= 0 else None,      # (career/faces.py)
                                  club if cid >= 0 else None)
        self.win.blit(face, (x0, 12))
        pygame.draw.rect(self.win, LINE, (x0, 12, 88, 88), 1, border_radius=4)
        self.text(p["Name"], "h1", TEXT, (x0 + 104, 18))
        in_xi = {v: k for k, v in club["lineup"].items()}.get(pid)
        sub = f"{club['name']}  ·  {POS_NAMES.get(p['Pos'], p['Pos'])}  ·  age {p.get('Age', '?')}"
        if cid == -2:
            sub = sub.replace(club["name"], p.get("abroad_club", "abroad") + " (outside the league)")
        if cid >= spain.ID_BASE:
            sub = sub.replace(club["name"], club["name"] + " (Spain" + (", non-EU)" if p.get("non_eu") else ")"))
        if cid == -1:
            sub += f"  ·  last club: {p.get('_from_club', '?')}"
        else:
            sub += f"  ·  starting XI ({in_xi})" if in_xi else "  ·  not in the starting XI"
        if p.get("loan"):
            ln = p["loan"]
            sub = (f"{club['name']}  ·  {POS_NAMES.get(p['Pos'], p['Pos'])}  ·  age {p.get('Age', '?')}  ·  on loan "
                   f"from {'you' if ln['from'] == self.career['my_club'] else ln['from_name']} until "
                   f"{cal.fmt(ln['until'], False)} ({ln.get('apps', 0)} games)")
        elif p.get("loan_listed"):
            sub += "  ·  on your loan list"
        self.text(self._fit_text(sub, "body", W - x0 - 134), "body", MUTED, (x0 + 104, 72))
        today = self.career.get("date")
        if today and avail.banned(p):
            self.text(f"Suspended for {p['ban']} more match{'es' if p['ban'] > 1 else ''}", "body", DRAW,
                      (W - 30, 30), "topright")
        elif today and avail.injured(p, today):
            inj = p["injury"]
            self.text(f"Injured: {inj['name']} - back {cal.fmt(inj['until'], False)}", "body", LOSS,
                      (W - 30, 30), "topright")

        # Attributes
        groups = list(self.ATTR_GROUPS)
        if p["Pos"] == "GK":
            groups = [("Goalkeeping", ["Shot Stopping", "Handling"])] + groups
        r = pygame.Rect(x0, 112, 600, H - 190)
        self.panel(r)
        col_w = r.w // 2
        cx, cy = r.x + 18, r.y + 14
        colnum = 0
        for title, attrs in groups:
            if cy + 30 + len(attrs) * 28 > r.bottom - 10:
                colnum += 1
                cx, cy = r.x + 18 + colnum * col_w, r.y + 14
            self.text(title, "h3", TEXT, (cx, cy))
            cy += 32
            for a in attrs:
                v = _attr20(p[a])
                self.text(a, "body", TEXT, (cx, cy))
                box = pygame.Rect(cx + col_w - 70, cy - 1, 34, 24)
                pygame.draw.rect(self.win, PANEL_2, box, border_radius=5)
                self.text(v, "body", _attr_colour(v), box.center, "center")
                cy += 28
            cy += 12
            col_end = getattr(self, "_col_end", {})
            col_end[colnum] = (cx, cy)
            self._col_end = col_end

        # Ratings by position, and this season
        rx = x0 + 620
        if mine and cid >= 0:                       # how he's feeling (career/morale.py)
            ends = self.__dict__.pop("_col_end", {}) or {0: (cx, cy)}
            mx, my = min(ends.values(), key=lambda e: e[1])          # (under the shorter column of attributes)
            my += 6
            self.text("Morale", "h3", TEXT, (mx, my))
            self.text(morale.label(p), "h3", MORALE_COLOUR[morale.colour_key(p)], (mx + col_w - 52, my), "topright")
            note = morale.assistant_note(p)
            told = p.get("told")
            line_y = my + 36
            if told and cal.days_between(told["date"], self.career["date"]) <= 21:
                said = f"He told you ({cal.fmt(told['date'], False)}): {told['text']}."
            else:
                said = ("Assistant: " + note) if note else "Nothing obvious on his mind - you'd have to ask him."
            lines = [said] + ([chats.character_note(p)] if chats.character_note(p) else [])
            lv = captains.assistant_view(p, club, self.career["date"])
            if lv:
                lines.append("Assistant: " + lv)
            fv = fitness.assistant_view(p)                    # (career/fitness.py - hidden numbers)
            if fv:
                lines.append("Assistant: " + fv)
            if club.get("captain") == p["id"] or club.get("vice") == p["id"]:
                lines.append("Club captain." if club.get("captain") == p["id"] else "Vice-captain.")
            if p.get("rest_for"):
                lines.append(f"Resting for the match on {cal.fmt(p['rest_for'], False)}.")
            if p.get("promise"):
                lines.append(f"You promised him more games (by {cal.fmt(p['promise']['check'], False)}).")
            if p.get("wants_out"):
                lines.append("He's handed in a transfer request - he wants to leave.")
            for text_ in lines:
                for line in self._lines(text_, "small", col_w - 40):
                    self.text(line, "small", MUTED, (mx, line_y))
                    line_y += 20
                line_y += 4
            self.buttons.append(Button((mx, line_y + 6, 170, 38), "Talk to him", lambda: self.open_chat(pid),
                                       primary=True, font="btn_s"))
        rr = pygame.Rect(rx, 112, W - rx - 30, 330)
        self.panel(rr, "Rating by position")
        spots = (("GK", "GK"), ("LCB", "CB"), ("LB", "LB"), ("RB", "RB"), ("LWB", "LWB"), ("RWB", "RWB"),
                 ("DM", "DM"), ("LCM", "CM"), ("AM", "AM"), ("LM", "LM"), ("RM", "RM"), ("LW", "LW"),
                 ("RW", "RW"), ("ST1", "ST"))
        half = (rr.w - 32) // 2
        for i, (slot, label) in enumerate(spots):
            cx = rr.x + 16 + (i // 7) * (half + 16)
            y = rr.y + 48 + (i % 7) * 38
            f = clubs_mod.fit(p, slot)
            v = clubs_mod.overall(p, slot)
            col = ACCENT if f in (0, 4) else DRAW if f == 1 else LOSS
            self.text(label, "body", TEXT if f in (0, 1, 4) else MUTED, (cx, y))
            self.text(v, "body", col, (cx + half - 8, y), "topright")
        sr = pygame.Rect(rx, 456, W - rx - 30, H - 534)
        self.panel(sr, "This season")
        res = league.results_of(self.career, cid) if 0 <= cid < len(self.career["clubs"]) else self.career["results"]
        quick = res is not self.career["results"]           # (the other division: quick results)
        goals = [g for day in res.values() for m in day
                 for g in m["goals"] if g["name"] == p["Name"] and not g.get("own_goal")
                 and (m["home"] if g["team"] == 0 else m["away"]) == cid]
        starts = subs_on = minutes = yellows = reds = 0
        for day in res.values():
            for m in day:
                for a in m.get("players", []):
                    if a["id"] == pid and (m["home"] if a["team"] == 0 else m["away"]) == cid:
                        starts += a["start"]
                        subs_on += not a["start"]
                        minutes += a["minutes"]
                        yellows += a["yellow"]
                        reds += bool(a["red"])
        apps = f"{starts}" + (f" (+{subs_on} as sub)" if subs_on else "")
        if cid >= spain.ID_BASE:                       # (quick results: starts and goals only)
            apps, minutes, goals = str(p.get("lg_apps", 0)), p.get("lg_apps", 0) * 90, [0] * p.get("lg_goals", 0)
        self.text(f"Appearances: {apps}", "body", TEXT, (sr.x + 16, sr.y + 48))
        self.text(f"Minutes: {minutes}", "body", TEXT, (sr.x + 16, sr.y + 76))
        self.text(f"Goals: {len(goals)}", "body", TEXT, (sr.x + 16, sr.y + 104))
        if cid >= spain.ID_BASE or quick:
            self.text("Cards: not recorded", "body", MUTED, (sr.x + 16, sr.y + 132))
        else:
            self.text(f"Cards: {yellows} yellow, {reds} red", "body", TEXT, (sr.x + 16, sr.y + 132))
        self.text(f"Overall rating: {clubs_mod.overall(p)}", "body", TEXT, (sr.x + 16, sr.y + 160))
        if "wage" in p:
            today = self.career.get("date")
            self.text(f"Value: {fin.money(fin.value(p, today))}", "body", ACCENT, (sr.x + 16, sr.y + 196))
            self.text(f"Wage: {fin.weekly(p['wage'])}", "body", TEXT, (sr.x + 16, sr.y + 224))
            note = None
            if p.get("cut_from"):
                note = f"Cut from {fin.weekly(p['cut_from'])} by his relegation clause"
            elif 0 <= cid < len(self.career["clubs"]) and cid == self.career["my_club"] \
                    and fin.league_of(self.career["clubs"][cid]) == "pl":
                cut = p.get("releg_cut", fin.club_clause(self.career["clubs"][cid]))
                note = f"Relegation clause: wage cut {cut}% if we go down" if cut else "No relegation wage cut"
            if note:
                self.text(note, "small", MUTED, (sr.x + 16, sr.y + 282))
            if p.get("contract_end"):
                self.text(f"Contract until {cal.fmt(p['contract_end'])[4:]}", "body", TEXT, (sr.x + 16, sr.y + 252))

        back = getattr(self, "player_back", "squad")
        self.buttons.append(Button((x0, H - 66, 160, 46), "Back", lambda: self.go(back)))
        loan = p.get("loan")
        window = trf.in_window(self.career["date"])
        if loan:
            # On loan - here, or one of yours away
            ours = loan["from"] == self.career["my_club"]
            if mine and loan.get("option") and not loan.get("obligation") and window:
                self.buttons.append(Button((x0 + 180, H - 66, 300, 46),
                                           f"Make it permanent ({fin.money(loan['option'])})",
                                           lambda: self._loan_buy(p), primary=True))
            if ours and lns.can_recall(self.career, p):
                self.buttons.append(Button((x0 + 180, H - 66, 200, 46), "Recall him",
                                           lambda: self._loan_recall(p, club), primary=True))
            if ours and fin.contract_years_left(p, self.career["date"]) < 2.0:
                self.buttons.append(Button((x0 + 400, H - 66, 240, 46), "Offer new contract",
                                           lambda: self.open_talks(cid, pid)))
            if getattr(self, "flash", None):
                self.text(self.flash, "body", LOSS, (x0, H - 100))
            return
        if mine and "finance" in club:
            self.buttons.append(Button((W - 30 - 220 - 200, H - 66, 190, 46),
                                       "Off the loan list" if p.get("loan_listed") else "Loan list",
                                       lambda: self._loan_list(p)))
            if p.get("listed"):
                self.buttons.append(Button((W - 30 - 220, H - 66, 220, 46), "Take off the list",
                                           lambda: self._list_player(p, False)))
                self.text(f"Transfer listed at {fin.money(p.get('asking', 0))}", "body", DRAW, (W - 30 - 360, H - 112))
                self.buttons.append(Button((W - 30 - 100, H - 120, 46, 38), "-", lambda: self._asking(p, -1)))
                self.buttons.append(Button((W - 30 - 46, H - 120, 46, 38), "+", lambda: self._asking(p, 1)))
            else:
                self.buttons.append(Button((W - 30 - 220, H - 66, 220, 46), "Put on transfer list",
                                           lambda: self._list_player(p, True)))
        if "wage" in p and (mine or cid == -1):
            today = self.career.get("date")
            left = fin.contract_years_left(p, today) if p.get("contract_end") else 0
            if cid == -1 or left < 2.0:
                label = "Offer a contract" if cid == -1 else "Offer new contract"
                self.buttons.append(Button((x0 + 180, H - 66, 240, 46), label,
                                           lambda: self.open_talks(cid, pid), primary=True))
        if cid >= 0 and not mine or cid == -2:
            if trf.agreed_bid(self.career, cid, p):
                self.buttons.append(Button((x0 + 180, H - 66, 260, 46), "Agree personal terms",
                                           lambda: self.open_talks(cid, pid), primary=True))
            elif trf.in_window(self.career["date"]):
                self.buttons.append(Button((x0 + 180, H - 66, 210, 46), "Make an offer",
                                           lambda: self.open_bid(cid, pid), primary=True))
                if cid >= 0:
                    self.buttons.append(Button((x0 + 400, H - 66, 210, 46), "Ask about a loan",
                                               lambda: self.open_loan(cid, pid)))
            price, nfs = trf.asking_price(self.career, cid, p)
            self.text(("Not for sale - " if nfs else "") + f"they'd want ~{fin.money(price)}", "small",
                      DRAW if nfs else MUTED, (x0 + 625, H - 52))
        if getattr(self, "flash", None):
            self.text(self.flash, "body", LOSS, (x0, H - 100))

    # -- tactics ------------------------------------------------------------
    # The pitch is drawn attacking upwards, one row per line of the grid (config/slots.py)
    ROW_Y = {-1: 0.035, 0: 0.205, 1: 0.375, 2: 0.545, 3: 0.715, 4: 0.885}      # (GK row = -1)
    SLOT_NAMES = {"GK": "Goalkeeper", "LB": "Left-back", "LCB": "Centre-back (left)", "CB": "Centre-back",
                  "RCB": "Centre-back (right)", "RB": "Right-back", "LWB": "Left wing-back",
                  "LDM": "Defensive midfield (left)", "DM": "Defensive midfield", "RDM": "Defensive midfield (right)",
                  "RWB": "Right wing-back", "LM": "Left midfield", "LCM": "Centre midfield (left)",
                  "CM": "Centre midfield", "RCM": "Centre midfield (right)", "RM": "Right midfield",
                  "LW": "Left winger", "LAM": "Attacking midfield (left)", "AM": "Attacking midfield",
                  "RAM": "Attacking midfield (right)", "RW": "Right winger", "ST1": "Striker (left)",
                  "ST": "Striker", "ST2": "Striker (right)"}
    PRESETS = ["4-4-2", "4-2-3-1", "4-3-3", "4-1-4-1", "3-4-2-1", "3-5-2", "5-3-2", "4-3-1-2", "5-4-1"]
    STYLE_OPTIONS = [("low_block", "Low block", "Sit deep and compact. Hard to break down, but you give them the ball."),
                     ("mid_block", "Mid block", "Compact around halfway, press once they're in your half."),
                     ("press", "Press", "Press them in their half, counter-press when you lose it."),
                     ("high_press", "High press", "Squeeze right up and press everywhere. Wins it high, tiring.")]
    LINE_OPTIONS = [("deep", "Deep", "Never more than ~26 m out."),
                    ("low", "Low", "Up to ~32 m out."),
                    ("standard", "Standard", "Up to ~38 m out."),
                    ("high", "High", "Up to ~46 m - squeezes midfield."),
                    ("very_high", "Very high", "Up to halfway. Space in behind!")]
    PRESS_OPTIONS = [("low", "Low", "Only within ~40 m of your goal."),
                     ("mid", "Mid", "From just inside their half."),
                     ("high", "High", "Deep in their half; counter-press."),
                     ("vhigh", "Very high", "Up to their box - not the keeper."),
                     ("very_high", "Full", "Everywhere, even their keeper. Tiring.")]
    STYLE_LEVEL = {"low_block": ("deep", "low"), "mid_block": ("standard", "mid"), "press": ("high", "high"),
                   "high_press": ("very_high", "very_high")}
    BUILD_OPTIONS = [("play_out", "Play out", "Keep the ball from the back unless it's really on fire."),
                     ("mixed", "Mixed", "Play out when it's on, clear it when it isn't."),
                     ("clear", "Clear to flanks", "Get it away early and out wide, especially under pressure.")]

    def _line_press(self, club):
        """(back line, pressing) - the style's own unless you've set them."""
        t = club["tactics"]
        dl, dp = self.STYLE_LEVEL.get(t.get("defence"), ("standard", "mid"))
        return t.get("line_height") or dl, t.get("press_height") or dp

    def _set_line_press(self, field, key):
        club = self._my_club()
        t = club["tactics"]
        line, press = self._line_press(club)
        t["line_height"], t["press_height"] = (key, press) if field == "line_height" else (line, key)
        pair = (t["line_height"], t["press_height"])
        preset = next((st for st, lv in self.STYLE_LEVEL.items() if lv == pair), None)
        if preset:                                       # (that's just one of the four styles)
            t["defence"] = preset
            t.pop("line_height", None)
            t.pop("press_height", None)
        league.save(self.career)

    def _line_press_marks(self, club, pr):
        """Dashed lines on the tactics pitch: how far up the back line pushes, where the pressing starts."""
        import ai.tactics as tac
        import ai.team_shape as ts
        st = tac.style_for(club["tactics"].get("defence") or tac.DEFAULT_STYLE, club["tactics"])
        top, bot = pr.y + 10, pr.bottom - 10

        def y_of(m):
            return int(bot - min(m, ts.PITCH_L) / ts.PITCH_L * (bot - top))

        def dashed(y, col):
            x = pr.x + 10
            while x < pr.right - 10:
                pygame.draw.line(self.win, col, (x, y), (min(x + 10, pr.right - 10), y), 2)
                x += 16

        marks = [(y_of(st["line_max"]), (120, 190, 255), "Back line"),
                 (y_of(st["press_from"]) if st["press_from"] < ts.PITCH_L else top + 3, (255, 196, 80),
                  "Press from" if st["press_from"] < ts.PITCH_L else "Press everywhere")]
        self._lp_labels = []
        for i, (y, col, label) in enumerate(marks):
            dashed(y, col)
            t = self.fonts["small"].render(label, True, col)
            x = pr.x + 14 if i == 0 else pr.right - 14 - t.get_width() - 8   # (back line left, press right)
            self._lp_labels.append((t, pygame.Rect(x, y - t.get_height() - 3, t.get_width() + 8, t.get_height() + 2)))

    def _set_style(self, key):
        t = self._my_club()["tactics"]
        t["defence"] = key
        t.pop("line_height", None)                       # the style sets both
        t.pop("press_height", None)
        league.save(self.career)

    def _my_club(self):
        return self.career["clubs"][self.career["my_club"]]

    def _role_for_slot(self, club, slot):
        import roles.library as rl
        roles = club.get("roles") or {}
        if slot in roles:
            return roles[slot]
        from config import slots as slots_mod
        if slot not in rl.POSITIONS:                  # a spot outside the 4-4-2: its usual role
            return slots_mod.DEFAULT_ROLE.get(slot) or f"{slots_mod.proxy(slot)}_blue"
        base = roles.get("base", "blue") if isinstance(roles, dict) else roles
        return rl.ROLE_SETS.get(base, rl.ROLE_SETS["blue"]).get(slot)

    def _role_label(self, role_id, slot):
        import roles.library as rl
        from config import slots as slots_mod
        for rid, label, _ in rl.MANAGER_ROLES.get(rl.POSITION_GROUP.get(slots_mod.proxy(slot), ""), []):
            if rid == role_id:
                return label
        r = rl.ROLES.get(role_id)
        return r.name.split(" (")[0] if r else "-"

    def _menu_roles(self, club):
        """
        Give every position an explicit role from the Tactics menu, so what you
        see is exactly what's played (the old role sets include a few roles the
        menu doesn't offer - they're mapped to the nearest one).
        """
        import roles.library as rl
        nearest = {"LCM_red": "LCM_blue", "RB_red": "LB_blue", "ST2_red": "ST2_blue", "LCB_blue": "LCB_red",
                   "RCB_blue": "LCB_red", "RCB_red": "LCB_red", "RM_red_old": "LM_red"}
        roles = club.setdefault("roles", {})
        if isinstance(roles, str):
            roles = club["roles"] = {"base": roles}
        for slot in rl.POSITIONS:
            rid = self._role_for_slot(club, slot)
            menu = [r for r, _, _ in rl.MANAGER_ROLES[rl.POSITION_GROUP[slot]]]
            if rid not in menu:
                rid = nearest.get(rid, menu[0])
            roles[slot] = rid
        club["_menu_roles"] = True
        league.save(self.career)

    def _set(self, *path_and_value):
        *path, value = path_and_value
        d = self._my_club()
        for k in path[:-1]:
            d = d.setdefault(k, {})
        d[path[-1]] = value
        league.save(self.career)

    def _pick_player(self, slot, pid):
        club = self._my_club()
        lineup = club["lineup"]
        current = lineup.get(slot)
        other = next((s for s, p in lineup.items() if p == pid), None)
        if other is not None and other != slot:
            lineup[other] = current               # he was already in the XI: they swap places
        lineup[slot] = pid
        league.save(self.career)

    def _fit_text(self, s, font, width):
        """The text, cut short with ... if it's wider than `width`."""
        s = str(s)
        f = self.fonts[font]
        if f.size(s)[0] <= width:
            return s
        while s and f.size(s + "…")[0] > width:
            s = s[:-1]
        return s.rstrip() + "…"

    def _lines(self, s, font, width):
        """The text split into lines that fit `width` (for drawing yourself)."""
        lines, line = [], ""
        for w_ in str(s).split():
            if line and self.fonts[font].size(line + " " + w_)[0] > width:
                lines.append(line)
                line = w_
            else:
                line = (line + " " + w_).strip()
        return lines + ([line] if line else [])

    def _select_spot(self, s):
        self.tactics_slot = s
        self.tactics_msg = None

    def _move_to(self, spot):
        """Move the selected player to an empty spot on the grid."""
        from career import shapes
        slot = getattr(self, "tactics_slot", "GK")
        if slot == "GK":
            self.tactics_msg = "Click one of your outfield players first, then the empty spot to move him to."
            return
        club = self._my_club()
        problem = shapes.move(club, slot, spot)
        self.tactics_msg = problem
        self.tactics_note = False
        if not problem:
            self.tactics_slot = spot
            league.save(self.career)

    def _armband(self, pid, role):
        club = self._my_club()
        if pid is None:
            return
        changes = captains.set_captain(club, pid, role)
        if changes:
            bits = []
            for p, d, why in changes:
                feel = "proud" if d > 0 else "hurt"
                bits.append(f"{p['Name'].split(' ')[-1]} {why} - {feel}")
            self.tactics_msg = "; ".join(bits) + "."
            self.tactics_note = True
            league.save(self.career)

    def _preset(self, name):
        from career import shapes
        from config import slots as slots_mod
        club = self._my_club()
        out = avail.unavailable_ids(club, self.career["date"]) if self.career.get("date") else set()
        changes = shapes.remap(club, slots_mod.FORMATIONS[name], exclude=out)
        if getattr(self, "tactics_slot", "GK") not in club["lineup"]:
            self.tactics_slot = "GK"
        self.tactics_msg = None
        if changes:
            names = [f"{clubs_mod.player_by_id(club, i)['Name'].split(' ')[-1]} in at {slots_mod.LABEL[s]} for "
                     f"{clubs_mod.player_by_id(club, o)['Name'].split(' ')[-1]}" for s, i, o in changes]
            self.tactics_msg = "Assistant: " + ", ".join(names) + "."
            self.tactics_note = True
        league.save(self.career)

    def draw_tactics(self):
        import roles.library as rl
        W, H = self.size
        self.sidebar("tactics")
        club = self._my_club()
        if not club.get("_menu_roles"):
            self._menu_roles(club)
        slot = getattr(self, "tactics_slot", "LM")
        x0 = 250
        self.text("Tactics", "h1", TEXT, (x0, 18))

        # Team instructions: defending and build-up
        y = 78
        self.text("Out of possession", "small", MUTED, (x0, y))
        mixed = "line_height" in club["tactics"] or "press_height" in club["tactics"]
        for i, (key, label, desc) in enumerate(self.STYLE_OPTIONS):
            on = club["tactics"].get("defence") == key and not mixed
            b = Button((x0 + 130 + i * 128, y - 6, 120, 30), label,
                       lambda k=key: self._set_style(k), primary=on, font="btn_s")
            self.buttons.append(b)
        if mixed:
            self.text("Your own mix:", "small", ACCENT_HI, (x0 + 130 + 4 * 128 + 8, y))
        # ...and the two halves of it, set separately (ai/tactics.py): the style picks both
        line, press = self._line_press(club)
        for row, (label, opts, cur, field) in enumerate((("Back line", self.LINE_OPTIONS, line, "line_height"),
                                                         ("Pressing", self.PRESS_OPTIONS, press, "press_height"))):
            yy = y + 36 + row * 32
            self.text(label, "small", MUTED, (x0 + 18, yy))
            for i, (key, lab, d) in enumerate(opts):
                self.buttons.append(Button((x0 + 130 + i * 88, yy - 5, 84, 26), lab,
                                           lambda k=key, f=field: self._set_line_press(f, k), primary=cur == key,
                                           font="btn_s"))
            d = next(d for k, _, d in opts if k == cur)
            self.text(self._fit_text(d, "small", W - (x0 + 130 + 5 * 88) - 36), "small", MUTED,
                      (x0 + 130 + 5 * 88 + 6, yy))
        y = 178
        self.text("Build-up", "small", MUTED, (x0, y))
        for i, (key, label, d) in enumerate(self.BUILD_OPTIONS):
            on = club["tactics"].get("build_up") == key
            self.buttons.append(Button((x0 + 130 + i * 140, y - 6, 132, 30), label,
                                       lambda k=key: self._set("tactics", "build_up", k), primary=on, font="btn_s"))
        desc = next(d for k, _, d in self.BUILD_OPTIONS if k == club["tactics"].get("build_up"))
        self.text(self._fit_text(desc, "small", W - (x0 + 130 + 3 * 140) - 40), "small", MUTED,
                  (x0 + 130 + 3 * 140 + 8, y))

        # Formation: ready-made shapes
        from career import shapes
        from config import slots as slots_mod
        spots_now = clubs_mod.formation_of(club)
        name = clubs_mod.formation_name(club)
        if not clubs_mod.lineup_ok(club):
            shapes.remap(club, spots_now)
        if slot != "GK" and slot not in spots_now:
            slot = self.tactics_slot = "GK"
        y = 218
        self.text("Formation", "small", MUTED, (x0, y))
        for i, f in enumerate(self.PRESETS):
            self.buttons.append(Button((x0 + 130 + i * 76, y - 6, 70, 30), f, lambda f=f: self._preset(f),
                                       primary=f == name, font="btn_s"))

        # The pitch with the XI - and the empty spots you can move a man to
        pr = pygame.Rect(x0, 262, 440, H - 262 - 104)
        pygame.draw.rect(self.win, (34, 92, 52), pr, border_radius=10)
        pygame.draw.rect(self.win, (70, 130, 85), pr.inflate(-20, -20), 2)
        pygame.draw.line(self.win, (70, 130, 85), (pr.x + 10, pr.centery), (pr.right - 10, pr.centery), 2)
        pygame.draw.circle(self.win, (70, 130, 85), pr.center, 40, 2)
        pygame.draw.rect(self.win, (70, 130, 85), (pr.centerx - 90, pr.bottom - 10 - 60, 180, 60), 2)
        pygame.draw.rect(self.win, (70, 130, 85), (pr.centerx - 90, pr.y + 10, 180, 60), 2)
        lane_w = (pr.w - 40) / 5
        self._line_press_marks(club, pr)

        def spot_rect(s):
            r_, ln = slots_mod.GRID.get(s, (-1, 0))
            cx = pr.x + 20 + (ln + 2.5) * lane_w
            cy = pr.bottom - 20 - self.ROW_Y[r_] * (pr.h - 40)
            rect = pygame.Rect(0, 0, int(lane_w) - 3, 42)
            rect.center = (int(cx), int(cy))
            return rect

        moving = slot != "GK"
        for s in slots_mod.GRID:
            if s in spots_now:
                continue
            rect = spot_rect(s)
            pygame.draw.rect(self.win, (52, 112, 70) if moving else (44, 102, 62), rect, 1, border_radius=8)
            self.text(slots_mod.LABEL[s], "small", (96, 150, 110) if moving else (70, 128, 86), rect.center, "center")
            self.buttons.append(_Invisible(rect, lambda s=s: self._move_to(s)))
        for s in ["GK"] + spots_now:
            p = clubs_mod.player_by_id(club, club["lineup"][s])
            f = clubs_mod.fit(p, s)
            col = TEXT if f in (0, 4) else DRAW if f == 1 else LOSS
            if self.career.get("date") and not avail.available(p, self.career["date"]):
                col = LOSS
            spot = spot_rect(s)
            if s == slot:
                pygame.draw.rect(self.win, ACCENT, spot.inflate(6, 6), border_radius=10)
            pygame.draw.rect(self.win, PANEL, spot, border_radius=8)
            self.text(self._fit_text(p["Name"].split(" ")[-1], "small", spot.w - 4), "small", col,
                      (spot.centerx, spot.y + 4), "midtop")
            band = "C" if club.get("captain") == p["id"] else "VC" if club.get("vice") == p["id"] else None
            if band:
                br = pygame.Rect(spot.right - (18 if band == "C" else 26), spot.y - 8, 18 if band == "C" else 26, 16)
                pygame.draw.rect(self.win, (232, 196, 70), br, border_radius=5)
                self.text(band, "tiny", (30, 30, 30), br.center, "center")
            role = self._role_label(self._role_for_slot(club, s), s) if s != "GK" else "Goalkeeper"
            role = PITCH_ROLE.get(role, SHORT_ROLE.get(role, role))
            self.text(self._fit_text(role, "tiny", spot.w - 4), "tiny", MUTED, (spot.centerx, spot.y + 23), "midtop")
            self.buttons.append(_Invisible(spot, lambda s=s: self._select_spot(s)))
        for t, bg in getattr(self, "_lp_labels", []):          # (the line labels, on top of the boxes)
            pygame.draw.rect(self.win, (34, 92, 52), bg, border_radius=3)
            self.win.blit(t, (bg.x + 4, bg.y + 1))
        hint = getattr(self, "tactics_msg", None)
        if hint:
            self.text(self._fit_text(hint, "small", W - x0 - 30), "small",
                      ACCENT if getattr(self, "tactics_note", False) else LOSS, (x0, pr.bottom + 8))
        else:
            self.text(f"{name if name != 'Custom' else 'Your own shape'}  ·  click a player, then an empty spot to "
                      f"move him there", "small", MUTED, (x0, pr.bottom + 8))
        cap, vice = captains.armband(club)
        rec, _ = captains.recommend(club)
        line = (f"Captain: {cap['Name'] if cap else 'none'}  ·  Vice: {vice['Name'] if vice else 'none'}"
                + (f"  ·  Assistant: \u201c{rec['Name'].split(' ')[-1]} would be my captain.\u201d"
                   if rec is not None and (cap is None or rec['id'] != cap['id']) else ""))
        self.text(self._fit_text(line, "small", W - x0 - 30), "small", MUTED, (x0, pr.bottom + 28))

        # The selected position: player, role, instructions
        rx = pr.right + 18
        rr = pygame.Rect(rx, 262, W - rx - 30, pr.h)
        self.panel(rr)
        self.text(self.SLOT_NAMES.get(slot, slot), "h3", TEXT, (rr.x + 16, rr.y + 12))
        here = club["lineup"].get(slot)                  # the armband (career/captains.py)
        self.buttons.append(Button((rr.right - 180, rr.y + 8, 92, 30), "Captain",
                                   lambda pid=here: self._armband(pid, "captain"), primary=club.get("captain") == here,
                                   font="btn_s"))
        self.buttons.append(Button((rr.right - 82, rr.y + 8, 66, 30), "Vice",
                                   lambda pid=here: self._armband(pid, "vice"), primary=club.get("vice") == here,
                                   font="btn_s"))
        y = rr.y + 46
        if slot != "GK":
            group = rl.POSITION_GROUP[slots_mod.proxy(slot)]
            cur = self._role_for_slot(club, slot)
            options = rl.MANAGER_ROLES[group]
            bw = (rr.w - 40) // 2
            for i, (rid, label, desc) in enumerate(options):
                on = rid == cur or (len(options) == 1)
                bx = rr.x + 16 + (i % 2) * (bw + 8)
                self.buttons.append(Button((bx, y + (i // 2) * 34, bw, 28), label,
                                           lambda r=rid: self._set("roles", slot, r), primary=on, font="btn_s"))
            y += ((len(options) + 1) // 2) * 34
            chosen = next((d for r, _, d in options if r == cur), options[0][2])
            for line in self._lines(chosen, "small", rr.w - 32):
                self.text(line, "small", MUTED, (rr.x + 16, y))
                y += 18
            y += 8
            if slots_mod.kind(slot) in ("FB", "WM", "WB", "W"):
                y += 2
                ins = rl.instructions_for(_Probe(slot, club, self._role_for_slot(club, slot)))   # role defaults
                ins.update(club.get("instructions", {}).get(slot, {}))                           # your choices
                self.text("Crossing", "small", MUTED, (rr.x + 16, y + 6))
                for i, v in enumerate(("less", "normal", "more")):
                    self.buttons.append(Button((rr.x + 110 + i * 92, y, 86, 28), v.capitalize(),
                                               lambda v=v: self._set("instructions", slot, "crossing", v),
                                               primary=ins["crossing"] == v, font="btn_s"))
                y += 34
                self.text("Cross from", "small", MUTED, (rr.x + 16, y + 6))
                for i, v in enumerate(("early", "mixed", "byline")):
                    self.buttons.append(Button((rr.x + 110 + i * 92, y, 86, 28), v.capitalize(),
                                               lambda v=v: self._set("instructions", slot, "cross_from", v),
                                               primary=ins["cross_from"] == v, font="btn_s"))
                y += 34
        # Who plays there
        y += 8
        self.text("Player", "small", MUTED, (rr.x + 16, y))
        self.text("Rating there", "small", MUTED, (rr.right - 200, y))
        y += 20
        in_xi = {pid: s for s, pid in club["lineup"].items()}
        cands = sorted(club["players"], key=lambda p: -clubs_mod.overall(p, slot))
        rows = max(4, (rr.bottom - y - 8) // 24)
        today = self.career.get("date") or ""
        for p in cands[:rows]:
            row = pygame.Rect(rr.x + 10, y - 2, rr.w - 20, 22)
            chosen = club["lineup"][slot] == p["id"]
            st = avail.status(p, today) if today else ""
            if chosen:
                pygame.draw.rect(self.win, HIGHLIGHT, row, border_radius=5)
            f = clubs_mod.fit(p, slot)
            self.text(self._fit_text(f"{p['Pos']:<3} {p['Name']}", "small", rr.w - 236), "small", TEXT, (rr.x + 16, y))
            self.text(clubs_mod.overall(p, slot), "small", ACCENT if f in (0, 4) else DRAW if f == 1 else LOSS,
                      (rr.right - 200, y))
            tag = clubs_mod.FIT_LABEL[f] if f else ""
            if p["id"] in in_xi and not chosen:
                tag = (tag + "  ·  " if tag else "") + f"at {slots_mod.LABEL.get(in_xi[p['id']], in_xi[p['id']])}"
            cnd = training.condition(p)
            if cnd < 0.97:
                tag = (tag + "  ·  " if tag else "") + f"fitness {round(100 * cnd)}%"
            if p.get("rest_for"):
                tag = "Resting next game"
            if st:
                tag = ("Injured" if st.startswith("INJ") else "Suspended") + f" ({st[4:]})"
            self.text(self._fit_text(tag, "small", 164), "small", (LOSS if st else MUTED), (rr.right - 168, y))
            if not st:                                   # can't pick an injured / suspended man
                self.buttons.append(_Invisible(row, lambda pid=p["id"]: self._pick_player(slot, pid)))
            y += 24

        # Next opponent
        nf = league.next_fixture(self.career)
        if nf:
            _, home, away = nf
            opp = away if home == self.career["my_club"] else home
            oc = self.career["clubs"][opp]
            best = max((clubs_mod.player_by_id(oc, pid) for pid in oc["lineup"].values()),
                       key=lambda p: clubs_mod.overall(p))
            msg = (f"Next: {oc['name']} - {STYLE_TEXT[oc['tactics']['defence']]}, "
                   f"{BUILD_TEXT[oc['tactics']['build_up']]}.  Danger man: {best['Name']} ({best['Pos']}, "
                   f"{clubs_mod.overall(best)})")
            self.text(self._fit_text(msg, "small", W - x0 - 30), "small", MUTED, (x0, H - 46))

    # -- table --------------------------------------------------------------
    # -- the Spanish league ---------------------------------------------------
    def draw_spain(self):
        W, H = self.size
        self.sidebar("spain")
        self._paper_tabs("spain")
        c = self.career
        s = c["spain"]
        x0 = 250
        self.text(spain.NAME, "h1", TEXT, (x0, 18))
        played = s["matchday"] - 1
        sub = f"Spain  ·  played {played} of {len(s['fixtures'])} matchdays  ·  quick results, in the background"
        if s.get("history"):
            last = s["history"][-1]
            sub += f"  ·  champions last season: {self.name(last['champion'])}"
        self.text(self._fit_text(sub, "body", W - 30 - 3 * 112 - x0 - 16), "body", MUTED, (x0, 72))
        tab = getattr(self, "es_tab", "table")
        for i, (key, label) in enumerate((("table", "Table"), ("results", "Results"), ("scorers", "Top scorers"))):
            self.buttons.append(Button((W - 30 - (3 - i) * 112, 68, 106, 30), label,
                                       lambda k=key: setattr(self, "es_tab", k), primary=tab == key, font="btn_s"))
        r = pygame.Rect(x0, 106, W - x0 - 30, H - 126)
        self.panel(r)
        if tab == "table":
            self._table_rows(spain.table(c), r.x + 20, r.y + 14, r.w - 40)
            return
        if tab == "scorers":
            y = r.y + 14
            for label, cx in (("", 0), ("Player", 40), ("Club", 330), ("Apps", r.w - 170), ("Goals", r.w - 90)):
                self.text(label, "small", MUTED, (r.x + 20 + cx, y))
            y += 28
            for i, (n, p, club) in enumerate(spain.top_scorers(c, 20), start=1):
                self.text(str(i), "body", MUTED, (r.x + 20, y))
                self.text(f"{p['Name']} ({p['Pos']}, {p['Age']})", "body", TEXT, (r.x + 60, y))
                _badge(self.win, tuple(club["colour"]), (r.x + 358, y + 11), 7, club)
                self.text(club["name"], "body", TEXT, (r.x + 372, y))
                self.text(str(p.get("lg_apps", 0)), "body", TEXT, (r.x + r.w - 150, y))
                self.text(str(n), "body", TEXT, (r.x + r.w - 70, y))
                self.buttons.append(_Invisible(pygame.Rect(r.x + 10, y - 3, r.w - 20, 27),
                                               lambda cid=club["id"], pid=p["id"]: self.view_player(cid, pid)))
                y += 30
            if not spain.top_scorers(c, 1):
                self.text("No goals yet - the season hasn't started.", "body", MUTED, (r.x + 20, y))
            return
        # Results, a matchday at a time
        md = getattr(self, "es_md", None)
        if md is None or md > max(1, played) or md < 1:
            md = self.es_md = max(1, played)
        self.buttons.append(Button((r.x + 16, r.y + 12, 44, 34), "<",
                                   lambda: setattr(self, "es_md", max(1, md - 1)), font="btn_s"))
        self.buttons.append(Button((r.x + 380, r.y + 12, 44, 34), ">",
                                   lambda: setattr(self, "es_md", min(max(1, played), md + 1)), font="btn_s"))
        date = (c.get("calendar") or [None] * md)[md - 1]
        self.text(f"Matchday {md}" + (f"  ·  {cal.fmt(date, False)}" if date else ""), "h3", TEXT,
                  (r.x + 72, r.y + 16))
        res = s["results"].get(str(md))
        y = r.y + 64
        if not res:
            self.text("No matches played yet.", "body", MUTED, (r.x + 20, y))
            return
        mid = r.x + r.w // 2
        for m in res:
            self.text(self.name(m["home"]), "body", TEXT, (mid - 50, y), "topright")
            self.text(f"{m['hg']} - {m['ag']}", "h3", TEXT, (mid, y - 2), "midtop")
            self.text(self.name(m["away"]), "body", TEXT, (mid + 50, y))
            sc = [[], []]
            for g in m.get("goals", []):
                sc[g["team"]].append(f"{g['name'].split(' ')[-1]} {g['minute']}'")
            self.text(", ".join(sc[0]), "small", MUTED, (mid - 50, y + 24), "topright")
            self.text(", ".join(sc[1]), "small", MUTED, (mid + 50, y + 24))
            y += 64

    def _paper_tabs(self, active):
        """League table / Fixtures / Spain - the newspaper's sports pages (office)."""
        W, H = self.size
        tabs = (("papers", "Papers"), ("table", "League table"), ("fixtures", "Fixtures"), ("spain", "Spain"))
        for i, (key, label) in enumerate(tabs):
            self.buttons.append(Button((W - 30 - len(tabs) * 128 + i * 128, 24, 122, 36), label,
                                       lambda k=key: self._menu(k), primary=key == active, font="btn_s"))

    def _laptop_tabs(self, active, x):
        """Transfers / Social media - the laptop (office)."""
        for i, (key, label) in enumerate((("transfers", "Transfers"), ("social", "Social media"))):
            self.buttons.append(Button((x + i * 136, 24, 130, 34), label, lambda k=key: self._menu(k),
                                       primary=key == active, font="btn_s"))

    # -- the papers (career/media.py) ---------------------------------------------
    PAPER_STYLE = {media.TABLOID: ("tabloid", (200, 30, 35), (255, 255, 255)),
                   media.BROADSHEET: ("broadsheet", (245, 240, 228), (20, 20, 20))}

    def _paper_look(self, paper):
        return self.PAPER_STYLE.get(paper, ("local", (25, 50, 95), (255, 255, 255)))

    def _pfont(self, size, bold=False, serif=True):
        key = ("pf", size, bold, serif)
        cache = self.__dict__.setdefault("_pfonts", {})
        if key not in cache:
            cache[key] = pygame.font.SysFont("georgia,timesnewroman,serif" if serif else "arial", size, bold=bold)
        return cache[key]

    def draw_papers(self):
        W, H = self.size
        self.sidebar("table")
        self._paper_tabs("papers")
        c = self.career
        media.catch_up(c)
        self.text("The papers", "h1", TEXT, (250, 24))
        local = media.local_paper(c)
        papers = [None, media.TABLOID, media.BROADSHEET, local]
        pf = getattr(self, "paper_filter", None)
        if pf not in papers:
            pf = self.paper_filter = None
        for i, pp in enumerate(papers):
            self.buttons.append(Button((250 + [0, 134, 314, 534][i], 80, [128, 174, 214, 210][i], 30), pp or "All papers",
                                       lambda v=pp: (setattr(self, "paper_filter", v), setattr(self, "paper_page", 0)),
                                       primary=pf == pp, font="btn_s"))
        arts = [a for a in media.articles(c) if pf is None or (a["paper"] == pf or (pf == local and a["paper"] == "local"))]
        lst = pygame.Rect(250, 122, 380, H - 152)
        self.panel(lst)
        rows = max(1, (lst.h - 60) // 54)
        page = min(getattr(self, "paper_page", 0), max(0, (len(arts) - 1) // rows))
        sel = getattr(self, "paper_sel", None)
        if not arts:
            self.text("Nothing in the papers yet.", "body", MUTED, (lst.x + 16, lst.y + 16))
        if sel is None or not any(a["id"] == sel for a in arts):
            sel = self.paper_sel = arts[0]["id"] if arts else None
        y = lst.y + 10
        mouse = pygame.mouse.get_pos()
        for a in arts[page * rows:(page + 1) * rows]:
            row = pygame.Rect(lst.x + 8, y, lst.w - 16, 50)
            if a["id"] == sel:
                pygame.draw.rect(self.win, HIGHLIGHT, row, border_radius=6)
            elif row.collidepoint(mouse):
                pygame.draw.rect(self.win, PANEL_2, row, border_radius=6)
            name = local if a["paper"] == "local" else a["paper"]
            kind, bg, fg = self._paper_look(a["paper"])
            col = (235, 80, 80) if kind == "tabloid" else (130, 160, 220) if kind == "local" else (200, 195, 180)
            self.text(f"{name}  ·  {cal.fmt(a['date'], False) if a.get('date') else ''}", "tiny", col,
                      (row.x + 8, row.y + 5))
            self.text(self._fit_text(a["head"], "body", row.w - 16), "body", TEXT, (row.x + 8, row.y + 22))
            self.buttons.append(_Invisible(row, lambda i=a["id"]: setattr(self, "paper_sel", i)))
            y += 54
        if len(arts) > rows:
            self.buttons.append(Button((lst.x + 10, lst.bottom - 44, 90, 34), "Newer",
                                       lambda: setattr(self, "paper_page", max(0, page - 1)), enabled=page > 0,
                                       font="btn_s"))
            self.buttons.append(Button((lst.right - 100, lst.bottom - 44, 90, 34), "Older",
                                       lambda: setattr(self, "paper_page", page + 1),
                                       enabled=(page + 1) * rows < len(arts), font="btn_s"))
            self.text(f"{page + 1} / {(len(arts) - 1) // rows + 1}", "small", MUTED, (lst.centerx, lst.bottom - 36),
                      "midtop")
        a = next((x for x in arts if x["id"] == sel), None)
        if a is not None:
            more = [x for x in media.articles(c) if x["paper"] == a["paper"] and x["id"] != a["id"]][:4]
            self._article(a, pygame.Rect(lst.right + 16, 122, W - lst.right - 46, H - 152), local, more)

    def _article(self, a, r, local, more=()):
        """One story, printed in its paper's style."""
        kind, bg, fg = self._paper_look(a["paper"])
        name = local if a["paper"] == "local" else a["paper"]
        pygame.draw.rect(self.win, (238, 233, 220), r, border_radius=6)              # newsprint
        mast = pygame.Rect(r.x, r.y, r.w, 64)
        pygame.draw.rect(self.win, bg, mast, border_top_left_radius=6, border_top_right_radius=6)
        if kind == "tabloid":
            t = self._pfont(34, True, serif=False).render(name.upper(), True, fg)
        elif kind == "broadsheet":
            t = self._pfont(30, True).render(name, True, fg)
            pygame.draw.line(self.win, (40, 40, 40), (r.x + 12, mast.bottom - 4), (r.right - 12, mast.bottom - 4), 2)
        else:
            t = self._pfont(28, True).render(name, True, fg)
        self.win.blit(t, t.get_rect(center=mast.center))
        y = mast.bottom + 10
        d = cal.fmt(a["date"]) if a.get("date") else ""
        self.win.blit(self._pfont(13, False, serif=kind != "tabloid").render(d, True, (90, 85, 80)), (r.x + 18, y))
        y += 26
        hf = self._pfont(34 if kind == "tabloid" else 26, True, serif=kind != "tabloid")
        for line in self._wrap_font(a["head"].upper() if kind == "tabloid" else a["head"], hf, r.w - 36):
            self.win.blit(hf.render(line, True, (180, 20, 25) if kind == "tabloid" else (20, 20, 20)), (r.x + 18, y))
            y += hf.get_height() + 2
        y += 10
        pygame.draw.line(self.win, (170, 165, 155), (r.x + 18, y), (r.right - 18, y), 1)
        y += 12
        bf = self._pfont(17, False, serif=True)
        stop = r.bottom - 26 - (30 + 26 * len(more) if more else 0)
        for line in self._wrap_font(a["body"], bf, r.w - 36):
            if y > stop:
                break
            self.win.blit(bf.render(line, True, (35, 32, 30)), (r.x + 18, y))
            y += bf.get_height() + 4
        if more:                                            # the rest of the page
            y = r.bottom - 22 - 26 * len(more) - 24
            pygame.draw.line(self.win, (170, 165, 155), (r.x + 18, y), (r.right - 18, y), 1)
            self.win.blit(self._pfont(13, True, serif=False).render("MORE FROM " + (local if a["paper"] == "local"
                          else a["paper"]).upper(), True, (110, 100, 90)), (r.x + 18, y + 6))
            y += 28
            mf = self._pfont(15, True, serif=kind != "tabloid")
            mouse = pygame.mouse.get_pos()
            for x in more:
                row = pygame.Rect(r.x + 12, y - 2, r.w - 24, 24)
                if row.collidepoint(mouse):
                    pygame.draw.rect(self.win, (222, 214, 196), row, border_radius=4)
                txt = x["head"]
                while mf.size(txt)[0] > r.w - 40 and len(txt) > 4:
                    txt = txt[:-4] + "..."
                self.win.blit(mf.render(txt, True, (60, 50, 45)), (r.x + 18, y))
                self.buttons.append(_Invisible(row, lambda i=x["id"]: (setattr(self, "paper_sel", i),
                                                                       setattr(self, "paper_filter", None))))
                y += 26

    def _wrap_font(self, text, font, width):
        words, lines, cur = text.split(" "), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if font.size(t)[0] <= width or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    # -- social media (career/media.py) -------------------------------------------
    def draw_social(self):
        W, H = self.size
        self.sidebar("transfers")
        c = self.career
        media.catch_up(c)
        x0 = 250
        self.text("Social media", "h1", TEXT, (x0, 18))
        self._laptop_tabs("social", x0 + 330)
        me = self._my_club()
        mine_only = getattr(self, "social_mine", False)
        for i, (v, label) in enumerate(((False, "Everything"), (True, "About us"))):
            self.buttons.append(Button((x0 + i * 130, 76, 124, 30), label,
                                       lambda v=v: (setattr(self, "social_mine", v), setattr(self, "social_starts", [0])),
                                       primary=mine_only == v, font="btn_s"))
        feed = [p for p in media.posts(c) if not mine_only or p.get("club") == me["id"]]
        r = pygame.Rect(x0, 118, 560, H - 148)
        pygame.draw.rect(self.win, (20, 24, 30), r, border_radius=10)
        y = r.y + 10
        starts = self.__dict__.setdefault("social_starts", [0])
        start = min(starts[-1], max(0, len(feed) - 1))
        shown = 0
        if not feed:
            self.text("Quiet so far. Play a match and the internet will have opinions.", "body", MUTED, (r.x + 16, y + 6))
        for post in feed[start:]:
            lines = self._lines(post["text"], "body", r.w - 90)
            h = 30 + 24 * len(lines) + 22
            if y + h > r.bottom - 50:
                break
            self._post(post, pygame.Rect(r.x + 8, y, r.w - 16, h), lines, me)
            y += h + 6
            shown += 1
        if len(starts) > 1:
            self.buttons.append(Button((r.x + 10, r.bottom - 42, 90, 32), "Newer", lambda: starts.pop(), font="btn_s"))
        if start + shown < len(feed) and shown:
            self.buttons.append(Button((r.right - 100, r.bottom - 42, 90, 32), "Older",
                                       lambda n=start + shown: starts.append(n), font="btn_s"))
        # the fans' mood
        r2 = pygame.Rect(r.right + 16, 118, W - r.right - 46, 300)
        self.panel(r2, "Fan mood")
        m = media.mood(c)
        word = media.mood_word(m)
        col = MORALE_COLOUR["good" if m >= 64 else "ok" if m >= 45 else "bad"]
        self.text(word, "h1", col, (r2.x + 16, r2.y + 48))
        bar = pygame.Rect(r2.x + 16, r2.y + 108, r2.w - 32, 14)
        pygame.draw.rect(self.win, PANEL_2, bar, border_radius=7)
        pygame.draw.rect(self.win, col, (bar.x, bar.y, int(bar.w * m / 100), bar.h), border_radius=7)
        hist = (c.get("media") or {}).get("mood_hist", [])
        if len(hist) >= 2:
            trend = hist[-1] - hist[-2]
            self.text(("Rising" if trend > 1 else "Falling" if trend < -1 else "Steady") + " since the last game", "small",
                      MUTED, (r2.x + 16, r2.y + 132))
        notes = []
        if m >= 64:
            notes.append("The crowd will be right behind the team at home.")
            notes.append("The board hears the fans are happy.")
        elif m < 45:
            notes.append("The home crowd is getting edgy - the players feel it.")
            notes.append("Grumbling from the stands is reaching the boardroom.")
        else:
            notes.append("The fans are with you - for now.")
        y = r2.y + 162
        for n in notes:
            y = self._wrap(n, "small", MUTED, r2.x + 16, y, r2.w - 32) + 6
        r3 = pygame.Rect(r2.x, r2.bottom + 16, r2.w, H - r2.bottom - 46)
        self.panel(r3, "What moves them")
        y = r3.y + 48
        for n in ("Results - above all, against what they expect.", "Big signings lift them; selling stars hurts.",
                  "They forget slowly, but they do forget."):
            y = self._wrap(n, "small", MUTED, r3.x + 16, y, r3.w - 32) + 8

    def _post(self, post, r, lines, me):
        """One post: avatar, name, handle, text, likes."""
        pygame.draw.rect(self.win, (30, 36, 45), r, border_radius=8)
        ax, ay = r.x + 10, r.y + 10
        kind = post["kind"]
        if kind == "player" and post.get("pid") is not None:
            p = clubs_mod.player_by_id(me, post["pid"])
            if p is not None:
                self._face(p, me["id"], 36, (ax, ay), border=False)
            else:
                pygame.draw.circle(self.win, (90, 90, 100), (ax + 18, ay + 18), 18)
        elif kind == "club" and post.get("club") is not None:
            _badge(self.win, self.colour(post["club"]), (ax + 18, ay + 18), 18, self._club_of(post["club"]))
        else:
            colr = {"fan": tuple(me.get("colour", (120, 120, 120))), "rival": (110, 110, 120),
                    "journo": (60, 120, 200)}.get(kind, (100, 100, 110))
            pygame.draw.circle(self.win, colr, (ax + 18, ay + 18), 18)
            t = self.fonts["h3"].render(post["who"][:1].upper(), True, (255, 255, 255))
            self.win.blit(t, t.get_rect(center=(ax + 18, ay + 18)))
        x = r.x + 58
        self.text(self._fit_text(post["who"], "h3", 220), "h3", TEXT, (x, r.y + 6))
        nx = x + self.fonts["h3"].size(self._fit_text(post["who"], "h3", 220))[0] + 8
        tag = {"journo": "  · journalist", "player": "  · player", "club": "  · official", "rival": ""}.get(kind, "")
        when = cal.fmt(post["date"], False) if post.get("date") else ""
        self.text(self._fit_text(f"{post['handle']}{tag}  ·  {when}", "small", r.right - nx - 10), "small", MUTED,
                  (nx, r.y + 10))
        y = r.y + 32
        for line in lines:
            self.text(line, "body", TEXT, (x, y))
            y += 24
        likes = post["likes"]
        self.text(f"{likes / 1000:.1f}k likes" if likes >= 1000 else f"{likes} likes", "tiny", MUTED, (x, y + 2))

    def draw_table(self):
        W, H = self.size
        self.sidebar("table")
        self._paper_tabs("table")
        from career import divisions
        mine = divisions.my_div(self.career)
        div = getattr(self, "table_div", None) or mine
        if not divisions.exists(self.career):
            div = mine
        self.text(divisions.name(div), "h1", TEXT, (250, 24))
        if divisions.exists(self.career):
            for i, d in enumerate(divisions.ORDER):
                self.buttons.append(Button((250 + i * 170, 60, 162, 26), divisions.name(d),
                                           lambda d=d: setattr(self, "table_div", d), primary=d == div, font="btn_s"))
            if div != mine:
                o = self.career["other"]
                self.text(f"Played {o['matchday'] - 1} of {len(o['fixtures'])}  ·  quick results, in the background",
                          "small", MUTED, (600, 65))
        scorers = getattr(self, "table_scorers", False)
        self.buttons.append(Button((W - 30 - 170, 60, 170, 26), "Table" if scorers else "Top scorers",
                                   lambda: setattr(self, "table_scorers", not scorers), font="btn_s"))
        r = pygame.Rect(250, 94, W - 280, H - 124)
        self.panel(r)
        if not scorers:
            self._table_rows(league.table(self.career, div), r.x + 20, r.y + 18, r.w - 40)
            return
        y = r.y + 14
        for label, cx in (("", 0), ("Player", 40), ("Club", 380), ("Apps", r.w - 170), ("Goals", r.w - 90)):
            self.text(label, "small", MUTED, (r.x + 20 + cx, y))
        y += 28
        rows = league.top_scorers(self.career, div, 22)
        if not rows:
            self.text("No goals yet - the season hasn't started.", "body", MUTED, (r.x + 20, y))
        for i, (n, apps, p, club) in enumerate(rows, start=1):
            self.text(str(i), "body", MUTED, (r.x + 20, y))
            self.text(f"{p['Name']} ({p['Pos']}, {p['Age']})", "body", TEXT, (r.x + 60, y))
            _badge(self.win, tuple(club["colour"]), (r.x + 408, y + 11), 7, club)
            self.text(club["name"], "body", TEXT, (r.x + 422, y))
            self.text(str(apps), "body", TEXT, (r.x + r.w - 150, y))
            self.text(str(n), "body", TEXT, (r.x + r.w - 70, y))
            self.buttons.append(_Invisible(pygame.Rect(r.x + 10, y - 3, r.w - 20, 27),
                                           lambda cid=club["id"], pid=p["id"]: self.view_player(cid, pid)))
            y += 29

    # -- training -----------------------------------------------------------
    def _set_training(self, key, value):
        club = self._my_club()
        club.setdefault("training", dict(training.DEFAULT))[key] = value
        league.save(self.career)

    def draw_training(self):
        W, H = self.size
        self.sidebar("training")
        c = self.career
        club = self._my_club()
        s = training.settings(club)
        x0 = 250
        self.text("Training", "h1", TEXT, (x0, 18))
        self.text("Counts from today until each match. Young players improve towards their potential - "
                  "faster with games and harder training.", "small", MUTED, (x0, 70))
        y = 104
        self.text("Focus", "small", MUTED, (x0, y + 8))
        for i, (key, (label, desc, _)) in enumerate(training.FOCUS.items()):
            self.buttons.append(Button((x0 + 90 + i * 128, y, 122, 32), label,
                                       lambda k=key: self._set_training("focus", k), primary=s["focus"] == key,
                                       font="btn_s"))
        self.text(training.FOCUS[s["focus"]][1], "small", MUTED, (x0 + 90, y + 40))
        y = 176
        self.text("Intensity", "small", MUTED, (x0, y + 8))
        effects = {"light": "Quicker recovery, fewer injuries, slower development.",
                   "normal": "Full fitness about four days after a match.",
                   "hard": "Faster development - but slower recovery and more injuries."}
        for i, (key, (label, *_)) in enumerate(training.INTENSITY.items()):
            self.buttons.append(Button((x0 + 90 + i * 128, y, 122, 32), label,
                                       lambda k=key: self._set_training("intensity", k),
                                       primary=s["intensity"] == key, font="btn_s"))
        self.text(effects[s["intensity"]], "small", MUTED, (x0 + 90, y + 40))

        # The squad: fitness and development
        r = pygame.Rect(x0, 246, W - x0 - 30, H - 266)
        self.panel(r)
        cols = [("Pos", 0), ("Name", 46), ("Age", 250), ("Fitness", 300), ("Rating", 470),
                ("This season", 540), ("Coaches' view", 650)]
        y = r.y + 12
        for label, cx in cols:
            self.text(label, "small", MUTED, (r.x + 18 + cx, y))
        y += 24
        today = c.get("date") or ""
        order = {p: i for i, p in enumerate(["GK", "LB", "LWB", "CB", "RB", "RWB", "DM", "CM", "AM", "LM", "LW",
                                                "RM", "RW", "ST"])}
        step = min(30, (r.bottom - y - 4) // max(1, len(club["players"])))
        for p in sorted(club["players"], key=lambda p: (order.get(p["Pos"], 99), -clubs_mod.overall(p))):
            cnd = training.condition(p)
            rating = clubs_mod.overall(p)
            start = p.get("season_start_rating", rating)
            change = rating - start
            st = avail.status(p, today) if today else ""
            gap = (p.get("Potential") or rating) - rating
            age = p.get("Age", 26)
            if st:
                view, vcol = ("Injured" if st.startswith("INJ") else "Suspended"), LOSS
            elif age <= 21 and gap >= 8:
                view, vcol = "Could become a top player", ACCENT
            elif age <= 23 and gap >= 4:
                view, vcol = "Still improving", TEXT
            elif age >= 30:
                view, vcol = "Experienced", MUTED
            else:
                view, vcol = "At his level", MUTED
            vals = [p["Pos"], p["Name"], age, None, rating, f"{change:+d}" if change else "-", view]
            for (label, cx), v in zip(cols, vals):
                if label == "Fitness":
                    bar = pygame.Rect(r.x + 18 + cx, y + 6, 110, 9)
                    pygame.draw.rect(self.win, PANEL_2, bar, border_radius=4)
                    colr = ACCENT if cnd >= 0.95 else DRAW if cnd >= training.FIT_TO_PLAY else LOSS
                    pygame.draw.rect(self.win, colr, (bar.x, bar.y, int(bar.w * cnd), bar.h), border_radius=4)
                    self.text(f"{round(100 * cnd)}%", "small", colr, (bar.right + 8, y + 2))
                    continue
                col = vcol if label == "Coaches' view" else (ACCENT if label == "This season" and change > 0 else
                                                             LOSS if label == "This season" and change < 0 else TEXT)
                self.text(v, "small" if label == "Coaches' view" else "body", col, (r.x + 18 + cx, y))
            row = pygame.Rect(r.x + 8, y - 2, r.w - 16, step - 2)
            self.buttons.append(_Invisible(row, lambda pid=p["id"]: self.view_player(club["id"], pid)))
            y += step

    # -- calendar -----------------------------------------------------------
    def _cal_move(self, delta):
        y, m = self.cal_ym
        m += delta
        if m < 1:
            y, m = y - 1, 12
        elif m > 12:
            y, m = y + 1, 1
        self.cal_ym = (y, m)

    def _my_fixture(self, md):
        mc = self.career["my_club"]
        for home, away in self.career["fixtures"][md - 1]:
            if mc in (home, away):
                return home, away
        return None

    def draw_calendar(self):
        import calendar as pycal
        W, H = self.size
        self.sidebar("calendar")
        c = self.career
        if not hasattr(self, "cal_ym"):
            d = cal.parse(c["date"])
            self.cal_ym = (d.year, d.month)
        y, m = self.cal_ym
        x0 = 250
        self.text("Calendar", "h1", TEXT, (x0, 18))
        self.buttons.append(Button((x0 + 300, 30, 46, 40), "<", lambda: self._cal_move(-1)))
        self.text(f"{pycal.month_name[m]} {y}", "h2", TEXT, (x0 + 470, 34), "midtop")
        self.buttons.append(Button((x0 + 594, 30, 46, 40), ">", lambda: self._cal_move(1)))
        days = {d: i + 1 for i, d in enumerate(c.get("calendar", []))}
        breaks = set(c.get("breaks", []))
        fr_on = {f["date"]: f for f in friendlies.all_(c)}
        st_po = playoffs.state(c)
        po_on = {m_["date"]: m_ for m_ in (st_po or {}).get("matches", []) if playoffs.involved(c, m_)}
        self.text("Click a free day to arrange a friendly", "small", MUTED, (x0 + 470, 72), "midtop")
        today = c.get("date")
        r = pygame.Rect(x0, 90, W - x0 - 30, H - 110)
        self.panel(r)
        cw = (r.w - 20) // 7
        for i, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            self.text(name, "small", MUTED, (r.x + 10 + i * cw + cw // 2, r.y + 10), "midtop")
        weeks = pycal.Calendar(0).monthdatescalendar(y, m)
        ch = min(108, (r.h - 40) // len(weeks))
        mc = c["my_club"]
        for wi, week in enumerate(weeks):
            for di, d in enumerate(week):
                cell = pygame.Rect(r.x + 10 + di * cw + 2, r.y + 34 + wi * ch + 2, cw - 4, ch - 4)
                iso = d.isoformat()
                inside = d.month == m
                pygame.draw.rect(self.win, PANEL_2 if inside else PANEL, cell, border_radius=6)
                if iso == today:
                    pygame.draw.rect(self.win, ACCENT, cell, 2, border_radius=6)
                self.text(d.day, "small", TEXT if inside else MUTED, (cell.x + 6, cell.y + 4))
                md = days.get(iso)
                if md and inside:
                    fx = self._my_fixture(md)
                    if fx:
                        home, away = fx
                        opp = away if home == mc else home
                        _badge(self.win, self.colour(opp), (cell.x + 14, cell.y + 36), 7, self._club_of(opp))
                        self.text(f"{self.name(opp, True)} ({'H' if home == mc else 'A'})", "small", TEXT,
                                  (cell.x + 26, cell.y + 27))
                        res = next((x for x in c["results"].get(str(md), [])
                                    if x["home"] == home and x["away"] == away), None)
                        if res:
                            gf, ga = (res["hg"], res["ag"]) if home == mc else (res["ag"], res["hg"])
                            out = "W" if gf > ga else "D" if gf == ga else "L"
                            col = {"W": WIN, "D": DRAW, "L": LOSS}[out]
                            self.text(f"{out} {gf}-{ga}", "small", col, (cell.x + 6, cell.y + 50))
                        else:
                            self.text(f"{cal.kick_off(iso)}  ·  MD {md}", "small", MUTED, (cell.x + 6, cell.y + 50))
                    self.buttons.append(_Invisible(cell, lambda md=md: self._cal_open(md)))
                elif inside and po_on.get(iso):
                    pm = po_on[iso]
                    opp = pm["away"] if pm["home"] == mc else pm["home"]
                    self.text("Play-off final" if pm["round"] == "final" else f"Play-off, leg {pm['leg']}", "small",
                              ACCENT_HI, (cell.x + 6, cell.y + 24))
                    self.text(self._fit_text(f"{self.name(opp, True)} " + ("(N)" if pm["neutral"] else
                                             "(H)" if pm["home"] == mc else "(A)"), "small", cell.w - 10), "small",
                              TEXT, (cell.x + 6, cell.y + 42))
                    if pm.get("result"):
                        rr = pm["result"]
                        gf, ga = (rr["hg"], rr["ag"]) if pm["home"] == mc else (rr["ag"], rr["hg"])
                        self.text(f"{gf}-{ga}", "small", MUTED, (cell.x + 6, cell.y + 60))
                    self.buttons.append(_Invisible(cell, lambda: self.go("playoff")))
                elif inside and fr_on.get(iso):
                    f = fr_on[iso]
                    self.text("Friendly", "small", ACCENT_HI, (cell.x + 6, cell.y + 24))
                    self.text(self._fit_text(f"{f['name']} ({'H' if f['home'] else 'A'})", "small", cell.w - 10), "small",
                              TEXT, (cell.x + 6, cell.y + 42))
                    if f.get("result"):
                        rr = f["result"]
                        out = "W" if rr["gf"] > rr["ga"] else "D" if rr["gf"] == rr["ga"] else "L"
                        self.text(f"{out} {rr['gf']}-{rr['ga']}", "small", {"W": WIN, "D": DRAW, "L": LOSS}[out],
                                  (cell.x + 6, cell.y + 60))
                    self.buttons.append(_Invisible(cell, lambda iso=iso: self.open_arrange(iso)))
                else:
                    if iso in breaks and inside:
                        self.text("International", "small", MUTED, (cell.x + 6, cell.y + 30))
                        self.text("break", "small", MUTED, (cell.x + 6, cell.y + 48))
                    if inside and iso > (today or ""):
                        self.buttons.append(_Invisible(cell, lambda iso=iso: self.open_arrange(iso)))

    # -- friendlies (career/friendlies.py) ------------------------------------------
    def open_arrange(self, iso):
        self.arr = {"date": iso, "kind": "local", "home": True, "pick": None, "msg": None}
        self.go("arrange")

    def draw_arrange(self):
        W, H = self.size
        self.sidebar("calendar")
        c = self.career
        a = self.arr
        x0 = 250
        self.text("Arrange a friendly", "h1", TEXT, (x0, 18))
        self.text(cal.fmt(a["date"]), "h2", ACCENT_HI, (x0, 74))
        self.buttons.append(Button((W - 230, 24, 200, 40), "Back to calendar", lambda: self.go("calendar"), font="btn_s"))
        existing = next((f for f in friendlies.all_(c) if f["date"] == a["date"]), None)
        r = pygame.Rect(x0, 120, W - x0 - 30, H - 150)
        self.panel(r)
        if existing:
            where = "at home" if existing["home"] else "away"
            self.text(f"Friendly v {existing['name']} ({where})", "h2", TEXT, (r.x + 20, r.y + 20))
            if existing.get("result"):
                rr = existing["result"]
                self.text(f"Played: {rr['gf']}-{rr['ga']}", "body", MUTED, (r.x + 20, r.y + 64))
            else:
                self.text("Arranged. On the day, Continue stops there.", "body", MUTED, (r.x + 20, r.y + 64))
                self.buttons.append(Button((r.x + 20, r.y + 110, 220, 46), "Cancel the friendly",
                                           lambda: (friendlies.cancel(c, existing["id"]), league.save(c),
                                                    self.go("calendar"))))
            return
        ok, why = friendlies.date_ok(c, a["date"])
        if not ok:
            self.text(why, "body", LOSS, (r.x + 20, r.y + 20))
            self.text("Friendlies need two clear days either side of a league match or another friendly.", "small",
                      MUTED, (r.x + 20, r.y + 52))
            return
        y = r.y + 18
        self.text("Who against?", "small", MUTED, (r.x + 20, y + 8))
        kinds = [("local", "Local non-league side"), ("league", "Club from our league")]
        if "spain" in c:
            kinds.append(("spain", "Spanish club"))
        for i, (k, label) in enumerate(kinds):
            self.buttons.append(Button((r.x + 140 + i * 216, y, 208, 34), label,
                                       lambda k=k: a.update(kind=k, pick=None), primary=a["kind"] == k, font="btn_s"))
        y += 48
        self.text("Where?", "small", MUTED, (r.x + 20, y + 8))
        for i, (v, label) in enumerate(((True, "Home"), (False, "Away"))):
            self.buttons.append(Button((r.x + 140 + i * 128, y, 120, 34), label, lambda v=v: a.update(home=v),
                                       primary=a["home"] == v, font="btn_s"))
        hint = {"local": "Part-timers: an easy run-out, minutes for everyone. Small gate.",
                "league": "A proper test against a side from our league.",
                "spain": "A pre-season tour game against Spanish opposition. Good gate at home."}[a["kind"]]
        self.text(hint, "small", MUTED, (r.x + 420, y + 9))
        y += 56
        opts = friendlies.options(c, a["kind"], a["date"])
        cols = 3
        bw = (r.w - 40 - (cols - 1) * 8) // cols
        for i, (oid, name) in enumerate(opts):
            bx = r.x + 20 + (i % cols) * (bw + 8)
            by = y + (i // cols) * 40
            if by > r.bottom - 120:
                break
            key = (oid, name)
            self.buttons.append(Button((bx, by, bw, 34), name, lambda key=key: a.update(pick=key),
                                       primary=a["pick"] == key, font="btn_s"))
        if a.get("msg"):
            self.text(a["msg"], "small", LOSS, (r.x + 20, r.bottom - 92))
        def go_arrange():
            if not a["pick"]:
                a["msg"] = "Pick an opponent first."
                return
            err = friendlies.arrange(c, a["date"], a["kind"], a["pick"][0], a["pick"][1], a["home"])
            if err:
                a["msg"] = err
                return
            league.save(c)
            self.go("calendar")
        label = f"Arrange: v {a['pick'][1]}" if a["pick"] else "Arrange"
        self.buttons.append(Button((r.right - 300, r.bottom - 66, 280, 48), self._fit_text(label, "btn", 260),
                                   go_arrange, primary=True))

    def draw_friendly(self):
        W, H = self.size
        self.sidebar("home")
        c = self.career
        f = next((x for x in friendlies.all_(c) if x["id"] == getattr(self, "friendly_id", None)), None)
        if f is None:
            return self.go("home")
        me = self._my_club()
        home, away = friendlies.sides(c, f)
        x0 = 250
        pre = f["date"] < (c.get("calendar") or ["9999"])[0]
        self.text("Pre-season friendly" if pre else "Friendly", "h1", TEXT, (x0, 24))
        self.text(cal.fmt(f["date"]), "body", MUTED, (x0, 72))
        r = pygame.Rect(x0, 100, W - x0 - 30, 220)
        self.panel(r)
        cx = r.centerx
        _badge(self.win, tuple(home["colour"]), (cx - 60, r.y + 62), 18, home)
        _badge(self.win, tuple(away["colour"]), (cx + 60, r.y + 62), 18, away)
        self.text(home["name"], "h2", TEXT, (cx - 90, r.y + 48), "topright")
        self.text(away["name"], "h2", TEXT, (cx + 90, r.y + 48))
        res = f.get("result")
        if res:
            self.text(f"{res['hg']} - {res['ag']}", "big", ACCENT, (cx, r.y + 96), "midtop")
            gy = r.y + 166
            for side, club in ((0, home), (1, away)):
                gl = [f"{g['name'].split(' ')[-1]} {g['minute']}'" for g in res.get("goals", []) if g["team"] == side]
                if gl:
                    self.text(self._fit_text(f"{club['name']}: " + ", ".join(gl), "small", r.w - 40), "small", MUTED,
                              (cx, gy), "midtop")
                    gy += 22
        else:
            self.text("v", "h2", MUTED, (cx, r.y + 48), "midtop")
            self.text({"local": "Non-league opposition", "league": "League opposition",
                       "spain": "Spanish opposition"}[f["kind"]] + "  ·  doesn't count in the table  ·  up to 11 substitutes",
                      "small", MUTED, (cx, r.y + 110), "midtop")
        r2 = pygame.Rect(x0, r.bottom + 16, W - x0 - 30, 150)
        self.panel(r2, "Your assistant")
        xi = list((me.get("lineup") or {}).values())
        note = fitness.squad_note(me, xi)
        if res:
            line = ("Good work-out. " if res["gf"] >= res["ga"] else "Result doesn't matter - the minutes do. ") + \
                   (f"Still some way to go: {note}" if note else "The lads are getting there.")
            hurt = [p for p in me["players"] if (p.get("injury") or {}).get("since") == f["date"]]
            if hurt:
                line += "  Picked up: " + ", ".join(
                    f"{p['Name'].split(' ')[-1]} ({p['injury']['name'].lower()}, back {cal.fmt(p['injury']['until'], False)[4:]})"
                    for p in hurt[:4]) + "."
        else:
            line = (note + " Give them the minutes.") if note else "Everyone's in decent shape."
            if pre:
                line += "  I'll give the bench a run-out at half-time unless you'd rather do it yourself."
        self._wrap(line, "body", TEXT, r2.x + 16, r2.y + 48, r2.w - 32)
        y = r2.bottom + 20
        if res:
            self.buttons.append(Button((W - 260, H - 76, 220, 50), "Continue", self.continue_to_match, primary=True))
            self.buttons.append(Button((x0, H - 76, 200, 50), "Office", lambda: self.go("home")))
        else:
            self.buttons.append(Button((x0, y, 200, 50), "Pick the team", lambda: self.go("tactics")))
            self.buttons.append(Button((W - 500, y, 220, 50), "Quick result", self._friendly_quick))
            self.buttons.append(Button((W - 260, y, 220, 50), "Watch", self._friendly_watch, primary=True))

    def _friendly_quick(self):
        f = next(x for x in friendlies.all_(self.career) if x["id"] == self.friendly_id)
        friendlies.finish(self.career, f, friendlies.quick(self.career, f))
        league.save(self.career)

    def _friendly_watch(self):
        f = next(x for x in friendlies.all_(self.career) if x["id"] == self.friendly_id)
        result, quit_ = matches.watch_friendly(self.career, f)
        if quit_:
            self.quit()
            return
        self._window()
        if result is None:
            self.go("friendly")
            return
        friendlies.finish(self.career, f, result)
        league.save(self.career)
        self.go("friendly")

    def _cal_open(self, md):
        self.fixtures_md = md
        self.screen = "fixtures"

    # -- fixtures -----------------------------------------------------------
    def draw_fixtures(self):
        W, H = self.size
        self.sidebar("fixtures")
        self._paper_tabs("fixtures")
        c = self.career
        from career import divisions
        mine = divisions.my_div(c)
        div = getattr(self, "fixtures_div", None) or mine
        if not divisions.exists(c):
            div = mine
        fixtures, res_all = (c["fixtures"], c["results"]) if div == mine else (c["other"]["fixtures"],
                                                                                c["other"]["results"])
        po = div == playoffs.DIV and playoffs.state(c) is not None        # (a page for the play-offs)
        last = len(fixtures) + (1 if po else 0)
        md = min(self.fixtures_md, last)
        self.text("Fixtures & results", "h1", TEXT, (250, 24))
        if divisions.exists(c):
            for i, d_ in enumerate(divisions.ORDER):
                self.buttons.append(Button((W - 330 + i * 150, 82, 142, 34), divisions.name(d_),
                                           lambda d_=d_: setattr(self, "fixtures_div", d_),
                                           primary=d_ == div, font="btn_s"))
        self.buttons.append(Button((250, 80, 46, 40), "<", lambda: setattr(self, "fixtures_md", max(1, md - 1))))
        self.buttons.append(Button((250 + 414, 80, 46, 40), ">",
                                   lambda: setattr(self, "fixtures_md", min(last, md + 1))))
        r = pygame.Rect(250, 140, W - 280, H - 170)
        self.panel(r)
        if md > len(fixtures):
            self.text("Play-offs", "h2", TEXT, (250 + 230, 84), "midtop")
            y = r.y + 24
            for label, txt in playoffs.lines(c):
                self.text(label, "small", MUTED, (r.x + 20, y + 2))
                self.text(self._fit_text(txt, "body", r.w - 250), "body", TEXT, (r.x + 220, y))
                y += 40
            return
        self.text(f"Matchday {md} of {len(fixtures)}", "h2", TEXT, (250 + 230, 84), "midtop")
        d = league.match_date(c, md)
        if d:
            self.text(f"{cal.fmt(d)}, {cal.kick_off(d)}" + ("" if div == mine else "  ·  quick results"),
                      "small", MUTED, (250 + 230, 118), "midtop")
        results = {(x["home"], x["away"]): x for x in res_all.get(str(md), [])}
        day = fixtures[md - 1]
        step = min(98, (r.h - 20) // max(1, len(day)))
        y = r.y + 16
        for home, away in day:
            self._match_row(r, y, step, home, away, results.get((home, away)))
            y += step

    def _match_row(self, r, y, step, home, away, res, minute=None):
        """One match on the fixtures / results screens: names, score (or a progress
        bar while it's being played) and scorers.  Smaller when there are lots."""
        c = self.career
        cx = r.x + r.w // 2
        big = step >= 90
        name_font = "h3" if big else "body"
        if c["my_club"] in (home, away):
            pygame.draw.rect(self.win, HIGHLIGHT, (r.x + 12, y - 6, r.w - 24, step - 6), border_radius=8)
        self.text(self.name(home), name_font, TEXT, (cx - 70, y), "topright")
        _badge(self.win, self.colour(home), (cx - 50, y + 11), 8, self._club_of(home))
        _badge(self.win, self.colour(away), (cx + 50, y + 11), 8, self._club_of(away))
        self.text(self.name(away), name_font, TEXT, (cx + 70, y))
        sub_y = y + (32 if big else 24)
        if res:
            self.text(f"{res['hg']} - {res['ag']}", "h3", ACCENT, (cx, y - (0 if big else 2)), "midtop")
            if res.get("goals"):
                self._scorers(res, cx, sub_y)
        elif minute is not None:
            self.text("playing", "small", MUTED, (cx, y + 2), "midtop")
            bar = pygame.Rect(cx - 60, sub_y + 4, 120, 8)
            pygame.draw.rect(self.win, PANEL_2, bar, border_radius=4)
            pygame.draw.rect(self.win, ACCENT, (bar.x, bar.y, int(bar.w * minute / 90), bar.h), border_radius=4)
            self.text(f"{minute}'", "small", MUTED, (bar.right + 10, sub_y), "topleft")
        else:
            self.text("v", "h3", MUTED, (cx, y - (0 if big else 2)), "midtop")

    def _scorers(self, res, cx, y):
        hs = [g for g in res["goals"] if g["team"] == 0]
        aw = [g for g in res["goals"] if g["team"] == 1]

        def fmt(g):
            return f"{g['name'].split(' ')[-1]}{' (og)' if g.get('own_goal') else ''} {g['minute']}'"
        self.text(", ".join(fmt(g) for g in hs), "small", MUTED, (cx - 70, y), "topright")
        self.text(", ".join(fmt(g) for g in aw), "small", MUTED, (cx + 70, y))

    # -- match day ----------------------------------------------------------
    def draw_prematch(self):
        W, H = self.size
        self.sidebar("home")
        c = self.career
        md, home, away = league.next_fixture(c)
        x0 = 250
        self.text(f"Matchday {md}", "h1", TEXT, (x0, 24))
        d = league.match_date(c)
        if d:
            self.text(f"{cal.fmt(d)}, kick-off {cal.kick_off(d)}", "body", MUTED, (x0, 72))
        r = pygame.Rect(x0, 100, W - x0 - 30, 300)
        self.panel(r)
        cx = r.x + r.w // 2
        for cid, side in ((home, -1), (away, 1)):
            x = cx + side * 220
            _badge(self.win, self.colour(cid), (x, r.y + 90), 36, self._club_of(cid))
            self.text(self.name(cid), "h2", TEXT, (x, r.y + 140), "midtop")
            pos = league.position_of(c, cid)
            cl = c["clubs"][cid]
            played = any(cid in (m["home"], m["away"]) for day in c["results"].values() for m in day)
            self.text(f"{_ordinal(pos)} in the league" if played else f"{_stars(cl['strength'])}-star squad",
                      "body", MUTED, (x, r.y + 178), "midtop")
            self.text(f"{STYLE_TEXT[cl['tactics']['defence']]}, {BUILD_TEXT[cl['tactics']['build_up']]}", "small",
                      MUTED, (x, r.y + 206), "midtop")
            if c.get("date"):
                d_ = league.match_date(c) or c["date"]
                out = [p for p in cl["players"] if not avail.available(p, d_)]
                if out:
                    names = ", ".join(p["Name"].split(" ")[-1] for p in out[:4]) + ("..." if len(out) > 4 else "")
                    self.text(f"Missing: {names}", "small", LOSS, (x, r.y + 230), "midtop")
        self.text("v", "big", MUTED, (cx, r.y + 70), "midtop")
        self.text("Home team in blue, away team in red", "small", MUTED, (cx, r.bottom - 34), "midtop")
        self.buttons.append(Button((x0, 430, 320, 56), "Watch the match", self.watch_match, primary=True))
        self.buttons.append(Button((x0 + 340, 430, 320, 56), "Simulate it (results only)", self.simulate_match))
        have = {(x["home"], x["away"]) for x in c.get("pending_results", {}).get(str(md), [])}
        n_other = len(self._others(md))
        n_done = sum(1 for f in self._others(md) if f in have)
        msg = (f"The other {n_other} matches have all been played (full match engine, in the background)."
               if n_done == n_other else
               f"The other {n_other} matches are being played by the full match engine in the background "
               f"({n_done} finished so far).")
        self.text(msg, "small", MUTED, (x0, 506))
        me = self._my_club()                                # the team talk (career/teamtalk.py)
        r3 = pygame.Rect(x0, 540, W - x0 - 30, 86)
        self.panel(r3, "Team talk")
        last = (me.get("talks") or {}).get("last") or {}
        if teamtalk.done(c, me, "pre") and last.get("phase") == "pre":
            words = dict((k, w) for k, w in teamtalk.PRE)[last["key"]]
            self.text(f"You told them: \u201c{words}\u201d", "small", TEXT, (r3.x + 150, r3.y + 16))
            self.text(self._fit_text(self._talk_summary(me, last), "small", r3.w - 166), "small", MUTED,
                      (r3.x + 150, r3.y + 42))
        else:
            self.text(teamtalk.situation(teamtalk.context(c, me, "pre")), "small", MUTED, (r3.x + 16, r3.y + 48))
            self.buttons.append(Button((r3.right - 236, r3.y + 20, 220, 46), "Give a team talk",
                                       lambda: self.open_talk("pre"), primary=True))
        self.buttons.append(Button((x0, H - 70, 160, 46), "Back", lambda: self.go("home")))

    def _others(self, md):
        mc = self.career["my_club"]
        return [tuple(f) for f in self.career["fixtures"][md - 1] if mc not in f]

    # The other matches of a matchday start in the background as soon as the
    # previous matchday is over - while you look at the table, pick your team
    # and so on - so they're usually finished by the time you've played yours.
    # Each one's result is kept in the save the moment it's in, so quitting
    # only loses the matches still being played (they're replayed next time).
    def _pending(self):
        return self.career.setdefault("pending_results", {}).setdefault(str(self.career["matchday"]), [])

    def _keep_running(self):
        """Called every frame: start / poll / collect the background matches."""
        c = self.career
        if not c or self.screen in ("title", "choose", "season_end", "sacked") or league.season_over(c):
            return
        md = c["matchday"]
        if self.bg is not None and self.bg.matchday != md:
            self.bg.stop()
            self.bg = None
        if self.bg is None:
            have = {(r["home"], r["away"]) for r in self._pending()}
            todo = [f for f in self._others(md) if f not in have]
            d = league.match_date(c)
            if d and not training.trained_up_to(c, d, exclude=c["my_club"]):
                todo = []           # (in a transfer window the other clubs' days aren't done until Continue)
            if todo:
                self.bg = matches.BackgroundMatches(c, todo, md)
        changed = False
        for bg in (self.bg, self.my_bg):
            if bg is None:
                continue
            bg.poll()
            if bg is self.bg:
                have = {(r["home"], r["away"]) for r in self._pending()}
                for r in bg.result_list():
                    if (r["home"], r["away"]) not in have:
                        self._pending().append(r)
                        changed = True
        if changed:
            league.save(c)

    def _others_done(self):
        have = {(r["home"], r["away"]) for r in self._pending()}
        return all(f in have for f in self._others(self.career["matchday"]))

    def watch_match(self):
        md, home, away = league.next_fixture(self.career)
        league.advance_to_match(self.career)
        result, quit_ = matches.watch(self.career, home, away, md)
        if quit_:
            self.quit()
            return
        self._window()
        if result is None:                           # left early: your match doesn't count yet
            self.go("home")
            return
        self.my_result = result
        self.go("results")

    def simulate_match(self):
        md, home, away = league.next_fixture(self.career)
        league.advance_to_match(self.career)
        self.my_bg = matches.BackgroundMatches(self.career, [(home, away)], md)
        self.my_result = None
        self.go("results")

    def draw_results(self):
        W, H = self.size
        c = self.career
        md = c["matchday"]
        date = league.match_date(c)
        self.text(f"Matchday {md} results", "h1", TEXT, (40, 24))
        if date:
            self.text(cal.fmt(date), "body", MUTED, (W - 40, 40), "topright")
        if self.my_bg is not None and self.my_bg.done() and self.my_result is None:
            got = self.my_bg.result_list()
            if got:
                self.my_result = got[0]
        res = {(r["home"], r["away"]): r for r in self._pending()}
        if self.my_result:
            res[(self.my_result["home"], self.my_result["away"])] = self.my_result
        live = {}
        for bg in (self.bg, self.my_bg):
            if bg is not None:
                live.update({(h, a): m for h, a, m in bg.progress()[2]})
        r = pygame.Rect(40, 90, W - 80, H - 190)
        self.panel(r)
        day = [tuple(f) for f in c["fixtures"][md - 1]]
        step = min(100, (r.h - 20) // max(1, len(day)))
        y = r.y + 16
        for home, away in day:
            got = res.get((home, away))
            self._match_row(r, y, step, home, away, got, None if got else live.get((home, away), 0))
            y += step
        errors = {}
        for bg in (self.bg, self.my_bg):
            if bg is not None:
                errors.update(bg.errors)
        all_in = len(res) == len(day)
        if errors and not any(bg is not None and not bg.done() for bg in (self.bg, self.my_bg)):
            self.text("A match failed to finish - see the console. It will be replayed.", "small", LOSS,
                      (40, H - 92))
            self.buttons.append(Button((W - 260, H - 76, 220, 50), "Replay failed matches", self.retry_failed,
                                       primary=True))
        elif all_in:
            self.buttons.append(Button((W - 260, H - 76, 220, 50), "Continue", self.finish_matchday, primary=True))
        if self.my_result and self.my_result.get("ht_talk"):      # what was said at half-time
            ht = self.my_result["ht_talk"]
            who = "You" if ht.get("by") == "you" else "Your assistant"
            self.text(self._fit_text(f"Half-time: {who} told them \u201c{ht.get('words_said', '')}\u201d", "small",
                                     W - 580), "small", MUTED, (40, H - 66))
        if self.my_result:                                # the full-time team talk (career/teamtalk.py)
            me = self._my_club()
            last = (me.get("talks") or {}).get("last") or {}
            if teamtalk.done(c, me, "post") and last.get("phase") == "post":
                self.text(self._fit_text("After the game: " + self._talk_summary(me, last), "small", W - 360),
                          "small", MUTED, (40, H - 94))
            else:
                self.buttons.append(Button((W - 520, H - 76, 240, 50), "Full-time team talk",
                                           lambda: self.open_talk("post")))
        else:
            self.text(f"{len(res)} of {len(day)} matches finished", "body", MUTED, (40, H - 70))

    def retry_failed(self):
        for bg in (self.bg, self.my_bg):
            if bg is not None:
                for t, msg in bg.errors.items():
                    print(f"[Career] {t} failed:\n{msg}")
        if self.my_bg is not None and self.my_bg.errors:
            md, home, away = league.next_fixture(self.career)
            self.my_bg = matches.BackgroundMatches(self.career, [(home, away)], md)
        if self.bg is not None and self.bg.errors:
            self.bg = None                               # _keep_running starts the missing ones again

    def finish_matchday(self):
        results = list(self._pending())
        if self.my_result:
            results.append(self.my_result)
        md = self.career["matchday"]
        teamtalk.after_match(self.career, results)           # the half-time talk: morale (career/teamtalk.py)
        league.record_matchday(self.career, results)
        avail.after_matchday(self.career, md, results)    # bans, injuries, training, teams for next time
        media.after_matchday(self.career, md, results)    # the papers, social media, the fans (career/media.py)
        league.save(self.career)
        self.bg = None
        self.my_bg = None
        self.my_result = None
        self.go("sacked" if brd.state(self.career).get("sacked") else "home")

    # -- the board ------------------------------------------------------------
    # -- the club: history, honours, the ground (career/clubinfo.py) ----------
    def _club_tabs(self, active, y=24, board=True):
        W, H = self.size
        tabs = (("history", "History"), ("honours", "Honours"), ("ground", "The ground"))
        if board:
            tabs += (("board", "The board"),)
        for i, (key, label) in enumerate(tabs):
            def go(k=key):
                if k == "board":
                    self.go("board")
                else:
                    self.club_tab = k
                    self.go("club")
            self.buttons.append(Button((W - 30 - len(tabs) * 128 + i * 128, y, 122, 36), label, go,
                                       primary=key == active, font="btn_s"))

    def open_club_page(self, cid):
        """Another club's page (history, honours, ground) - from their squad screen."""
        self.club_view = cid
        self.club_tab = "history"
        self.club_era = 0
        self.go("club")

    def draw_club(self):
        W, H = self.size
        self.sidebar("club")
        cid = getattr(self, "club_view", None)
        mine = cid is None or cid == self.career["my_club"]
        me = self._my_club() if mine else self.club(cid)
        pr = clubinfo.profile(me)
        x0 = 250
        tab = getattr(self, "club_tab", "history")
        if pr:
            self._club_tabs(tab, 104, board=mine)
        else:
            tab = "honours"                             # (no profile yet: just the roll of honour)
        if not mine:
            self.buttons.append(Button((x0, 104, 140, 36), "Back", lambda: self.view_squad(cid), font="btn_s"))
        crest = clubinfo.image(me, "crest", (92, 92))
        tx = x0
        if crest is not None:
            self.win.blit(crest, (x0, 14))
            tx = x0 + crest.get_width() + 16
        self.text(me["name"], "h1", TEXT, (tx, 14))
        if not pr:
            from career import divisions, stadium
            cap = stadium.full_capacity(self.career, me) or me.get("finance", {}).get("capacity", 0)
            self.text(f"{divisions.name(divisions.div_of(me))}  ·  ground holds {cap:,}  ·  "
                      f"their full story hasn't been written yet", "body", MUTED, (tx, 66))
            return self._club_honours(me, {}, x0, 152)
        loc = pr["location"]
        g = pr["ground"]
        nick = ", ".join('"' + n + '"' for n in pr["nicknames"])
        from career import stadium
        cap = stadium.full_capacity(self.career, me) or g["capacity"]
        line = f"Founded {pr['founded']}  ·  {loc['town']}, {loc['county']}  ·  {g['name']} ({cap:,})  ·  {nick}"
        self.text(self._fit_text(line, "body", W - tx - 30), "body", MUTED, (tx, 66))
        top = 152
        if tab == "history":
            self._club_history(pr, x0, top)
        elif tab == "honours":
            self._club_honours(me, pr, x0, top)
        else:
            self._club_ground(me, pr, x0, top)

    def _club_history(self, pr, x0, top):
        W, H = self.size
        eras = pr["history"]
        sel = getattr(self, "club_era", 0)
        sel = min(sel, len(eras) - 1)
        left = pygame.Rect(x0, top, 300, H - top - 20)
        self.panel(left)
        y = left.y + 12
        mouse = pygame.mouse.get_pos()
        for i, e in enumerate(eras):
            row = pygame.Rect(left.x + 8, y, left.w - 16, 52)
            if i == sel:
                pygame.draw.rect(self.win, HIGHLIGHT, row, border_radius=6)
            elif row.collidepoint(mouse):
                pygame.draw.rect(self.win, PANEL_2, row, border_radius=6)
            self.text(e["title"], "h3", TEXT, (row.x + 10, row.y + 5))
            self.text(e["years"], "small", MUTED, (row.x + 10, row.y + 30))
            self.buttons.append(_Invisible(row, lambda i=i: setattr(self, "club_era", i)))
            y += 58
        y += 6
        self.text("Colours", "small", ACCENT_HI, (left.x + 16, y)); y += 22
        y = self._wrap(pr["colours"]["story"], "small", MUTED, left.x + 16, y, left.w - 32) + 8
        r = pygame.Rect(left.right + 16, top, W - left.right - 46, H - top - 20)
        self.panel(r)
        e = eras[sel]
        self.text(e["title"], "h2", TEXT, (r.x + 20, r.y + 16))
        self.text(e["years"], "body", MUTED, (r.x + 20, r.y + 52))
        y = self._wrap(e["text"], "body", TEXT, r.x + 20, r.y + 90, r.w - 40) + 24
        self.text("Rivals", "h3", ACCENT_HI, (r.x + 20, y)); y += 32
        for rv in pr.get("rivals", []):
            name = f"{rv['club']} - {rv['derby']}" if rv.get("derby") else rv["club"]
            y = self._wrap(f"{name}: {rv['why']}.", "body", MUTED, r.x + 20, y, r.w - 40) + 8
        y += 12
        self.text("Where", "h3", ACCENT_HI, (r.x + 20, y)); y += 32
        self._wrap(pr["location"]["about"], "body", MUTED, r.x + 20, y, r.w - 40)

    def _club_honours(self, club, pr, x0, top):
        W, H = self.size
        r = pygame.Rect(x0, top, 520, H - top - 20)
        self.panel(r, "Honours")
        y = r.y + 52
        hon = clubinfo.honours(club["name"], self.career)
        ru = clubinfo.runners_up(club["name"], "league", self.career)
        rows = hon[:1] if hon and hon[0][0] == "The League" else []
        rows += [("League runners-up", ru)] if ru else []
        rows += [h for h in hon if h[0] != "The League"]
        seasons = ("The League", "League runners-up", "Second Division / Division 1", "Division 1 play-offs")
        if not rows:
            self.text("Nothing in the trophy cabinet yet.", "body", MUTED, (r.x + 16, y))
        for comp, years in rows:
            label = "Second Division / Division 1 champions" if comp == "Second Division / Division 1" else \
                "Division 1 play-off winners" if comp == "Division 1 play-offs" else comp
            self.text(f"{label}  ({len(years)})", "h3", TEXT, (r.x + 16, y)); y += 28
            y = self._wrap(", ".join(clubinfo.season(yy) if comp in seasons else str(yy) for yy in years),
                           "small", MUTED, r.x + 16, y, r.w - 32) + 12
            if y > r.bottom - 40:
                break
        r2 = pygame.Rect(r.right + 16, top, W - r.right - 46, H - top - 20)
        self.panel(r2, "Records and legends")
        y = r2.y + 52
        if not pr:
            self._wrap("Their records and legends haven't been written yet. The roll of honour on the left "
                       "goes back to the 1870s - and every season you play adds to it.", "body", MUTED,
                       r2.x + 16, y, r2.w - 32)
            return
        labels = {"attendance": "Record crowd", "win": "Record win", "defeat": "Record defeat",
                  "top_scorer": "Top scorer", "appearances": "Most games", "season_goals": "Most in a season"}
        for k, v in pr.get("records", {}).items():
            self.text(labels.get(k, k), "small", ACCENT_HI, (r2.x + 16, y)); y += 20
            y = self._wrap(v, "small", TEXT, r2.x + 16, y, r2.w - 32) + 8
        y += 6
        for lg in pr.get("legends", []):
            self.text(lg["name"], "small", ACCENT_HI, (r2.x + 16, y)); y += 20
            y = self._wrap(f"{lg['role']}. {lg['note']}", "small", MUTED, r2.x + 16, y, r2.w - 32) + 8
            if y > r2.bottom - 40:
                break

    def _club_ground(self, club, pr, x0, top):
        W, H = self.size
        g = pr["ground"]
        from career import stadium
        which = getattr(self, "ground_pic", "inside")
        pic = clubinfo.image(club, which, (560, 316), self.career)
        if pic is not None:
            self.win.blit(pic, (x0, top))
            pygame.draw.rect(self.win, LINE, (x0, top, pic.get_width(), pic.get_height()), 1, border_radius=4)
            for i, (k, label) in enumerate((("inside", "Inside"), ("aerial", "From above"))):
                self.buttons.append(Button((x0 + i * 128, top + pic.get_height() + 10, 122, 34), label,
                                           lambda k=k: setattr(self, "ground_pic", k), primary=which == k,
                                           font="btn_s"))
        y = top + 316 + 56
        self.text(f"{g['name']}  ·  opened {g['opened']}  ·  {stadium.full_capacity(self.career, club):,}", "h3",
                  TEXT, (x0, y)); y += 32
        ph, b = stadium.building(self.career, club)
        if ph:
            self.text(f"Being rebuilt: the {ph['stand']} - opens {stadium.when(b['end'])}", "small", DRAW, (x0, y))
            y += 22
        from career import crowds                     # who's been coming (career/crowds.py)
        s = crowds.this_season(self.career, club)
        lab = "This season"
        if not s:
            s, lab = crowds.last_season(self.career, club), "Last season"
        if s:
            line = (f"{lab}: average {s['avg']:,} ({round(100 * s['pct'])}% full)  ·  {s['sellouts']} of "
                    f"{s['games']} sold out  ·  about {crowds.support(self.career, club):,} fans would come")
        else:
            line = f"About {crowds.support(self.career, club):,} fans would come every week if they could"
        self.text(self._fit_text(line, "small", 560), "small", ACCENT_HI, (x0, y)); y += 24
        nxt = stadium.next_phase(self.career, club) if club["id"] == self.career["my_club"] else None
        if nxt:                                         # (developing the ground: ask the board)
            box = pygame.Rect(x0, y, 560, H - y - 20)
            self.panel(box)
            self.text(nxt["name"], "h3", ACCENT_HI, (box.x + 14, box.y + 10))
            yy = self._wrap(nxt["about"], "small", TEXT, box.x + 14, box.y + 40, box.w - 28) + 6
            self.text(f"{fin.money(nxt['cost'])}  ·  +{nxt['adds']:,} seats  ·  about {nxt['months']} months  ·  "
                      f"{nxt['closed_during']:,} seats shut while it's built", "small", MUTED, (box.x + 14, yy))
            yy += 26
            said = getattr(self, "stadium_reply", None)
            if said:
                self._wrap(said, "small", DRAW, box.x + 240, yy, box.w - 254)
            def ask():
                ok, self.stadium_reply = stadium.ask(self.career, club)
                league.save(self.career)
            self.buttons.append(Button((box.x + 14, yy, 210, 40), "Ask the board", ask, primary=True))
        else:
            y = self._wrap(g["surroundings"][0].upper() + g["surroundings"][1:] + ".", "small", MUTED, x0, y, 560) + 8
            self._wrap(g["atmosphere"][0].upper() + g["atmosphere"][1:] + ".", "small", MUTED, x0, y, 560)
        r = pygame.Rect(x0 + 576, top, W - x0 - 606, H - top - 20)
        self.panel(r, "The stands")
        y = r.y + 50
        for s in stadium.stands(self.career, club):
            self.text(f"{s['name']}  ·  {s['capacity']:,}", "h3", TEXT, (r.x + 16, y)); y += 26
            if s.get("building"):
                self.text(f"Being rebuilt - {s['open_now']:,} open meanwhile", "small", DRAW, (r.x + 16, y)); y += 20
            meta = f"{s['side'].title()} side  ·  built {s['built']}  ·  {s['tiers']} tier{'s' if s['tiers'] > 1 else ''}"
            self.text(self._fit_text(meta, "small", r.w - 32), "small", ACCENT_HI, (r.x + 16, y)); y += 20
            lines = self._lines(s["features"][0].upper() + s["features"][1:] + ".", "small", r.w - 32)
            if len(lines) > 4:                          # (four lines a stand: they all fit)
                lines = lines[:4]
                lines[-1] = self._fit_text(lines[-1] + " ...", "small", r.w - 32)
            lh = self.fonts["small"].get_linesize()
            for ln in lines:
                self.text(ln, "small", MUTED, (r.x + 16, y)); y += lh
            y += 12

    def draw_board(self):
        W, H = self.size
        self.sidebar("board")
        c = self.career
        b = brd.state(c)
        x0 = 250
        self._club_tabs("board")
        self.text("The board", "h1", TEXT, (x0, 18))
        r = pygame.Rect(x0, 80, W - x0 - 30, 170)
        self.panel(r, "This season")
        self.text(f"Objective: {b.get('objective', '-')}", "h3", TEXT, (r.x + 16, r.y + 50))
        self.text("...and keep the club out of debt and within the wage budget.", "body", MUTED, (r.x + 16, r.y + 82))
        conf = b["confidence"]
        col = ACCENT if conf >= 60 else DRAW if conf >= brd.WARN_AT else LOSS
        bar = pygame.Rect(r.x + 16, r.y + 122, r.w - 32, 18)
        pygame.draw.rect(self.win, PANEL_2, bar, border_radius=8)
        pygame.draw.rect(self.win, col, (bar.x, bar.y, int(bar.w * conf / 100), bar.h), border_radius=8)
        mood = ("delighted" if conf >= 80 else "pleased" if conf >= 60 else "satisfied" if conf >= 45 else
                "concerned" if conf >= brd.ULTIMATUM_AT else "losing patience")
        self.text(f"Confidence {round(conf)}/100 - {mood}", "body", col, (r.right - 16, r.y + 52), "topright")
        # Recent views and past seasons
        r2 = pygame.Rect(x0, 266, (W - x0 - 44) // 2, H - 286)
        self.panel(r2, "What they've said")
        y = r2.y + 50
        msgs = [m for m in reversed(trf.inbox(c)) if m["kind"] == "board"][:8]
        for m in msgs:
            y = self._wrap(f"{cal.fmt(m['date'], False)}: {m['text']}", "small", TEXT, r2.x + 16, y, r2.w - 32) + 8
            if y > r2.bottom - 30:
                break
        if not msgs:
            self.text("Nothing yet.", "body", MUTED, (r2.x + 16, y))
        r3 = pygame.Rect(r2.right + 14, 266, W - r2.right - 44, H - 286)
        self.panel(r3, "Past seasons")
        y = r3.y + 50
        for h in reversed(b.get("history", [])[-8:]):
            self.text(f"{cal.season_label(h['year']) if h.get('year') else ''}: {h['position']}{brd._suffix(h['position'])}"
                      f" - {h['objective']} ({h['verdict']})", "small", TEXT, (r3.x + 16, y))
            y += 26
        for j in reversed(b.get("career_log", [])[-4:]):
            self.text(f"Sacked by {j['club']} ({cal.fmt(j['until'], False)})", "small", LOSS, (r3.x + 16, y))
            y += 26
        if not b.get("history") and not b.get("career_log"):
            self.text("Your first season.", "body", MUTED, (r3.x + 16, y))

    def draw_sacked(self):
        W, H = self.size
        c = self.career
        b = brd.state(c)
        self.text("You've been sacked", "h1", LOSS, (40, 30))
        self.text(f"The board of {self.name(c['my_club'])} have dismissed you: {b.get('sacked_reason', '')}.",
                  "body", TEXT, (40, 90))
        self.text("Some clubs would like to talk to you:", "h3", TEXT, (40, 150))
        if not hasattr(self, "_offers") or self._offers[0] != b.get("sacked_date"):
            self._offers = (b.get("sacked_date"), brd.job_offers(c))
        for i, cid in enumerate(self._offers[1]):
            club = c["clubs"][cid]
            rect = pygame.Rect(40 + i * 360, 196, 340, 200)
            self.panel(rect)
            _badge(self.win, tuple(club["colour"]), (rect.x + 34, rect.y + 40), 18, club)
            self.text(club["name"], "h3", TEXT, (rect.x + 64, rect.y + 28))
            pos = league.position_of(c, cid)
            text, _ = brd.objective(c, club)
            self.text(f"Currently {pos}{brd._suffix(pos)}", "body", MUTED, (rect.x + 20, rect.y + 76))
            self.text(f"Objective: {text.lower()}", "small", MUTED, (rect.x + 20, rect.y + 104))
            self.buttons.append(Button((rect.x + 20, rect.bottom - 62, 200, 46), "Take the job",
                                       lambda cid=cid: self._take_job(cid), primary=True))
        self.buttons.append(Button((40, H - 80, 260, 50), "Start a new career", self.new_career_screen))

    def _take_job(self, cid):
        c = self.career
        for bg in (self.bg, self.my_bg):
            if bg is not None:
                bg.stop()
        self.bg = self.my_bg = None
        self.my_result = None
        # your new club's match this round hasn't been played by the computer
        md = str(c["matchday"])
        c.get("pending_results", {})[md] = [r for r in c.get("pending_results", {}).get(md, [])
                                             if cid not in (r["home"], r["away"])]
        brd.take_job(c, cid)
        league.save(c)
        self.go("home")

    # -- end of season --------------------------------------------------------
    # -- the play-offs (career/playoffs.py) ------------------------------------------
    def draw_playoff(self):
        W, H = self.size
        c = self.career
        self.sidebar("home")
        x0 = 250
        st = playoffs.ensure(c)
        if st is None:
            return self.go("home")
        m = playoffs.my_next(c)
        self.text("Division 1 play-offs", "h1", TEXT, (x0, 18))
        self.text("3rd v 6th and 4th v 5th over two legs, then the final at " + playoffs.VENUE +
                  ". The winners go up with the top two.", "body", MUTED, (x0, 70))
        r = pygame.Rect(x0, 104, W - x0 - 30, 300)
        self.panel(r, "The draw")
        y = r.y + 50
        for label, txt in playoffs.lines(c):
            self.text(label, "small", MUTED, (r.x + 16, y + 2))
            self.text(self._fit_text(txt, "body", r.w - 230), "body", TEXT, (r.x + 210, y))
            y += 34
        r2 = pygame.Rect(x0, r.bottom + 16, W - x0 - 30, H - r.bottom - 112)
        if m is None:
            self.panel(r2)
            if st.get("winner") == c["my_club"]:
                msg = "Promoted! Premier Division football next season."
            elif playoffs.done(c) or not playoffs.still_in(c):
                msg = "It's over for this season."
            else:
                msg = "Waiting for the other semi-final."
            self.text(msg, "h2", ACCENT if st.get("winner") == c["my_club"] else TEXT, (r2.x + 20, r2.y + 24))
            self.buttons.append(Button((W - 260, H - 76, 220, 50), "Continue", self._playoff_continue, primary=True))
            return
        self.panel(r2, "Your next match")
        cx = r2.centerx
        home, away = c["clubs"][m["home"]], c["clubs"][m["away"]]
        _badge(self.win, tuple(home["colour"]), (cx - 60, r2.y + 70), 18, home)
        _badge(self.win, tuple(away["colour"]), (cx + 60, r2.y + 70), 18, away)
        self.text(home["name"], "h2", TEXT, (cx - 90, r2.y + 56), "topright")
        self.text(away["name"], "h2", TEXT, (cx + 90, r2.y + 56))
        what = ("The final" if m["round"] == "final" else
                f"Semi-final, {'first' if m['leg'] == 1 else 'second'} leg")
        where = playoffs.VENUE if m["neutral"] else f"at {home['name']}"
        self.text(f"{what}  ·  {cal.fmt(m['date'], False)}  ·  {where}", "body", MUTED, (cx, r2.y + 104), "midtop")
        if m["round"] == "semi" and m["leg"] == 2:
            first = next(x for x in st["matches"] if x["tie"] == m["tie"] and x["leg"] == 1)["result"]
            self.text(f"First leg: {self.name(m['away'])} {first['hg']} - {first['ag']} {self.name(m['home'])}"
                      "  ·  level on aggregate after 90 minutes: extra time, then penalties", "small", MUTED,
                      (cx, r2.y + 132), "midtop")
        elif m["round"] == "final":
            self.text("Level after 90 minutes: extra time, then penalties", "small", MUTED, (cx, r2.y + 132), "midtop")
        y = H - 76
        self.buttons.append(Button((x0, y, 200, 50), "Pick the team", lambda: self.go("tactics")))
        self.buttons.append(Button((W - 500, y, 220, 50), "Quick result", lambda: self._playoff_play(False)))
        self.buttons.append(Button((W - 260, y, 220, 50), "Watch", lambda: self._playoff_play(True), primary=True))

    def _playoff_play(self, watch):
        c = self.career
        m = playoffs.my_next(c)
        if m is None:
            return
        if m["date"] > c["date"]:
            from career import training
            training.run_all(c, m["date"])
            c["date"] = m["date"]
        avail.fix_lineups(c, m["date"])
        playoffs.play_others(c, until=m["date"])                 # (the other semi on the same night)
        if watch:
            result, quit_ = matches.watch_playoff(c, m)
            if quit_:
                self.quit()
                return
            self._window()
            if result is None:                                   # left early: it doesn't count yet
                self.go("playoff")
                return
        else:
            result = playoffs.quick(c, m)
        playoffs.record(c, m, result)
        playoffs.play_others(c, until=m["date"])
        league.save(c)
        self.go("playoff")

    def _playoff_continue(self):
        playoffs.play_others(self.career)
        league.save(self.career)
        self.go("season_end")

    def draw_season_end(self):
        W, H = self.size
        c = self.career
        from career import divisions
        if playoffs.my_next(c):                      # (your play-offs aren't finished)
            self.go("playoff")
            return self.draw_playoff()
        playoffs.play_others(c)                      # (everyone else's: quick results)
        t = league.table(c)
        champ = t[0]["club"]
        pos = league.position_of(c, c["my_club"])
        mine = divisions.my_div(c)
        up, down = divisions.movers(c, divisions.tables(c)) if divisions.exists(c) else ([], [])
        self.text(f"Season {c['season']} is over", "h1", TEXT, (40, 24))
        title = "the champions" if mine == "pl" else "Division 1 champions"
        if c["my_club"] in up:
            msg = ("Champions - and promoted!" if champ == c["my_club"] else
                   f"Promoted! You finished {_ordinal(pos)}" + (" and won the play-offs." if pos > divisions.UP else "."))
        elif c["my_club"] in down:
            msg = f"Relegated. You finished {_ordinal(pos)} - Division 1 next season."
        elif champ == c["my_club"]:
            msg = f"You are {title}!"
        else:
            msg = f"{self.name(champ, True)} are {title}. You finished {_ordinal(pos)}."
            st = playoffs.state(c)
            if st and c["my_club"] in st["seeds"]:
                msg = msg[:-1] + (", lost the play-off final." if c["my_club"] in
                                  (st["ties"][0]["winner"], st["ties"][1]["winner"]) else ", out in the play-off semis.")
        good = champ == c["my_club"] or c["my_club"] in up
        self.text(self._fit_text(msg, "h2", W - 80), "h2", ACCENT if good else LOSS if c["my_club"] in down else TEXT,
                  (40, 74))
        if up:
            nm = lambda i: self.name(i, True)
            self.text(self._fit_text(f"Going up: {nm(up[0])}, {nm(up[1])} and {nm(up[2])} (play-off winners)   ·   "
                                     f"Going down: {', '.join(nm(i) for i in down)}", "body", W - 80),
                      "body", MUTED, (40, 108))
        r = pygame.Rect(40, 136, W - 80, H - 236)
        self.panel(r)
        self._table_rows(t, r.x + 20, r.y + 18, r.w - 40)
        self.buttons.append(Button((W - 300, H - 80, 260, 52), "Start next season", self.next_season, primary=True))
        self.buttons.append(Button((40, H - 80, 200, 52), "Save & quit", self.save_and_quit))

    def next_season(self):
        league.new_season(self.career)
        league.save(self.career)
        self.go("sacked" if brd.state(self.career).get("sacked") else "summer")

    def draw_summer(self):
        """The summer: what happened to your squad between seasons."""
        W, H = self.size
        c = self.career
        mc = c["my_club"]
        club = c["clubs"][mc]
        sm = c.get("summer", {})
        self.text(f"Summer {c.get('year', '')}", "h1", TEXT, (40, 24))
        self.text("Everyone is a year older. Here's what changed at your club before the new season.", "body",
                  MUTED, (40, 76))
        byname = {p["Name"]: p for p in club["players"]}
        cols = [("Youth intake", sm.get("intake", []), ACCENT), ("Signed", sm.get("signed", []), TEXT),
                ("Out of contract", sm.get("free", []), MUTED),
                ("Retired", sm.get("retired", []), MUTED), ("Released", sm.get("released", []), MUTED),
                ("Lost a step", sm.get("declined", []), DRAW)]
        cols = [x for x in cols if x[1] or x[0] in ("Youth intake", "Retired", "Released")]
        cw = (W - 80 - (len(cols) - 1) * 12) // len(cols)
        for i, (title, names, col) in enumerate(cols):
            r = pygame.Rect(40 + i * (cw + 12), 116, cw, H - 330)
            self.panel(r, title)
            y = r.y + 48
            if not names:
                self.text("Nobody", "body", MUTED, (r.x + 16, y))
            for e in names:
                if isinstance(e, str):                       # (older saves: just the name)
                    e = {"name": e}
                p = byname.get(e["name"])
                self.text(e["name"], "body", TEXT, (r.x + 16, y))
                if "pos" in e:
                    self.text(f"{e['pos']}, {e['age']}  ·  rated {e['rating']}", "small", col, (r.x + 16, y + 22))
                if p is not None:
                    if title == "Youth intake":
                        gap = (p.get("Potential") or 0) - clubs_mod.overall(p)
                        view = "a real prospect" if gap >= 18 else "promising" if gap >= 12 else "one for the future"
                        self.text(view, "small", col, (r.x + 16, y + 40))
                    self.buttons.append(_Invisible(pygame.Rect(r.x + 8, y - 2, r.w - 16, 60),
                                                   lambda pid=p["id"]: self.view_player(mc, pid)))
                y += 66 if title == "Youth intake" else 50
        # Around the league
        r = pygame.Rect(40, H - 200, W - 80, 110)
        self.panel(r, "Around the league")
        notes = [n for n in c.get("news", []) if n["club"] != mc and n["date"] == c.get("date")
                 and "retires" in n["text"]]
        big = []
        for n in notes:
            big.append(f"{self.name(n['club'], True)}: {n['text']}")
        self.text(("   ".join(big[:3]) or "A quiet summer.")[:170], "small", MUTED, (r.x + 16, r.y + 50))
        if len(big) > 3:
            self.text(f"...and {len(big) - 3} more retirements.", "small", MUTED, (r.x + 16, r.y + 74))
        self.buttons.append(Button((W - 300, H - 70, 260, 52), "On to the new season", lambda: self.go("home"),
                                   primary=True))


class _Probe:
    """Stands in for a player so roles/library.instructions_for can work out his instructions."""
    def __init__(self, slot, club, role_id):
        self.role = slot
        self.role_style = role_id
        self.team = -1
        self._club = club



class _Invisible(Button):
    """A clickable area drawn by the screen itself."""
    def __init__(self, rect, action):
        super().__init__(rect, "", action)

    def draw(self, surf, fonts, mouse):
        pass


def main():
    App().run()
