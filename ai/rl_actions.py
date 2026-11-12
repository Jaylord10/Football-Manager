"""
ai/rl_actions.py
================
Translates an RLAgent action index into concrete in-game commands for the
RL-controlled CB player.

Action map:
  0  hold_role   – follow formation target (normal CB defensive shape)
  1  press       – sprint toward the ball / ball carrier
  2  mark        – stand between nearest attacker and own goal
  3  drop        – retreat to a deeper defensive line
  4  pass_best   – pass to the most open non-GK teammate
  5  clear       – boot ball away from danger (clearance)
  6  hold_ball   – shield / hold position with the ball
  7  pass_gk     – back-pass to the goalkeeper
"""

from pygame.math import Vector2
from config.constants import WIDTH, HEIGHT, M_TO_PX, PASS_SPEED
from core.utils import distance, clamp


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────

def execute_rl_action(action: int, player, ball, team, opponents,
                      mechanics, current_time: float, ball_cell):
    """
    Execute one RL action for `player`.
    Returns True if the action was consumed (prevents normal AI overriding it).
    """
    has_ball = (ball.owner is player)

    # ── Without-ball actions (0–3) ────────────────────────────────────────────
    if action == 0:
        return _hold_role(player, ball, team, opponents, ball_cell)
    elif action == 1:
        return _press(player, ball)
    elif action == 2:
        return _mark(player, opponents)
    elif action == 3:
        return _drop(player)

    # ── With-ball actions (4–7) — only meaningful when player has possession ──
    elif action == 4:
        return _pass_best(player, ball, team, opponents, mechanics, current_time) if has_ball else _hold_role(player, ball, team, opponents, ball_cell)
    elif action == 5:
        return _clear(player, ball, mechanics, current_time) if has_ball else _press(player, ball)
    elif action == 6:
        return _hold_ball(player, ball, mechanics, current_time) if has_ball else _drop(player)
    elif action == 7:
        return _pass_gk(player, ball, team, mechanics, current_time) if has_ball else _mark(player, opponents)

    return False


# ──────────────────────────────────────────────────────────────────────────────
# Without-ball actions
# ──────────────────────────────────────────────────────────────────────────────

def _hold_role(player, ball, team, opponents, ball_cell):
    """
    Position within a dynamic zone rather than a fixed formation cell.

    Depth (X): shifts with ball position — Neo pushes higher when the ball is
    in the opponent half and drops deeper when it's near our goal.
    This gives Neo genuine freedom to participate in build-up without
    abandoning the defensive line when it matters.

    Lateral (Y): leans toward the nearest opposition forward so Neo stays
    goal-side of the most dangerous attacker in his corridor.
    """
    from core.utils import clamp, distance

    poss = ball.owner is not None and ball.owner.team == player.team

    if player.team == 0:
        # Team 0 defends left (x=0).
        # ball_frac=0 → ball on our goal line; ball_frac=1 → ball on their goal line.
        ball_frac = clamp(ball.pos.x / WIDTH, 0.0, 1.0)
        # Zone x slides from 10 % of width (deep defence) to 38 % (high line)
        zone_x = WIDTH * (0.10 + ball_frac * 0.28)
    else:
        # Team 1 defends right (x=WIDTH).
        ball_frac = clamp(1.0 - ball.pos.x / WIDTH, 0.0, 1.0)
        zone_x = WIDTH * (0.90 - ball_frac * 0.28)

    # LCB's natural corridor is the upper-centre (roughly y = 35–40 % of height)
    default_y = HEIGHT * 0.38
    zone_y    = default_y

    # Lean toward the nearest opposition forward if one is within 20 m
    fwd_roles = {"ST1", "ST2", "LM", "RM"}
    threats   = [o for o in opponents if o.role in fwd_roles]
    if threats:
        nearest = min(threats, key=lambda o: distance(player.pos, o.pos))
        # Blend 50/50 between default corridor and threat's y — stay goal-side
        zone_y = clamp(default_y * 0.5 + nearest.pos.y * 0.5,
                       HEIGHT * 0.10, HEIGHT * 0.90)

    player.target = Vector2(zone_x, zone_y)
    player.state  = "support" if poss else "defend"
    return True


