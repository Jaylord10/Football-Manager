"""
ai/rl_messi_actions.py
======================
Translates a RLMessiAgent action index into concrete in-game commands
for the RL-controlled ST1 (Messi) player.

Action map:
  0  move_to_space    – intelligent run into space behind the defensive line
  1  make_run_goal    – sprint toward the opposition penalty area
  2  support_play     – drop back to receive, offer a pass option
  3  press_high       – press the opposition ball carrier
  4  dribble_forward  – drive at defenders toward goal; scan for clearest lane
  5  shoot            – attempt a shot on goal
  6  pass_forward     – pass to the most forward open teammate
  7  lay_off          – short lay-off to the nearest teammate
"""

import math
from pygame.math import Vector2
from config.constants import WIDTH, HEIGHT, M_TO_PX, PASS_SPEED
from core.utils import distance, clamp


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────

def execute_messi_action(action: int, player, ball, team, opponents,
                         mechanics, current_time: float, ball_cell):
    """
    Execute one Messi RL action.
    Sets player.last_action_was_shot = True when shooting so match_engine
    can detect off-target shots when the ball leaves play.
    """
    has_ball = (ball.owner is player)

    # ── Off-ball actions (0–3) ────────────────────────────────────────────────
    if action == 0:
        player.last_action_was_shot = False
        return _move_to_space(player, ball, opponents)
    elif action == 1:
        player.last_action_was_shot = False
        return _make_run_goal(player)
    elif action == 2:
        player.last_action_was_shot = False
        return _support_play(player, ball)
    elif action == 3:
        player.last_action_was_shot = False
        return _press_high(player, ball)

    # ── On-ball actions (4–7) — fall back gracefully if no possession ─────────
    elif action == 4:
        if has_ball:
            # Override: RL agent wants to dribble, but if we're inside the
            # penalty area shoot instead — the agent learned to run at the keeper
            # rather than slot it in, so we hard-override that bad habit here.
            goal_pos = Vector2(WIDTH, HEIGHT / 2) if player.team == 0 else Vector2(0.0, HEIGHT / 2)
            dist_m = (goal_pos - player.pos).length() / M_TO_PX
            if dist_m <= 16.5:
                player.last_action_was_shot = True
                return _shoot(player, ball, mechanics, current_time, opponents)
            player.last_action_was_shot = False
            return _dribble_forward(player, ball, opponents, mechanics, current_time)
        player.last_action_was_shot = False
        return _move_to_space(player, ball, opponents)
    elif action == 5:
        if has_ball:
            player.last_action_was_shot = True
            return _shoot(player, ball, mechanics, current_time, opponents)
        else:
            player.last_action_was_shot = False
            return _make_run_goal(player)
    elif action == 6:
        player.last_action_was_shot = False
        return (_pass_forward(player, ball, team, opponents, mechanics, current_time)
                if has_ball else _support_play(player, ball))
    elif action == 7:
        player.last_action_was_shot = False
        return (_lay_off(player, ball, team, mechanics, current_time)
                if has_ball else _press_high(player, ball))

    return False


# ──────────────────────────────────────────────────────────────────────────────
# Off-ball actions
# ──────────────────────────────────────────────────────────────────────────────

def _move_to_space(player, ball, opponents):
    """
    Intelligent run into space: pick a target 10–15 m ahead of the ball in
    the attacking half, then nudge the y coordinate toward the biggest gap
    between defenders.
    """
    if player.team == 0:
        # attacks right
        target_x = clamp(ball.pos.x + 12.0 * M_TO_PX,
                         WIDTH * 0.40, WIDTH - 8.0 * M_TO_PX)
    else:
        # attacks left
        target_x = clamp(ball.pos.x - 12.0 * M_TO_PX,
                         8.0 * M_TO_PX, WIDTH * 0.60)

    # Scan 5 y-positions around the centre to find the one with most space
    best_y   = HEIGHT / 2
    best_gap = 0.0
    for dy in (-HEIGHT * 0.18, -HEIGHT * 0.09, 0.0, HEIGHT * 0.09, HEIGHT * 0.18):
        test_y   = clamp(HEIGHT / 2 + dy, HEIGHT * 0.08, HEIGHT * 0.92)
        test_pos = Vector2(target_x, test_y)
        gap = min(
            (distance(test_pos, o.pos) for o in opponents if o.role != "GK"),
            default=999.0,
        )
        if gap > best_gap:
            best_gap = gap
            best_y   = test_y

    player.target = Vector2(target_x, best_y)
    player.state  = "run"
    return True


def _make_run_goal(player):
    """Sprint directly toward the penalty spot of the opposition goal."""
    if player.team == 0:
        goal_x = WIDTH - 11.0 * M_TO_PX    # penalty spot
    else:
        goal_x = 11.0 * M_TO_PX
    player.target = Vector2(goal_x, HEIGHT / 2)
    player.state  = "run"
    return True


def _support_play(player, ball):
    """
    Drop ~5 m behind the ball to offer a quick lay-off / pass option.
    Messi's false-9 movement — come short to receive and turn.
    """
    if player.team == 0:
        drop_x = clamp(ball.pos.x - 5.0 * M_TO_PX, WIDTH * 0.10, WIDTH * 0.90)
    else:
        drop_x = clamp(ball.pos.x + 5.0 * M_TO_PX, WIDTH * 0.10, WIDTH * 0.90)
    player.target = Vector2(drop_x, ball.pos.y)
    player.state  = "support"
    return True


