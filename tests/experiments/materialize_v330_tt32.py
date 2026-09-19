#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "engine" / "c" / "zchezz_v330"


def req(text: str, old: str, new: str, count: int = 1) -> str:
    found = text.count(old)
    if found < count:
        raise RuntimeError(f"expected at least {count} occurrence(s), found {found}: {old[:120]!r}")
    return text.replace(old, new, count)


def patch_tt32_key(text: str) -> str:
    old = """typedef struct {
    uint16_t key16;
    uint8_t  depth8;      /* stored depth + 1; zero means empty */
    uint8_t  genBound8;   /* generation[4:0], bound[6:5] */
    uint16_t move16;
    int16_t  score16;
    int16_t  eval16;
} TTEntry10;

typedef struct __attribute__((aligned(32))) {
    TTEntry10 e[3];
    uint8_t pad[2];
} TTCluster32;

typedef char tt_entry_must_be_10[(sizeof(TTEntry10)==10)?1:-1];
typedef char tt_cluster_must_be_32[(sizeof(TTCluster32)==32)?1:-1];
"""
    new = """typedef struct {
    uint32_t key32;
    uint8_t  depth8;      /* stored depth + 1; zero means empty */
    uint8_t  genBound8;   /* generation[4:0], bound[6:5] */
    uint16_t move16;
    int16_t  score16;
    int16_t  eval16;
} TTEntry12;

typedef struct __attribute__((aligned(64))) {
    TTEntry12 e[5];
    uint8_t pad[4];
} TTCluster64;

typedef char tt_entry_must_be_12[(sizeof(TTEntry12)==12)?1:-1];
typedef char tt_cluster_must_be_64[(sizeof(TTCluster64)==64)?1:-1];
"""
    text = req(text, old, new)
    text = text.replace("TTCluster32", "TTCluster64")
    text = text.replace("TTEntry10", "TTEntry12")
    text = req(text,
        "static inline uint16_t tt_key16(uint64_t h) { return (uint16_t)h; }",
        "static inline uint32_t tt_key32(uint64_t h) { return (uint32_t)h; }")
    text = text.replace("tt_key16", "tt_key32")
    text = text.replace("key16", "key32")
    text = text.replace("uint16_t key = tt_key32(hash);", "uint32_t key = tt_key32(hash);")
    text = text.replace("g_tt_clusters * 3", "g_tt_clusters * 5")
    text = text.replace("clusters*3", "clusters*5")
    text = text.replace("for (int i=0; i<3; ++i)", "for (int i=0; i<5; ++i)")
    text = text.replace("for (int i=1; i<3; ++i)", "for (int i=1; i<5; ++i)")
    text = text.replace("tt_aligned_alloc(32, bytes)", "tt_aligned_alloc(64, bytes)")
    text = req(text,
        'fprintf(stderr, "[TT] sf32: requested=%d MB actual=%.1f MB clusters=%zu entries=%zu entry=10B cluster=32B\\n",',
        'fprintf(stderr, "[TT] sf64-key32: requested=%d MB actual=%.1f MB clusters=%zu entries=%zu entry=12B cluster=64B\\n",')
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SRC, out)
    p = out / "search.c"
    p.write_text(patch_tt32_key(p.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"materialized TT32-key candidate at {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
