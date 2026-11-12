from pygame.math import Vector2
from core.utils import distance, clamp, opponent_will_intercept, angle_between
from config.constants import WIDTH, HEIGHT, M_TO_PX, PASS_SPEED

def evaluate_shoot_decision(carrier, opponents, teammates):
    """
    Decides YES/NO on shooting using a Deduction Model.
    Start Score: 100 (Perfect Shot). Threshold: 50.
    
    🔧 FIXED VERSION - Players now shoot from realistic distances!
    """
    
    # --- 1. SETUP ---
    goal_pos = Vector2(WIDTH, HEIGHT/2) if carrier.team == 0 else Vector2(0, HEIGHT/2)
    to_goal = goal_pos - carrier.pos
    dist_m = to_goal.length() / M_TO_PX
    
    attack_dir = Vector2(1, 0) if carrier.team == 0 else Vector2(-1, 0)
    angle_deviation = angle_between(to_goal.normalize(), attack_dir)
    
    finishing = carrier.attributes.get("Finishing", 10)
    teamwork = carrier.attributes.get("Teamwork", 10)

    # --- 2. HARD GATES (Absolutely NO shooting) ---
    if dist_m > 30.0: return False, 0.0  # Too far (30m = 33 yards max)
    if angle_deviation > 70: return False, 0.0  # Too wide
    
    # NEW: Don't shoot if you're in your own half (too desperate!)
    if carrier.team == 0 and carrier.pos.x < WIDTH * 0.5:
        return False, 0.0
    elif carrier.team == 1 and carrier.pos.x > WIDTH * 0.5:
        return False, 0.0

    # --- 2b. FAST TRACK: Inside the penalty area, facing goal → ALWAYS shoot.
    # Real players don't run a scoring model from 12 yards — they just pull the trigger.
    # Gate: within 16.5 m (penalty area depth), angle less than 45°.
    # We keep the "being literally tackled" (< 1.5 m) as the only exception —
    # if a defender is that close the shot almost certainly gets blocked/deflected.
    if dist_m <= 16.5 and angle_deviation < 45:
        nearest_def_now = 999
        if opponents:
            nearest_def_now = min(distance(carrier.pos, o.pos) for o in opponents)
        if nearest_def_now > 1.5 * M_TO_PX:
            return True, 100.0

    # --- 3. DEDUCTIONS (Start at 100) ---
    score = 100.0
    
    # A. DISTANCE (Reduced penalties - shooting from 15m is normal!)
    if dist_m < 8.0: 
        deduction = 0.0  # Close range - perfect!
    elif dist_m < 16.0: 
        deduction = 10.0  # Mid range - still good!
    elif dist_m < 22.0: 
        deduction = 25.0  # Long range - harder
    elif dist_m < 28.0:
        deduction = 40.0  # Very long - risky
    else: 
        deduction = 50.0  # Extremely long - desperate shot
    score -= deduction
    
    # B. ANGLE (Same as before)
    if angle_deviation > 45: 
        score -= 25.0  # Very wide
    elif angle_deviation > 25: 
        score -= 10.0  # Slightly wide
        
    # C. PRESSURE & BLOCKERS
    nearest_def_dist = 999
    blockers_in_way = count_defenders_in_cone(carrier.pos, goal_pos, opponents)
    
    if opponents:
        nearest_def_dist = min([distance(carrier.pos, o.pos) for o in opponents])

    # Pressure Penalties
    if nearest_def_dist < 1.5 * M_TO_PX: 
        score -= 25.0  # Being tackled!
    elif nearest_def_dist < 3.0 * M_TO_PX: 
        score -= 10.0  # Defender close
    
    # Blocker Penalties
    if blockers_in_way > 0:
        closest_blocker_dist = 999
        for o in opponents:
            if is_in_cone(carrier.pos, goal_pos, o.pos):
                d = distance(carrier.pos, o.pos)
                if d < closest_blocker_dist: 
                    closest_blocker_dist = d
        
        # Only penalize if blocker is REALLY close
        if closest_blocker_dist < 4.0 * M_TO_PX: 
            score -= 15.0  # Close blocker
        elif closest_blocker_dist < 8.0 * M_TO_PX:
            score -= 8.0  # Distant blocker
             
        # Multiple blockers
        if blockers_in_way >= 2: 
            score -= 10.0

    # D. CONTEXT - Should I do something else instead?

    # 1. Sweaty Pass Option (tap-in for teammate)
    is_opposed = nearest_def_dist < 3.0 * M_TO_PX
    bad_angle = angle_deviation > 25
    
    # Only suggest passing if you're in a BAD position
    if (is_opposed or bad_angle) and check_sweaty_option(carrier, teammates, opponents, goal_pos):
        pass_penalty = 10.0 + (teamwork * 0.5)  # Reduced penalty
        score -= pass_penalty

    # E. 🔧 FIXED: Finishing Stat Bonus (was dividing by 100, should be 20!)
    finishing_bonus = (finishing / 20.0) * 10.0  # Now gives up to +10 points!
    score += finishing_bonus

    # F. BONUS: Reward shooting from the "sweet spot" (10-18m)
    if 10.0 <= dist_m <= 18.0:
        score += 8.0  # Good position — but keep the threshold high enough to prefer build-up

    # G. CLEAN THROUGH: he doesn't shoot from distance - he runs at the keeper.
    # (This used to be a big BONUS for shooting, so a man clean through fired
    # from 25-30 m.)  Through on goal, a real player carries it on and shoots
    # from inside the box (the fast track above) - unless a defender is about
    # to catch him or the keeper is rushing out at him, then he hits it now.
    if dist_m > BREAKAWAY_SHOOT and (not opponents or nearest_def_dist > BREAKAWAY_FREE * M_TO_PX):
        goal_side = [o for o in opponents if is_in_cone(carrier.pos, goal_pos, o.pos)] if opponents else []
        catching = any(_closing_on(o, carrier, BREAKAWAY_CATCH) for o in (opponents or []))
        keeper_out = _keeper_rushing(carrier, goal_pos)
        if not goal_side and not catching and not keeper_out:
            return False, 0.0

    # --- 4. VERDICT ---
    final_score = clamp(score, 0.0, 100.0)
    should_shoot = final_score >= 62.0

    return should_shoot, final_score


