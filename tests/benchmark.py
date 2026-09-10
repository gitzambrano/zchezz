#!/usr/bin/env python3
"""Run the standard Zchezz-vs-Stockfish benchmark through the UCI runner."""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'utils'))
from engine_profiles import DEFAULT_PROFILE, profile, stockfish_executable
PROFILE=DEFAULT_PROFILE; MOVETIME_MS=200; THREADS=1; CONCURRENCY=1
def engine_exe(p):
    for name in ('zchezz.exe','zchezz'):
        x=p.engine_dir/name
        if x.is_file(): return x
    return p.engine_dir/'zchezz.exe'
def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--profile',default=PROFILE); ap.add_argument('--show-config',action='store_true'); a,rest=ap.parse_known_args(); p=profile(a.profile); sf=stockfish_executable()
    if a.show_config: print(f'profile={p.name}\nmovetime_ms={MOVETIME_MS}\nthreads={THREADS}\nconcurrency={CONCURRENCY}\nstockfish={sf or "not found"}'); return 0
    if sf is None: print('Stockfish not found. Set ZCHEZZ_STOCKFISH, install under engine/stockfish/, or put stockfish on PATH.'); return 2
    cmd=[sys.executable,'tests/run_tournament_quick.py','--engine-a',str(engine_exe(p)),'--label-a',p.name,'--engine-b',str(sf),'--label-b','Stockfish','--threads','1','--movetime','200','--concurrency','1',*rest]
    return subprocess.run(cmd,cwd=ROOT).returncode
if __name__=='__main__': raise SystemExit(main())
