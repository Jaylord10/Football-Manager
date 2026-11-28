"""
gameplay/commentary.py
======================
(28 Nov, Jay: "a basic commentary for the match" - with his ElevenLabs voices)

A commentator and a co-commentator, from a phrase bank made once (data/commentary/lines.json; the sound files in
data/commentary/audio/<voice>/<id>.mp3 are made by dev/make_commentary.py on Jay's PC, with his ElevenLabs key).

  - It WATCHES the match, like gameplay/match_stats.py: shots, saves, goals, corners, crosses, balls in behind,
    tackles, fouls, cards, penalties, offsides, substitutions, kick-offs, half-time and full-time.  It never changes
    anything (its own random numbers, not the match's), so the football is exactly the same with it on or off.
  - In the build-up the commentator just says names as the ball moves ("Cole... Hargreaves..."), like real
    commentators; for each moment, a line for it (a different one each time).  The co-commentator chips in after
    the big moments (goals, big saves and misses, a red card, half-time, full-time).
  - The big moments jump the queue and cut off the chatter; old news is dropped (no "shoots!" three seconds late).
    At fast match speeds only the big moments are called.
  - It's in time with the picture: with the 3D view on (half a second behind the match) it waits for the moment
    to be on screen (MatchEngine._shown_t).
  - A line with no sound file yet is skipped (the transcript still has it: dev/commentary_transcript.py).

MatchEngine: update(engine, dt) every step; tick(engine) every drawn frame (plays the sound); K turns it on / off.
"""
import json
import os
import random
import re
import time

from config.constants import M_TO_PX, WIDTH, HEIGHT

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LINES = os.path.join(ROOT, "data", "commentary", "lines.json")
AUDIO = os.path.join(ROOT, "data", "commentary", "audio")

# Priority (0-10) of each kind of call: a higher one cuts off a lower one that's talking (GOAL cuts off a name)
PRI = {"name": 1, "goal_kick": 1, "tackle": 2, "late": 2, "stoppage": 3, "cross": 3, "corner_in": 3, "offside": 3,
       "through": 4, "corner": 4, "foul": 4, "fk_danger": 4, "sub": 3, "kickoff_restart": 2, "shot": 6,
       "outcome": 6, "save": 6, "yellow": 7, "red": 8, "penalty": 8, "goal": 10, "whistle": 9, "co": 5}
CUT_FROM = 7               # a call this important cuts off anything less important that's being said
STALE = ((8, 8.0), (5, 2.5), (0, 1.3))   # (priority from, s): a call older than this (on the picture) is dropped
SPEED_MIN_PRI = ((5, 9), (3, 7), (0, 0))  # (match speed above, only calls this important): fast-forward = big moments
GAP = 0.08                 # s between the parts of one call ("Hayes" ... "Shoots!")
CO_AFTER = 1.2             # s of quiet after the commentator before the co-commentator speaks...
CO_STALE = 12.0            # ...as long as it's within this long of the moment
THROUGH = (0.5, 15.0)      # "played through!": half the balls in behind (ending in their third) of 15 m+
NAME_EVERY = 1.1           # s: at most one name this often in the build-up...
NAME_CHANCE = 0.6          # ...and not every pass
FAR_M = 22.0               # m from goal: a shot from further out is "from distance"
CLOSE_M = 1.8              # m outside the post (or over the bar): "so close!"
BIG_SAVE = (12.0, 24.0)    # a save from a shot inside 12 m, or hit harder than 24 m/s: "what a save!"
BIG_CHANCE_M = 12.0        # a miss from inside 12 m with nobody close: the co-commentator has a word
CO_CHANCE = {"co_goal": 1.0, "co_own_goal": 1.0, "co_save": 0.6, "co_miss": 0.7, "co_red": 1.0, "co_ht": 1.0,
             "co_ft": 1.0}
