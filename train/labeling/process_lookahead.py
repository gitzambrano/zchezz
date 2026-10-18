#!/usr/bin/env python3
"""Process self-play .bin shards into Parquet with dense temporal lookahead targets.

Formula:
  Target(t) = 0.60 * sigmoid(cp_t / 320)
            + 0.20 * sigmoid(cp_{t+2} / 320)
            + 0.10 * sigmoid(cp_{t+4} / 320)
            + 0.10 * result_prob

Followed by quiet position filtering (checks, winning/equal captures, terminal states).
"""
import glob
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path
import chess
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from train.dataset import SAMPLE_DTYPE, read_bin_header
from train.labeling.process_positions import bin_record_to_fen, is_quiet_advanced

SIG_T = 320.0
W_0, W_2, W_4, W_Z = 0.60, 0.20, 0.10, 0.10


def sig(cp: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(cp, -30000, 30000) / SIG_T))


def inv_sig(p: np.ndarray) -> np.ndarray:
    p_clamped = np.clip(p, 1e-6, 1.0 - 1e-6)
    return SIG_T * np.log(p_clamped / (1.0 - p_clamped))


def process_shard(args: tuple) -> tuple[int, int, str]:
    bin_path, out_dir, shard_id = args
    if not os.path.exists(bin_path) or os.path.getsize(bin_path) == 0:
        return 0, 0, ""

    hdr_offset, _ = read_bin_header(bin_path)
    data_size = os.path.getsize(bin_path) - hdr_offset
    if data_size % SAMPLE_DTYPE.itemsize != 0:
        return 0, 0, ""

    arr = np.memmap(bin_path, dtype=SAMPLE_DTYPE, mode="r", offset=hdr_offset)
    n_records = len(arr)
    if n_records == 0:
        return 0, 0, ""

    # Detect game boundaries (stm doesn't alternate, or rule50 reset on white)
    stms = arr["stm"]
    r50s = arr["rule50"]
    game_starts = [0]
    for i in range(n_records - 1):
        if stms[i + 1] == stms[i] or (r50s[i + 1] == 0 and stms[i + 1] == 0 and r50s[i] > 5):
            game_starts.append(i + 1)
    game_starts.append(n_records)

    surviving_fens = []
    surviving_cps = []
    surviving_results = []

    for g_idx in range(len(game_starts) - 1):
        start = game_starts[g_idx]
        end = game_starts[g_idx + 1]
        g_len = end - start
        if g_len < 2:
            continue

        g_cp = arr["eval_cp"][start:end].astype(np.float64)
        g_res = arr["game_result"][start:end].astype(np.float64)
        g_stm = arr["stm"][start:end]

        res_prob = (g_res + 1.0) / 2.0
        v_0 = sig(g_cp)

        # v_2: 2 plies ahead (same color)
        v_2 = np.empty_like(v_0)
        if g_len > 2:
            v_2[:-2] = v_0[2:]
            v_2[-2:] = res_prob[-2:]
        else:
            v_2[:] = res_prob[:]

        # v_4: 4 plies ahead (same color)
        v_4 = np.empty_like(v_0)
        if g_len > 4:
            v_4[:-4] = v_0[4:]
            v_4[-4:] = res_prob[-4:]
        else:
            v_4[:] = res_prob[:]

        target_prob = W_0 * v_0 + W_2 * v_2 + W_4 * v_4 + W_Z * res_prob
        cp_stm = inv_sig(target_prob)
        # Convert to White-relative
        cp_white = np.where(g_stm == 0, cp_stm, -cp_stm)

        for i in range(g_len):
            raw = arr[start + i]
            try:
                fen = bin_record_to_fen(raw)
                board = chess.Board(fen)
                quiet, _ = is_quiet_advanced(board)
                if quiet:
                    surviving_fens.append(fen)
                    surviving_cps.append(float(cp_white[i]))
                    gr = int(raw["game_result"])
                    if gr > 0:
                        r_str = "1-0" if raw["stm"] == 0 else "0-1"
                    elif gr < 0:
                        r_str = "0-1" if raw["stm"] == 0 else "1-0"
                    else:
                        r_str = "1/2-1/2"
                    surviving_results.append(r_str)
            except Exception:
                continue

    del arr

    if not surviving_fens:
        return n_records, 0, ""

    out_path = os.path.join(out_dir, f"chunk_{shard_id:05d}.parquet")
    df = pd.DataFrame({
        "fen": surviving_fens,
        "cp": surviving_cps,
        "result": surviving_results,
    })
    table = pa.Table.from_pandas(df)
    pq.write_table(table, out_path, compression="zstd")
    return n_records, len(surviving_fens), out_path


def main():
    out_dir = str(ROOT / "data" / "selfplay_lookahead_filter")
    os.makedirs(out_dir, exist_ok=True)

    all_bins = sorted(glob.glob(str(ROOT / "data" / "selfplay_v331" / "*.bin")))
    all_bins += sorted(glob.glob(str(ROOT / "data" / "selfplay_v507" / "*.bin")))

    print(f"Total .bin shards to process: {len(all_bins)}")
    print(f"Output directory: {out_dir}")
    print(f"Weights: W_0={W_0}, W_2={W_2}, W_4={W_4}, W_Z={W_Z}")

    tasks = [(p, out_dir, i) for i, p in enumerate(all_bins)]

    n_workers = min(14, max(1, os.cpu_count() - 2))
    print(f"Processing on {n_workers} CPU workers...")

    t0 = time.time()
    total_read = 0
    total_quiet = 0
    with mp.Pool(n_workers) as pool:
        for i, (n_in, n_out, path) in enumerate(pool.imap_unordered(process_shard, tasks, chunksize=1)):
            total_read += n_in
            total_quiet += n_out
            if (i + 1) % 10 == 0 or (i + 1) == len(tasks):
                elapsed = time.time() - t0
                pct = (i + 1) / len(tasks) * 100
                print(f"[{i+1}/{len(tasks)} - {pct:.1f}%] Read: {total_read:,} | Quiet Lookahead: {total_quiet:,} ({total_quiet/max(1,total_read):.1%}) | {elapsed:.1f}s")

    print(f"\nDone! Extracted {total_quiet:,} quiet positions with lookahead targets in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
