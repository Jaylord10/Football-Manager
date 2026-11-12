"""
ai/team_shape.py
================
Where each player should be: the TEAM decides its shape first, then every
player takes his place in it.

Before: 20 separate role files each worked out one player's spot on their
own - no idea what teammates were doing, several of them blind to everyone
else, the ball seen as a 4-5 m grid square.  Result: 50 m gaps between the
lines, players doubling up, nobody deliberately covering anyone.

How it works now (all distances in metres, measured in the team's own
"attacking frame": `a` = distance up the pitch from our own goal line,
`l` = sideways, negative = our left, positive = our right):

OUT OF POSSESSION - a compact block of three lines
  - The BACK LINE sits a set distance in front of our goal that depends on
    where the ball is (deeper when it's near our box) and on the team's
    defensive style (ai/tactics.py: low block / mid block / press / high press).
  - The MIDFIELD LINE sits ~11 m in front of it, goal-side of the ball.
  - The FRONT TWO sit further on, ready to press or break (how far, and how
    high they stay, depends on the style).
  - The whole block slides across towards the ball; players on the far side
    tuck in.

IN POSSESSION - stretch the pitch
  - Centre-backs stay behind the ball (rest defence) and split wide when
    we're building from the back.
  - Full-backs push on as far as their role likes, holding the width.
  - Wide men hold the touchline - or the inside channel if they're inverted.
  - Central midfielders support behind the ball; box-to-box ones join the
    attack in the final third.
  - Strikers pin the opposition's last line (on the offside line) or drop
    into the space between the lines to link play, depending on role.
  - Then each player JUDGES the spots around his base spot - open passing
    lane, time on the ball, danger, team rules - and takes the best one
    (ai/spot_value.py).
  - Teamwork patterns on top (ai/patterns.py): the two best-placed come to
    help a teammate who's being pressed, and when someone leaves an
    important spot the nearest teammate covers it.
  - Nobody stands right on top of the man on the ball.

Each player's ROLE (roles/library.py) is a handful of settings - how high a
full-back goes, how wide a winger stays, whether a striker pins or links -
rather than a block of code.  Reasons are written to player.pos_reason for
the debug overlay (press D in the match window).

All tuning numbers are in the TUNING block.
"""

import random
from pygame.math import Vector2
from config.constants import WIDTH, HEIGHT, M_TO_PX

PITCH_L = WIDTH / M_TO_PX            # 110 m
PITCH_W = HEIGHT / M_TO_PX           # 70 m
HALF_W = PITCH_W / 2.0
HALFWAY = PITCH_L / 2.0

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------

# Out of possession
DEF_LINE_MIN     = 7.0       # never deeper than this (m from goal)
BOX_DROP_FROM    = 42.0      # m from our goal: ball out wide nearer than this - the back line drops into the box...
BOX_DROP_WIDE    = 12.0      # ...if it's at least this far out from the middle...
BOX_DROP_FULL    = 22.0      # ...all the way by the time it's this close
BOX_EDGE         = 16.0      # m: the line goes from the edge of the box...
BOX_LINE         = 11.0      # ...to about the penalty spot
LINE_GAP         = 11.0      # m between the back line and the midfield line
MID_GOALSIDE     = 1.5       # midfield line stays at least this far goal-side of the ball
DEF_SHIFT        = 0.55      # block slides this share of the ball's sideways position...
DEF_SHIFT_FAR    = 0.25      # ...but only this share when the ball is far away (in their half)
BACK_HALF_WIDTH  = 16.0      # back four spread across 32 m
MID_HALF_WIDTH   = 18.0      # midfield four across 36 m
FRONT_HALF_WIDTH = 5.0       # front two
FAR_SIDE_TUCK    = 0.85      # far-side players squeeze in towards the middle
# Cover and balance: the block angles towards the ball.  The further a
# defender is across from the ball, the deeper he drops to cover behind the
# men nearer it (far full-back deepest) - so the lines aren't flat.
DIAG_FROM        = 12.0      # m across from the ball before he starts dropping...
DIAG_BACK        = 0.25      # ...back line: this many m deeper per m further across...
DIAG_BACK_MAX    = 5.0       # ...up to this much
DIAG_MID         = 0.15      # midfield line: m deeper per m across...
DIAG_MID_MAX     = 3.0

