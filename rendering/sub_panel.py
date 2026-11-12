"""
rendering/sub_panel.py
======================
The substitutions panel in the match window (career matches you watch).

S opens it (the match pauses) and closes it again; Esc closes it too.
  - click one of your players on the left, then a substitute on the right:
    the change is queued and made at the next stoppage
  - click a queued change to cancel it
  - "Assistant" decides whether your assistant also makes changes for you
  - click a player's ROLE (the button by his name) to change how he plays -
    straight away, no substitution needed (it's an instruction from the
    touchline, for this match)
  - FORMATION: move your players around the grid (click a player, then a
    spot - an empty one, or another player to swap them) or pick a
    ready-made shape, then Confirm.  Also straight away.
"""

import pygame

BG = (16, 22, 30)
PANEL = (28, 36, 48)
ROW = (38, 48, 62)
ROW_HI = (60, 90, 130)
ROW_OFF = (30, 34, 40)
WHITE = (235, 235, 235)
GREY = (150, 155, 165)
DIM = (95, 100, 110)
GREEN = (110, 210, 120)
AMBER = (240, 190, 70)
RED = (230, 90, 80)
YELLOW = (250, 215, 40)

SLOT_ORDER = ["GK", "RB", "RCB", "LCB", "LB", "RM", "RCM", "LCM", "LM", "ST1", "ST2"]
SLOT_LABEL = {"GK": "GK", "RB": "RB", "RCB": "CB", "LCB": "CB", "LB": "LB", "RM": "RM",
              "RCM": "CM", "LCM": "CM", "LM": "LM", "ST1": "ST", "ST2": "ST"}
FIT_WORD = {0: ("Natural", GREEN), 4: ("Can play there", AMBER), 10: ("Out of position", RED),
            30: ("Not his position", RED)}


