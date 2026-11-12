"""
ai/pressing.py
==============
Closing down the man on the ball.

Before this, nobody was ever told to press: role code could aim a player
near the ball carrier, but he jogged there like any other repositioning.
Now, while the opposition have the ball, one player is the PRESSER:

  1. Every candidate gets a cost: how long he'd take to reach the carrier,
     plus penalties - centre-backs don't get dragged out unless the ball is
     near our goal, tired players are reluctant - and a bonus for high Work
     Rate.  The cheapest is the presser.
  2. He only goes if he can get there in time - and WHERE pressing starts
     depends on the team's defensive style (ai/tactics.py): a low block
     waits until they're near our box, a high press goes everywhere.
     Outside the pressing zone he only steps in if he's right there.
  3. The current presser keeps the job unless someone else is clearly
     better placed, so the job doesn't flicker between two players.
  4. He runs to a point just GOAL-SIDE of the carrier (between him and our
     goal) - showing him away from goal and putting himself in the way -
     and arrives ready to tackle from the front.

Pressing styles add more:
  - SECOND PRESSER ("press", "high_press"): the next man cuts off the
    easiest pass - he stands in the passing lane to the carrier's nearest
    teammate (his "cover shadow").
  - MARK THE SHORT OPTIONS ("high_press"): other players close to the ball
    step tight onto the nearest opponents, so there's no easy way out.
  - COUNTER-PRESS ("press", "high_press"): for a few seconds after we lose
    the ball, the nearest two or three players hunt it straight back
    instead of dropping into shape.

BLOCK THE RUN (anywhere on the pitch): pressure from BEHIND doesn't stop a
man driving forward.  If he's running at us and whoever is closing him down
isn't goal-side of him (a midfielder chasing him back, say) - or nobody is -
the player in the next line he's running into steps across into his path and
slows him down from the front, standing off a few metres and showing him
away from goal, until the chaser catches up and it's two on one.
  - WHERE it starts depends on the defensive style (ai/tactics.py
    "step_from"): a high press steps out anywhere, a mid block from around
    halfway, a low block only once he's in our half - it lets him come.
  - The back line holds its line until he gets near it, and never steps out
    beyond halfway - except in the high press.
  - Stepping out costs more if it would leave a dangerous opponent free
    behind him; then someone else goes, or nobody does and the block drops.
  - Inside our last 30 m he's met whether he's running or not.
COVER: whoever steps out, the nearest teammate in the same line drops in
behind and inside him - the other centre-back behind a centre-back who
engages, the other central midfielder screening behind a midfielder - so one
dribble past him doesn't leave a free run.

His speed (core/locomotion.py) depends on his Work Rate: a hard worker
closes down flat out, a lazy one at ~80%.

All tuning numbers are in the TUNING block.
"""

from pygame.math import Vector2
from config.constants import WIDTH, HEIGHT, M_TO_PX
from core.utils import distance

# ---------------------------------------------------------------------------
# TUNING
# ---------------------------------------------------------------------------
OUTSIDE_ZONE_REACH  = 1.4    # s: outside the style's pressing zone, only press if he's this close
# (the pressing zone and reach inside it come from the style in ai/tactics.py)
CB_ENGAGE_DIST      = 28.0   # m from our goal: centre-backs only press inside this...
CB_PENALTY          = 1.2    # s: ...otherwise they count as this much further away
TIRED_STAMINA       = 0.45   # below this condition (worse of sprint energy / match stamina)...
TIRED_PENALTY       = 0.6    # s: ...he's reluctant
WORK_RATE_BONUS     = 0.03   # s cheaper per Work Rate point above 10
KEEP_MARGIN         = 0.4    # s: someone must be this much better to take over
JOCKEY_DIST         = 1.8    # m goal-side of the carrier: close enough to tackle, far enough not to be skinned
LEAD_TIME           = 0.25   # s: aim where the carrier is about to be...
LEAD_TIME_FAR       = 0.8    # s: ...or further ahead when he's still far away
PITCH_MARGIN        = 0.5    # m
LANE_SHARE          = 0.55   # second presser stands this far along the pass from carrier to receiver
MARK_RADIUS         = 20.0   # m: high press marks opponents within this of the ball...
MARK_REACH          = 15.0   # m: ...if one of ours is within this of them
MARK_MAX            = 3      # ...up to this many
MARK_GOALSIDE       = 1.5    # m goal-side of his man
COUNTER_REACH       = 2.5    # s: counter-pressers must be able to get there this fast