# In possession
ATT_SHIFT        = 0.30      # shape slides this share of the ball's sideways position
CB_BEHIND_BALL   = 28.0      # centre-backs this far behind the ball...
CB_MIN           = 10.0      # ...but no deeper than this
CB_SPLIT_BUILDUP = 15.0      # centre-backs split this far apart (each side) when building from the back
CB_SPLIT         = 10.0
BUILDUP_DEPTH    = 32.0      # "building from the back" = ball within this of our goal
TOUCHLINE_INSET  = 3.0       # width 1.0 = this far in from the touchline
NARROWEST        = 22.0      # width 0.0 = this much further in
CM_BEHIND_BALL   = 8.0       # central midfielders support this far behind the ball...
CM_BUILDUP_AHEAD = 6.0       # ...but in build-up they show ahead of it, offering a forward pass
CM_HOLD_EXTRA    = 6.0       # a holding midfielder sits this much deeper still
CM_JOIN_ATTACK   = 16.0      # box-to-box: up to this much further forward in the final third
CM_HALF_WIDTH    = 9.0
FINAL_THIRD      = 70.0      # m from our goal
ST_ONSIDE        = 1.0       # pinning strikers sit this far onside
ST_LINK_DROP     = 9.0       # link striker drops this far off the last line...
ST_LINK_AHEAD    = 12.0      # ...but no further ahead of the ball than this
ST_MAX_AHEAD     = 35.0      # nobody further than this ahead of the ball
ST_HALF_WIDTH    = 7.0
SWITCH_SIDE      = 10.0      # m: ball this far over on the other flank -> far winger stays wide for the switch
WM_PUSH_FROM     = 35.0      # m: from here (ball distance from our goal) the wide men push up...
WM_PUSH_SPAN     = 15.0      # ...fully by this much further on...
WM_LINE_GAP      = 3.0       # ...to this far short of their back line (more for cautious wide men)
WM_MIN_HEIGHT    = 45.0      # m from our goal: wide men don't come deeper than this in possession
CARRIER_SPACE    = 6.0       # m: keep this clear around the man on the ball
EDGE             = 2.0       # m: targets stay this far inside the lines
ROAM_STEP        = 5.0       # s between a roaming player's changes of idea
ROAM_RANGE       = 6.0       # m he wanders from his spot

# Role defaults by position (a role in roles/library.py can override any of these)
DEFAULTS = {
    "LB":  {"fb_height": 10.0, "width": 0.95},
    "RB":  {"fb_height": 10.0, "width": 0.95},
    "LCB": {}, "RCB": {},
    "LCM": {"cm_forward": 0.5}, "RCM": {"cm_forward": 0.5},
    "LM":  {"wm_height": 4.0, "width": 0.95, "track_back": 1.0},
    "RM":  {"wm_height": 4.0, "width": 0.95, "track_back": 1.0},
    "ST1": {"st_style": "pin", "stay_up": True},
    "ST2": {"st_style": "pin", "stay_up": True},
}
LEFT = {"LB": -1, "LCB": -1, "LCM": -1, "LM": -1, "ST1": -1,
        "RB": 1, "RCB": 1, "RCM": 1, "RM": 1, "ST2": 1}

# ---------------------------------------------------------------------------
# Any formation (config/slots.py).  The 4-4-2 keeps the code it was tuned with;
# other shapes place each man from his spot's row and lane.
# ---------------------------------------------------------------------------
# Out of possession, in lines: half-width of a line (m) by how many are in it
G_BACK_HALF   = {1: 0.0, 2: 6.0, 3: 11.0, 4: BACK_HALF_WIDTH, 5: 19.0}
G_MID_HALF    = {1: 0.0, 2: 8.0, 3: 13.0, 4: MID_HALF_WIDTH, 5: 21.0}
G_SCREEN_HALF = {1: 0.0, 2: 5.0, 3: 8.0}
G_AM_HALF     = {1: 0.0, 2: 6.0, 3: 10.0}
G_FRONT_HALF  = {1: 0.0, 2: FRONT_HALF_WIDTH, 3: 12.0}
SCREEN_BELOW  = 5.0      # a defensive midfielder behind a midfield line screens this far behind it
AM_ABOVE      = 6.0      # attacking midfielders out of possession: this far in front of the midfield line
# In possession
WB_EXTRA      = 8.0      # wing-backs push on this much further than full-backs
W_EXTRA       = 4.0      # wingers in an attacking-midfield spot play this much higher than wide midfielders
AM_DROP       = 6.0      # a number 10 sits this far short of their last line...
AM_AHEAD      = 14.0     # ...and no further than this ahead of the ball
AM_HALF_WIDTH = 8.0
AM_PAIR_HALF  = 12.0     # two number 10s (3-4-2-1): one in each half-space
AM_ARRIVE     = 0.75     # ...and near the box they close most of the gap to the last line
AM_STAY_FROM  = 60.0     # m: ball this far up, a number 10 doesn't drop off to help or fill gaps
CB3_SPREAD    = 3.0      # a back three: the outside centre-backs split this much wider


