"""
ai/rl_learning.py
=================
Shared learning rule for the tabular RL agents (Neo + Messi).

Why this exists
---------------
The old rule did `q[a] += alpha * discounted_reward` for every step in the
trajectory.  That only ever ADDS reward, never pulls a value back toward a
target, so Q-values drifted without limit (Neo's table had reached +343/-114)
and, because the agents decided 60 times a second with gamma=0.95 per frame,
a reward only reached the last ~1 second of play.

This mixin implements standard one-step Q-learning at DECISION points
(the decision maker now only asks the agent for a new action every
RL_DECISION_INTERVAL seconds):

    Q(s,a) += alpha * (r + gamma * max_a' Q(s',a') - Q(s,a))

Rewards that arrive between decisions are accumulated and credited to the
decision that was active when they happened.  A reward with clear=True
(goal, full time) ends the episode: the last decision is updated with no
bootstrap term.

The host class must provide: self.alpha, self.gamma, self.total_points,
self._get_q(state).
"""

ALGO_VERSION = "td-v2"   # stored in the save file; older tables are backed up and reset


def valid_actions(has_ball):
    """Actions 0-3 are off-ball, 4-7 are on-ball (same split for both agents)."""
    return range(4, 8) if has_ball else range(0, 4)


class TDLearningMixin:

    def _td_reset(self):
        self._prev_decision = None    # (state, action)
        self._pending_reward = 0.0

    def record(self, state, action, has_ball=None):
        """Called once per DECISION.  Updates the previous decision's Q-value."""
        if not hasattr(self, "_prev_decision"):
            self._td_reset()
        if has_ball is None:
            has_ball = action >= 4
        if self._prev_decision is not None:
            prev_s, prev_a = self._prev_decision
            q_next = self._get_q(state)
            best_next = max(q_next[a] for a in valid_actions(has_ball))
            target = self._pending_reward + self.gamma * best_next
            q = self._get_q(prev_s)
            q[prev_a] += self.alpha * (target - q[prev_a])
        self._prev_decision = (state, action)
        self._pending_reward = 0.0

    def apply_reward(self, reward, clear=False):
        """Bank a reward for the current decision.  clear=True ends the episode."""
        if not hasattr(self, "_prev_decision"):
            self._td_reset()
        self.total_points += reward
        self._pending_reward += reward
        if clear:
            self._end_episode()

    def _end_episode(self):
        if self._prev_decision is not None:
            prev_s, prev_a = self._prev_decision
            q = self._get_q(prev_s)
            q[prev_a] += self.alpha * (self._pending_reward - q[prev_a])
        self._td_reset()