# Block the run / cover
# (where it starts and how tight the blocker gets come from the style: ai/tactics.py)
BLOCK_ALWAYS        = 30.0   # m from our goal: inside this he's met whether he's running or not
BLOCK_RUN_SPEED     = 2.5    # m/s towards our goal = "running at us"
GOAL_SIDE           = 1.0    # m: a presser this far goal-side of the carrier is in his way already
BLOCK_CONE          = 0.55   # blockers come from roughly in front: |side| <= this x ahead + 4 m
BLOCK_REACH         = 2.2    # s: and must be able to get to his path this fast
BLOCK_JOCKEY_BOX    = 1.8    # m: inside BLOCK_JOCKEY_BOX_D of goal everyone gets this tight
BLOCK_JOCKEY_BOX_D  = 20.0
BLOCK_KEEP_MARGIN   = 0.4    # s: the current blocker keeps the job unless someone's this much better
BACK_LINE           = ("LB", "RB", "LCB", "RCB")
MIDFIELD            = ("LCM", "RCM", "LM", "RM")
BACK_STEP_AHEAD     = 12.0   # m: the back line only steps out once he's this close to it
HALFWAY_M           = 55.0
HOLE_RADIUS         = 9.0    # m: stepping out leaves a hole if an opponent this close to him...
HOLE_COVERED        = 5.0    # m: ...isn't also near another of ours...
HOLE_PENALTY        = 0.8    # s: ...costs this much (x how dangerous that opponent is)
HOLE_DANGER_FAR     = 50.0   # m from our goal: an opponent this far out isn't dangerous
COVER_FROM          = 45.0   # m from our goal: a back-line player engaging inside this gets cover
COVER_BEHIND        = 6.0    # m: cover sits this far behind the man engaging...
COVER_BEHIND_MID    = 7.0    # m: ...(a midfielder screens a bit deeper, in front of the back line)
COVER_INSIDE        = 3.0    # m: ...and this far inside him (towards the middle of the goal)


from core.stats import stat20 as _stat    # (cached: attributes never change during a match)


def _cost(p, carrier, d_goal_m):
    import core.locomotion as locomotion
    t = distance(p.pos, carrier.pos) / M_TO_PX / max(locomotion.top_speed_ms(p), 1.0)
    if p.role in ("LCB", "RCB") and d_goal_m > CB_ENGAGE_DIST:
        t += CB_PENALTY
    import core.fatigue as fatigue
    if fatigue.condition(p) < TIRED_STAMINA:
        t += TIRED_PENALTY
    t -= WORK_RATE_BONUS * (_stat(p, "Work Rate") - 10.0)
    return t


def update(state, team, opponents, ball, now, since_change=99.0):
    """
    Called every frame for the team WITHOUT the ball, after normal defensive
    positioning (so it overrides the pressers' shape targets).
    state: dict kept per team by the decision maker.
    since_change: seconds since we lost the ball (for the counter-press).
    """
    best = _press(state, team, opponents, ball, now, since_change)
    _block_and_cover(state, team, opponents, ball, now)
    return best


