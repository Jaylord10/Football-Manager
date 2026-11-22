from pygame.math import Vector2
from core.utils import distance, clamp, cell_center
from config.constants import *
from config.formations import formation_4_4_2_positions
# --- UPDATED IMPORTS ---
import ai.progression as progression
import ai.recycle as recycle
import ai.actions as actions
import ai.movement as movement

GK_HOLD = (1.5, 5.0)     # s a keeper holds it, with the ball in his hands, while his team gets out...
GK_COUNTER_SCORE = 80.0  # ...unless a pass this good is on (a quick counter): then at once
GK_LAW_HOLD = 6.0        # s: the most he'll hold it in his hands (the law allows 8) - waiting for an opponent stood
                         #    right by him to back off...
GK_CLOSE = 5.0           # m: ...an opponent this close: he won't roll it out short past him, he kicks it long
GK_FEET_HOLD = (0.4, 1.2)  # s: a back-pass at his feet: a touch to set it, then he plays it...
GK_FEET_PRESS = 8.0      # m: ...at once if an opponent's this close (and long, if one's within GK_CLOSE)
GK_SPOT_RATE = 5.0       # m/s: how fast his spot moves as play moves...
GK_SPOT_RATE_RUSH = 9.0  # ...coming out to meet a man through on him


def goal_line_centre(keeper):
    return Vector2(0.0 if keeper.team == 0 else float(WIDTH), HEIGHT / 2)


