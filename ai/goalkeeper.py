from pygame.math import Vector2
from core.utils import distance, clamp, cell_center
from config.constants import *
from config.formations import formation_4_4_2_positions
# --- UPDATED IMPORTS ---
import ai.progression as progression
import ai.recycle as recycle
import ai.actions as actions
import ai.movement as movement

def update_goalkeeper(keeper, ball, current_time, team_has_possession, ball_cell, opponents, team, mechanics):
    keeper.pos_reason = "keeper"          # (debug overlay label; loose-ball chases overwrite it)
    # Dive recovery
    if keeper.dive_state == "recover" and (current_time - keeper.last_dive_time) > keeper.recover_time:
        keeper.dive_state = "idle"

    # Check for saves
    if ball.owner is None and ball.vel.length() > 10:
        evaluate_dive(keeper, ball, current_time)

    # Positioning — runs every frame so the GK always has a sensible base target.
    # Carrier logic may override keeper.target for a single frame (e.g. passing), but
    # this runs first in the decision loop so any dribble override is immediately
    # corrected next frame by this code.
    if keeper.dive_state not in ("preparing", "diving"):
        # Home position from formation, snapped to vertical centre
        formation = formation_4_4_2_positions(keeper.team)     # (the keeper's spot is the same in every formation)
        base_pos = next((cell_center(col, row) for r, col, row in formation if r == "GK"), keeper.pos)
        base_pos.y = HEIGHT / 2

        # Track ball vertically (small shift only)
        if ball.owner:
            y_shift = (ball.pos.y - HEIGHT / 2) * 0.3
            base_pos.y += y_shift
            base_pos.y = clamp(base_pos.y, HEIGHT / 2 - 40, HEIGHT / 2 + 40)

        # Narrow the angle: when an opponent has the ball within 30 m of goal,
        # stand on the line between the ball and the centre of goal and come
        # off the line - further the closer the shooter is.
        if ball.owner is not None and ball.owner.team != keeper.team:
            goal_centre = Vector2(0.0 if keeper.team == 0 else float(WIDTH), HEIGHT / 2)
            to_ball = ball.pos - goal_centre
            dist_m = to_ball.length() / M_TO_PX
            if 0 < dist_m < 30.0:
                come_out_m = clamp(6.0 - 0.15 * dist_m, 1.5, 4.0)
                come_out_m = min(come_out_m, dist_m - 1.5)
                if come_out_m > 0:
                    base_pos = goal_centre + to_ball.normalize() * (come_out_m * M_TO_PX)

        keeper.target = base_pos
        keeper.state = "guard"
        to_ball = ball.pos - keeper.pos
        if to_ball.length_squared() > 0:
            keeper.facing = to_ball.normalize()


def evaluate_dive(keeper, ball, current_time):
    """
    Predict the ball's trajectory to the GOAL LINE and dive to intercept it there.

    Previous bug: dive_target was set to where the ball crossed the PENALTY-BOX
    BOUNDARY (~162 px ahead of the keeper), so the keeper dived *forward* while
    the ball flew *past* into the net.  This fix calculates the ball's y-position
    when it actually reaches x = 0 (team-0 goal) or x = WIDTH (team-1 goal).
    """
    if abs(ball.vel.x) < 1.0:
        return  # ball barely moving horizontally – no dive needed

    goal_x = 0.0 if keeper.team == 0 else float(WIDTH)

    # Ball must be heading TOWARD this keeper's goal
    if keeper.team == 0 and ball.vel.x >= 0:
        return  # moving away from team-0 goal (left)
    if keeper.team == 1 and ball.vel.x <= 0:
        return  # moving away from team-1 goal (right)

    # Time until ball reaches the goal line
    time_to_goal = (goal_x - ball.pos.x) / ball.vel.x
    if time_to_goal < 0.0 or time_to_goal > 3.5:
        return  # already past, or too far away to matter

    # Predict ball position at goal line
    intercept_y = ball.pos.y + ball.vel.y * time_to_goal
    intercept_z = max(0.0, ball.z + ball.vz * time_to_goal
                      - 0.5 * GRAVITY * time_to_goal ** 2)

    # Over the crossbar – no save possible
    if intercept_z > GOAL_HEIGHT + KEEPER_PARRY_RADIUS:
        return

    # Ball heading well wide of the posts – don't bother diving
    goal_top    = HEIGHT / 2.0 - GOAL_WIDTH / 2.0
    goal_bottom = HEIGHT / 2.0 + GOAL_WIDTH / 2.0
    save_margin = KEEPER_PARRY_RADIUS   # generous 1.8 m each side
    if not (goal_top - save_margin <= intercept_y <= goal_bottom + save_margin):
        return

    # Target: goal-line position at the predicted y intercept
    dive_target = Vector2(
        goal_x,
        clamp(intercept_y, goal_top - save_margin, goal_bottom + save_margin)
    )

    # Check keeper can physically reach dive_target before ball arrives
    dist_to_target  = (dive_target - keeper.pos).length()
    dive_time_needed = dist_to_target / keeper.dive_speed  # seconds

    # Keepers now dive at human speed, so they often can't get all the way
    # there.  They still go for it; gameplay/goalkeeping.py decides whether
    # the stretch is enough.
    if (current_time - keeper.last_dive_time) >= keeper.dive_cooldown:
        if keeper.dive_state == "idle":
            # Begin the preparation phase — record start time ONCE
            keeper.dive_state      = "preparing"
            keeper.dive_target     = dive_target
            keeper.dive_start_time = current_time
        elif keeper.dive_state == "preparing":
            # Already preparing — update target as trajectory refines,
            # but DO NOT reset dive_start_time (that would freeze the timer)
            keeper.dive_target = dive_target

def handle_goalkeeper_with_ball(keeper, teammates, opponents, ball, current_time, mechanics):
    """
    Decision logic when the goalkeeper has possession.
    Goalkeepers NEVER dribble — they pass or clear only.
    This prevents the keeper wandering up the pitch.
    """

    # =========================================================================
    # 1. TRY PROGRESSION PASS (long outlet / counter-attack)
    # =========================================================================
    prog_result = progression.evaluate_progression_layer(keeper, teammates, opponents)

    # Unpack regardless of whether progression returned 3 or 4 values
    if len(prog_result) == 4:
        prog_type, prog_target, prog_score, _ = prog_result   # ignore speed for GK
    else:
        prog_type, prog_target, prog_score = prog_result

    # Only act on pass suggestions — never let the GK dribble
    if prog_type == "pass" and prog_target and prog_score > 55.0:
        mechanics.execute_pass(keeper, prog_target, ball, current_time)
        return keeper.team

    # =========================================================================
    # 2. TRY RECYCLE (short, safe distribution to nearest teammate)
    # =========================================================================
    rec_type, rec_target, rec_score = recycle.evaluate_recycle_layer(keeper, teammates, opponents)
    if rec_type == "pass" and rec_target:
        mechanics.execute_pass(keeper, rec_target, ball, current_time)
        return keeper.team

    # =========================================================================
    # 3. CLEARANCE (last resort — boot it upfield)
    # =========================================================================
    return actions.perform_smart_clearance(keeper, teammates, ball, current_time, mechanics)