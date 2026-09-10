#!/usr/bin/env python3
"""Architecture-neutral tournament entrypoint.

No arguments run the safe v325-v325 200 ms configuration. Optional arguments
are forwarded to the quick UCI tournament runner. Use tests/benchmark.py for
Zchezz-vs-Stockfish benchmarking.
"""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    raise SystemExit(subprocess.run(
        [sys.executable, str(ROOT / "tests/run_tournament_quick.py"), *sys.argv[1:]],
        cwd=ROOT,
    ).returncode)
