import pygame
from config.constants import *
from core.utils import grid_cell_from_position

# Action names matching ai/rl_agent.py NUM_ACTIONS order
_RL_ACTION_NAMES = [
    "hold role", "press", "mark", "drop",
    "pass best", "clear", "hold ball", "pass GK",
]


# The score/clock bar and the possession bar sit ABOVE the pitch (they used
# to be drawn over the top of it), and the legend sits below it.
TOP_UI = 56
BOTTOM_UI = 24


class UIRenderer:
    def __init__(self):
        self.normal_font = pygame.font.SysFont("Arial", FONT_SIZE_NORMAL)
        self.large_font  = pygame.font.SysFont("Arial", FONT_SIZE_LARGE)
        self.huge_font   = pygame.font.SysFont("Arial", 48, bold=True)
        self.med_font    = pygame.font.SysFont("Arial", 20, bold=True)
        self.small_font  = pygame.font.SysFont("Arial", 13)

    # ------------------------------------------------------------------
    # Main UI entry point
    # ------------------------------------------------------------------

    def draw_ui(self, surface, score, current_time, ball, match_info=None):
        """Draw all HUD elements. `match_info` comes from MatchEngine._build_match_info()."""
        if match_info is None:
            match_info = {
                "half_label": "1ST", "game_minute": 1,
                "possession": [50, 50], "shots_on_target": [0, 0],
            }

        # `surface` is the whole window; the pitch is drawn in the area between
        # the top bars and the legend (see MatchEngine).  The RL panel is drawn
        # on the pitch area by the engine.
        self._draw_top_bar(surface, score, match_info)
        self._draw_stats_bar(surface, match_info, ball)
        self._draw_legend(surface)

    # ------------------------------------------------------------------
    # Top bar: score + clock + half label
    # ------------------------------------------------------------------

    def _draw_top_bar(self, surface, score, mi):
        half_label  = mi["half_label"]
        game_minute = mi["game_minute"]

        # Background strip
        bar_rect = pygame.Rect(0, 0, WIDTH + FIELD_MARGIN * 2, 34)
        pygame.draw.rect(surface, (20, 20, 20), bar_rect)

        # Half label  (left)
        half_col = (80, 200, 80) if half_label in ("1ST", "2ND") else (220, 200, 60)
        half_surf = self.med_font.render(half_label, True, half_col)
        surface.blit(half_surf, (12, 7))

        # Clock  (just right of half label)
        clock_str  = f"{game_minute}'"
        clock_surf = self.med_font.render(clock_str, True, WHITE)
        surface.blit(clock_surf, (60, 7))

        # Watching speed (+ / - to change)
        speed = mi.get("speed")
        if speed:
            sp_surf = self.normal_font.render(f"{speed}x", True, (150, 200, 255))
            surface.blit(sp_surf, (60 + clock_surf.get_width() + 12, 10))

        # Score  (centre)
        score_str  = f"{score[0]}  –  {score[1]}"
        score_surf = self.large_font.render(score_str, True, WHITE)
        sx         = (WIDTH + FIELD_MARGIN * 2) // 2 - score_surf.get_width() // 2
        surface.blit(score_surf, (sx, 4))

        # Team labels flanking the score
        blue_surf = self.normal_font.render(mi.get("home_name", "Blue"), True, BLUE)
        red_surf  = self.normal_font.render(mi.get("away_name", "Red"),  True, RED)
        surface.blit(blue_surf, (sx - blue_surf.get_width() - 8, 10))
        surface.blit(red_surf,  (sx + score_surf.get_width() + 8, 10))

        # Keys reminder (right)
        keys_text = "SPACE pause  +/- speed  D overlay" + ("  S subs" if mi.get("can_sub") else "") \
            + ("" if mi.get("career") else "  R reset")
        keys_surf = self.normal_font.render(keys_text, True, (140, 140, 140))
        surface.blit(keys_surf, (WIDTH + FIELD_MARGIN * 2 - keys_surf.get_width() - 8, 10))

    # ------------------------------------------------------------------
    # Stats bar: possession + shots-on-target + ball position
    # ------------------------------------------------------------------

    def _draw_stats_bar(self, surface, mi, ball):
        poss = mi["possession"]            # [blue%, red%]
        sot  = mi["shots_on_target"]       # [blue, red]

        bar_y = 34

        # Possession bar background
        bar_w     = WIDTH + FIELD_MARGIN * 2
        bar_rect  = pygame.Rect(0, bar_y, bar_w, 22)
        pygame.draw.rect(surface, (40, 40, 40), bar_rect)

        # Blue portion
        blue_w = int(bar_w * poss[0] / 100)
        pygame.draw.rect(surface, (40, 80, 140), pygame.Rect(0, bar_y, blue_w, 22))
        # Red portion (right)
        red_w = bar_w - blue_w
        pygame.draw.rect(surface, (140, 50, 50), pygame.Rect(blue_w, bar_y, red_w, 22))

        # Divider
        pygame.draw.line(surface, (200, 200, 200), (blue_w, bar_y), (blue_w, bar_y + 22), 2)

        # Possession text
        poss_str  = f"Poss  {poss[0]}%  |  {poss[1]}%"
        poss_surf = self.normal_font.render(poss_str, True, (230, 230, 230))
        px = bar_w // 2 - poss_surf.get_width() // 2
        surface.blit(poss_surf, (px, bar_y + 4))

        # Shots on target (left)
        sot_str  = f"Shots on target:  {sot[0]}"
        sot_surf = self.normal_font.render(sot_str, True, (200, 220, 255))
        surface.blit(sot_surf, (10, bar_y + 4))

        # Shots on target (right) — right-aligned
        sot_str2  = f"{sot[1]}  :on target"
        sot_surf2 = self.normal_font.render(sot_str2, True, (255, 190, 190))
        surface.blit(sot_surf2, (bar_w - sot_surf2.get_width() - 10, bar_y + 4))

    # ------------------------------------------------------------------
    # Bottom legend
    # ------------------------------------------------------------------

    def _draw_legend(self, surface):
        legend_y   = surface.get_height() - BOTTOM_UI
        pygame.draw.rect(surface, (20, 20, 20), pygame.Rect(0, legend_y, surface.get_width(), BOTTOM_UI))
        legend_y  += 4
        legend_str = "States: press / dribble / pass / drive / support / chase / guard / tackle"
        legend_surf = self.normal_font.render(legend_str, True, (100, 100, 100))
        surface.blit(legend_surf, (12, legend_y))

    # ------------------------------------------------------------------
    # RL agent mini-panel (bottom-right, above legend)
    # ------------------------------------------------------------------

    def _draw_rl_panel(self, surface, mi):
        """Compact HUD panel showing Neo's Q-learning stats."""
        agent  = mi["rl_agent"]
        player = mi.get("rl_player")

        # ── Data ─────────────────────────────────────────────────────
        pts        = agent.total_points
        eps        = agent.epsilon
        q_states   = len(agent.q_table)
        matches    = agent.matches_played
        last_act   = _RL_ACTION_NAMES[agent.last_action] if 0 <= agent.last_action < len(_RL_ACTION_NAMES) else "?"
        name       = player.name if player else agent.player_name

        lines = [
            (f"\u2605 {name}  (LCB · RL)",  (255, 220, 60)),   # gold header
            (f"Pts   {pts:+.0f}",           (255, 255, 140) if pts >= 0 else (255, 100, 100)),
            (f"\u03b5     {eps:.3f}",        (120, 220, 120)),
            (f"States  {q_states}",          (160, 200, 255)),
            (f"Matches  {matches}",          (180, 180, 180)),
            (f"\u2192  {last_act}",          (200, 200, 200)),
        ]

        pad      = 7
        line_h   = 16
        panel_w  = 170
        panel_h  = pad * 2 + line_h * len(lines)

        total_w  = WIDTH + FIELD_MARGIN * 2
        total_h  = HEIGHT + FIELD_MARGIN * 2
        legend_h = 22    # height reserved for the legend bar at the very bottom
        px       = total_w - panel_w - 10
        py       = total_h - legend_h - panel_h - 4

        # Background
        bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        bg.fill((10, 10, 30, 200))
        surface.blit(bg, (px, py))

        # Border
        pygame.draw.rect(surface, (80, 80, 160), (px, py, panel_w, panel_h), 1)

        # Text rows
        for i, (text, colour) in enumerate(lines):
            surf = self.small_font.render(text, True, colour)
            surface.blit(surf, (px + pad, py + pad + i * line_h))

    # ------------------------------------------------------------------
    # Overlay screens
    # ------------------------------------------------------------------

    def draw_match_event_overlay(self, surface, match_state, score, names=("Blue", "Red"), career=False, extra=None):
        """Semi-transparent overlay for HALF TIME and FULL TIME."""
        overlay = pygame.Surface(
            (WIDTH + FIELD_MARGIN * 2, HEIGHT + FIELD_MARGIN * 2), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        cx = (WIDTH + FIELD_MARGIN * 2) // 2
        cy = (HEIGHT + FIELD_MARGIN * 2) // 2

        if match_state == "halftime":
            title = "HALF TIME"
            sub   = "2nd half starting shortly…"
        elif match_state in ("et_break", "et_halftime"):
            title = "EXTRA TIME" if match_state == "et_break" else "EXTRA TIME - HALF TIME"
            sub   = "Starting shortly…"
        else:   # full_time
            title = "FULL TIME"
            after = "Press ENTER to continue" if career else "Press R to replay"
            if score[0] > score[1]:
                sub = f"{names[0]} win  {score[0]} – {score[1]}  ·  {after}"
            elif score[1] > score[0]:
                sub = f"{names[1]} win  {score[1]} – {score[0]}  ·  {after}"
            else:
                sub = f"Draw  {score[0]} – {score[1]}  ·  {after}"

        title_surf = self.huge_font.render(title, True, WHITE)
        score_surf = self.large_font.render(f"{score[0]}  –  {score[1]}", True, YELLOW)
        sub_surf   = self.normal_font.render(sub, True, (180, 180, 180))

        surface.blit(title_surf, (cx - title_surf.get_width() // 2, cy - 60))
        surface.blit(score_surf, (cx - score_surf.get_width() // 2, cy))
        surface.blit(sub_surf,   (cx - sub_surf.get_width() // 2,   cy + 48))
        if extra:
            ex = self.med_font.render(extra, True, YELLOW)
            surface.blit(ex, (cx - ex.get_width() // 2, cy + 78))

    def draw_paused_message(self, surface):
        overlay = pygame.Surface(
            (WIDTH + FIELD_MARGIN * 2, HEIGHT + FIELD_MARGIN * 2), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 120))
        surface.blit(overlay, (0, 0))
        cx   = (WIDTH + FIELD_MARGIN * 2) // 2
        cy   = (HEIGHT + FIELD_MARGIN * 2) // 2
        surf = self.large_font.render("PAUSED  –  SPACE to resume", True, WHITE)
        surface.blit(surf, (cx - surf.get_width() // 2, cy - surf.get_height() // 2))

    def draw_offside_message(self, surface):
        surf = self.large_font.render("OFFSIDE!", True, (255, 60, 60))
        cx   = (WIDTH + FIELD_MARGIN * 2) // 2
        surface.blit(surf, (cx - surf.get_width() // 2, HEIGHT // 2 - 50 + FIELD_MARGIN))

    def draw_foul_message(self, surface):
        """Show 'FOUL!' banner in the centre of the pitch."""
        surf = self.large_font.render("FOUL!", True, (255, 200, 0))
        cx   = (WIDTH + FIELD_MARGIN * 2) // 2
        surface.blit(surf, (cx - surf.get_width() // 2, HEIGHT // 2 - 30 + FIELD_MARGIN))

    def draw_card_flash(self, surface, card_type, player_name):
        """
        Flash a card notification: coloured card rectangle + player name.
        Appears above the 'FOUL!' banner so both can be visible at once.
        """
        if card_type in ("yellow", "second_yellow"):
            card_col  = (255, 220, 0)
            label_col = (0, 0, 0)
            card_label = "YELLOW CARD" if card_type == "yellow" else "2ND YELLOW → RED"
        else:
            card_col   = (200, 20, 20)
            label_col  = (255, 255, 255)
            card_label = "RED CARD"

        cx = (WIDTH + FIELD_MARGIN * 2) // 2
        cy = HEIGHT // 2 + FIELD_MARGIN - 90

        card_w, card_h = 180, 64
        rect = pygame.Rect(cx - card_w // 2, cy, card_w, card_h)
        pygame.draw.rect(surface, card_col,   rect, border_radius=6)
        pygame.draw.rect(surface, (0, 0, 0), rect, 2, border_radius=6)

        lbl_surf = self.med_font.render(card_label, True, label_col)
        surface.blit(lbl_surf, (cx - lbl_surf.get_width() // 2, cy + 6))

        name_surf = self.normal_font.render(player_name, True, label_col)
        surface.blit(name_surf, (cx - name_surf.get_width() // 2, cy + 36))

    def draw_sub_flash(self, surface, text, team, row=0, kind="sub"):
        """A substitution: a green board with who's going off and who's coming on."""
        surf = self.med_font.render(text, True, WHITE)
        w, h = surf.get_width() + 36, surf.get_height() + 16
        cx = (WIDTH + FIELD_MARGIN * 2) // 2
        y = HEIGHT + FIELD_MARGIN - h - 14 - row * (h + 6)
        rect = pygame.Rect(cx - w // 2, y, w, h)
        pygame.draw.rect(surface, (20, 110, 50) if kind == "sub" else (150, 90, 20), rect, border_radius=6)
        pygame.draw.rect(surface, BLUE if team == 0 else RED, rect, 3, border_radius=6)
        surface.blit(surf, (cx - surf.get_width() // 2, y + 8))

    # Kept for backward compatibility (match_engine no longer calls this directly)
    def draw_winner_message(self, surface, score, first_to):
        pass
