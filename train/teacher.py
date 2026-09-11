#!/usr/bin/env python3
"""Public architecture-neutral teaching entry point.

The implementation lives in ``train/teaching/teacher.py`` so teaching
methods, binary format, input sources, inspection, and hard-position mining
remain modular. Bare execution is supported; all defaults live in that
module's CONFIGURATION block.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from train.teaching.teacher import main


if __name__ == "__main__":
    raise SystemExit(main())
