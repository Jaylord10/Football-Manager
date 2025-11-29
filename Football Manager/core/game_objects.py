import pygame
from pygame.math import Vector2
from config.constants import *
from core.utils import clamp

class Ball:
    def __init__(self, position):
        self.pos = Vector2(position)
        self.vel = Vector2(0, 0)
        self.owner = None
        self.last_kick_time = -10.0
        self.last_pass_time = -10.0
        self.pass_start_pos = None

    def update(self, delta_time, current_time):
        """Update ball position and physics."""
        if self.owner:
            # Ball follows owner
            direction = self.owner.vel.normalize() if self.owner.vel.length_squared() > 0 else Vector2(1, 0)
            offset = direction * (PLAYER_RADIUS + BALL_RADIUS + 2)
            self.pos = self.owner.pos + offset
            self.vel = Vector2(0, 0)
        else:
            # Ball physics
            self.pos += self.vel * delta_time
            self.vel *= (0.99 ** (delta_time * 60))  # FPS-normalized friction
            if self.vel.length_squared() < 2:
                self.vel = Vector2(0, 0)
            
            # Keep ball in bounds
            self.pos.x = clamp(self.pos.x, -8, WIDTH + 8)
            self.pos.y = clamp(self.pos.y, 0, HEIGHT)

    def kick(self, velocity, kicker=None):
        """Kick the ball with given velocity."""
        self.owner = None
        self.vel = Vector2(velocity)
        self.last_pass_time = pygame.time.get_ticks() / 1000.0
        
        if kicker:
            self.pass_start_pos = Vector2(kicker.pos)
            if self.vel.length() > 1:
                self.pos = Vector2(kicker.pos) + self.vel.normalize() * (PLAYER_RADIUS + BALL_RADIUS + 1)


class Player:
    """Represents a football player with movement, AI, and state."""
    
    def __init__(self, team, role, pos, idx):
        self.team = team
        self.role = role
        self.pos = Vector2(pos)
        self.vel = Vector2(0, 0)
        self.target = Vector2(pos)
        self.has_ball = False
        self.idx = idx
        self.state = "idle"
        self.stamina = 1.0
        self.last_tackle_time = -10.0

        # Keeper-specific attributes
        self._init_keeper_attributes()

    def _init_keeper_attributes(self):
        """Initialize goalkeeper-specific attributes."""
        if self.role != "GK":
            return
            
        self.last_dive_time = -10.0
        self.dive_cooldown = KEEPER_DIVE_COOLDOWN
        self.dive_state = "idle"  # idle / preparing / diving / recover
        self.dive_target = Vector2(self.pos)
        self.dive_reaction = KEEPER_DIVE_REACTION
        self.dive_speed = KEEPER_DIVE_SPEED
        self.dive_start_time = 0.0
        self.catch_radius = KEEPER_CATCH_RADIUS
        self.parry_radius = KEEPER_PARRY_RADIUS
        self.recover_time = KEEPER_RECOVER_TIME

    def update(self, delta_time):
        """Update player position and state."""
        if self.role == "GK" and self.dive_state == "diving":
            self._update_diving_movement(delta_time)
            return
            
        self._update_normal_movement(delta_time)

    def _update_diving_movement(self, delta_time):
        """Handle goalkeeper diving movement."""
        to_target = self.dive_target - self.pos
        distance_to_target = to_target.length()
        
        if distance_to_target > 1:
            move = to_target.normalize() * min(self.dive_speed * delta_time, distance_to_target)
            self.pos += move
            self.vel = move / max(delta_time, 1e-6)
        else:
            self.vel = Vector2(0, 0)

    def _update_normal_movement(self, delta_time):
        """Handle normal player movement."""
        to_target = self.target - self.pos
        distance_to_target = to_target.length()
        
        if distance_to_target > 2:
            speed = self._calculate_movement_speed()
            move = to_target.normalize() * min(speed * delta_time, distance_to_target)
            self.pos += move
            self.vel = move / max(delta_time, 1e-6)
            self._update_stamina(delta_time, True)
        else:
            self.vel = Vector2(0, 0)
            self._update_stamina(delta_time, False)

    def _calculate_movement_speed(self):
        """Calculate movement speed based on state and stamina."""
        base_speed = MAX_SPEED * (0.6 + 0.4 * self.stamina)
        
        if self.state == "press":
            return min(MAX_SPEED * 1.2, base_speed * 1.3)
        elif self.state == "dribble":
            return DRIBBLE_SPEED
        elif self.state == "chase":
            return min(MAX_SPEED * 1.15, base_speed * 1.15)
        else:
            return base_speed

    def _update_stamina(self, delta_time, is_moving):
        """Update player stamina based on movement."""
        if is_moving:
            drain_rate = 0.0008 * (self.vel.length() / MAX_SPEED) * (delta_time * 60)
            if self.state == "press":
                drain_rate *= 1.6
            self.stamina = clamp(self.stamina - drain_rate + 0.0009 * (delta_time * 60) / 60, 0.25, 1.0)
        else:
            self.stamina = clamp(self.stamina + 0.0016 * (delta_time * 60), 0.0, 1.0)

    def draw(self, surface, font):
        """Draw the player on the surface."""
        color = BLUE if self.team == 0 else RED
        screen_pos = (int(self.pos.x) + FIELD_MARGIN, int(self.pos.y) + FIELD_MARGIN)
        
        # Draw player circle
        pygame.draw.circle(surface, color, screen_pos, PLAYER_RADIUS)
        pygame.draw.circle(surface, BLACK, screen_pos, PLAYER_RADIUS, 2)
        
        # Draw role label
        label = font.render(self.role, True, BLACK)
        surface.blit(label, (self.pos.x - 20 + FIELD_MARGIN, self.pos.y - 28 + FIELD_MARGIN))
        
        # Draw ball indicator if player has ball
        if self.has_ball:
            pygame.draw.circle(surface, YELLOW, screen_pos, PLAYER_RADIUS // 2)
        
        # Draw stamina bar
        self._draw_stamina_bar(surface, screen_pos)

    def _draw_stamina_bar(self, surface, screen_pos):
        """Draw player stamina bar."""
        bar_width = 28
        x = int(self.pos.x - bar_width / 2) + FIELD_MARGIN
        y = int(self.pos.y + PLAYER_RADIUS + 6) + FIELD_MARGIN
        
        pygame.draw.rect(surface, (50, 50, 50), (x, y, bar_width, 6))
        pygame.draw.rect(surface, (60, 200, 80), (x, y, int(bar_width * self.stamina), 6))