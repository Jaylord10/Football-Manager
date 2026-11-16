"""
The 3D match, live, inside the game's match screen.

The match engine plays the match as always (gameplay/match_engine.py) and decides everything; this only draws
it.  A second process runs the 3D view (viewer.py) off-screen: the game hands it what the engine says every
1/30 s of football (where everyone is, the ball, dead balls, celebrations...), it draws the TV picture and puts
it in a piece of shared memory, and the game copies the newest picture onto the pitch area of its window - the
score bar, the panels, subs and half-time talks stay the game's own.

The 3D view shows the match LAG frames (half a second) behind the engine, because a few things (a kick, the run
up to a shot) are drawn from what happens next.  The score bar shows the same moment as the picture.

After a goal the 3D view shows a replay; the engine waits while it does (holding()), so nothing's missed.
If anything goes wrong in the 3D view the game carries on in 2D (the error is in broadcast3d/live_3d.log).
"""
import os
import sys
import time
import struct
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
LAG = 15                         # (frames of 1/30 s: how far behind the engine the picture runs)
HEAD = 64                        # (bytes at the start of the shared memory: see _Header)
LOG = os.path.join(HERE, "live_3d.log")


def frame_from_engine(e):
    """One frame of the match as the 3D view reads it (the same as record.py writes)."""
    b = e.ball
    everyone = e.team0 + e.team1
    fr = {"t": round(e.time_elapsed, 2), "s": list(e.score), "st": e.match_state,
          "b": [round(b.pos.x, 1), round(b.pos.y, 1), round(getattr(b, "z", 0.0), 1)],
          "o": everyone.index(b.owner) if b.owner in everyone else -1,
          "p": [[round(p.pos.x, 1), round(p.pos.y, 1), round(p.facing.x, 3), round(p.facing.y, 3),
                 round(p.vel.length(), 1), p.state, int(getattr(p, "is_active", True)),
                 getattr(p, "dive_state", "") if p.role == "GK" else ""] for p in everyone]}
    if getattr(b, "is_dead", False) and getattr(b, "restart_type", None):        # (a dead ball: who takes it)
        tk = getattr(b, "restart_taker", None)
        fr["r"] = [b.restart_type, everyone.index(tk) if tk in everyone else -1]
    cd = getattr(e, "_card_display", None)                                        # (a booking: who, which card)
    if cd and e.time_elapsed < cd.get("until", 0):
        who = next((j for j, p in enumerate(everyone) if getattr(p, "name", None) == cd.get("name")), -1)
        fr["card"] = [cd.get("type"), who]
    cel = getattr(b, "_celebration", None)
    if cel and e.time_elapsed < cel.get("until", 0) and cel.get("scorer") in everyone:   # (a goal celebration)
        fr["c"] = [cel["team"], everyone.index(cel["scorer"])]
    return fr


def names_from_engine(e):
    return [[p.name, p.role, getattr(p, "number", i + 1)] for i, p in enumerate(e.team0 + e.team1)]


# The shared memory: a header, then two picture slots (the 3D side fills one while the game reads the other).
#   ready (0: starting, 1: drawing, 2: given up), latest slot (0/1), picture count, the frame shown, replay on,
#   width, height
_FMT = "<iiqqiii"


def _write_head(buf, **kw):
    cur = list(struct.unpack_from(_FMT, buf, 0))
    keys = ("ready", "slot", "count", "k", "replay", "w", "h")
    for n, key in enumerate(keys):
        if key in kw:
            cur[n] = kw[key]
    struct.pack_into(_FMT, buf, 0, *cur)


def _read_head(buf):
    ready, slot, count, k, replay, w, h = struct.unpack_from(_FMT, buf, 0)
    return {"ready": ready, "slot": slot, "count": count, "k": k, "replay": replay, "w": w, "h": h}


