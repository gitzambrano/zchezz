"""
tools/train_aux_head_million.py — Train auxiliary NNUE head on Millions of positions.

Streams through millions of positions from:
- data/selfplay-lichess_cp_sf500k_res_filter_endgames/
- data/lichess_cp_sf400k_filter/
- data/extraquiet_cp_sfd14_endgames_filter/

Uses out-of-core streaming covariance accumulation (constant memory footprint).
Solves the exact L2 regularized least-squares problem across 2,000,000+ positions.
Quantizes weights to int8_t for 2.5ns AVX2 SIMD evaluation.
"""
from __future__ import annotations

import argparse
import glob
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "train"))
from encoding_nnu3 import encode_chunk
from model_nnu3 import NNUE

def train_aux_head_million(target_positions: int = 2_000_000, alpha_reg: float = 200.0):
    print("=" * 75)
    print(f" TRAINING AUXILIARY HEAD ON {target_positions:,} POSITIONS")
    print("=" * 75)

    # Collect parquet files
    source_patterns = [
        str(ROOT / "data" / "selfplay-lichess_cp_sf500k_res_filter_endgames" / "*.parquet"),
        str(ROOT / "data" / "lichess_cp_sf400k_filter" / "*.parquet"),
        str(ROOT / "data" / "extraquiet_cp_sfd14_endgames_filter" / "*.parquet"),
    ]
    files = []
    for pat in source_patterns:
        found = sorted(glob.glob(pat))
        files.extend(found)
        print(f"Found {len(found)} files for pattern: {pat}")
    
    if not files:
        raise FileNotFoundError("No parquet datasets found in data/!")

    # Load NNU3 checkpoint
    ckpt_path = ROOT / "checkpoints" / "v334" / "latest.pt"
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    state = ckpt["model"] if "model" in ckpt else ckpt["state_dict"]
    model = NNUE()
    model.load_state_dict(state)
    model.eval()
    w1, b1 = model.l1.weight, model.l1.bias

    print(f"\nModel loaded from {ckpt_path}. Starting streaming accumulation...")

    # Covariance accumulation matrices
    # X_bias has shape [N, 257] (256 relu1 features + 1 bias column)
    D = 256
    AtA = np.zeros((D + 1, D + 1), dtype=np.float64)
    Aty = np.zeros(D + 1, dtype=np.float64)

    total_streamed = 0
    t0 = time.time()

    val_fens = []
    val_targets = []
    val_nnu3 = []

    for f_idx, fpath in enumerate(files):
        if total_streamed >= target_positions:
            break
        try:
            df = pd.read_parquet(fpath)
        except Exception as e:
            print(f"Skipping {fpath}: {e}")
            continue

        fens = df["fen"].tolist()
        cp = np.array(df["cp"], dtype=np.float32)

        # Reserve first 20k positions for validation
        if len(val_fens) < 20_000:
            take_val = min(20_000 - len(val_fens), len(fens))
            val_fens.extend(fens[:take_val])
            val_targets.extend(cp[:take_val])
            fens = fens[take_val:]
            cp = cp[take_val:]
            if not fens:
                continue

        # Limit to target_positions
        if total_streamed + len(fens) > target_positions:
            fens = fens[:target_positions - total_streamed]
            cp = cp[:target_positions - total_streamed]

        # Process in batches of 25,000 to keep memory small
        batch_sz = 25_000
        for b_start in range(0, len(fens), batch_sz):
            b_fens = fens[b_start:b_start + batch_sz]
            b_cp = cp[b_start:b_start + batch_sz]

            x_np, is_black = encode_chunk(b_fens)
            # Side to move relative target
            cp_stm = np.where(is_black, -b_cp, b_cp)
            target_cp = np.clip(cp_stm, -2000.0, 2000.0)

            with torch.no_grad():
                x = torch.from_numpy(x_np)
                h1 = F.linear(x, w1, b1).clamp(0.0, 1.0)
                relu1 = (h1 * 255.0).round().clamp(0.0, 255.0).numpy()

            # Append bias column of 1.0
            N = len(relu1)
            X_b = np.hstack([relu1, np.ones((N, 1), dtype=np.float32)])

            # Accumulate normal equations
            AtA += X_b.T @ X_b
            Aty += X_b.T @ target_cp

            total_streamed += N

        elapsed = time.time() - t0
        rate = total_streamed / max(0.1, elapsed)
        if (f_idx + 1) % 5 == 0 or total_streamed >= target_positions:
            print(f"[{f_idx+1}/{len(files)}] Streamed {total_streamed:,} positions ({rate:,.0f} pos/sec, {elapsed:.1f}s)")

    print(f"\nCompleted streaming of {total_streamed:,} positions in {time.time()-t0:.1f}s.")

    # Solve Ridge regression: (AtA + alpha * I) w = Aty
    print("Solving Ridge regression...")
    reg = np.eye(D + 1, dtype=np.float64) * alpha_reg
    reg[-1, -1] = 0.0  # Do not regularize bias
    w_full = np.linalg.solve(AtA + reg, Aty)

    w_float = w_full[:D]
    b_float = float(w_full[D])

    # Validation on 20,000 held-out positions
    print(f"\nEvaluating on {len(val_fens):,} held-out positions...")
    vx_np, v_is_black = encode_chunk(val_fens)
    v_cp_stm = np.where(v_is_black, -np.array(val_targets, dtype=np.float32), np.array(val_targets, dtype=np.float32))
    v_target_cp = np.clip(v_cp_stm, -2000.0, 2000.0)

    with torch.no_grad():
        vx = torch.from_numpy(vx_np)
        vh1 = F.linear(vx, w1, b1).clamp(0.0, 1.0)
        v_relu1 = (vh1 * 255.0).round().clamp(0.0, 255.0).numpy()
        v_pred_prob = model(vx).squeeze().numpy()
        v_pred_nnu3 = -320.0 * np.log(1.0 / np.clip(v_pred_prob, 1e-5, 1.0 - 1e-5) - 1.0)

    pred_unquant = v_relu1 @ w_float + b_float
    corr_unquant = np.corrcoef(pred_unquant, v_target_cp)[0, 1]
    mae_unquant = np.mean(np.abs(pred_unquant - v_target_cp))
    corr_to_nnu3 = np.corrcoef(pred_unquant, v_pred_nnu3)[0, 1]

    print(f"Unquantized Head: Corr with Target = {corr_unquant:.4f}, MAE = {mae_unquant:.1f} cp")
    print(f"Unquantized Head: Corr with Full NNU3 = {corr_to_nnu3:.4f}")

    # Quantize to int8
    max_abs_w = np.max(np.abs(w_float))
    scale_w = 127.0 / max_abs_w
    w_int8 = np.clip(np.round(w_float * scale_w), -127, 127).astype(np.int8)

    pred_quant = (v_relu1 @ w_int8.astype(np.float32)) / scale_w + b_float
    corr_q = np.corrcoef(pred_quant, v_target_cp)[0, 1]
    mae_q = np.mean(np.abs(pred_quant - v_target_cp))
    corr_q_to_nnu3 = np.corrcoef(pred_quant, v_pred_nnu3)[0, 1]

    print(f"Quantized int8 Head: Corr with Target = {corr_q:.4f}, MAE = {mae_q:.1f} cp")
    print(f"Quantized int8 Head: Corr with Full NNU3 = {corr_q_to_nnu3:.4f}")
    print(f"scale_w = {scale_w:.6f}, bias = {b_float:.4f}")

    # Generate C header
    c_header_content = f"""/* fast_head_weights.h — Auxiliary NNUE linear head weights
 * Trained on {total_streamed:,} positions with out-of-core streaming.
 * Corr with Target: {corr_q:.4f}, Corr with Full NNU3: {corr_q_to_nnu3:.4f}, MAE: {mae_q:.2f} cp.
 */
#pragma once
#include <stdint.h>

#define FAST_HEAD_BIAS   ({b_float:.4f}f)
#define FAST_HEAD_INV_SCALE ({1.0 / scale_w:.8f}f)

static const int8_t FAST_HEAD_W[256] __attribute__((aligned(32))) = {{
"""
    for row in range(0, 256, 16):
        vals = ", ".join(f"{w_int8[i]:4d}" for i in range(row, row + 16))
        c_header_content += f"    {vals},\n"
    c_header_content += "};\n"

    out_file = ROOT / "artifacts" / "fast_head_weights_million.h"
    out_file.write_text(c_header_content, encoding="utf-8")
    print(f"\nExported {out_file} successfully!")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--positions", type=int, default=2_000_000)
    args = p.parse_args()
    train_aux_head_million(args.positions)
