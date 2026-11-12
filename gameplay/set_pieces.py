# ===========================================================================
# gameplay/set_pieces.py
# All set piece and match flow mechanics: goal kicks, throw-ins, restarts
# 🆕 NOW WITH DEAD BALL SYSTEM - No more instant lightning kicks!
# ===========================================================================

import random
from pygame.math import Vector2
from core.utils import distance, clamp, cell_center
from config.constants import *
from config.formations import formation_4_4_2_positions


# ===========================================================================
# BOUNDARY & GOAL CHECKS
# ===========================================================================

def check_ball_out(ball):
    """
    Check if ball has gone out of play (over sidelines or goal lines).
    
    Returns: True if out, False if in play
    """
    
    # Check sidelines (Y boundaries)
    if ball.pos.y < -5 or ball.pos.y > HEIGHT + 5:
        return True
    
    # Check goal lines (X boundaries)
    if ball.pos.x < -5 or ball.pos.x > WIDTH + 5:
        return True
    
    return False


def check_goal(ball):
    """
    Check if ball has crossed the goal line within the goal.
    
    RULES:
    - Ball must be between goal posts (Y dimension)
    - Ball must be below crossbar (Z dimension)
    - Ball must cross goal line (X dimension)
    
    Returns: 
        - 0 if Team 0 scored
        - 1 if Team 1 scored
        - None if no goal
    """
    
    # Goal post positions (Y dimension)
    goal_top = (HEIGHT / 2) - GOAL_WIDTH / 2
    goal_bottom = (HEIGHT / 2) + GOAL_WIDTH / 2
    
    # Goal line depth
    depth = int(0.5 * M_TO_PX)
    
    # Crossbar height
    GOAL_HEIGHT = 2.44 * M_TO_PX
    
    # Ball too high - over the bar
    if ball.z > GOAL_HEIGHT:
        return None
    
    # Check Team 1 goal (left side, x < 0)
    if ball.pos.x < -depth:
        if goal_top < ball.pos.y < goal_bottom:
            return 1  # Team 0 scored!
    
    # Check Team 0 goal (right side, x > WIDTH)
    if ball.pos.x > WIDTH + depth:
        if goal_top < ball.pos.y < goal_bottom:
            return 0  # Team 1 scored!
    
    return None


# ===========================================================================
# OUT OF PLAY RESOLUTION
# ===========================================================================

def resolve_out_of_play(mechanics, ball, last_touch_team, team0, team1, ai_system, current_time):
    """
    Determine what type of restart is needed when ball goes out.
    
    🆕 NOW PASSES current_time FOR DEAD BALL SYSTEM
    
    RESTART TYPES:
    - Sideline out = Throw-in (opposite team)
    - Goal line out (attacking team last touch) = Goal kick (defending team)
    - Goal line out (defending team last touch) = Corner kick (NOT IMPLEMENTED YET)
    
    NOTE: Corner kicks not implemented - treated as goal kick for now
    """
    
    is_side_out = (ball.pos.y < -5 or ball.pos.y > HEIGHT + 5)
    is_goal_line_out = (ball.pos.x < -5 or ball.pos.x > WIDTH + 5)
    
    if not (is_side_out or is_goal_line_out):
        return  # Ball still in play

    # GOAL LINE OUT — checked first so corner-area balls that are also
    # past the sideline are never mis-classified as throw-ins.
    if is_goal_line_out:
        # Determine which goal line
        if ball.pos.x < 0:
            # Left goal line = Team 0's goal.  Attacking team = Team 1.
            defending_team, attacking_team = 0, 1
        else:
            # Right goal line = Team 1's goal.  Attacking team = Team 0.
            defending_team, attacking_team = 1, 0

        last_touch = getattr(ball, 'last_toucher_team', None)
        if last_touch == defending_team:
            # Defender/GK last touched (parry, clearance behind own line) → corner for attackers
            _setup_corner_kick(mechanics, attacking_team, team0, team1, ball, ai_system, current_time)
        else:
            # Attacker last touched (shot wide/over) OR unknown → goal kick for defenders
            _setup_goal_kick(mechanics, defending_team, team0, team1, ball, ai_system, current_time)
        return

    # SIDELINE OUT = THROW-IN (only if not also past the goal line)
    # Against the team that last TOUCHED it - not the team that last had it
    # (a defender who toe-pokes a pass into touch gives the throw away).
    if is_side_out:
        toucher = getattr(ball, 'last_toucher_team', None)
        if toucher in (0, 1):
            last_touch_team = toucher
        restarting_team_id = 1 if last_touch_team == 0 else 0
        _setup_throw_in(mechanics, restarting_team_id, team0, team1, ball, ai_system, current_time)


