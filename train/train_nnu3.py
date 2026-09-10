#!/usr/bin/env python3
"""NNU3 training entrypoint. Bare execution trains the default v325 profile."""
from __future__ import annotations
import subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__': raise SystemExit(subprocess.run([sys.executable,str(ROOT/'train/run.py'),'--profile','v325',*sys.argv[1:]],cwd=ROOT).returncode)
