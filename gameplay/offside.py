import pygame
from pygame.math import Vector2
from core.utils import distance
from config.constants import OFFSIDE_MARGIN, WIDTH, HEIGHT, FIELD_MARGIN, M_TO_PX

class OffsideSystem:
    """
    SIMPLE OFFSIDE RULES:
    
    1. When YOUR TEAMMATE kicks the ball, we take a "photo" 📸
    2. You're in an OFFSIDE POSITION if there aren't 2 defenders between you and the goal
    3. You're only PENALIZED if you get within 1 meter of the ball in the next 3 seconds
    4. That's it!
    
    🆕 NOW WITH DEAD BALL FREE KICKS - No more instant restarts!
    """
    
    def __init__(self):
        # Is offside currently active?
        self.offside_detected = False
        self.offside_team = None
        self.offside_player = None
        self.detection_time = 0.0
        self.offside_line_x = 0
        
        # SNAPSHOT SYSTEM - The "photo" we take when ball is kicked
        self.last_pass_snapshot = None
        self.snapshot_time = 0.0
        self.snapshot_team = None   # which team's pass the photo belongs to
        
        # ACTIVE MONITORING - Track players in offside positions
        self.players_being_watched = []  # List of (player, time_started_watching)
        
        # Settings
        self.INVOLVEMENT_TIME = 3.0  # 3 seconds to get involved
        self.INVOLVEMENT_DISTANCE = 1.0 * M_TO_PX  # 1 meter from ball
        self.RESET_DELAY = 2.0  # How long to show offside before free kick
        
    def check_offside(self, passing_team, receiving_team, ball, current_time):
        """
        MAIN OFFSIDE CHECK
        
        Step 1: Did a teammate just kick the ball? Take a photo!
        Step 2: Who's in an offside position? Start watching them!
        Step 3: Did any watched player get within 1m of ball? OFFSIDE!
        """
        
        # Already flagged? Don't check again
        if self.offside_detected:
            return False
        
        attacker_team_id = passing_team[0].team
        
        # ==================================================================
        # STEP 1: IS THIS A NEW PASS FROM A TEAMMATE?
        # ==================================================================
        is_new_pass = (
            ball.pass_start_pos is not None and
            current_time - ball.last_pass_time < 0.1
        )
        
        if is_new_pass:
            # Check: Did a TEAMMATE kick it?
            if hasattr(ball, 'last_owner') and ball.last_owner:
                if ball.last_owner.team != attacker_team_id:
                    # Opponent kicked it - OUR earlier photo no longer counts.
                    # (Only clear our own photo: this used to wipe the other
                    # team's brand-new photo too, and because both teams share
                    # this object, Red's offsides were then judged as Blue's.)
                    if self.snapshot_team == attacker_team_id:
                        self.last_pass_snapshot = None
                        self.players_being_watched = []
                    return False
            
            # 📸 CLICK! Take a photo of everyone RIGHT NOW
            self._create_position_snapshot(passing_team, receiving_team, ball, current_time)
            
            # Start watching players who are in offside positions
            self._identify_offside_positions(passing_team, receiving_team, ball, current_time)
        
        # No snapshot of OUR pass? Nothing to check
        if self.last_pass_snapshot is None or self.snapshot_team != attacker_team_id:
            return False
        
        # ==================================================================
        # STEP 2: CLEAN UP OLD WATCHES (Past 3 seconds)
        # ==================================================================
        self.players_being_watched = [
            (player, start_time) 
            for player, start_time in self.players_being_watched 
            if current_time - start_time <= self.INVOLVEMENT_TIME
        ]
        
        # If no one is being watched anymore, clear the snapshot
        if not self.players_being_watched:
            self.last_pass_snapshot = None
            return False
        
        # ==================================================================
        # STEP 3: CHECK IF ANY WATCHED PLAYER GOT INVOLVED
        # ==================================================================
        for player, start_time in self.players_being_watched:
            
            # Did they get within 1 meter of the ball?
            dist_to_ball = distance(player.pos, ball.pos)
            
            if dist_to_ball < self.INVOLVEMENT_DISTANCE:
                # 🚩 OFFSIDE! They got involved!
                self.offside_detected = True
                self.offside_team = attacker_team_id
                self.offside_player = player
                self.detection_time = current_time
                
                # Store the offside line for drawing
                snapshot = self.last_pass_snapshot
                if snapshot and 'offside_line_x' in snapshot:
                    self.offside_line_x = snapshot['offside_line_x']
                
                # Clear watches
                self.players_being_watched = []
                self.last_pass_snapshot = None
                
                return True
        
        return False
    
    def _create_position_snapshot(self, passing_team, receiving_team, ball, current_time):
        """
        📸 TAKE A PHOTO!
        
        Remember exactly where everyone was when the ball was kicked.
        """
        self.last_pass_snapshot = {
            'attackers': [Vector2(p.pos) for p in passing_team],
            # (sent-off players are parked off the pitch - they don't count)
            'defenders': [Vector2(p.pos) for p in receiving_team if getattr(p, 'is_active', True)],
            'ball_pos': Vector2(ball.pass_start_pos if ball.pass_start_pos else ball.pos),
            'offside_line_x': 0  # Will be calculated next
        }
        self.snapshot_time = current_time
        self.snapshot_team = passing_team[0].team
    
    def _identify_offside_positions(self, passing_team, receiving_team, ball, current_time):
        """
        🔍 WHO'S IN AN OFFSIDE POSITION?
        
        For each attacker:
        1. Are they closer to the goal than the ball? 
        2. Are there 2 defenders between them and the goal?
           (NOTE: The GOALKEEPER counts as one of these 2 defenders!)
        3. If NO to question 2 → They're in an OFFSIDE POSITION → Start watching them!
        """
        
        attacker_team_id = passing_team[0].team
        snapshot = self.last_pass_snapshot
        
        # Where's the goal we're attacking?
        if attacker_team_id == 0:
            goal_x = WIDTH  # Blue attacks Right →
        else:
            goal_x = 0  # Red attacks Left ←
        
        # Get all defender positions from the snapshot
        defender_positions = snapshot['defenders']
        ball_pos = snapshot['ball_pos']
        
        # Start fresh watch list
        self.players_being_watched = []
        
        # ==================================================================
        # FOR EACH ATTACKER
        # ==================================================================
        for i, attacker in enumerate(passing_team):
            
            # Skip the player who kicked the ball
            if attacker == ball.last_owner or attacker.has_ball or not getattr(attacker, 'is_active', True):
                continue
            
            # Get their position from the snapshot
            attacker_pos = snapshot['attackers'][i]
            
            # ==============================================================
            # CHECK 1: Are they ahead of the ball?
            # ==============================================================
            if attacker_team_id == 0:  # Blue attacking Right
                ahead_of_ball = attacker_pos.x > (ball_pos.x + OFFSIDE_MARGIN)
            else:  # Red attacking Left
                ahead_of_ball = attacker_pos.x < (ball_pos.x - OFFSIDE_MARGIN)
            
            # If not ahead of ball, they can't be offside
            if not ahead_of_ball:
                continue
            
            # ==============================================================
            # CHECK 2: How many defenders are between them and the goal?
            # ==============================================================
            defenders_between = 0
            
            for def_pos in defender_positions:
                # Is this defender between the attacker and the goal?
                if attacker_team_id == 0:  # Blue attacking Right
                    if def_pos.x > attacker_pos.x:
                        defenders_between += 1
                else:  # Red attacking Left
                    if def_pos.x < attacker_pos.x:
                        defenders_between += 1
            
            # ==============================================================
            # VERDICT: Less than 2 defenders? OFFSIDE POSITION!
            # ==============================================================
            if defenders_between < 2:
                # Start watching this player!
                self.players_being_watched.append((attacker, current_time))
                
                # Store the offside line.
                # FIFA rule: offside line = the SECOND-to-last defender
                # (the last defender = GK, sorted_defs[0]; the second-last
                # outfield defender = sorted_defs[1] — that's the offside line).
                if defender_positions:
                    if attacker_team_id == 0:
                        sorted_defs = sorted(defender_positions, key=lambda p: p.x, reverse=True)
                    else:
                        sorted_defs = sorted(defender_positions, key=lambda p: p.x)

                    if len(sorted_defs) >= 2:
                        snapshot['offside_line_x'] = sorted_defs[1].x
                    elif len(sorted_defs) == 1:
                        snapshot['offside_line_x'] = sorted_defs[0].x
    
    def update_reset_logic(self, team0, team1, ball, current_time):
        """
        ⏰ RESET TIMER
        
        After offside is called, wait 2 seconds then give a free kick
        🆕 NOW PASSES current_time TO FREE KICK SETUP
        """
        if not self.offside_detected:
            return
        
        # Has enough time passed?
        if current_time - self.detection_time > self.RESET_DELAY:
            self._execute_free_kick_reset(team0, team1, ball, current_time)
    
    def _execute_free_kick_reset(self, team0, team1, ball, current_time):
        """
        ⚽ FREE KICK SETUP
        
        The defending team gets the ball where offside happened
        🆕 NOW USES DEAD BALL SYSTEM - No more instant kicks!
        """
        
        # Who gets the free kick? The defending team!
        defending_team = team1 if self.offside_team == 0 else team0
        
        # Put ball at the offside line (safe Y position)
        safe_y = max(30, min(HEIGHT - 30, ball.pos.y))
        free_kick_pos = Vector2(self.offside_line_x, safe_y)
        
        # Find nearest defender to take it
        eligible_takers = [p for p in defending_team if p.role != "GK" and getattr(p, 'is_active', True)]
        if eligible_takers:
            taker = min(eligible_takers, key=lambda p: distance(p.pos, free_kick_pos))
            
            # Move ball and taker to position
            ball.pos = Vector2(free_kick_pos)
            ball.vel = Vector2(0, 0)
            ball.z = 0
            ball.vz = 0
            
            # (He used to be teleported onto the ball - now he walks over to
            # it like any other restart taker.)  Take the ball off whoever
            # had it - the offside player used to keep "owning" the dead
            # ball and walk around with it until a safety timer ran out.
            for p in team0 + team1:
                p.has_ball = False
            ball.owner = None
            
            # === 🆕 DEAD BALL SETUP (instead of ball.owner) ===
            ball.is_dead = True
            ball.restart_type = "offside"
            ball.restart_taker = taker
            ball.restart_time = current_time
            
            # Taker doesn't "have" it yet (prevents instant pass)
            taker.has_ball = False
            
        # Clear the offside flag
        self.offside_detected = False
        self.offside_team = None
        self.offside_player = None
        self.last_pass_snapshot = None
        self.players_being_watched = []
    
    def clear_offside_on_possession_change(self, ball):
        """
        🔄 CLEAR ON POSSESSION CHANGE
        
        If the ball changes teams, clear everything
        """
        if self.offside_detected:
            return  # Don't clear if we're waiting for free kick
        
        # Clear snapshot and watches if possession changed
        if hasattr(ball, 'owner') and ball.owner:
            self.last_pass_snapshot = None
            self.players_being_watched = []
    
    def draw_offside_line(self, surface, offside_line_x, team_attacking):
        """
        📏 DRAW THE OFFSIDE LINE
        
        Show a yellow dashed line where the defender(s) were
        """
        x_pos = FIELD_MARGIN + int(offside_line_x)
        
        # Draw dashed yellow line
        dash_length = 15
        gap_length = 10
        
        y = FIELD_MARGIN
        while y < FIELD_MARGIN + HEIGHT:
            pygame.draw.line(
                surface, 
                (255, 255, 0),  # Yellow
                (x_pos, y), 
                (x_pos, min(y + dash_length, FIELD_MARGIN + HEIGHT)), 
                3  # Line thickness
            )
            y += dash_length + gap_length
        
        # Draw a circle marker at top of line
        indicator_y = FIELD_MARGIN + 10
        pygame.draw.circle(surface, (255, 255, 0), (x_pos, indicator_y), 8)
        pygame.draw.circle(surface, (255, 0, 0), (x_pos, indicator_y), 4)
