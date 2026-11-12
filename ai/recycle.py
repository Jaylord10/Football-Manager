from pygame.math import Vector2
from core.utils import distance, opponent_will_intercept, clamp
from config.constants import M_TO_PX, PASS_SPEED
from ai.sanity import is_action_nonsense
from ai.vision import can_see_teammate, is_clearance_situation

# =============================================================================
# RECYCLE LAYER: POSSESSION & SAFETY
# =============================================================================

def evaluate_recycle_layer(carrier, teammates, opponents):
    """
    The 'Emergency' or 'Reset' layer. 
    Finds the safest possible pass to keep the ball.
    NOW WITH VISION!
    
    Special rule: If you're in a clearance situation (panic!), 
    vision checks are relaxed - just boot it!
    """
    best_mate = None
    max_safety = -999.0
    
    teamwork_stat = carrier.attributes.get("Teamwork", 10)
    
    # Check if this is a panic clearance situation
    is_panic = is_clearance_situation(carrier, opponents)

    for mate in teammates:
        # 1. Physical Validity
        if is_action_nonsense(carrier, "pass", mate.pos, opponents): 
            continue
            
        if opponent_will_intercept(carrier.pos, mate.pos, opponents, PASS_SPEED): 
            continue
        
        # 2. VISION CHECK (unless panicking!)
        if not is_panic:
            can_see, vision_reason = can_see_teammate(carrier, mate, opponents)
            
            if not can_see:
                # Can't see them - but we're desperate!
                # In recycle layer, we're more lenient
                # Only block if they're completely out of range
                if distance(carrier.pos, mate.pos) > 25 * M_TO_PX:
                    continue  # Too far and can't see = skip
                else:
                    # Close enough that we might "feel" where they are
                    # But penalize heavily
                    pass  # Allow but with penalty below
        
        # 3. Safety Calculation (Distance from nearest defender)
        nearest_def_dist = 999.0
        if opponents:
            nearest_def_dist = min([distance(mate.pos, d.pos) for d in opponents])
            
        # 4. Positional Value (Backward/Sideways is GOOD here)
        # We want to reward teammates in open space even if they are behind us
        safety_score = nearest_def_dist / M_TO_PX
        
        # Vision penalties (if not panicking)
        if not is_panic:
            can_see, vision_reason = can_see_teammate(carrier, mate, opponents)
            
            if not can_see:
                # Heavy penalty for blind passes in recycle
                safety_score -= 8.0
            elif vision_reason == "peripheral":
                # Small penalty for peripheral passes
                safety_score -= 2.0
            elif vision_reason == "clear_view":
                # Bonus for clear passes
                safety_score += 3.0
        
        # Small bonus for teamwork to recognize reset opportunities
        safety_score += (teamwork_stat / 5.0)
        
        # Back to the keeper only when we're under pressure - not as a habit
        if mate.role == "GK" and not is_panic:
            near_carrier = min((distance(carrier.pos, d.pos) for d in opponents), default=999.0)
            if near_carrier > 4.0 * M_TO_PX:
                safety_score -= 8.0

        # Penalty for passes that are too short (risk of collision/stolen ball)
        if distance(carrier.pos, mate.pos) < 4.0 * M_TO_PX:
            safety_score -= 10.0

        if safety_score > max_safety:
            max_safety = safety_score
            best_mate = mate
            
    # Verdict: If we found a safe teammate, we recycle.
    # Lower threshold if panicking
    min_threshold = 3.0 if is_panic else 5.0
    
    if best_mate and max_safety > min_threshold:
        return "pass", best_mate, max_safety
        
    return None, None, 0.0