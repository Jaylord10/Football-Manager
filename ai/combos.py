"""
ai/combos.py
============
Combination play: runs that two or three players make TOGETHER.

The run planner (ai/run_planner.py) sends players in behind on their own.
These are the classic patterns where one player's movement is a reaction
to a teammate's:

  OVERLAP / UNDERLAP   The winger has the ball.  The full-back on that side
                       bursts past him - round the OUTSIDE if the winger is
                       inside (overlap), or through the INSIDE channel if the
                       winger is hugging the touchline (underlap).  The winger
                       HOLDS IT UP (slows, checks inside, drawing his marker)
                       until the full-back is level, then has a pass - or a
                       defender who doesn't know which way to go.

  RUN BEYOND           A striker drops deep towards the ball, dragging his
                       centre-back with him.  A box-to-box midfielder (or the
                       winger on that side) runs into the space he left, on
                       the last line.

  THIRD MAN            A pass is on its way to a teammate who's facing his
                       own goal (or a striker / midfielder coming short).  A
                       third player who reads it runs beyond him, so the
                       receiver can lay it off or flick it on into his path.

Each is started at most every COMBO_GAP seconds per team, one at a time,
and only by players whose role likes it.  Teamwork and Off The Ball make a
player more likely to spot it.  The runs then work exactly like the run
planner's (through balls, the overlay, stats in sim.py) - they end if the
partner loses or moves the ball on elsewhere.

The far-side winger also stays wide and high when the ball is on the other
flank, so the switch of play is always on - that one lives in
ai/team_shape.py ("stay wide for the switch").

All tuning numbers are in the TUNING block.  Metres and seconds.
"""

import random
from pygame.math import Vector2
from config.constants import WIDTH, HEIGHT, M_TO_PX
from core.utils import distance

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
COMBO_GAP        = 1.5     # s between new combination runs (per team)
CHECK_INTERVAL   = 0.25    # s between looks
KINDS            = ("overlap", "underlap", "beyond", "third_man")

# Overlap / underlap
OVERLAP_ZONE     = (38.0, 95.0)  # winger's distance from our goal for it to happen
OVERLAP_RANGE    = 14.0    # full-back within this of the winger...
OVERLAP_BEHIND   = 12.0    # ...and no more than this far behind him
WIDE_WINGER      = 24.0    # winger this far from the middle = he's wide -> underlap
OVERLAP_AHEAD    = 14.0    # run finishes this far beyond the winger
OUTSIDE_L        = 31.0    # overlap lane (m from the middle)
INSIDE_L         = 16.0    # underlap lane
OVERLAP_CHANCE   = 0.6     # once per spell on the ball for the winger, x full-back's appetite

# Run beyond a dropping striker
DROPPED          = 8.0     # striker this far short of the last line = he's dropped
BEYOND_RANGE     = 22.0    # runner within this of the striker
BEYOND_CHANCE    = 0.35    # once per spell on the ball, x runner's appetite
DROPPING_SPEED   = 1.0     # m/s: the striker must actually be coming towards the ball
BEYOND_STRIKER_NEAR = 15.0 # m: ...and be this close to it

# Third man
THIRD_RECEIVER_SHORT = 6.0 # receiver at least this far short of the last line
THIRD_RANGE      = 25.0    # third man within this of the receiver
THIRD_AHEAD      = 12.0    # run finishes this far beyond the receiver
THIRD_CHANCE     = 0.5     # per pass, x runner's appetite
PASS_JUST_PLAYED = 0.4     # s: only react to a pass in its first moments

ONSIDE           = 1.0     # m onside
MIN_CONDITION    = 0.35    # too tired below this (core/fatigue.py)