def _press_high(player, ball):
    """Sprint toward the ball carrier (or loose ball) to press high."""
    if ball.owner and ball.owner.team != player.team:
        player.target = Vector2(ball.owner.pos)
    else:
        player.target = Vector2(ball.pos)
    player.state = "press"
    return True


# ──────────────────────────────────────────────────────────────────────────────
# On-ball actions
# ──────────────────────────────────────────────────────────────────────────────

def _dribble_forward(player, ball, opponents, mechanics, current_time):
    """
    Drive at goal picking the lane with the most space between defenders.
    Scans ±40° around the direct goal direction in 10° increments.
    """
    if player.team == 0:
        goal_pos = Vector2(WIDTH, HEIGHT / 2)
    else:
        goal_pos = Vector2(0.0, HEIGHT / 2)

    # Safety net: never dribble when inside the penalty area with the ball —
    # shoot instead.  This catches any code path that calls _dribble_forward
    # directly (e.g. the >25m fallback in _shoot won't fire at this range).
    if ball.owner is player:
        dist_m = (goal_pos - player.pos).length() / M_TO_PX
        if dist_m <= 16.5:
            mechanics.execute_shot(player, ball, current_time, opponents)
            return True

    raw_dir = goal_pos - player.pos
    if raw_dir.length() > 0:
        raw_dir = raw_dir.normalize()

    base_angle = math.atan2(raw_dir.y, raw_dir.x)
    best_angle = base_angle
    best_gap   = -1.0

    for deg in range(-40, 41, 10):
        rad      = base_angle + math.radians(deg)
        test_dir = Vector2(math.cos(rad), math.sin(rad))
        test_pos = player.pos + test_dir * (8.0 * M_TO_PX)
        test_pos.x = clamp(test_pos.x, 0.0, float(WIDTH))
        test_pos.y = clamp(test_pos.y, 0.0, float(HEIGHT))
        gap = min(
            (distance(test_pos, o.pos) for o in opponents if o.role != "GK"),
            default=999.0,
        )
        if gap > best_gap:
            best_gap   = gap
            best_angle = rad

    target_dir = Vector2(math.cos(best_angle), math.sin(best_angle))
    target = player.pos + target_dir * (8.0 * M_TO_PX)
    target.x = clamp(target.x, 0.0, float(WIDTH))
    target.y = clamp(target.y, 0.0, float(HEIGHT))

    mechanics.execute_dribble(player, target, ball, current_time, speed_mult=1.0)
    return True


_MAX_SHOOT_DIST_M = 25.0   # metres — beyond this the shot is unrealistic

def _shoot(player, ball, mechanics, current_time, opponents=None):
    """
    Attempt a shot on goal.
    Hard gate: if the player is more than 25 m from goal, dribble forward
    instead — this stops the RL agent learning that half-way shots can score
    due to a keeper that can't cover the distance in time.
    """
    if player.team == 0:
        goal_pos = Vector2(WIDTH, HEIGHT / 2)
    else:
        goal_pos = Vector2(0.0, HEIGHT / 2)

    dist_m = (goal_pos - player.pos).length() / M_TO_PX
    if dist_m > _MAX_SHOOT_DIST_M:
        # Too far — advance toward goal instead
        player.last_action_was_shot = False
        return _dribble_forward(player, ball, opponents or [], mechanics, current_time)

    mechanics.execute_shot(player, ball, current_time, opponents)
    return True


def _pass_forward(player, ball, team, opponents, mechanics, current_time):
    """
    Pass to the most forward open teammate (minimises interception risk,
    maximises forward progress toward the opposition goal).
    """
    from core.utils import opponent_will_intercept

    candidates = [p for p in team if p is not player and p.role != "GK"]
    if not candidates:
        return _shoot(player, ball, mechanics, current_time, opponents)

    best       = None
    best_score = -9999.0
    for c in candidates:
        intercepted = opponent_will_intercept(player.pos, c.pos, opponents, PASS_SPEED)
        # Forward progress: positive = further toward opposition goal
        fwd  = (c.pos.x - player.pos.x) * (1 if player.team == 0 else -1)
        prox = -distance(player.pos, c.pos) * 0.02
        s    = fwd + prox + (-50 if intercepted else 0)
        if s > best_score:
            best_score = s
            best       = c

    if best is None:
        best = min(candidates, key=lambda c: distance(player.pos, c.pos))

    mechanics.execute_pass(player, best, ball, current_time)
    return True


def _lay_off(player, ball, team, mechanics, current_time):
    """Quick short lay-off to the nearest teammate — safe possession retention."""
    candidates = [p for p in team if p is not player]
    if not candidates:
        # Nothing to pass to — dribble forward
        return _dribble_forward(player, ball, [], mechanics, current_time)
    nearest = min(candidates, key=lambda c: distance(player.pos, c.pos))
    mechanics.execute_pass(player, nearest, ball, current_time)
    return True
