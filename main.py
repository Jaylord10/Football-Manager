#!/usr/bin/env python3
"""
Football Manager - start here.

    python main.py             the manager game (career mode)
    python main.py --friendly  just the match engine: Blue v Red (match_config.json)
"""
import os
import sys


def main():
    # Run from the game's own folder, so data/ and saves/ are always found
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    try:
        if "--friendly" in sys.argv:
            from gameplay.match_engine import MatchEngine
            MatchEngine().run()
        else:
            from career.ui import main as career_main
            career_main()
    except Exception as e:
        print(f"Error starting game: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
