# gameplay/mechanics.py
"""
Main mechanics coordinator - delegates to specialized modules.
NOW INCLUDES: Two-phase first touch system (Prepare → Execute)
🆕 UPDATED: resolve_out_of_play now accepts current_time for dead ball system
"""

from gameplay.passing import execute_pass, calculate_pass_elevation, count_defenders_in_lane
from gameplay.shooting import execute_shot
from gameplay.ball_control import apply_first_touch, execute_dribble
from gameplay.defending import (
    handle_tackles,
    check_interceptions,
    handle_loose_balls
)
from gameplay.set_pieces import (
    resolve_out_of_play,
    check_ball_out,
    check_goal,
    reset_game,
    setup_free_kick,
    setup_penalty,
)

from core.utils import distance
import random

# Taking a moving ball in your stride (Scenario 1b in handle_possession_pickup).
# A ball doesn't have to be coming straight at a player for him to take it:
# one rolling across him, or into his path as he runs, is controlled if it
# passes within reach - how reliably depends on his Control and on how fast
# the ball is moving RELATIVE to him (a ball rolling at 12 m/s into the path
# of a man running at 8 m/s is only 4 m/s relative - easy; one fizzing
# across a man standing still is hard).
ON_RUN_REACH         = 1.0    # m: anyone can reach a ball passing this close...
ON_RUN_REACH_TARGET  = 1.3    # m: ...the player it was meant for, who's set himself for it, a bit further
ON_RUN_MAX_HEIGHT    = 1.0    # m
ON_RUN_EASY_REL      = 5.0    # m/s: ball speed relative to him that's no harder than a standing pass
ON_RUN_BASE          = 0.55   # chance per attempt...
ON_RUN_PER_CONTROL   = 0.025  # ...plus per Control point (10 -> 0.80, 20 -> 1.05 before the cap)
ON_RUN_PER_REL_SPEED = 0.035  # ...minus per m/s of relative speed above ON_RUN_EASY_REL
ON_RUN_MIN, ON_RUN_MAX = 0.10, 0.95
ON_RUN_RETRY         = 0.12   # s between attempts
JUST_KICKED          = 0.25   # s after kicking it before he can touch it again

# Cutting out an opponent's pass (ai/intercepts.py sends defenders to it).
# His reach is a stretch / lunge / slide (1.0-1.8 m from Agility).  Whether he
# gets anything on it falls off the further he has to stretch and the faster
# the ball; if he does, Control decides between a clean interception and a
# touch that just knocks it loose.
CUT_TOUCH_NEAR       = 0.60   # chance per attempt of getting a touch when it's right at him...
CUT_TOUCH_STRETCH    = 0.45   # ...minus this at full stretch
CUT_NEAR             = 0.6    # m: "right at him"
CUT_FAST             = 12.0   # m/s: faster than this it's harder...
CUT_PER_MS           = 0.025  # ...by this per m/s
CUT_CLEAN_BASE       = 0.45   # a clean take (rather than knocking it loose): this...
CUT_CLEAN_PER_CONTROL = 0.03  # ...plus this per Control point (13 -> 0.84)...
CUT_CLEAN_STRETCH    = 0.30   # ...less this at full stretch...
CUT_CLEAN_FAST       = 15.0   # ...and less CUT_CLEAN_PER_MS per m/s faster than this
CUT_CLEAN_PER_MS     = 0.02
CUT_DEFLECT_TURN     = (20.0, 120.0)   # degrees a deflection sends it off its line
CUT_DEFLECT_SPEED    = (0.30, 0.70)    # ...keeping this share of its speed (a toe-poke can go anywhere)
from gameplay.goalkeeping import resolve_keeper_contact
import gameplay.ricochet as ricochet


def dist_to_ball_quick(player, ball):
    return (player.pos - ball.pos).length()
from config.constants import *


