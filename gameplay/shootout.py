"""
gameplay/shootout.py
====================
A penalty shoot-out, after extra time in a knockout match (gameplay/match_engine.py).

The rules (IFAB Law 10):
  - both sides take five kicks, in turn, at the same goal; it's over as soon as one side can't catch up
  - level after five each: sudden death, one kick each until one scores and the other doesn't
  - only the players on the pitch at the end of extra time take kicks; nobody takes a second until all his
    team-mates have had one (the keeper last here)
  - the team that wins the toss kicks first

How it plays: each kick is shown - the taker walks from the centre circle to the spot, runs up, the ball
flies to a corner (or the middle) and the keeper dives.  Whether it goes in is worked out from the taker's
Penalties and Composure against the keeper's Shot Stopping.

Real-world figures: about 3 in 4 shoot-out penalties are scored (World Cups and Euros 1976-2022: ~70%;
club football ~75-78%); of the misses, roughly two in three are saved and one in three goes wide or over.
Kickers go to the keeper's sides far more than the middle (about 14% down the middle).
"""

import random
from pygame.math import Vector2
import pygame

from config.constants import WIDTH, HEIGHT, M_TO_PX, GOAL_WIDTH, GOAL_HEIGHT, FIELD_MARGIN

SCORE_BASE = 0.60          # chance of scoring, before the taker and keeper ...
PER_PENALTIES = 0.012      # ... + this per point of the taker's Penalties (1-20)
PER_COMPOSURE = 0.006      # ... + this per point of his Composure
PER_KEEPER = 0.008         # ... - this per point of the keeper's Shot Stopping above 10
SCORE_RANGE = (0.50, 0.92)
SAVED_SHARE = 0.65         # of the misses: saved (the rest wide or over)
MIDDLE = 0.14              # kicks down the middle
# The kick, in game seconds
WALK, READY, RUNUP, FLIGHT, SHOW = 1.6, 0.5, 0.55, 0.42, 1.6
END_HOLD = 3.0             # after the last kick, before full time


