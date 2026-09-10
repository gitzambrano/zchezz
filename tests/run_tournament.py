#!/usr/bin/env python3
"""Simple architecture-neutral tournament entrypoint.

The default is the same safe v325-v325 200 ms sanity configuration as the
quick runner. Optional arguments are forwarded to that runner. The legacy
multi-anchor implementation remains internal as tests/_run_tournament_core.py.
"""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__': raise SystemExit(subprocess.run([sys.executable,str(ROOT/'tests/run_tournament_quick.py'),*sys.argv[1:]],cwd=ROOT).returncode)
