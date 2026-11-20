"""
gameplay/match_stats.py
=======================
The match statistics shown at half time and full time - the numbers a TV graphic gives - worked out from what
actually happens in the match (they used to be the score and possession only; "shots on target" counted goals).

  shots / on target   every shot; on target = it scored or the keeper had to save it
  big chances         a shot from inside 12 m with no defender within 2 m of the shooter (close to Opta's
                      "a situation where a player should reasonably be expected to score")
  passes              a ball played to a team-mate that a team-mate got next (completed), or that the other
                      side got next (not completed) - tackles don't count
  corners, fouls, yellow / red cards
  distance            km run by the team (Premier League teams run ~105-115 km a match - Opta)
  top speed           the quickest any player went (the Premier League record is 37.4 km/h)

Fed by MatchEngine.step() -> update(); read with table().
"""

from config.constants import M_TO_PX, WIDTH, HEIGHT

BIG_CHANCE_M = 12.0
BIG_CHANCE_FREE_M = 2.0


class MatchStats:
    def __init__(self):
        z = lambda: [0, 0]
        self.shots, self.on_target, self.big = z(), z(), z()
        self.passes, self.passes_ok = z(), z()
        self.corners, self.fouls, self.yellows, self.reds = z(), z(), z(), z()
        self.dist = [0.0, 0.0]
        self.top = (0.0, None)                       # (m/s, player)
        self._shot = None                            # the last shot: [team, time, score, decided]
        self._last_owner = None
        self._loose_from = None                      # the man it last left (played, not taken off him)
        self._was_shot = False
        self._prev = {}
        self._restart = None
        self._cards = set()

    # ------------------------------------------------------------------------------------------------------
    def update(self, e, dt):
        b = e.ball
        live = e.match_state in ("first_half", "second_half", "et_first", "et_second")
        ps = [p for p in e.team0 + e.team1 if getattr(p, "is_active", True)]
        if live and not b.is_dead:
            for p in ps:
                k = id(p)
                last = self._prev.get(k)
                if last is not None:
                    d = (p.pos - last).length()
                    if d < 1.2 * M_TO_PX:                  # (a jump - a sub or a reset - isn't running)
                        self.dist[p.team] += d / M_TO_PX
                sp = p.vel.length() / M_TO_PX
                if sp > self.top[0] and sp < 12.5:
                    self.top = (sp, p)
        for p in ps:
            self._prev[id(p)] = p.pos.copy()

        # Shots, and whether they were on target
        si = getattr(b, "shot_info", None)
        if si and si.get("shooter") is not None and (self._shot is None or si["time"] != self._shot[1]):
            sh = si["shooter"]
            t = sh.team
            self.shots[t] += 1
            gx = float(WIDTH) if t == 0 else 0.0
            opp = e.team1 if t == 0 else e.team0
            dist_goal = ((sh.pos.x - gx) ** 2 + (sh.pos.y - HEIGHT / 2) ** 2) ** 0.5 / M_TO_PX
            free = all((o.pos - sh.pos).length() > BIG_CHANCE_FREE_M * M_TO_PX
                       for o in opp if o.role != "GK" and getattr(o, "is_active", True))
            if dist_goal < BIG_CHANCE_M and free and si.get("type") != "penalty":
                self.big[t] += 1
            if si.get("type") == "penalty":
                self.big[t] += 1                       # (a penalty is always a big chance)
            self._shot = [t, si["time"], list(e.score), False]
        if self._shot is not None and not self._shot[3]:
            t = self._shot[0]
            sv = getattr(b, "last_save", None)
            if list(e.score) != self._shot[2] and e.score[t] > self._shot[2][t]:
                self.on_target[t] += 1
                self._shot[3] = True
            elif sv and sv.get("time", -1) >= self._shot[1] and sv.get("keeper") is not None \
                    and sv["keeper"].team != t:
                self.on_target[t] += 1
                self._shot[3] = True
            elif e.time_elapsed - self._shot[1] > 4.0:
                self._shot[3] = True

        # Passes: the ball left a man's feet (not taken off him) - who got it next?
        o = b.owner
        if b.is_dead:
            self._last_owner = self._loose_from = None
        elif o is not None:
            A = self._last_owner
            if A is not None and o is not A and self._loose_from is A:
                if o.team == A.team:
                    self.passes[A.team] += 1
                    self.passes_ok[A.team] += 1
                elif not self._was_shot:
                    self.passes[A.team] += 1
            self._last_owner, self._loose_from = o, None
        elif self._last_owner is not None and self._loose_from is None:
            self._loose_from = self._last_owner
            self._was_shot = bool(si and si.get("shooter") is self._last_owner
                                  and e.time_elapsed - si.get("time", -9) < 0.5)

        # Corners
        if b.is_dead and getattr(b, "restart_type", None) == "corner_kick" and \
                getattr(b, "restart_taker", None) is not None:
            key = round(getattr(b, "restart_time", 0.0) or 0.0, 2)
            if key != self._restart:
                self._restart = key
                self.corners[b.restart_taker.team] += 1

        # Fouls and cards (the engine's booking display)
        cd = getattr(e, "_card_display", None)
        if cd and e.time_elapsed < cd.get("until", 0):
            key = (cd.get("name"), cd.get("type"), round(cd.get("until", 0), 1))
            if key not in self._cards:
                self._cards.add(key)
                who = next((p for p in e.team0 + e.team1 if getattr(p, "name", None) == cd.get("name")), None)
                if who is not None:
                    if cd.get("type") == "yellow":
                        self.yellows[who.team] += 1
                    elif cd.get("type") in ("red", "second_yellow"):
                        self.reds[who.team] += 1
                        if cd.get("type") == "second_yellow":
                            self.yellows[who.team] += 1

    def foul(self, team):
        self.fouls[team] += 1

    # ------------------------------------------------------------------------------------------------------
    def table(self, possession):
        """Rows for the screen: (label, home, away)."""
        pc = lambda t: f"{round(100 * self.passes_ok[t] / self.passes[t])}%" if self.passes[t] else "-"
        rows = [("Possession", f"{possession[0]}%", f"{possession[1]}%"),
                ("Shots", str(self.shots[0]), str(self.shots[1])),
                ("On target", str(self.on_target[0]), str(self.on_target[1])),
                ("Big chances", str(self.big[0]), str(self.big[1])),
                ("Passes", str(self.passes[0]), str(self.passes[1])),
                ("Pass accuracy", pc(0), pc(1)),
                ("Corners", str(self.corners[0]), str(self.corners[1])),
                ("Fouls", str(self.fouls[0]), str(self.fouls[1])),
                ("Yellow cards", str(self.yellows[0]), str(self.yellows[1])),
                ("Distance run", f"{self.dist[0] / 1000:.1f} km", f"{self.dist[1] / 1000:.1f} km")]
        if self.reds[0] or self.reds[1]:
            rows.insert(9, ("Red cards", str(self.reds[0]), str(self.reds[1])))
        return rows

    def fastest(self):
        sp, p = self.top
        return (getattr(p, "name", "?"), p.team, sp * 3.6) if p is not None else None

    def as_dict(self, possession):
        return {"rows": self.table(possession), "fastest": self.fastest()}
