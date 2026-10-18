#!/usr/bin/env python3
"""Fine-tuning for Zchezz v600 (NNUE5 - HalfKAv2 32-Bucket) using multi-horizon lookahead targets.

Target formula applied to selfplay data:
  Target(t) = 0.60 * v_0 + 0.20 * v_2 + 0.10 * v_4 + 0.10 * z
Where:
  - v_0: current static eval (sigmoid(cp_t / 320))
  - v_2: position 2 plies ahead (same color)
  - v_4: position 4 plies ahead (same color)
  - z:   game result (1.0 = win, 0.5 = draw, 0.0 = loss)

Mix:
  1. data/selfplay_lookahead_filter (100% of newly generated lookahead positions)
  2. Anchor datasets:
     - extraquiet_cp_sf60k_filter (50%)
     - extraquiet_cp_sfd14_endgames_filter (100%)
     - selfplay-lichess_cp_sf500k_res_filter_endgames (100%)
     - synthetic_endgame_cp_sf_filter_data20260414 (100%)

Learning rate: 1e-5 decaying to 1e-7 over N epochs.
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
    print(f"Atomically refreshed {latest} from {newest}")

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
    parser = argparse.ArgumentParser(description="Zchezz v600 lookahead fine-tuning")
    parser.add_argument("--epochs", type=int, default=12, help="Number of fine-tuning epochs")
    parser.add_argument("--batch-size", type=int, default=32768, help="Minibatch size")
    parser.add_argument("--lr", type=float, default=1e-5, help="Initial learning rate for L1")
    parser.add_argument("--lr-dense", type=float, default=5e-4, help="Learning rate for L2/L3 dense head")
    parser.add_argument("--freeze-l1-epochs", type=int, default=3, help="Epochs to freeze L1 weights")
    parser.add_argument("--eta-min", type=float, default=1e-7, help="Minimum learning rate")
    parser.add_argument("--checkpoint", type=str, default="checkpoints/v600/latest.pt", help="Checkpoint to resume")
    return parser.parse_args()

def main():
    args = parse_args()

    print("=" * 75)
    print(f" Zchezz v600 (NNUE5) — Lookahead Fine-Tuning ({args.epochs} Epochs, LR={args.lr:.1e} -> {args.eta_min:.1e})")
    print("=" * 75)

    ckpt_path = ROOT / args.checkpoint
    if not ckpt_path.is_file():
        print(f"[ERROR] Checkpoint not found: {ckpt_path}")
        return 1

    parquet_datasets = [
        ("data/selfplay_lookahead_filter", 0.25, "colab_selfplay_lookahead_quiet"),
        ("data/extraquiet_cp_sf60k_filter", 1.00, "anchor_sf60k"),
        ("data/extraquiet_cp_sfd14_endgames_filter", 1.00, "anchor_endgames_d14"),
        ("data/selfplay-lichess_cp_sf500k_res_filter_endgames", 1.00, "anchor_endgames_sf500k"),
        ("data/synthetic_endgame_cp_sf_filter_data20260414", 1.00, "anchor_synth_endgames"),
        ("data/selfplay_cp_sf100k_res_endgames_filter_data20260414", 1.00, "anchor_selfplay_sf100k"),
    ]

    sources = []
    for rel_path, pct, name in parquet_datasets:
        full_dir = ROOT / rel_path
        if full_dir.is_dir():
            files = list(full_dir.glob("*.parquet"))
            if files:
                sources.extend([
                    "--source",
                    f"kind=parquet,path={rel_path},train_pct={pct},name={name}",
                ])
                print(f"  [+] Source: {name:32s} ({len(files):4d} shards, pct={pct:.2f})")
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
        "--dataset-name", "v600_lookahead_64neurons_warmed",
        "--epochs", str(args.epochs),
        "--batch-size", str(args.batch_size),
        "--device", "cuda",
        "--lr", str(args.lr),
        "--lr-dense", str(args.lr_dense),
        "--freeze-l1-epochs", str(args.freeze_l1_epochs),
        "--transfer-lr", str(args.lr),
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