def _press(state, team, opponents, ball, now, since_change):
    import ai.tactics as tactics
    state["presser"] = None
    if not team:
        return None
    st = tactics.style(team[0].team)
    sign = 1.0 if team[0].team == 0 else -1.0          # direction we attack
    own_goal = Vector2(0.0 if sign > 0 else WIDTH, HEIGHT / 2)
    candidates = [p for p in team if p.role != "GK" and getattr(p, "is_active", True)
                  and not p.has_ball and now >= getattr(p, "stagger_until", 0.0)]
    if not candidates:
        return None

    carrier = ball.owner if (ball.owner is not None and ball.owner in opponents) else None
    counter = since_change < st["counter_press"]

    # Loose ball just after we lost it: counter-pressers go for the ball itself
    if carrier is None:
        if counter and ball.owner is None and not ball.is_dead:
            _counter_press(candidates, ball.pos, st, own_goal, None, exclude=())
        return None
    if carrier.role == "GK" and st["press_from"] < 100.0:
        return None

    d_goal_m = distance(carrier.pos, own_goal) / M_TO_PX
    depth_m = abs(carrier.pos.x - own_goal.x) / M_TO_PX         # how far up the pitch (from our goal line)
    in_zone = depth_m <= st["press_from"]
    max_time = st["press_reach"] if in_zone else OUTSIDE_ZONE_REACH
    if counter:
        max_time = max(max_time, COUNTER_REACH)

    costs = {id(p): _cost(p, carrier, d_goal_m) for p in candidates}
    best = min(candidates, key=lambda p: costs[id(p)])
    current = state.get("_last_presser")
    if current is not None and current in candidates \
            and costs[id(current)] <= costs[id(best)] + KEEP_MARGIN:
        best = current
    if costs[id(best)] > max_time:
        state["_last_presser"] = None
        return None

    state["presser"] = best
    state["_last_presser"] = best
    best.target = press_point(best, carrier, own_goal)
    best.state = "press"
    best.pos_reason = "counter-press" if counter else "press the ball"
    busy = {id(best)}

    # Counter-press: the next nearest hunt the ball too
    if counter and st["counter_pressers"] > 1:
        busy |= _counter_press(candidates, carrier.pos, st, own_goal, carrier, exclude=busy)

    if not in_zone and not counter:
        return best

    # Second presser: cut off the easiest pass
    mates = [o for o in opponents if o is not carrier and getattr(o, "is_active", True)]
    if st["second_presser"] and mates:
        receiver = min(mates, key=lambda o: distance(o.pos, carrier.pos))
        lane = carrier.pos + (receiver.pos - carrier.pos) * LANE_SHARE
        free = [p for p in candidates if id(p) not in busy and p.role not in ("LCB", "RCB")]
        if free:
            cover = min(free, key=lambda p: distance(p.pos, lane))
            if distance(cover.pos, lane) / M_TO_PX < 20.0:
                cover.target = Vector2(lane)
                cover.state = "press"
                cover.pos_reason = "cut the passing lane"
                busy.add(id(cover))

    # High press: mark the short options tight
    if st["mark_short"]:
        near = sorted((o for o in mates if distance(o.pos, carrier.pos) < MARK_RADIUS * M_TO_PX),
                      key=lambda o: distance(o.pos, carrier.pos))
        marked = 0
        for o in near:
            if marked >= MARK_MAX:
                break
            free = [p for p in candidates if id(p) not in busy]
            if not free:
                break
            m = min(free, key=lambda p: distance(p.pos, o.pos))
            if distance(m.pos, o.pos) > MARK_REACH * M_TO_PX:
                continue
            to_goal = own_goal - o.pos
            spot = o.pos + (to_goal.normalize() * (MARK_GOALSIDE * M_TO_PX) if to_goal.length_squared() > 0 else Vector2())
            m.target = spot
            m.state = "press"
            m.pos_reason = f"mark tight: {o.role}"
            busy.add(id(m))
            marked += 1
    return best


def _counter_press(candidates, point, st, own_goal, carrier, exclude):
    """The nearest few (besides `exclude`) sprint at the ball. Returns the ids used."""
    used = set()
    import core.locomotion as locomotion
    want = st["counter_pressers"] - len(exclude)
    pool = sorted((p for p in candidates if id(p) not in exclude),
                  key=lambda p: distance(p.pos, point))
    for p in pool[:max(0, want)]:
        t = distance(p.pos, point) / M_TO_PX / max(locomotion.top_speed_ms(p), 1.0)
        if t > COUNTER_REACH:
            break
        p.target = press_point(p, carrier, own_goal) if carrier is not None else Vector2(point)
        p.state = "press"
        p.pos_reason = "counter-press"
        used.add(id(p))
    return used


def press_point(presser, carrier, own_goal, jockey=JOCKEY_DIST):
    """Just goal-side of where the carrier is about to be."""
    dist_m = distance(presser.pos, carrier.pos) / M_TO_PX
    lead = LEAD_TIME if dist_m < 6.0 else LEAD_TIME_FAR
    ahead = carrier.pos + carrier.vel * lead
    to_goal = own_goal - ahead
    if to_goal.length_squared() > 1e-6:
        ahead = ahead + to_goal.normalize() * (jockey * M_TO_PX)
    m = PITCH_MARGIN * M_TO_PX
    return Vector2(min(max(ahead.x, m), WIDTH - m), min(max(ahead.y, m), HEIGHT - m))


def _goal_frame(carrier, own_goal):
    """Unit vector from the carrier towards our goal, and his distance from it (m)."""
    to_goal = own_goal - carrier.pos
    d = to_goal.length()
    return (to_goal / d if d > 1e-6 else Vector2(1, 0)), d / M_TO_PX


def _ahead_side(p, carrier, dirg):
    """How far (m) p is goal-side of the carrier, and how far off his line to goal."""
    rel = p.pos - carrier.pos
    return rel.dot(dirg) / M_TO_PX, abs(rel.cross(dirg)) / M_TO_PX


