#!/usr/bin/env python3
"""Shared training API plus safe default training entrypoint.

Importing this module exposes the complete NNU4 data/source infrastructure,
including the private parsing helpers consumed by the NNU3 implementation.
Executing it directly follows the repository default and trains v325. Select
v500 explicitly with ``python train/run.py --profile v500``.
"""
from __future__ import annotations
import importlib
_core = importlib.import_module(f"{__package__}._train_nnu4_core" if __package__ else "_train_nnu4_core")
for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)
if __name__ == "__main__":
    import subprocess, sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[1]
    raise SystemExit(subprocess.run([sys.executable, str(ROOT / "train/run.py"), *sys.argv[1:]], cwd=ROOT).returncode)
