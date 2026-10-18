#!/usr/bin/env python3
"""Execute full lookahead fine-tuning (12 epochs) followed by evaluation tournament against v331_exp."""

from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run_step(cmd: list[str], title: str) -> int:
    print(f"\n{'='*75}")
    print(f" >>> [RUN] {title}")
    print(f"     CMD: {' '.join(cmd)}")
    print(f"{'='*75}\n")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - t0
    if res.returncode != 0:
        print(f"\n[ERROR] {title} failed with code {res.returncode} in {elapsed:.1f}s")
        return res.returncode
    print(f"\n[SUCCESS] {title} completed in {elapsed:.1f}s ({elapsed/60:.1f}m)")
    return 0

def main():
    print("=" * 75)
    print(" ZCHEZZ v600 / v601: LOOKAHEAD TRAINING & EVALUATION PIPELINE")
    print("=" * 75)

    # 1. Train 12 epochs on CUDA
    train_cmd = [
        sys.executable,
        "-u",
        str(ROOT / "train" / "train_v600_lookahead.py"),
        "--epochs", "12",
        "--batch-size", "32768",
        "--lr", "1e-5",
        "--eta-min", "1e-7",
    ]
    ret = run_step(train_cmd, "v600 Lookahead Fine-Tuning (12 Epochs)")
    if ret != 0:
        return ret

    # 2. Run match vs v331_exp (10 pairs x 2 colors = 20 games each)
    eval_cmd = [
        sys.executable,
        "-u",
        str(ROOT / "tests" / "check_v600_vs_331.py"),
        "--games", "10",
        "--movetime", "100",
        "--concurrency", "4",
    ]
    ret = run_step(eval_cmd, "Evaluation Tournament: v600 & v601 vs v331_exp")
    return ret

if __name__ == "__main__":
    raise SystemExit(main())
