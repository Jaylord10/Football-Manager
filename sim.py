#!/usr/bin/env python3
"""
sim.py - headless test bench for the match engine
=================================================
Runs full matches with no window, as fast as the CPU allows (~10-20 s per
match), and prints the stats you need to judge a change: goals, shots,
possession, pass accuracy, cards, set pieces and keeper own goals.

Typical use (from this folder):

    python sim.py                      # 10 matches, RL tables NOT saved
    python sim.py --matches 30         # more matches = more reliable numbers
    python sim.py --rl                 # switch on Neo + Messi (the learning players) for this run
    python sim.py --train --matches 50 # train Neo + Messi fast and SAVE their Q-tables
    python sim.py --away-roles blue    # give Red the same roles as Blue (fairness test)
    python sim.py --seed 1             # repeatable run (same seed = same matches)

Workflow: run it before a change, make the change, run it again with the same
--seed and --matches, and compare the summary.
"""

import os as _os, sys as _sys
if "--config" in _sys.argv:          # must be set before the game modules load the teams
    _os.environ["FM_MATCH_CONFIG"] = _sys.argv[_sys.argv.index("--config") + 1]
import argparse
import array
import contextlib
import math
import io
import os
import random
import sys
import time

# Must be set before pygame is imported: no window, no sound.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)                 # match_config.json / data/ use relative paths
sys.path.insert(0, HERE)

with contextlib.redirect_stdout(io.StringIO()):
    import pygame              # hide the pygame banner
    from config.constants import WIDTH, HEIGHT, M_TO_PX, FPS, HALF_DURATION_REAL, GOAL_WIDTH, GOAL_HEIGHT
    import gameplay.match_engine as match_engine_module   # (prints "Match Loaded")
    from roles.library import apply_role_set
    import ai.run_planner as run_planner


DT = 1.0 / FPS


def parse_args():
    ap = argparse.ArgumentParser(description="Run matches headless and print stats.")
    ap.add_argument("--matches", type=int, default=10, help="number of matches (default 10)")
    ap.add_argument("--half", type=float, default=HALF_DURATION_REAL,
                    help=f"real seconds per half (default {HALF_DURATION_REAL:g}, same as the game)")
    ap.add_argument("--seed", type=int, default=None, help="random seed for repeatable runs")
    ap.add_argument("--train", action="store_true", help="save Neo/Messi Q-tables after each match")
    ap.add_argument("--rl", action="store_true", help="switch Neo/Messi on for this run (off by default)")
    ap.add_argument("--no-rl", action="store_true", help="force Neo/Messi off")
    ap.add_argument("--home-roles", default=None,
                    help="override Blue's roles: 'blue', 'red', or a role set name from roles/library.py")
    ap.add_argument("--away-roles", default=None,
                    help="override Red's roles: 'blue', 'red', or a role set name from roles/library.py")
    ap.add_argument("--home-defence", default=None,
                    help="Blue's defensive style: low_block, mid_block, press, high_press")
    ap.add_argument("--home-build", default=None, help="Blue's build-up: play_out, mixed, clear")
    ap.add_argument("--away-build", default=None, help="Red's build-up: play_out, mixed, clear")
    ap.add_argument("--home-crossing", default=None,
                    help="Blue's crossing instruction for all wide players and full-backs: more, normal, less "
                         "(or POS=value,POS=value e.g. RM=more,LM=less)")
    ap.add_argument("--away-crossing", default=None, help="Red's crossing instruction (as --home-crossing)")
    ap.add_argument("--away-defence", default=None,
                    help="Red's defensive style: low_block, mid_block, press, high_press")
    ap.add_argument("--verbose", action="store_true", help="show the game's own print output")
    ap.add_argument("--config", default=None,
                    help="match set-up to use instead of match_config.json, e.g. match_config_benchmark.json "
                         "(two average sides - the fairest comparison with real football)")
    return ap.parse_args()


SHOT_OUTCOMES = ("goal", "caught", "parried", "tipped", "blocked", "wide", "over", "other")
THROUGH_OUTCOMES = ("reached_runner", "other_teammate", "intercepted", "keeper", "offside", "out_of_play")


class MatchStats:
    def __init__(self):
        self.passes = [0, 0]
        self.passes_ok = [0, 0]
        self.passes_lost = [0, 0]
        self.shots = [0, 0]            # shots from <= 30 m
        self.long_kicks = [0, 0]       # "shots" from > 30 m (mostly Neo's clearances)
        self.keeper_own_goals = 0
        self.restarts = {}
        self.clear_out = {}          # what happened after each clearance
        self.cross_out = {}          # ...and each cross
        self.header_shots = 0
        self.header_goals = 0
        self.turnovers = 0
        self.play_frames = 0        # frames of match time (halves only)
        self.inplay_frames = 0      # ...with the ball in play
        self.dead_spells = {}       # restart type -> [count, total seconds]
        # What happened to each shot from <= 30 m
        self.outcomes = {k: 0 for k in SHOT_OUTCOMES}
        # Through balls into space
        self.through = {k: 0 for k in THROUGH_OUTCOMES}
        self.through_tried = [0, 0]
        self.through_shots = 0      # completed through ball -> shot within 6 s
        self.through_goals = 0      # completed through ball -> goal within 10 s
        self.offsides = [0, 0]      # offsides given against each team
        self.tackles = [0, 0]       # successful tackles won by each team
        self.press_kept = 0         # pressed on the ball (opponent within 3 m): still ours 3 s later
        self.press_lost = 0         # ...or theirs
        self.wins = [0, 0]          # times each team won the ball from the other...
        self.win_depth = [0.0, 0.0] # ...summed: how far up the pitch (m from their own goal)
        self.wins_high = [0, 0]     # ...in the opposition half
        self.line_sum = [0.0, 0.0]  # back-four depth (m from own goal) while defending, summed...
        self.line_n = [0, 0]        # ...over frames
        self.carry_frames = 0       # frames someone had the ball in open play...
        self.pressured_frames = 0   # ...with an opponent within 3 m


