#!/usr/bin/env python3
"""Stage 1: Foundation Pre-Training / Warmup for Zchezz v600 (NNUE5 - HalfKAv2 32-Bucket).

Trains 120 epochs starting with high learning rate across the massive general dataset corpus
(hundreds of millions of positions), with heavy weighting for top-tier Stockfish teaching:
  - Broad general datasets: sf5k, sfdb, sf_filter, sf50k (x2), zchezz selfplay (x2), v507, v331
    (resampled every epoch to cover the entire multi-hundred-million position pool)
  - Heavily weighted Stockfish teaching: SF 60k, Endgames D14, SF 500k, Synth endgames (all 2x passes),
    SF 100k endgames, D12 endgames, SF 400k, SF 1M
  - Learning Rate: starts high (lr=3e-4, lr-dense=1e-3) and smoothly decays to eta-min=1e-6 via CosineAnnealing.
"""
from __future__ import annotations
import argparse
import glob
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

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

def export_weights():
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

def parse_args():
    parser = argparse.ArgumentParser(description="Zchezz v600 Stage 1 Foundation Warmup Training")
    parser.add_argument("--epochs", type=int, default=120, help="Number of training epochs (default: 120)")
    parser.add_argument("--batch-size", type=int, default=262144, help="Minibatch size (default: 262144)")
    parser.add_argument("--freeze-l1-epochs", type=int, default=2, help="Epochs to freeze L1 (default: 2)")
    parser.add_argument("--lr", type=float, default=3e-4, help="Learning rate for L1 features (default: 3e-4)")
    parser.add_argument("--lr-dense", type=float, default=1e-3, help="Learning rate for L2/L3 dense head (default: 1e-3)")
    parser.add_argument("--eta-min", type=float, default=1e-6, help="Minimum learning rate (default: 1e-6)")
    parser.add_argument("--checkpoint", type=str, default="checkpoints/v600/latest.pt", help="Checkpoint to resume")
    parser.add_argument("--dataset-name", type=str, default="v600_foundation_120ep", help="Dataset name tag")
    return parser.parse_args()

def main():
    args = parse_args()

    print("=" * 80)
    print(" Zchezz v600 (NNUE5) — Stage 1 Foundation Warmup (120 Epochs)")
    print(f" Config: LR_L1={args.lr:.1e}, LR_Dense={args.lr_dense:.1e} -> eta_min={args.eta_min:.1e}, Batch={args.batch_size}")
    print("=" * 80)

    # Dataset specification:
    # 1. Broad general corpora (sampled with sample-files and resample_each_epoch=True)
    # 2. Heavily weighted Stockfish teaching (100% and 2x passes for top-tier teaching)
    # Clean massive general warmup selfplay (pre-encoded HalfKAv2 32-bucket):
    datasets = [
        ("data/selfplay_v507_filter", 0.40, "sample-files", "v507_selfplay"),
        ("data/selfplay_v331_filter", 1.00, "sample-files", "v331_selfplay"),
        ("data/selfplay_lookahead_filter", 1.00, "sample-files", "selfplay_lookahead"),
        # Top-tier Stockfish teaching (pre-encoded HalfKAv2 32-bucket, heavily weighted 2x passes):
        ("data/extraquiet_cp_sf60k_filter", 1.00, "sample-files", "sf60k_pass1"),
        ("data/extraquiet_cp_sf60k_filter", 1.00, "sample-files", "sf60k_pass2"),
        ("data/extraquiet_cp_sfd14_endgames_filter", 1.00, "sample-files", "endgames_d14_pass1"),
        ("data/extraquiet_cp_sfd14_endgames_filter", 1.00, "sample-files", "endgames_d14_pass2"),
        ("data/selfplay-lichess_cp_sf500k_res_filter_endgames", 1.00, "sample-files", "endgames_sf500k_pass1"),
        ("data/selfplay-lichess_cp_sf500k_res_filter_endgames", 1.00, "sample-files", "endgames_sf500k_pass2"),
        ("data/synthetic_endgame_cp_sf_filter_data20260414", 1.00, "sample-files", "synth_endgames_14_pass1"),
        ("data/synthetic_endgame_cp_sf_filter_data20260414", 1.00, "sample-files", "synth_endgames_14_pass2"),
        ("data/synthetic_endgame_cp_sf_filter_data20260413", 1.00, "sample-files", "synth_endgames_13"),
        ("data/extraquiet_cp_sfd12_endgames_filter", 1.00, "sample-files", "endgames_d12"),
        ("data/lichess_cp_sf400k_filter", 1.00, "sample-files", "sf400k"),
        ("data/miscelaneous_cp_sf1M_res_filter", 1.00, "sample-files", "sf1M"),
    ]

    sources = []
    for rel_path, pct, mode, name in datasets:
        full_dir = ROOT / rel_path
        if full_dir.is_dir():
            parquet_files = list(full_dir.glob("*.parquet"))
            if parquet_files:
                sources.extend([
                    "--source",
                    f"kind=parquet,path={rel_path},train_pct={pct},pct_mode={mode},name={name}",
                ])
                print(f"  [+] Included source: {name:28s} ({len(parquet_files):4d} shards, pct={pct:.2f})")
            else:
                print(f"  [-] Skipped (no parquets): {name}")
        else:
            print(f"  [-] Skipped (directory missing): {name}")

    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "train" / "_train_nnu5_core.py"),
        *sources,
        "--ckpt-dir", "checkpoints/v600",
        "--checkpoint-source", str(args.checkpoint),
        "--dataset-name", str(args.dataset_name),
        "--epochs", str(args.epochs),
        "--batch-size", str(args.batch_size),
        "--max-positions-chunk", "250000",
        "--parquet-chunk-rows", "100000",
        "--device", "cuda",
        "--lr", str(args.lr),
        "--transfer-lr", str(args.lr),
        "--lr-dense", str(args.lr_dense),
        "--freeze-l1-epochs", str(args.freeze_l1_epochs),
        "--eta-min", str(args.eta_min),
    ]

    print(f"\nStarting {args.epochs}-epoch Stage 1 foundation training on CUDA...")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - t0

    if res.returncode != 0:
        print(f"\n[ERROR] Training failed with return code {res.returncode}")
        return res.returncode

    print(f"\n[SUCCESS] {args.epochs}-Epoch foundation training completed in {elapsed:.1f}s ({elapsed/3600:.2f}h)!")
    refresh_latest()
    export_weights()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
