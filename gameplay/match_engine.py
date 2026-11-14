import gameplay.aerial as aerial
import pygame
import random
from pygame.math import Vector2
from config.constants import *
from core.game_objects import Ball
from config.formations import spawn_team
from ai.decision_maker import AIDecisionMaker
from rendering.pitch_renderer import PitchRenderer
from rendering.object_renderer import ObjectRenderer
from rendering.ui_renderer import UIRenderer
from gameplay.mechanics import GameMechanics
from gameplay.offside import OffsideSystem
from gameplay.cards import apply_card, reset_cards
import core.fatigue as fatigue
import core.locomotion as locomotion
from ai.rl_agent import RLAgent
from ai.rl_messi_agent import RLMessiAgent
from ai.rl_messi_actions import execute_messi_action
import core.clock as game_clock
import core.world as world


class MatchEngine:
    def __init__(self, career=False):
        # career=True: played from the manager game (career/ui.py) - at full
        # time it hands back to the manager screens instead of offering a replay
        self.career = career
        self.quit_requested = False      # the window was closed (career mode)
        self.goal_events = []            # [{team, name, minute, own_goal}]
        # Initialize pygame
        pygame.init()
        # The window has the score / possession bars above the pitch and the
        # legend below it; self.screen is the pitch area inside the window.
        from rendering.ui_renderer import TOP_UI, BOTTOM_UI
        self.window = pygame.display.set_mode(
            (WIDTH + FIELD_MARGIN*2, HEIGHT + FIELD_MARGIN*2 + TOP_UI + BOTTOM_UI))
        self.screen = self.window.subsurface(
            pygame.Rect(0, TOP_UI, WIDTH + FIELD_MARGIN*2, HEIGHT + FIELD_MARGIN*2))
        pygame.display.set_caption("11v11 Football Simulation - Pro Version")
        self.clock = pygame.time.Clock()

        # Initialize systems
        self.ai = AIDecisionMaker()
        self.pitch_renderer = PitchRenderer()
        self.object_renderer = ObjectRenderer()
        self.ui_renderer = UIRenderer()
        self.mechanics = GameMechanics()
        self.offside_system = OffsideSystem()

        # Initialize game state
        self.team0 = spawn_team(0)
        self.team1 = spawn_team(1)
        self.ball = Ball(Vector2(WIDTH/2, HEIGHT/2))
        world.players = self.team0 + self.team1
        world.ball = self.ball
        # Substitutes and the sub rules (gameplay/substitutions.py)
        import config.formations as formations
        from gameplay.substitutions import Substitutions
        self.subs = Substitutions(self, formations.db)
        self.my_team = next((t for t in (0, 1) if formations.db.human.get(t)), None)
        self.sub_panel = None             # rendering/sub_panel.py while it's open
        # Half-time team talk (career matches: career/teamtalk.py makes the table)
        self.ht_tables = {t: (getattr(formations.db, "ht_talk", {}) or {}).get(t) for t in (0, 1)}
        self.ht_panel = None              # rendering/ht_panel.py while you choose
        self.ht_given = None              # what was said, for the result
        # A knockout tie this match decides (career cups / play-offs): level at the end - extra time, then
        # penalties (gameplay/shootout.py).  {"agg": [home, away]} = the goals from earlier legs.
        self.knockout = getattr(formations.db, "knockout", None)
        self.score_90 = None              # the score after 90 minutes, once extra time starts
        self.shootout = None
        self.final_minute = 90

        # ── Learning players (Neo + Messi) ───────────────────────────────────
        # Off by default: set RL_ENABLED = True in config/constants.py to use them.
        self.rl_agent = self.rl_player = None
        self.messi_agent = self.messi_player = None
        if RL_ENABLED:
            # ── RL agent: tag team-0's LCB ───────────────────────────────────────
            self.rl_agent  = RLAgent(team_id=0, player_name="Neo")
            self.rl_player = next(
                (p for p in self.team0 if p.role == "LCB"), None
            )
            if self.rl_player:
                self.rl_player.rl_agent = self.rl_agent
                self.rl_player.name     = "Neo"   # visible on the pitch
                print(f"[RL] Agent 'Neo' attached to {self.rl_player.role} (team 0)")
            else:
                print("[RL] Warning: no LCB found on team 0")

            # ── RL agent: tag team-0's ST1 as Messi ──────────────────────────────
            self.messi_agent  = RLMessiAgent(team_id=0, player_name="Messi")
            self.messi_agent.execute_fn = execute_messi_action   # attacker action set
            self.messi_player = next(
                (p for p in self.team0 if p.role == "ST1"), None
            )
            if self.messi_player:
                self.messi_player.rl_agent = self.messi_agent
                self.messi_player.name     = "Messi"
                # Override attributes with elite attacking stats (1-20 scale)
                self.messi_player.attributes.update({
                    "Pace":       16,
                    "Finishing":  20,
                    "Passing":    20,
                    "Dribbling":  20,
                    "Control":    20,
                    "Composure":  20,
                    "Physical":   13,
                    "Tackling":    4,
                    "Defending":   3,
                    "Teamwork":   18,
                })
                # Initialise shot-tracking flag
                self.messi_player.last_action_was_shot = False
                print(f"[RL] Agent 'Messi' attached to {self.messi_player.role} (team 0)")
            else:
                print("[RL] Warning: no ST1 found on team 0")

        self.score = [0, 0]
        self.running = True
        self.paused = False
        self.match_speed = DEFAULT_MATCH_SPEED     # watching speed (+ / - to change)
        self.time_elapsed = 0.0
        game_clock.set_time(0.0)

        # ── Match structure ───────────────────────────────────────────────
        # States: "first_half" | "halftime" | "second_half" | "full_time"
        self.match_state    = "first_half"
        self.half_elapsed   = 0.0   # time into the CURRENT half (real seconds)
        self.ht_elapsed     = 0.0   # time spent showing the half-time screen

        # ── Statistics ───────────────────────────────────────────────────
        self.possession_frames = [0, 0]   # frames each team had the ball
        self.shots             = [0, 0]   # total shots
        self.shots_on_target   = [0, 0]   # saved + goals

        # ── RL per-step tracking ──────────────────────────────────────────
        self._prev_ball_owner  = None     # used to detect when Neo wins the ball

        # Messi per-step tracking
        self._prev_messi_had_ball   = False   # did Messi own the ball last frame?
        self._messi_nearby_defs     = set()   # IDs of defenders near Messi last frame
        self._tracked_last_toucher  = None    # for prev_toucher (assist detection)

        # ── Foul / card display state ─────────────────────────────────────
        self._foul_display_until = 0.0   # time_elapsed when "FOUL!" banner expires
        self._card_display       = None  # dict: {type, name, until} or None

        self._initialize_game()

    # ------------------------------------------------------------------
    # Startup / reset helpers
    # ------------------------------------------------------------------

    def _initialize_game(self):
        """Proper kick-off to start the match."""
        self._kickoff()

    def _kickoff(self, conceding_team_id=None):
        """
        Start of a half (or a fresh match): everyone out on his kick-off spot
        (both strikers of the kicking team on the ball, the other team outside
        the circle) and kick off after a moment.
        """
        import gameplay.set_pieces as set_pieces
        self.mechanics.reset_game(self.team0, self.team1, self.ball, self.ai)
        self.offside_system.offside_detected = False
        if conceding_team_id is not None:
            kicking_team = self.team1 if conceding_team_id == 0 else self.team0
        else:
            kicking_team = random.choice([self.team0, self.team1])
            self._first_kickoff = kicking_team[0].team   # the other team kicks off the 2nd half
        taker = self._kickoff_taker(kicking_team)
        if taker is None:
            return
        for team in (self.team0, self.team1):
            spots = set_pieces.kickoff_spots(team[0].team, team is kicking_team, taker.slot)
            for p in team:
                if p.slot in spots and getattr(p, "is_active", True):
                    p.pos = Vector2(spots[p.slot])
                    p.target = Vector2(p.pos)
                    p.vel = Vector2(0, 0)
        self._set_kickoff(taker, celebration=None)

    def _kickoff_taker(self, team):
        field = [p for p in team if p.role != "GK" and getattr(p, "is_active", True)]
        if not field:
            return None
        for role in ("ST1", "ST2"):
            st = next((p for p in field if p.role == role), None)
            if st is not None:
                return st
        return min(field, key=lambda p: (p.pos - Vector2(WIDTH / 2, HEIGHT / 2)).length())

    def _set_kickoff(self, taker, celebration):
        b = self.ball
        b.pos = Vector2(WIDTH / 2, HEIGHT / 2)
        b.vel = Vector2(0, 0)
        b.z = 0
        b.vz = 0
        b.owner = None
        b.is_dead = True
        b.restart_type = "kick_off"
        b.restart_taker = taker
        b.restart_time = self.time_elapsed
        b._celebration = celebration
        for p in self.team0 + self.team1:
            p.has_ball = False
        self.ai.last_possession_team = taker.team

    def _reset_match(self):
        """R-key: wipe score, stats and start a fresh match."""
        self.score             = [0, 0]
        self.match_state       = "first_half"
        self.half_elapsed      = 0.0
        self.ht_elapsed        = 0.0
        self.possession_frames = [0, 0]
        self.shots             = [0, 0]
        self.shots_on_target   = [0, 0]
        # NOTE: time_elapsed is deliberately NOT reset to 0 here.  Players and
        # the ball store timestamps (last pass, last tackle, restart time...)
        # and rewinding the clock made them look like they were in the future,
        # so after pressing R players froze in "hold" and tackles were blocked.
        # Reset Messi tracking state
        self._prev_messi_had_ball  = False
        self._messi_nearby_defs    = set()
        self._tracked_last_toucher = None
        if self.messi_player:
            self.messi_player.last_action_was_shot = False
        # Reset cards for all players
        reset_cards(self.team0)
        reset_cards(self.team1)
        # Fresh legs for a new match (not after goals - fatigue builds all game)
        for p in self.team0 + self.team1:
            fatigue.init(p)
        # Clear any pending foul / card UI
        self._foul_display_until = 0.0
        self._card_display       = None
        self._kickoff()

    # ------------------------------------------------------------------
    # Match-state transitions
    # ------------------------------------------------------------------

    def _start_halftime(self):
        self.match_state  = "halftime"
        self.ht_elapsed   = 0.0
        self.ball.vel     = Vector2(0, 0)
        self.ball.owner   = None
        self.ball.is_dead = True        # freeze ball during the HT screen
        for tid in (0, 1):              # the team talk: you choose (watching), else your assistant does
            tab = self.ht_tables.get(tid)
            if not tab:
                continue
            if tid == self.my_team:
                from rendering.ht_panel import HTPanel
                self.ht_panel = HTPanel(tid)
            else:
                self.give_ht_talk(tid, tab["pick"][self.ht_state(tid)], by="assistant")

    def ht_state(self, tid):
        m = self.score[tid] - self.score[1 - tid]
        return "up2" if m >= 2 else "up1" if m == 1 else "level" if m == 0 else "down1" if m == -1 else "down2"

    def give_ht_talk(self, tid, key, by="you"):
        """The talk lands: each man's second half moves with how he took it (1-20 scale)."""
        tab = self.ht_tables[tid]
        state = self.ht_state(tid)
        team = self.team0 if tid == 0 else self.team1
        here = {str(getattr(p, "pid", None)) for p in team} | {str(b["id"]) for b in self.subs.bench[tid]}
        react = {pid: d for pid, d in tab["react"][state][key].items() if pid in here}   # (the matchday squad)
        bad = (tab.get("bad") or {}).get(state, {}).get(key, {})
        eff = tab.get("effect", {})
        for p in team:
            d = react.get(str(getattr(p, "pid", None)))
            if d:
                for attr, k in eff.items():
                    p.attributes[attr] = max(1.0, min(20.0, p.attributes.get(attr, 10) + k * d))
        for b in self.subs.bench[tid]:
            d = react.get(str(b["id"]))
            if d and not b.get("used"):
                b["row"] = row = dict(b["row"])
                for attr, k in eff.items():
                    if attr in row:
                        row[attr] = int(max(5, min(100, round(float(row[attr]) + 5 * k * d))))
        words = {}
        for pid, d in react.items():
            w = bad.get(pid)
            words[pid] = (w if (w and d <= -0.6) else "Fired up" if d >= 2.0 else "Motivated" if d >= 0.8 else
                          "No change" if d > -0.6 else (w or "Unhappy"))
        self.ht_given = {"team": tid, "key": key, "by": by, "state": state, "react": dict(react), "words": words,
                         "words_said": dict(tab["options"]).get(key, key)}
        return self.ht_given

    def _start_second_half(self):
        self.match_state  = "second_half"
        self.half_elapsed = 0.0
        fatigue.half_time(self.team0 + self.team1)     # a breather at half-time
        self.subs.half_time(self.time_elapsed)          # changes at the break
        # The team that kicked off the first half doesn't kick off the second
        self._kickoff(conceding_team_id=getattr(self, "_first_kickoff", None))

    # --- Extra time and penalties (knockout ties only) ------------------------------------------------
    def _tie_level(self):
        if not self.knockout:
            return False
        agg = self.knockout.get("agg") or [0, 0]
        return self.score[0] + agg[0] == self.score[1] + agg[1]

    def _stop_ball(self):
        self.ball.vel = Vector2(0, 0)
        self.ball.owner = None
        self.ball.is_dead = True

    def _start_et_break(self):
        """Level after 90 minutes: a short break, then 2 x 15 minutes.  (IFAB: one more substitution, and one
        more window, in extra time.)"""
        self.match_state = "et_break"
        self.ht_elapsed = 0.0
        self.score_90 = list(self.score)
        self.final_minute = 120
        self._stop_ball()
        if not self.subs.friendly:
            self.subs.max_subs += 1
            self.subs.max_windows += 1

    def _start_et_halftime(self):
        self.match_state = "et_halftime"
        self.ht_elapsed = 0.0
        self._stop_ball()

    def _start_et_half(self, which):
        self.match_state = which
        self.half_elapsed = 0.0
        self.subs.half_time(self.time_elapsed, 91 if which == "et_first" else 106)   # (changes at the break)
        if which == "et_first":
            self._kickoff()                             # a new toss
            self._et_kickoff = getattr(self, "_first_kickoff", 0)
        else:
            self._kickoff(conceding_team_id=getattr(self, "_et_kickoff", 0))

    def _start_penalties(self):
        from gameplay.shootout import Shootout
        self.match_state = "penalties"
        self._stop_ball()
        self.subs.messages.clear()                      # (no substitution boards over the shoot-out)
        self.shootout = Shootout(self)

    def _start_fulltime(self):
        self.match_state  = "full_time"
        self.ball.vel     = Vector2(0, 0)
        self.ball.owner   = None
        self.ball.is_dead = True

        # ── RL match-outcome rewards ──────────────────────────────────────────
        # Neo (CB)
        if self.rl_agent:
            our_goals = self.score[self.rl_agent.team_id]
            opp_goals = self.score[1 - self.rl_agent.team_id]
            if our_goals > opp_goals:
                print(f"[RL] Match WON {our_goals}-{opp_goals}! +10")
                self.rl_agent.end_match(+10)
            elif our_goals < opp_goals:
                print(f"[RL] Match LOST {our_goals}-{opp_goals}! -10")
                self.rl_agent.end_match(-10)
            else:
                print(f"[RL] Match DRAWN {our_goals}-{opp_goals}. +0")
                self.rl_agent.end_match(0)

        # Messi (ST1) — ±5 for win/loss, 0 for draw
        if self.messi_agent:
            m_goals = self.score[self.messi_agent.team_id]
            m_opp   = self.score[1 - self.messi_agent.team_id]
            if m_goals > m_opp:
                print(f"[RLMessi] Match WON {m_goals}-{m_opp}! +5")
                self.messi_agent.end_match(+5)
            elif m_goals < m_opp:
                print(f"[RLMessi] Match LOST {m_goals}-{m_opp}! -5")
                self.messi_agent.end_match(-5)
            else:
                print(f"[RLMessi] Match DRAWN {m_goals}-{m_opp}. +0")
                self.messi_agent.end_match(0)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        while self.running:
            # Cap the frame step so a stall (e.g. dragging the window) can't
            # teleport players/ball through each other.
            delta_time = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self._handle_events()
            if self.subs.ask is not None and self.sub_panel is None:
                # One of your players is injured: stop and let you choose his replacement
                from rendering.sub_panel import SubPanel
                hurt, self.subs.ask = self.subs.ask, None
                self.sub_panel = SubPanel()
                if getattr(hurt, "is_active", True):
                    self.sub_panel.selected = hurt
                    self.sub_panel.notice = (f"{hurt.name} is injured and has to come off - pick his replacement "
                                             f"(or close this and he limps on)")
            if self.sub_panel is not None:
                self._render(flip=False)
                self.sub_panel.draw(self.window, self)
                pygame.display.flip()
                continue
            if self.ht_panel is not None:                   # half-time: the match waits for your talk
                self._render(flip=False)
                self.ht_panel.draw(self.window, self)
                pygame.display.flip()
                continue
            if self.paused:
                # Game clock is frozen while paused (it used to keep running,
                # so restart timers and cooldowns ran down during a pause).
                self._render_paused()
                continue
            # The football always runs in fixed 1/60 s steps (exactly like
            # sim.py); watching at 8x just plays 8 steps per drawn frame.
            # (Half-time / full-time screens stay at normal speed.)
            playing = ("first_half", "second_half", "et_first", "et_second")
            steps = (self.match_speed if self.match_state in playing else
                     min(2, self.match_speed) if self.match_state == "penalties" else 1)
            for _ in range(steps):
                self.step(1.0 / FPS)
                if self.match_state not in playing and self.match_state != "penalties":
                    break
            self._render()
        if not self.career:
            pygame.quit()

    def step(self, delta_time):
        """Advance the match by one frame.  Used by run() and by sim.py (headless)."""
        world.players = self.team0 + self.team1
        world.ball = self.ball
        self.time_elapsed += delta_time
        game_clock.set_time(self.time_elapsed)
        self._update_game(delta_time)

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                self.quit_requested = True
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.sub_panel is not None:
                self.sub_panel.click(event.pos, self)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.ht_panel is not None:
                self.ht_panel.click(event.pos, self)
            elif event.type == pygame.KEYDOWN and self.ht_panel is not None and \
                    event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.ht_given is not None:
                self.ht_panel.close(self)
            elif event.type == pygame.KEYDOWN and self.sub_panel is not None:
                if event.key in (pygame.K_s, pygame.K_ESCAPE):
                    self.sub_panel = None                # back to the match
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_s and self.my_team is not None and self.subs.active \
                        and self.match_state not in ("full_time", "penalties"):
                    from rendering.sub_panel import SubPanel
                    self.sub_panel = SubPanel()          # the match waits while it's open
                    continue
                if self.career and self.match_state == "full_time" and \
                        event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_ESCAPE):
                    self.running = False             # back to the manager screens
                    continue
                if event.key == pygame.K_SPACE:
                    self.paused = not self.paused
                if event.key == pygame.K_r and not self.career:
                    self._reset_match()
                if event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS, pygame.K_UP):
                    self._change_speed(+1)
                if event.key in (pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_DOWN):
                    self._change_speed(-1)
                if event.key == pygame.K_d:
                    # Positioning debug overlay: off -> both -> Blue -> Red
                    from rendering import debug_overlay
                    self.overlay_mode = debug_overlay.next_mode(getattr(self, "overlay_mode", "off"))

    def _change_speed(self, direction):
        speeds = list(MATCH_SPEEDS)
        cur = self.match_speed if self.match_speed in speeds else DEFAULT_MATCH_SPEED
        i = max(0, min(len(speeds) - 1, speeds.index(cur) + direction))
        self.match_speed = speeds[i]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def _update_game(self, delta_time):

        # ── Match-state gating ─────────────────────────────────────────
        if self.match_state == "halftime":
            if self.ht_panel is not None:
                return   # waiting for your half-time talk (rendering/ht_panel.py)
            self.ht_elapsed += delta_time
            if self.ht_elapsed >= HALFTIME_DURATION:
                self._start_second_half()
            return   # nothing else ticks during HT

        if self.match_state in ("et_break", "et_halftime"):
            self.ht_elapsed += delta_time
            if self.ht_elapsed >= HALFTIME_DURATION:
                self._start_et_half("et_first" if self.match_state == "et_break" else "et_second")
            return
        if self.match_state == "penalties":
            self.shootout.update(delta_time)
            if self.shootout.finished():
                self._start_fulltime()
            return

        if self.match_state == "full_time":
            return   # game frozen; press R to restart

        # Advance the in-half clock
        self.half_elapsed += delta_time

        # Check for end of each half
        if self.match_state == "first_half" and self.half_elapsed >= HALF_DURATION_REAL:
            self._start_halftime()
            return
        if self.match_state == "second_half" and self.half_elapsed >= HALF_DURATION_REAL:
            if self._tie_level():
                self._start_et_break()                  # (a knockout tie, still level: extra time)
            else:
                self._start_fulltime()
            return
        if self.match_state in ("et_first", "et_second") and self.half_elapsed >= HALF_DURATION_REAL / 3.0:
            if self.match_state == "et_first":
                self._start_et_halftime()
            elif self._tie_level():
                self._start_penalties()
            else:
                self._start_fulltime()
            return

        # ── Possession counter ─────────────────────────────────────────
        if self.ball.owner is not None:
            self.possession_frames[self.ball.owner.team] += 1

        # ── Normal game update ─────────────────────────────────────────
        # Teams take turns deciding first, so neither side always gets to react
        # to the other's moves (Blue used to go first every single frame).
        self._blue_first = not getattr(self, "_blue_first", False)
        first, second = (self.team0, self.team1) if self._blue_first else (self.team1, self.team0)
        # Each team does its thinking every other frame (30 times a second),
        # the two teams taking turns.  Movement, the ball and duels still run
        # every frame.  (Thinking 60 times a second was more than half the
        # cost of simulating a match, for no real difference: players' own
        # decisions already run on human timing - tenths of a second.)
        self.ai.make_team_decisions(first, second, self.ball, self.time_elapsed, self.mechanics)

        _tackle_success, _foul_info = self.mechanics.handle_tackles(self.team0, self.team1, self.ball, self.time_elapsed)
        if _foul_info is not None:
            self._handle_foul(_foul_info)
        self.mechanics.handle_loose_balls(self.team0 + self.team1, self.ball)
        # A lofted ball: the right men go to where it's coming down (gameplay/aerial.py)
        aerial.update_movement(self.team0, self.team1, self.ball, self.time_elapsed)
        self.mechanics.update_goalkeeper_dive_states(self.team0, self.team1, self.time_elapsed)

        self.offside_system.check_offside(self.team0, self.team1, self.ball, self.time_elapsed)
        self.offside_system.check_offside(self.team1, self.team0, self.ball, self.time_elapsed)
        self.offside_system.update_reset_logic(self.team0, self.team1, self.ball, self.time_elapsed)

        # Same turn-taking for movement: whoever moves first in a collision
        # gets pushed differently, so alternate it too.
        all_players = (self.team0 + self.team1) if self._blue_first else (self.team1 + self.team0)
        # (Everyone's x, kept up to date as each one moves, so the body-contact
        # check in core/locomotion.py can skip far-apart pairs quickly)
        xs = [p.pos.x for p in all_players]
        locomotion.CONTACT_XS = (all_players, xs)
        try:
            for i, player in enumerate(all_players):
                player.update(delta_time, all_players=all_players)
                xs[i] = player.pos.x
        finally:
            locomotion.CONTACT_XS = None
        self.ball.update(delta_time, self.time_elapsed)

        # Headers and aerial challenges come first: a ball at head height is
        # contested in the air before anyone can bring it down (gameplay/aerial.py)
        _air_foul = aerial.resolve(self.team0, self.team1, self.ball, self.time_elapsed, self.ai)
        if _air_foul is not None:
            self._handle_foul(_air_foul)
        else:
            self.mechanics.handle_goalkeeper_interactions(self.team0, self.team1, self.ball, self.time_elapsed, self.ai)
            self.mechanics.handle_possession_pickup(self.team0, self.team1, self.ball, self.time_elapsed, self.ai)

        # ── RL per-step reward: Neo wins the ball ─────────────────────────
        # Fires once per possession-change event, not every frame, so it
        # doesn't drown out the goal-level rewards.
        if self.rl_player and self.rl_agent:
            if (self.ball.owner is self.rl_player
                    and self._prev_ball_owner is not self.rl_player):
                self.rl_agent.apply_reward(+1.0)
        self._prev_ball_owner = self.ball.owner

        # ── Messi per-step reward hooks ───────────────────────────────────
        if self.messi_player and self.messi_agent:
            from core.utils import distance
            from config.constants import M_TO_PX

            _messi_owns = (self.ball.owner is self.messi_player)
            _prev_owned = self._prev_messi_had_ball

            # Turnover / successful pass detection (fires once per event)
            if _prev_owned and not _messi_owns:
                if self.ball.owner is not None:
                    if self.ball.owner.team == self.messi_player.team:
                        self.messi_agent.apply_reward(+0.5)
                        print("[RLMessi] Successful pass! +0.5")
                    else:
                        self.messi_agent.apply_reward(-2.0)
                        print("[RLMessi] Turnover! -2")
                # If ball.owner is None it's a loose ball — no reward either way

            # Successful dribble: defender was within 3 m last frame but
            # is now >4 m away AND Messi still has the ball
            if _messi_owns and _prev_owned:
                opp_field = [o for o in self.team1 if o.role != "GK"]
                cur_near  = {
                    id(o) for o in opp_field
                    if distance(self.messi_player.pos, o.pos) < 4.0 * M_TO_PX
                }
                beaten = self._messi_nearby_defs - cur_near
                if beaten:
                    self.messi_agent.apply_reward(+1.0 * len(beaten))
                    print(f"[RLMessi] Dribbled past {len(beaten)} defender(s)! +{len(beaten)}")
                self._messi_nearby_defs = {
                    id(o) for o in opp_field
                    if distance(self.messi_player.pos, o.pos) < 3.0 * M_TO_PX
                }
            else:
                self._messi_nearby_defs = set()

            self._prev_messi_had_ball = _messi_owns

        # ── ball.prev_toucher tracking (for assist detection) ─────────────
        _cur_toucher = getattr(self.ball, 'last_toucher', None)
        if _cur_toucher is not self._tracked_last_toucher:
            self.ball.prev_toucher = self._tracked_last_toucher
            self._tracked_last_toucher = _cur_toucher

        # ── Messi offside reward ──────────────────────────────────────────
        if (self.messi_player and self.messi_agent
                and self.offside_system.offside_detected
                and self.offside_system.offside_player is self.messi_player):
            self.messi_agent.apply_reward(-1.0)
            print("[RLMessi] Offside! -1")

        # ── Goal & boundary checks ─────────────────────────────────────
        # Priority order:
        #   1. Goal (but not if offside is flagged — disallow the goal)
        #   2. Ball out of play — ALWAYS fires even during an offside window
        #      because the ball leaving the field cancels the offside call.
        _event_handled = False

        if not self.offside_system.offside_detected:
            goal_scorer = self.mechanics.check_goal(self.ball)
            if goal_scorer is not None:
                self.score[goal_scorer] += 1
                self._record_goal(goal_scorer)
                self.shots_on_target[goal_scorer] += 1
                self._reset_after_goal(goal_scorer)
                _event_handled = True

        if not _event_handled and self.mechanics.check_ball_out(self.ball):
            # ── Messi off-target shot detection ──────────────────────────
            # If Messi's last action was a shot and he was the last toucher,
            # the ball going out of play means it missed the target.
            if (self.messi_player and self.messi_agent
                    and getattr(self.messi_player, 'last_action_was_shot', False)
                    and getattr(self.ball, 'last_toucher', None) is self.messi_player):
                self.messi_agent.apply_reward(-1.0)
                print("[RLMessi] Shot off target! -1")
                self.messi_player.last_action_was_shot = False

            # Ball out: cancel any pending offside and restart play.
            self.offside_system.offside_detected = False
            self.offside_system.players_being_watched = []
            self.offside_system.last_pass_snapshot = None
            self.mechanics.resolve_out_of_play(
                self.ball,
                self.ai.last_possession_team,
                self.team0,
                self.team1,
                self.ai,
                self.time_elapsed
            )

        # ── Injuries, and substitutions (only ever at a stoppage) ─────────
        self.subs.injuries(delta_time, self.match_minute())
        self.subs.update(self.time_elapsed, self.match_minute())

    def _team_name(self, team):
        try:
            import config.formations as formations
            name = formations.db.home_team_name if team == 0 else formations.db.away_team_name
        except Exception:
            name = None
        if not name or name in ("Home", "Away", "Team Blue", "Team Red"):
            return "Blue" if team == 0 else "Red"
        return name

    def match_minute(self):
        if self.match_state in ("et_first", "et_second"):
            m = int(self.half_elapsed * 15.0 / (HALF_DURATION_REAL / 3.0)) + 1
            return min(105, 90 + m) if self.match_state == "et_first" else min(120, 105 + m)
        if self.match_state in ("et_break", "et_halftime", "penalties") or self.score_90 is not None:
            return {"et_break": 90, "et_halftime": 105}.get(self.match_state, 120)
        m = int(self.half_elapsed * 45.0 / HALF_DURATION_REAL) + 1
        return min(90, 45 + m) if self.match_state == "second_half" else min(45, m)

    def _record_goal(self, team):
        lt = getattr(self.ball, "last_toucher", None)
        own = lt is not None and lt.team != team
        self.goal_events.append({
            "team": team,
            "name": getattr(lt, "name", "?") if lt is not None else "?",
            "pid": getattr(lt, "pid", None) if lt is not None else None,
            "minute": self.match_minute(),
            "own_goal": own,
        })

    def result(self):
        """What the manager game needs from a finished match."""
        total = sum(self.possession_frames) or 1
        out = {}
        if self.score_90 is not None:               # (extra time: the 90-minute score + the extra-time goals)
            out["et"] = [self.score[0] - self.score_90[0], self.score[1] - self.score_90[1]]
            if self.shootout is not None:
                out["pens"] = self.shootout.score()
                out["pen_kicks"] = [list(k) for k in self.shootout.kicks]
        s = self.score_90 if self.score_90 is not None else self.score
        return {
            **out,
            "hg": s[0], "ag": s[1],
            "goals": list(self.goal_events),
            "possession": [round(100 * f / total) for f in self.possession_frames],
            "shots_on_target": list(self.shots_on_target),
            "subs": list(self.subs.log),
            "players": self.subs.finish(),
            "ht_talk": self.ht_given,
        }

    # ------------------------------------------------------------------
    # Post-goal reset
    # ------------------------------------------------------------------

    def _reset_after_goal(self, goal_scorer):
        conceding_team_id = 1 if goal_scorer == 0 else 0

        # ── Neo RL reward delivery ────────────────────────────────────────────
        if self.rl_player and self.rl_agent:
            if goal_scorer == self.rl_agent.team_id:
                personal = (self.ball.last_toucher is self.rl_player)
                if personal:
                    print(f"[RL] Neo scored! +5 personal, +5 team")
                    self.rl_agent.apply_reward(+5)   # personal goal
                else:
                    print(f"[RL] Team scored! +5")
                self.rl_agent.apply_reward(+5, clear=True)   # team goal
            else:
                print(f"[RL] Team conceded! -10")
                self.rl_agent.apply_reward(-10, clear=True)

        # ── Messi RL reward delivery ──────────────────────────────────────────
        if self.messi_player and self.messi_agent:
            last_t = getattr(self.ball, 'last_toucher',  None)
            prev_t = getattr(self.ball, 'prev_toucher',  None)
            if goal_scorer == self.messi_agent.team_id:
                if last_t is self.messi_player:
                    print("[RLMessi] Messi scored! +5")
                    self.messi_agent.apply_reward(+5, clear=True)
                elif (prev_t is self.messi_player
                      and last_t is not None
                      and last_t.team == self.messi_agent.team_id):
                    print("[RLMessi] Messi assisted! +3")
                    self.messi_agent.apply_reward(+3, clear=True)
            # No negative reward on concede here — that's handled via match result

            # Clear shot flag on any goal event
            self.messi_player.last_action_was_shot = False
            # Reset dribble tracking at kickoff
            self._prev_messi_had_ball = False
            self._messi_nearby_defs   = set()

        self._goal_restart(conceding_team_id)

    # Goal celebration (then both teams walk back - ai/decision_maker.py)
    CELEBRATION = (10.0, 16.0)     # s the scorer and his mates celebrate
    CELEBRATE_SPOT = 4.0           # m in from the corner flag he runs to

    def _goal_restart(self, conceding_team_id):
        """
        After a goal: no instant reset.  The scorer wheels away towards the
        corner flag and his teammates run over to join him, the other team
        trudges back; then everyone walks to his kick-off spot and the team
        that conceded kicks off (~45-60 s, as in real football).
        """
        self.offside_system.offside_detected = False
        scoring = 1 - conceding_team_id
        kicking_team = self.team0 if conceding_team_id == 0 else self.team1
        scoring_team = self.team1 if conceding_team_id == 0 else self.team0
        taker = self._kickoff_taker(kicking_team)
        if taker is None:
            self._kickoff(conceding_team_id)
            return
        for p in self.team0 + self.team1:
            if p.role == "GK":
                p.dive_state = "idle"
        scorer = getattr(self.ball, "last_toucher", None)
        if scorer is None or scorer.team != scoring or scorer.role == "GK" \
                or not getattr(scorer, "is_active", True):
            outfield = [p for p in scoring_team if p.role != "GK" and getattr(p, "is_active", True)]
            scorer = min(outfield, key=lambda p: (p.pos - self.ball.pos).length()) if outfield else None
        celebration = None
        if scorer is not None:
            m = self.CELEBRATE_SPOT * M_TO_PX
            goal_x = WIDTH - m if scoring == 0 else m
            corner_y = m if scorer.pos.y < HEIGHT / 2 else HEIGHT - m
            celebration = {"team": scoring, "scorer": scorer,
                           "spot": Vector2(goal_x, corner_y),
                           "until": self.time_elapsed + random.uniform(*self.CELEBRATION)}
        self._set_kickoff(taker, celebration)

    # ------------------------------------------------------------------
    # Foul handling
    # ------------------------------------------------------------------

    def _handle_foul(self, foul_info):
        """
        Process a foul event:
          1. Issue card (if any) to the fouling player.
          2. Show 'FOUL!' banner and optional card flash on screen.
          3. Set up a free kick or penalty for the fouled team.
        """
        fouler         = foul_info["fouler"]
        card_type      = foul_info["card_type"]
        foul_pos       = foul_info["pos"]
        attacking_team = foul_info["attacking_team"]

        # Issue the card
        fouler_team = self.team0 if fouler.team == 0 else self.team1
        display_card = apply_card(fouler, card_type, fouler_team, self.time_elapsed)
        if fouler.red_card:
            self.subs.sent_off(fouler, self.match_minute(), display_card)
        self.subs.fouled(foul_info.get("fouled"), self.match_minute())     # hurt? (career matches)

        # Schedule UI messages
        self._foul_display_until = self.time_elapsed + 2.0 * getattr(self, "match_speed", 1)   # 2 s of watching time
        if display_card != "none":
            self._card_display = {
                "type":  display_card,
                "name":  getattr(fouler, "name", fouler.role),
                "until": self.time_elapsed + 3.5 * getattr(self, "match_speed", 1),
            }

        # Decide penalty vs free kick
        # Attacking team 0 attacks right (toward x=WIDTH); their penalty box is the right end.
        # Attacking team 1 attacks left (toward x=0); their penalty box is the left end.
        if attacking_team == 0:
            in_box = foul_pos.x > WIDTH - 16.5 * M_TO_PX
        else:
            in_box = foul_pos.x < 16.5 * M_TO_PX

        if in_box:
            self.mechanics.setup_penalty(
                attacking_team, self.team0, self.team1, self.ball, self.ai, self.time_elapsed
            )
        else:
            self.mechanics.setup_free_kick(
                attacking_team, foul_pos, self.team0, self.team1, self.ball, self.ai, self.time_elapsed
            )

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _build_match_info(self):
        """Collect display data for the UI renderer."""
        total = sum(self.possession_frames)
        poss  = (
            [int(100 * f / total) for f in self.possession_frames]
            if total > 0 else [50, 50]
        )

        # 1 real second → scale game-minutes (0–45 per half)
        scale = 45.0 / HALF_DURATION_REAL
        if self.match_state == "first_half":
            gm         = min(45, int(self.half_elapsed * scale) + 1)
            half_label = "1ST"
        elif self.match_state == "halftime":
            gm         = 45
            half_label = "HT"
        elif self.match_state == "second_half":
            gm         = min(90, 45 + int(self.half_elapsed * scale) + 1)
            half_label = "2ND"
        elif self.match_state in ("et_first", "et_second", "et_break", "et_halftime", "penalties") or \
                (self.match_state == "full_time" and self.score_90 is not None):
            gm         = self.match_minute()
            half_label = {"et_first": "ET1", "et_second": "ET2", "penalties": "PEN",
                          "full_time": "AET"}.get(self.match_state, "ET")
        else:   # full_time
            gm         = 90
            half_label = "FT"

        return {
            "match_state":     self.match_state,
            "half_label":      half_label,
            "game_minute":     gm,
            "speed":           getattr(self, "match_speed", 1),
            "possession":      poss,
            "shots":           self.shots,
            "shots_on_target": self.shots_on_target,
            "rl_agent":        self.rl_agent,
            "rl_player":       self.rl_player,
            "messi_agent":     self.messi_agent,
            "messi_player":    self.messi_player,
            "home_name":       self._team_name(0),
            "away_name":       self._team_name(1),
            "career":          self.career,
            "can_sub":         self.my_team is not None and self.subs.active,
        }

    def _render(self, flip=True):
        self.pitch_renderer.draw_pitch(self.screen)

        if self.offside_system.offside_detected:
            self.offside_system.draw_offside_line(
                self.screen,
                self.offside_system.offside_line_x,
                self.offside_system.offside_team
            )

        self.object_renderer.draw_players(
            self.screen, self.team0 + self.team1, self.ui_renderer.normal_font
        )
        self.object_renderer.draw_ball(self.screen, self.ball)
        self._draw_overlay()

        match_info = self._build_match_info()
        self.ui_renderer.draw_ui(
            self.window, self.score, self.time_elapsed, self.ball, match_info
        )
        if match_info.get("rl_agent"):
            self.ui_renderer._draw_rl_panel(self.screen, match_info)

        if self.offside_system.offside_detected:
            self.ui_renderer.draw_offside_message(self.screen)

        # Foul + card display
        if self.time_elapsed < self._foul_display_until:
            self.ui_renderer.draw_foul_message(self.screen)
        if self._card_display and self.time_elapsed < self._card_display["until"]:
            self.ui_renderer.draw_card_flash(
                self.screen,
                self._card_display["type"],
                self._card_display["name"]
            )

        boards = [m for m in self.subs.messages.values() if self.time_elapsed < m["until"]]
        for i, msg in enumerate(boards):
            self.ui_renderer.draw_sub_flash(self.screen, msg["text"], msg["team"], row=i,
                                            kind=msg.get("kind", "sub"))

        names = (self._team_name(0), self._team_name(1))
        if self.match_state == "penalties" and self.shootout is not None:
            self.shootout.draw(self.screen, self.ui_renderer, names)
        if self.match_state in ("halftime", "full_time", "et_break", "et_halftime") and self.sub_panel is None:
            self.ui_renderer.draw_match_event_overlay(
                self.screen, self.match_state, self.score, names, self.career, extra=self._extra_line()
            )

        if flip:
            pygame.display.flip()

    def _extra_line(self):
        """The line under the score on the extra-time / full-time screens (knockout ties)."""
        if not self.knockout:
            return None
        agg = self.knockout.get("agg") or [0, 0]
        two_legs = any(agg)
        n = (self._team_name(0), self._team_name(1))
        if self.match_state == "et_break":
            return ("Level on aggregate" if two_legs else "Level after 90 minutes") + " - 30 minutes of extra time"
        if self.match_state == "et_halftime":
            return "Extra time: half time"
        if self.match_state != "full_time":
            return None
        if self.shootout is not None and self.shootout.winner is not None:
            p = self.shootout.score()
            return f"{n[self.shootout.winner]} win {max(p)}-{min(p)} on penalties"
        tot = [self.score[0] + agg[0], self.score[1] + agg[1]]
        how = " after extra time" if self.score_90 is not None else ""
        if two_legs:
            return f"Aggregate {tot[0]}-{tot[1]}{how}" + (f" - {n[0 if tot[0] > tot[1] else 1]} go through"
                                                          if tot[0] != tot[1] else "")
        return how.strip().capitalize() or None

    def _draw_overlay(self):
        mode = getattr(self, "overlay_mode", "off")
        if mode != "off":
            from rendering import debug_overlay
            debug_overlay.draw(self.screen, self.team0 + self.team1, mode)

    def _render_paused(self):
        self.pitch_renderer.draw_pitch(self.screen)
        self.object_renderer.draw_players(
            self.screen, self.team0 + self.team1, self.ui_renderer.normal_font
        )
        self.object_renderer.draw_ball(self.screen, self.ball)
        if getattr(self, "overlay_mode", "off") != "off":
            # Studying the overlay: no dark veil, just a small banner
            self._draw_overlay()
            font = self.ui_renderer.normal_font
            msg = font.render("PAUSED - SPACE to resume", True, (255, 255, 255))
            self.screen.blit(msg, (FIELD_MARGIN + 5, FIELD_MARGIN + 20))
        else:
            self.ui_renderer.draw_paused_message(self.screen)
        pygame.display.flip()