class MoveStats:
    """How outfield players move, sampled every frame (all matches together)."""
    def __init__(self):
        self.accel = array.array('f')      # m/s^2, speeding up (along direction of travel)
        self.brake = array.array('f')      # m/s^2, slowing down
        self.turn = array.array('f')       # deg/s, change of running direction while > 5 m/s
        self.speed_frames = 0
        self.speed_sum = 0.0
        self.sprint_frames = 0             # > 7 m/s
        self.top_speed = 0.0
        self.about_turns = 0               # direction flips > 120 deg in one frame while moving
        self.teleports = 0                 # jumped more than 0.5 m in one frame (open play)
        self.player_seconds = 0.0
        self.distance = 0.0
        self.bands = [0, 0, 0, 0, 0]       # frames walking / jogging / running / high-speed / sprinting
        self.period_dist = [0.0] * 6       # by 15-minute period of the match
        self.period_hsr = [0.0] * 6        # metres above 5.5 m/s
        self.period_time = [0.0] * 6
        self.gassed_frames = 0             # sprint energy below 30%
        self.moving_frames = 0             # off the ball, moving > 1 m/s...
        self.side_frames = 0               # ...shuffling sideways (60-120 deg to facing)
        self.back_frames = 0               # ...backpedalling (> 120 deg)
        self.end_stamina = []              # (stamina at full time, Stamina stat)


MOVE = MoveStats()


def _track_movement(engine, prev):
    """prev: dict id(player) -> (pos, vel) from the previous frame."""
    ball = engine.ball
    open_play = not ball.is_dead and engine.match_state in ("first_half", "second_half")
    players = [p for p in engine.team0 + engine.team1
               if p.role != "GK" and getattr(p, "is_active", True)]
    jumps = 0
    samples = []
    for p in players:
        key = id(p)
        pos, vel = (p.pos.x, p.pos.y), (p.vel.x, p.vel.y)
        old = prev.get(key)
        prev[key] = (pos, vel)
        if old is None or not open_play:
            continue
        (ox, oy), (ovx, ovy) = old
        dx, dy = (pos[0] - ox) / M_TO_PX, (pos[1] - oy) / M_TO_PX
        moved = math.hypot(dx, dy)
        if moved > 0.5:          # half a metre in one frame (30 m/s) = a visible jump
            jumps += 1
            continue
        if moved / DT > 13.0:
            continue                 # small set-piece adjustment, not running
        samples.append((moved, vel, (ovx, ovy)))
        if getattr(p, "energy", 1.0) < 0.3:
            MOVE.gassed_frames += 1
        if not p.has_ball and p.vel.length() > 1.0 * M_TO_PX and p.facing.length_squared() > 0:
            MOVE.moving_frames += 1
            c = max(-1.0, min(1.0, p.vel.normalize().dot(p.facing.normalize())))
            ang = math.degrees(math.acos(c))
            if ang > 120:
                MOVE.back_frames += 1
            elif ang > 60:
                MOVE.side_frames += 1
    if jumps > 4:            # kick-off / restart reset - not a real movement
        return
    MOVE.teleports += jumps
    half = match_engine_module.HALF_DURATION_REAL
    period = min(2, int(3 * engine.half_elapsed / half)) + (3 if engine.match_state == "second_half" else 0)
    for moved, (vx, vy), (ovx, ovy) in samples:
        v = v_now = math.hypot(vx, vy) / M_TO_PX
        ov = math.hypot(ovx, ovy) / M_TO_PX
        MOVE.player_seconds += DT
        MOVE.distance += moved
        MOVE.period_dist[period] += moved
        MOVE.period_time[period] += DT
        if v_now > 5.5:
            MOVE.period_hsr[period] += moved
        MOVE.speed_frames += 1
        MOVE.speed_sum += v
        MOVE.top_speed = max(MOVE.top_speed, v)
        if v > 7.0:
            MOVE.sprint_frames += 1
        MOVE.bands[0 if v < 2.0 else 1 if v < 4.0 else 2 if v < 5.5 else 3 if v < 7.0 else 4] += 1
        if ov > 0.5:
            ux, uy = ovx / (ov * M_TO_PX), ovy / (ov * M_TO_PX)
            dvx, dvy = (vx - ovx) / M_TO_PX / DT, (vy - ovy) / M_TO_PX / DT
            along = dvx * ux + dvy * uy
            if along >= 0:
                MOVE.accel.append(along)
            else:
                MOVE.brake.append(-along)
            if v > 0.5:
                cosang = max(-1.0, min(1.0, (vx * ovx + vy * ovy) / (v * ov * M_TO_PX * M_TO_PX)))
                ang = math.degrees(math.acos(cosang))
                if ang > 120 and ov > 1.0:
                    MOVE.about_turns += 1
                if ov > 5.0:
                    MOVE.turn.append(ang / DT)


def _pctl(arr, q):
    if not arr:
        return 0.0
    s = sorted(arr)
    return s[min(len(s) - 1, int(q * len(s)))]