# Appetite by position (roles/library.py can override with "combos": {...})
APPETITE = {
    "LB": {"overlap": 0.6}, "RB": {"overlap": 0.6},
    "LCM": {"beyond": 0.5, "third_man": 0.4}, "RCM": {"beyond": 0.5, "third_man": 0.4},
    "LM": {"beyond": 0.4, "third_man": 0.6}, "RM": {"beyond": 0.4, "third_man": 0.6},
    "ST1": {"third_man": 0.6}, "ST2": {"third_man": 0.6},
}

STATS_KEY = "combo"


from core.stats import stat20 as _stat    # (cached: attributes never change during a match)


def appetite(p, kind):
    import roles.library as role_library
    a = dict(APPETITE.get(p.role, {}))
    try:
        role = role_library.role_for(p)
        a.update(getattr(role, "combos", None) or {})
        if p.role in ("LB", "RB") and "overlap" not in (getattr(role, "combos", None) or {}):
            # Attacking full-backs (high fb_height) love to overlap
            fb_h = (role.shape or {}).get("fb_height", 10.0)
            a["overlap"] = max(0.2, min(1.0, (fb_h - 4.0) / 14.0))
        if p.role in ("LCM", "RCM") and "beyond" not in (getattr(role, "combos", None) or {}):
            a["beyond"] = max(0.05, min(1.0, (role.shape or {}).get("cm_forward", 0.5)))
    except Exception:
        pass
    if kind == "underlap":
        kind = "overlap"
    return a.get(kind, 0.0)


def _mind(p):
    """How likely he is to spot it: Teamwork and Off The Ball."""
    return 0.5 + 0.25 * (_stat(p, "Teamwork") + _stat(p, "Off The Ball")) / 20.0


