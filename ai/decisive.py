import math
from pygame.math import Vector2
from core.utils import distance, opponent_will_intercept, clamp
from config.constants import WIDTH, HEIGHT, M_TO_PX, PASS_SPEED
from ai.progression import can_dribble_to_goal
from ai.vision import can_see_teammate, is_cross_situation

def evaluate_decisive_layer(carrier, opponents, teammates):
    """
    Compares the best Killer Pass, Through Ball, Dribble, and Cross.
    Returns: (ActionType, Target) or (None, None)
    Threshold: 60.0
    """
    
    pass_target, pass_score = score_decisive_pass(carrier, teammates, opponents)
    through_target, through_score = score_through_ball_opportunity(carrier, teammates, opponents)
    dribble_target, dribble_score = score_decisive_dribble(carrier, opponents)
    cross_target, cross_score = score_decisive_cross(carrier, teammates, opponents)
    
    options = [
        ("pass", pass_target, pass_score),
        ("through_ball", through_target, through_score),
        ("dribble", dribble_target, dribble_score),
        ("cross", cross_target, cross_score)
    ]
    
    best_option = max(options, key=lambda x: x[2])
    
    if best_option[2] >= 60.0:
        return best_option[0], best_option[1] 
        
    return None, None 


def score_decisive_pass(carrier, teammates, opponents):
    """
    Standard killer pass to a player in a dangerous position.
    Target: Player's FEET (not space ahead).
    NOW WITH VISION!
    """
    best_target = None
    best_score = 0.0
    
    goal_x = 0 if carrier.team == 1 else WIDTH
    passing_stat = carrier.attributes.get("Passing", 10)
    vision_stat = carrier.attributes.get("Vision", 10) 
    
    for mate in teammates:
        dist = distance(carrier.pos, mate.pos)
        if dist < 5.0 * M_TO_PX: continue
        
        # VISION CHECK!
        can_see, vision_reason = can_see_teammate(carrier, mate, opponents)
        
        if not can_see:
            # Can't see them - skip this option
            continue
        
        is_through = False
        if opponents:
            sorted_defs = sorted(opponents, key=lambda d: abs(d.pos.x - goal_x))
            if len(sorted_defs) > 1:
                offside_line_x = sorted_defs[1].pos.x
                if carrier.team == 1: 
                    if mate.pos.x <= offside_line_x + (1.0 * M_TO_PX): is_through = True
                else: 
                    if mate.pos.x >= offside_line_x - (1.0 * M_TO_PX): is_through = True
                    
        if not is_through: continue 

        score = 50.0 
        score += (passing_stat + vision_stat) / 4.0
        
        # Vision quality bonus
        if vision_reason == "clear_view":
            score += 5.0  # Clear sight = better pass
        
        nearest_def = min([distance(mate.pos, d.pos) for d in opponents]) if opponents else 999
        if nearest_def > 3.0 * M_TO_PX: score += 15.0
        elif nearest_def > 1.5 * M_TO_PX: score += 5.0
        else: score -= 20.0 

        if opponent_will_intercept(carrier.pos, mate.pos, opponents, PASS_SPEED * 1.1):
            score -= 40.0
            
        if score > best_score:
            best_score = score
            best_target = mate
            
    return best_target, best_score


# The plan for the best through ball found by the last evaluation (used by
# carrier.py to execute it: meeting point + pass speed).
last_through_plan = None

THROUGH_BASE_SCORE = 45.0     # decisive options need >= 60 to be played

# A through ball is only on when the run is really happening (before, one was
# played whenever any runner existed and a lane was open - ~100 per 90 against
# a handful in real football):
RUNNER_NEAR_LINE  = 4.0       # m: the runner is within this of the last line (not 20 m deep)...
RUNNER_SPEED      = 5.0       # m/s: ...and going
IN_BEHIND         = 2.0       # m: the ball is played to a point at least this far beyond the last line
SPOT_CHANCE       = (0.35, 0.90)   # chance the passer spots it (Passing + Decisions 1 / 20)...
SPOT_EVERY        = 1.0       # s: ...re-rolled this often per runner