SCORE_WORDS = ["nil", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def score_text(a, b):
    """'two-one', 'one-all', 'nil-nil' (the bigger first)."""
    a, b = max(a, b), min(a, b)
    if a > 9:
        return f"{a}-{b}"
    if a == b:
        return "nil-nil" if a == 0 else f"{SCORE_WORDS[a]}-all"
    return f"{SCORE_WORDS[a]}-{SCORE_WORDS[b]}"


def name_parts(players):
    """{player: (clip id, what's said)} for a team: the surname - or the full name where two of them share it."""
    from collections import Counter
    sur = Counter(_surname(p) for p in players)
    out = {}
    for p in players:
        full = str(getattr(p, "name", "") or "").strip()
        s = _surname(p)
        if not full or full in (getattr(p, "role", None), getattr(p, "slot", None)) or (full.isupper() and len(full) <= 4):
            continue                                    # (no real name - "ST", "LCB": nothing to say)
        out[p] = ("fname_" + slug(full), full) if sur[s] > 1 else ("name_" + slug(s), s)
    return out


def _surname(p):
    full = str(getattr(p, "name", "") or "").strip()
    return full.split()[-1] if full else ""


class Commentary:
    def __init__(self, engine, audio=True, seed=None):
        self.rng = random.Random(seed)          # (its own: the match's random numbers are never touched)
        self.bank = json.load(open(LINES))["moments"]
        self.last_pick = {}
        self.on = True
        self.log = []                           # [(game time, minute, voice, text)] - everything said
        self.queue = []                         # calls waiting: {"t", "pri", "parts": [(voice, clip, text)]}
        self.audio = audio and self._mixer()
        self.sounds = {}
        self.cur = None                         # the call being said: {"pri", "parts", "i", "voice", "until"}
        self.quiet_since = 0.0
        self.last_name = -99.0
        self.names = {}
        self.clubs = {}
        self._seen = {"shot": None, "save": None, "cross": None, "kick": None, "card": None, "foul": None,
                      "restart": None, "subs": 0, "state": None, "score": [0, 0], "late": False, "stoppage": False}
        self._shot = None                       # the last shot, till we know how it went
        self._last_live = None
        self._owner = None
        self._setup(engine)

    # ------------------------------------------------------------------------------------------------------
    def _mixer(self):
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100)
            pygame.mixer.set_num_channels(max(8, pygame.mixer.get_num_channels()))
            self.chan = {"comm": pygame.mixer.Channel(6), "co": pygame.mixer.Channel(7)}
            return True
        except Exception:
            return False

    def _setup(self, e):
        for team in (e.team0, e.team1):
            self.names.update(name_parts(team))
        for t in (0, 1):
            nm = e._team_name(t)
            short = _short(nm)
            self.clubs[t] = ("club_" + slug(short), short)

    def _name(self, p):
        if p not in self.names and getattr(p, "name", None):        # (on from the bench)
            team = [q for q in self.names if getattr(q, "team", None) == p.team] + [p]
            self.names.update(name_parts(team))
        n = self.names.get(p)
        return [("comm", n[0], n[1])] if n else []

    def _line(self, moment):
        m = self.bank.get(moment)
        if not m or not m["lines"]:
            return []
        ls = m["lines"]
        i = self.rng.randrange(len(ls))
        if len(ls) > 1 and i == self.last_pick.get(moment):
            i = (i + 1 + self.rng.randrange(len(ls) - 1)) % len(ls)
        self.last_pick[moment] = i
        return [(m["voice"], ls[i]["id"], ls[i]["text"])]

    def _say(self, e, pri, parts, t=None):
        if parts:
            m = 90 if e.match_state == "full_time" else e.match_minute()
            self.queue.append({"t": e.time_elapsed if t is None else t, "pri": pri, "parts": parts, "min": m})

    # ------------------------------------------------------------------------------------------------------
    def update(self, e, dt):
        """Every step of the match: what's happened that's worth a word?"""
        if not self.on:
            return
        b = e.ball
        S = self._seen
        st = e.match_state
        if not b.is_dead:
            self._last_live = (b.pos.y, getattr(b, "z", 0.0))       # (where it was as it went out)

        # The whistles
        if st != S["state"]:
            prev, S["state"] = S["state"], st
            if st == "first_half" and e.half_elapsed < 2.0:
                S["ko"] = "kickoff_match"                       # (said as the kick-off's taken)
            elif st == "second_half":
                S["ko"] = "kickoff_second"
            elif st in ("halftime", "full_time"):
                self._whistle(e, st)
        if S.get("ko") and not b.is_dead and st in ("first_half", "second_half"):
            self._say(e, PRI["whistle"], self._line(S["ko"]))
            S["ko"] = None
        live = st in ("first_half", "second_half", "et_first", "et_second")

        # Goals
        if list(e.score) != S["score"]:
            team = 0 if e.score[0] > S["score"][0] else 1
            S["score"] = list(e.score)
            self._goal(e, team)
            self._shot = None
        if not live:
            return

        # Shots
        si = getattr(b, "shot_info", None)
        if si and si.get("shooter") is not None and si.get("time") != S["shot"]:
            S["shot"] = si["time"]
            self._new_shot(e, si)
        self._shot_outcome(e)

        # Saves
        sv = getattr(b, "last_save", None)
        if sv and sv.get("time") != S["save"]:
            S["save"] = sv["time"]
            self._save(e, sv)

        # Crosses, balls in behind
        lc = getattr(b, "last_cross", None)
        if lc and lc.get("time") != S["cross"] and lc.get("kind") != "set_piece":
            S["cross"] = lc["time"]
            self._say(e, PRI["cross"], self._line("cross"))
        tp = getattr(b, "through_plan", None)
        if tp is not None and id(tp) != S["kick"] and b.owner is None:
            S["kick"] = id(tp)
            pt = tp.get("point")
            kicker = getattr(b, "last_owner", None) or self._owner
            if pt is not None and kicker is not None:
                gx = float(WIDTH) if kicker.team == 0 else 0.0
                far = abs(pt[0] - kicker.pos.x) / M_TO_PX
                if abs(gx - pt[0]) / M_TO_PX < 36.7 and far >= THROUGH[1] and self.rng.random() < THROUGH[0]:
                    self._say(e, PRI["through"], self._line("through"))

        # Who's got it: names in the build-up, a tackle
        o = b.owner
        if o is not None and o is not self._owner and not b.is_dead:
            prev = self._owner
            if prev is not None and prev.team != o.team and o.role != "GK" and \
                    (o.pos - prev.pos).length() < 2.5 * M_TO_PX and self.rng.random() < 0.5:
                self._say(e, PRI["tackle"], self._line("tackle"))
            elif e.time_elapsed - self.last_name >= NAME_EVERY and self.rng.random() < NAME_CHANCE:
                self.last_name = e.time_elapsed
                self._say(e, PRI["name"], self._name(o))
        if o is not None:
            self._owner = o

        # Fouls, cards
        fa = getattr(e, "_foul_display_at", None)
        cd = getattr(e, "_card_display", None)
        card_now = cd is not None and cd.get("at") == fa
        if fa is not None and fa != S["foul"]:
            S["foul"] = fa
            if not card_now:
                self._say(e, PRI["foul"], self._line("foul"))
        if cd and cd.get("at") != S["card"]:
            S["card"] = cd.get("at")
            who = next((p for p in e.team0 + e.team1 if getattr(p, "name", None) == cd.get("name")), None)
            kind = cd.get("type")
            moment = {"yellow": "yellow", "red": "red", "second_yellow": "second_yellow"}.get(kind)
            if moment:
                self._say(e, PRI["red"] if moment != "yellow" else PRI["yellow"],
                          (self._name(who) if who else []) + self._line(moment))
                if moment != "yellow":
                    self._co(e, "co_red")

        # Restarts
        if b.is_dead and getattr(b, "restart_type", None):
            key = (b.restart_type, round(getattr(b, "restart_time", 0.0) or 0.0, 2))
            if key != S["restart"]:
                S["restart"] = key
                self._restart(e, b)

        # Substitutions
        log = getattr(getattr(e, "subs", None), "log", None) or []
        if len(log) > S["subs"]:
            for s in log[S["subs"]:]:
                on = next((p for p in e.team0 + e.team1 if getattr(p, "name", None) == s.get("on_name")), None)
                club = self.clubs.get(s.get("team"))
                self._say(e, PRI["sub"], self._line("sub") + ([("comm",) + club] if club else []) +
                          (self._name(on) if on else []))
            S["subs"] = len(log)

        # The clock
        m = e.match_minute()
        if st == "second_half" and m >= 80 and not S["late"]:
            S["late"] = True
            self._say(e, PRI["late"], self._line("late"))
        try:
            import gameplay.match_engine as me
            over = e.half_elapsed > me.HALF_DURATION_REAL
        except Exception:
            over = False
        if st == "second_half" and over and not S["stoppage"]:
            S["stoppage"] = True
            self._say(e, PRI["stoppage"], self._line("stoppage"))

    # ------------------------------------------------------------------------------------------------------
    def _whistle(self, e, st):
        s0, s1 = e.score
        if st == "halftime":
            parts = self._line("half_time")
            if s0 == s1:
                parts += self._line("ht_level")
                co = "co_ht_level"
            else:
                w = 0 if s0 > s1 else 1
                parts += [("comm",) + self.clubs[w]] + self._line("ht_lead") + self._score(s0, s1)
                co = "co_ht_lead"
        else:
            parts = self._line("full_time")
            if s0 == s1:
                parts += self._line("ft_draw")
                co = "co_ft_draw"
            else:
                w = 0 if s0 > s1 else 1
                parts += [("comm",) + self.clubs[w]] + self._line("ft_win") + self._score(s0, s1)
                co = "co_ft_win"
        self._say(e, PRI["whistle"], parts)
        self._co(e, co)

    def _score(self, a, b):
        return [("comm", f"score_{max(a, b)}_{min(a, b)}", score_text(a, b))]

    def _co(self, e, moment):
        key = "co_ht" if moment.startswith("co_ht") else "co_ft" if moment.startswith("co_ft") else moment
        if self.rng.random() < CO_CHANCE.get(key, 0.6):
            self._say(e, PRI["co"], self._line(moment))

    def _goal(self, e, team):
        g = e.goal_events[-1] if getattr(e, "goal_events", None) else {}
        scorer = next((p for p in e.team0 + e.team1 if getattr(p, "name", None) == g.get("name")), None)
        if g.get("own_goal"):
            self._say(e, PRI["goal"], self._line("own_goal"))
            self._co(e, "co_own_goal")
            return
        pen = self._shot is not None and self._shot.get("type") == "penalty"
        parts = self._line("goal")
        if scorer is not None:
            parts += self._name(scorer) + self._line("goal_scorer")
        if e.match_minute() <= 5 and sum(e.score) == 1 and e.match_state == "first_half":
            parts += self._line("early_goal")
        self._say(e, PRI["goal"], parts)
        if not pen:
            self._co(e, "co_goal")

    def _new_shot(self, e, si):
        sh = si["shooter"]
        gx = float(WIDTH) if sh.team == 0 else 0.0
        d = ((sh.pos.x - gx) ** 2 + (sh.pos.y - HEIGHT / 2) ** 2) ** 0.5 / M_TO_PX
        opp = e.team1 if sh.team == 0 else e.team0
        free = all((o.pos - sh.pos).length() > 2.0 * M_TO_PX for o in opp
                   if o.role != "GK" and getattr(o, "is_active", True))
        self._shot = {"t": si["time"], "team": sh.team, "dist": d, "type": si.get("type"),
                      "speed": si.get("speed_ms", 0.0) or 0.0, "big": d < BIG_CHANCE_M and free, "done": False,
                      "shooter": sh}
        if si.get("type") == "penalty":
            return                                              # (the penalty's been called already)
        moment = "header_shot" if si.get("type") == "header" else "shot_far" if d > FAR_M else "shot"
        parts = self._line(moment)
        if self.rng.random() < 0.6:
            parts = self._name(sh) + parts
        self._say(e, PRI["shot"], parts)

    def _shot_outcome(self, e):
        s = self._shot
        if s is None or s["done"]:
            return
        b = e.ball
        if e.time_elapsed - s["t"] > 4.0:
            s["done"] = True
            return
        lt = getattr(b, "last_toucher", None)
        if lt is not None and lt.team != s["team"] and lt.role != "GK" and e.time_elapsed - s["t"] < 0.8 \
                and not b.is_dead:
            s["done"] = True
            self._say(e, PRI["outcome"], self._line("blocked"))
            return
        if b.is_dead and getattr(b, "restart_type", None) in ("goal_kick", "corner_kick") and \
                getattr(b, "restart_time", 0.0) >= s["t"]:
            s["done"] = True
            if b.restart_type == "corner_kick":
                return                                          # (off a defender or the keeper: the corner's called)
            if s.get("type") == "penalty":
                self._say(e, PRI["outcome"], self._line("pen_missed"))
                return
            y, z = self._last_live if self._last_live is not None else (None, None)
            moment = "wide"
            if z is not None and z > 2.44 * M_TO_PX:
                moment = "over"
            if y is not None and abs(y - HEIGHT / 2) < (3.66 + CLOSE_M) * M_TO_PX and (z is None or z < (2.44 + CLOSE_M) * M_TO_PX):
                moment = "close"
            self._say(e, PRI["outcome"], self._line(moment))
            if s["big"]:
                self._co(e, "co_miss")

    def _save(self, e, sv):
        s = self._shot
        if s is None or s["done"] or sv.get("time", 0) < s["t"]:
            return
        s["done"] = True
        if s.get("type") == "penalty":
            self._say(e, PRI["outcome"], self._line("pen_saved"))
            self._co(e, "co_save")
            return
        big = s["dist"] < BIG_SAVE[0] or s["speed"] > BIG_SAVE[1] or sv.get("type") == "tip"
        self._say(e, PRI["outcome"], self._line("big_save" if big else "save"))
        if big:
            self._co(e, "co_save")

    def _restart(self, e, b):
        rt = b.restart_type
        if rt == "corner_kick":
            self._say(e, PRI["corner"], self._line("corner"))
        elif rt == "penalty":
            self._say(e, PRI["penalty"], self._line("penalty"))
        elif rt == "offside":
            self._say(e, PRI["offside"], self._line("offside"))
        elif rt == "free_kick" and getattr(b, "_fk_zone", None) == "shoot":
            self._say(e, PRI["fk_danger"], self._line("fk_danger"), t=e.time_elapsed + 1.5)
        elif rt == "goal_kick" and (self._shot is None or self._shot["done"]) and self.rng.random() < 0.25:
            self._say(e, PRI["goal_kick"], self._line("goal_kick"))
        elif rt == "kick_off" and e.match_state in ("first_half", "second_half") and sum(e.score) > 0 \
                and e.half_elapsed > 1.0:
            self._say(e, PRI["kickoff_restart"], self._line("kickoff_restart"), t=e.time_elapsed + 2.0)

    # ------------------------------------------------------------------------------------------------------
    def tick(self, e, clock=None, length=None):
        """Every drawn frame: say what's next.  clock / length: for the transcript (game time, estimated length)
        instead of the real clock and the sound's own length."""
        now = time.perf_counter() if clock is None else clock
        shown = getattr(e, "_shown_t", e.time_elapsed) if clock is None else e.time_elapsed
        speed = getattr(e, "match_speed", 1) or 1
        min_pri = next(p for s, p in SPEED_MIN_PRI if speed > s)
        # drop old news
        self.queue = [q for q in self.queue if shown - q["t"] <= (CO_STALE if q["pri"] == PRI["co"] else
                                                                  next(s for p, s in STALE if q["pri"] >= p))
                      and q["pri"] >= min_pri]
        ready = [q for q in self.queue if q["t"] <= shown + 0.02]
        cur = self.cur
        if cur is not None:
            if ready and max(q["pri"] for q in ready) >= CUT_FROM and max(q["pri"] for q in ready) > cur["pri"] \
                    and cur["pri"] < CUT_FROM:
                self._stop()
                cur = None
            elif now < cur["until"]:
                return
            elif cur["i"] < len(cur["parts"]):
                self._part(cur, now, length)
                return
            else:
                self.cur = None
                self.quiet_since = now
                cur = None
        if not ready or not self.on:
            return
        nxt = max(ready, key=lambda q: (q["pri"], -q["t"]))
        if nxt["pri"] == PRI["co"] and now - self.quiet_since < CO_AFTER:
            others = [q for q in ready if q is not nxt]
            if not others:
                return
            nxt = max(others, key=lambda q: (q["pri"], -q["t"]))
        self.queue.remove(nxt)
        self.cur = {"pri": nxt["pri"], "parts": nxt["parts"], "i": 0, "until": now, "min": nxt["min"],
                    "t": shown}
        self.log.append((round(e.time_elapsed, 1), nxt["min"], nxt["parts"][0][0],
                         " ".join(p[2] for p in nxt["parts"])))
        self._part(self.cur, now, length)

    def _part(self, cur, now, length):
        voice, clip, text = cur["parts"][cur["i"]]
        cur["i"] += 1
        dur = None
        if self.audio and length is None:
            snd = self._sound(voice, clip)
            if snd is not None:
                self.chan[voice].play(snd)
                dur = snd.get_length()
        if dur is None:
            dur = length(text) if length else 0.0
        cur["until"] = now + dur + GAP

    def _sound(self, voice, clip):
        k = (voice, clip)
        if k not in self.sounds:
            path = os.path.join(AUDIO, voice, clip + ".mp3")
            snd = None
            if os.path.exists(path):
                try:
                    import pygame
                    snd = pygame.mixer.Sound(path)
                except Exception:
                    snd = None
            self.sounds[k] = snd
        return self.sounds[k]

    def _stop(self):
        if self.audio:
            for c in self.chan.values():
                c.stop()
        self.cur = None

    def toggle(self):
        self.on = not self.on
        if not self.on:
            self._stop()
            self.queue = []
        return self.on


def _short(name):
    """A club's name as it's said: 'Northwick FC' -> 'Northwick', 'Westmoor County' stays."""
    for suf in (" FC", " AFC", " F.C."):
        if name.endswith(suf):
            return name[: -len(suf)]
    return name


def have_audio():
    """Are there any commentary sound files yet?"""
    try:
        return any(f.endswith(".mp3") for v in ("comm", "co") for f in os.listdir(os.path.join(AUDIO, v)))
    except Exception:
        return False