def update(state, team, opponents, ball, now):
    """Called every frame for the team in possession, after the run planner."""
    import ai.run_planner as rp
    import core.fatigue as fatigue
    from ai.team_shape import to_frame, to_world

    runs = state.setdefault("runs", {})
    if now < state.get("combo_next_look", 0.0):
        return
    state["combo_next_look"] = now + CHECK_INTERVAL
    if any(r["kind"] in KINDS for r in runs.values()):
        return
    if now < state.get("combo_next", 0.0):
        return
    tid = team[0].team
    sign = rp._attack_sign(tid)
    line_a = to_frame(tid, Vector2(rp._offside_line_x(sign, opponents), HEIGHT / 2))[0]
    onside_a = line_a - ONSIDE

    def free(p):
        return (p.role != "GK" and not p.has_ball and id(p) not in runs
                and now >= getattr(p, "_run_cooldown_until", 0.0)
                and not getattr(p, "_support_job", False)
                and fatigue.condition(p) >= MIN_CONDITION)

    carrier = ball.owner if ball.owner is not None and ball.owner in team else None
    made = None
    # Each pattern gets ONE roll per spell on the ball (not one every look)
    spell = (id(carrier), getattr(carrier, "last_received_time", 0.0)) if carrier is not None else None
    rolled = state.setdefault("_rolled", set())
    if spell is not None and state.get("_spell") != spell:
        state["_spell"] = spell
        rolled.clear()

    # 1. Overlap / underlap around a winger on the ball
    if carrier is not None and carrier.role in ("LM", "RM"):
        ca, cl = to_frame(tid, carrier.pos)
        if OVERLAP_ZONE[0] <= ca <= OVERLAP_ZONE[1]:
            fb_role = "LB" if carrier.role == "LM" else "RB"
            side = -1.0 if fb_role == "LB" else 1.0
            fb = next((p for p in team if p.role == fb_role and getattr(p, "is_active", True)), None)
            if fb is not None and free(fb):
                fa, fl = to_frame(tid, fb.pos)
                if ca - OVERLAP_BEHIND < fa < ca + 2.0 and distance(fb.pos, carrier.pos) < OVERLAP_RANGE * M_TO_PX \
                        and "overlap" not in rolled:
                    rolled.add("overlap")
                    kind = "underlap" if abs(cl) > WIDE_WINGER else "overlap"
                    if random.random() < OVERLAP_CHANCE * appetite(fb, kind) * _mind(fb):
                        lane = side * (OUTSIDE_L if kind == "overlap" else INSIDE_L)
                        end_a = min(ca + OVERLAP_AHEAD, onside_a)
                        # Straight at the space beside him, then on past him
                        pts = [to_world(tid, ca + 3.0, lane), to_world(tid, end_a, lane)]
                        made = (fb, kind, pts, [carrier], True)

    # 2. Run beyond a striker who has dropped towards the ball
    if made is None and carrier is not None:
        ca, cl = to_frame(tid, carrier.pos)
        for st in (p for p in team if p.role in ("ST1", "ST2") and getattr(p, "is_active", True)
                   and p is not carrier and ("beyond", id(p)) not in rolled):
            sa, sl = to_frame(tid, st.pos)
            if line_a - sa < DROPPED or distance(st.pos, carrier.pos) > BEYOND_STRIKER_NEAR * M_TO_PX:
                continue
            to_ball = carrier.pos - st.pos
            if to_ball.length_squared() < 1e-6 or st.vel.dot(to_ball.normalize()) < DROPPING_SPEED * M_TO_PX:
                continue                    # he isn't coming short
            rolled.add(("beyond", id(st)))
            cands = [p for p in team if free(p) and p.role in ("LCM", "RCM", "LM", "RM")
                     and distance(p.pos, st.pos) < BEYOND_RANGE * M_TO_PX
                     and to_frame(tid, p.pos)[0] < sa + 3.0]
            if not cands:
                continue
            runner = max(cands, key=lambda p: appetite(p, "beyond") * _mind(p))
            if random.random() < BEYOND_CHANCE * appetite(runner, "beyond") * _mind(runner):
                ra, rl = to_frame(tid, runner.pos)
                tl = sl + (4.0 if rl > sl else -4.0)
                pts = [to_world(tid, onside_a, tl)]
                made = (runner, "beyond", pts, [carrier, st], True)
                break

    # 3. Third man: a pass is on its way to a teammate coming short / facing back
    if made is None and ball.owner is None:
        r = getattr(ball, "intended_target", None)
        kicked = getattr(ball, "last_kick_time", -99.0)
        if r is not None and r in team and now - kicked < PASS_JUST_PLAYED and state.get("_third_for") != kicked:
            state["_third_for"] = kicked
            ra, rl = to_frame(tid, r.pos)
            facing_back = (r.facing.x * sign) < 0.0
            if line_a - ra > THIRD_RECEIVER_SHORT and (facing_back or r.role in ("ST1", "ST2", "LCM", "RCM")):
                passer = getattr(ball, "last_owner", None)
                cands = [p for p in team if free(p) and p is not r and p is not passer
                         and p.role not in ("LCB", "RCB")
                         and distance(p.pos, r.pos) < THIRD_RANGE * M_TO_PX
                         and to_frame(tid, p.pos)[0] > ra - 5.0]
                if cands:
                    runner = max(cands, key=lambda p: appetite(p, "third_man") * _mind(p))
                    if random.random() < THIRD_CHANCE * appetite(runner, "third_man") * _mind(runner):
                        pa, pl = to_frame(tid, runner.pos)
                        tl = rl + (6.0 if pl > rl else -6.0)
                        end_a = min(ra + THIRD_AHEAD, onside_a)
                        made = (runner, "third_man", [to_world(tid, end_a, tl)], [r], False)

    if made is None:
        return
    player, kind, pts, partners, must_hold = made
    run = {"kind": kind, "target": Vector2(pts[-1]), "waypoints": [Vector2(p) for p in pts],
           "start": now, "player": player, "received": False,
           "partners": partners, "partners_must_hold": must_hold}
    runs[id(player)] = run
    player._planned_run = run
    rp.STATS[("started", kind)] += 1
    state["combo_next"] = now + COMBO_GAP