class Live3D:
    """The game's side.  push(engine) every engine step, picture() for the newest picture (a pygame Surface,
    or None while there isn't one), shown() for the frame it shows, holding() while a replay's on."""

    def __init__(self, engine, size, home, away, flags=()):
        import multiprocessing as mp
        from multiprocessing import shared_memory
        self.w, self.h = size
        self.frames = []                # (only what the score bar needs: "s", "t", "st")
        self.failed = False
        self._step = 0
        self._sent = 0
        self._count = -1
        self._surf = None
        self._k = -1
        self.shm = shared_memory.SharedMemory(create=True, size=HEAD + 2 * self.w * self.h * 3)
        _write_head(self.shm.buf, ready=0, slot=0, count=0, k=-1, replay=0, w=self.w, h=self.h)
        ctx = mp.get_context("spawn")
        self.conn, child = ctx.Pipe()
        meta = {"home": home, "away": away, "names": names_from_engine(engine)}
        self.proc = ctx.Process(target=_child, args=(child, self.shm.name, self.w, self.h, meta, list(flags)),
                                daemon=True)
        self.proc.start()
        self.push(engine, force=True)

    # -- the game's side ---------------------------------------------------------------------------------
    def push(self, engine, force=False):
        """After each engine step: every second step (1/30 s of football) is a frame for the 3D view."""
        if self.failed:
            return
        self._step += 1
        if not force and self._step % 2:
            return
        fr = frame_from_engine(engine)
        self.frames.append({"s": fr["s"], "t": fr["t"], "st": fr["st"]})
        try:
            self.conn.send(("frame", fr))
        except Exception:
            self._give_up("the 3D view stopped (sending)")

    def ready(self):
        if self.failed:
            return False
        h = _read_head(self.shm.buf)
        if h["ready"] == 2 or not self.proc.is_alive():
            self._give_up("the 3D view stopped")
            return False
        return h["ready"] == 1

    def holding(self):
        """True while the 3D view needs the engine to wait (getting ready, or a replay)."""
        if self.failed:
            return False
        h = _read_head(self.shm.buf)
        if h["ready"] == 2 or not self.proc.is_alive():
            self._give_up("the 3D view stopped")
            return False
        return h["ready"] == 0 or bool(h["replay"])

    def replaying(self):
        """True while the 3D view shows a goal again."""
        if self.failed:
            return False
        return bool(_read_head(self.shm.buf)["replay"])

    def skip(self):
        """Stop the replay: back to the match."""
        try:
            self.conn.send(("skip",))
        except Exception:
            self._give_up("the 3D view stopped (sending)")

    def picture(self):
        """The newest picture (a pygame Surface the size of the pitch area), or None."""
        import pygame
        if not self.ready():
            return None
        h = _read_head(self.shm.buf)
        if h["count"] != self._count and h["count"] > 0:
            off = HEAD + h["slot"] * self.w * self.h * 3
            data = bytes(self.shm.buf[off:off + self.w * self.h * 3])
            self._surf = pygame.image.frombuffer(data, (self.w, self.h), "RGB").copy()
            self._count = h["count"]
            self._k = h["k"]
        return self._surf

    def shown(self):
        """The frame the picture shows ({"s": score, "t": time, "st": match state}), or None."""
        if 0 <= self._k < len(self.frames):
            return self.frames[self._k]
        return None

    def close(self):
        try:
            self.conn.send(("quit",))
        except Exception:
            pass
        try:
            self.proc.join(timeout=2)
            if self.proc.is_alive():
                self.proc.terminate()
        except Exception:
            pass
        try:
            self.shm.close()
            self.shm.unlink()
        except Exception:
            pass

    def _give_up(self, why):
        if not self.failed:
            self.failed = True
            try:
                with open(LOG, "a") as f:
                    f.write(time.strftime("%Y-%m-%d %H:%M ") + why + " - carrying on in 2D\n")
            except Exception:
                pass


class _LiveDirector:
    """Which frame to draw: LAG behind the newest, and after a goal - once they've celebrated a few seconds -
    a replay of the five seconds before it, slowed, from behind the goal (the engine waits meanwhile)."""
    BEFORE, AFTER, WAIT, SLOW = 150, 18, 150, 0.55

    def __init__(self, v):
        self.v = v
        self.t = 0.0
        self.goals = []
        self.done = set()
        self.rp = None
        v.replay = None

    def note(self, F, k):
        if k > 0 and "c" in F[k] and "c" not in F[k - 1]:
            self.goals.append(k)

    def frame(self, F, real_dt):
        """-> (frame index, how much match time it moves on)"""
        import viewer
        if self.rp is not None:
            g, pos = self.rp
            pos += real_dt * 30.0 * self.SLOW
            if pos >= g + self.AFTER:
                self.rp = None
                self.v.replay = None
                self.v._gp = {}
            else:
                self.rp = (g, pos)
                return int(pos), real_dt * self.SLOW
        want = max(0, len(F) - 1 - LAG)
        dt = max(0.0, (want - self.t) / 30.0)
        self.t = float(max(self.t, want))
        for g in self.goals:
            if g not in self.done and self.t >= g + self.WAIT:
                self.done.add(g)
                if g - self.BEFORE >= 0:
                    self.rp = (g, float(g - self.BEFORE))
                    side = 1 if viewer.to_world(F[g - 5]["b"][0], F[g - 5]["b"][1])[0] > 0 else -1
                    self.v.replay = side
                    self.v._gp = {}                         # (the replay shows them where they were)
                    self.v.gball = None                     # (and the ball where it was, not in the net)
                    return g - self.BEFORE, 1 / 30.0
        return int(self.t), dt


