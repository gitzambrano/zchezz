#!/usr/bin/env python3
"""Run the global-projection trainer using only genuinely informative features.

v3.28 feature 13 is a constant 1.0 and therefore acts as an extra trainable
bias, not additional chess information. Excluding it makes the experiment
causal: all=30 informative features, aggregate=13 count/material features,
relational=17 passed-pawn/king-geometry features.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from train.teaching import train_global_projection_nnu4 as impl  # noqa: E402

impl.FEATURE_SETS = {
    "all": [i for i in range(31) if i != 13],
    "aggregate": list(range(13)),
    "relational": list(range(14, 31)),
}

if __name__ == "__main__":
    raise SystemExit(impl.main())
