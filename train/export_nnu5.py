#!/usr/bin/env python3
"""Export a v600 HalfKAv2_hm-32Bucket checkpoint to NNU5."""
from __future__ import annotations
import argparse, struct
from pathlib import Path
import numpy as np, torch

ROOT = Path(__file__).resolve().parents[1]
L1_IN = 22528; L1_OUT = 64; L2_IN = 128; L2_OUT = 16; L3_IN = 16
QA = 255.0; QB = 64.0; SHIFT = 8.0; QA_EFF = 254.0; OUT_SCALE = 320.0 / (QB * QB)
EXPECTED_SIZE = 4 + 4 + 20 + 16 + (L1_IN * L1_OUT * 2) + (L1_OUT * 4) + (L2_OUT * L2_IN) + (L2_OUT * 4) + L3_IN + 4
assert EXPECTED_SIZE == 2_886_016

DEFAULT_CKPT = ROOT / 'checkpoints/v600/latest.pt'
DEFAULT_DST = ROOT / 'engine/c/zchezz_v600/nnue_weights.bin'


def _q(a, scale, limit, dtype, name):
    q = np.rint(a * scale)
    n = int((np.abs(q) > limit).sum())
    if n:
        print(f'WARNING: clipping {n} {name} values')
    return np.clip(q, -limit, limit).astype(dtype)


def convert(ckpt_path: Path, dst: Path):
    ckpt = torch.load(ckpt_path, map_location='cpu', weights_only=False)
    arch = ckpt.get('arch', {})
    expected = {'input': L1_IN, 'h1': L1_OUT, 'concat': L2_IN, 'h2': L2_OUT, 'encoding': 'halfka_v2_hm_32b'}
    for k, v in expected.items():
        if arch.get(k) != v:
            raise ValueError(f'incompatible checkpoint {k}={arch.get(k)!r}, expected {v!r}')
    w = ckpt.get('weights', ckpt)
    arr = lambda k: w[k].detach().cpu().numpy().astype(np.float32)
    l1w = arr('l1.weight')
    l1b = arr('l1_bias')
    l2w = arr('l2.weight')
    l2b = arr('l2.bias')
    l3w = arr('l3.weight')
    l3b = arr('l3.bias')

    if (l1w.shape != (L1_IN, L1_OUT) or l1b.shape != (L1_OUT,) or
            l2w.shape != (L2_OUT, L2_IN) or l2b.shape != (L2_OUT,) or
            l3w.reshape(-1).shape != (L3_IN,)):
        raise ValueError('checkpoint tensor shape mismatch')

    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open('wb') as f:
        f.write(b'NNU5')
        f.write(struct.pack('<I', int(ckpt.get('epoch', 0))))
        f.write(struct.pack('<5I', L1_IN, L1_OUT, L2_IN, L2_OUT, L3_IN))
        f.write(struct.pack('<4f', QA, QB, SHIFT, OUT_SCALE))
        f.write(np.ascontiguousarray(_q(l1w, QA, 32767, '<i2', 'L1W')).tobytes())
        f.write(np.rint(l1b * QA).astype('<i4').tobytes())
        f.write(np.ascontiguousarray(_q(l2w, QB, 127, 'i1', 'L2W')).tobytes())
        f.write(np.rint(l2b * QA_EFF * QB).astype('<i4').tobytes())
        f.write(_q(l3w.reshape(-1), QB, 127, 'i1', 'L3W').tobytes())
        f.write(struct.pack('<f', float(l3b.reshape(-1)[0])))

    if dst.stat().st_size != EXPECTED_SIZE:
        dst.unlink(missing_ok=True)
        raise ValueError(f'NNU5 size mismatch: got {dst.stat().st_size}, expected {EXPECTED_SIZE}')
    print(f'NNU5 export: {ckpt_path} -> {dst} ({EXPECTED_SIZE} bytes)')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint', type=Path, default=DEFAULT_CKPT)
    p.add_argument('--output', type=Path, default=DEFAULT_DST)
    a = p.parse_args()
    convert(a.checkpoint, a.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
