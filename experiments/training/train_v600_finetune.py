#!/usr/bin/env python3
"""Stage 2: Fine-Tuning for Zchezz v600 (NNUE5 - HalfKAv2 32-Bucket).

Refines the 120-epoch foundation model using a balanced mix:
  1. Dense multi-horizon lookahead quiet selfplay:
     - data/selfplay_lookahead_filter (target = 0.60*v0 + 0.20*v2 + 0.10*v4 + 0.10*result)
  2. Richest Stockfish evaluations and tactical/strategic anchors:
     - SF 1M nodes (highest search budget in repository)
     - SF 400k nodes
     - SF 60k nodes extra-quiet complex positions
     - SF 50k nodes deep-search selfplay positions
  3. Richest Stockfish endgame anchors:
     - SF Depth 14 endgames (2.8M positions)
     - SF 500k nodes endgames (2.7M positions)
     - Synthetic endgames (1.7M positions)
     - SF 100k nodes endgames (3.4M positions)
     - SF Depth 12 endgames (0.26M positions)

Learning Rate: low fine-tuning rate (lr=1e-5, lr-dense=5e-5) decaying to eta-min=1e-7 over 50 epochs.
Resumes directly from Stage 1 foundation checkpoint: checkpoints/v600/latest.pt.
"""
from __future__ import annotations
import argparse
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
    parser = argparse.ArgumentParser(description="Zchezz v600 Stage 2 Fine-Tuning")
    parser.add_argument("--epochs", type=int, default=50, help="Number of fine-tuning epochs (default: 50)")
    parser.add_argument("--batch-size", type=int, default=262144, help="Minibatch size (default: 262144)")
    parser.add_argument("--lr", type=float, default=1e-5, help="Learning rate for L1 features (default: 1e-5)")
    parser.add_argument("--lr-dense", type=float, default=5e-5, help="Learning rate for dense head (default: 5e-5)")
    parser.add_argument("--eta-min", type=float, default=1e-7, help="Minimum learning rate (default: 1e-7)")
    parser.add_argument("--checkpoint", type=str, default="checkpoints/v600/latest.pt", help="Checkpoint to resume")
    parser.add_argument("--dataset-name", type=str, default="v600_stage2_finetune_50ep", help="Dataset name tag")
    return parser.parse_args()

def main():
    args = parse_args()

    print("=" * 80)
    print(f" Zchezz v600 (NNUE5) — Stage 2 Fine-Tuning ({args.epochs} Epochs)")
    print(" Mix: Dense Lookahead Selfplay + Richest Stockfish Teaching (1M, 500k, 400k, 60k, D14, Endgames)")
    print(f" Config: LR_L1={args.lr:.1e}, LR_Dense={args.lr_dense:.1e} -> eta_min={args.eta_min:.1e}, Batch={args.batch_size}")
    print("=" * 80)

    ckpt_path = ROOT / args.checkpoint
    if not ckpt_path.is_file():
        print(f"[ERROR] Checkpoint not found: {ckpt_path}")
        print("Please ensure Stage 1 foundation training has completed.")
        return 1

    # Stage 2 datasets: 5:1 Ratio (5 parts Dense Lookahead Selfplay : 1 part Stockfish Teachers for anti-forgetting)
    parquet_datasets = [
        # 1. Specialized Dense Lookahead Selfplay (Weight 5x): 5 distinct random file passes per epoch
        ("data/selfplay_lookahead_filter", 0.40, "sample-files", "selfplay_lookahead_p1"),
        ("data/selfplay_lookahead_filter", 0.40, "sample-files", "selfplay_lookahead_p2"),
        ("data/selfplay_lookahead_filter", 0.40, "sample-files", "selfplay_lookahead_p3"),
        ("data/selfplay_lookahead_filter", 0.40, "sample-files", "selfplay_lookahead_p4"),
        ("data/selfplay_lookahead_filter", 0.40, "sample-files", "selfplay_lookahead_p5"),

        # 2. Richest Stockfish Middlegame & Complex Positions (Weight 1x - Anti-Forgetting Anchor):
        ("data/miscelaneous_cp_sf1M_res_filter", 0.35, "sample-files", "sf1M_anti_forgetting"),
        ("data/lichess_cp_sf400k_filter", 0.35, "sample-files", "sf400k_anti_forgetting"),
        ("data/extraquiet_cp_sf60k_filter", 0.35, "sample-files", "sf60k_anti_forgetting"),

        # 3. Richest Stockfish Endgames (Weight 1x - Anti-Forgetting Anchor):
        ("data/extraquiet_cp_sfd14_endgames_filter", 0.35, "sample-files", "endgames_d14_anti_forgetting"),
        ("data/selfplay-lichess_cp_sf500k_res_filter_endgames", 0.35, "sample-files", "endgames_sf500k_anti_forgetting"),
        ("data/synthetic_endgame_cp_sf_filter_data20260414", 0.35, "sample-files", "synth_endgames_14_anti_forgetting"),
        ("data/synthetic_endgame_cp_sf_filter_data20260413", 0.35, "sample-files", "synth_endgames_13_anti_forgetting"),
        ("data/extraquiet_cp_sfd12_endgames_filter", 0.35, "sample-files", "endgames_d12_anti_forgetting"),
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
            else:
                print(f"  [-] Skipped (no parquet files): {name} ({rel_path})")
        else:
            print(f"  [-] Skipped (missing directory): {name} ({rel_path})")

    if not sources:
        print("[ERROR] No data sources found for fine-tuning!")
        return 1

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
        "--device", "cuda",
        "--lr", str(args.lr),
        "--transfer-lr", str(args.lr),
        "--lr-dense", str(args.lr_dense),
        "--eta-min", str(args.eta_min),
    ]

    print(f"\nStarting {args.epochs}-epoch fine-tuning on CUDA...")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - t0

    if res.returncode != 0:
        print(f"\n[ERROR] Fine-tuning failed with return code {res.returncode}")
        return res.returncode

    print(f"\n[SUCCESS] Fine-tuning completed in {elapsed:.1f}s ({elapsed/3600:.2f}h)!")
    refresh_latest()
    export_weights()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