# ===========================================================================
# GOAL KICK - 🆕 DEAD BALL VERSION
# ===========================================================================

def _setup_goal_kick(mechanics, team_id, team0, team1, ball, ai_system, current_time):
    """
    Set up a goal kick for the defending team.

    The ball goes in the 6-yard box and the keeper is the taker.  Nobody is
    moved: both teams walk into their goal-kick shapes (ai/decision_maker.py)
    and it's taken once the keeper's there and his team is set.
    """
    from config.formations import formation_4_4_2_positions
    from core.utils import cell_center
    from ai.movement import reset_stable_ball

    # (Everyone used to be snapped - teleported - back to their formation
    # spots here.  Now they walk into the goal-kick shape themselves while the
    # keeper sets the ball down: ai/decision_maker.py _restart_positions.)
    for team in (team0, team1):
        for player in team:
            player.has_ball = False

    # Reset the smoothed ball position so role targets don't lag from old position
    reset_stable_ball()

    # ── 2. Place ball in the 6-yard box ───────────────────────────────────
    box_depth = 5.5 * M_TO_PX
    if team_id == 0:
        ball_pos = Vector2(box_depth - 10, HEIGHT / 2 + random.choice([-20, 20]))
    else:
        ball_pos = Vector2(WIDTH - box_depth + 10, HEIGHT / 2 + random.choice([-20, 20]))

    ball.pos = ball_pos
    ball.vel = Vector2(0, 0)
    ball.z   = 0
    ball.vz  = 0

    # ── 3. GK takes the kick ──────────────────────────────────────────────
    kicking_team = team0 if team_id == 0 else team1
    keeper = next((p for p in kicking_team if p.role == "GK"), None)

    if keeper:
        # He walks over to put the ball down (he's only a few metres away)
        keeper.target = Vector2(ball_pos)
        keeper.has_ball = False

        ball.owner         = None   # clear any stale owner before locking dead ball
        ball.is_dead       = True
        ball.restart_type  = "goal_kick"
        ball.restart_taker = keeper
        ball.restart_time  = current_time

        if ai_system:
            ai_system.last_possession_team = team_id


# ===========================================================================
# THROW-IN - 🆕 DEAD BALL VERSION
# ===========================================================================

def _setup_throw_in(mechanics, team_id, team0, team1, ball, ai_system, current_time):
    """
    Set up a throw-in for the team.
    
    🆕 DEAD BALL SYSTEM:
    - Ball is dead (can't be dribbled)
    - Nearest player is designated taker
    - Brief wait before throw
    
    RULES:
    - Ball placed on sideline where it went out
    - Nearest field player takes throw
    - Throwing team gets possession when taken
    """
    
    # Place ball on sideline
    throw_x = clamp(ball.pos.x, 20, WIDTH - 20)
    
    # Determine which sideline (top or bottom)
    throw_y = 0 if ball.pos.y < HEIGHT/2 else HEIGHT
    
    # Set ball position
    ball.pos = Vector2(throw_x, throw_y)
    ball.vel = Vector2(0, 0)
    ball.z = 0
    ball.vz = 0
    
    # Find nearest field player to take throw
    throwing_team = team0 if team_id == 0 else team1
    field_players = [p for p in throwing_team if p.role != "GK" and getattr(p, 'is_active', True)]
    
    if field_players:
        taker = min(field_players, key=lambda p: distance(p.pos, ball.pos))

        # Steer taker TOWARD the ball rather than teleporting them there.
        # The 0.7s restart delay in decision_maker.py gives them time to jog over.
        taker.target = Vector2(ball.pos)
        taker.state = "idle"

        # === 🆕 DEAD BALL SETUP ===
        ball.owner         = None   # clear stale owner before locking dead ball
        ball.is_dead = True
        ball.restart_type = "throw_in"
        ball.restart_taker = taker
        ball.restart_time = current_time

        taker.has_ball = False  # Not "owned" yet

        # Update possession tracking
        if ai_system:
            ai_system.last_possession_team = team_id


