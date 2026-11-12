"""
ai/rl_messi_agent.py
====================
Tabular Q-learning agent for Messi — an attacking ST1 player.

Messi starts as a pure explorer (epsilon=1.0) and learns entirely from
experience.  He will be poor early on but improve across matches as the
Q-table fills in.

Reward contract (per-event, delivered via apply_reward):
  +5   Messi scores a goal
  +3   Messi assists (prev_toucher before a teammate goal)
  +1   successful dribble (beat a defender — defender was close, now gone)
  +0.5 successful pass (teammate receives Messi's pass)
  -1   shot off target / out of play
  -2   turnover (lost possession to an opponent)
  -1   flagged offside
  +5   team wins at full time
  -5   team loses at full time
   0   draw

State: (bx, by, px, py, has_ball, def_close, goal_dist, poss)
       8·5·8·5·2·3·3·2  =  115 200 cells

Actions: 8  (4 off-ball + 4 on-ball)
"""

_STATE_LEN = 8   # bump if state tuple length changes — triggers auto-reset

import json
import os
import random
import shutil

from ai.rl_learning import TDLearningMixin, ALGO_VERSION

# ── Action space ──────────────────────────────────────────────────────────────
NUM_ACTIONS  = 8
ACTION_NAMES = [
    "move_to_space",    # 0  intelligent run into space behind defensive line (no ball)
    "make_run_goal",    # 1  sprint toward the opposition goal area           (no ball)
    "support_play",     # 2  drop to receive / offer easy pass option         (no ball)
    "press_high",       # 3  press the opposition ball carrier                (no ball)
    "dribble_forward",  # 4  dribble at defenders toward goal                 (has ball)
    "shoot",            # 5  attempt a shot on goal                           (has ball)
    "pass_forward",     # 6  pass to the most forward open teammate           (has ball)
    "lay_off",          # 7  short lay-off to nearest teammate                (has ball)
]

_SAVE_PATH = os.path.join(os.path.dirname(__file__), "rl_messi_qtable.json")