_TEAMS = {}


def _team_of(p):
    return _TEAMS.get(p.team, [p])


def _generic(tid):
    import config.formations as formations
    return bool(formations.formation_slots(tid))


_bands = {}


def _is_ten(p):
    return getattr(p, "slot", None) in ("AM", "LAM", "RAM")


def _band_info(team):
    """{id(player): (band, fraction -1..1 across it, size)} for a non-4-4-2 team, defending and attacking."""
    from config import slots
    act = [p for p in team if p.role != "GK" and getattr(p, "is_active", True)]
    key = (team[0].team, tuple(sorted((p.slot, id(p)) for p in act)))
    hit = _bands.get(key)
    if hit is not None:
        return hit
    has_cm = any(slots.row(p.slot) == 2 and abs(slots.lane(p.slot)) < 2 for p in act)
    has_st = any(slots.row(p.slot) == 4 for p in act)
    n_def = sum(1 for p in act if slots.row(p.slot) == 0)

    def d_band(p):
        r, ln = slots.row(p.slot), slots.lane(p.slot)
        if r == 0 or (r == 1 and abs(ln) == 2 and n_def >= 3):
            return "back"                  # (wing-backs drop in beside a back three - not when it's all-out with two)
        if r == 1 and abs(ln) == 2:
            return "mid"
        if r == 1:
            return "screen" if has_cm else "mid"
        if r == 2 or (r == 3 and abs(ln) == 2):
            return "mid"
        if r == 3:
            return "am" if has_st else "front"
        return "front"

    wide_sides = {slots.side(p.slot) for p in act if slots.kind(p.slot) in ("WM", "W")}

    def a_band(p):
        k = slots.kind(p.slot)
        if k == "WB" and slots.side(p.slot) not in wide_sides:
            return "wide"                  # nobody wide ahead of him: the wing-back IS the width (3-4-2-1, 3-5-2, 5-3-2)
        return {"FB": "fb", "WB": "fb", "CB": "cb", "DM": "cm", "CM": "cm", "WM": "wide", "W": "wide",
                "AM": "am", "ST": "st"}.get(k, "cm")
    out = {}
    for which, fn in (("d", d_band), ("a", a_band)):
        groups = {}
        for p in act:
            groups.setdefault(fn(p), []).append(p)
        if which == "d":
            # Out of possession the midfield line needs bodies: number 10s drop into it (3-4-2-1 -> 5-4-1)
            # and a lone holding midfielder steps into a thin one (3-5-2 -> 5-3-2)
            mid = groups.setdefault("mid", [])
            am = sorted(groups.get("am", []), key=lambda q: -abs(slots.lane(q.slot)))
            while len(mid) < 4 and am and groups.get("front"):
                mid.append(am.pop(0))
            groups["am"] = am
            if len(mid) < 3 and groups.get("screen"):
                mid.extend(groups.pop("screen"))
            groups = {k: v for k, v in groups.items() if v}
        for band, ps in groups.items():
            ps.sort(key=lambda q: slots.lane(q.slot) + 0.1 * slots.side(q.slot) * slots.row(q.slot))
            n = len(ps)
            for i, q in enumerate(ps):
                frac = 0.0 if n == 1 else -1.0 + 2.0 * i / (n - 1)
                out.setdefault(id(q), {})[which] = (band, frac, n)
    _bands[key] = out
    if len(_bands) > 64:
        _bands.clear()
    return out


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------
def to_frame(team, v):
    """World Vector2 (px) -> (a, l) in the team's attacking frame (m)."""
    if team == 0:
        return v.x / M_TO_PX, v.y / M_TO_PX - HALF_W
    return PITCH_L - v.x / M_TO_PX, HALF_W - v.y / M_TO_PX


