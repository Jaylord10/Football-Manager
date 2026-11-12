# Game Constants - Organized by category

# Pitch Dimensions
PITCH_M_W, PITCH_M_H = 110, 70  # meters
M_TO_PX = 10
WIDTH, HEIGHT = int(PITCH_M_W * M_TO_PX), int(PITCH_M_H * M_TO_PX)
FIELD_MARGIN = 20

# Grid Configuration
GRID_COLS, GRID_ROWS = 24, 16
CELL_W, CELL_H = WIDTH / GRID_COLS, HEIGHT / GRID_ROWS

# Object Sizes
PLAYER_RADIUS = int(0.6 * M_TO_PX)
BALL_RADIUS = int(0.32 * M_TO_PX)

# Speeds (m/s converted to px/s)
MAX_SPEED_M = 10.5
MAX_SPEED = MAX_SPEED_M * M_TO_PX
DRIBBLE_SPEED = 9.5 * M_TO_PX
PASS_SPEED = 25.0 * M_TO_PX
SHOT_SPEED = 38.0 * M_TO_PX

# Gameplay Constants
TACKLE_DISTANCE = 2.5 * M_TO_PX
TACKLE_CHANCE = 0.4
TACKLE_COOLDOWN = 1.0
POSSESSION_DIST = PLAYER_RADIUS + BALL_RADIUS + 4
MIN_PASS_DIST = 8.0 * M_TO_PX
PASS_LEAD_FACTOR = 0.5
PASS_ERROR_RATIO = 0.06
SHOT_ERROR_RATIO = 0.14
FIRST_TO = 5

# Match Structure
HALF_DURATION_REAL = 45 * 60.0   # a full 45 minutes of football per half (like Football Manager:
                                 # watch it sped up - see MATCH_SPEEDS)
HALFTIME_DURATION  =   5.0   # 5 real seconds of half-time display before 2nd half

# Watching speed (like FM): the football is always played out in full at real
# pace; this is how many times faster than real time you watch it.
# Change it during the match with + / - (or the up / down arrow keys).
MATCH_SPEEDS        = (1, 2, 4, 8, 16, 32)
DEFAULT_MATCH_SPEED = 8          # a 90-minute match takes ~11 minutes to watch

# Pitch Areas
GOAL_WIDTH = 7.32 * M_TO_PX
KEEPER_BOX_DEPTH = 16.5 * M_TO_PX
GOAL_AREA_DEPTH = 5.5 * M_TO_PX
GOAL_AREA_WIDTH = 18.32 * M_TO_PX
PENALTY_AREA_DEPTH = 16.5 * M_TO_PX
PENALTY_AREA_WIDTH = 40.32 * M_TO_PX
PENALTY_SPOT_DISTANCE = 11.0 * M_TO_PX
PENALTY_ARC_RADIUS = 9.15 * M_TO_PX

# Offside System
OFFSIDE_MARGIN = 0.5 * M_TO_PX
OFFSIDE_ACTIVE_DISTANCE = 30 * M_TO_PX

# Keeper Behavior
KEEPER_DIVE_REACTION = 0.15
KEEPER_DIVE_SPEED = 240.0
KEEPER_DIVE_COOLDOWN = 1.5
KEEPER_RECOVER_TIME = 0.8
KEEPER_CATCH_RADIUS = 12.0
KEEPER_PARRY_RADIUS = 18.0

# Colors
GRASS_A   = (62, 148, 54)   # natural grass green — light stripe
GRASS_B   = (48, 118, 44)   # slightly darker      — dark stripe  (subtle ~30pt diff)
GRASS_OUT = (18,  72, 18)   # very dark green for the pitch margin / surrounds
WHITE     = (255, 255, 255)
BLACK     = (10, 10, 10)
BLUE      = (60, 120, 200)
RED       = (200, 70, 70)
YELLOW    = (250, 220, 60)
GOAL_COLOR = (255, 255, 255)  # goals drawn as white outlines
GRID_COLOR = (180, 180, 180)  # slightly softer grid lines against bright grass

# Font Sizes
FONT_SIZE_NORMAL = 14
FONT_SIZE_LARGE = 26
FPS = 60

# Physics
GRAVITY = 9.8 * M_TO_PX # Gravity in pixels per second squared
AIR_RESISTANCE = 0.98   # Slow down slightly in air
BOUNCE_FACTOR = 0.6     # How much energy is kept after a bounce

# Goal Dimensions (3D)
GOAL_HEIGHT = 2.44 * M_TO_PX # Standard crossbar height ~24px
GOAL_ZONES_X = 3 # 3 columns
GOAL_ZONES_Y = 3 # 3 rows (Height)

# RL agents (Neo / Messi)
RL_ENABLED = False           # True = Blue's LCB (Neo) and ST1 (Messi) are learning players
RL_DECISION_INTERVAL = 0.3   # seconds between RL decisions (was every frame = 60/s)
