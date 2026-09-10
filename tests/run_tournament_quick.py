#!/usr/bin/env python3
"""Simple architecture-neutral head-to-head entrypoint.

No arguments runs a safe v325-v325 sanity match at 200 ms, Threads=1 and one
game at a time. Use tests/benchmark.py for the Stockfish benchmark.
"""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'utils'))
from engine_profiles import DEFAULT_PROFILE, profile

def _exe(p):
    for name in ('zchezz.exe','zchezz'):
        x=p.engine_dir/name
        if x.is_file(): return x
    return p.engine_dir/'zchezz.exe'

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--profile',default=DEFAULT_PROFILE); ap.add_argument('--opponent-profile',default=''); ap.add_argument('--show-config',action='store_true'); a,rest=ap.parse_known_args(); pa=profile(a.profile); pb=profile(a.opponent_profile or a.profile)
    cmd=[sys.executable,str(ROOT/'tests/_run_tournament_quick_core.py'),'--engine-a',str(_exe(pa)),'--label-a',pa.name,'--engine-b',str(_exe(pb)),'--label-b',pb.name,'--threads','1','--movetime','200','--concurrency','1']
    if a.show_config: cmd.append('--show-config')
    return subprocess.run([*cmd,*rest],cwd=ROOT).returncode
if __name__=='__main__': raise SystemExit(main())
