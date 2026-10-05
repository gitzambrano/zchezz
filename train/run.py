#!/usr/bin/env python3
"""Profile-agnostic NNUE training entrypoint. Bare run trains v325."""
from __future__ import annotations
import argparse, shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'utils'))
from engine_profiles import DEFAULT_PROFILE, profile
PROFILE=DEFAULT_PROFILE
def _bootstrap(p):
    if not p.latest_checkpoint.is_file(): subprocess.run([sys.executable,str(p.importer)],cwd=ROOT,check=True)
def _refresh_latest(p):
    pts=[x for x in p.checkpoint_dir.glob('*.pt') if x.name!='latest.pt']
    if not pts: return
    newest=max(pts,key=lambda x:x.stat().st_mtime_ns); tmp=p.latest_checkpoint.with_suffix('.pt.tmp'); shutil.copy2(newest,tmp); tmp.replace(p.latest_checkpoint)
def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--profile',default=PROFILE); ap.add_argument('--show-config',action='store_true'); a,rest=ap.parse_known_args(); p=profile(a.profile)
    if a.show_config: print(f'profile={p.name}\nformat={p.network_format}\ntrainer={p.trainer}\ncheckpoint={p.latest_checkpoint}'); return 0
    _bootstrap(p); cmd=[sys.executable,str(p.trainer),'--checkpoint-source',str(p.latest_checkpoint),'--ckpt-dir',str(p.checkpoint_dir),*rest]; rc=subprocess.run(cmd,cwd=ROOT).returncode
    if rc==0: _refresh_latest(p)
    return rc
if __name__=='__main__': raise SystemExit(main())
