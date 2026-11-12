"""
Ball Control System - Intelligent First Touch + Realistic Physics
Now supports: Pre-calculated context from preparation phase
"""

import random
import math
from pygame.math import Vector2
from core.utils import distance, clamp, opponent_will_intercept
from config.constants import *


# =============================================================================
# MAIN ENTRY POINT: First Touch Handler
# =============================================================================

def apply_first_touch(receiver, ball, opponents, teammates, current_time, mechanics, prepared_context=None):
    """
    Called when ball arrives at receiver.
    Can use pre-calculated context from preparation phase.
    
    Returns: True if first-time pass executed, False if controlled
    """
    
    # Use prepared context if available, otherwise analyze now
    if prepared_context:
        context = prepared_context
    else:
        context = analyze_receiving_context(receiver, ball, opponents, teammates)

    # Check if we have a planned action
    if 'planned_action' in context:

        # FIRST-TIME PASS
        if context['planned_action'] == 'first_time_pass':
            outlet = context.get('planned_target')
            # Only if he'd already seen it - scanned before the ball arrived (ai/decision_timing.py) -
            # and he's still under pressure now it's here (he planned it a moment ago: if the
            # man on him has been left behind, he takes a touch instead)
            import ai.decision_timing as timing
            still_pressed = calculate_pressure_urgency(receiver, opponents) in ("Immediate", "Crowded")
            if outlet and still_pressed and timing.has_picture(receiver, ball):
                execute_first_time_pass(receiver, outlet, ball, current_time, mechanics, opponents)
                return True

        # TOUCH (PUSH/SET/KILL)
        else:
            touch_intent = context['planned_action']
            touch_direction = context['planned_direction']
            execute_first_touch_with_physics(receiver, ball, touch_intent, touch_direction, current_time)
            return False

    # No plan - emergency decision

    # Quick first-time check
    import ai.decision_timing as timing
    if context['pressure_urgency'] in ["Immediate", "Crowded"] and timing.has_picture(receiver, ball):
        outlet = find_first_time_outlet(receiver, teammates, opponents, context)
        if outlet:
            execute_first_time_pass(receiver, outlet, ball, current_time, mechanics, opponents)
            return True

    # Emergency touch
    touch_intent, touch_direction = choose_first_touch_intent(receiver, context, opponents)
    execute_first_touch_with_physics(receiver, ball, touch_intent, touch_direction, current_time)
    return False


# =============================================================================
# CONTEXT ANALYSIS (Called during preparation phase)
# =============================================================================

def analyze_receiving_context(receiver, ball, opponents, teammates):
    """
    Analyzes the situation BEFORE the touch.
    
    Returns dict with:
    - pressure_direction: "front", "back", "inside", "outside", "multiple"
    - pressure_urgency: "Calm", "Pressured", "Immediate", "Crowded"
    - exit_lanes: dict with available exit options
    """
    
    # Find nearest opponent
    nearest_opp = None
    nearest_dist = 9999
    
    if opponents:
        nearest_opp = min(opponents, key=lambda o: distance(receiver.pos, o.pos))
        nearest_dist = distance(receiver.pos, nearest_opp.pos)
    
    # --- A) PRESSURE DIRECTION ---
    pressure_direction = calculate_pressure_direction(receiver, nearest_opp, opponents)
    
    # --- B) PRESSURE URGENCY ---
    pressure_urgency = calculate_pressure_urgency(receiver, opponents)
    
    # --- C) EXIT LANES ---
    exit_lanes = identify_exit_lanes(receiver, opponents, teammates)
    
    return {
        'pressure_direction': pressure_direction,
        'pressure_urgency': pressure_urgency,
        'exit_lanes': exit_lanes,
        'nearest_opponent': nearest_opp,
        'nearest_distance': nearest_dist
    }