def _last_line_x(team, opponents):
    """x of the second-last opponent (the offside line) for a team attacking `team`'s way."""
    xs = sorted((o.pos.x for o in opponents if getattr(o, "is_active", True)), reverse=(team == 0))
    return xs[1] if len(xs) > 1 else (WIDTH if team == 0 else 0.0)


def _runner_beating_line(runner, opponents):
    line = _last_line_x(runner.team, opponents)
    sign = 1.0 if runner.team == 0 else -1.0
    behind_m = (line - runner.pos.x) * sign / M_TO_PX          # + = still behind (onside side of) the line
    fwd = runner.vel.x * sign / M_TO_PX
    return behind_m <= RUNNER_NEAR_LINE and fwd >= RUNNER_SPEED


def _in_behind(point, team, opponents):
    line = _last_line_x(team, opponents)
    sign = 1.0 if team == 0 else -1.0
    return (point.x - line) * sign / M_TO_PX >= IN_BEHIND


def _spots_it(passer, runner):
    import random
    import core.clock as clock
    now = clock.now()
    seen = getattr(passer, "_spotted", None)
    if seen is None:
        seen = passer._spotted = {}
    rec = seen.get(runner.slot)
    if rec is None or now - rec[0] > SPOT_EVERY:
        def s20(name):
            v = passer.attributes.get(name, 10)
            return max(1.0, min(20.0, v / 5.0 if v > 25 else v))
        q = (0.5 * (s20("Passing") + s20("Decisions")) - 1) / 19
        lo, hi = SPOT_CHANCE
        rec = (now, random.random() < lo + (hi - lo) * q)
        seen[runner.slot] = rec
    return rec[1]


def score_through_ball_opportunity(carrier, teammates, opponents):
    """
    Through ball into SPACE for a teammate making a forward run.

    Uses gameplay/through_pass.py to find a meeting point where the runner and
    the ball arrive together, with the runner onside now and no defender (or
    the keeper) able to get there first.  Better passers (Passing, Vision -
    or Decisions if there's no Vision column) value these more.
    """
    global last_through_plan
    import core.world as world
    from gameplay import through_pass

    last_through_plan = None
    all_opponents = world.opponents_of(carrier) if world.players else opponents
    if len(all_opponents) < 2:
        return None, 0.0

    passing = carrier.attributes.get("Passing", 10)
    vision = carrier.attributes.get("Vision", carrier.attributes.get("Decisions", 10))

    best_target, best_score, best_plan = None, 0.0, None
    for mate in teammates:
        if mate.role == "GK":
            continue
        if distance(carrier.pos, mate.pos) < 6.0 * M_TO_PX:
            continue
        can_see, vision_reason = can_see_teammate(carrier, mate, opponents)
        if not can_see:
            continue
        if not _runner_beating_line(mate, all_opponents) or not _spots_it(carrier, mate):
            continue
        plan = through_pass.plan(carrier, mate, all_opponents)
        if plan is None or not _in_behind(plan["point"], carrier.team, all_opponents):
            continue
        score = (THROUGH_BASE_SCORE
                 + 30.0 * plan["value"]
                 + 8.0 * min(plan["safety"], 1.0)
                 + 6.0 * ((passing + vision) / 40.0))
        if vision_reason == "clear_view":
            score += 3.0
        if score > best_score:
            best_target, best_score, best_plan = mate, score, plan

    last_through_plan = best_plan
    return best_target, clamp(best_score, 0, 100)


