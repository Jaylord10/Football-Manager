"""
gameplay/substitutions.py
=========================
Substitutions, Premier League rules:

  - 9 named substitutes (the career's bench - whoever isn't starting)
  - up to 5 substitutions, made in at most 3 "windows" during play; changes
    at half-time don't use up a window
  - a substitution is only made when the ball is dead (throw-in, goal kick,
    free kick, corner, after a goal) - never with the ball in play
  - a man who's been taken off can't come back on

How a substitution happens on the pitch: the restart is held up while the
change is made (SUB_HOLD), the player going off disappears and his
replacement comes on at the halfway line on the bench side, fresh, and runs
to his position.  He takes the same place in the team (LB for LB...) and
plays that position's role unless the manager picks another.  A man playing
out of position has the usual penalty (career/clubs.py FIT_DROP) - worked out
by the career before the match and sent with the bench.

Who makes the changes:
  - AI managers (and your assistant, when you simulate or tick "assistant
    handles subs") - see AIPlanner below
  - you, when you watch: the S key in the match window (rendering/sub_panel.py)
    queues a change; it's made at the next stoppage.

The match also keeps everyone's minutes (on / off) and cards for the career
(appearances now; bans and injuries later).
"""

import random
from pygame.math import Vector2
from config.constants import WIDTH, HEIGHT, M_TO_PX

MAX_SUBS = 5
MAX_WINDOWS = 3
FRIENDLY_SUBS = 11         # a friendly (career/friendlies.py): change the whole team if you like...
FRIENDLY_HT_CHANGES = 7    # ...and the AI / your assistant give this many a run-out at half-time
SUB_HOLD = 25.0            # s the restart is held up by a change (one or more men)
SUB_HOLD_EXTRA = 5.0       # ...plus this per extra man in the same window
ENTRY = (0.0, 0.5)         # m: he comes on at halfway, just inside the bench-side touchline

# --- AI managers --------------------------------------------------------------
# Premier League 2024-25: teams made ~4 changes a game on average, the first
# usually just before or after the hour, most of the rest between 70 and 85.
FIRST_WINDOW = (56, 68)    # minute of the first planned change (earlier if losing)
SECOND_GAP = (8, 15)       # minutes after the first
LATE_WINDOW = (78, 87)
LOSING_EARLIER = 6         # losing: every planned change this many minutes sooner
HT_SUB_LOSING_BY_2 = 0.5   # chance of a half-time change when 2+ down
HT_SUB_BOOKED = 0.25       # ...of taking off a booked defender / midfielder at half-time
BOOKED_TIRED = 0.04        # a booked defender / midfielder counts as this much more tired
RATING_MARGIN = 12         # won't bring on a man more than this much worse (0-100) for the slot
TIME_WASTE = 0.6           # winning in the last minutes with a change left: chance to make it

# --- Injuries during the match (career matches) ------------------------------
# UEFA Elite Club Injury Study (Ekstrand et al.): 29 injuries per 1000 match
# hours - about 0.48 per team per match.  How long they're out is decided by
# the career afterwards (career/availability.py); here we decide who and when,
# and whether he can carry on.
INJURY_PER_MIN = 0.0005     # chance per player per match minute (x the factors below)
INJURY_TIRED = 3.0          # x (1 + this x how far his stamina is below 0.85)
INJURY_AGE = {30: 1.15, 33: 1.3}   # from this age on, x this
CONTACT_INJURY = 0.03       # the player fouled: chance he's hurt
KNOCK_SHARE = 0.30          # a knock: he carries on (still misses a day or two afterwards)
LIMP = 0.70                 # an injured man waiting to come off: pace / acceleration / agility x this

POS_GROUP = {"GK": "GK", "LB": "DF", "RB": "DF", "LCB": "DF", "RCB": "DF",
             "LCM": "MF", "RCM": "MF", "LM": "AT", "RM": "AT", "ST1": "AT", "ST2": "AT"}


