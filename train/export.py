#!/usr/bin/env python3
"""Profile-agnostic NNUE export entrypoint. Bare run exports v325."""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'utils'))
from engine_profiles import DEFAULT_PROFILE, profile
PROFILE=DEFAULT_PROFILE
def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--profile',default=PROFILE); ap.add_argument('--show-config',action='store_true'); a,rest=ap.parse_known_args(); p=profile(a.profile)
    if a.show_config: print(f'profile={p.name}\nexporter={p.exporter}\ncheckpoint={p.latest_checkpoint}'); return 0
    return subprocess.run([sys.executable,str(p.exporter),'--checkpoint',str(p.latest_checkpoint),*rest],cwd=ROOT).returncode
if __name__=='__main__': raise SystemExit(main())
