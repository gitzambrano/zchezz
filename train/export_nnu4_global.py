#!/usr/bin/env python3
"""Append a GLB1 global-projection trailer to an existing NNU4 weight file.

Trailer layout, little-endian:
  magic      4 bytes  b"GLB1"
  n_features uint32   31
  hidden     uint32   48
  weights    int16    [31][48], feature-major, scale QA=255

The base NNU4 payload is copied byte-for-byte. Old loaders therefore continue to
read the file as ordinary NNU4 and ignore the trailer; the experimental runtime
uses it only when GLB1 is present and valid.
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

import numpy as np
import torch

QA = 255.0
NFEAT = 31
HIDDEN = 48


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
    w = ck["global_proj"].detach().cpu().numpy().astype(np.float64)
    if w.shape != (NFEAT, HIDDEN):
        raise SystemExit(f"bad global projection shape {w.shape}")
    q = np.rint(w * QA).clip(-32768, 32767).astype("<i2")
    trailer = struct.pack("<4sII", b"GLB1", NFEAT, HIDDEN) + q.tobytes(order="C")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_bytes(base + trailer)
    print(f"wrote {a.output} base_bytes={len(base)} trailer_bytes={len(trailer)} total={len(base)+len(trailer)}")
    print(f"feature_set={ck.get('feature_set')} best_epoch={ck.get('best_epoch')} validation={ck.get('validation')}")
    print(f"quant_nonzero={int(np.count_nonzero(q))}/{q.size} q_min={int(q.min())} q_max={int(q.max())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