class Substitutions:
    def __init__(self, engine, db):
        self.engine = engine
        self.bench = {t: [dict(b) for b in db.bench.get(t, [])] for t in (0, 1)}
        self.ratings = {t: dict(db.lineup_ratings.get(t, {})) for t in (0, 1)}
        self.auto = {t: db.auto_subs.get(t, True) for t in (0, 1)}
        self.friendly = bool(getattr(db, "friendly", False))
        self.max_subs = FRIENDLY_SUBS if self.friendly else MAX_SUBS
        self.max_windows = 99 if self.friendly else MAX_WINDOWS
        self.used = {0: 0, 1: 0}
        self.windows = {0: 0, 1: 0}
        self.queue = {0: [], 1: []}          # [(player object in the slot, bench id, role_style or None)]
        self.log = []                        # [{team, minute, off_id, off_name, on_id, on_name, slot}]
        self.shape_done = {}                 # AI managers' late changes of shape (gameplay/formation_change.py)
        self.shape_log = []                  # [{team, minute, formation}]
        self.apps = {}                       # (team, pid) -> {team, name, on, off, yellow, red, start}
        self._stoppage = None                # which stoppage we're in (so it's one window per team)
        self._window_this_stop = {0: False, 1: False}
        # (No bench - a friendly or a test match: nothing to do, and no random
        # numbers drawn, so those matches play exactly as before)
        self.active = any(self.bench[t] for t in (0, 1))
        self.ai = {t: AIPlanner(t) for t in (0, 1)} if self.active else {}
        self.messages = {}                   # team -> {"text", "team", "until"}: the board in the match window
        self.ages = {}                       # (team, pid) -> age (injury risk)
        for t in (0, 1):
            for slot, pid in db.lineup_ids.get(t, {}).items():
                self.ages[(t, pid)] = db.lineup_ages.get(t, {}).get(slot, 26)
            for b in self.bench[t]:
                self.ages[(t, b["id"])] = b.get("age", 26)
        self._injury_clock = 0.0
        self.ask = None                      # your injured player, waiting for you to pick his replacement
        for team in (engine.team0, engine.team1):
            for p in team:
                if getattr(p, "pid", None) is not None:
                    self.apps[(p.team, p.pid)] = {"team": p.team, "name": p.name, "on": 0, "off": None,
                                                  "yellow": 0, "red": False, "start": True, "injury": None}

    # ------------------------------------------------------------------
    def team(self, tid):
        return self.engine.team0 if tid == 0 else self.engine.team1

    def left(self, tid):
        return self.max_subs - self.used[tid] - len(self.queue[tid])

    def can_sub_now(self, tid):
        """Room for another change?  (subs left, and a window left unless this
        stoppage already is one of ours)"""
        if self.used[tid] >= self.max_subs:
            return False
        return self.windows[tid] < self.max_windows or self._window_this_stop[tid]

    def available(self, tid):
        """Bench players who can still come on."""
        queued = {b for _, b, _ in self.queue[tid]}
        return [b for b in self.bench[tid] if not b.get("used") and b["id"] not in queued]

    def request(self, tid, player, bench_id, role_style=None):
        """Queue a change (made at the next stoppage).  Returns an error string or None."""
        if self.used[tid] + len(self.queue[tid]) >= self.max_subs:
            return "No substitutions left"
        if self.windows[tid] >= self.max_windows and not self._window_this_stop[tid] \
                and self.engine.match_state != "halftime":
            return "No substitution windows left (you can still change at half-time)"
        if not getattr(player, "is_active", True):
            return "He's been sent off"
        if any(q[0] is player for q in self.queue[tid]):
            return "He's already coming off"
        if bench_id not in {b["id"] for b in self.available(tid)}:
            return "He can't come on"
        self.queue[tid].append((player, bench_id, role_style))
        return None

    def cancel(self, tid, player):
        self.queue[tid] = [q for q in self.queue[tid] if q[0] is not player]

    # ------------------------------------------------------------------
    def update(self, now, minute):
        """Every frame: at a stoppage, let AI managers decide and make queued changes."""
        if not self.active:
            return
        ball = self.engine.ball
        if not (ball.is_dead and ball.restart_taker is not None):
            return
        key = (ball.restart_type, ball.restart_time)
        if key != self._stoppage:
            self._stoppage = key
            self._window_this_stop = {0: False, 1: False}
            for tid in (0, 1):
                if self.auto[tid] and minute >= 30:
                    for player, bench_id in self.ai[tid].decide(self, minute):
                        self.request(tid, player, bench_id)
                if tid != self.engine.my_team:            # AI managers: chase a game / protect a lead
                    from gameplay import formation_change
                    form = formation_change.ai_manage(self.engine, tid, minute, self.shape_done.setdefault(tid, set()))
                    if form:
                        self.log_shape(tid, minute, form)
        for tid in (0, 1):
            if self.queue[tid]:
                self._make(tid, now, minute, half_time=False)

    def log_shape(self, tid, minute, form):
        self.shape_log.append({"team": tid, "minute": minute, "formation": form})
        try:
            self.engine.show_notice(f"{minute}' {self.engine._team_name(tid)} change to {form}")
        except Exception:
            pass

    def half_time(self, now, minute=46):
        """Changes at half-time (and at the breaks in extra time): AI managers decide, then everything
        queued is made (no window used)."""
        if not self.active:
            return
        for tid in (0, 1):
            if self.auto[tid]:
                for player, bench_id in self.ai[tid].decide_half_time(self):
                    self.request(tid, player, bench_id)
                if self.friendly:
                    self._friendly_changes(tid)
            if self.queue[tid]:
                self._make(tid, now, minute, half_time=True)

    def _friendly_changes(self, tid):
        """A friendly at half-time: give the bench a run-out, like for like."""
        queued = {id(q[0]) for q in self.queue[tid]}
        on = [p for p in self.team(tid) if getattr(p, "is_active", True) and id(p) not in queued]
        for b in list(self.available(tid)):
            if len(self.queue[tid]) >= FRIENDLY_HT_CHANGES:
                break
            gk = b.get("pos") == "GK"
            cands = [p for p in on if (p.slot == "GK") == gk]
            if not cands:
                continue
            p = max(cands, key=lambda q: b.get("rating", {}).get(q.slot, 0) - b.get("drop", {}).get(q.slot, 0))
            if self.request(tid, p, b["id"]) is None:
                on.remove(p)

    def _make(self, tid, now, minute, half_time):
        ball = self.engine.ball
        done = []
        keep = []
        for item in self.queue[tid]:
            player, bench_id, role_style = item
            if not half_time and (player is ball.restart_taker or player is ball.owner):
                keep.append(item)              # not while he's taking the restart
                continue
            if (not half_time and not self.can_sub_now(tid)) or self.used[tid] >= self.max_subs:
                keep.append(item)
                continue
            b = next((x for x in self.bench[tid] if x["id"] == bench_id and not x.get("used")), None)
            if b is None or not getattr(player, "is_active", True):
                continue
            self._swap(tid, player, b, role_style, minute)
            self.used[tid] += 1
            if not half_time and not self._window_this_stop[tid]:
                self._window_this_stop[tid] = True
                self.windows[tid] += 1
            done.append(f"{player.__dict__.get('_off_name', '?')}  >>  {b['name']}")
        self.queue[tid] = keep
        if done:
            e = self.engine
            self.messages[tid] = {"text": "SUB   " + "     |     ".join(done), "team": tid,
                                  "until": e.time_elapsed + 5.0 * getattr(e, "match_speed", 1)}
        if done and not half_time:
            hold = now + SUB_HOLD + SUB_HOLD_EXTRA * (len(done) - 1)
            ball.sub_hold_until = max(getattr(ball, "sub_hold_until", 0.0), hold)

    def _swap(self, tid, player, b, role_style, minute):
        """The player in this slot goes off; b comes on in his place (same object,
        so everything that refers to 'the left back' still does - but a fresh man)."""
        from core.game_objects import Player
        from core.database import row_to_attributes
        from config import slots as slots_mod
        slot = player.slot
        old_id, old_name = getattr(player, "pid", None), player.name
        rec = self.apps.get((tid, old_id))
        if rec is not None:
            rec["off"] = minute
            rec["yellow"] = player.yellow_cards
            rec["red"] = player.red_card
            rec["stamina"] = round(getattr(player, "stamina", 1.0), 3)
        row = dict(b["row"])
        drop = b.get("drop", {}).get(slot, 0)
        for k in list(row):
            if k in ("Name", "Role", "Id", "Pos", "Age"):
                continue
            v = row[k]
            if k in ("Shot Stopping", "Handling"):
                if slot != "GK":
                    row[k] = 5
            elif drop and k not in PHYSICAL:
                row[k] = int(max(15, min(97, round(v - drop))))      # (career/clubs.py _clamp)
        row["Role"] = slot
        row["Name"] = b["name"]
        x = WIDTH / 2 + ENTRY[0] * M_TO_PX
        y = HEIGHT - ENTRY[1] * M_TO_PX
        fresh = Player(team=tid, role=slots_mod.proxy(slot), pos=Vector2(x, y), idx=player.idx,
                       attributes=row_to_attributes(row))
        fresh.slot = slot
        fresh.name = b["name"]
        fresh.pid = b["id"]
        fresh.stamina = float(b.get("condition", 1.0))      # his fitness coming on
        style = role_style or getattr(player, "role_style", None)
        if style is not None:
            fresh.role_style = style
        fresh.state = "run"
        fresh.target = Vector2(x, y - 6 * M_TO_PX)
        player.__dict__.clear()
        player.__dict__.update(fresh.__dict__)
        player._off_name = old_name                 # (for the board shown in the match window)
        b["used"] = True
        self.ratings[tid][slot] = b.get("rating", {}).get(slot, self.ratings[tid].get(slot))
        self.apps[(tid, b["id"])] = {"team": tid, "name": b["name"], "on": minute, "off": None,
                                     "yellow": 0, "red": False, "start": False, "injury": None}
        self.log.append({"team": tid, "minute": minute, "slot": slot,
                         "off_id": old_id, "off_name": old_name, "on_id": b["id"], "on_name": b["name"]})

    # ------------------------------------------------------------------
    # Injuries
    # ------------------------------------------------------------------
    def injuries(self, dt, minute):
        """Every frame while the ball's in play (career matches): once a second,
        does anyone pick up an injury?"""
        if not self.active:
            return
        self._injury_clock += dt
        if self._injury_clock < 1.0:
            return
        secs, self._injury_clock = self._injury_clock, 0.0
        import gameplay.match_engine as me
        match_minutes = secs * 45.0 / max(1.0, me.HALF_DURATION_REAL)
        for team in (self.engine.team0, self.engine.team1):
            for p in team:
                if not getattr(p, "is_active", True) or p.__dict__.get("_injury"):
                    continue
                risk = INJURY_PER_MIN * match_minutes
                risk *= 1.0 + INJURY_TIRED * max(0.0, 0.85 - getattr(p, "stamina", 1.0))
                age = self.ages.get((p.team, getattr(p, "pid", None)), 26)
                risk *= max([f for a, f in INJURY_AGE.items() if age >= a], default=1.0)
                if random.random() < risk:
                    self._injure(p, minute, "match")

    def fouled(self, player, minute):
        if self.active and player is not None and not player.__dict__.get("_injury") \
                and random.random() < CONTACT_INJURY:
            self._injure(player, minute, "foul")

    def _injure(self, player, minute, cause):
        knock = random.random() < KNOCK_SHARE
        player._injury = {"minute": minute, "knock": knock, "cause": cause}
        rec = self.apps.get((player.team, getattr(player, "pid", None)))
        if rec is not None:
            rec["injury"] = dict(player._injury)
        e = self.engine
        tid = player.team
        if knock:
            text = f"KNOCK   {player.name} is hurt but carries on"
        else:
            # Limping until he can come off
            a = dict(player.attributes)
            for k in ("Top Speed", "Acceleration", "Agility"):
                if isinstance(a.get(k), (int, float)):
                    a[k] = max(1, a[k] * LIMP)
            player.attributes = a
            player.__dict__.pop("_ts_cache", None)
            if tid == getattr(e, "my_team", None) and not self.auto[tid]:
                # Your team, assistant off: the match stops and you choose (match_engine opens the panel)
                self.ask = player
                self.messages[f"inj{tid}"] = {"text": f"INJURY   {player.name} has to come off", "team": tid,
                                              "kind": "injury",
                                              "until": e.time_elapsed + 5.0 * getattr(e, "match_speed", 1)}
                return
            bench_id = self._injury_replacement(tid, player)
            err = "no replacement" if bench_id is None else None
            if bench_id is not None:
                self.cancel(tid, player)
                err = self.request(tid, player, bench_id)
                if err is None:                       # first in the queue
                    q = self.queue[tid]
                    q.insert(0, q.pop())
            text = f"INJURY   {player.name} has to come off" if err is None else \
                f"INJURY   {player.name} - no changes left, he limps on"
        self.messages[f"inj{tid}"] = {"text": text, "team": tid, "kind": "injury",
                                      "until": e.time_elapsed + 5.0 * getattr(e, "match_speed", 1)}

    def _injury_replacement(self, tid, player):
        """Like for like if possible, otherwise the best man for the position (a keeper for a keeper)."""
        slot = player.slot
        best = None
        for b in self.available(tid):
            if (b.get("pos") == "GK") != (slot == "GK"):
                continue
            r = b.get("rating", {}).get(slot, 0) - b.get("drop", {}).get(slot, 0)
            if best is None or r > best[0]:
                best = (r, b["id"])
        return best[1] if best else None

    def sent_off(self, player, minute, kind="red"):
        """A red card: his match ends there.  kind: "red" (straight) or "second_yellow"."""
        rec = self.apps.get((player.team, getattr(player, "pid", None)))
        if rec is not None and rec["off"] is None:
            rec["off"] = minute
            rec["yellow"] = player.yellow_cards
            rec["red"] = kind
            rec["stamina"] = round(getattr(player, "stamina", 1.0), 3)

    # ------------------------------------------------------------------
    def finish(self):
        """At full time: everyone's minutes and cards."""
        for team in (self.engine.team0, self.engine.team1):
            for p in team:
                rec = self.apps.get((p.team, getattr(p, "pid", None)))
                if rec is not None and rec["off"] is None:
                    rec["yellow"] = p.yellow_cards
                    rec["red"] = p.red_card
                    rec["stamina"] = round(getattr(p, "stamina", 1.0), 3)
        out = []
        for (_, pid), r in self.apps.items():
            on, off = r["on"], (r["off"] if r["off"] is not None else getattr(self.engine, "final_minute", 90))
            out.append(dict(r, id=pid, minutes=max(0, off - on)))
        return out


