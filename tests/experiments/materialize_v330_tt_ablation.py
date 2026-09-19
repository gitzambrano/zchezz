#!/usr/bin/env python3
"""Materialize TT structure ablations from immutable v3.30."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from materialize_v330_tt32 import SRC, patch_tt32_key

VARIANTS = ("key32cl64", "key16cl64")


def replace_exact(s: str, old: str, new: str, expected: int = 1) -> str:
    n = s.count(old)
    if n != expected:
        raise RuntimeError(f"expected {expected} occurrences, found {n}: {old!r}")
    return s.replace(old, new)


def patch_key16_cl64(s: str) -> str:
    old = """typedef struct __attribute__((aligned(32))) {
    TTEntry10 e[3];
    uint8_t pad[2];
} TTCluster32;

typedef char tt_entry_must_be_10[(sizeof(TTEntry10)==10)?1:-1];
typedef char tt_cluster_must_be_32[(sizeof(TTCluster32)==32)?1:-1];
"""
    new = """typedef struct __attribute__((aligned(64))) {
    TTEntry10 e[6];
    uint8_t pad[4];
} TTCluster64K16;

typedef char tt_entry_must_be_10[(sizeof(TTEntry10)==10)?1:-1];
typedef char tt_cluster_must_be_64_k16[(sizeof(TTCluster64K16)==64)?1:-1];
"""
    s = replace_exact(s, old, new)
    s = s.replace("TTCluster32", "TTCluster64K16")
    s = s.replace("g_tt_clusters * 3", "g_tt_clusters * 6")
    s = s.replace("clusters*3", "clusters*6")
    s = s.replace("for (int i=0; i<3; ++i)", "for (int i=0; i<6; ++i)")
    s = s.replace("for (int i=1; i<3; ++i)", "for (int i=1; i<6; ++i)")
    s = s.replace("tt_aligned_alloc(32, bytes)", "tt_aligned_alloc(64, bytes)")
    s = replace_exact(
        s,
        'fprintf(stderr, "[TT] sf32: requested=%d MB actual=%.1f MB clusters=%zu entries=%zu entry=10B cluster=32B\\n",',
        'fprintf(stderr, "[TT] sf64-key16: requested=%d MB actual=%.1f MB clusters=%zu entries=%zu entry=10B cluster=64B\\n",'
    )
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=VARIANTS, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SRC, out)
    p = out / "search.c"
    s = p.read_text(encoding="utf-8")
    if args.variant == "key32cl64":
        s = patch_tt32_key(s)
    else:
        s = patch_key16_cl64(s)
    p.write_text(s, encoding="utf-8")
    print(f"materialized {args.variant}: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
