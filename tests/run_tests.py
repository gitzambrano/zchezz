#!/usr/bin/env python3
"""Canonical local test entrypoint. Bare execution tests v325 smoke only."""
from __future__ import annotations
import importlib
_core=importlib.import_module(f"{__package__}._run_tests_core" if __package__ else "_run_tests_core")
for _name in dir(_core):
    if not _name.startswith("__"): globals()[_name]=getattr(_core,_name)
if __name__=='__main__':
    import subprocess,sys
    from pathlib import Path
    ROOT=Path(__file__).resolve().parents[1]
    argv=[sys.executable,str(ROOT/'tests/_run_tests_core.py')]
    if '--baseline' not in sys.argv[1:]: argv += ['--baseline','v325']
    argv += sys.argv[1:]
    raise SystemExit(subprocess.run(argv,cwd=ROOT).returncode)
