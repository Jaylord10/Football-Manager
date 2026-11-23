"""
ai/tactics.py
=============
Team tactics: how a team defends.

Set it per team in match_config.json:
    "tactics": {"defence": "mid_block"}

Four styles, from most passive to most aggressive:

  low_block   Sit deep and compact around our box.  Only close down once
              they're in our final third-ish.  Hard to break down, but you
              give them the ball and the territory.
  mid_block   Hold a compact block around halfway.  Press once they come
              into our half.  The balanced option.
  press       Push up.  Press them in their own half, a second man cuts off
              the easy pass, and when we lose the ball the nearest two
              hunt it straight back for a few seconds (counter-press).
  high_press  Squeeze right up, press everywhere - even their keeper's
              area - with two pressers, the nearest teammates marking the
              short options tight, and a three-man counter-press.  Wins the
              ball high, but leaves space behind a high line and runs the
              legs into the ground.

Stepping out to block a man running at us (ai/pressing.py "block the run"):
  step_from       how far from our goal (m) a man running at us gets met from
                  the front (low block 55 = our half only; high press anywhere)
  block_jockey    how far off him the blocker stands (pressing teams get tighter)
  cb_beyond_half  whether the back line will step out beyond halfway

Their goal kick (ai/team_shape.py):
  gk_back         how far from our goal (m) our back line sets up...
  gk_front        ...and our front two: a low block lets them have it and
                  waits in our half; a mid block pushes up and screens the
                  passes into midfield; the press and high press go and meet
                  the centre-backs on the edge of their box

Each style is a set of numbers (STYLES below) used by:
  ai/team_shape.py  - how high and compact the block sits
  ai/pressing.py    - where pressing starts, how many press, counter-press
  ai/urgency.py     - how sharp everyone is out of possession
You can tweak any number or add your own style.
"""

STYLES = {
    #                  back line           front two          pressing                                    counter-press
    "low_block":  dict(line_max=26.0, line_ratio=0.50, line_offset=2.0, front_gap=12.0, stay_up=38.0,
                       press_from=40.0, press_reach=2.2, second_presser=False, mark_short=False,
                       counter_press=0.0, counter_pressers=0, urgency_bonus=0.0, att_line_max=40.0,
                       step_from=55.0, block_jockey=3.0, cb_beyond_half=False, gk_back=28.0, gk_front=50.0),
    "mid_block":  dict(line_max=38.0, line_ratio=0.60, line_offset=2.0, front_gap=14.0, stay_up=45.0,
                       press_from=62.0, press_reach=2.6, second_presser=False, mark_short=False,
                       counter_press=0.0, counter_pressers=0, urgency_bonus=0.0, att_line_max=50.0,
                       step_from=62.0, block_jockey=3.0, cb_beyond_half=False, gk_back=45.0, gk_front=80.0),
    "press":      dict(line_max=46.0, line_ratio=0.70, line_offset=4.0, front_gap=14.0, stay_up=55.0,
                       press_from=85.0, press_reach=3.0, second_presser=True, mark_short=False,
                       counter_press=3.0, counter_pressers=2, urgency_bonus=0.10, att_line_max=55.0,
                       step_from=85.0, block_jockey=2.5, cb_beyond_half=False, gk_back=55.0, gk_front=92.0),
    "high_press": dict(line_max=54.0, line_ratio=0.80, line_offset=6.0, front_gap=13.0, stay_up=65.0,
                       press_from=110.0, press_reach=3.4, second_presser=True, mark_short=True,
                       counter_press=5.0, counter_pressers=2, urgency_bonus=0.20, att_line_max=58.0,
                       step_from=110.0, block_jockey=2.0, cb_beyond_half=True, gk_back=60.0, gk_front=95.0),
}
DEFAULT_STYLE = "mid_block"

# The older "line" setting still works: deep / mid / high
_LINE_TO_STYLE = {"deep": "low_block", "mid": "mid_block", "high": "press"}

# Optional overrides (e.g. from sim.py --home-defence); team id -> style name
OVERRIDE = {}
_warned = set()


