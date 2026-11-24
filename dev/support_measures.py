"""Showing for the ball: the same measures for real tracking data and for our match engine (23 Nov).

One "moment" = a team-mate has the ball in open play.  For his outfield team-mates we measure:
  nearest      how far away the nearest team-mate is (m)
  within15     how many team-mates are within 15 m of him
  open         how many team-mates he could pass to: 5-40 m away, and no opponent within LANE_M of the
               straight line between them (leaving out the first 3 m by the passer - his marker's there)
  open_fwd     ...of those, how many are ahead of him (towards the goal he's attacking), more than 3 m
  open_short   ...how many are within 15 m
  none_open    1 if nobody is open;  few_open: 1 if one at most;  no_fwd: 1 if nobody ahead of him is open
  move         how fast his team-mates within 30 m are moving (m/s) - standing about or getting free
  marked       how many team-mates within 30 m have an opponent within 2 m of them
Each moment also has a zone: the third of the pitch the ball's in (own / middle / final), from his side.
"""
import math

LANE_M = 2.0
SHORT_M = 15.0


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        return math.hypot(px - ax, py - ay), 0.0
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)), t * math.sqrt(L2)


def moment(carrier, direction, mates, opps, length):
    """carrier (x, y) m; direction +1 / -1 (the way he's attacking along x); mates [(x, y, vx, vy)] outfield
    team-mates; opps [(x, y)] opponents (keeper included); length of the pitch (m).  Returns a dict."""
    cx, cy = carrier
    ds = [math.hypot(x - cx, y - cy) for x, y, _, _ in mates]
    out = dict(nearest=min(ds) if ds else 99.0, within15=sum(1 for d in ds if d < 15.0))
    open_n = fwd = short = 0
    for (x, y, _, _), d in zip(mates, ds):
        if not (5.0 <= d <= 40.0):
            continue
        blocked = False
        for ox, oy in opps:
            dd, along = _seg_dist(ox, oy, cx, cy, x, y)
            if dd < LANE_M and along > 3.0:
                blocked = True
                break
        if blocked:
            continue
        open_n += 1
        if (x - cx) * direction > 3.0:
            fwd += 1
        if d <= SHORT_M:
            short += 1
    out.update(open=open_n, open_fwd=fwd, open_short=short, none_open=1 if open_n == 0 else 0,
               few_open=1 if open_n <= 1 else 0, no_fwd=1 if fwd == 0 else 0)
    near = [(x, y, vx, vy) for (x, y, vx, vy), d in zip(mates, ds) if d < 30.0]
    out["move"] = (sum(math.hypot(vx, vy) for _, _, vx, vy in near) / len(near)) if near else 0.0
    out["marked"] = sum(1 for x, y, _, _ in near if any(math.hypot(ox - x, oy - y) < 2.0 for ox, oy in opps))
    # the zone, from his side: 0 own third, 1 middle, 2 final third
    depth = cx if direction > 0 else length - cx
    out["zone"] = min(2, int(3 * depth / length))
    return out


KEYS = ("nearest", "within15", "open", "open_fwd", "open_short", "none_open", "few_open", "no_fwd", "move", "marked")


def summarise(moments):
    """{zone: {key: mean}} plus "all"."""
    res = {}
    for z, name in ((None, "all"), (0, "own third"), (1, "middle third"), (2, "final third")):
        ms = [m for m in moments if z is None or m["zone"] == z]
        if not ms:
            continue
        res[name] = {k: sum(m[k] for m in ms) / len(ms) for k in KEYS}
        res[name]["n"] = len(ms)
    return res