# ===========================================================================
# KICKOFF / FULL RESET
# ===========================================================================

def reset_game(team0, team1, ball, ai_system):
    """
    Full game reset - returns all players to kickoff positions.
    
    WHEN TO USE:
    - After a goal is scored (kickoff)
    - At start of match
    - At start of second half
    
    WHEN NOT TO USE:
    - Goal kicks (players should stay where they are) ✅
    - Throw-ins (players should stay where they are) ✅
    - Free kicks (not implemented yet)
    """
    
    # Reset all players to formation positions
    for team in (team0, team1):
        from config.formations import formation_positions
        formation = formation_positions(team[0].team)
        
        for index, (role, col, row) in enumerate(formation):
            player = next((p for p in team if p.slot == role and getattr(p, 'is_active', True)), None)
            
            if player:
                # Position player at formation spot
                player.pos = cell_center(col, row)
                
                # Goalkeeper exception - always at exact center
                if role == "GK":
                    player.pos.y = HEIGHT/2
                
                # Reset player state
                player.target = Vector2(player.pos)
                player.has_ball = False
                player.state = "idle"
                
                # Reset facing direction
                player.facing = Vector2(1, 0) if player.team == 0 else Vector2(-1, 0)
                
                # Reset GK dive state if applicable
                if player.role == "GK":
                    player.dive_state = "idle"
                    player.last_dive_time = -10.0
    
    # Reset ball to center
    ball.pos = Vector2(WIDTH / 2, HEIGHT / 2)
    ball.vel = Vector2(0, 0)
    ball.owner = None
    ball.z = 0
    ball.vz = 0

    # Reset smooth ball position so role targets start fresh at centre
    from ai.movement import reset_stable_ball
    reset_stable_ball()
    
    # Reset ball tracking
    ball.last_kick_time = -10.0
    ball.last_pass_time = -10.0
    ball.pass_start_pos = None
    ball.intended_target = None
    ball.last_toucher = None
    ball.last_toucher_team = None
    
    # === 🆕 CLEAR DEAD BALL STATE ===
    ball.is_dead = False
    ball.restart_type = None
    ball.restart_taker = None
    ball.restart_time = 0.0
    
    # Random possession for kickoff
    if ai_system:
        ai_system.last_possession_team = random.choice([0, 1])


# ===========================================================================
# FREE KICK
# ===========================================================================

def setup_free_kick(mechanics, attacking_team_id, foul_pos, team0, team1, ball, ai_system, current_time):
    """Public entry point — called from GameMechanics."""
    _setup_free_kick(mechanics, attacking_team_id, foul_pos, team0, team1, ball, ai_system, current_time)


# Free-kick zones (distance from the goal it's being taken towards, metres)
FK_SHOOT_DIST     = 28.0    # inside this, and central enough: a shooting free kick
FK_SHOOT_ANGLE    = 0.45    # ...central enough = |sideways| / distance below this
FK_DELIVERY_DIST  = 40.0    # inside this (but not a shooting one): a delivery into the box
                            # beyond it: a "long" free kick - quick, both teams in shape
FK_WALL_BY_DIST   = ((20.0, 5), (24.0, 4), (28.0, 3))   # shooting free kick: wall size
FK_DELIVERY_WALL  = 2       # delivery: a couple in the wall (1 if it's wide)
FK_LINE           = 17.0    # m from goal: defending line for a delivery (edge of the box)...
FK_LINE_MIN       = 8.0     # ...never deeper than this
FK_SHOOT_LINE     = 13.0    # m from goal: defending line behind a shooting wall
FK_BOX_ATTACKERS  = 4       # delivery: this many attackers on the line (best in the air)
FK_SHOOT_ATTACKERS = 3      # shooting free kick: this many in the box
FK_STAY_BACK      = 3       # attackers kept back for the counter
FK_DEF_STAY_UP    = 1       # defending team leaves this many up front


