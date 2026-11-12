import pygame
from pygame.math import Vector2
from config.constants import *
from core.utils import distance, clamp
import core.clock as game_clock
import core.locomotion as locomotion
import core.fatigue as fatigue
import random
import math

class Ball:
    def __init__(self, position):
        self.pos = Vector2(position)
        self.vel = Vector2(0, 0)
        self.z = 0.0
        self.vz = 0.0
        
        self.owner = None
        self.last_kick_time = -10.0
        self.last_pass_time = -10.0
        self.pass_start_pos = None
        self.intended_target = None 
        
        # === NEW: DEAD BALL RESTART SYSTEM ===
        self.is_dead = False
        self.restart_type = None  # "goal_kick", "throw_in", "corner_kick", etc.
        self.restart_taker = None
        self.restart_time = 0.0

        # === LAST TOUCHER TRACKING (for corner/goal-kick decisions) ===
        self.last_toucher      = None
        self.last_toucher_team = None
        # second-to-last toucher — used for assist detection
        self.prev_toucher      = None

    def update(self, delta_time, current_time):
        # === DEAD BALL: Ball is frozen (can't be dribbled or moved) ===
        if self.is_dead:
            self.vel = Vector2(0, 0)
            self.z = 0
            self.vz = 0
            # Ball stays exactly where it was placed - no movement!
            return
        
        # === LIVE BALL: Normal physics ===
        if self.owner:
            self.z = 0; self.vz = 0
            if self.owner.facing.length_squared() > 0:
                offset = self.owner.facing * (PLAYER_RADIUS + BALL_RADIUS + 2)
            else:
                offset = Vector2(PLAYER_RADIUS + BALL_RADIUS, 0)
            target_pos = self.owner.pos + offset
            # lerp 0.5 — equilibrium lag ≈ speed / 0.5 ≈ 3 px (barely noticeable).
            # Velocity-based facing (set after movement) now prevents facing-jitter,
            # so the old reason for reducing this to 0.15 no longer applies.
            self.pos = self.pos.lerp(target_pos, 0.5)
            self.vel = self.owner.vel 
        else:
            self._arrival_speed = self.vel.length() / M_TO_PX   # how it's arriving (ai/clearance.py)
            self._arrival_z = self.z / M_TO_PX
            self.pos += self.vel * delta_time
            
            friction = 0.995 if self.z > 0.1 else 0.992
            self.vel *= (friction ** (delta_time * 60)) 

            self.z += self.vz * delta_time
            self.vz -= GRAVITY * delta_time 
            
            if self.z < 0:
                self.z = 0
                if abs(self.vz) > 20: self.vz = -self.vz * BOUNCE_FACTOR
                else: self.vz = 0
            
            if self.vel.length_squared() < 2 and self.z == 0: self.vel = Vector2(0, 0)
            # Allow ball to cross the touchlines (needed for throw-in / corner detection)
            # Clamp generously so the ball stays on-screen but CAN go out of play
            self.pos.x = clamp(self.pos.x, -30, WIDTH + 30)
            self.pos.y = clamp(self.pos.y, -30, HEIGHT + 30)

    def kick(self, velocity, kicker=None, elevation=0.0):
        """Execute a kick - automatically ends dead ball state"""
        # === TAKING A RESTART ===
        if self.is_dead:
            self.is_dead = False
            self.restart_type = None
            self.restart_taker = None
        
        # Track last toucher for corner/goal-kick decisions
        if kicker is not None:
            self.last_toucher = kicker
            self.last_toucher_team = kicker.team
            self.last_kick_team = kicker.team      # who actually kicked it (pick-ups don't change this)
            if kicker.role == "GK":
                # Don't let the keeper catch his own kick the moment it leaves his
                # hands (he used to re-claim it and "pass" again for several frames)
                kicker._no_touch_until = game_clock.now() + 0.5
        
        self.owner = None
        self.vel = Vector2(velocity)
        if elevation > 0:
            speed = velocity.length()
            self.vz = speed * elevation * 0.8 
        else: self.vz = 0
        self.last_pass_time = game_clock.now()   # game time, not wall-clock
        if kicker: self.pass_start_pos = Vector2(kicker.pos)