def print_movement_summary():
    m = MOVE
    if m.speed_frames == 0:
        return
    mins = m.player_seconds / 60.0
    print("Player movement (outfield, open play):")
    print(f"  distance:             {m.distance / mins:.0f} m per player-minute   (real ~110 per match-minute, ~130-160 while the ball is in play)")
    print(f"  average / top speed:  {m.speed_sum / m.speed_frames:.1f} / {m.top_speed:.1f} m/s   (real ~1.8 per match-minute / 9-10)")
    print(f"  time sprinting >7m/s: {100 * m.sprint_frames / m.speed_frames:.1f}%   (real ~1-1.5% of ball-in-play time)")
    b = [100.0 * x / m.speed_frames for x in m.bands]
    print(f"  time walk/jog/run/hsr/sprint: {b[0]:.0f}/{b[1]:.0f}/{b[2]:.0f}/{b[3]:.1f}/{b[4]:.1f}%"
          f"   (real, ball in play: roughly 45/40/10/3.5/1)")
    print(f"  acceleration p95/max: {_pctl(m.accel, 0.95):.1f} / {_pctl(m.accel, 0.999):.1f} m/s2   (real ~3 / 6)")
    print(f"  braking p95/max:      {_pctl(m.brake, 0.95):.1f} / {_pctl(m.brake, 0.999):.1f} m/s2   (real ~4 / 8)")
    print(f"  turning at >5 m/s:    p95 {_pctl(m.turn, 0.95):.0f} deg/s   (real ~60-90)")
    print(f"  about-turns:          {m.about_turns / mins:.1f} per player-minute   (real ~0)")
    print(f"  teleports:            {m.teleports}   (should be 0)")
    if m.moving_frames:
        print(f"  off-ball movement:    {100 * m.side_frames / m.moving_frames:.0f}% sideways, "
              f"{100 * m.back_frames / m.moving_frames:.0f}% backwards (rest forwards)")
    pt = [max(t, 1e-9) / 60.0 for t in m.period_time]
    print("Fatigue:")
    print("  distance by 15 min:   " + " ".join(f"{m.period_dist[i] / pt[i]:.0f}" for i in range(6))
          + " m/min   (real: falls ~5-10% by the last 15)")
    print("  high-speed by 15 min: " + " ".join(f"{m.period_hsr[i] / pt[i]:.1f}" for i in range(6))
          + " m/min   (real: last 15 ~15-20% below the first)")
    print(f"  time gassed (<30% sprint energy): {100 * m.gassed_frames / m.speed_frames:.1f}%")
    if m.end_stamina:
        es = sorted(m.end_stamina)
        avg = sum(x for x, _ in es) / len(es)
        by = {}
        for x, st in es:
            band = "Stamina 16+" if st >= 16 else "Stamina <11" if st < 11 else "Stamina 11-15"
            by.setdefault(band, []).append(x)
        print(f"  stamina at full time: avg {avg:.2f}, lowest {es[0][0]:.2f}, highest {es[-1][0]:.2f}; "
              + ", ".join(f"{k} {sum(v) / len(v):.2f}" for k, v in sorted(by.items())))


def instrument(engine, st):
    """Wrap the engine's mechanics so we can count events without changing game code."""
    mech = engine.mechanics
    pending = {"pass_team": None, "shot": None, "through": None, "through_done": None}

    orig_pass = mech.execute_pass
    def counted_pass(passer, receiver, ball, current_time, opponents=None, through_plan=None):
        st.passes[passer.team] += 1
        pending["pass_team"] = passer.team
        if through_plan is not None:
            st.through_tried[passer.team] += 1
            pending["through"] = {"team": passer.team, "runner": receiver, "t": current_time}
        return orig_pass(passer, receiver, ball, current_time, opponents, through_plan)
    mech.execute_pass = counted_pass

    orig_shot = mech.execute_shot
    def counted_shot(player, ball, current_time, opponents=None, **kwargs):
        goal_x = WIDTH if player.team == 0 else 0
        dist_m = ((goal_x - player.pos.x) ** 2 + (HEIGHT / 2 - player.pos.y) ** 2) ** 0.5 / M_TO_PX
        done = pending.get("through_done")
        if done and done["team"] == player.team and current_time - done["t"] < 6.0 and not done.get("shot"):
            st.through_shots += 1
            done["shot"] = True
        if dist_m <= 30:
            st.shots[player.team] += 1
            if pending["shot"] is not None:
                st.outcomes["other"] += 1          # previous shot never resolved
            pending["shot"] = {"team": player.team, "frames": 0, "t": current_time}
        else:
            st.long_kicks[player.team] += 1
        pending["pass_team"] = None
        return orig_shot(player, ball, current_time, opponents, **kwargs)
    mech.execute_shot = counted_shot

    orig_out = mech.resolve_out_of_play
    def counted_out(ball, *a, **k):
        result = orig_out(ball, *a, **k)
        kind = ball.restart_type or "other"
        st.restarts[kind] = st.restarts.get(kind, 0) + 1
        return result
    mech.resolve_out_of_play = counted_out

    for name, label in (("setup_free_kick", "free_kick"), ("setup_penalty", "penalty")):
        orig = getattr(mech, name)
        def counted(*a, _orig=orig, _label=label, **k):
            st.restarts[_label] = st.restarts.get(_label, 0) + 1
            return _orig(*a, **k)
        setattr(mech, name, counted)

    import gameplay.aerial as aerial_mod
    orig_header = aerial_mod.__dict__.setdefault("_orig_header_shot", aerial_mod.header_shot)
    def counted_header(p, ball, now, opponents, clean=True):
        st.shots[p.team] += 1
        st.header_shots += 1
        if pending["shot"] is not None:
            st.outcomes["other"] += 1
        pending["shot"] = {"team": p.team, "frames": 0, "t": now}
        pending["pass_team"] = None
        return orig_header(p, ball, now, opponents, clean)
    aerial_mod.header_shot = counted_header

    orig_goal = engine._reset_after_goal
    def counted_goal(scorer):
        si = getattr(engine.ball, "shot_info", None) or {}
        if si.get("type") == "header" and si.get("time") == getattr(engine.ball, "last_kick_time", None):
            st.header_goals += 1
        done = pending.get("through_done")
        if done and done["team"] == scorer and engine.time_elapsed - done["t"] < 10.0:
            st.through_goals += 1
            pending["through_done"] = None
        lt = engine.ball.last_toucher
        if lt is not None and lt.role == "GK" and lt.team != scorer:
            st.keeper_own_goals += 1
        return orig_goal(scorer)
    engine._reset_after_goal = counted_goal

    return pending


