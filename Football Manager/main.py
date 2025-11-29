#!/usr/bin/env python3
"""
Football 11v11 Simulation - Professional Structure
"""
from gameplay.match_engine import MatchEngine

def main():
    try:
        match = MatchEngine()
        match.run()
    except Exception as e:
        print(f"Error starting game: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()