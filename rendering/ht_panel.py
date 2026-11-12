"""
rendering/ht_panel.py
=====================
The half-time team talk (career matches you watch).

At the break the match waits: pick what to tell them, see how each man took
it, then start the second half (button or Enter).  S still opens the
substitutions panel - changes at half-time are free.

The reactions come from the career (career/teamtalk.py half_table): this
just shows them and calls engine.give_ht_talk().
"""

import pygame

from rendering.sub_panel import PANEL, ROW, ROW_HI, WHITE, GREY, DIM, GREEN, AMBER, RED

BTN = (50, 110, 70)


class HTPanel:
    def __init__(self, tid):
        self.tid = tid
        self.font = pygame.font.SysFont("Arial", 17)
        self.small = pygame.font.SysFont("Arial", 14)
        self.big = pygame.font.SysFont("Arial", 24, bold=True)
        self.hits = []

    def _names(self, engine):
        team = engine.team0 if self.tid == 0 else engine.team1
        out = {str(getattr(p, "pid", None)): p.name for p in team}
        for b in engine.subs.bench[self.tid]:
            out.setdefault(str(b["id"]), b.get("name", "?"))
        return out

    def draw(self, surface, engine):
        w, h = surface.get_size()
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 170))
        surface.blit(veil, (0, 0))
        box = pygame.Rect(max(40, w // 2 - 430), 66, min(w - 80, 860), h - 66 - 40)
        pygame.draw.rect(surface, PANEL, box, border_radius=8)
        self.hits = []
        import config.formations as formations
        names = (formations.db.home_team_name, formations.db.away_team_name)
        title = self.big.render(f"Half-time:  {names[0]} {engine.score[0]} - {engine.score[1]} {names[1]}", True, WHITE)
        surface.blit(title, (box.x + 20, box.y + 14))
        surface.blit(self.small.render("S: substitutions (free at half-time)", True, GREY), (box.x + 22, box.y + 50))
        given = engine.ht_given
        y = box.y + 84
        if given is None:
            surface.blit(self.font.render("What do you tell them?", True, WHITE), (box.x + 20, y))
            y += 34
            for key, words in engine.ht_tables[self.tid]["options"]:
                r = pygame.Rect(box.x + 20, y, box.w - 40, 42)
                hover = r.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, ROW_HI if hover else ROW, r, border_radius=6)
                t = self.font.render(words, True, WHITE)
                surface.blit(t, (r.x + 16, r.centery - t.get_height() // 2))
                self.hits.append((r, "talk", key))
                y += 50
            return
        surface.blit(self.font.render(f"You told them: “{given['words_said']}”", True, WHITE), (box.x + 20, y))
        y += 32
        react = given["react"]
        n = len(react) or 1
        good = sum(1 for d in react.values() if d >= 0.8)
        head = ("That went down well - they're up for the second half." if good / n >= 0.6 else
                "A mixed reaction." if good / n >= 0.3 else "That didn't really land.")
        surface.blit(self.font.render(head, True, GREY), (box.x + 20, y))
        y += 34
        nm = self._names(engine)
        rows = sorted(react.items(), key=lambda kv: -kv[1])
        per = max(1, (box.bottom - 80 - y) // 22)
        colw = (box.w - 40) // 2
        surnames = [nm.get(pid, "?").split(" ")[-1] for pid, _ in rows]
        for i, (pid, d) in enumerate(rows[:per * 2]):
            cx, cy = box.x + 20 + (i // per) * colw, y + (i % per) * 22
            word = given["words"].get(pid, "")
            col = GREEN if d >= 0.8 else RED if d <= -0.6 else GREY
            full = nm.get(pid, "?")
            name = full.split(" ")[-1]
            if surnames.count(name) > 1:
                name = f"{full[0]}. {name}"
            surface.blit(self.small.render(name, True, WHITE), (cx, cy))
            t = self.small.render(word, True, col)
            surface.blit(t, (cx + colw - 30 - t.get_width(), cy))
        r = pygame.Rect(box.right - 260, box.bottom - 60, 240, 44)
        pygame.draw.rect(surface, BTN, r, border_radius=6)
        t = self.font.render("Start the second half", True, WHITE)
        surface.blit(t, (r.centerx - t.get_width() // 2, r.centery - t.get_height() // 2))
        self.hits.append((r, "go", None))

    def click(self, pos, engine):
        for r, action, data in self.hits:
            if r.collidepoint(pos):
                if action == "talk" and engine.ht_given is None:
                    engine.give_ht_talk(self.tid, data, by="you")
                elif action == "go":
                    self.close(engine)
                return

    def close(self, engine):
        engine.ht_panel = None
        from config.constants import HALFTIME_DURATION
        engine.ht_elapsed = HALFTIME_DURATION            # straight into the second half