def _track_through(engine, st, pending):
    tb = pending["through"]
    if tb is None:
        return
    ball = engine.ball

    def done(kind):
        st.through[kind] += 1
        pending["through"] = None
        if kind == "reached_runner":
            pending["through_done"] = {"team": tb["team"], "t": engine.time_elapsed}

    if engine.offside_system.offside_detected:
        return done("offside")
    if ball.is_dead or ball.restart_type is not None:
        return done("out_of_play")
    owner = ball.owner
    if owner is not None:
        if owner is tb["runner"]:
            return done("reached_runner")
        if owner.team == tb["team"]:
            return done("other_teammate")
        return done("keeper" if owner.role == "GK" else "intercepted")
    if engine.time_elapsed - tb["t"] > 6.0:
        return done("out_of_play")


def _track_shot(engine, st, pending, prev_pos, prev_z, prev_toucher, prev_score):
    """Follow the most recent shot until we know how it ended."""
    shot = pending["shot"]
    if shot is None:
        return
    shot["frames"] += 1
    ball = engine.ball
    team = shot["team"]

    def done(kind):
        st.outcomes[kind] += 1
        pending["shot"] = None

    if engine.score != prev_score:
        return done("goal")
    if ball.is_dead or ball.restart_type is not None:
        x, y = prev_pos
        top, bottom = HEIGHT / 2 - GOAL_WIDTH / 2, HEIGHT / 2 + GOAL_WIDTH / 2
        crossed_goal_line = x < 0 or x > WIDTH
        if crossed_goal_line and top < y < bottom and prev_z > GOAL_HEIGHT:
            return done("over")
        if crossed_goal_line or y < 0 or y > HEIGHT:
            return done("wide")
        return done("other")
    rc = getattr(ball, "last_ricochet", None)
    if rc is not None and rc["time"] >= shot.get("t", 1e9):
        return done("blocked")                         # came off a player (gameplay/ricochet.py)
    lt = ball.last_toucher
    if lt is not prev_toucher and lt is not None and lt.role == "GK" and lt.team != team:
        sv = getattr(ball, "last_save", None) or {}
        if sv.get("type") == "tip":
            return done("tipped")
        return done("caught" if ball.owner is lt else "parried")
    owner = ball.owner
    if owner is not None:
        if owner.role == "GK" and owner.team != team:
            return done("caught")
        if owner.team != team:
            return done("blocked")
        return done("other")
    if shot["frames"] > 4 * FPS:
        return done("other")


def _track_cross(engine, st, pending):
    """Did each (lofted) cross find a team-mate first?"""
    ball = engine.ball
    lc = getattr(ball, "last_cross", None)
    cur = pending.get("cross")
    if lc is not None and lc is not pending.get("cross_seen"):
        pending["cross_seen"] = lc
        cur = pending["cross"] = dict(lc)
    if cur is None:
        return

    def done(k):
        st.cross_out[k] = st.cross_out.get(k, 0) + 1
        pending["cross"] = None

    lt = ball.last_toucher
    if ball.is_dead or ball.restart_type is not None:
        return done("out of play")
    if lt is not None and lt is not cur["passer"]:
        return done("found a team-mate" if lt.team == cur["team"] else "won by them")
    if engine.time_elapsed - cur["time"] > 5.0:
        return done("nobody")


def _track_clearance(engine, st, pending):
    """Where did each clearance end up?"""
    ball = engine.ball
    lc = getattr(ball, "last_clearance", None)
    cur = pending.get("clear")
    if lc is not None and lc is not pending.get("clear_seen"):
        pending["clear_seen"] = lc
        if cur is not None:
            st.clear_out["other"] = st.clear_out.get("other", 0) + 1
        cur = pending["clear"] = dict(lc)
    if cur is None:
        return

    def done(k):
        st.clear_out[k] = st.clear_out.get(k, 0) + 1
        pending["clear"] = None

    rc = getattr(ball, "last_ricochet", None)
    if rc is not None and rc["time"] >= cur["time"] and rc["time"] - cur["time"] < 0.4 \
            and rc["player"].team != cur["team"]:
        return done("charged down")
    if ball.is_dead and ball.restart_type is not None:
        kind = ball.restart_type
        if kind == "throw_in":
            ours = ball.restart_taker is not None and ball.restart_taker.team == cur["team"]
            return done("throw-in (ours)" if ours else "throw-in (theirs)")
        if kind == "corner_kick":
            return done("corner (theirs)")
        return done(kind)
    if ball.owner is not None and ball.owner is not cur["player"]:
        return done("won by us" if ball.owner.team == cur["team"] else "won by them")
    if engine.time_elapsed - cur["time"] > 12.0:
        return done("other")


