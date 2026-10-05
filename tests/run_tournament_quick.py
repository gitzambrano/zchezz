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
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--profile',default=DEFAULT_PROFILE); ap.add_argument('--opponent-profile',default=''); ap.add_argument('--show-config',action='store_true'); a,rest=ap.parse_known_args(); pa=profile(a.profile); pb=profile(a.opponent_profile or a.profile); ea,eb=_exe(pa),_exe(pb)
    if a.show_config:
        print(f'profile={pa.name}\nopponent_profile={pb.name}\nengine_a={ea}\nengine_b={eb}\nmovetime_ms=200\nthreads=1\nconcurrency=1'); return 0
    return subprocess.run([sys.executable,str(ROOT/'tests/_run_tournament_quick_core.py'),'--engine-a',str(ea),'--label-a',pa.name,'--engine-b',str(eb),'--label-b',pb.name,'--threads','1','--movetime','200','--concurrency','1',*rest],cwd=ROOT).returncode
if __name__=='__main__': raise SystemExit(main())
