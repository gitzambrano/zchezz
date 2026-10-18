#!/usr/bin/env python3
"""Fine-Tuning orchestrator for Zchezz v507_exp2 (NNU4: 2560 -> 48x2 -> 20 -> 1).

60-epoch fine-tuning using:
  - 3 parts Dense Lookahead Selfplay (quiet-only verified: 0 checks)
  - 1 part Richest Stockfish Teachers (1M, 500k, 400k, 60k, D14 endgames)
  - Resumes from checkpoints/v507/latest.pt
  - Weight transfer / fine-tuning LR: transfer_lr=3e-5 decaying to 1e-7
  - Output checkpoint: checkpoints/v507_exp2/
  - Output engine weights: artifacts/engines/v507_exp2/nnue_weights.bin
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
    ckpt_dir = ROOT / "checkpoints" / "v507_exp2"
    pts = [x for x in ckpt_dir.glob("*.pt") if x.name != "latest.pt"]
    if not pts:
        return None
    newest = max(pts, key=lambda x: x.stat().st_mtime_ns)
    latest = ckpt_dir / "latest.pt"
    tmp = latest.with_suffix(".pt.tmp")
    shutil.copy2(newest, tmp)
    tmp.replace(latest)
    print(f"Atomically refreshed {latest} from {newest.name}")
    return latest

def export_weights(ckpt_path: Path):
    print("\n[Export] Exporting binary weights for v507_exp2...")
    out_dir = ROOT / "artifacts" / "engines" / "v507_exp2"
    out_dir.mkdir(parents=True, exist_ok=True)
    weights_path = out_dir / "nnue_weights.bin"

    sys.path.insert(0, str(ROOT / "train"))
    from export_nnu4 import convert
    convert(ckpt_path, weights_path)
    print(f"Exported v507_exp2 weights: {weights_path} ({weights_path.stat().st_size:,} bytes)")

    # Copy engine binary if available
    v507_src = ROOT / "artifacts" / "engines" / "v507_new" / "zchezz.exe"
    if not v507_src.is_file():
        v507_src = ROOT / "engine" / "c" / "zchezz_v507" / "zchezz.exe"
    if v507_src.is_file():
        dst_exe = out_dir / "zchezz.exe"
        shutil.copy2(v507_src, dst_exe)
        print(f"Copied engine executable: {dst_exe}")

def parse_args():
    parser = argparse.ArgumentParser(description="Zchezz v507_exp2 60-Epoch Fine-Tuning")
    parser.add_argument("--epochs", type=int, default=60, help="Number of fine-tuning epochs (default: 60)")
    parser.add_argument("--batch-size", type=int, default=32768, help="Minibatch size (default: 32768)")
    parser.add_argument("--lr", type=float, default=3e-5, help="Learning rate (default: 3e-5)")
    parser.add_argument("--eta-min", type=float, default=1e-7, help="Minimum learning rate (default: 1e-7)")
    parser.add_argument("--checkpoint", type=str, default="checkpoints/v507/latest.pt", help="Base checkpoint")
    parser.add_argument("--dataset-name", type=str, default="v507_exp2_finetune_60ep", help="Dataset name tag")
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default="cpu", help="Compute device (default: cpu)")
    parser.add_argument("--workers", type=int, default=4, help="Encoding workers (default: 4)")
    return parser.parse_args()

def main():
    args = parse_args()

    print("=" * 80)
    print(f" Zchezz v507_exp2 (NNU4) — 60-Epoch Fine-Tuning")
    print(" Mix: 3 Parts Dense Quiet Selfplay : 1 Part Richest Stockfish Teaching")
    print(f" Config: LR={args.lr:.1e} -> eta_min={args.eta_min:.1e}, Batch={args.batch_size}, Device={args.device}")
    print("=" * 80)

    base_ckpt = ROOT / args.checkpoint
    if not base_ckpt.is_file():
        print(f"[ERROR] Checkpoint not found: {base_ckpt}")
        return 1

    # 3:1 Dataset ratio:
    # 3 parts Dense Lookahead Quiet Selfplay (each pass 0.30 of 118 files = ~3.5M rows -> 10.5M rows total)
    # 1 part Stockfish Highest-Quality Teachers (~3.5M rows total)
    datasets = [
        # --- Selfplay (Weight 3x): 3 distinct random file passes per epoch ---
        ("data/selfplay_lookahead_filter", 0.30, "sample-files", "selfplay_lookahead_p1"),
        ("data/selfplay_lookahead_filter", 0.30, "sample-files", "selfplay_lookahead_p2"),
        ("data/selfplay_lookahead_filter", 0.30, "sample-files", "selfplay_lookahead_p3"),

        # --- Stockfish Teachers (Weight 1x): Top search depth & endgame anchors ---
        ("data/miscelaneous_cp_sf1M_res_filter", 1.00, "sample-files", "sf_1M_richest"),
        ("data/lichess_cp_sf400k_filter", 1.00, "sample-files", "sf_400k_richest"),
        ("data/extraquiet_cp_sf60k_filter", 0.40, "sample-files", "sf_60k_quiet"),
        ("data/extraquiet_cp_sfd14_endgames_filter", 0.40, "sample-files", "sf_d14_endgames"),
        ("data/selfplay-lichess_cp_sf500k_res_filter_endgames", 0.40, "sample-files", "sf_500k_endgames"),
        ("data/synthetic_endgame_cp_sf_filter_data20260414", 0.40, "sample-files", "sf_synth14_endgames"),
        ("data/synthetic_endgame_cp_sf_filter_data20260413", 0.40, "sample-files", "sf_synth13_endgames"),
        ("data/extraquiet_cp_sfd12_endgames_filter", 0.40, "sample-files", "sf_d12_endgames"),
    ]

    sources = []
    for rel_path, pct, mode, name in datasets:
        full_dir = ROOT / rel_path
        if full_dir.is_dir():
            files = list(full_dir.glob("*.parquet"))
            if files:
                sources.extend([
                    "--source",
                    f"kind=parquet,path={rel_path},train_pct={pct},pct_mode={mode},name={name}",
                ])
                print(f"  [+] Source: {name:25s} ({len(files):4d} shards, pct={pct:.2f})")
            else:
                print(f"  [-] Skipped (empty): {name}")
        else:
            print(f"  [-] Skipped (missing): {name}")

    ckpt_out = ROOT / "checkpoints" / "v507_exp2"
    ckpt_out.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "train" / "_train_nnu4_core.py"),
        *sources,
        "--ckpt-dir", str(ckpt_out),
        "--checkpoint-source", str(base_ckpt),
        "--dataset-name", str(args.dataset_name),
        "--epochs", str(args.epochs),
        "--batch-size", str(args.batch_size),
        "--max-positions-chunk", "150000",
        "--parquet-chunk-rows", "50000",
        "--device", str(args.device),
        "--workers", str(args.workers),
        "--lr", str(args.lr),
        "--transfer-lr", str(args.lr),
        "--eta-min", str(args.eta_min),
    ]

    print(f"\nLaunching {args.epochs}-epoch v507_exp2 fine-tuning...")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - t0

    if res.returncode != 0:
        print(f"\n[ERROR] v507_exp2 fine-tuning failed with return code {res.returncode}")
        return res.returncode

    print(f"\n[SUCCESS] v507_exp2 fine-tuning completed in {elapsed:.1f}s ({elapsed/3600:.2f}h)!")
    latest = refresh_latest()
    if latest:
        export_weights(latest)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