def _air(p):
    return p.attributes.get("Heading", 50) + p.attributes.get("Jumping", 50) + p.attributes.get("Strength", 50)


def _fk_zone(ball_a, ball_l):
    """'shoot', 'delivery' or 'long' for a free kick at (a, l) in the attacking frame."""
    d = ((110.0 - ball_a) ** 2 + ball_l ** 2) ** 0.5
    if d <= FK_SHOOT_DIST and abs(ball_l) / max(d, 1.0) <= FK_SHOOT_ANGLE:
        return "shoot", d
    if d <= FK_DELIVERY_DIST or (ball_a >= 110.0 - FK_DELIVERY_DIST and abs(ball_l) > 12.0):
        return "delivery", d
    return "long", d


def _setup_free_kick(mechanics, attacking_team_id, foul_pos, team0, team1, ball, ai_system, current_time):
    """
    Set up a free kick for attacking_team_id at foul_pos.  Three set-ups,
    depending on where it is (positions given in the attacking team's frame):

    LONG (more than ~40 m out): no wall.  Both teams simply take up their
        normal shape - the defenders 9.15 m away - and it's played short or
        long like any other pass (ai/decision_maker.py builds the shapes).

    DELIVERY (~28-40 m out, or a wide one near the box): a lofted ball in.
        Defenders: a wall of 1-2, the rest holding a line on the edge of the
        box (the offside line), one left up front.  Attackers: the best in
        the air lined up on that line ready to attack the ball, one on the
        edge of the box for the second ball, three kept back.

    SHOOTING (central, inside ~28 m): a 3-5 man wall made of midfielders and
        strikers (not the centre-backs), the keeper covering the side the wall
        doesn't, the rest marking in the box.  Attackers: the taker plus a
        decoy over the ball, three in the box for rebounds, one on the edge,
        three back.

    Nobody is moved: they all walk to these spots.
    """
    from ai.team_shape import to_frame, to_world
    attack_team = team0 if attacking_team_id == 0 else team1
    defend_team = team1 if attacking_team_id == 0 else team0
    tid = attacking_team_id

    ball.pos = Vector2(foul_pos)
    ball.vel = Vector2(0, 0)
    ball.z   = 0
    ball.vz  = 0

    ba, bl = to_frame(tid, ball.pos)
    zone, d_goal = _fk_zone(ba, bl)
    ball._fk_zone = zone

    field_att = [p for p in attack_team if p.role != "GK" and getattr(p, 'is_active', True)]
    defend_field = [p for p in defend_team if p.role != "GK" and getattr(p, 'is_active', True)]
    if not field_att:
        return

    def W(a, l):
        return to_world(tid, a, l)

    # ── Taker ────────────────────────────────────────────────────────────
    if zone == "shoot":
        taker = max(field_att, key=lambda p: p.attributes.get("Long Shots", 50) + p.attributes.get("Finishing", 50) * 0.5)
    elif zone == "delivery":
        taker = max(field_att, key=lambda p: p.attributes.get("Crossing", 50) + p.attributes.get("Passing", 50) * 0.5)
    else:
        taker = min(field_att, key=lambda p: distance(p.pos, foul_pos))   # quick: whoever's nearest
    taker.target = Vector2(foul_pos)

    gk = next((p for p in defend_team if p.role == "GK" and getattr(p, 'is_active', True)), None)

    if zone == "long":
        # Shapes come from ai/decision_maker.py (like a throw-in, 9.15 m away)
        if gk:
            gk.target = W(110.0 - 3.0, 0.0)
        _dead_free_kick(ball, taker, current_time, ai_system, attacking_team_id)
        return

    # Where does the ball go towards goal? (for the wall)
    goal = W(110.0, 0.0)
    to_goal = goal - ball.pos
    goal_dir = to_goal.normalize() if to_goal.length_squared() > 0 else Vector2(1, 0)
    perp = Vector2(-goal_dir.y, goal_dir.x)

    # ── Defending team ───────────────────────────────────────────────────
    if zone == "shoot":
        n_wall = next((n for dist, n in FK_WALL_BY_DIST if d_goal <= dist), 3)
        line_a = 110.0 - FK_SHOOT_LINE
    else:
        n_wall = FK_DELIVERY_WALL if abs(bl) < 20.0 else 1
        line_a = 110.0 - max(FK_LINE_MIN, min(FK_LINE, (110.0 - ba) - 2.0))
    # Wall: midfielders and strikers first, never the centre-backs if avoidable
    wall_pref = {"ST1": 0, "ST2": 0, "LM": 1, "RM": 1, "LCM": 2, "RCM": 2, "LB": 3, "RB": 3, "LCB": 4, "RCB": 4}
    stay_up = sorted((p for p in defend_field if p.role in ("ST1", "ST2")),
                     key=lambda p: -p.attributes.get("Top Speed", 50))[:FK_DEF_STAY_UP]
    pool = [p for p in defend_field if p not in stay_up]
    wall = sorted(pool, key=lambda p: (wall_pref.get(p.role, 2), distance(p.pos, foul_pos)))[:n_wall]
    wall_centre = ball.pos + goal_dir * (9.15 * M_TO_PX)
    for i, p in enumerate(wall):
        off = (i - (len(wall) - 1) / 2.0) * 0.7 * M_TO_PX
        p.target = wall_centre + perp * off
        p.state = "defend"
        p.pos_reason = "free kick: wall"
    for p in stay_up:
        p.target = W(52.0, -6.0 if p.role == "ST1" else 6.0)
        p.pos_reason = "free kick: stay up for the counter"
    markers = [p for p in pool if p not in wall]
    # Spread across the box on the line, the best in the air nearest the middle
    markers.sort(key=lambda p: -_air(p))
    lanes = [0.0, -5.0, 5.0, -10.0, 10.0, -15.0, 15.0, -19.0]
    for i, p in enumerate(markers):
        p.target = W(line_a, lanes[i % len(lanes)])
        p.state = "defend"
        p.pos_reason = "free kick: hold the line" if zone == "delivery" else "free kick: mark in the box"
    if gk:
        # The wall covers one side of the goal; the keeper stands off-centre to the other
        wall_side = 1.0 if bl > 0 else -1.0
        gk.target = W(110.0 - 1.0, -wall_side * (1.5 if zone == "shoot" else 0.5))

    # ── Attacking team ───────────────────────────────────────────────────
    others = [p for p in field_att if p is not taker]
    n_box = FK_BOX_ATTACKERS if zone == "delivery" else FK_SHOOT_ATTACKERS
    box = sorted(others, key=lambda p: -_air(p))[:n_box]
    rest = [p for p in others if p not in box]
    # Keep the quickest defenders back, the best passer on the edge of the box
    back = sorted(rest, key=lambda p: (p.role not in ("LCB", "RCB", "LB", "RB"),
                                       -p.attributes.get("Top Speed", 50)))[:FK_STAY_BACK]
    rest = [p for p in rest if p not in back]
    for i, p in enumerate(box):
        lane = [-4.0, 4.0, 0.0, -8.0, 8.0][i % 5]
        # Level with the defenders' line (onside), ready to attack the ball
        p.target = W(line_a - 0.5, lane + 1.5)
        p.state = "support"
        p.pos_reason = "free kick: attack the ball"
    for i, p in enumerate(rest):
        if i == 0:
            p.target = W(110.0 - 20.0, -bl * 0.3)
            p.pos_reason = "free kick: edge of the box (second ball)"
        elif zone == "shoot" and i == 1:
            p.target = ball.pos + perp * (1.2 * M_TO_PX) - goal_dir * (0.8 * M_TO_PX)
            p.pos_reason = "free kick: decoy over the ball"
        else:
            p.target = W(min(ba - 12.0, 75.0), (i - 1.5) * 10.0)
            p.pos_reason = "free kick: support"
        p.state = "support"
    for i, p in enumerate(back):
        p.target = W(55.0 + 3.0 * i, (i - 1) * 12.0)
        p.state = "support"
        p.pos_reason = "free kick: stay back"

    _dead_free_kick(ball, taker, current_time, ai_system, attacking_team_id)


