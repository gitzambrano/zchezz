#!/usr/bin/env python3
"""Simple architecture-neutral self-play entrypoint.

No arguments uses v325 at 200 ms with one game at a time. Extra arguments are
forwarded to the internal mature runner only as optional overrides.
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
    ap=argparse.ArgumentParser(description=__doc__,add_help=True); ap.add_argument('--profile',default=DEFAULT_PROFILE); ap.add_argument('--show-config',action='store_true'); a,rest=ap.parse_known_args(); p=profile(a.profile)
    cmd=[sys.executable,str(ROOT/'tests/_run_selfplay_core.py'),'--engine',str(_exe(p)),'--engine-label',p.name,'--movetime','200','--concurrency','1']
    if a.show_config: cmd.append('--show-config')
    return subprocess.run([*cmd,*rest],cwd=ROOT).returncode
if __name__=='__main__': raise SystemExit(main())