RUSH_FROM = 18.0   # m: a man clean through closer than this - the keeper comes out to meet him...
RUSH_MEET = 5.0    # ...getting to about this far from him...
RUSH_MAX  = 6.0    # ...but no more than this far off his line


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

        # Track ball vertically (small shift only) - all the time, not only when someone has it (between
        # passes he used to snap back to the middle and then out again: a keeper twitching about)
        if not ball.is_dead:
            y_shift = (ball.pos.y - HEIGHT / 2) * 0.3
            base_pos.y += y_shift
            base_pos.y = clamp(base_pos.y, HEIGHT / 2 - 40, HEIGHT / 2 + 40)

        # Narrow the angle: when an opponent has the ball within 30 m of goal,
        # stand on the line between the ball and the centre of goal and come
        # off the line - further the closer the shooter is.
        theirs = (ball.owner is not None and ball.owner.team != keeper.team) or \
            (ball.owner is None and not ball.is_dead and getattr(ball, "last_toucher_team", keeper.team) != keeper.team)
        if theirs:
            goal_centre = Vector2(0.0 if keeper.team == 0 else float(WIDTH), HEIGHT / 2)
            to_ball = ball.pos - goal_centre
            dist_m = to_ball.length() / M_TO_PX
            if 0 < dist_m < 30.0:
                come_out_m = clamp(6.0 - 0.15 * dist_m, 1.5, 4.0)
                # Clean through on him: he comes off his line to meet the man - closing the angle and
                # making him decide (slot it early, dink it over him, or try to go round)
                if dist_m < RUSH_FROM and ball.owner is not None:
                    import ai.shooting as _sh
                    field = [p for p in team if p.role != "GK" and getattr(p, "is_active", True)]
                    if _sh.clean_through(ball.owner, field, goal_centre):
                        come_out_m = max(come_out_m, clamp(dist_m - RUSH_MEET, 1.5, RUSH_MAX))
                come_out_m = min(come_out_m, dist_m - 1.5)
                if come_out_m > 0:
                    base_pos = goal_centre + to_ball.normalize() * (come_out_m * M_TO_PX)

        # His spot moves smoothly (a keeper shuffles across and steps out - his spot used to jump about as
        # the ball changed hands, and he twitched back and forth after it)
        last = getattr(keeper, "_gk_spot", None)
        lt = getattr(keeper, "_gk_spot_t", None)
        if last is not None and lt is not None and 0.0 < current_time - lt < 0.5:
            step = (GK_SPOT_RATE_RUSH if theirs and base_pos.distance_to(goal_line_centre(keeper)) > 4.5 * M_TO_PX
                    else GK_SPOT_RATE) * M_TO_PX * (current_time - lt)
            move = base_pos - last
            if move.length() > step:
                base_pos = last + move.normalize() * step
        keeper._gk_spot, keeper._gk_spot_t = Vector2(base_pos), current_time
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
    if getattr(ball, "last_toucher_team", None) == keeper.team and keeper.dive_state == "idle":
        from gameplay.ricochet import is_ricochet
        if not is_ricochet(ball):
            return                                          # (one of his own playing it back to him)

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

    # Going over HIS head on the way (a dink over a keeper who's come out): nothing to dive at - he can only
    # stretch up and watch it
    t_k = (keeper.pos.x - ball.pos.x) / ball.vel.x
    if 0.0 < t_k < time_to_goal:
        z_k = ball.z + ball.vz * t_k - 0.5 * GRAVITY * t_k ** 2
        if z_k > 2.5 * M_TO_PX:
            return

    # Ball heading well wide of the posts – don't bother diving
    goal_top    = HEIGHT / 2.0 - GOAL_WIDTH / 2.0
    goal_bottom = HEIGHT / 2.0 + GOAL_WIDTH / 2.0
    save_margin = KEEPER_PARRY_RADIUS   # generous 1.8 m each side
    if not (goal_top - save_margin <= intercept_y <= goal_bottom + save_margin):
        return

    # Target: where it will pass HIM - level with where he's standing - not where it crosses the goal line (he
    # used to dive back to the line from a few yards out, into his own net).  He goes across, a touch forward.
    from gameplay.goalkeeping import DIVE_NEEDED, DIVE_FORWARD
    if not 0.02 < t_k:
        return                                               # (level with him already, or past him)
    y_k = ball.pos.y + ball.vel.y * t_k
    z_kk = max(0.0, ball.z + ball.vz * t_k - 0.5 * GRAVITY * t_k ** 2)
    if abs(y_k - keeper.pos.y) < DIVE_NEEDED * M_TO_PX and keeper.dive_state == "idle":
        return                                               # (it's at him: no need to dive)
    fwd = 1.0 if keeper.team == 0 else -1.0
    dive_target = Vector2(keeper.pos.x + fwd * DIVE_FORWARD * M_TO_PX, y_k)
    keeper.dive_height = z_kk / M_TO_PX

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
            keeper.target          = Vector2(keeper.pos)     # (he sets himself - feet planted - as he reads it)
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
    # Holding it a few seconds while his team gets out (real keepers take 4-6 s - the law allows 8) - unless
    # there's a quick counter on: then he lets it go at once.
    import random
    feet = getattr(keeper, "_feet", False)          # (a back-pass: at his feet, not in his hands - the back-pass rule)
    near = min((distance(keeper.pos, o.pos) for o in opponents if getattr(o, "is_active", True)),
               default=9e9) / M_TO_PX
    if current_time - getattr(keeper, "_hold_last", -99.0) > 0.5:      # (a new spell with it)
        keeper._hold_start = current_time
        keeper._hold_for = random.uniform(*(GK_FEET_HOLD if feet else GK_HOLD))
    keeper._hold_last = current_time
    held = current_time - keeper._hold_start
    if feet:
        # At his feet: a touch and he plays it - straight away if someone's closing him down, and if they're right on
        # him he just clears it (no rolling it short past a man stood next to him)
        if near < GK_CLOSE:
            return actions.perform_smart_clearance(keeper, teammates, ball, current_time, mechanics)
        if held < keeper._hold_for and near >= GK_FEET_PRESS:
            keeper.target = keeper.pos
            keeper.state = "guard"
            return keeper.team
    elif not (prog_type == "pass" and prog_score > GK_COUNTER_SCORE) and \
            (held < keeper._hold_for or (near < GK_CLOSE and held < GK_LAW_HOLD)):
        keeper.target = keeper.pos                  # (in his hands: holding it while his team gets out - and while
        keeper.state = "guard"                      #  someone's stood right by him, waiting for him to back off)
        return keeper.team
    if not feet and near < GK_CLOSE and not (prog_type == "pass" and prog_score > 55.0):
        # Still someone right by him: he doesn't roll it out short past him - he kicks it long
        return actions.perform_smart_clearance(keeper, teammates, ball, current_time, mechanics)

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