def score_decisive_dribble(carrier, opponents):
    goal_pos = Vector2(WIDTH, HEIGHT/2) if carrier.team == 0 else Vector2(0, HEIGHT/2)
    dist_to_goal = distance(carrier.pos, goal_pos) / M_TO_PX
    
    defenders_ahead = 0
    if carrier.team == 0: 
        defenders_ahead = len([d for d in opponents if d.pos.x > carrier.pos.x])
    else: 
        defenders_ahead = len([d for d in opponents if d.pos.x < carrier.pos.x])

    max_dist = 35.0
    if defenders_ahead <= 2: max_dist = 65.0
    
    if dist_to_goal > max_dist: return None, 0.0
    
    if can_dribble_to_goal(carrier, opponents):
        return goal_pos, 95.0

    dribbling = carrier.attributes.get("Dribbling", 10)
    score = 40.0
    
    threats = []
    for d in opponents:
        dist = distance(carrier.pos, d.pos)
        if dist < 12.0 * M_TO_PX: 
            to_goal = goal_pos - carrier.pos
            to_def = d.pos - carrier.pos
            if to_goal.dot(to_def) > 0:
                threats.append(d)

    if len(threats) == 0:
        score += 30.0
    elif len(threats) == 1:
        # 1v1: only if he fancies it - good dribblers usually do, ordinary
        # players often look for the pass or shot instead (gameplay/duels.py)
        import gameplay.duels as duels
        import core.clock as clock
        if not duels.wants_take_on(carrier, threats[0], opponents, clock.now()):
            return None, 0.0
        score += 15.0 + ((dribbling - 10) * 0.5)
    else:
        score -= (len(threats) * 15.0)
        
    if len(threats) == 1:
        defender = threats[0]
        def_to_goal = distance(defender.pos, goal_pos)
        
        cover_defs = []
        for d in opponents:
            if d is not defender and distance(d.pos, goal_pos) < def_to_goal:
                if abs(d.pos.y - HEIGHT/2) < 25.0 * M_TO_PX:
                    cover_defs.append(d)
                    
        if not cover_defs:
            score += 30.0
            
    if abs(carrier.pos.y - HEIGHT/2) > 15 * M_TO_PX:
        target = goal_pos + Vector2(0, (HEIGHT/2 - carrier.pos.y) * 0.5)
    else:
        target = goal_pos

    return target, clamp(score, 0, 100)


# ---------------------------------------------------------------------------
# Crossing (the delivery itself is gameplay/crossing.py)
# ---------------------------------------------------------------------------
# Whether a wide player puts a cross in.  Before this the Crossing attribute
# was read as if it were out of 100, so a Crossing-20 winger was hardly more
# likely to cross than a Crossing-5 one - and a team-mate's heading ability,
# or who was marking him, didn't come into it.
#
# Now it adds up:
#   - his Crossing;
#   - what's in the box: for the best two targets, how good they are in the
#     air against the man marking them (Heading + Jumping + Strength), and
#     whether they're free; and how many of ours there are against theirs;
#   - whether he has a man right in front of him (it'd be blocked);
#   - where he is: from near the byline is the best place to cross from;
#   - his instructions (roles/library.py): crossing more / less, and
#     cross_from "byline" (get to the line first) or "early" (whip it in
#     from deep).
CROSS_ZONE_A     = 78.0     # m from his own goal: crossing territory starts here (32 m out)...
CROSS_WIDE       = 13.0     # ...and this far from the middle (out wide, not cutting inside)
BYLINE_A         = 96.0     # m: at the byline
BOX_A, BOX_L     = 94.0, 16.0   # a team-mate in the box is a target...
DANGER_A, DANGER_L = 98.0, 9.0  # ...more so between the penalty spot and the six-yard box
DANGER_BONUS     = 6.0
ARRIVE_IN        = 1.0      # s: a team-mate counts where his run will have taken him by then...
ON_LINE_M        = 2.5      # ...or if he's waiting within this of their line...
LINE_RUNNER_A    = 86.0     # ...and at least this far up
CROSS_BASE       = 56.0
CROSS_PER_POINT  = 2.0      # per Crossing point over 10
TARGET_BASE      = 6.0      # each of the best two targets: this...
TARGET_PER_AIR   = 0.8      # ...+ this per point he's better in the air than his marker...
TARGET_FREE      = 5.0      # ...+ this if nobody's within FREE_M of him
FREE_M           = 3.0
TARGETS_MAX      = 30.0
NUMBERS_PER_MAN  = 2.0      # per extra man of ours in the box (or minus, theirs), up to NUMBERS_MAX
NUMBERS_MAX      = 8.0
BLOCKED          = 18.0     # a man right in front of him
BLOCK_M          = 2.5
AT_BYLINE        = 8.0
INSTR_CROSSING   = {"more": 12.0, "normal": 0.0, "less": -15.0}
INSTR_FROM       = {"byline": (-15.0, 6.0), "early": (10.0, 0.0), "mixed": (0.0, 0.0)}   # (deep, at the byline)