class Player:
    def __init__(self, team, role, pos, idx, attributes=None):
        self.team = team
        self.role = role                   # the behaviour kind (config/slots.py proxy - the 4-4-2 names)
        self.slot = role                   # his spot in the formation (config/slots.py)
        self.pos = Vector2(pos)
        self.vel = Vector2(0, 0)
        self.target = Vector2(pos)
        self.has_ball = False
        self.idx = idx
        self.state = "idle"
        fatigue.init(self)                 # stamina + sprint energy (core/fatigue.py)
        self.last_tackle_time = -10.0
        self.last_pass_time = -10.0
        self.name = role 
        self.facing = Vector2(1, 0) if team == 0 else Vector2(-1, 0)
        self.last_decision_time = 0.0
        self.current_run_type    = "hold"  # Off-ball run this player is executing
        self.run_committed_until = 0.0     # Don't pick a new run before this time

        # ── Discipline ────────────────────────────────────────────────────────
        self.yellow_cards  = 0      # bookings this match
        self.red_card      = False  # True when sent off
        self.is_active     = True   # False when red-carded (removed from pitch)
        self.last_foul_time = -99.0 # timestamp of last foul committed

        # RL agent hook – set to an RLAgent instance to override normal AI
        self.rl_agent = None

        raw_attributes = attributes if attributes else self._get_default_attributes()
        self.attributes = self._normalize_attributes(raw_attributes)
        
        if attributes and "Name" in attributes: self.name = attributes["Name"]
        self._init_keeper_attributes()

    def _get_default_attributes(self):
        return {
            "Acceleration": 10, "Top Speed": 10, "Agility": 10, "Physical": 10, 
            "Finishing": 10, "Passing": 10, "Dribbling": 10, "Control": 10,
            "Tackling": 10, "Defending": 10, "Composure": 10, "Anticipation": 10, 
            "Interceptions": 10, "Reflexes": 10, "Handling": 10, "Positioning": 10
        }

    def _normalize_attributes(self, attrs):
        normalized = {}
        for key, value in attrs.items():
            if key == "Name" or isinstance(value, str):
                normalized[key] = value
                continue
            if isinstance(value, (int, float)):
                if value > 25: normalized[key] = value / 5.0
                else: normalized[key] = value
            else: normalized[key] = value
        return normalized

    def _init_keeper_attributes(self):
        if self.role != "GK": return
        self.last_dive_time = -10.0; self.dive_cooldown = KEEPER_DIVE_COOLDOWN
        self.dive_state = "idle"; self.dive_target = Vector2(self.pos)
        self.dive_reaction = KEEPER_DIVE_REACTION; self.dive_speed = KEEPER_DIVE_SPEED
        self.dive_start_time = 0.0; self.catch_radius = KEEPER_CATCH_RADIUS
        self.parry_radius = KEEPER_PARRY_RADIUS; self.recover_time = KEEPER_RECOVER_TIME
        # Dive speed, reaction and reach now come from Shot Stopping
        from gameplay.goalkeeping import init_keeper
        init_keeper(self)

    def update(self, delta_time, all_players=None):
        if not self.is_active:
            return                       # sent off - he's left the pitch
        if self.role == "GK" and self.dive_state == "diving":
            self._update_diving_movement(delta_time)
            return
        self._update_normal_movement(delta_time, all_players)

    def _update_diving_movement(self, delta_time):
        to_target = self.dive_target - self.pos
        distance_to_target = to_target.length()
        if distance_to_target > 1:
            move = to_target.normalize() * min(self.dive_speed * delta_time, distance_to_target)
            self.pos += move; self.vel = move / max(delta_time, 1e-6)
            if self.vel.length_squared() > 0: self.facing = self.vel.normalize()
        else: self.vel = Vector2(0, 0)

    def _update_normal_movement(self, delta_time, all_players=None):
        if self.role == "GK":
            # Keepers keep their simple positional movement (diving has its own code)
            to_target = self.target - self.pos
            dist_sq = to_target.length_squared()
            if dist_sq > 4:
                speed = self._calculate_movement_speed()
                move = to_target.normalize() * min(speed * delta_time, math.sqrt(dist_sq))
                self.pos += move; self.vel = move / max(delta_time, 1e-6)
            else:
                self.vel = Vector2(0, 0)
            self.facing = Vector2(1, 0) if self.team == 0 else Vector2(-1, 0)
            fatigue.update(self, delta_time)
            return

        # Outfield players: realistic acceleration, braking and turning
        # (see core/locomotion.py for how it works and the tuning numbers)
        locomotion.step(self, delta_time, all_players)

        fatigue.update(self, delta_time)

    def _calculate_acceleration(self):
        accel_stat = self.attributes.get("Acceleration", 10)
        base_accel = 50.0
        bonus_accel = accel_stat * 5.0
        return (base_accel + bonus_accel) * M_TO_PX * 0.35

    def _calculate_movement_speed(self):
        top_speed_stat = self.attributes.get("Top Speed", 10)
        MIN_REAL_SPEED = 7.5; MAX_REAL_SPEED = 10.5 
        speed_range = MAX_REAL_SPEED - MIN_REAL_SPEED
        progress = (top_speed_stat - 1) / 19.0
        player_ms = MIN_REAL_SPEED + (progress * speed_range)
        base_speed = player_ms * M_TO_PX
        base_speed *= (0.7 + 0.3 * self.stamina)
        
        if self.state == "press":
            return base_speed * 1.05            # closing down — slight boost
        elif self.state == "chase":
            return base_speed * 1.0             # chasing / receiving ball — full sprint
        elif self.state == "run":
            return base_speed * 1.0             # committed off-ball run — full sprint
        elif self.state == "dribble":
            dribble_stat = self.attributes.get("Dribbling", 10)
            dribble_efficiency = 0.80 + (dribble_stat / 20.0) * 0.15
            # _dribble_speed_mult is set by execute_dribble so the carrier layer
            # can request shield-slow (0.25×) or sidestep-fast (1.1×) etc.
            mult = getattr(self, '_dribble_speed_mult', 1.0)
            return base_speed * dribble_efficiency * mult
        elif self.state == "shield":
            # Ball-shielding: player barely creeps, using body to block defender.
            # speed_mult=0.25 from carrier.py applies here via _dribble_speed_mult
            # stored before state was flipped to "shield".
            mult = getattr(self, '_dribble_speed_mult', 0.25)
            return base_speed * mult
        elif self.state == "support":
            return base_speed * 0.65            # jogging purposefully into position
        elif self.state == "defend":
            return base_speed * 0.70            # jogging back into defensive shape
        elif self.state == "hold":
            return base_speed * 0.10            # planted — barely creeping
        elif self.state == "walk":
            return min(base_speed, 1.6 * M_TO_PX)   # dead ball: walking into position
        else:
            return base_speed * 0.80            # default jog for any unlisted state