def style_name(team_id):
    if team_id in OVERRIDE:
        return OVERRIDE[team_id]
    try:
        import core.database as database
        t = database.TACTICS.get(team_id, {}) or {}
    except Exception:
        t = {}
    name = t.get("defence") or _LINE_TO_STYLE.get(t.get("line"), DEFAULT_STYLE)
    if name not in STYLES:
        if name not in _warned:
            _warned.add(name)
            print(f"[Tactics] Unknown defensive style '{name}' - using {DEFAULT_STYLE}. "
                  f"Choose from: {', '.join(STYLES)}")
        name = DEFAULT_STYLE
    return name


# Build-up / clearing (ai/clearance.py), set per team in match_config.json:
#     "tactics": {"defence": "mid_block", "build_up": "play_out"}
#   play_out  Play Out Of Defence - keep the ball unless it's really on fire
#   mixed     the default
#   clear     Clear Ball To Flanks - get it away early, out wide
BUILD_UPS = ("play_out", "mixed", "clear")
DEFAULT_BUILD_UP = "mixed"
OVERRIDE_BUILD = {}      # team id -> build-up (sim.py --home-build / --away-build)


def build_up(team_id):
    if team_id in OVERRIDE_BUILD:
        return OVERRIDE_BUILD[team_id]
    try:
        import core.database as database
        b = (database.TACTICS.get(team_id, {}) or {}).get("build_up", DEFAULT_BUILD_UP)
    except Exception:
        b = DEFAULT_BUILD_UP
    if b not in BUILD_UPS:
        if ("build", b) not in _warned:
            _warned.add(("build", b))
            print(f"[Tactics] Unknown build_up '{b}' - using {DEFAULT_BUILD_UP}. Choose from: {', '.join(BUILD_UPS)}")
        b = DEFAULT_BUILD_UP
    return b


# Back line and pressing set separately (career tactics screen):
#     "tactics": {"defence": "mid_block", "line_height": "high", "press_height": "low"}
# The style is the starting point; line_height swaps in the back-line numbers of
# another style, press_height its pressing numbers.  Left out (or the same as
# the style) = the style exactly as it is.
LINE_KEYS = ("line_max", "line_ratio", "line_offset", "gk_back", "cb_beyond_half", "att_line_max")
PRESS_KEYS = ("press_from", "press_reach", "second_presser", "mark_short", "counter_press", "counter_pressers",
              "urgency_bonus", "step_from", "block_jockey", "gk_front", "front_gap", "stay_up")
LINE_HEIGHTS = {"deep": "low_block", "standard": "mid_block", "high": "press", "very_high": "high_press"}
PRESS_HEIGHTS = {"low": "low_block", "mid": "mid_block", "high": "press", "very_high": "high_press"}
# ...and the in-between levels (halfway between two styles)
LINE_HEIGHTS["low"] = {"line_max": 32.0, "line_ratio": 0.55, "line_offset": 2.0, "gk_back": 36.5,
                       "cb_beyond_half": False, "att_line_max": 45.0}                      # deep .. standard
PRESS_HEIGHTS["vhigh"] = {"press_from": 97.0, "press_reach": 3.2, "second_presser": True, "mark_short": False,
                          "counter_press": 4.0, "counter_pressers": 2, "urgency_bonus": 0.15, "step_from": 97.0,
                          "block_jockey": 2.25, "gk_front": 93.5, "front_gap": 13.5, "stay_up": 60.0}  # high .. full
                          # (press_from < 100: leaves their keeper alone)
_MIXED = {}


def _part(level, keys):
    return level if isinstance(level, dict) else {k: STYLES[level][k] for k in keys}


def style(team_id):
    name = style_name(team_id)
    try:
        import core.database as database
        t = database.TACTICS.get(team_id, {}) or {}
    except Exception:
        t = {}
    return style_for(name, t)