def play_match(args):
    quiet = not args.verbose
    out = io.StringIO()
    match_engine_module.RL_ENABLED = (args.rl or args.train) and not args.no_rl
    with contextlib.redirect_stdout(out if quiet else sys.stdout):
        engine = match_engine_module.MatchEngine()
    import ai.tactics as tactics
    tactics.OVERRIDE.clear()
    import roles.library as _rl
    _rl.OVERRIDE_INSTRUCTIONS.clear()
    for tid, spec in ((0, args.home_crossing), (1, args.away_crossing)):
        if spec:
            pos_map = {}
            if "=" in spec:
                for part in spec.split(","):
                    pos, val = part.split("=")
                    pos_map[pos.strip()] = {"crossing": val.strip()}
            else:
                for pos in ("LB", "RB", "LM", "RM"):
                    pos_map[pos] = {"crossing": spec}
            _rl.OVERRIDE_INSTRUCTIONS[tid] = pos_map
    tactics.OVERRIDE_BUILD.clear()
    for tid, b in ((0, args.home_build), (1, args.away_build)):
        if b:
            tactics.OVERRIDE_BUILD[tid] = b
    for tid, d in ((0, args.home_defence), (1, args.away_defence)):
        if d:
            tactics.OVERRIDE[tid] = d
    for team, override in ((engine.team0, args.home_roles), (engine.team1, args.away_roles)):
        if override:
            apply_role_set(team, override)
    match_engine_module.HALF_DURATION_REAL = args.half  # engine reads this module global

    for agent in (engine.rl_agent, engine.messi_agent):
        if agent is not None:
            agent.save_enabled = args.train
    if args.no_rl:
        for p in engine.team0 + engine.team1:
            p.rl_agent = None
        engine.rl_agent = None
        engine.messi_agent = None

    st = MatchStats()
    pending = instrument(engine, st)
    move_prev = {}
    last_owner = None
    max_frames = int((args.half * 2 + 60) / DT)

    for _ in range(max_frames):
        if engine.match_state == "full_time":
            break
        ball = engine.ball
        prev_pos, prev_z = (ball.pos.x, ball.pos.y), ball.z
        prev_toucher = ball.last_toucher
        prev_score = list(engine.score)
        if quiet:
            with contextlib.redirect_stdout(out):
                engine.step(DT)
            out.seek(0); out.truncate(0)
        else:
            engine.step(DT)

        _track_shot(engine, st, pending, prev_pos, prev_z, prev_toucher, prev_score)
        _track_through(engine, st, pending)
        _track_clearance(engine, st, pending)
        _track_cross(engine, st, pending)
        off = engine.offside_system
        if off.offside_detected and not pending.get("offside_flag"):
            if off.offside_team in (0, 1):
                st.offsides[off.offside_team] += 1
        pending["offside_flag"] = off.offside_detected
        _track_movement(engine, move_prev)
        if engine.match_state in ("first_half", "second_half"):
            dead = engine.ball.is_dead or off.offside_detected
            if engine.match_state != pending.get("half"):
                pending["half"] = engine.match_state
                pending["half_start"] = True       # the opening kick-off of a half
            if not dead:
                pending["half_start"] = False
            # The kick-off at the start of each half isn't counted: with short
            # test matches there are far more of them than in a real 90 minutes.
            if not pending.get("half_start"):
                st.play_frames += 1
                if not dead:
                    st.inplay_frames += 1
                spell = pending.get("dead_spell")
                if dead and spell is None:
                    kind = engine.ball.restart_type or ("offside" if off.offside_detected else None)
                    if kind == "free_kick":
                        kind = "free_kick_" + str(getattr(engine.ball, "_fk_zone", "?"))
                    pending["dead_spell"] = [kind, engine.time_elapsed]
                elif dead and spell[0] is None and engine.ball.restart_type:
                    spell[0] = engine.ball.restart_type
                elif not dead and spell is not None:
                    c = st.dead_spells.setdefault(spell[0] or "other", [0, 0.0])
                    c[0] += 1
                    c[1] += engine.time_elapsed - spell[1]
                    pending["dead_spell"] = None
        own = engine.ball.owner
        if own is not None and own.role != "GK" and not engine.ball.is_dead \
                and engine.match_state in ("first_half", "second_half"):
            st.carry_frames += 1
            dt_ = 1 - own.team                        # the defending team
            back = [p for p in (engine.team0 if dt_ == 0 else engine.team1)
                    if p.role in ("LB", "LCB", "RCB", "RB")]
            if back:
                xs = [p.pos.x / M_TO_PX if dt_ == 0 else (WIDTH - p.pos.x) / M_TO_PX for p in back]
                st.line_sum[dt_] += sum(xs) / len(xs)
                st.line_n[dt_] += 1
            opps = engine.team1 if own.team == 0 else engine.team0
            if any((o.pos - own.pos).length() < 3.0 * M_TO_PX for o in opps):
                st.pressured_frames += 1
                if pending.get("press_ep") is None:
                    pending["press_ep"] = (own.team, engine.time_elapsed)
        ep = pending.get("press_ep")
        if ep is not None and engine.time_elapsed - ep[1] >= 3.0:
            pending["press_ep"] = None
            if engine.ball.is_dead and engine.ball.restart_type is not None:
                pass                                   # out of play: don't count
            else:
                cur = engine.ball.owner.team if engine.ball.owner is not None else engine.ai.last_possession_team
                if cur == ep[0]:
                    st.press_kept += 1
                else:
                    st.press_lost += 1

        owner = engine.ball.owner
        if owner is not None and owner is not last_owner:
            if pending["pass_team"] is not None:
                if owner.team == pending["pass_team"]:
                    st.passes_ok[owner.team] += 1
                else:
                    st.passes_lost[pending["pass_team"]] += 1
                pending["pass_team"] = None
            if last_owner is not None and owner.team != last_owner.team:
                st.turnovers += 1
                d = owner.pos.x / M_TO_PX if owner.team == 0 else (WIDTH - owner.pos.x) / M_TO_PX
                st.wins[owner.team] += 1
                st.win_depth[owner.team] += d
                if d > WIDTH / M_TO_PX / 2:
                    st.wins_high[owner.team] += 1
                if owner.state == "tackle":
                    st.tackles[owner.team] += 1
            last_owner = owner

    for p in engine.team0 + engine.team1:
        if p.role != "GK" and getattr(p, "is_active", True):
            stv = p.attributes.get("Stamina", 10)
            MOVE.end_stamina.append((p.stamina, stv / 5.0 if stv > 25 else stv))
    if engine.match_state != "full_time":
        # Make sure RL agents still get their end-of-match update when training
        with contextlib.redirect_stdout(out if quiet else sys.stdout):
            engine._start_fulltime()

    total = sum(engine.possession_frames) or 1
    cards = [[sum(p.yellow_cards for p in t), sum(p.red_card for p in t)]
             for t in (engine.team0, engine.team1)]
    return {
        "score": list(engine.score),
        "possession": [f / total for f in engine.possession_frames],
        "stats": st,
        "cards": cards,
        "messi_eps": getattr(engine.messi_agent, "epsilon", None),
        "neo_eps": getattr(engine.rl_agent, "epsilon", None),
    }


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "-"