def calculate_pressure_direction(receiver, nearest_opp, opponents):
    """
    Determines WHERE the pressure is coming from.
    Returns: "front", "back", "inside", "outside", "multiple", or "none"
    """
    
    if not nearest_opp:
        return "none"
    
    # Check if multiple defenders close
    close_defenders = [o for o in opponents if distance(receiver.pos, o.pos) < 4.0 * M_TO_PX]
    
    if len(close_defenders) >= 3:
        return "multiple"
    
    # Vector from receiver to opponent
    to_opp = nearest_opp.pos - receiver.pos
    
    if to_opp.length_squared() == 0:
        return "multiple"
    
    to_opp_norm = to_opp.normalize()
    
    # --- FRONT vs BACK ---
    facing_dot = receiver.facing.dot(to_opp_norm)
    
    if facing_dot > 0.5:
        direction = "front"
    elif facing_dot < -0.5:
        direction = "back"
    else:
        # --- INSIDE vs OUTSIDE ---
        pitch_center_y = HEIGHT / 2
        receiver_side = "left" if receiver.pos.y < pitch_center_y else "right"
        
        if receiver_side == "left":
            if nearest_opp.pos.y > receiver.pos.y + (2 * M_TO_PX):
                direction = "inside"
            elif nearest_opp.pos.y < receiver.pos.y - (2 * M_TO_PX):
                direction = "outside"
            else:
                direction = "front"
        else:
            if nearest_opp.pos.y < receiver.pos.y - (2 * M_TO_PX):
                direction = "inside"
            elif nearest_opp.pos.y > receiver.pos.y + (2 * M_TO_PX):
                direction = "outside"
            else:
                direction = "front"
    
    return direction


def calculate_pressure_urgency(receiver, opponents):
    """
    How urgent is the pressure?
    Returns: "Calm", "Pressured", "Immediate", "Crowded"
    """
    
    if not opponents:
        return "Calm"
    
    nearest_dist = min([distance(receiver.pos, o.pos) for o in opponents])
    nearby_count = len([o for o in opponents if distance(receiver.pos, o.pos) < 5.0 * M_TO_PX])
    
    if nearby_count >= 3:
        return "Crowded"
    
    if nearest_dist < 1.5 * M_TO_PX:
        return "Immediate"
    elif nearest_dist < 3.0 * M_TO_PX:
        return "Pressured"
    elif nearest_dist < 5.0 * M_TO_PX:
        return "Pressured"
    else:
        return "Calm"


def identify_exit_lanes(receiver, opponents, teammates):
    """
    Identifies available exit options (360 degree scan).
    """
    
    exit_lanes = {
        'safe_pass_lanes': [],
        'safe_touch_lanes': [],
        'shield_lanes': []
    }
    
    # --- CHECK PASS LANES ---
    for mate in teammates:
        mate_dist = distance(receiver.pos, mate.pos)
        
        if mate_dist < 5.0 * M_TO_PX:
            continue
        
        nearest_def_to_mate = 999
        if opponents:
            nearest_def_to_mate = min([distance(mate.pos, o.pos) for o in opponents])
        
        if nearest_def_to_mate > 3.0 * M_TO_PX:
            exit_lanes['safe_pass_lanes'].append(mate)
    
    # --- CHECK TOUCH LANES (8 directions) ---
    directions = [
        Vector2(0, -1), Vector2(1, -1).normalize(), Vector2(1, 0), Vector2(1, 1).normalize(),
        Vector2(0, 1), Vector2(-1, 1).normalize(), Vector2(-1, 0), Vector2(-1, -1).normalize()
    ]
    
    for direction in directions:
        check_point = receiver.pos + direction * (4.0 * M_TO_PX)
        
        if not (0 < check_point.x < WIDTH and 0 < check_point.y < HEIGHT):
            continue
        
        lane_clear = True
        for opp in opponents:
            if distance(opp.pos, check_point) < 3.0 * M_TO_PX:
                lane_clear = False
                break
        
        if lane_clear:
            exit_lanes['safe_touch_lanes'].append(direction)
    
    # --- SHIELD LANES ---
    if opponents:
        nearest_opp = min(opponents, key=lambda o: distance(receiver.pos, o.pos))
        shield_dir = (receiver.pos - nearest_opp.pos)
        
        if shield_dir.length_squared() > 0:
            exit_lanes['shield_lanes'].append(shield_dir.normalize())
    
    return exit_lanes