def style_for(name, t):
    """The numbers for style `name` with a tactics dict's line_height / press_height (also for the career screens)."""
    lh = LINE_HEIGHTS.get(t.get("line_height"))
    ph = PRESS_HEIGHTS.get(t.get("press_height"))
    if (lh is None or lh == name) and (ph is None or ph == name):
        return STYLES[name]
    key = (name, t.get("line_height"), t.get("press_height"))
    if key not in _MIXED:
        d = dict(STYLES[name])
        if lh:
            d.update(_part(lh, LINE_KEYS))
        if ph:
            d.update(_part(ph, PRESS_KEYS))
        _MIXED[key] = d
    return _MIXED[key]


# ---------------------------------------------------------------------------
# The choices as the manager sees them: the career Tactics screen (career/ui.py) and, during a match, the
# S screen's Tactics page (rendering/sub_panel.py).  t = a team's "tactics" dict.
# ---------------------------------------------------------------------------
STYLE_OPTIONS = [("low_block", "Low block", "Sit deep and compact. Hard to break down, but you give them the ball."),
                 ("mid_block", "Mid block", "Compact around halfway, press once they're in your half."),
                 ("press", "Press", "Press them in their half, counter-press when you lose it."),
                 ("high_press", "High press", "Squeeze right up and press everywhere. Wins it high, tiring.")]
LINE_OPTIONS = [("deep", "Deep", "Never more than ~26 m out."),
                ("low", "Low", "Up to ~32 m out."),
                ("standard", "Standard", "Up to ~38 m out."),
                ("high", "High", "Up to ~46 m - squeezes midfield."),
                ("very_high", "Very high", "Up to halfway. Space in behind!")]
PRESS_OPTIONS = [("low", "Low", "Only within ~40 m of your goal."),
                 ("mid", "Mid", "From just inside their half."),
                 ("high", "High", "Deep in their half; counter-press."),
                 ("vhigh", "Very high", "Up to their box - not the keeper."),
                 ("very_high", "Full", "Everywhere, even their keeper. Tiring.")]
STYLE_LEVEL = {"low_block": ("deep", "low"), "mid_block": ("standard", "mid"), "press": ("high", "high"),
               "high_press": ("very_high", "very_high")}
BUILD_OPTIONS = [("play_out", "Play out", "Keep the ball from the back unless it's really on fire."),
                 ("mixed", "Mixed", "Play out when it's on, clear it when it isn't."),
                 ("clear", "Clear to flanks", "Get it away early and out wide, especially under pressure.")]


def line_press(t):
    """(back line, pressing) - the style's own unless they've been set."""
    dl, dp = STYLE_LEVEL.get(t.get("defence"), ("standard", "mid"))
    return t.get("line_height") or dl, t.get("press_height") or dp


def set_style(t, key):
    t["defence"] = key
    t.pop("line_height", None)                       # (the style sets both)
    t.pop("press_height", None)


def set_line_press(t, field, key):
    """field "line_height" or "press_height".  If the pair is just one of the four styles, it becomes that style."""
    line, press = line_press(t)
    t["line_height"], t["press_height"] = (key, press) if field == "line_height" else (line, key)
    preset = next((st for st, lv in STYLE_LEVEL.items() if lv == (t["line_height"], t["press_height"])), None)
    if preset:
        set_style(t, preset)


def is_mixed(t):
    return "line_height" in t or "press_height" in t


def summary(t):
    """A short description, e.g. "High press, play out" or "Line high / press low, mixed"."""
    if is_mixed(t):
        line, press = line_press(t)
        lab = dict((k, l) for k, l, _ in LINE_OPTIONS)
        pl = dict((k, l) for k, l, _ in PRESS_OPTIONS)
        out = f"Line {lab.get(line, line).lower()} / press {pl.get(press, press).lower()}"
    else:
        out = dict((k, l) for k, l, _ in STYLE_OPTIONS).get(t.get("defence") or DEFAULT_STYLE, "Mid block")
    build = dict((k, l) for k, l, _ in BUILD_OPTIONS).get(t.get("build_up") or DEFAULT_BUILD_UP, "Mixed")
    return f"{out}, {build.lower()}"