def _air(p):
    def st(name):
        v = p.attributes.get(name, 10)
        return v / 5.0 if v > 25 else v
    return (st("Heading") + st("Jumping") + st("Strength")) / 3.0


def score_decisive_cross(carrier, teammates, opponents):
    from ai.team_shape import to_frame
    a, l = to_frame(carrier.team, carrier.pos)
    if a < CROSS_ZONE_A or abs(l) < CROSS_WIDE:
        return None, 0.0
    try:
        import roles.library as role_library
        instr = role_library.instructions_for(carrier)
    except Exception:
        instr = {"crossing": "normal", "cross_from": "mixed"}

    # Their line (the deepest outfield man): a runner waiting on it will
    # attack the space behind it as the ball is struck
    line = max((to_frame(carrier.team, o.pos)[0] for o in opponents), default=110.0)
    targets = []
    for mate in teammates:
        # where he'll be when it gets there (crossers aim at the run, not the man)
        ma, ml = to_frame(carrier.team, mate.pos + mate.vel * ARRIVE_IN)
        on_line = ma >= LINE_RUNNER_A and ma >= line - ON_LINE_M
        if (ma >= BOX_A or on_line) and abs(ml) <= BOX_L:
            marker = min(opponents, key=lambda o: distance(o.pos, mate.pos)) if opponents else None
            md = distance(marker.pos, mate.pos) / M_TO_PX if marker else 99.0
            value = TARGET_BASE + TARGET_PER_AIR * (_air(mate) - (_air(marker) if marker and md < 6.0 else 8.0))
            if md > FREE_M:
                value += TARGET_FREE
            if ma >= DANGER_A and abs(ml) <= DANGER_L:
                value += DANGER_BONUS
            targets.append((value, mate))
    if not targets:
        return None, 0.0
    targets.sort(key=lambda t: -t[0])

    crossing = carrier.attributes.get("Crossing", 10)
    if crossing > 25:
        crossing /= 5.0
    score = CROSS_BASE + CROSS_PER_POINT * (crossing - 10)
    score += clamp(sum(v for v, _ in targets[:2]), -5.0, TARGETS_MAX)
    n_def = 0
    for o in opponents:
        oa, ol = to_frame(carrier.team, o.pos)
        if oa >= BOX_A and abs(ol) <= BOX_L + 2.0:
            n_def += 1
    score += clamp(NUMBERS_PER_MAN * (len(targets) - n_def), -NUMBERS_MAX, NUMBERS_MAX)

    box = Vector2(WIDTH - 11 * M_TO_PX, HEIGHT / 2) if carrier.team == 0 else Vector2(11 * M_TO_PX, HEIGHT / 2)
    to_box = box - carrier.pos
    if to_box.length_squared() > 0:
        to_box = to_box.normalize()
        for o in opponents:
            rel = o.pos - carrier.pos
            if rel.length() < BLOCK_M * M_TO_PX and rel.length_squared() > 0 and rel.normalize().dot(to_box) > 0.3:
                score -= BLOCKED
                break

    at_byline = a >= BYLINE_A
    if at_byline:
        score += AT_BYLINE
    score += INSTR_CROSSING.get(instr.get("crossing"), 0.0)
    deep, byline = INSTR_FROM.get(instr.get("cross_from"), (0.0, 0.0))
    score += byline if at_byline else deep

    return targets[0][1], clamp(score, 0, 100)