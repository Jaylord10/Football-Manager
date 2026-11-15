"""
broadcast3d/check.py - a quick check that the 3D view still works in all its modes: renders a couple of frames
of each (day, close camera, a player camera, night, rain, overcast, another club's ground, the live window's
test) and says which (if any) went wrong.  usage: python broadcast3d/check.py
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = [("day", ["5600", "2"]), ("close", ["5600", "2", "--close"]), ("follow", ["6260", "2", "--follow=11"]),
        ("night", ["5600", "2", "--night"]), ("rain", ["5600", "2", "--rain"]), ("overcast", ["5600", "2", "--overcast"]),
        ("goal", ["13500", "3"]), ("other ground", ["5600", "2", "--teams=Kingsmere,Penrith"]),
        ("bowl", ["5600", "2", "--teams=Northwick FC,Lydmouth"]), ("live", ["5600", "--test"])]


def main():
    bad = []
    with tempfile.TemporaryDirectory() as out:
        for name, args in RUNS:
            cmd = [sys.executable, os.path.join(HERE, "viewer.py")]
            if "--test" in args:
                cmd += args
            else:
                cmd += args[:2] + [out] + args[2:]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            ok = r.returncode == 0 and ("rendered" in r.stdout or "live test ok" in r.stdout)
            print(f"  {'ok ' if ok else 'BAD'}  {name}")
            if not ok:
                bad.append((name, (r.stdout + r.stderr)[-1500:]))
    for name, log in bad:
        print(f"\n--- {name} ---\n{log}")
    print("all good" if not bad else f"{len(bad)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