BREAKAWAY_SHOOT = 16.5    # m: clean through, he carries it on until he's this close (inside the box)...
BREAKAWAY_FREE  = 8.0     # ...if no outfield defender is within this of him...
BREAKAWAY_CATCH = 1.0     # ...and none will be on him within this many seconds...
KEEPER_RUSH_M   = 9.0     # ...and the keeper isn't charging out within this of him


def _closing_on(o, carrier, within_s):
    rel = carrier.pos - o.pos
    d = rel.length()
    if d < 1e-6:
        return True
    closing = o.vel.dot(rel / d) - carrier.vel.dot(rel / d)       # px/s he's gaining
    return d - max(0.0, closing) * within_s < 2.0 * M_TO_PX


def _keeper_rushing(carrier, goal_pos):
    try:
        import core.world as world
        keeper = next((o for o in world.opponents_of(carrier) if o.role == "GK"), None)
    except Exception:
        keeper = None
    if keeper is None:
        return False
    return distance(keeper.pos, carrier.pos) < KEEPER_RUSH_M * M_TO_PX


# --- SHOOTING SPECIFIC HELPERS (Same as before) ---

def count_defenders_in_cone(start, end, defenders):
    """Counts how many defenders are blocking the shot"""
    count = 0
    if not defenders: return 0
    for d in defenders:
        if is_in_cone(start, end, d.pos):
            count += 1
    return count


def is_in_cone(start, end, point):
    """Checks if a point is in the shooting cone"""
    to_end = end - start
    length = to_end.length()
    if length == 0:
        return False
    
    direction = to_end.normalize()
    to_point = point - start
    
    # Project point onto line
    proj = to_point.dot(direction)
    
    # Check if in front and not behind
    if 0 < proj < length:
        # Check perpendicular distance (width of cone)
        perp_dist = (to_point - direction * proj).length()
        if perp_dist < 2.5 * M_TO_PX: 
            return True
    return False


def check_sweaty_option(carrier, teammates, opponents, goal_pos):
    """
    Checks if there's a teammate in a much better position
    (closer to goal with clear pass lane)
    """
    dist_to_goal = distance(carrier.pos, goal_pos)
    
    for mate in teammates:
        d_mate_goal = distance(mate.pos, goal_pos)
        
        # Teammate must be significantly closer (at least 5m)
        if d_mate_goal < (dist_to_goal - 5.0 * M_TO_PX) and d_mate_goal < 15 * M_TO_PX:
            # And the pass must be clear
            if not opponent_will_intercept(carrier.pos, mate.pos, opponents, PASS_SPEED):
                return True
    
    return False