class GameMechanics:
    """
    Lightweight coordinator for all game mechanics.
    Delegates actual work to specialized modules.
    """
    from collections import Counter as _Counter
    CUT_STATS = _Counter()      # interceptions / deflections (read by sim.py)

    @staticmethod
    def _cutting_out(player, ball):
        """Is this an opponent's pass he's trying to cut out?"""
        passer_team = getattr(ball, "last_toucher_team", None)
        return (getattr(ball, "intended_target", None) is not None
                and passer_team is not None and passer_team != player.team)

    @staticmethod
    def _reach(player, ball):
        """m: how far from him a moving ball can be for him to get to it."""
        if GameMechanics._cutting_out(player, ball):
            import ai.intercepts as intercepts
            return intercepts.reach_m(player)
        if getattr(ball, "intended_target", None) is player:
            return ON_RUN_REACH_TARGET
        return ON_RUN_REACH
    
    def __init__(self):
        # Track players who are preparing to receive
        self.receiving_preparations = {}  # {player_id: context_dict}
    
    # Offensive actions
    def execute_pass(self, passer, receiver, ball, current_time, opponents=None, through_plan=None):
        return execute_pass(passer, receiver, ball, current_time, opponents, through_plan)
    
    def execute_shot(self, player, ball, current_time, opponents=None, shot_type=None):
        return execute_shot(player, ball, current_time, opponents, shot_type)
    
    def execute_cross(self, passer, receiver, ball, current_time, opponents=None, kind="cross"):
        from gameplay.crossing import execute_cross
        return execute_cross(passer, receiver, ball, current_time, opponents, kind)

    def execute_clearance(self, player, ball, current_time, kind, aim, pressured=False, first_time=False):
        import ai.clearance as clearance
        return clearance.execute(player, ball, current_time, kind, aim, pressured, first_time)

    def execute_dribble(self, dribbler, target_pos, ball, current_time, speed_mult=1.0):
        return execute_dribble(dribbler, target_pos, ball, current_time, speed_mult)
    
    # Defensive actions
    def handle_tackles(self, team0, team1, ball, current_time):
        """Returns (successful: bool, foul_info: dict | None)."""
        return handle_tackles(self, team0, team1, ball, current_time)
    
    def check_interceptions(self, team0, team1, ball, current_time):
        return check_interceptions(team0, team1, ball, current_time)
    
    def handle_loose_balls(self, all_players, ball):
        return handle_loose_balls(all_players, ball)
    
    # Ball control
    def apply_first_touch(self, receiver, ball, opponents, teammates, current_time, prepared_context=None):
        """
        Intelligent first touch system.
        Can accept pre-calculated context from preparation phase.
        """
        return apply_first_touch(receiver, ball, opponents, teammates, current_time, self, prepared_context)
    
    # Possession pickup (UPDATED with two-phase system!)
    def handle_possession_pickup(self, team0, team1, ball, current_time, ai_system):
        """
        Two-phase receiving system:
        PHASE 1 (5m): Analyze context, prepare decision
        PHASE 2 (0.5m): Execute the touch
        """
        
        # Don't pick up during dead-ball restarts or if someone already has it
        if ball.is_dead:
            return
        if ball.owner:
            return
        
        # Check if ball is close to any player - closest first, so a contested
        # ball goes to whoever is nearest (it used to go to Blue on ties,
        # because Blue's players were always checked first).
        all_players = sorted(team0 + team1, key=lambda p: distance(p.pos, ball.pos))
        
        for player in all_players:
            # Skip goalkeepers (they have their own logic) and sent-off players
            if player.role == "GK" or not getattr(player, 'is_active', True):
                continue

            # Struck too hard to control (a shot, a ricochet, a cross from
            # right next to him): it comes off him or gets past him
            # (gameplay/ricochet.py) - nobody cushions a 25 m/s shot.
            if dist_to_ball_quick(player, ball) < 3.0 * M_TO_PX and ricochet.blockable(player, ball, current_time):
                if ricochet.try_block(player, ball, current_time):
                    return
                continue
            if current_time < getattr(player, '_no_touch_until', -1.0):
                continue
            # The man who has just kicked it can't touch it again straight away
            # (a pass to someone behind him used to go back through him, and he'd
            # "receive" his own pass - sometimes several times over)
            if ball.last_toucher is player and current_time - getattr(ball, 'last_kick_time', -9.0) < JUST_KICKED:
                continue
            
            dist_to_ball = distance(player.pos, ball.pos)
            player_id = id(player)
            
            # ===================================================================
            # SCENARIO 1: RECEIVING A PASS (Ball is moving toward player)
            # ===================================================================
            if ball.vel.length() > 5.0 * M_TO_PX:  # Ball is moving
                
                # Check if ball is coming TOWARD this player
                ball_direction = ball.vel.normalize()
                to_player = (player.pos - ball.pos)
                
                if to_player.length_squared() > 0:
                    to_player_norm = to_player.normalize()
                    
                    # Dot product > 0.7 means ball is heading toward player
                    if ball_direction.dot(to_player_norm) > 0.7:
                        
                        # -------------------------------------------------------
                        # PHASE 1: PREPARATION (Ball 2-5 meters away)
                        # -------------------------------------------------------
                        if 2.0 * M_TO_PX < dist_to_ball < 5.0 * M_TO_PX:
                            
                            # Only prepare once (don't spam analysis every frame)
                            if player_id not in self.receiving_preparations:

                                # Get teammates and opponents
                                teammates = [p for p in all_players if p.team == player.team and p != player and p.role != "GK"]
                                opponents = team1 if player.team == 0 else team0

                                # Import context analysis function
                                from gameplay.ball_control import analyze_receiving_context, choose_first_touch_intent, find_first_time_outlet

                                # Analyze situation
                                context = analyze_receiving_context(player, ball, opponents, teammates)

                                # Decide what to do (but don't execute yet!)
                                if context['pressure_urgency'] in ["Immediate", "Crowded"]:
                                    outlet = find_first_time_outlet(player, teammates, opponents, context)
                                    if outlet:
                                        context['planned_action'] = 'first_time_pass'
                                        context['planned_target'] = outlet
                                    else:
                                        touch_intent, touch_direction = choose_first_touch_intent(player, context, opponents)
                                        context['planned_action'] = touch_intent
                                        context['planned_direction'] = touch_direction
                                else:
                                    touch_intent, touch_direction = choose_first_touch_intent(player, context, opponents)
                                    context['planned_action'] = touch_intent
                                    context['planned_direction'] = touch_direction

                                # Store preparation
                                self.receiving_preparations[player_id] = context
                        
                        # -------------------------------------------------------
                        # PHASE 2: EXECUTION (Ball arrives at feet < 1m)
                        # -------------------------------------------------------
                        elif dist_to_ball < 1.0 * M_TO_PX:
                            # Height gate: ball must be reachable (≤ 2.5 m off ground).
                            # Above that it's too high for feet/chest — let it bounce down.
                            if ball.z > 2.5 * M_TO_PX:
                                continue

                            # Get teammates and opponents
                            teammates = [p for p in all_players if p.team == player.team and p != player and p.role != "GK"]
                            opponents = team1 if player.team == 0 else team0
                            
                            # Use prepared context if available
                            prepared_context = self.receiving_preparations.get(player_id, None)
                            
                            # Execute first touch
                            first_timed = self.apply_first_touch(
                                player, 
                                ball, 
                                opponents, 
                                teammates, 
                                current_time,
                                prepared_context
                            )
                            
                            # Clear preparation
                            if player_id in self.receiving_preparations:
                                del self.receiving_preparations[player_id]
                            
                            if first_timed:
                                return
                            else:
                                # Ball controlled with first touch
                                ball.owner = player
                                player.has_ball = True
                                player.last_received_time = current_time
                                ball.last_toucher = player
                                ball.last_toucher_team = player.team
                                ai_system.last_possession_team = player.team
                                return

                    # ---------------------------------------------------
                    # SCENARIO 1b: TAKING IT IN HIS STRIDE
                    # The ball isn't coming straight at him - it's rolling
                    # across him, or into his path as he runs onto it.  He
                    # can take it if it passes within reach; how cleanly
                    # depends on Control and the ball's speed relative to him.
                    # ---------------------------------------------------
                    elif (dist_to_ball < self._reach(player, ball) * M_TO_PX
                          and ball.z < ON_RUN_MAX_HEIGHT * M_TO_PX):
                        rel_speed = (ball.vel - player.vel).length() / M_TO_PX
                        if current_time >= getattr(player, '_next_run_touch', -1.0):
                            player._next_run_touch = current_time + ON_RUN_RETRY
                            control = player.attributes.get("Control", 10)
                            if control > 25:
                                control /= 5.0
                            p_take = max(ON_RUN_MIN, min(ON_RUN_MAX, ON_RUN_BASE + ON_RUN_PER_CONTROL * control
                                                   - ON_RUN_PER_REL_SPEED * max(0.0, rel_speed - ON_RUN_EASY_REL)))
                            if self._cutting_out(player, ball):
                                # An opponent's pass: does he get a touch at all?
                                reach = self._reach(player, ball)
                                stretch = max(0.0, min(1.0, (dist_to_ball / M_TO_PX - CUT_NEAR)
                                                       / max(0.1, reach - CUT_NEAR)))
                                ball_ms = ball.vel.length() / M_TO_PX
                                p_touch = (CUT_TOUCH_NEAR - CUT_TOUCH_STRETCH * stretch) \
                                    * max(0.2, 1.0 - CUT_PER_MS * max(0.0, ball_ms - CUT_FAST))
                                if random.random() >= p_touch:
                                    continue
                                p_clean = CUT_CLEAN_BASE + CUT_CLEAN_PER_CONTROL * control \
                                    - CUT_CLEAN_STRETCH * stretch - CUT_CLEAN_PER_MS * max(0.0, ball_ms - CUT_CLEAN_FAST)
                                if random.random() >= p_clean:
                                    # Just a toe on it - it's knocked loose
                                    turn = random.uniform(*CUT_DEFLECT_TURN) * random.choice((-1.0, 1.0))
                                    ball.vel = ball.vel.rotate(turn) * random.uniform(*CUT_DEFLECT_SPEED)
                                    ball.intended_target = None
                                    ball.last_toucher = player
                                    ball.last_toucher_team = player.team
                                    player._next_run_touch = current_time + 0.4
                                    GameMechanics.CUT_STATS["deflected"] += 1
                                    return
                                GameMechanics.CUT_STATS["intercepted"] += 1
                                p_take = 1.0
                            if random.random() < p_take:
                                ball.owner = player
                                player.has_ball = True
                                player.last_received_time = current_time
                                ball.last_toucher = player
                                ball.last_toucher_team = player.team
                                ai_system.last_possession_team = player.team
                                if id(player) in self.receiving_preparations:
                                    del self.receiving_preparations[id(player)]
                                return

            # ===================================================================
            # SCENARIO 2: PICKING UP LOOSE BALL (Ball is stationary or slow)
            # ===================================================================
            elif dist_to_ball < POSSESSION_DIST:
                # Height gate: ball must be on or very near the ground (≤ 0.8 m).
                # A bouncing/aerial ball needs to land before it can be picked up.
                if ball.z > 0.8 * M_TO_PX:
                    continue

                # Simple pickup (no first touch needed for loose balls)
                ball.owner = player
                player.has_ball = True
                player.last_received_time = current_time
                ball.last_toucher = player
                ball.last_toucher_team = player.team
                ai_system.last_possession_team = player.team

                # Clear any preparations
                if id(player) in self.receiving_preparations:
                    del self.receiving_preparations[id(player)]
                return
    
    # Set pieces & match flow - 🆕 UPDATED SIGNATURE
    def resolve_out_of_play(self, ball, last_touch_team, team0, team1, ai_system, current_time):
        """
        🆕 NOW PASSES current_time FOR DEAD BALL SYSTEM
        """
        return resolve_out_of_play(self, ball, last_touch_team, team0, team1, ai_system, current_time)
    
    def check_ball_out(self, ball):
        return check_ball_out(ball)
    
    def check_goal(self, ball):
        return check_goal(ball)
    
    def reset_game(self, team0, team1, ball, ai_system):
        return reset_game(team0, team1, ball, ai_system)

    def setup_free_kick(self, attacking_team_id, foul_pos, team0, team1, ball, ai_system, current_time):
        return setup_free_kick(self, attacking_team_id, foul_pos, team0, team1, ball, ai_system, current_time)

    def setup_penalty(self, attacking_team_id, team0, team1, ball, ai_system, current_time):
        return setup_penalty(self, attacking_team_id, team0, team1, ball, ai_system, current_time)
    
    # Goalkeeper dive state machine and ball interaction
    def update_goalkeeper_dive_states(self, team0, team1, current_time):
        """
        Manages GK dive state transitions:
          • preparing → diving  (after reaction delay)
          • diving    → recover (timeout if ball is never caught / parried —
                                 prevents GK getting stuck at dive target forever)
        """
        # Maximum time the GK spends in the actual diving phase.
        # If a shot misses both catch and parry radius, this pulls them back.
        DIVE_MAX_DURATION = 0.65  # seconds of actual diving before auto-recovery

        for team in (team0, team1):
            keeper = next((p for p in team if p.role == "GK"), None)
            if not keeper:
                continue

            if keeper.dive_state == "preparing":
                time_preparing = current_time - keeper.dive_start_time
                if time_preparing >= keeper.dive_reaction:
                    keeper.dive_state = "diving"

            elif keeper.dive_state == "diving":
                # dive_start_time is when "preparing" began; subtract reaction to get
                # how long we have been in the actual dive phase.
                actual_dive_duration = (current_time - keeper.dive_start_time) - keeper.dive_reaction
                if actual_dive_duration > DIVE_MAX_DURATION:
                    keeper.dive_state = "recover"
                    keeper.last_dive_time = current_time

    def handle_goalkeeper_interactions(self, team0, team1, ball, current_time, ai_system):
        """
        After movement, check if the GK's position overlaps the ball close enough
        to catch or parry it.  Also handles standing collection of slow balls.
        """
        import random
        from pygame.math import Vector2

        if ball.is_dead:
            return
        if ball.owner is not None:
            return

        for team in (team0, team1):
            keeper = next((p for p in team if p.role == "GK"), None)
            if not keeper:
                continue

            # Only act when ball is inside or just outside the penalty area
            if keeper.team == 0:
                box_x_min, box_x_max = -10, KEEPER_BOX_DEPTH + 15
            else:
                box_x_min, box_x_max = WIDTH - KEEPER_BOX_DEPTH - 15, WIDTH + 10

            if not (box_x_min <= ball.pos.x <= box_x_max):
                continue

            # Save / claim resolution lives in gameplay/goalkeeping.py
            if resolve_keeper_contact(keeper, ball, current_time, ai_system):
                return