class SubPanel:
    def __init__(self):
        self.font = pygame.font.SysFont("Arial", 16)
        self.small = pygame.font.SysFont("Arial", 13)
        self.big = pygame.font.SysFont("Arial", 22, bold=True)
        self.selected = None        # the player object picked to come off
        self.error = None
        self.notice = None          # e.g. "X is injured - pick his replacement"
        self.hits = []              # [(rect, action, data)]
        self.role_menu = None       # the player whose role list is open
        self.mode = None            # "formation": the formation board
        self.f_plan = {}            # id(player) -> spot, while you're changing the formation
        self.f_sel = None           # the player picked to move

    def _stamina_colour(self, s):
        return GREEN if s >= 0.80 else AMBER if s >= 0.70 else RED

    def draw(self, surface, engine):
        subs, tid = engine.subs, engine.my_team
        w, h = surface.get_size()
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 170))
        surface.blit(veil, (0, 0))
        box = pygame.Rect(40, 66, w - 80, h - 66 - 40)
        pygame.draw.rect(surface, PANEL, box, border_radius=8)
        self.hits = []

        # Title line
        used, windows = subs.used[tid], subs.windows[tid]
        title = self.big.render("Substitutions", True, WHITE)
        surface.blit(title, (box.x + 18, box.y + 12))
        info = (f"Used {used} of {5}    Windows {windows} of 3 (half-time is free)    "
                f"Minute {engine.match_minute() if engine.match_state != 'halftime' else 'HT'}")
        surface.blit(self.font.render(info, True, GREY), (box.x + 200, box.y + 17))
        on = subs.auto[tid]
        btn = pygame.Rect(box.right - 230, box.y + 10, 210, 30)
        pygame.draw.rect(surface, (50, 110, 70) if on else ROW, btn, border_radius=5)
        t = self.font.render(f"Assistant makes changes: {'ON' if on else 'OFF'}", True, WHITE)
        surface.blit(t, (btn.centerx - t.get_width() // 2, btn.y + 6))
        self.hits.append((btn, "assistant", None))
        fbtn = pygame.Rect(btn.x - 180, box.y + 10, 160, 30)
        pygame.draw.rect(surface, ROW_HI if self.mode == "formation" else ROW, fbtn, border_radius=5)
        t = self.font.render("Formation", True, WHITE)
        surface.blit(t, (fbtn.centerx - t.get_width() // 2, fbtn.y + 6))
        self.hits.append((fbtn, "formation", None))
        if self.mode == "formation":
            return self._draw_formation(surface, engine, box)

        # Your team (left)
        lx, ty = box.x + 18, box.y + (78 if self.notice else 58)
        col_w = (box.width - 54) * 58 // 100            # (wider: room for the role button)
        bench_w = box.width - 54 - col_w
        surface.blit(self.font.render("On the pitch - click who comes off, or a role to change it", True, GREY), (lx, ty))
        team = engine.team0 if tid == 0 else engine.team1
        by_slot = {getattr(p, "slot", p.role): p for p in team}
        coming_off = {id(q[0]): q for q in subs.queue[tid]}
        y = ty + 24
        from config import slots as slots_mod
        order = SLOT_ORDER if set(by_slot) <= set(SLOT_ORDER) else \
            ["GK"] + sorted((s for s in by_slot if s != "GK"), key=lambda s: (slots_mod.row(s), -slots_mod.lane(s)))
        for slot in order:
            p = by_slot.get(slot)
            if p is None:
                continue
            r = pygame.Rect(lx, y, col_w, 30)
            active = getattr(p, "is_active", True)
            colour = ROW_HI if p is self.selected else (ROW if active else ROW_OFF)
            pygame.draw.rect(surface, colour, r, border_radius=4)
            surface.blit(self.font.render(SLOT_LABEL.get(slot) or slots_mod.LABEL.get(slot, slot), True, GREY),
                         (r.x + 8, r.y + 6))
            name_col = WHITE if active else DIM
            surface.blit(self.font.render(self._fit(p.name, 165), True, name_col), (r.x + 48, r.y + 6))
            if slot != "GK" and active and id(p) not in coming_off:
                rb = pygame.Rect(r.x + 220, r.y + 3, 158, 24)
                open_ = self.role_menu is p
                pygame.draw.rect(surface, ROW_HI if open_ else (48, 60, 78), rb, border_radius=4)
                label = self._fit(_role_name(p), 150)
                surface.blit(self.small.render(label, True, WHITE), (rb.x + 6, rb.y + 5))
                self.hits.append((rb, "role_menu", p))
            rating = subs.ratings[tid].get(slot)
            if rating is not None:
                surface.blit(self.small.render(str(rating), True, GREY), (r.right - 200, r.y + 8))
            st = getattr(p, "stamina", 1.0)
            if active:
                sc = self.font.render(f"{round(st * 100)}%", True, self._stamina_colour(st))
                surface.blit(sc, (r.right - 70, r.y + 6))
                bar = pygame.Rect(r.right - 150, r.y + 12, 70, 7)
                pygame.draw.rect(surface, (20, 24, 30), bar)
                pygame.draw.rect(surface, self._stamina_colour(st),
                                 pygame.Rect(bar.x, bar.y, int(bar.w * st), bar.h))
            else:
                surface.blit(self.font.render("Sent off", True, RED), (r.right - 90, r.y + 6))
            if p.yellow_cards:
                pygame.draw.rect(surface, YELLOW, pygame.Rect(r.right - 172, r.y + 7, 10, 15))
            if id(p) in coming_off:
                surface.blit(self.small.render("coming off", True, AMBER), (r.x + 226, r.y + 8))
            if active and id(p) not in coming_off:
                self.hits.append((r, "select", p))
            y += 34

        # Bench (right)
        rx = lx + col_w + 18
        col_w = bench_w
        hint = "Substitutes" if self.selected is None else \
            f"Substitutes - who replaces {self.selected.name} ({_label(self.selected)})?"
        surface.blit(self.font.render(hint, True, GREY), (rx, ty))
        y = ty + 24
        queued = {q[1] for q in subs.queue[tid]}
        for b in subs.bench[tid]:
            r = pygame.Rect(rx, y, col_w, 30)
            gone = b.get("used") or b["id"] in queued
            pygame.draw.rect(surface, ROW_OFF if gone else ROW, r, border_radius=4)
            surface.blit(self.font.render(b.get("pos", ""), True, GREY), (r.x + 8, r.y + 6))
            surface.blit(self.font.render(b["name"], True, DIM if gone else WHITE), (r.x + 48, r.y + 6))
            if b.get("used"):
                surface.blit(self.small.render("on the pitch", True, DIM), (r.right - 90, r.y + 8))
            elif b["id"] in queued:
                surface.blit(self.small.render("coming on", True, AMBER), (r.right - 90, r.y + 8))
            elif self.selected is not None:
                slot = getattr(self.selected, "slot", self.selected.role)
                drop = b.get("drop", {}).get(slot, 0)
                word, wc = FIT_WORD.get(drop, ("", GREY))
                rating = b.get("rating", {}).get(slot)
                surface.blit(self.small.render(word, True, wc), (r.right - 190, r.y + 8))
                if rating is not None:
                    surface.blit(self.font.render(str(rating), True, WHITE), (r.right - 40, r.y + 6))
            if not gone:
                self.hits.append((r, "bring_on", b))
            y += 34

        # Queued changes and messages (bottom)
        y = box.bottom - 30 - 26 * max(1, len(subs.queue[tid]))
        if subs.queue[tid]:
            for p, bid, _ in subs.queue[tid]:
                b = next((x for x in subs.bench[tid] if x["id"] == bid), None)
                txt = f"{p.name}  off   >>   {b['name'] if b else '?'}  on      (at the next stoppage - click to cancel)"
                r = pygame.Rect(lx, y, box.width - 36, 24)
                pygame.draw.rect(surface, (60, 50, 30), r, border_radius=4)
                surface.blit(self.font.render(txt, True, AMBER), (r.x + 8, r.y + 3))
                self.hits.append((r, "cancel", p))
                y += 26
        # A role list, open over the rest
        if self.role_menu is not None:
            p = self.role_menu
            row = next((r for r, a, d in self.hits if a == "role_menu" and d is p), None)
            if row is not None:
                opts = _role_options(p)
                mr = pygame.Rect(row.x, row.bottom + 2, 420, 8 + 44 * len(opts))
                if mr.bottom > box.bottom - 8:
                    mr.bottom = row.y - 2
                pygame.draw.rect(surface, (22, 28, 38), mr, border_radius=6)
                pygame.draw.rect(surface, ROW_HI, mr, 1, border_radius=6)
                yy = mr.y + 4
                current = getattr(p, "role_style", None)
                self.hits = [h for h in self.hits if h[1] in ("role_menu",)]   # (the list takes the clicks)
                for rid, name, desc in opts:
                    orr = pygame.Rect(mr.x + 4, yy, mr.w - 8, 40)
                    if _same_role(rid, current, p):
                        pygame.draw.rect(surface, (50, 110, 70), orr, border_radius=4)
                    surface.blit(self.font.render(name, True, WHITE), (orr.x + 8, orr.y + 3))
                    surface.blit(self.small.render(self._fit(desc, mr.w - 24), True, GREY), (orr.x + 8, orr.y + 22))
                    self.hits.append((orr, "set_role", (p, rid)))
                    yy += 44
                self.hits.append((box, "close_menu", None))
        msg = self.error or "S or Esc to go back to the match"
        surface.blit(self.small.render(msg, True, RED if self.error else DIM), (lx, box.bottom - 24))
        if self.notice:
            t = self.font.render(self.notice, True, (20, 20, 20))
            r = pygame.Rect(box.x + 18, box.y + 46 - 2, t.get_width() + 20, 24)
            pygame.draw.rect(surface, AMBER, r, border_radius=4)
            surface.blit(t, (r.x + 10, r.y + 3))

    def click(self, pos, engine):
        subs, tid = engine.subs, engine.my_team
        for r, action, data in self.hits:
            if not r.collidepoint(pos):
                continue
            self.error = None
            if action == "assistant":
                subs.auto[tid] = not subs.auto[tid]
            elif action == "formation":
                if self.mode == "formation":
                    self.mode = None
                else:
                    team = engine.team0 if tid == 0 else engine.team1
                    self.mode, self.f_sel = "formation", None
                    self.f_plan = {id(p): p.slot for p in team if p.role != "GK" and getattr(p, "is_active", True)}
            elif action == "f_cell":
                self._f_cell(engine, data)
            elif action == "f_preset":
                from gameplay import formation_change as fc
                team = engine.team0 if tid == 0 else engine.team1
                self.f_plan = {id(p): s for p, s in fc.fit(team, data).items()}
                self.f_sel = None
            elif action == "f_confirm":
                from gameplay import formation_change as fc
                team = engine.team0 if tid == 0 else engine.team1
                plan = {p: self.f_plan[id(p)] for p in team if id(p) in self.f_plan}
                problem = fc.apply(engine, tid, plan)
                if problem:
                    self.error = problem
                else:
                    self.mode = None
                    self.notice = f"Formation changed: {fc.name_of(team)}"
            elif action == "f_cancel":
                self.mode, self.f_sel = None, None
            elif action == "select":
                self.selected = None if data is self.selected else data
            elif action == "bring_on":
                if self.selected is None:
                    self.error = "First pick the player coming off (left)"
                else:
                    err = subs.request(tid, self.selected, data["id"])
                    if err:
                        self.error = err
                    else:
                        self.selected = None
                        self.notice = None
            elif action == "cancel":
                subs.cancel(tid, data)
            elif action == "role_menu":
                self.role_menu = None if self.role_menu is data else data
            elif action == "set_role":
                p, rid = data
                set_role(p, rid)
                self.role_menu = None
            elif action == "close_menu":
                self.role_menu = None
            return

    # -- the formation board ----------------------------------------------------
    def _f_cell(self, engine, slot):
        tid = engine.my_team
        team = engine.team0 if tid == 0 else engine.team1
        by_id = {id(p): p for p in team}
        occupant = next((pid for pid, s in self.f_plan.items() if s == slot), None)
        if self.f_sel is None:
            self.f_sel = occupant
            return
        if occupant == self.f_sel:
            self.f_sel = None
            return
        mine = self.f_plan[self.f_sel]
        if occupant is not None:
            self.f_plan[occupant] = mine
        self.f_plan[self.f_sel] = slot
        self.f_sel = None

    def _draw_formation(self, surface, engine, box):
        from config import slots
        from gameplay import formation_change as fc
        tid = engine.my_team
        team = engine.team0 if tid == 0 else engine.team1
        by_id = {id(p): p for p in team}
        occ = {s: by_id[pid] for pid, s in self.f_plan.items() if pid in by_id}
        # The board: attack at the top, our goal at the bottom
        cw, ch = 118, 62
        bx, by = box.x + 18, box.y + 58
        surface.blit(self.font.render("Click a player, then a spot (or another player to swap)", True, GREY), (bx, by))
        by += 26
        pitch = pygame.Rect(bx, by, cw * 5 + 24, ch * 6 + 30)
        pygame.draw.rect(surface, (32, 70, 44), pitch, border_radius=6)
        for row in range(4, -1, -1):
            y = by + 8 + (4 - row) * (ch + 4)
            for i, lane in enumerate(range(-2, 3)):
                slot = next((s for s, rl in slots.GRID.items() if rl == (row, lane)), None)
                x = bx + 8 + i * (cw + 2)
                if slot is None:
                    continue
                r = pygame.Rect(x, y, cw - 4, ch)
                p = occ.get(slot)
                sel = p is not None and id(p) == self.f_sel
                col = (60, 110, 160) if sel else (44, 92, 60) if p is None else (52, 64, 82)
                pygame.draw.rect(surface, col, r, border_radius=5)
                surface.blit(self.small.render(slot, True, GREY), (r.x + 5, r.y + 3))
                if p is not None:
                    surface.blit(self.font.render(self._fit(p.name.split(" ")[-1], cw - 14), True, WHITE),
                                 (r.x + 5, r.y + 22))
                    surface.blit(self.small.render(slots.LABEL.get(p.slot, p.slot) + " now", True, DIM),
                                 (r.x + 5, r.y + 42))
                self.hits.append((r, "f_cell", slot))
        gk = pygame.Rect(bx + 8 + 2 * (cw + 2), by + 8 + 5 * (ch + 4), cw - 4, 28)
        pygame.draw.rect(surface, (52, 64, 82), gk, border_radius=5)
        keeper = next((p for p in team if p.role == "GK"), None)
        surface.blit(self.small.render("GK  " + (keeper.name.split(" ")[-1] if keeper else ""), True, WHITE),
                     (gk.x + 5, gk.y + 7))
        # Ready-made shapes, and the verdict
        rx = pitch.right + 24
        surface.blit(self.font.render("Ready-made", True, GREY), (rx, box.y + 58))
        names = list(slots.FORMATIONS)
        for i, name in enumerate(names):
            r = pygame.Rect(rx + (i % 2) * 150, box.y + 84 + (i // 2) * 40, 142, 32)
            label = {"2-3-5": "2-3-5 (all out)", "5-4-1": "5-4-1 (park it)"}.get(name, name)
            pygame.draw.rect(surface, ROW, r, border_radius=5)
            t = self.font.render(label, True, WHITE)
            surface.blit(t, (r.centerx - t.get_width() // 2, r.y + 7))
            self.hits.append((r, "f_preset", name))
        y = box.y + 84 + ((len(names) + 1) // 2) * 40 + 10
        field = sorted(self.f_plan.values())
        name = next((n for n, sp in slots.FORMATIONS.items() if sorted(sp) == field), "custom")
        surface.blit(self.big.render(f"Shape: {name}", True, WHITE), (rx, y))
        y += 34
        moved = sum(1 for p in team if id(p) in self.f_plan and self.f_plan[id(p)] != p.slot)
        surface.blit(self.font.render(f"{moved} player(s) moving", True, GREY), (rx, y))
        y += 28
        if not any(slots.row(s) == 0 for s in field):
            surface.blit(self.font.render("Nobody at the back!", True, RED), (rx, y))
        ok = pygame.Rect(rx, box.bottom - 100, 140, 40)
        no = pygame.Rect(rx + 150, box.bottom - 100, 140, 40)
        pygame.draw.rect(surface, (50, 110, 70), ok, border_radius=6)
        pygame.draw.rect(surface, ROW, no, border_radius=6)
        for r, label in ((ok, "Confirm"), (no, "Cancel")):
            t = self.font.render(label, True, WHITE)
            surface.blit(t, (r.centerx - t.get_width() // 2, r.y + 11))
        self.hits.append((ok, "f_confirm", None))
        self.hits.append((no, "f_cancel", None))
        msg = self.error or "S or Esc to go back to the match"
        surface.blit(self.font.render(msg, True, RED if self.error else DIM), (box.x + 18, box.bottom - 30))

    def _fit(self, text, width):
        """Shorten text to fit a width (px)."""
        f = self.font if width > 152 else self.small
        if f.size(text)[0] <= width:
            return text
        while text and f.size(text + "...")[0] > width:
            text = text[:-1]
        return text + "..."


# ---------------------------------------------------------------------------
# Roles (roles/library.py)
# ---------------------------------------------------------------------------
def _label(p):
    from config import slots
    s = getattr(p, "slot", p.role)
    return SLOT_LABEL.get(s) or slots.LABEL.get(s, s)


def _role_options(p):
    import roles.library as lib
    return lib.MANAGER_ROLES.get(lib.POSITION_GROUP.get(p.role), [])


def _same_role(rid, current, p):
    """The same settings (a left- or right-sided version of one role counts as the same)."""
    import roles.library as lib
    if current is None:
        return False
    a, b = lib.ROLES.get(rid), lib.ROLES.get(current)
    return a is not None and b is not None and a.shape == b.shape and a.runs == b.runs \
        and a.instructions == b.instructions


def _role_name(p):
    """His role's name as the Tactics screen calls it."""
    for rid, name, _ in _role_options(p):
        if _same_role(rid, getattr(p, "role_style", None), p):
            return name
    import roles.library as lib
    try:
        return lib.role_for(p).name.split(" (")[0]
    except Exception:
        return "Role"


def set_role(p, rid):
    """Change how he plays, now (the shape is worked out fresh every fraction of a second)."""
    p.role_style = rid