def _dead_free_kick(ball, taker, current_time, ai_system, attacking_team_id):
    import core.world as world
    for p in (getattr(world, "players", None) or []):
        p.has_ball = False
    taker.has_ball     = False
    ball.owner         = None
    ball.is_dead       = True
    ball.restart_type  = "free_kick"
    ball.restart_taker = taker
    ball.restart_time  = current_time
    if ai_system:
        ai_system.last_possession_team = attacking_team_id


# ===========================================================================
# PENALTY KICK
# ===========================================================================

def setup_penalty(mechanics, attacking_team_id, team0, team1, ball, ai_system, current_time):
    """Public entry point — called from GameMechanics."""
    _setup_penalty(mechanics, attacking_team_id, team0, team1, ball, ai_system, current_time)


def _setup_penalty(mechanics, attacking_team_id, team0, team1, ball, ai_system, current_time):
    """
    Set up a penalty kick.

    • Ball at the penalty spot (11 m from goal line, centre).
    • GK on the goal line, centred.
    • All other players outside the penalty area.
    • Taker is the nearest outfield attacker to the spot.
    • 3-second delay so everyone gets into position (longer than free kick).
    """
    attack_team = team0 if attacking_team_id == 0 else team1
    defend_team = team1 if attacking_team_id == 0 else team0

    goal_x = WIDTH if attacking_team_id == 0 else 0
    sign   = -1    if attacking_team_id == 0 else 1

    # Penalty spot
    pen_spot = Vector2(goal_x + sign * 11.0 * M_TO_PX, HEIGHT / 2)

    ball.pos = Vector2(pen_spot)
    ball.vel = Vector2(0, 0)
    ball.z   = 0
    ball.vz  = 0

    # ── Taker ────────────────────────────────────────────────────────────
    field_att = [p for p in attack_team if p.role != "GK" and getattr(p, 'is_active', True)]
    if not field_att:
        return
    taker = min(field_att, key=lambda p: distance(p.pos, pen_spot))
    taker.target = Vector2(pen_spot)
    taker.state  = "idle"

    # ── All other attackers: outside the box, spread along its edge ──────
    runners = [p for p in field_att if p is not taker]
    edge_x  = goal_x + sign * 18.0 * M_TO_PX   # edge of penalty area
    for i, runner in enumerate(runners):
        spread_y = HEIGHT / 2 + (i - len(runners) / 2.0) * 3.5 * M_TO_PX
        runner.target = Vector2(clamp(edge_x, 0, WIDTH), clamp(spread_y, 0, HEIGHT))
        runner.state  = "support"

    # ── GK on goal line ───────────────────────────────────────────────────
    gk = next((p for p in defend_team if p.role == "GK"), None)
    if gk:
        gk.target = Vector2(goal_x + sign * 0.5 * M_TO_PX, HEIGHT / 2)
        gk.state  = "guard"

    # ── All other defenders outside the box too ───────────────────────────
    defend_field = [p for p in defend_team if p.role != "GK" and getattr(p, 'is_active', True)]
    for i, dp in enumerate(defend_field):
        spread_y = HEIGHT / 2 + (i - len(defend_field) / 2.0) * 3.5 * M_TO_PX
        dp.target = Vector2(clamp(edge_x, 0, WIDTH), clamp(spread_y, 0, HEIGHT))
        dp.state  = "defend"

    # ── Dead ball ─────────────────────────────────────────────────────────
    ball.owner         = None
    ball.is_dead       = True
    ball.restart_type  = "penalty"
    ball.restart_taker = taker
    ball.restart_time  = current_time
    taker.has_ball     = False

    if ai_system:
        ai_system.last_possession_team = attacking_team_id


