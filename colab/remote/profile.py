"""Resolve a remote runner profile through the repository interface."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.engine_profiles import normalize_profile

CONFIG = {"profile": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", nargs="?", default=CONFIG["profile"])
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()
    print(normalize_profile(args.profile or None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