class Shootout:
    def __init__(self, engine, rng=None):
        self.e = engine
        self.rng = rng or random.Random()
        self.goal_x = WIDTH                                  # (both teams shoot at the right-hand goal)
        self.spot = Vector2(WIDTH - 11.0 * M_TO_PX, HEIGHT / 2)
        self.kicks = [[], []]                                # [True / False per kick] for each team
        self.order = {t: self._takers(t) for t in (0, 1)}
        self.first = self.rng.choice((0, 1))                 # the toss
        self.turn = self.first
        self.n = [0, 0]                                      # kicks taken
        self.phase = "walk"
        self.t = 0.0
        self.done = False
        self.winner = None
        self.banner = None
        self.end_t = 0.0
        self.home = {}                                       # where each man waits
        self._line_up()
        self._new_kick()

    # --- who kicks -----------------------------------------------------------------------------------
    def _team(self, t):
        return [p for p in (self.e.team0 if t == 0 else self.e.team1) if getattr(p, "is_active", True)]

    def _keeper(self, t):
        team = self._team(t)
        return next((p for p in team if p.role == "GK"), None) or (team[0] if team else None)

    def _takers(self, t):
        team = self._team(t)
        gk = self._keeper(t)
        field = [p for p in team if p is not gk]
        a = lambda p, k: p.attributes.get(k, 10)
        field.sort(key=lambda p: -(2 * a(p, "Penalties") + a(p, "Composure") + a(p, "Finishing")))
        return field + ([gk] if gk else [])

    # --- the scene -----------------------------------------------------------------------------------
    def _line_up(self):
        """Everyone in the centre circle (keepers by the box), the ball dead."""
        b = self.e.ball
        b.owner, b.is_dead, b.vel, b.z, b.vz = None, True, Vector2(0, 0), 0, 0
        for t in (0, 1):
            others = [p for p in self._team(t) if p is not self._keeper(t)]
            for i, p in enumerate(others):
                x = WIDTH / 2 + (-1.6 if t == 0 else 1.6) * M_TO_PX
                y = HEIGHT / 2 + (i - (len(others) - 1) / 2) * 1.4 * M_TO_PX
                self.home[id(p)] = Vector2(x, y)
            gk = self._keeper(t)
            if gk is not None:
                self.home[id(gk)] = Vector2(WIDTH - (19.0 if t == 0 else 22.0) * M_TO_PX, HEIGHT / 2 + 18 * M_TO_PX)
        for t in (0, 1):
            for p in self._team(t):
                p.pos = Vector2(self.home[id(p)])
                p.target = Vector2(p.pos)
                p.vel = Vector2(0, 0)
                p.has_ball = False

    def _new_kick(self):
        t = self.turn
        takers = self.order[t] or self._team(t)
        self.taker = takers[self.n[t] % len(takers)] if takers else None
        self.keeper = self._keeper(1 - t)
        self.t, self.phase, self.banner = 0.0, "walk", None
        self.taker_from = Vector2(self.taker.pos) if self.taker else None
        self.keeper_from = Vector2(self.keeper.pos) if self.keeper else None
        self.back = [(p, Vector2(p.pos)) for p in self._team(0) + self._team(1)
                     if p is not self.taker and p is not self.keeper and (p.pos - self.home[id(p)]).length() > 1]
        b = self.e.ball
        b.pos, b.z, b.vel = Vector2(self.spot), 0, Vector2(0, 0)
        self._decide()

    def _decide(self):
        """Where it goes and whether it goes in."""
        a = lambda p, k: (p.attributes.get(k, 10) if p is not None else 10)
        p = (SCORE_BASE + PER_PENALTIES * a(self.taker, "Penalties") + PER_COMPOSURE * a(self.taker, "Composure")
             - PER_KEEPER * (a(self.keeper, "Shot Stopping") - 10))
        p = max(SCORE_RANGE[0], min(SCORE_RANGE[1], p))
        r = self.rng
        self.scored = r.random() < p
        self.how = "goal" if self.scored else ("saved" if r.random() < SAVED_SHARE else "missed")
        side = 0 if r.random() < MIDDLE else r.choice((-1, 1))
        half = GOAL_WIDTH / 2
        if self.how == "missed":
            if r.random() < 0.5 or side == 0:
                y = HEIGHT / 2 + (side or r.choice((-1, 1))) * r.uniform(half * 0.5, half * 0.9)
                z = GOAL_HEIGHT * r.uniform(1.15, 1.6)             # over the bar
            else:
                y = HEIGHT / 2 + side * (half + r.uniform(0.4, 1.5) * M_TO_PX)    # wide
                z = GOAL_HEIGHT * r.uniform(0.1, 0.6)
            x = self.goal_x + 1.5 * M_TO_PX
            dive = r.choice((-1, 0, 1))
        else:
            y = HEIGHT / 2 + side * r.uniform(half * 0.45, half * 0.85)
            z = GOAL_HEIGHT * r.uniform(0.05, 0.7)
            x = self.goal_x + (1.0 * M_TO_PX if self.how == "goal" else -0.3 * M_TO_PX)
            if self.how == "saved":
                dive = side
            else:
                dive = r.choice([d for d in (-1, 0, 1) if d != side] + ([side] if r.random() < 0.35 else []))
        self.target = Vector2(x, y)
        self.target_z = z
        self.dive = Vector2(self.goal_x - 0.4 * M_TO_PX, HEIGHT / 2 + dive * half * 0.6)
        if self.how == "saved":
            self.dive = Vector2(self.goal_x - 0.6 * M_TO_PX, y)
        self.rebound = Vector2(self.goal_x - r.uniform(4, 8) * M_TO_PX, y + r.uniform(-3, 3) * M_TO_PX)

    # --- each frame ----------------------------------------------------------------------------------
    def update(self, dt):
        if self.done:
            self.end_t += dt
            return
        self.t += dt
        tk, gk, b = self.taker, self.keeper, self.e.ball
        behind = self.spot + Vector2(-2.2 * M_TO_PX, 0.8 * M_TO_PX)
        line = Vector2(self.goal_x - 0.4 * M_TO_PX, HEIGHT / 2)
        if self.phase == "walk":
            k = min(1.0, self.t / WALK)
            if tk is not None:
                tk.pos = self.taker_from.lerp(behind, k)
            if gk is not None:
                gk.pos = self.keeper_from.lerp(line, k)
            for p, frm in self.back:
                p.pos = frm.lerp(self.home[id(p)], k)
            if self.t >= WALK:
                self._next("ready")
        elif self.phase == "ready":
            if self.t >= READY:
                self._next("runup")
        elif self.phase == "runup":
            k = min(1.0, self.t / RUNUP)
            if tk is not None:
                tk.pos = behind.lerp(self.spot + Vector2(-0.4 * M_TO_PX, 0), k)
            if self.t >= RUNUP:
                self._next("flight")
        elif self.phase == "flight":
            k = min(1.0, self.t / FLIGHT)
            b.pos = self.spot.lerp(self.target, k)
            b.z = self.target_z * k
            if gk is not None:
                gk.pos = line.lerp(self.dive, min(1.0, k * 1.2))
            if self.t >= FLIGHT:
                if self.how == "goal":
                    self.kicks[self.turn].append(True)
                else:
                    self.kicks[self.turn].append(False)
                self.n[self.turn] += 1
                self.banner = {"goal": "GOAL!", "saved": "SAVED!", "missed": "MISSED!"}[self.how]
                self._next("show")
        elif self.phase == "show":
            if self.how == "saved":
                k = min(1.0, self.t / 0.5)
                b.pos = self.target.lerp(self.rebound, k)
                b.z = self.target_z * (1 - k)
            elif self.how == "goal":
                b.z = max(0.0, b.z - dt * 60)
            if self.t >= SHOW:
                self.winner = self._decided()
                if self.winner is not None:
                    self.done = True
                    self.banner = None
                    return
                self.turn = 1 - self.turn
                self._new_kick()

    def _next(self, phase):
        self.phase, self.t = phase, 0.0

    def _decided(self):
        """The winning team, or None while it's still going."""
        g = [sum(k) for k in self.kicks]
        n = [len(k) for k in self.kicks]
        if n[0] <= 5 and n[1] <= 5 and max(n) <= 5:
            left = [5 - n[0], 5 - n[1]]
            if g[0] > g[1] + left[1]:
                return 0
            if g[1] > g[0] + left[0]:
                return 1
            if n[0] == n[1] == 5 and g[0] != g[1]:
                return 0 if g[0] > g[1] else 1
            return None
        if n[0] == n[1] and g[0] != g[1]:                    # sudden death: after each pair
            return 0 if g[0] > g[1] else 1
        return None

    def score(self):
        return [sum(self.kicks[0]), sum(self.kicks[1])]

    def finished(self):
        return self.done and self.end_t >= END_HOLD

    # --- drawing -------------------------------------------------------------------------------------
    def draw(self, surface, ui, names):
        """The shoot-out board at the top of the pitch, and the GOAL / SAVED banner."""
        w = 460
        x0 = FIELD_MARGIN + WIDTH / 2 - w / 2
        y0 = FIELD_MARGIN + 8
        box = pygame.Surface((w, 74), pygame.SRCALPHA)
        box.fill((0, 0, 0, 175))
        surface.blit(box, (x0, y0))
        title = ui.med_font.render("PENALTIES", True, (255, 255, 255))
        surface.blit(title, (x0 + w / 2 - title.get_width() / 2, y0 + 4))
        sc = self.score()
        cols = ((30, 144, 255), (220, 50, 50))
        for t in (0, 1):
            y = y0 + 30 + t * 21
            nm = ui.small_font.render(names[t][:18], True, cols[t])
            surface.blit(nm, (x0 + 10, y))
            n = max(5, len(self.kicks[0]), len(self.kicks[1]))
            for i in range(n):
                cx = int(x0 + 150 + i * 22)
                cy = y + 8
                if i < len(self.kicks[t]):
                    col = (60, 200, 90) if self.kicks[t][i] else (220, 60, 60)
                    pygame.draw.circle(surface, col, (cx, cy), 7)
                else:
                    pygame.draw.circle(surface, (150, 150, 150), (cx, cy), 7, 1)
            s = ui.med_font.render(str(sc[t]), True, (255, 220, 0))
            surface.blit(s, (x0 + w - 30, y - 2))
        if self.banner:
            col = {"GOAL!": (60, 220, 90), "SAVED!": (255, 220, 0), "MISSED!": (230, 70, 70)}[self.banner]
            text = ui.huge_font.render(self.banner, True, col)
            who = ui.normal_font.render(getattr(self.taker, "name", ""), True, (255, 255, 255))
            cx = FIELD_MARGIN + WIDTH * 0.74                  # (over the box, clear of the players)
            cy = FIELD_MARGIN + HEIGHT * 0.22
            surface.blit(text, (cx - text.get_width() / 2, cy))
            surface.blit(who, (cx - who.get_width() / 2, cy + 54))
        elif self.phase in ("walk", "ready") and self.taker is not None and not self.done:
            t = ui.normal_font.render(f"{self.taker.name} to take it", True, (255, 255, 255))
            surface.blit(t, (FIELD_MARGIN + WIDTH / 2 - t.get_width() / 2, y0 + 82))
        if self.done:
            sc = self.score()
            msg = ui.large_font.render(f"{names[self.winner]} win {max(sc)}-{min(sc)} on penalties", True,
                                       (255, 220, 0))
            surface.blit(msg, (FIELD_MARGIN + WIDTH / 2 - msg.get_width() / 2, FIELD_MARGIN + HEIGHT * 0.22))
