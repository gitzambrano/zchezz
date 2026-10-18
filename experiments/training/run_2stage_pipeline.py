#!/usr/bin/env python3
"""Automated 2-Stage Training and Verification Pipeline for Zchezz v600.

Stage 1 (Foundation Warmup - 120 Epochs):
  - Massive general warmup corpus (hundreds of millions of positions)
  - Heavy weighting for top Stockfish depth/node teaching
  - High learning rate (lr=3e-4, lr-dense=1e-3 -> eta-min=1e-6)

Stage 2 (Specialized Fine-Tuning - 50 Epochs):
  - Multi-horizon lookahead quiet positions (0.60*v0 + 0.20*v2 + 0.10*v4 + 0.10*z)
  - High-precision endgame anchors
  - Fine-tuning learning rate (lr=1e-5, lr-dense=5e-5 -> eta-min=1e-7)

Stage 3 (Validation & Benchmark):
  - Binary weight export & verification
  - Head-to-head tournament check vs v331_exp
"""
from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run_stage(title: str, script: str, extra_args: list[str] = None):
    print("\n" + "#" * 80)
    print(f" STARTING: {title}")
    print("#" * 80 + "\n")
    cmd = [sys.executable, "-u", str(ROOT / "train" / script)]
    if extra_args:
        cmd.extend(extra_args)
    t0 = time.time()
    res = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - t0
    if res.returncode != 0:
        print(f"\n[PIPELINE ERROR] {title} failed with exit code {res.returncode} after {elapsed:.1f}s")
        sys.exit(res.returncode)
    print(f"\n[PIPELINE SUCCESS] {title} completed in {elapsed:.1f}s ({elapsed/3600:.2f}h)!")

def main():
    print("=" * 80)
    print(" Zchezz v600 — Full 2-Stage Training & Benchmark Pipeline")
    print("=" * 80)

    # 1. Stage 1: Foundation Pre-Training (120 epochs)
    run_stage("Stage 1: Foundation Warmup (120 Epochs)", "train_v600_foundation.py", ["--epochs", "120"])

    # 2. Stage 2: Specialized Lookahead Fine-Tuning (50 epochs)
    run_stage("Stage 2: Lookahead Fine-Tuning (50 Epochs)", "train_v600_finetune.py", ["--epochs", "50"])

    # 3. Post-training Evaluation Tournament vs v331_exp
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
    print("\n[PIPELINE FINISHED] All stages completed successfully!")

if __name__ == "__main__":
    raise SystemExit(main())