def _press(player, ball):
    """Sprint directly toward the ball carrier (or loose ball)."""
    if ball.owner and ball.owner.team != player.team:
        player.target = Vector2(ball.owner.pos)
    else:
        player.target = Vector2(ball.pos)
    player.state = "press"
    return True


def _mark(player, opponents):
    """
    Mark the nearest opposition attacker by positioning between them
    and our own goal, 2–3 m toward goal from the attacker.
    """
    goal_x = 0.0 if player.team == 0 else float(WIDTH)
    field_opps = [o for o in opponents if o.role != "GK"]
    if not field_opps:
        # No attackers visible – drop toward goal
        player.target = Vector2(goal_x + (20 if player.team == 0 else -20),
                                player.pos.y)
        player.state  = "defend"
        return True

    nearest = min(field_opps, key=lambda o: distance(player.pos, o.pos))
    # Stand 30 % of the way between attacker and centre of own goal
    goal_centre = Vector2(goal_x, HEIGHT / 2)
    midpoint    = nearest.pos.lerp(goal_centre, 0.3)
    player.target = midpoint
    player.state  = "mark"
    return True


def _drop(player):
    """
    Retreat to a very compact defensive position deep in our own half.
    The agent hugs the penalty-area edge at its current y.
    """
    if player.team == 0:
        deep_x = WIDTH * 0.15
    else:
        deep_x = WIDTH * 0.85
    player.target = Vector2(deep_x, player.pos.y)
    player.state  = "defend"
    return True


# ──────────────────────────────────────────────────────────────────────────────
# With-ball actions
# ──────────────────────────────────────────────────────────────────────────────

def _pass_best(player, ball, team, opponents, mechanics, current_time):
    """
    Pass to the most open non-GK teammate ranked by:
      • not interceptable
      • forward progress toward opposition goal
      • proximity (prefer closer options)
    Falls back to nearest teammate if no clear lane found.
    """
    from core.utils import opponent_will_intercept

    candidates = [p for p in team if p is not player and p.role != "GK"]
    if not candidates:
        return _clear(player, ball, mechanics, current_time)

    best = None
    best_score = -9999
    for c in candidates:
        intercepted = opponent_will_intercept(player.pos, c.pos, opponents, PASS_SPEED)
        fwd  = (c.pos.x - player.pos.x) * (1 if player.team == 0 else -1)
        prox = -distance(player.pos, c.pos) * 0.03
        intercept_penalty = -50 if intercepted else 0
        s = fwd + prox + intercept_penalty
        if s > best_score:
            best_score = s
            best = c

    if best is None:
        best = min(candidates, key=lambda c: distance(player.pos, c.pos))

    mechanics.execute_pass(player, best, ball, current_time)
    return True


def _clear(player, ball, mechanics, current_time):
    """
    Boot the ball clear: execute a shot-style kick aimed at the opposition goal.
    We reuse execute_shot here because it produces the right ball velocity.
    """
    mechanics.execute_shot(player, ball, current_time)
    return True


def _hold_ball(player, ball, mechanics, current_time):
    """Shield the ball — dribble very slowly in place."""
    safe = Vector2(
        clamp(player.pos.x, 20, WIDTH - 20),
        clamp(player.pos.y, 20, HEIGHT - 20)
    )
    mechanics.execute_dribble(player, safe, ball, current_time, speed_mult=0.4)
    return True


def _pass_gk(player, ball, team, mechanics, current_time):
    """Back-pass to own goalkeeper."""
    gk = next((p for p in team if p.role == "GK"), None)
    if gk is None:
        return _clear(player, ball, mechanics, current_time)
    mechanics.execute_pass(player, gk, ball, current_time)
    return True