def to_world(team, a, l):
    a = min(max(a, EDGE), PITCH_L - EDGE)
    l = min(max(l, -HALF_W + EDGE), HALF_W - EDGE)
    if team == 0:
        return Vector2(a * M_TO_PX, (l + HALF_W) * M_TO_PX)
    return Vector2((PITCH_L - a) * M_TO_PX, (HALF_W - l) * M_TO_PX)


def _clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def settings(player):
    """The player's role settings: position defaults + his role's choices."""
    import roles.library as role_library
    s = dict(DEFAULTS.get(player.role, {}))
    try:
        s.update(role_library.role_for(player).shape or {})
    except Exception:
        pass
    return s


def _focus(ball):
    """Where the ball is about to be (a loose / passed ball 0.4 s ahead)."""
    if ball.owner is None and ball.vel.length() > 0.5 * M_TO_PX:
        return ball.pos + ball.vel * 0.4
    return Vector2(ball.pos)


def _last_line(team, opponents):
    """Opposition offside line in our frame: second-deepest of them, never in our half."""
    depths = sorted((to_frame(team, o.pos)[0] for o in opponents
                     if getattr(o, "is_active", True)), reverse=True)
    second = depths[1] if len(depths) > 1 else PITCH_L
    return max(second, HALFWAY)


def _roam(p, now):
    """A roaming player's current wander offset (changes every ROAM_STEP s)."""
    off = getattr(p, "_roam_off", None)
    if off is None or now >= getattr(p, "_roam_next", 0.0):
        off = (random.uniform(-ROAM_RANGE, ROAM_RANGE), random.uniform(-ROAM_RANGE, ROAM_RANGE))
        p._roam_off = off
        p._roam_next = now + ROAM_STEP
    return off


# ---------------------------------------------------------------------------
ATT_REFRESH      = 0.2       # s: the attacking shape (with its spot judging) is worked out this often
DEF_REFRESH      = 0.1       # s: ...and the defending shape this often
_cache = {}


def compute(team, opponents, ball, in_possession, now, restart=None):
    """
    Returns {id(player): (target Vector2, reason)} for every outfield player.
    """
    if not team:
        return {}
    if in_possession:
        key = team[0].team
        hit = _cache.get(key)
        if hit is not None and 0.0 <= now - hit[0] < ATT_REFRESH:
            return hit[1]
        result = _compute(team, opponents, ball, in_possession, now)
        _cache[key] = (now, result)
        return result
    # Defending: worked out DEF_REFRESH times a second rather than every frame.
    # (Each defender only re-reads the play every 0.15-0.75 s anyway - see
    # ai/reading.py - so this costs nothing in behaviour and saves ~25% of the
    # time a match takes to simulate.)
    key = ("def", team[0].team, restart)
    hit = _cache.get(key)
    if hit is not None and 0.0 <= now - hit[0] < DEF_REFRESH:
        return hit[1]
    result = _compute(team, opponents, ball, in_possession, now, restart)
    _cache[key] = (now, result)
    return result


def _compute(team, opponents, ball, in_possession, now, restart=None):
    tid = team[0].team
    _TEAMS[tid] = team
    import ai.tactics as tactics
    st = tactics.style(tid)
    fa, fl = to_frame(tid, _focus(ball))
    out = {}
    if in_possession:
        _attacking(team, opponents, ball, tid, fa, fl, st, now, out)
    else:
        # Each defender places himself from his OWN read of the ball (ai/reading.py)
        import ai.reading as reading
        for p in team:
            if p.role == "GK":
                continue
            pa, pl = to_frame(tid, reading.focus(p, ball, now))
            _defending([p], tid, pa, pl, st, out, now, restart)
            spot, why = out[id(p)]
            out[id(p)] = (reading.hold_zone(p, spot, now), why)
    return out