# =============================================================================
# FIRST-TIME PASS
# =============================================================================

def find_first_time_outlet(receiver, teammates, opponents, context):
    """Finds the best outlet for a first-time pass."""
    
    if not teammates:
        return None
    
    pressure_dir = context['pressure_direction']
    
    best_outlet = None
    best_score = -999
    
    for mate in teammates:
        mate_dist = distance(receiver.pos, mate.pos)
        
        if mate_dist < 5.0 * M_TO_PX or mate_dist > 30.0 * M_TO_PX:
            continue
        
        if opponent_will_intercept(receiver.pos, mate.pos, opponents, PASS_SPEED):
            continue
        
        nearest_def_to_mate = 999
        if opponents:
            nearest_def_to_mate = min([distance(mate.pos, o.pos) for o in opponents])
        
        if nearest_def_to_mate < 3.0 * M_TO_PX:
            continue
        
        score = 50.0
        score += (30.0 - mate_dist / M_TO_PX)
        score += (nearest_def_to_mate / M_TO_PX) * 2.0
        
        to_mate = (mate.pos - receiver.pos).normalize()
        
        if pressure_dir == "front":
            facing_dot = receiver.facing.dot(to_mate)
            if facing_dot > 0.3:
                score -= 30.0
        
        if score > best_score:
            best_score = score
            best_outlet = mate
    
    if not best_outlet:
        gk_or_cbs = [p for p in teammates if p.role in ["GK", "LCB", "RCB"]]
        if gk_or_cbs:
            best_outlet = min(gk_or_cbs, key=lambda p: distance(receiver.pos, p.pos))
    
    return best_outlet


def execute_first_time_pass(receiver, outlet, ball, current_time, mechanics, opponents):
    """Executes a first-time pass using proper passing physics."""
    
    mechanics.execute_pass(receiver, outlet, ball, current_time, opponents)

    receiver.state = "first_time_pass"
    receiver.has_ball = False


# =============================================================================
# TOUCH INTENT SELECTION
# =============================================================================

def choose_first_touch_intent(receiver, context, opponents):
    """
    Chooses what TYPE of touch to take.
    Priority: PUSH > SET > KILL
    """
    
    pressure_dir = context['pressure_direction']
    pressure_urgency = context['pressure_urgency']
    exit_lanes = context['exit_lanes']
    
    # PUSH
    if pressure_urgency == "Calm" and exit_lanes['safe_touch_lanes']:
        push_dir = choose_push_direction(receiver, pressure_dir, exit_lanes, opponents)
        if push_dir:
            return "push", push_dir
    
    # SET
    if pressure_urgency in ["Calm", "Pressured"] and exit_lanes['safe_touch_lanes']:
        set_dir = choose_set_direction(receiver, pressure_dir, exit_lanes)
        if set_dir:
            return "set", set_dir
    
    # KILL
    kill_dir = choose_kill_direction(receiver, pressure_dir, exit_lanes)
    return "kill", kill_dir


def choose_push_direction(receiver, pressure_dir, exit_lanes, opponents):
    """Choose direction for PUSH touch."""
    
    goal_pos = Vector2(WIDTH, HEIGHT/2) if receiver.team == 0 else Vector2(0, HEIGHT/2)
    to_goal = (goal_pos - receiver.pos).normalize()
    
    for lane in exit_lanes['safe_touch_lanes']:
        if lane.dot(to_goal) > 0.5:
            return lane
    
    if exit_lanes['safe_touch_lanes']:
        return exit_lanes['safe_touch_lanes'][0]
    
    return None