def main():
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    rl_on = (args.rl or args.train) and not args.no_rl
    print(f"Running {args.matches} match(es), {args.half:g}s halves"
          f"{', Neo+Messi ON' if rl_on else ''}{', TRAINING (Q-tables saved)' if args.train else ''}"
          f"{', Blue roles: ' + args.home_roles if args.home_roles else ''}"
          f"{', Red roles: ' + args.away_roles if args.away_roles else ''}\n")
    print(f"{'#':>3}  {'Score':>7}  {'Poss B/R':>9}  {'Shots':>7}  {'Pass% B/R':>10}  {'Cards Y/R':>9}  time")

    results = []
    for i in range(args.matches):
        t0 = time.time()
        r = play_match(args)
        results.append(r)
        st = r["stats"]
        acc = [pct(st.passes_ok[t], st.passes_ok[t] + st.passes_lost[t]) for t in (0, 1)]
        yel = r["cards"][0][0] + r["cards"][1][0]
        red = r["cards"][0][1] + r["cards"][1][1]
        print(f"{i+1:>3}  {r['score'][0]:>3}-{r['score'][1]:<3}  "
              f"{r['possession'][0]*100:>3.0f}/{r['possession'][1]*100:<3.0f}   "
              f"{st.shots[0]:>3}-{st.shots[1]:<3}  {acc[0]:>4}/{acc[1]:<4}   "
              f"{yel:>3}/{red:<3}     {time.time()-t0:.0f}s")

    n = len(results)
    n90 = n * 2.0 * args.half / 5400.0          # how many full 90 minutes of football that was
    g = [sum(r["score"][t] for r in results) for t in (0, 1)]
    w = sum(r["score"][0] > r["score"][1] for r in results)
    l = sum(r["score"][0] < r["score"][1] for r in results)
    shots = [sum(r["stats"].shots[t] for r in results) for t in (0, 1)]
    longk = [sum(r["stats"].long_kicks[t] for r in results) for t in (0, 1)]
    ok = [sum(r["stats"].passes_ok[t] for r in results) for t in (0, 1)]
    lost = [sum(r["stats"].passes_lost[t] for r in results) for t in (0, 1)]
    poss = [sum(r["possession"][t] for r in results) / n for t in (0, 1)]
    yel = sum(r["cards"][0][0] + r["cards"][1][0] for r in results)
    red = sum(r["cards"][0][1] + r["cards"][1][1] for r in results)
    kog = sum(r["stats"].keeper_own_goals for r in results)
    restarts = {}
    for r in results:
        for k, v in r["stats"].restarts.items():
            restarts[k] = restarts.get(k, 0) + v

    print("\n=== SUMMARY (Blue = home, Red = away) ===")
    print(f"Football played:        {n} match(es) x {2 * args.half / 60:.0f} min = {n90:.1f} x 90 minutes"
          f"   (rates below are PER 90 MINUTES, both teams together)")
    pf_ = sum(r["stats"].play_frames for r in results)
    ip_ = sum(r["stats"].inplay_frames for r in results)
    print(f"Ball in play:           {pct(ip_, pf_)} of the match   (real ~56-60%: Premier League 2023-27; kick-offs at the start of each half not counted)")
    print(f"Results (Blue W/D/L):   {w}/{n-w-l}/{l}")
    print(f"Goals:                  {g[0]}-{g[1]}  ({(g[0]+g[1])/n90:.1f} per 90; real ~2.7)")
    print(f"Keeper own goals:       {kog}")
    print(f"Shots (<=30 m):         {shots[0]}-{shots[1]}  ({(shots[0]+shots[1])/n90:.0f} per 90, real ~25; "
          f"conversion {pct(g[0]+g[1]-kog, shots[0]+shots[1])})")
    oc = {k: sum(r["stats"].outcomes[k] for r in results) for k in SHOT_OUTCOMES}
    total_shots = shots[0] + shots[1]
    on_target = oc["goal"] + oc["caught"] + oc["parried"] + oc["tipped"]
    print(f"  on target:            {pct(on_target, total_shots)}   (real football ~33%)")
    print(f"  scored:               {pct(oc['goal'], total_shots)}   (real football ~10%)")
    saves_ = oc['caught'] + oc['parried'] + oc['tipped']
    print(f"  keeper saves:         {pct(saves_, on_target)} of shots on target (real ~70%): "
          f"held {pct(oc['caught'], saves_)}, tipped behind {pct(oc['tipped'], saves_)}, "
          f"parried back into play {pct(oc['parried'], saves_)}")
    import gameplay.ricochet as _rc
    print(f"  blocked:              {pct(oc['blocked'], total_shots)} of shots   (real ~25-30%)")
    print(f"Ricochets:              {(_rc.STATS['block'] + _rc.STATS['glance']) / n90:.0f} per 90 "
          f"({_rc.STATS['block'] / n90:.0f} blocks, {_rc.STATS['glance'] / n90:.0f} glancing deflections; "
          f"off shots {_rc.STATS['off_shot'] / n90:.0f}, passes/crosses {_rc.STATS['off_pass'] / n90:.0f}, "
          f"other ricochets {_rc.STATS['off_ricochet'] / n90:.0f})")
    print("  breakdown:            " + ", ".join(f"{k} {oc[k]}" for k in SHOT_OUTCOMES))
    tt = [sum(r["stats"].through_tried[t] for r in results) for t in (0, 1)]
    tho = {k: sum(r["stats"].through[k] for r in results) for k in THROUGH_OUTCOMES}
    tshots = sum(r["stats"].through_shots for r in results)
    tgoals = sum(r["stats"].through_goals for r in results)
    print(f"Through balls:          {tt[0]}-{tt[1]}  ({(tt[0]+tt[1])/n90:.0f} per 90, real ~5; "
          f"reached runner {pct(tho['reached_runner'], tt[0]+tt[1])}, led to {tshots} shots / {tgoals} goals)")
    print("  outcomes:             " + ", ".join(f"{k} {tho[k]}" for k in THROUGH_OUTCOMES))
    offs = [sum(r["stats"].offsides[t] for r in results) for t in (0, 1)]
    rs = run_planner.STATS
    kinds = sorted({k for (_, k) in rs})
    if kinds:
        parts = []
        for k in kinds:
            st_ = rs[("started", k)]
            parts.append(f"{k} {st_ / n90:.0f}/90 (passed to {pct(rs[('targeted', k)], st_)}, "
                         f"got the ball {pct(rs[('received', k)], st_)})")
        print("Planned runs:           " + "; ".join(parts))
    print(f"Offsides:               {offs[0]}-{offs[1]}  ({(offs[0]+offs[1])/n90:.1f} per 90; real ~4)")
    print(f"Long kicks (>30 m):     {longk[0]}-{longk[1]}  (mostly clearances)")
    print(f"Possession:             {poss[0]*100:.0f}% / {poss[1]*100:.0f}%")
    print(f"Pass accuracy:          {pct(ok[0], ok[0]+lost[0])} / {pct(ok[1], ok[1]+lost[1])}   (real ~80-85%)")
    print(f"Passes:                 {(sum(ok)+sum(lost))/n90:.0f} per 90   (real ~850-950)")
    print(f"Cards:                  {yel} yellow, {red} red  ({yel/n90:.1f} yellow per 90; real ~3.7)")
    tk = [sum(r["stats"].tackles[t] for r in results) for t in (0, 1)]
    turn = sum(r["stats"].turnovers for r in results)
    cf = sum(r["stats"].carry_frames for r in results)
    pf = sum(r["stats"].pressured_frames for r in results)
    print(f"Tackles won:            {tk[0]}-{tk[1]}  ({(tk[0]+tk[1])/n90:.0f} per 90); "
          f"turnovers {turn/n90:.0f} per 90")
    print(f"Carrier under pressure: {pct(pf, cf)} of time on the ball (opponent within 3 m)")
    pk = sum(r["stats"].press_kept for r in results)
    pl_ = sum(r["stats"].press_lost for r in results)
    print(f"  escaped the pressure: {pct(pk, pk + pl_)} still had the ball 3 s later ({(pk + pl_) / n90:.0f} times per 90)")
    import ai.tactics as tactics
    names = [tactics.style_name(t) for t in (0, 1)]
    wins = [sum(r["stats"].wins[t] for r in results) for t in (0, 1)]
    wdep = [sum(r["stats"].win_depth[t] for r in results) for t in (0, 1)]
    whigh = [sum(r["stats"].wins_high[t] for r in results) for t in (0, 1)]
    lsum = [sum(r["stats"].line_sum[t] for r in results) for t in (0, 1)]
    ln = [sum(r["stats"].line_n[t] for r in results) for t in (0, 1)]
    print(f"Defensive style:        {names[0]} / {names[1]}")
    print("  back line height:     " + " / ".join(f"{lsum[t] / ln[t]:.0f} m" if ln[t] else "-" for t in (0, 1))
          + "   (average, from own goal, while defending)")
    print("  ball won at:          " + " / ".join(f"{wdep[t] / wins[t]:.0f} m" if wins[t] else "-" for t in (0, 1))
          + "   (average, from own goal)")
    print("  won in their half:    " + " / ".join(pct(whigh[t], wins[t]) for t in (0, 1)))
    from gameplay import duels
    ds = duels.STATS
    names = sorted({k[1] for k in ds if isinstance(k, tuple) and k[0] == "takeon"},
                   key=lambda nm: -ds[("takeon", nm)])
    t_all = sum(ds[("takeon", nm)] for nm in names)
    w_all = sum(ds[("takeon_won", nm)] for nm in names)
    print(f"Take-ons:               {t_all / n90:.0f} per 90 (real ~35), beat his man {pct(w_all, t_all)}"
          f"   (real: league average ~50%, Messi ~57%)")
    print("  most attempts:        " + ", ".join(
        f"{nm.split()[-1]} {ds[('takeon_won', nm)]}/{ds[('takeon', nm)]} ({pct(ds[('takeon_won', nm)], ds[('takeon', nm)])})"
        for nm in names[:6]))
    from gameplay.mechanics import GameMechanics
    cs_ = GameMechanics.CUT_STATS
    print(f"Interceptions:          {cs_['intercepted'] / n90:.0f} per 90 (real ~20), "
          f"plus {cs_['deflected'] / n90:.0f} per 90 knocked loose")
    print(f"Tackles attempted:      {ds['tackle'] / n90:.0f} per 90 (real ~35), won {pct(ds['tackle_won'], ds['tackle'])}")
    import gameplay.crossing as _cr
    xo = {}
    for r in results:
        for k, v in r["stats"].cross_out.items():
            xo[k] = xo.get(k, 0) + v
    nx = sum(xo.values())
    C_ = _cr.STATS
    print(f"Crosses:                {(C_['cross'] + C_['cut_back']) / n90:.0f} per 90 from open play (Blue {C_['open0'] / n90:.0f} / Red {C_['open1'] / n90:.0f}; incl. {C_['cut_back'] / n90:.0f} cut-backs), "
          f"{C_['set_piece'] / n90:.0f} from corners / free kicks   (real: ~25-30 from open play + ~10 corners; about a quarter find a team-mate)")
    if nx:
        print("  in the air, first touch: " + ", ".join(f"{k} {pct(v, nx)}" for k, v in sorted(xo.items(), key=lambda kv: -kv[1])))
    import gameplay.aerial as _ae
    A = _ae.STATS
    hs = sum(r["stats"].header_shots for r in results)
    hg = sum(r["stats"].header_goals for r in results)
    won = A['won_att'] + A['won_def']
    print(f"Aerial duels:           {A['duels'] / n90:.0f} per 90 challenged (real ~35-45), plus {A['free_headers'] / n90:.0f} free headers at goal; "
          f"won by the side that played it {pct(A['won_att'], won)}; nobody won it {A['nobody'] / n90:.0f}; fouls {A['fouls'] / n90:.1f}")
    print(f"  won by:               defenders {A['won_by_def'] / n90:.0f}, midfielders {A['won_by_mid'] / n90:.0f}, "
          f"forwards {A['won_by_fwd'] / n90:.0f}, keepers {A['won_by_gk'] / n90:.0f} "
          f"(caught {A['gk_catch'] / n90:.0f}, punched {A['gk_punch'] / n90:.0f})")
    print(f"  headers:              at goal {hs / n90:.1f} per 90 (scored {hg}; {pct(hg, g[0] + g[1])} of all goals, real ~14%), "
          f"clearances {A['clearance'] / n90:.0f}, passes / flick-ons {A['pass'] / n90:.0f}, headed on {A['on'] / n90:.0f}")
    import ai.clearance as _cl
    co = {}
    for r in results:
        for k, v in r["stats"].clear_out.items():
            co[k] = co.get(k, 0) + v
    ncl = sum(co.values())
    print(f"Clearances:             {(_cl.STATS['away'] + _cl.STATS['touch'] + _cl.STATS['behind']) / n90:.0f} per 90 "
          f"(real ~50 - 18-32 a team, a lot of them headed)  "
          f"away {_cl.STATS['away'] / n90:.0f}, into touch {_cl.STATS['touch'] / n90:.0f}, behind {_cl.STATS['behind'] / n90:.0f}; "
          f"headed {_cl.STATS['headed'] / n90:.0f}, first time {_cl.STATS['first_time'] / n90:.0f}, sliced {_cl.STATS['sliced'] / n90:.0f}; "
          f"Blue {_cl.STATS['team0'] / n90:.0f} / Red {_cl.STATS['team1'] / n90:.0f}")
    if ncl:
        print("  ended up:             " + ", ".join(f"{k} {pct(v, ncl)}" for k, v in sorted(co.items(), key=lambda kv: -kv[1])))
    print("Restarts per 90:        " + ", ".join(f"{k} {v / n90:.0f}" for k, v in sorted(restarts.items()))
          + "   (real: corners ~10, free kicks ~22, throw-ins ~36, goal kicks ~15.5)")
    spells = {}
    for r in results:
        for k, (c, t) in r["stats"].dead_spells.items():
            a = spells.setdefault(k, [0, 0.0])
            a[0] += c
            a[1] += t
    real_t = {"throw_in": "16", "goal_kick": "29", "corner_kick": "35", "free_kick_long": "~25",
              "free_kick_delivery": "~40", "free_kick_shoot": "60+", "kick_off": "60-75 after a goal"}
    print("Restart time (avg s):   " + ", ".join(
        f"{k} {t / c:.0f}" + (f" (real {real_t[k]})" if k in real_t else "")
        for k, (c, t) in sorted(spells.items()) if c))
    print(f"                        free kicks overall {sum(spells[k][1] for k in spells if k.startswith('free_kick')) / max(1, sum(spells[k][0] for k in spells if k.startswith('free_kick'))):.0f} s (real ~33)")
    print_movement_summary()
    last = results[-1]
    if last["messi_eps"] is not None or last["neo_eps"] is not None:
        def f(x):
            return "-" if x is None else f"{x:.2f}"
        print(f"RL exploration (ε):     Messi {f(last['messi_eps'])}, Neo {f(last['neo_eps'])}"
              f"{'' if args.train else '  (not saved - use --train to save)'}")


if __name__ == "__main__":
    main()