def _defending(team, tid, ba, bl, st, out, now=None, restart=None):
    # How high the block sits comes from the team's defensive style (ai/tactics.py)
    back = _clamp(st["line_ratio"] * ba + st["line_offset"], DEF_LINE_MIN, st["line_max"])
    # Ball out wide in our final third (a cross is on): the back line drops into
    # the box to protect the space in front of goal - from the edge of the box
    # down to about the penalty spot as the ball gets closer.  (It used to hold
    # just outside the box, leaving it empty for the cross.)
    if ba < BOX_DROP_FROM and abs(bl) >= BOX_DROP_WIDE:
        q = _clamp((BOX_DROP_FROM - ba) / (BOX_DROP_FROM - BOX_DROP_FULL), 0.0, 1.0)
        back = min(back, BOX_EDGE - (BOX_EDGE - BOX_LINE) * q)
    mid = max(back + 5.0, min(back + LINE_GAP, ba - MID_GOALSIDE))
    front = mid + st["front_gap"]
    if restart == "goal_kick":
        # Their goal kick: each style has its own set-up (ai/tactics.py)
        back = st["gk_back"]
        mid = back + LINE_GAP
        front = max(mid + 6.0, st["gk_front"])
    near = _clamp((PITCH_L * 0.75 - ba) / (PITCH_L * 0.5), 0.0, 1.0)    # 1 = ball in our half
    shift = DEF_SHIFT_FAR + (DEF_SHIFT - DEF_SHIFT_FAR) * near
    c = _clamp(bl * shift, -(HALF_W - BACK_HALF_WIDTH - EDGE), HALF_W - BACK_HALF_WIDTH - EDGE)

    def lateral(slot, half_width):
        l = c + slot * half_width
        if (l - c) * bl < 0:                    # far side of the ball: tuck in
            l = c + (l - c) * FAR_SIDE_TUCK
        return l

    gen = _generic(tid)
    for p in team:
        if p.role == "GK":
            continue
        s = settings(p)
        side = LEFT.get(p.role, 0)
        if gen:
            band, frac, n = _band_info(_team_of(p)).get(id(p), {}).get("d", ("mid", 0.0, 1))
            if band == "back":
                a, l, why = back, lateral(frac, G_BACK_HALF.get(n, 19.0)), "back line"
            elif band == "screen":
                a, l, why = max(back + 3.0, mid - SCREEN_BELOW), lateral(frac, G_SCREEN_HALF.get(n, 8.0)), \
                    "screen the back line"
            elif band == "mid":
                tb = s.get("track_back", 1.0) if p.role in ("LM", "RM") else 1.0
                a = mid + (1.0 - tb) * 6.0
                l = lateral(frac, G_MID_HALF.get(n, 21.0))
                why = "midfield line" if tb >= 0.99 else "midfield line (stays higher)"
            elif band == "am":
                a = min(front, mid + AM_ABOVE)
                l = c + frac * G_AM_HALF.get(n, 10.0)
                why = "between midfield and attack"
            else:
                a = front
                if s.get("stay_up", True) and restart != "goal_kick":
                    a = max(a, min(st["stay_up"], ba + 15.0))
                l = c + frac * G_FRONT_HALF.get(n, 12.0)
                why = "front line"
            across = max(0.0, abs(l - bl) - DIAG_FROM)
            if band == "back":
                a -= min(DIAG_BACK_MAX, DIAG_BACK * across)
            elif band != "front":
                a -= min(DIAG_MID_MAX, DIAG_MID * across)
            if now is not None:
                import ai.reading as reading
                da, dl = reading.habit(p, now)
                a, l = a + da, l + dl
            out[id(p)] = (to_world(tid, a, l), why)
            continue
        if p.role in ("LB", "RB"):
            a, l, why = back, lateral(side * 1.0, BACK_HALF_WIDTH), "back line"
        elif p.role in ("LCB", "RCB"):
            a, l, why = back, lateral(side / 3.0, BACK_HALF_WIDTH), "back line"
        elif p.role in ("LM", "RM"):
            tb = s.get("track_back", 1.0)
            a = mid + (1.0 - tb) * 6.0
            l = lateral(side * 1.0, MID_HALF_WIDTH)
            why = "midfield line" if tb >= 0.99 else "midfield line (stays higher)"
        elif p.role in ("LCM", "RCM"):
            a, l, why = mid, lateral(side / 3.0, MID_HALF_WIDTH), "midfield line"
        else:                                   # strikers
            a = front
            if s.get("stay_up", True) and restart != "goal_kick":
                a = max(a, min(st["stay_up"], ba + 15.0))
            l = c + side * FRONT_HALF_WIDTH
            why = "front two"
        # Cover and balance: further across from the ball = a bit deeper
        across = max(0.0, abs(l - bl) - DIAG_FROM)
        if p.role in ("LB", "RB", "LCB", "RCB"):
            a -= min(DIAG_BACK_MAX, DIAG_BACK * across)
        elif p.role in ("LM", "RM", "LCM", "RCM"):
            a -= min(DIAG_MID_MAX, DIAG_MID * across)
        # His own positioning habits (ai/reading.py): Defensive Positioning / Teamwork
        if now is not None:
            import ai.reading as reading
            da, dl = reading.habit(p, now)
            a, l = a + da, l + dl
        out[id(p)] = (to_world(tid, a, l), why)


