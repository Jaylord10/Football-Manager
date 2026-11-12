"""
ai/attack_box.py
================
Attacking the box when the ball goes wide.

Before this, runs into the box came only from the run planner
(ai/run_planner.py), where they competed with runs in behind for two run
slots - and scored badly, because the box is where the defenders are.  So
when a winger got to the byline there was usually nobody in the box to
cross to.

Now, when one of ours has the ball out wide in the final third, the men
whose role likes getting into the box go there:
  - the strikers attack the NEAR POST and the FAR POST;
  - the wide man on the far side comes in to the far post (or the penalty
    spot if it's taken);
  - a midfielder who likes to get forward arrives late at the PENALTY SPOT
    or the edge of the box for the cut-back.
They hold their run on the offside line until the ball is ahead of it, and
anyone already making a planned run (in behind, an overlap...) carries on
with it.  Each role's "box" run preference (roles/library.py) decides who
goes.

All tuning numbers are in the TUNING block.
"""

from pygame.math import Vector2
from config.constants import M_TO_PX

# ---------------------------------------------------------------------------
# TUNING  (metres, in the attacking team's frame: a = from own goal line, l = across)
# ---------------------------------------------------------------------------
BALL_A        = 75.0           # our man on the ball this far up...
BALL_WIDE     = 13.0           # ...and this far out wide
MIN_PREF      = 0.5            # a role needs at least this "box" run preference to go
SPOTS = {                      # (a, l * ball side): l > 0 is the side the ball is on
    "near post":    (104.0,  3.0),
    "far post":     (103.0, -4.5),
    "penalty spot": (99.0,   0.0),
    "edge":         (93.0,  -2.0),
}
ORDER = {                      # which spots each kind of player prefers, best first
    "striker": ("near post", "far post", "penalty spot"),
    "wide":    ("far post", "penalty spot"),
    "mid":     ("penalty spot", "edge"),
    "am":      ("penalty spot", "far post", "edge"),
}
ONSIDE_GAP    = 0.8            # m: wait this far onside
RUN_FROM      = 4.0            # m from his spot: further than this he runs


def _kind(p):
    slot = getattr(p, "slot", p.role)
    if slot in ("AM", "LAM", "RAM"):
        return "am"                      # a number 10 (config/slots.py): arrives at the penalty spot
    if p.role.startswith("ST"):
        return "striker"
    if p.role in ("LM", "RM"):
        return "wide"
    if p.role in ("LCM", "RCM", "CM", "AM"):
        return "mid"
    return None


def _box_pref(p):
    import ai.run_planner as rp
    try:
        return rp._run_prefs(p).get("box", 0.0)
    except Exception:
        return rp.DEFAULT_RUNS.get(p.role, {}).get("box", 0.0)


def update(run_state, team, opponents, ball):
    owner = ball.owner
    if owner is None or owner not in team or owner.role == "GK" or ball.is_dead:
        return
    from ai.team_shape import to_frame, to_world, _last_line
    a, l = to_frame(owner.team, owner.pos)
    if a < BALL_A or abs(l) < BALL_WIDE:
        return
    side = 1.0 if l > 0 else -1.0
    running = {id(r["player"]) for r in (run_state.get("runs") or {}).values() if "player" in r}
    line = _last_line(owner.team, opponents)
    hold = a < line                                  # ball still behind their line: stay onside
    taken = set()
    cands = []
    for p in team:
        if p is owner or p.role == "GK" or not getattr(p, "is_active", True) or id(p) in running:
            continue
        kind = _kind(p)
        if kind is None or _box_pref(p) < MIN_PREF:
            continue
        if kind == "wide":
            pa, pl = to_frame(p.team, p.pos)
            if pl * side > 0:
                continue                             # he's on the ball side - not his job
        cands.append((0 if kind == "striker" else 1 if kind in ("wide", "am") else 2, kind, p))
    cands.sort(key=lambda c: c[0])
    for _, kind, p in cands:
        spot_name = next((s for s in ORDER[kind] if s not in taken), None)
        if spot_name is None:
            continue
        taken.add(spot_name)
        sa, sl = SPOTS[spot_name]
        if hold:
            sa = min(sa, line - ONSIDE_GAP)
        target = to_world(p.team, sa, sl * side)
        p.target = target
        far = (p.pos - target).length() > RUN_FROM * M_TO_PX
        p.state = "run" if far else "support"
        p.pos_reason = "attack the box: " + spot_name
