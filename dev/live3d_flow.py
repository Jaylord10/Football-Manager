"""Live 3D flow test: a real career match in the game window (SDL dummy) drawn in 3D by broadcast3d/live.py.
usage: python dev/live3d_flow.py <game_dir> <frames> <out_prefix> [speed]   env: HALF (seconds a half), NOHUMAN=1 (no
human side: no half-time talk), KNOCKOUT=1 (extra time / penalties), SHOTS=200,700 (pictures at those frames).
Copy the game to a scratch folder first (it writes saves)."""
import os, sys, time
G = sys.argv[1]; N = int(sys.argv[2]); OUT = sys.argv[3]; SPEED = int(sys.argv[4]) if len(sys.argv) > 4 else 1
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["FM_CAREER_HALF"] = "60"
sys.path.insert(0, G); os.chdir(G)
if __name__ == "__main__":
    from career import ui, matches
    import pygame
    app = ui.App(); app.new_career_screen(); app.start_career(7); c = app.career
    me_id = c["my_club"]
    opp = next(i for i in range(20) if i != me_id)
    cfg = matches.write_config(c, me_id, opp, "livetest", auto_subs={me_id: True}, human=(None if os.environ.get("NOHUMAN") else me_id))
    os.environ["FM_MATCH_CONFIG"] = cfg
    import config.formations as formations
    from core.database import PlayerDatabase
    formations.db = PlayerDatabase(cfg)
    if os.environ.get('KNOCKOUT'): formations.db.knockout = {'agg': [0, 0]}
    import gameplay.match_engine as mem
    mem.RL_ENABLED = False; mem.HALF_DURATION_REAL = float(os.environ.get("HALF", "60"))
    os.environ["FM_MATCH_VIEW"] = "3d"
    e = mem.MatchEngine(career=True)
    e.match_speed = SPEED
    class _C:
        def tick(self, *a):
            time.sleep(0.016); return 16
    e.clock = _C()
    cnt = {"n": 0, "t0": time.time()}
    real = e._render
    shots = {int(x) for x in os.environ.get("SHOTS", "").split(",") if x}
    def render(flip=True):
        real(flip)
        cnt["n"] += 1
        n = cnt["n"]
        if os.environ.get("KILL3D") and n == int(os.environ["KILL3D"]) and e.live3d:   # (the 3D side dies: 2D?)
            e.live3d.proc.kill()
        for kv in os.environ.get("KEYS", "").split(","):      # (KEYS=300:space,500:n - press keys at frames)
            if ":" in kv and int(kv.split(":")[0]) == n:
                key = getattr(pygame, "K_" + kv.split(":")[1])
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))
        if n in shots or n == N:
            pygame.image.save(e.window, f"{OUT}_{n}.png")
            sh = e.live3d.shown() if e.live3d else None
            print(n, "3d on" if e._3d_on() else "2d", "holding" if (e.live3d and e.live3d.holding()) else "", "shown", sh, "engine t", round(e.time_elapsed, 2), "score", e.score, f"{time.time()-cnt['t0']:.0f}s", flush=True)
        hold = bool(e.live3d and e.live3d.holding())
        if hold != cnt.get("hold") or e.match_state != cnt.get("st") or e.score != cnt.get("sc"):
            print(n, "state", e.match_state, "hold", hold, "score", list(e.score), "shown", e.live3d.shown() if e.live3d else None, flush=True)
            if cnt.get("hold") is not None and hold != cnt.get("hold"):
                pygame.image.save(e.window, f"{OUT}_hold{n}.png")
            cnt["hold"] = hold; cnt["st"] = e.match_state; cnt["sc"] = list(e.score)
        if cnt.get("rp_shot") is None and hold and n > 200:
            cnt["rp_shot"] = n + 120
        if n == cnt.get("rp_shot"):
            pygame.image.save(e.window, f"{OUT}_replay{n}.png")
        sh_st = (e.live3d.shown() or {}).get("st") if e.live3d else None
        if sh_st != cnt.get("sh_seen"):                         # (and after the picture's own state changes)
            cnt["sh_seen"] = sh_st
            cnt["sh_shot"] = (n + 60, sh_st)
        if cnt.get("sh_shot") and n == cnt["sh_shot"][0]:
            pygame.image.save(e.window, f"{OUT}_shown_{cnt['sh_shot'][1]}{n}.png")
        if e.match_state != cnt.get("st_seen"):                 # (a picture a little after each change of state)
            cnt["st_seen"] = e.match_state
            cnt["st_shot"] = (n + 45, e.match_state)
        if cnt.get("st_shot") and n == cnt["st_shot"][0]:
            pygame.image.save(e.window, f"{OUT}_{cnt['st_shot'][1]}{n}.png")
        if e.match_state == "full_time" and not cnt.get("ft"):
            cnt["ft"] = n
        if cnt.get("ft") and n == cnt["ft"] + 60:
            pygame.image.save(e.window, f"{OUT}_ft{n}.png"); e.running = False
        if n >= N:
            e.running = False
    e._render = render
    real_p = e._render_paused
    def render_paused():                                       # (paused frames count too: KEYS can unpause)
        real_p()
        cnt["n"] += 1
        n = cnt["n"]
        for kv in os.environ.get("KEYS", "").split(","):
            if ":" in kv and int(kv.split(":")[0]) == n:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=getattr(pygame, "K_" + kv.split(":")[1]),
                                                     mod=0, unicode=""))
        if n in shots:
            pygame.image.save(e.window, f"{OUT}_{n}.png")
    e._render_paused = render_paused
    names0 = [p.name for p in e.team0 + e.team1]
    e.run()
    print("subs on:", [(i, a, p.name) for i, (a, p) in enumerate(zip(names0, e.team0 + e.team1)) if a != p.name])
    print("done; live3d closed:", e.live3d is None, "view_wanted", e.view_wanted)