def choose_set_direction(receiver, pressure_dir, exit_lanes):
    """Choose direction for SET touch."""
    
    if pressure_dir == "front":
        for lane in exit_lanes['safe_touch_lanes']:
            if receiver.facing.dot(lane) < 0.3:
                return lane
    
    elif pressure_dir == "outside":
        pitch_center = Vector2(WIDTH / 2, HEIGHT / 2)
        to_center = (pitch_center - receiver.pos).normalize()
        for lane in exit_lanes['safe_touch_lanes']:
            if lane.dot(to_center) > 0.5:
                return lane
    
    elif pressure_dir == "inside":
        pitch_center = Vector2(WIDTH / 2, HEIGHT / 2)
        to_center = (pitch_center - receiver.pos).normalize()
        for lane in exit_lanes['safe_touch_lanes']:
            if lane.dot(to_center) < -0.5:
                return lane
    
    elif pressure_dir == "back":
        for lane in exit_lanes['safe_touch_lanes']:
            if receiver.facing.dot(lane) > 0.5:
                return lane
    
    if exit_lanes['safe_touch_lanes']:
        return exit_lanes['safe_touch_lanes'][0]
    
    return None


def choose_kill_direction(receiver, pressure_dir, exit_lanes):
    """Choose direction for KILL touch."""
    
    if exit_lanes['shield_lanes']:
        return exit_lanes['shield_lanes'][0]
    
    return receiver.facing


# =============================================================================
# EXECUTE FIRST TOUCH (WITH REALISTIC PHYSICS!)
# =============================================================================

def execute_first_touch_with_physics(receiver, ball, intent, direction, current_time=None):
    """
    Executes the first touch with REALISTIC ball physics.
    Ball keeps momentum and rolls naturally.
    current_time is stamped on receiver.last_received_time so the carrier
    layer can enforce a settle window before allowing passing decisions.
    """
    
    # Touch distances
    if intent == "push":
        touch_distance = 4.0 * M_TO_PX
    elif intent == "set":
        touch_distance = 1.5 * M_TO_PX
    else:  # kill
        touch_distance = 0.5 * M_TO_PX
    
    # Cushion based on intent
    if intent == "kill":
        speed_mult = 0.2
    elif intent == "set":
        speed_mult = 0.4
    else:  # push
        speed_mult = 0.7
    
    # Player contribution
    player_contribution = receiver.vel * 0.3
    
    # Touch velocity
    touch_velocity = (ball.vel * speed_mult) + player_contribution + (direction * touch_distance * 2.0)
    
    # Clamp speed
    max_touch_speed = DRIBBLE_SPEED * 1.2
    if touch_velocity.length() > max_touch_speed:
        touch_velocity = touch_velocity.normalize() * max_touch_speed
    
    # Apply physics
    ball.vel = touch_velocity
    ball.z = 0
    ball.vz = 0
    
    # Update receiver
    receiver.has_ball = True
    ball.owner = receiver
    ball.last_toucher = receiver
    ball.last_toucher_team = receiver.team
    receiver.facing = direction
    receiver.state = f"touch_{intent}"
    # Stamp receive time so carrier.py can enforce the settle window
    receiver.last_received_time = current_time if current_time is not None else -10.0


# =============================================================================
# DRIBBLE EXECUTION
# =============================================================================

def execute_dribble(dribbler, target_pos, ball, current_time, speed_mult=1.0):
    """Player dribbles toward a target position.

    speed_mult is stored on the player so _calculate_movement_speed() can
    read it.  This is how the carrier layer requests different speeds:
      0.25 → shield (barely moving)
      0.90 → normal dribble
      1.10 → sidestep burst
    Without this, the parameter was silently ignored and every dribble ran
    at the same 80-95% dribble-efficiency speed regardless of intent.
    """
    # Keep dribble targets safely inside the pitch (players now have
    # momentum, so a target on the line would carry the ball out)
    from config.constants import WIDTH, HEIGHT, M_TO_PX
    margin = 1.6 * M_TO_PX
    tx = min(max(target_pos.x, margin), WIDTH - margin)
    ty = min(max(target_pos.y, margin), HEIGHT - margin)
    dribbler.target = Vector2(tx, ty)
    dribbler.state = "dribble"
    dribbler._dribble_speed_mult = speed_mult   # consumed by _calculate_movement_speed