def _child(conn, shm_name, w, h, meta, flags):
    """The 3D side (its own process): draw the match as the frames come in."""
    from multiprocessing import shared_memory
    shm = shared_memory.SharedMemory(name=shm_name)
    buf = shm.buf
    try:
        os.environ["FM3D_SIZE"] = f"{w}x{h}"
        sys.argv = ["viewer.py", "--nolineups", "--embedded"] + list(flags)
        sys.path.insert(0, HERE)
        with open(os.path.join(HERE, "last_live.log"), "w") as log:
            sys.stdout = log
            sys.stderr = log
            _draw_loop(conn, buf, w, h, meta)
    except Exception:
        try:
            with open(LOG, "a") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M ") + "3D view failed:\n" + traceback.format_exc())
        except Exception:
            pass
        _write_head(buf, ready=2)
    finally:
        try:
            del buf
            shm.close()
        except Exception:
            pass


def _draw_loop(conn, buf, w, h, meta):
    import numpy as np
    import viewer
    import players3d
    viewer.AnimPlayer = players3d.AnimPlayer
    from panda3d.core import ClockObject
    F = []
    match = {"home": meta["home"], "away": meta["away"], "names": meta["names"], "frames": F}
    v = viewer.Viewer(match)
    try:
        g = v.win.getGsg()
        print("graphics:", g.getDriverVendor(), "|", g.getDriverRenderer(), "|", g.getDriverVersion(), flush=True)
    except Exception:
        pass
    gks = tuple(i for i, nm in enumerate(meta["names"]) if len(nm) > 1 and nm[1] == "GK") or (0, 11)
    ev_lo = 0
    d = _LiveDirector(v)
    clock = ClockObject.getGlobalClock()
    last = time.perf_counter()
    slot, count, shown_k, started = 0, 0, -1, False
    size = w * h * 3
    n_draw, t_draw = 0, 0.0
    while True:
        # the new frames from the game
        got = False
        while conn.poll(0 if F else 0.05):
            msg = conn.recv()
            if msg[0] == "quit":
                return
            if msg[0] == "skip" and d.rp is not None:           # (Enter: no more of the replay)
                d.rp = None
                v.replay = None
                v._gp = {}
                _write_head(buf, replay=0)
            if msg[0] == "frame":
                fr = msg[1]
                fr["k"] = len(F)
                F.append(fr)
                d.note(F, len(F) - 1)
                got = True
        if not F:
            continue
        if got and len(F) - 4 > ev_lo:
            viewer.find_events(F, gks, ev=v.events, lo=ev_lo)
            ev_lo = max(ev_lo, len(F) - 4)
        now = time.perf_counter()
        real_dt = min(0.1, now - last)
        k, dt = d.frame(F, real_dt)
        if k == shown_k and d.rp is None and started:
            time.sleep(0.004)                           # (nothing new to draw: the match is paused or waiting)
            last = now
            continue
        last = now
        t0 = time.perf_counter()
        v.show(F[k], dt or 1e-3)
        v.taskMgr.step()
        if not started:                                 # (the first time: draw twice - the shadows settle)
            v.show(F[k], 1e-3)
            v.taskMgr.step()
        tex = v.win.getScreenshot()
        if tex is None:
            continue
        a = np.frombuffer(bytes(tex.getRamImageAs("RGB")), np.uint8)
        tw, th = tex.getXSize(), tex.getYSize()
        if (tw, th) != (w, h):
            a = a.reshape(th, tw, 3)[::-1][:h, :w]
            img = np.zeros((h, w, 3), np.uint8)
            img[:a.shape[0], :a.shape[1]] = a
        else:
            img = a.reshape(h, w, 3)[::-1]
        nxt = 1 - slot
        off = HEAD + nxt * size
        buf[off:off + size] = np.ascontiguousarray(img).tobytes()
        slot, count, shown_k = nxt, count + 1, k
        _write_head(buf, ready=1, slot=slot, count=count, k=k, replay=1 if d.rp is not None else 0)
        started = True
        n_draw += 1
        t_draw += time.perf_counter() - t0
        if n_draw == 300:
            print(f"3D picture: {t_draw / n_draw * 1000:.1f} ms each", flush=True)
        clock.tick()
