#!/usr/bin/env python3
"""Append a GLB2 global-to-L2 side-channel trailer to an NNU4 file.

Trailer, little-endian:
  magic      4 bytes  b"GLB2"
  n_features uint32   31
  hidden     uint32   20
  weights    int8     [31][20], feature-major, scale QB=64

The NNU4 base payload is copied byte-for-byte. Feature row 13 (constant bias)
is expected to stay zero in the causal information-only experiments.
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

import numpy as np
import torch

QB = 64.0
NFEAT = 31
HIDDEN = 20


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    base = a.base.read_bytes()
    if base[:4] != b"NNU4":
        raise SystemExit("base is not NNU4")
    ck = torch.load(a.checkpoint, map_location="cpu", weights_only=False)
    w = ck["global_l2"].detach().cpu().numpy().astype(np.float64)
    if w.shape != (NFEAT, HIDDEN):
        raise SystemExit(f"bad global L2 shape {w.shape}")
    q = np.rint(w * QB).clip(-128, 127).astype(np.int8)
    trailer = struct.pack("<4sII", b"GLB2", NFEAT, HIDDEN) + q.tobytes(order="C")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_bytes(base + trailer)
    print(f"wrote {a.output} base_bytes={len(base)} trailer_bytes={len(trailer)} total={len(base)+len(trailer)}")
    print(f"feature_set={ck.get('feature_set')} best_epoch={ck.get('best_epoch')} validation={ck.get('validation')}")
    print(f"quant_nonzero={int(np.count_nonzero(q))}/{q.size} q_min={int(q.min())} q_max={int(q.max())} constant_row_nonzero={int(np.count_nonzero(q[13]))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
