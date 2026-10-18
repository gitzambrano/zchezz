#!/usr/bin/env python3
"""Fine-Tuning for Zchezz v600 with 100% Active 64-Neuron Dense Head.

Trains 20 epochs on CUDA with:
  - 2 initial epochs freezing L1 to calibrate the 64 dense neurons
  - 18 epochs end-to-end fine-tuning with CosineAnnealing down to 1e-7
  - Rich dataset mix: Lookahead quiet selfplay + Deepest Stockfish (1M, 500k, 400k, 60k, D14, synth endgames)
  - Automatic export of binary weights (verifying 64/64 active neurons in int8)
  - Automatic benchmark tournament vs v331_exp (20 games each for v600 and v601)
"""
from __future__ import annotations
import argparse
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

def refresh_latest():
    ckpt_dir = ROOT / "checkpoints" / "v600"
    pts = [x for x in ckpt_dir.glob("*.pt") if x.name != "latest.pt"]
    if not pts:
        return
    newest = max(pts, key=lambda x: x.stat().st_mtime_ns)
    latest = ckpt_dir / "latest.pt"
    tmp = latest.with_suffix(".pt.tmp")
    shutil.copy2(newest, tmp)
    tmp.replace(latest)
    print(f"Atomically refreshed {latest} from {newest.name}")

def export_and_verify_weights():
    print("\n[Export] Exporting binary weights for v600 and v601...")
    cmd = [sys.executable, str(ROOT / "train" / "export.py"), "--profile", "v600"]
    subprocess.run(cmd, cwd=str(ROOT), check=True)
    weights_path = ROOT / "engine" / "c" / "zchezz_v600" / "nnue_weights.bin"
    assert weights_path.is_file(), f"Expected binary weights at {weights_path}"
    size = weights_path.stat().st_size
    print(f"Verified v600 weights: {weights_path} ({size:,} bytes)")

    v601_weights = ROOT / "engine" / "c" / "zchezz_v601" / "nnue_weights.bin"
    shutil.copy2(weights_path, v601_weights)
    print(f"Copied weights to v601: {v601_weights} ({v601_weights.stat().st_size:,} bytes)")

    # Verify active neurons in binary file
    with open(weights_path, "rb") as f:
        magic = f.read(4)
        epoch = struct.unpack("<I", f.read(4))[0]
        l1_in, l1_out, l2_in, l2_out, l3_in = struct.unpack("<5I", f.read(20))
        qa, qb, shift, out_scale = struct.unpack("<4f", f.read(16))
        f.seek(4 + 4 + 20 + 16 + (l1_in * l1_out * 2) + (l1_out * 4))
        l2w = np.frombuffer(f.read(l2_out * l2_in), dtype=np.int8).reshape(l2_out, l2_in)
        f.seek(l2_out * 4, 1)
        l3w = np.frombuffer(f.read(l3_in), dtype=np.int8)

    active = sum(1 for i in range(64) if np.count_nonzero(l2w[i]) > 0 and l3w[i] != 0)
    print(f"\n[NEURON VERIFICATION] Confirmed active neurons in binary int8: {active} / 64 ({active/64*100:.1f}%)")

def main():
    print("=" * 80)
    print(" Zchezz v600 (NNUE5) — 64-Neuron Dense Head Calibration & Fine-Tuning")
    print("=" * 80)

    # Rich dataset mix
    parquet_datasets = [
        ("data/selfplay_lookahead_filter", 1.00, "sample-files", "selfplay_lookahead"),
        ("data/miscelaneous_cp_sf1M_res_filter", 1.00, "sample-files", "sf1M_richest"),
        ("data/lichess_cp_sf400k_filter", 1.00, "sample-files", "sf400k_richest"),
        ("data/extraquiet_cp_sf60k_filter", 1.00, "sample-files", "sf60k_richest"),
        ("data/selfplay_cp_sf50k_res_filter_data20260410", 0.20, "sample-files", "selfplay_sf50k_rich"),
        ("data/extraquiet_cp_sfd14_endgames_filter", 1.00, "sample-files", "endgames_d14_sf"),
        ("data/selfplay-lichess_cp_sf500k_res_filter_endgames", 1.00, "sample-files", "endgames_sf500k_sf"),
        ("data/synthetic_endgame_cp_sf_filter_data20260414", 1.00, "sample-files", "synth_endgames_14_sf"),
        ("data/synthetic_endgame_cp_sf_filter_data20260413", 1.00, "sample-files", "synth_endgames_13_sf"),
        ("data/selfplay_cp_sf100k_res_endgames_filter_data20260414", 0.60, "sample-files", "selfplay_sf100k_endgames"),
        ("data/extraquiet_cp_sfd12_endgames_filter", 1.00, "sample-files", "endgames_d12_sf"),
    ]

    sources = []
    for rel_path, pct, mode, name in parquet_datasets:
        full_dir = ROOT / rel_path
        if full_dir.is_dir():
            files = list(full_dir.glob("*.parquet"))
            if files:
                sources.extend([
                    "--source",
                    f"kind=parquet,path={rel_path},train_pct={pct},pct_mode={mode},name={name}",
                ])
                print(f"  [+] Source: {name:30s} ({len(files):4d} shards, pct={pct:.2f})")

    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "train" / "_train_nnu5_core.py"),
        *sources,
        "--ckpt-dir", "checkpoints/v600",
        "--checkpoint-source", "checkpoints/v600/latest.pt",
        "--dataset-name", "v600_64neurons_calibrated",
        "--epochs", "20",
        "--freeze-l1-epochs", "2",
        "--batch-size", "32768",
        "--device", "cuda",
        "--lr", "2e-5",
        "--transfer-lr", "2e-5",
        "--lr-dense", "3e-4",
        "--weight-decay", "1e-5",
        "--eta-min", "1e-7",
    ]

    print("\nStarting 20-epoch training on CUDA (2 epochs L1 freeze for dense warmup)...")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - t0

    if res.returncode != 0:
        print(f"\n[ERROR] Training failed with return code {res.returncode}")
        return res.returncode

    print(f"\n[SUCCESS] 20-Epoch calibration completed in {elapsed:.1f}s ({elapsed/60:.1f}m)!")
    refresh_latest()
    export_and_verify_weights()

    # Launch evaluation tournament vs v331_exp
    print("\n" + "#" * 80)
    print(" STARTING: Benchmark Tournament (v600 & v601 vs v331_exp)")
    print("#" * 80 + "\n")
    eval_cmd = [
        sys.executable,
        "-u",
        str(ROOT / "tests" / "check_v600_vs_331.py"),
        "--games", "10",
        "--movetime", "100",
        "--concurrency", "4",
    ]
    subprocess.run(eval_cmd, cwd=str(ROOT))
    print("\n[PIPELINE FINISHED] Calibration and Tournament complete!")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