# ===========================================================================
# CORNER KICK
# ===========================================================================

def _setup_corner_kick(mechanics, team_id, team0, team1, ball, ai_system, current_time):
    """
    Set up a corner kick for team_id.

    - Team 0 attacks RIGHT  → corner on RIGHT side (x ≈ WIDTH)
    - Team 1 attacks LEFT   → corner on LEFT  side (x ≈ 0)

    Positions are fully side-aware (near/far post calculated from which
    corner flag the ball is at).  GK is explicitly placed on the line.
    """

    # ── Ball at corner arc ────────────────────────────────────────────────
    corner_x = WIDTH - 3 if team_id == 0 else 3
    corner_y = 5.0 if ball.pos.y < HEIGHT / 2 else HEIGHT - 5.0

    ball.pos = Vector2(corner_x, corner_y)
    ball.vel = Vector2(0, 0)
    ball.z   = 0
    ball.vz  = 0

    attack_team = team0 if team_id == 0 else team1
    defend_team = team1 if team_id == 0 else team0

    field_att = [p for p in attack_team if p.role != "GK" and getattr(p, 'is_active', True)]
    if not field_att:
        _setup_goal_kick(mechanics, 1 - team_id, team0, team1, ball, ai_system, current_time)
        return

    # ── Taker ─────────────────────────────────────────────────────────────
    taker = min(field_att, key=lambda p: (p.pos - Vector2(corner_x, corner_y)).length())
    taker.target = Vector2(corner_x, corner_y)
    taker.state  = "idle"

    # ── Geometry ──────────────────────────────────────────────────────────
    goal_x = WIDTH if team_id == 0 else 0
    sign   = -1    if team_id == 0 else 1     # from goal line toward centre

    # Near / far post relative to the corner being taken
    is_top_corner = (corner_y < HEIGHT / 2)
    top_post_y    = HEIGHT / 2 - GOAL_WIDTH / 2
    bot_post_y    = HEIGHT / 2 + GOAL_WIDTH / 2
    near_post_y   = top_post_y if is_top_corner else bot_post_y
    far_post_y    = bot_post_y if is_top_corner else top_post_y
    mid_y         = HEIGHT / 2
    # spread: +1 when corner is top (y increases toward centre), -1 when bottom
    spread        = 1 if is_top_corner else -1

    # ── Attacking runners ─────────────────────────────────────────────────
    att_targets = [
        # 1. Near-post dart — tight to the near post for flick-on / early ball
        Vector2(goal_x + sign *  4.0 * M_TO_PX, near_post_y),
        # 2. Six-yard box — arrives just off-centre toward near side
        Vector2(goal_x + sign *  5.5 * M_TO_PX, mid_y - spread * 2.0 * M_TO_PX),
        # 3. Penalty spot, near side — primary header, comes from corner side
        Vector2(goal_x + sign * 11.0 * M_TO_PX, mid_y - spread * 3.5 * M_TO_PX),
        # 4. Penalty spot, centre — secondary header, fills the central channel
        Vector2(goal_x + sign * 10.0 * M_TO_PX, mid_y + spread * 1.5 * M_TO_PX),
        # 5. Far side inside the box — late runner attacking the far post
        Vector2(goal_x + sign * 11.0 * M_TO_PX, mid_y + spread * 5.5 * M_TO_PX),
        # 6. Edge of box, near side — second ball / shot if clearance falls short
        Vector2(goal_x + sign * 16.5 * M_TO_PX, mid_y - spread * 7.0 * M_TO_PX),
    ]

    runners = [p for p in field_att if p != taker]
    for i, runner in enumerate(runners[:len(att_targets)]):
        runner.target = Vector2(att_targets[i])
        runner.state  = "support"

    # ── GK: on goal line, central between the posts ───────────────────────
    gk = next((p for p in defend_team if p.role == "GK"), None)
    if gk:
        gk.target = Vector2(goal_x + sign * 1.0 * M_TO_PX, mid_y)
        gk.state  = "guard"

    # ── Outfield defenders: zonal box coverage ────────────────────────────
    def_targets = [
        # Near-post guard on line
        Vector2(goal_x + sign * 1.0  * M_TO_PX, near_post_y),
        # Far-post guard on line
        Vector2(goal_x + sign * 1.0  * M_TO_PX, far_post_y),
        # 6-yard box zone — near-post side
        Vector2(goal_x + sign * 4.5  * M_TO_PX, near_post_y + spread * 1.5 * M_TO_PX),
        # 6-yard box zone — central
        Vector2(goal_x + sign * 4.5  * M_TO_PX, mid_y),
        # 6-yard box zone — far-post side
        Vector2(goal_x + sign * 4.5  * M_TO_PX, far_post_y  - spread * 1.5 * M_TO_PX),
        # Penalty area — zone A (near side of box)
        Vector2(goal_x + sign * 10.0 * M_TO_PX, mid_y - spread * 3.5 * M_TO_PX),
        # Penalty area — zone B (far side of box)
        Vector2(goal_x + sign * 10.0 * M_TO_PX, mid_y + spread * 3.5 * M_TO_PX),
        # 18-yard line — deal with clearances
        Vector2(goal_x + sign * 16.5 * M_TO_PX, mid_y),
    ]

    defend_field = [p for p in defend_team if p.role != "GK" and getattr(p, 'is_active', True)]
    for i, dp in enumerate(defend_field[:len(def_targets)]):
        dp.target = Vector2(def_targets[i])
        dp.state  = "defend"

    # ── Dead-ball setup ───────────────────────────────────────────────────
    ball.owner         = None   # clear stale owner before locking dead ball
    ball.is_dead       = True
    ball.restart_type  = "corner_kick"
    ball.restart_taker = taker
    ball.restart_time  = current_time
    taker.has_ball     = False

    if ai_system:
        ai_system.last_possession_team = team_id

