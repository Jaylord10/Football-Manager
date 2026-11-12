# ai/progression.py - WITH SMART DRIBBLING AND THREAT SYSTEM!
from pygame.math import Vector2
from core.utils import distance, opponent_will_intercept, clamp
from config.constants import *
from ai.sanity import is_action_nonsense
from ai.vision import can_see_teammate

# Import threat calculation
from ai.threat import calculate_receiver_threat, calculate_carrier_threat

# 🆕 IMPORT THE NEW SMART DRIBBLING SYSTEM!
from ai.smart_dribbling import calculate_smart_dribble_target, calculate_dribble_speed

# =============================================================================
# ROLE BEHAVIOUR TABLES
# =============================================================================

# How eagerly each role applies the freedom bonus when running with the ball.
# CBs should almost never dribble into space; strikers should sprint whenever free.
_ROLE_DRIBBLE_EAGERNESS = {
    "LCB": 0.10, "RCB": 0.10,   # Centre-backs: almost never dribble forward
    "LB":  0.40, "RB":  0.40,   # Full-backs: occasional attacking run
    "LCM": 0.75, "RCM": 0.75,   # Central mids: balanced carry / pass
    "LM":  0.90, "RM":  0.90,   # Wide mids: love to carry and combine
    "ST1": 1.00, "ST2": 1.00,   # Strikers: full eagerness to run at goal
}

# How much a pass score must exceed dribble score for the carrier to pass.
# Negative = pass wins easily (CB policy); positive = carrier prefers running.
_ROLE_PASS_ADVANTAGE = {
    "LCB": -2.0, "RCB": -2.0,   # CBs: pass wins very easily (must keep it simple)
    "LB":  -1.0, "RB":  -1.0,   # Full-backs: prefer to release quickly
    "LCM": -0.5, "RCM": -0.5,   # Central mids: slight pass lean — good options beat dribbling
    "LM":   0.0, "RM":   0.0,   # Wide mids: neutral — best score wins
    "ST1":  0.0, "ST2":  0.0,   # Strikers: neutral too — role eagerness decides, not this
}


# =============================================================================
# PROGRESSION LAYER: THREAT-BASED DECISION MAKING
# =============================================================================

def evaluate_progression_layer(carrier, teammates, opponents):
    """
    NEW SIMPLIFIED SYSTEM using threat multipliers!
    
    Base scores:
    - Pass = 10 * receiver_threat
    - Dribble = 10 * carrier_threat  ← SAME BASE! Compare threat directly
    
    Threshold: 5.0 (need medium threat to accept)
    
    Logic: Who is more dangerous - my teammate or me?
    - If teammate threat > my threat → PASS
    - If my threat > teammate threat → DRIBBLE
    - If both < 5.0 → RECYCLE (nobody dangerous enough)
    
    🆕 NOW WITH SMART DRIBBLING - Players dodge around defenders!
    
    Hard rules still apply:
    - NO backward passes (rejected)
    - NO passes that will be intercepted (rejected)
    
    Returns: (action_type, target, score) or (action_type, target, score, speed)
    """
    
    # ==================================================================
    # OPTION 1: PASSING
    # ==================================================================
    pass_mate, pass_score = score_progression_pass(carrier, teammates, opponents)
    
    # ==================================================================
    # OPTION 2: DRIBBLING (🆕 NOW SMARTER!)
    # ==================================================================
    dribble_target, dribble_score, dribble_speed = score_progression_dribble(carrier, opponents)
    
    # ==================================================================
    # DECISION LOGIC
    # ==================================================================
    THRESHOLD = 5.0
    # A pass must beat dribbling by this margin to be preferred.
    # Each role has its own threshold: CBs always want to pass, strikers
    # only pass if it's clearly the superior choice.
    PASS_ADVANTAGE_NEEDED = _ROLE_PASS_ADVANTAGE.get(carrier.role, 2.0)

    # Both options viable?
    if pass_score >= THRESHOLD and dribble_score >= THRESHOLD:
        # Only pass if it's clearly the better option (not just marginally)
        if pass_score > dribble_score + PASS_ADVANTAGE_NEEDED:
            return "pass", pass_mate, pass_score
        else:
            return "dribble", dribble_target, dribble_score, dribble_speed

    # Only pass is good enough?
    elif pass_score >= THRESHOLD:
        return "pass", pass_mate, pass_score

    # Only dribble is good enough?
    elif dribble_score >= THRESHOLD:
        return "dribble", dribble_target, dribble_score, dribble_speed

    # Both failed — go to recycle layer
    return "recycle", None, max(pass_score, dribble_score)


# =============================================================================
# PASSING LOGIC (UNCHANGED - Still threat-based!)
# =============================================================================

