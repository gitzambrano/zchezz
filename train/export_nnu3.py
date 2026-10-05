#!/usr/bin/env python3
"""NNU3 export entrypoint. Bare execution exports the default v325 checkpoint."""
from __future__ import annotations
try:
    from ._export_nnu3_core import *  # noqa: F401,F403
except ImportError:
    from _export_nnu3_core import *  # type: ignore # noqa: F401,F403
if __name__=='__main__':
    import subprocess,sys
    from pathlib import Path
    ROOT=Path(__file__).resolve().parents[1]
    raise SystemExit(subprocess.run([sys.executable,str(ROOT/'train/export.py'),'--profile','v325',*sys.argv[1:]],cwd=ROOT).returncode)