PHYSICAL = {"Acceleration", "Top Speed", "Agility", "Jumping", "Stamina", "Strength"}


class AIPlanner:
    """When and whom an AI manager changes."""

    def __init__(self, tid):
        self.tid = tid
        first = random.uniform(*FIRST_WINDOW)
        self.plan = [first, first + random.uniform(*SECOND_GAP), random.uniform(*LATE_WINDOW)]
        self.plan.sort()
        self.size = [random.choice((1, 1, 2)), random.choice((1, 2)), 2]   # men per window
        self.wasted = False

    def _score(self, subs):
        e = subs.engine
        return e.score[self.tid] - e.score[1 - self.tid]

    def _candidates(self, subs, attacking_first):
        team = subs.team(self.tid)
        coming_off = {id(q[0]) for q in subs.queue[self.tid]}
        out = []
        for p in team:
            if p.role == "GK" or not getattr(p, "is_active", True) or id(p) in coming_off:
                continue
            tired = 1.0 - getattr(p, "stamina", 1.0)
            if p.yellow_cards and POS_GROUP.get(p.role) in ("DF", "MF"):
                tired += BOOKED_TIRED
            if attacking_first and POS_GROUP.get(p.role) == "AT":
                tired += 0.05
            out.append((tired, p))
        out.sort(key=lambda t: -t[0])
        return [p for _, p in out]

    def _replacement(self, subs, player, used_ids):
        slot = player.slot
        cur = subs.ratings[self.tid].get(slot, 0) or 0
        best = None
        for b in subs.available(self.tid):
            if b["id"] in used_ids or b.get("pos") == "GK":
                continue
            r = b.get("rating", {}).get(slot, 0)
            if b.get("drop", {}).get(slot, 0) > 4:          # natural or "can play there" only
                continue
            if r < cur - RATING_MARGIN:
                continue
            if best is None or r > best[0]:
                best = (r, b)
        return best[1] if best else None

    def _pick(self, subs, n, attacking_first):
        picks, used = [], set()
        for p in self._candidates(subs, attacking_first):
            if len(picks) >= n or len(picks) >= subs.left(self.tid):
                break
            b = self._replacement(subs, p, used)
            if b is not None:
                picks.append((p, b["id"]))
                used.add(b["id"])
        return picks

    def decide(self, subs, minute):
        if not subs.can_sub_now(self.tid) or subs.left(self.tid) <= 0 or not self.plan:
            return []
        diff = self._score(subs)
        due = self.plan[0] - (LOSING_EARLIER if diff < 0 else 0)
        if minute >= 85 and diff > 0 and not self.wasted:
            self.wasted = True                               # (one roll a match)
            if random.random() < TIME_WASTE:
                due = 0                                      # run the clock down
        if minute < due:
            return []
        self.plan.pop(0)
        n = self.size.pop(0) if self.size else 1
        if not self.plan:                                    # last window: use what's left
            n = max(n, subs.left(self.tid))
        return self._pick(subs, n, attacking_first=diff < 0)

    def decide_half_time(self, subs):
        diff = self._score(subs)
        if diff <= -2 and random.random() < HT_SUB_LOSING_BY_2:
            return self._pick(subs, 1, attacking_first=True)
        team = subs.team(self.tid)
        booked = [p for p in team if p.yellow_cards and getattr(p, "is_active", True)
                  and POS_GROUP.get(p.role) in ("DF", "MF")]
        if booked and random.random() < HT_SUB_BOOKED:
            b = self._replacement(subs, booked[0], set())
            if b is not None:
                return [(booked[0], b["id"])]
        return []
