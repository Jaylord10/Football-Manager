"""
ai/rl_agent.py
==============
Tabular Q-learning agent for a single CB player.

Reward contract:
  +1   Neo personally wins the ball (tackle / interception)
  +5   agent personally scores a goal
  +5   agent's team scores      (per goal)
  -10  agent's team concedes    (per goal)
  +10  team wins  at full time
  -10  team loses at full time
   0   draw

State  : (bx, by, px, py, poss, has_ball, threat, striker_close, carrier_faces_goal)
         → 8·5·8·5·2·2·2·2·2 = 51 200 cells
Actions: 8  (4 without ball + 4 with ball)

The agent is purely tabular — no libraries required beyond `json` / `os` / `random`.
Q-values are updated with one-step Q-learning at each decision (see ai/rl_learning.py);
the decision maker asks for a new action every RL_DECISION_INTERVAL seconds.
The Q-table is saved after every match so the agent improves across sessions.
"""

_STATE_LEN = 9   # bump this if you add more state dimensions; triggers auto-reset

import json
import os
import random
import shutil

from ai.rl_learning import TDLearningMixin, ALGO_VERSION

# ── Action space ──────────────────────────────────────────────────────────────
NUM_ACTIONS  = 8
ACTION_NAMES = [
    "hold_role",   # 0  follow formation target               (no ball)
    "press",       # 1  sprint to ball carrier                (no ball)
    "mark",        # 2  mark nearest attacker                 (no ball)
    "drop",        # 3  retreat deep toward own goal          (no ball)
    "pass_best",   # 4  pass to most open teammate            (has ball)
    "clear",       # 5  boot ball clear / upfield             (has ball)
    "hold_ball",   # 6  shield / hold position                (has ball)
    "pass_gk",     # 7  back-pass to goalkeeper               (has ball)
]

_SAVE_PATH = os.path.join(os.path.dirname(__file__), "rl_cb_qtable.json")


class RLAgent(TDLearningMixin):
    """
    One Q-learning agent bound to a single player (a CB).
    Keeps its own Q-table that persists to disk between sessions.
    """

    def __init__(self, team_id: int, player_name: str = "Neo"):
        self.team_id       = team_id
        self.player_name   = player_name

        # Hyper-parameters
        self.alpha         = 0.15    # learning rate
        self.gamma         = 0.95    # discount factor
        self.epsilon       = 0.25    # exploration rate (decays over matches)
        self.epsilon_min   = 0.05
        self.epsilon_decay = 0.999   # per-match multiplicative decay

        # State
        self.q_table: dict = {}      # state_tuple -> [Q0, Q1, … Q7]
        self.trajectory: list = []   # [(state, action), …]  — cleared on reward

        # Stats
        self.total_points   = 0.0
        self.matches_played = 0
        self.last_action    = 0      # for HUD display

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

        poss     = 1 if (ball.owner and ball.owner.team == self.team_id) else 0
        has_ball = 1 if ball.owner is player else 0

        # High threat = ball is deep in our defensive third
        if self.team_id == 0:
            threat = 1 if ball.pos.x < WIDTH * 0.33 else 0
        else:
            threat = 1 if ball.pos.x > WIDTH * 0.67 else 0

        # Is any opposition forward within ~15 m of Neo?
        # Gives context for whether to mark/drop or hold position.
        ZONE_RADIUS = 15.0 * M_TO_PX
        fwd_roles = {"ST1", "ST2", "LM", "RM", "LCM", "RCM"}
        striker_close = 0
        for opp in opponents:
            if opp.role in fwd_roles and distance(player.pos, opp.pos) < ZONE_RADIUS:
                striker_close = 1
                break

        # Is the ball carrier (if opponent) facing toward our goal?
        # Distinguishes "dangerous forward run" from "back to goal" situations.
        carrier_faces_goal = 0
        if ball.owner and ball.owner.team != self.team_id:
            carrier = ball.owner
            if self.team_id == 0:
                # Our goal is at x=0; carrier faces goal when facing left
                carrier_faces_goal = 1 if carrier.facing.x < -0.3 else 0
            else:
                # Our goal is at x=WIDTH; carrier faces goal when facing right
                carrier_faces_goal = 1 if carrier.facing.x > 0.3 else 0

        return (bx, by, px, py, poss, has_ball, threat, striker_close, carrier_faces_goal)

    # ──────────────────────────────────────────────────────────────────────────
    # Action selection
    # ──────────────────────────────────────────────────────────────────────────

    def choose_action(self, state, has_ball: bool) -> int:
        """ε-greedy action selection restricted to contextually valid actions."""
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
        """
        Called at full-time.  Delivers win/lose bonus, decays ε, saves Q-table.
        """
        self.apply_reward(outcome_reward, clear=True)
        self.epsilon       = max(self.epsilon_min, self.epsilon * self.epsilon_decay)
        self.matches_played += 1
        self._save()
        print(f"[RLAgent:{self.player_name}] Match {self.matches_played} done | "
              f"ε={self.epsilon:.3f} | total pts={self.total_points:.0f} | "
              f"Q-states={len(self.q_table)}")

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
            print(f"[RLAgent] save error: {e}")

    def _load(self):
        if not os.path.exists(_SAVE_PATH):
            print(f"[RLAgent:{self.player_name}] No saved Q-table – starting fresh.")
            return
        try:
            with open(_SAVE_PATH) as f:
                data = json.load(f)

            # Auto-detect stale Q-table: if state tuples have a different length
            # than _STATE_LEN, the state space changed and old data is incompatible.
            if data.get("algo") != ALGO_VERSION:
                backup = _SAVE_PATH.replace(".json", "_old_algorithm_backup.json")
                if not os.path.exists(backup):
                    shutil.copyfile(_SAVE_PATH, backup)
                print(f"[RLAgent:{self.player_name}] Q-table was made with the old learning rule: "
                      f"backed up to {os.path.basename(backup)} and starting fresh.")
                return

            raw_table = data.get("q_table", {})
            if raw_table:
                sample_key = next(iter(raw_table))
                saved_len = len(sample_key.strip("()").split(","))
                if saved_len != _STATE_LEN:
                    print(f"[RLAgent:{self.player_name}] State size changed "
                          f"({saved_len} → {_STATE_LEN}): discarding old Q-table.")
                    return   # leave stats/epsilon but don't load stale Q-values

            self.epsilon        = data.get("epsilon",        self.epsilon)
            self.total_points   = data.get("total_points",   0.0)
            self.matches_played = data.get("matches_played", 0)
            for k_str, v in raw_table.items():
                tup = tuple(int(x.strip()) for x in k_str.strip("()").split(","))
                self.q_table[tup] = v
            print(f"[RLAgent:{self.player_name}] Loaded: {len(self.q_table)} states | "
                  f"ε={self.epsilon:.3f} | pts={self.total_points:.0f} | "
                  f"matches={self.matches_played}")
        except Exception as e:
            print(f"[RLAgent] load error: {e}")