def score_progression_pass(carrier, teammates, opponents):
    """
    NEW SIMPLE SYSTEM: Base 10 * threat
    
    Hard rules:
    1. NO backward passes
    2. NO passes that will be intercepted
    3. Must have vision of teammate
    
    Returns: (best_teammate, score)
    """
    
    best_target = None
    best_score = 0.0
    
    attack_dir = Vector2(1, 0) if carrier.team == 0 else Vector2(-1, 0)
    
    for mate in teammates:
        # --- HARD RULE 1: Sanity Check ---
        if is_action_nonsense(carrier, "pass", mate.pos, opponents):
            continue
        
        # --- HARD RULE 2: Vision Check ---
        can_see, vision_reason = can_see_teammate(carrier, mate, opponents)
        if not can_see:
            continue
        
        # --- HARD RULE 3: Will Be Intercepted ---
        if opponent_will_intercept(carrier.pos, mate.pos, opponents, PASS_SPEED):
            continue

        # --- DIRECTIONAL MODIFIER ---
        # Forward passes get a bonus; square passes are neutral; backward passes
        # are penalised but NOT hard-rejected — a very safe backward option can
        # still beat a poor forward one, enabling realistic possession recycling.
        to_mate_vec = mate.pos - carrier.pos
        direction_modifier = 0.0
        if to_mate_vec.length_squared() > 0:
            fwd = to_mate_vec.normalize().dot(attack_dir)
            fwd_m = (fwd * to_mate_vec.length()) / M_TO_PX
            if fwd_m >= 5.0:
                direction_modifier =  1.5   # clearly forward — reward
            elif fwd_m >= 0.0:
                direction_modifier =  0.0   # lateral / slight forward — neutral
            elif fwd_m >= -3.0:
                direction_modifier = -2.0   # slightly back — penalise
            else:
                direction_modifier = -4.0   # clearly back — heavy penalty

        # ==============================================================
        # CALCULATE THREAT
        # ==============================================================
        receiver_threat = calculate_receiver_threat(mate, opponents, carrier.pos)

        # Base score: 10 * threat + directional modifier
        score = 10.0 * receiver_threat + direction_modifier
        
        # Track best option
        if score > best_score:
            best_score = score
            best_target = mate
    
    return best_target, best_score


# =============================================================================
# DRIBBLING LOGIC (🆕 NOW WITH SMART PATHFINDING!)
# =============================================================================

def score_progression_dribble(carrier, opponents):
    """
    Smart dribbling system — avoids defenders, moves toward goal.

    Returns: (target_position, score, speed_multiplier)

    FREEDOM BONUS: In real football an unopposed player runs with the ball.
    Previously the dribble score (10 * carrier_threat) was almost identical to the
    pass score (10 * receiver_threat) when everyone was free, so a marginally
    better-positioned teammate always "won" and the carrier never ran.
    The freedom bonus gives dribbling a meaningful edge when no defender is close,
    matching how real players behave.
    """

    goal_pos = Vector2(WIDTH, HEIGHT/2) if carrier.team == 0 else Vector2(0, HEIGHT/2)

    # STEP 1: Smart dribble target (best angle avoiding defenders)
    smart_target = calculate_smart_dribble_target(carrier, opponents, goal_pos)

    # STEP 2: Base threat score
    carrier_threat = calculate_carrier_threat(carrier, opponents)
    score = 10.0 * carrier_threat

    # STEP 3: Freedom bonus — player is unopposed, they should run.
    # The eagerness multiplier makes CBs nearly immune to this bonus while
    # strikers and wide mids get the full benefit.
    eagerness = _ROLE_DRIBBLE_EAGERNESS.get(carrier.role, 0.75)

    if opponents:
        nearest_def_dist = min(distance(carrier.pos, d.pos) for d in opponents)
        nearest_def_m = nearest_def_dist / M_TO_PX
    else:
        nearest_def_m = 999.0

    # Freedom bonus is intentionally modest so that a well-positioned
    # teammate can still win the comparison.  The old values (5.0/3.0/1.5)
    # pushed the dribble score above the maximum pass score (10.0), making
    # it mathematically impossible to pass from the progression layer.
    if nearest_def_m > 12:
        score += 1.0 * eagerness   # Completely free — slight run incentive
    elif nearest_def_m > 8:
        score += 0.6 * eagerness   # Plenty of space
    elif nearest_def_m > 5:
        score += 0.3 * eagerness   # Some breathing room

    # STEP 4: Dribble speed based on space available
    speed_multiplier = calculate_dribble_speed(carrier, smart_target, opponents)

    return smart_target, score, speed_multiplier


# =============================================================================
# LEGACY FUNCTIONS (Keep for compatibility with other files)
# =============================================================================

def can_dribble_to_goal(carrier, opponents):
    """
    Required by shooting.py
    Checks if path to goal is clear (no defenders in the way).
    """
    goal_pos = Vector2(WIDTH, HEIGHT/2) if carrier.team == 0 else Vector2(0, HEIGHT/2)
    dir_v = (goal_pos - carrier.pos).normalize()
    
    # Check 5 points along the path (5m, 10m, 15m, 20m, 25m ahead)
    for i in range(1, 6):
        check_point = carrier.pos + dir_v * i * (5 * M_TO_PX)
        
        # Is any defender within 3m of this point?
        closest = min([distance(check_point, d.pos) for d in opponents]) if opponents else 999
        if closest < 3.0 * M_TO_PX:
            return False  # Path blocked
    
    return True  # Path is clear!


def should_dribble_forward(player, opponents):
    """
    Checks if it's safe to dribble forward (6m ahead is clear).
    """
    goal_pos = Vector2(WIDTH, HEIGHT / 2) if player.team == 0 else Vector2(0, HEIGHT / 2)
    to_goal = (goal_pos - player.pos)
    
    if to_goal.length() == 0:
        return False
    
    # Check 6 meters ahead
    ahead = player.pos + to_goal.normalize() * 6.0 * M_TO_PX
    
    # Count defenders near that spot
    defenders = [d for d in opponents if distance(d.pos, ahead) < 4 * M_TO_PX]
    
    return len(defenders) == 0  # Safe if no defenders