class RLMessiAgent(TDLearningMixin):
    """
    Q-learning agent bound to Messi (team-0 ST1).
    Tabular, persistent across sessions, purely exploratory at first.
    """

    def __init__(self, team_id: int, player_name: str = "Messi"):
        self.team_id     = team_id
        self.player_name = player_name

        # Hyper-parameters
        self.alpha         = 0.15     # learning rate
        self.gamma         = 0.95     # discount factor
        self.epsilon       = 1.0      # exploration rate — full random to start
        self.epsilon_min   = 0.05
        self.epsilon_decay = 0.97     # per-match decay (was 0.993: ~80% random after 34 matches)

        # State
        self.q_table:   dict = {}
        self.trajectory: list = []    # [(state, action), …]

        # Stats
        self.total_points   = 0.0
        self.matches_played = 0
        self.last_action    = 0       # for HUD display

        # Executor function — set after import to avoid circular deps
        self.execute_fn = None

        self.save_enabled = True     # sim.py turns this off unless --train
        self._td_reset()
        self._load()

    # ──────────────────────────────────────────────────────────────────────────
    # State encoding
    # ──────────────────────────────────────────────────────────────────────────

    def get_state(self, player, ball, team, opponents):
        """Return the discrete state tuple for the given game snapshot."""
        from config.constants import WIDTH, HEIGHT, M_TO_PX
        from core.utils import clamp, distance

        bx = clamp(int(ball.pos.x / WIDTH  * 8), 0, 7)
        by = clamp(int(ball.pos.y / HEIGHT * 5), 0, 4)
        px = clamp(int(player.pos.x / WIDTH  * 8), 0, 7)
        py = clamp(int(player.pos.y / HEIGHT * 5), 0, 4)

        has_ball = 1 if ball.owner is player else 0
        poss     = 1 if (ball.owner and ball.owner.team == self.team_id) else 0

        # Nearest opponent field player distance → 3 buckets
        field_opps = [o for o in opponents if o.role != "GK"]
        if field_opps:
            min_def = min(distance(player.pos, o.pos) for o in field_opps)
        else:
            min_def = 999.0

        if min_def < 3.0 * M_TO_PX:
            def_close = 0   # tightly marked
        elif min_def < 8.0 * M_TO_PX:
            def_close = 1   # medium pressure
        else:
            def_close = 2   # free

        # Distance to opposition goal → 3 buckets
        goal_x = float(WIDTH) if self.team_id == 0 else 0.0
        dist_to_goal = abs(player.pos.x - goal_x)
        if dist_to_goal < 15.0 * M_TO_PX:
            goal_dist = 0   # in or near the box — shooting range
        elif dist_to_goal < 30.0 * M_TO_PX:
            goal_dist = 1   # attacking half
        else:
            goal_dist = 2   # deep / own half

        return (bx, by, px, py, has_ball, def_close, goal_dist, poss)

    # ──────────────────────────────────────────────────────────────────────────
    # Action selection
    # ──────────────────────────────────────────────────────────────────────────

    def choose_action(self, state, has_ball: bool) -> int:
        """ε-greedy selection restricted to contextually valid actions."""
        valid = list(range(4, 8)) if has_ball else list(range(0, 4))

        if random.random() < self.epsilon:
            action = random.choice(valid)
        else:
            q = self._get_q(state)
            action = max(valid, key=lambda a: q[a])

        self.last_action = action
        return action

    # ──────────────────────────────────────────────────────────────────────────
    # Trajectory & learning
    # ──────────────────────────────────────────────────────────────────────────


    def end_match(self, outcome_reward: float):
        """Called at full-time.  Delivers win/loss bonus, decays ε, saves."""
        self.apply_reward(outcome_reward, clear=True)
        self.epsilon       = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        self.matches_played += 1
        self._save()
        print(
            f"[RLMessi:{self.player_name}] Match {self.matches_played} done | "
            f"ε={self.epsilon:.3f} | total pts={self.total_points:.1f} | "
            f"Q-states={len(self.q_table)}"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Q-table helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _get_q(self, state):
        if state not in self.q_table:
            self.q_table[state] = [0.0] * NUM_ACTIONS
        return self.q_table[state]

    def best_action_name(self) -> str:
        return ACTION_NAMES[self.last_action]

    # ──────────────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────────────

    def _save(self):
        if not self.save_enabled:
            return
        try:
            data = {
                "algo":           ALGO_VERSION,
                "epsilon":        self.epsilon,
                "total_points":   self.total_points,
                "matches_played": self.matches_played,
                "q_table":        {str(k): v for k, v in self.q_table.items()},
            }
            with open(_SAVE_PATH, "w") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"[RLMessi] save error: {e}")

    def _load(self):
        if not os.path.exists(_SAVE_PATH):
            print(f"[RLMessi:{self.player_name}] No saved Q-table — starting fresh.")
            return
        try:
            with open(_SAVE_PATH) as f:
                data = json.load(f)

            if data.get("algo") != ALGO_VERSION:
                backup = _SAVE_PATH.replace(".json", "_old_algorithm_backup.json")
                if not os.path.exists(backup):
                    shutil.copyfile(_SAVE_PATH, backup)
                print(f"[RLMessi:{self.player_name}] Q-table was made with the old learning rule: "
                      f"backed up to {os.path.basename(backup)} and starting fresh.")
                return

            raw_table = data.get("q_table", {})
            if raw_table:
                sample_key = next(iter(raw_table))
                saved_len  = len(sample_key.strip("()").split(","))
                if saved_len != _STATE_LEN:
                    print(
                        f"[RLMessi:{self.player_name}] State size changed "
                        f"({saved_len} → {_STATE_LEN}): discarding old Q-table."
                    )
                    return   # discard stale Q-values, keep stats

            self.epsilon        = data.get("epsilon",        self.epsilon)
            self.total_points   = data.get("total_points",   0.0)
            self.matches_played = data.get("matches_played", 0)
            for k_str, v in raw_table.items():
                tup = tuple(int(x.strip()) for x in k_str.strip("()").split(","))
                self.q_table[tup] = v
            print(
                f"[RLMessi:{self.player_name}] Loaded: {len(self.q_table)} states | "
                f"ε={self.epsilon:.3f} | pts={self.total_points:.1f} | "
                f"matches={self.matches_played}"
            )
        except Exception as e:
            print(f"[RLMessi] load error: {e}")
