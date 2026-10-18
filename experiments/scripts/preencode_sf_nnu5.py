#!/usr/bin/env python3
"""Pre-encode top Stockfish teaching datasets for NNU5 (HalfKAv2 32-Bucket).

Reads parquet files from the top Stockfish teaching directories, runs
encode_positions (yielding full 22,528 HalfKAv2 features), and saves
them with '_encoded_nnu5.pt' suffix and 'encoding': 'halfka_v2_hm_32b'.
"""
from __future__ import annotations
import glob
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "train"))

from _train_nnu5_core import _build_parquet_file_cache, _source_stamp, SourceSpec

TARGET_DIRS = [
    "data/extraquiet_cp_sf60k_filter",
    "data/extraquiet_cp_sfd14_endgames_filter",
    "data/selfplay-lichess_cp_sf500k_res_filter_endgames",
    "data/synthetic_endgame_cp_sf_filter_data20260414",
    "data/synthetic_endgame_cp_sf_filter_data20260413",
    "data/extraquiet_cp_sfd12_endgames_filter",
    "data/lichess_cp_sf400k_filter",
    "data/miscelaneous_cp_sf1M_res_filter",
]

def encode_one_parquet(args):
    fpath, chunk_rows = args
    import torch
    target_cache = fpath.replace(".parquet", "_encoded_nnu5.pt")
    if os.path.exists(target_cache):
        try:
            d = torch.load(target_cache, map_location="cpu", weights_only=False)
            if d.get("encoding") == "halfka_v2_hm_32b" and int(d["stm_idx"].max()) > 10000:
                return fpath, True, "already exists"
        except Exception:
            pass

    src = SourceSpec(kind="parquet", path=os.path.dirname(fpath), name=os.path.basename(os.path.dirname(fpath)))
    try:
        t0 = time.time()
        # Single-process per file inside worker
        data = _build_parquet_file_cache(fpath, src, chunk_rows, pool=None, n_workers=1)
        data["src_stamp"] = _source_stamp(fpath)
        data["encoding"] = "halfka_v2_hm_32b"
        torch.save(data, target_cache)
        elapsed = time.time() - t0
        return fpath, True, f"{elapsed:.1f}s, {data['n_rows']} rows, max_idx={data['stm_idx'].max()}"
    except Exception as e:
        return fpath, False, str(e)

def main():
    all_files = []
    for rel in TARGET_DIRS:
        d = ROOT / rel
        if d.is_dir():
            files = sorted(d.glob("*.parquet"))
            all_files.extend([str(f) for f in files])

    print(f"Found {len(all_files)} target Stockfish parquet files across {len(TARGET_DIRS)} directories.")
    
    # Filter out already done
    pending = [f for f in all_files if not os.path.exists(f.replace(".parquet", "_encoded_nnu5.pt"))]
    print(f"{len(all_files) - len(pending)} already encoded. {len(pending)} pending encoding.")
    if not pending:
        print("All files already encoded!")
        return

    t0 = time.time()
    completed = 0
    # Use 3 workers so we leave CPU headroom for the ongoing Stockfish benchmark
    with mp.Pool(processes=3) as pool:
        for fpath, ok, msg in pool.imap_unordered(encode_one_parquet, [(f, 200_000) for f in pending]):
            completed += 1
            status = "OK" if ok else "FAIL"
            if completed % 10 == 0 or completed == len(pending):
                elapsed = time.time() - t0
                rate = completed / max(1.0, elapsed)
                rem = (len(pending) - completed) / max(0.01, rate)
                print(f"  [{completed:3d}/{len(pending):3d}] {Path(fpath).name}: {status} ({msg}) | {rate:.2f} files/s | ETA {rem/60:.1f}m")

    total_time = time.time() - t0
    print(f"\nFinished pre-encoding {completed} files in {total_time:.1f}s ({total_time/60:.1f}m)!")

if __name__ == "__main__":
    main()