def _hole_cost(p, team, opponents, carrier, own_goal):
    """Seconds added for stepping out if it leaves a dangerous opponent free behind him."""
    worst = 0.0
    for o in opponents:
        if o is carrier or o.role == "GK" or not getattr(o, "is_active", True):
            continue
        if distance(o.pos, p.pos) > HOLE_RADIUS * M_TO_PX:
            continue
        if any(q is not p and q.role != "GK" and distance(q.pos, o.pos) < HOLE_COVERED * M_TO_PX
               for q in team):
            continue                                   # someone else is on him
        d_goal = distance(o.pos, own_goal) / M_TO_PX
        danger = max(0.0, min(1.0, 1.0 - (d_goal - 15.0) / (HOLE_DANGER_FAR - 15.0)))
        worst = max(worst, danger)
    return HOLE_PENALTY * worst


def _block_and_cover(state, team, opponents, ball, now):
    import core.locomotion as locomotion
    import ai.tactics as tactics
    carrier = ball.owner if (ball.owner is not None and ball.owner in opponents) else None
    if carrier is None or carrier.role == "GK" or ball.is_dead:
        state["_blocker"] = None
        return
    st = tactics.style(team[0].team)
    sign = 1.0 if team[0].team == 0 else -1.0
    own_goal = Vector2(0.0 if sign > 0 else WIDTH, HEIGHT / 2)
    dirg, d_goal = _goal_frame(carrier, own_goal)
    depth = abs(carrier.pos.x - own_goal.x) / M_TO_PX          # m up the pitch from our goal line
    run_speed = carrier.vel.dot(dirg) / M_TO_PX
    presser = state.get("presser")
    engaging = presser
    blocker = None

    # --- Block the run ---
    threatening = d_goal <= BLOCK_ALWAYS or (depth <= st["step_from"] and run_speed >= BLOCK_RUN_SPEED)
    in_way = presser is not None and _ahead_side(presser, carrier, dirg)[0] >= GOAL_SIDE
    if threatening and not in_way:
        jockey = BLOCK_JOCKEY_BOX if d_goal <= BLOCK_JOCKEY_BOX_D else st["block_jockey"]
        # Where's our back line?  It holds until he's close to it
        backs = [p for p in team if p.role in BACK_LINE and getattr(p, "is_active", True)]
        back_depth = (sum(abs(p.pos.x - own_goal.x) for p in backs) / len(backs) / M_TO_PX) if backs else 0.0
        backs_may_step = depth <= back_depth + BACK_STEP_AHEAD and \
            (depth <= HALFWAY_M or st["cb_beyond_half"])
        cands = []
        for p in team:
            if p.role == "GK" or p is presser or p.has_ball or not getattr(p, "is_active", True) \
                    or now < getattr(p, "stagger_until", 0.0) or p.state == "press":
                continue                               # (state "press" = already given a job this frame)
            if p.role in BACK_LINE and not backs_may_step:
                continue
            ahead, side = _ahead_side(p, carrier, dirg)
            if ahead < GOAL_SIDE or side > BLOCK_CONE * ahead + 4.0:
                continue
            spot = press_point(p, carrier, own_goal, jockey)
            t = distance(p.pos, spot) / M_TO_PX / max(locomotion.top_speed_ms(p), 1.0)
            if t > BLOCK_REACH:
                continue
            cands.append((t + _hole_cost(p, team, opponents, carrier, own_goal), p, spot))
        if cands:
            cost, blocker, spot = min(cands, key=lambda c: c[0])
            cur = state.get("_blocker")
            for c in cands:
                if c[1] is cur and c[0] <= cost + BLOCK_KEEP_MARGIN:
                    cost, blocker, spot = c
            blocker.target = spot
            blocker.state = "press"
            blocker.pos_reason = "block the run" if blocker.role in BACK_LINE else "get in his way"
            engaging = blocker
    state["_blocker"] = blocker

    # --- Cover the man who steps out ---
    if engaging is None:
        return
    if engaging.role in BACK_LINE:
        if d_goal > COVER_FROM:
            return
        line, behind = BACK_LINE, COVER_BEHIND
    elif engaging is blocker and engaging.role in MIDFIELD:
        line, behind = MIDFIELD, COVER_BEHIND_MID
    else:
        return
    eng_to_goal = own_goal - engaging.target
    if eng_to_goal.length_squared() < 1e-6:
        return
    spot = engaging.target + eng_to_goal.normalize() * (behind * M_TO_PX)
    # ...and inside him, towards the middle of the goal
    lateral = HEIGHT / 2 - spot.y
    spot.y += max(-COVER_INSIDE * M_TO_PX, min(COVER_INSIDE * M_TO_PX, lateral))
    pool = [p for p in team if p.role in line and p is not engaging and p is not presser
            and p.state != "press" and getattr(p, "is_active", True) and not p.has_ball]
    if not pool:
        return
    cover = min(pool, key=lambda p: distance(p.pos, spot))
    cover.target = spot
    cover.state = "press"
    cover.pos_reason = "cover: " + engaging.role