def _attacking(team, opponents, ball, tid, ba, bl, st, now, out):
    c = _clamp(bl * ATT_SHIFT, -8.0, 8.0)
    last = _last_line(tid, opponents)
    cb_a = _clamp(ba - CB_BEHIND_BALL, CB_MIN, st["att_line_max"])
    buildup = ba < BUILDUP_DEPTH
    final_third = _clamp((ba - (FINAL_THIRD - 15.0)) / 15.0, 0.0, 1.0)   # 0 -> 1 approaching the final third
    max_a = min(last - ST_ONSIDE, ba + ST_MAX_AHEAD)

    carrier = ball.owner if ball.owner is not None and ball.owner in team else None
    car_a, car_l = to_frame(tid, carrier.pos) if carrier is not None else (None, None)

    def wide_l(side, width):
        return side * (HALF_W - TOUCHLINE_INSET - (1.0 - width) * NARROWEST)

    slots = []          # (player, a, l, why, settings) - base spots, judged below
    fixed = []          # spots that don't move (centre-backs)
    gen = _generic(tid)
    info = _band_info(team) if gen else None
    for p in team:
        if p.role == "GK" or p is carrier:
            continue
        s = settings(p)
        side = LEFT.get(p.role, 0)
        hold_spot = False
        if gen:
            from config import slots as slots_mod
            band, frac, n = info[id(p)]["a"] if id(p) in info else ("cm", 0.0, 1)
            side = slots_mod.side(p.slot)
            kind = slots_mod.kind(p.slot)
            if band == "cb":
                a = cb_a
                split = CB_SPLIT_BUILDUP if buildup else CB_SPLIT
                if n >= 3:
                    split += CB3_SPREAD
                l = c * 0.5 + frac * split
                why = "build-up: split wide" if buildup else "rest defence"
            elif band == "fb":
                extra = WB_EXTRA if kind == "WB" else 0.0
                a = min(cb_a + s.get("fb_height", 10.0) + extra, ba + 8.0 + extra, max_a)
                a = max(a, cb_a)
                l = wide_l(side, s.get("width", 0.95) if kind != "WB" else max(0.95, s.get("width", 0.95)))
                why = "wing-back: high and wide" if kind == "WB" else \
                    ("full-back: push on, hold width" if s.get("fb_height", 10.0) >= 14 else "full-back: width")
            elif band == "cm":
                fwd = s.get("cm_forward", 0.5)
                prog = _clamp((ba - BUILDUP_DEPTH) / 25.0, 0.0, 1.0)
                base = CM_BUILDUP_AHEAD + (-CM_BEHIND_BALL - CM_BUILDUP_AHEAD) * prog
                a = ba + base - (1.0 - fwd) * CM_HOLD_EXTRA * prog + fwd * final_third * CM_JOIN_ATTACK
                a = min(max(a, cb_a + 8.0), max_a)
                l = c + frac * (CM_HALF_WIDTH if n <= 2 else CM_HALF_WIDTH + 2.0)
                if prog < 0.3:
                    why = "build-up: show for the ball"
                elif fwd * final_third > 0.4:
                    why = "join the attack"
                elif fwd < 0.3:
                    why = "hold: screen behind the ball"
                else:
                    why = "support behind the ball"
            elif band == "wide":
                width = s.get("width", 0.95)
                h = s.get("wm_height", 4.0) + (W_EXTRA if kind == "W" else 0.0)
                push = _clamp((ba - WM_PUSH_FROM) / WM_PUSH_SPAN, 0.0, 1.0)
                near_line = last - WM_LINE_GAP - (1.0 - min(1.0, h / 8.0)) * 4.0
                a = min(max(ba + h, cb_a + 12.0, WM_MIN_HEIGHT, near_line * push + (ba + h) * (1.0 - push)), max_a)
                l = wide_l(side, width)
                why = "inside channel" if width < 0.75 else "hold the width"
                if side * bl < -SWITCH_SIDE:
                    a = min(max(a, ba), max_a)
                    l = side * (HALF_W - TOUCHLINE_INSET)
                    why = "stay wide for the switch"
                    hold_spot = True
            elif band == "am":
                # Between the lines; nearing the box they get up alongside the striker
                a = min(last - AM_DROP * (1.0 - AM_ARRIVE * final_third), ba + AM_AHEAD)
                a = min(max(a, ba - 2.0, cb_a + 15.0), max_a)
                half = AM_HALF_WIDTH if n != 2 else AM_PAIR_HALF          # (a pair: one in each half-space)
                l = _clamp(c * 0.5 + frac * half + bl * 0.25, -16.0, 16.0)
                why = "between the lines" if final_third < 0.5 else "arrive in the box"
            else:                                   # strikers
                if s.get("st_style", "pin") == "link":
                    a = min(last - ST_LINK_DROP, ba + ST_LINK_AHEAD)
                    a = max(a, ba - 2.0)
                    l = _clamp(bl * 0.5 + frac * ST_HALF_WIDTH, -12.0, 12.0)
                    why = "link: drop between the lines"
                else:
                    a = max_a
                    l = c + frac * (ST_HALF_WIDTH if n <= 2 else ST_HALF_WIDTH + 5.0)
                    why = "pin the last line"
                a = max(a, cb_a + 15.0)
        elif p.role in ("LCB", "RCB"):
            a = cb_a
            l = c * 0.5 + side * (CB_SPLIT_BUILDUP if buildup else CB_SPLIT)
            why = "build-up: split wide" if buildup else "rest defence"
        elif p.role in ("LB", "RB"):
            a = min(cb_a + s.get("fb_height", 10.0), ba + 8.0, max_a)
            a = max(a, cb_a)
            l = wide_l(side, s.get("width", 0.95))
            why = "full-back: push on, hold width" if s.get("fb_height", 10.0) >= 14 else "full-back: width"
        elif p.role in ("LCM", "RCM"):
            fwd = s.get("cm_forward", 0.5)
            # From "show ahead of the ball" in build-up to "support behind it" further up
            prog = _clamp((ba - BUILDUP_DEPTH) / 25.0, 0.0, 1.0)
            base = CM_BUILDUP_AHEAD + (-CM_BEHIND_BALL - CM_BUILDUP_AHEAD) * prog
            a = ba + base - (1.0 - fwd) * CM_HOLD_EXTRA * prog + fwd * final_third * CM_JOIN_ATTACK
            a = min(max(a, cb_a + 8.0), max_a)
            l = c + side * CM_HALF_WIDTH
            if prog < 0.3:
                why = "build-up: show for the ball"
            elif fwd * final_third > 0.4:
                why = "join the attack"
            elif fwd < 0.3:
                why = "hold: screen behind the ball"
            else:
                why = "support behind the ball"
        elif p.role in ("LM", "RM"):
            width = s.get("width", 0.95)
            # Stay high: in build-up the wingers hold up near halfway to stretch them;
            # once we're into their half they push up towards their back line
            push = _clamp((ba - WM_PUSH_FROM) / WM_PUSH_SPAN, 0.0, 1.0)
            near_line = last - WM_LINE_GAP - (1.0 - min(1.0, s.get("wm_height", 4.0) / 8.0)) * 4.0
            a = min(max(ba + s.get("wm_height", 4.0), cb_a + 12.0, WM_MIN_HEIGHT,
                        near_line * push + (ba + s.get("wm_height", 4.0)) * (1.0 - push)), max_a)
            l = wide_l(side, width)
            why = "inside channel" if width < 0.75 else "hold the width"
            if side * bl < -SWITCH_SIDE:
                # Ball on the other flank: stay wide and high, isolated -
                # the switch of play is always on (ai/combos.py)
                a = min(max(a, ba), max_a)
                l = side * (HALF_W - TOUCHLINE_INSET)
                why = "stay wide for the switch"
                hold_spot = True
        else:                                   # strikers
            style = s.get("st_style", "pin")
            if style == "link":
                a = min(last - ST_LINK_DROP, ba + ST_LINK_AHEAD)
                a = max(a, ba - 2.0)
                l = _clamp(bl * 0.5, -12.0, 12.0)
                why = "link: drop between the lines"
            else:
                a = max_a
                l = c + side * ST_HALF_WIDTH
                why = "pin the last line"
            a = max(a, cb_a + 15.0)

        if s.get("roam", 0.0) > 0:
            da, dl = _roam(p, now)
            a += da * s["roam"]
            l += dl * s["roam"]
            why += " + roam"

        if p.role in ("LCB", "RCB") or hold_spot:
            fixed.append((a, l))
            out[id(p)] = (a, l, why)
        else:
            slots.append((p, a, l, why, s))

    # Each player judges the spots around his base spot (ai/spot_value.py)
    import ai.spot_value as spot_value
    ref_a, ref_l = (car_a, car_l) if car_a is not None else (ba, bl)
    opp = [to_frame(tid, o.pos) for o in opponents if getattr(o, "is_active", True)]
    picked = spot_value.choose(slots, None, {
        "ball": (ref_a, ref_l), "opponents": opp, "fixed": fixed,
        "max_a": max_a, "min_a": cb_a,
    })
    out.update(picked)

    # Teamwork patterns (ai/patterns.py): help a pressed teammate, fill gaps
    import ai.patterns as patterns
    support = {}
    if carrier is not None:
        def fv(v):
            return (v.x / M_TO_PX, v.y / M_TO_PX) if tid == 0 else (-v.x / M_TO_PX, -v.y / M_TO_PX)
        car = (car_a, car_l) + fv(carrier.vel)
        opps_now = [to_frame(tid, o.pos) + fv(o.vel) for o in opponents
                    if getattr(o, "is_active", True) and o.role != "GK"]
        presser = patterns.pressed(car, opps_now)
        if presser is not None:
            helpers = [(p,) + to_frame(tid, p.pos) for p in team
                       if p is not carrier and p.role != "GK"
                       and getattr(p, "_planned_run", None) is None
                       and (p.role not in ("LCB", "RCB") or car_a < 35.0)
                       and not (gen and car_a > AM_STAY_FROM and _is_ten(p))]
            support = patterns.support_under_pressure(helpers, car, presser, opp, max_a, HALF_W)
    if not support:
        for p in team:
            p._support_job = False
    busy = set(support) | {id(p) for p in team if getattr(p, "_planned_run", None) is not None}
    if gen and car_a is not None and car_a > AM_STAY_FROM:
        busy |= {id(p) for p in team if _is_ten(p)}          # (a number 10 up near the box stays there)
    entries = [(p, out[id(p)][0], out[id(p)][1]) + to_frame(tid, p.pos) + (settings(p),)
               for p in team if id(p) in out]
    filled = patterns.fill_gaps(entries, busy)
    out.update(support)
    out.update(filled)

    for p in team:
        if id(p) not in out:
            continue
        a, l, why = out[id(p)]
        side = LEFT.get(p.role, 0)
        # Don't crowd the man on the ball
        if car_a is not None:
            da, dl = a - car_a, l - car_l
            d = (da * da + dl * dl) ** 0.5
            if d < CARRIER_SPACE:
                if d < 0.1:
                    da, dl, d = -1.0, float(side or 1), 1.4
                a = car_a + da / d * CARRIER_SPACE
                l = car_l + dl / d * CARRIER_SPACE

        out[id(p)] = (to_world(tid, a, l), why)