# ===========================================================================
# KICK-OFF POSITIONS
# ===========================================================================
KICKOFF_PARTNER_SIDE  = 2.5    # m: the second striker stands this far to the side of the ball...
KICKOFF_PARTNER_BACK  = 0.8    # m: ...and this far back
KICKOFF_TAKER_BACK    = 0.4    # m: the taker stands just behind the ball
KICKOFF_DEF_ST_BACK   = 10.0   # m: the other team's strikers wait this far back (outside the circle)...
KICKOFF_DEF_ST_SIDE   = 4.0    # m: ...this far either side


def kickoff_spots(team_id, kicking, taker_role="ST1"):
    """
    {role: Vector2} for a kick-off: everyone in his own half, the kicking
    team's two strikers on the ball, the other team outside the centre circle.
    """
    from config.formations import formation_positions
    from config import slots
    back = -1.0 if team_id == 0 else 1.0           # towards his own goal (x)
    centre = Vector2(WIDTH / 2, HEIGHT / 2)
    spots = {}
    for role, col, row in formation_positions(team_id):
        spot = cell_center(col, row)
        if role == "GK":
            spot.y = HEIGHT / 2
        spots[role] = spot
    strikers = [r for r in ("ST1", "ST2") if r in spots] + [r for r in ("ST",) if r in spots]
    if not strikers:                                # (nobody up front: the most advanced man kicks off)
        strikers = sorted((r for r in spots if r != "GK"), key=lambda r: -slots.row(r))[:1]
    if taker_role not in spots:
        taker_role = strikers[0]

    def _side(r):
        return 1.0 if r == "ST2" else -1.0 if r == "ST1" else (1.0 if slots.lane(r) > 0 else -1.0)
    if kicking:
        other = [r for r in strikers if r != taker_role]
        spots[taker_role] = centre + Vector2(back * KICKOFF_TAKER_BACK * M_TO_PX, 0)
        for r in other:
            side = _side(r)
            spots[r] = centre + Vector2(back * KICKOFF_PARTNER_BACK * M_TO_PX, side * KICKOFF_PARTNER_SIDE * M_TO_PX)
    else:
        for r in strikers:
            side = _side(r)
            if team_id == 1:
                side = -side
            spots[r] = centre + Vector2(back * KICKOFF_DEF_ST_BACK * M_TO_PX, side * KICKOFF_DEF_ST_SIDE * M_TO_PX)
    return spots
