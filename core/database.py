import csv
import json
import os

# Team tactics from match_config.json ("tactics": {"line": "deep" / "mid" / "high"}),
# filled in when the config is loaded; read by ai/team_shape.py.
TACTICS = {0: {}, 1: {}}
# Player instructions by position ("instructions": {"RM": {"crossing": "more"}}),
# read by roles/library.py instructions_for()
INSTRUCTIONS = {0: {}, 1: {}}

def row_to_attributes(row):
    """One CSV row (0-100 scale) -> the engine's attribute dict (1-20 scale).
    Used for the starting XI (load_csv_data) and for substitutes (gameplay/substitutions.py)."""
    def get_val(col_name):
        try:
            return int(row.get(col_name, 50))
        except (ValueError, TypeError):
            return 50

    # --- CALCULATE ENGINE STATS (1-20 Scale) ---
    
    raw_pace = (get_val("Acceleration") + get_val("Top Speed")) / 2
    pace = int(raw_pace / 5)
    
    finishing = int(get_val("Finishing") / 5)
    passing = int(get_val("Passing") / 5)
    
    # NEW: Load Dribbling and Control SEPARATELY
    dribbling = int(get_val("Dribbling") / 5)
    control = int(get_val("Control") / 5)
    
    # Tackling / Defending
    tackling = int(get_val("Tackling") / 5)
    raw_def = (get_val("Marking") + get_val("Tackling") + get_val("Defensive Positioning")) / 3
    defending = int(raw_def / 5)
    
    raw_phys = (get_val("Strength") + get_val("Stamina")) / 2
    physical = int(raw_phys / 5)
    
    composure = int(get_val("Composure") / 5)
    teamwork = int(get_val("Teamwork") / 5)
    
    # Store in Database
    attributes = {
        "Name": row.get("Name", (row.get("Role") or "").strip()),
        "Pace": pace,
        "Finishing": finishing,
        "Passing": passing,
        "Dribbling": dribbling,
        "Control": control,       # <--- New Attribute
        "Tackling": tackling,
        "Defending": defending,
        "Physical": physical,
        "Composure": composure,
        "Teamwork": teamwork
    }
    
    # Keep EVERY other CSV column too, converted to the 1-20 engine scale.
    # Before this, Top Speed, Acceleration, Agility, Aggression, Marking,
    # Work Rate, Off The Ball, Anticipation, Defensive Positioning etc.
    # were never loaded, so every player used the default 10 for them.
    for col, raw in row.items():
        if col is None or col in ("Role", "Name", "Id", "Pos", "Age") or col in attributes:
            continue
        try:
            attributes[col] = max(1, int(int(raw) / 5))
        except (ValueError, TypeError):
            pass
    return attributes


class PlayerDatabase:
    def __init__(self, config_file="match_config.json"):
        # sim.py --config (or FM_MATCH_CONFIG) can point at another match set-up,
        # e.g. match_config_benchmark.json (two average sides) for testing
        config_file = os.environ.get("FM_MATCH_CONFIG", config_file)
        self.database = {}
        self.home_team_name = "Home"
        self.away_team_name = "Away"
        self.team_roles = {0: "blue", 1: "red"}
        # Substitutes (career matches - gameplay/substitutions.py): per team a
        # list of {id, name, pos, row (0-100 CSV-style), drop {slot: n},
        # rating {slot: n}}; and the career id of the man in each starting slot
        self.bench = {0: [], 1: []}
        self.lineup_ids = {0: {}, 1: {}}
        self.lineup_ratings = {0: {}, 1: {}}
        self.lineup_ages = {0: {}, 1: {}}
        self.lineup_condition = {0: {}, 1: {}}
        self.auto_subs = {0: True, 1: True}
        self.friendly = False                    # a friendly: lots of substitutes (gameplay/substitutions.py)
        self.human = {0: False, 1: False}        # your team, when you watch (the S panel)
        self.ht_talk = {0: None, 1: None}        # the half-time team talk table (career/teamtalk.py)
        self.formation = {0: None, 1: None}      # the spots used (config/slots.py); None = 4-4-2
        self.knockout = None                     # a knockout tie this match decides: {"agg": [h, a]} (extra time)
        self.load_match_config(config_file)

    def load_match_config(self, config_file):
        """Reads the JSON config to decide which CSVs to load."""
        if not os.path.exists(config_file):
            print(f"Error: Config file {config_file} not found!")
            return

        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                
            # Roles each team plays (see roles/library.py)
            self.team_roles = {
                0: config['home_team'].get('roles', 'blue'),
                1: config['away_team'].get('roles', 'red'),
            }
            TACTICS[0] = dict(config['home_team'].get('tactics', {}))
            TACTICS[1] = dict(config['away_team'].get('tactics', {}))
            INSTRUCTIONS[0] = dict(config['home_team'].get('instructions', {}))
            INSTRUCTIONS[1] = dict(config['away_team'].get('instructions', {}))
            for tid, side in ((0, 'home_team'), (1, 'away_team')):
                self.bench[tid] = list(config[side].get('bench', []))
                self.lineup_ids[tid] = dict(config[side].get('lineup_ids', {}))
                self.lineup_ratings[tid] = dict(config[side].get('lineup_ratings', {}))
                self.lineup_ages[tid] = dict(config[side].get('lineup_ages', {}))
                self.lineup_condition[tid] = dict(config[side].get('lineup_condition', {}))
                self.auto_subs[tid] = bool(config[side].get('auto_subs', True))
                self.friendly = self.friendly or bool(config[side].get('friendly', False))
                self.human[tid] = bool(config[side].get('human', False))
                self.ht_talk[tid] = config[side].get('ht_talk')
                f = config[side].get('formation')
                if f:
                    from config import slots
                    if isinstance(f, str):
                        f = slots.FORMATIONS.get(f)
                    if f and not slots.check(f) and not slots.is_legacy(f):
                        self.formation[tid] = [s for s in f if s != "GK"]
                    elif f and slots.check(f):
                        print(f"[Formation] {config[side].get('name')}: {'; '.join(slots.check(f))} - playing 4-4-2")

            self.knockout = config.get('knockout')     # (extra time and penalties if level - career cups)
            self.home_team_name = config['home_team']['name']
            self.load_csv_data(config['home_team']['file'], override_team_id=0)
            
            self.away_team_name = config['away_team']['name']
            self.load_csv_data(config['away_team']['file'], override_team_id=1)
            
            print(f"Match Loaded: {self.home_team_name} vs {self.away_team_name}")
            
        except Exception as e:
            print(f"Failed to load match config: {e}")

    def load_csv_data(self, filepath, override_team_id):
        """Reads detailed 0-100 CSV and converts to 1-20 Game Engine stats."""
        if not os.path.exists(filepath):
            print(f"Warning: Team file {filepath} not found.")
            return

        with open(filepath, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                try:
                    if not row.get('Role'): continue
                        
                    role = row['Role'].strip()
                    key = (override_team_id, role)
                    
                    attributes = row_to_attributes(row)

                    self.database[key] = attributes
                    
                except Exception as e:
                    print(f"Error parsing row in {filepath}: {e}")

    def get_player_stats(self, team_id, role):
        return self.database.get((team_id, role))