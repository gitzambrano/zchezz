"""
tools/train_aux_head_nnu5.py — Train Dual-NNUE Auxiliary Head for NNU5 (v6xx Lineage).

Architecture:
- Inputs: 512 activations from SCReLU L1 [stm 256 | opp 256] (values 0..254).
- Out-of-core streaming covariance accumulation across Stockfish datasets.
- Solves exact Ridge regression across 1,000,000+ positions.
- Quantizes to int8_t for ultra-fast AVX2 dot-product (16 instructions, ~8ns).
- Exports artifacts/fast_head_weights_nnu5.h.
"""
from __future__ import annotations

import argparse
import glob
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "train"))
from encoding_nnu5 import encode_positions
from model_nnu5 import NNUE, fake_quant_int16, fake_quant_bias_int32, QA, QA_EFF

OUT_DIR = ROOT / "artifacts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def train_aux_head_nnu5(target_positions: int = 1_000_000, alpha_reg: float = 200.0, batch_sz: int = 5_000):
    print("=" * 80)
    print(" TRAINING DUAL-NNUE AUXILIARY HEAD FOR NNU5 (6xx FAMILY)")
    print(f" Target Positions: {target_positions:,} | Ridge Alpha: {alpha_reg} | Batch Size: {batch_sz:,}")
    print("=" * 80)

    # 1. Collect all Stockfish parquet files
    source_patterns = [
        str(ROOT / "data" / "extraquiet_cp_sf5k_res_filter" / "*.parquet"),
        str(ROOT / "data" / "extraquiet_cp_sfd14_endgames_filter" / "*.parquet"),
        str(ROOT / "data" / "selfplay-lichess_cp_sf500k_res_filter_endgames" / "*.parquet"),
        str(ROOT / "data" / "synthetic_endgame_cp_sf_filter_data20260414" / "*.parquet"),
        str(ROOT / "data" / "lichess_cp_sf400k_filter" / "*.parquet"),
        str(ROOT / "data" / "extraquiet_cp_sf60k_filter" / "*.parquet"),
    ]
    files = []
    for pat in source_patterns:
        found = sorted(glob.glob(pat))
        files.extend(found)
    print(f"Total parquet files found: {len(files)}")
    if not files:
        raise FileNotFoundError("No parquet datasets found in data/!")

    # 2. Load NNU5 checkpoint
    ckpt_path = ROOT / "checkpoints" / "v604" / "latest.pt"
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    weights = ckpt["weights"] if "weights" in ckpt else ckpt["model"]
    model = NNUE()
    model.load_state_dict(weights)
    model.eval()

    w1 = fake_quant_int16(model.l1.weight, QA)
    b1 = fake_quant_bias_int32(model.l1_bias, float(QA))

    print(f"NNU5 Model loaded from {ckpt_path}. Starting streaming accumulation...\n")

    D = 512
    AtA = np.zeros((D + 1, D + 1), dtype=np.float64)
    Aty = np.zeros(D + 1, dtype=np.float64)

    val_fens: list[str] = []
    val_targets: list[float] = []

    total_streamed = 0
    t0 = time.time()
    last_print = t0

    for f_idx, fpath in enumerate(files):
        if total_streamed >= target_positions:
            break
        try:
            df = pd.read_parquet(fpath)
        except Exception as e:
            continue

        if "fen" not in df.columns or "cp" not in df.columns:
            continue

        fens = df["fen"].tolist()
        cp = np.array(df["cp"], dtype=np.float32)

        # Reserve 15,000 positions for validation
        if len(val_fens) < 15_000:
            take_val = min(15_000 - len(val_fens), len(fens))
            val_fens.extend(fens[:take_val])
            val_targets.extend(cp[:take_val])
            fens = fens[take_val:]
            cp = cp[take_val:]
            if not fens:
                continue

        if total_streamed + len(fens) > target_positions:
            fens = fens[:target_positions - total_streamed]
            cp = cp[:target_positions - total_streamed]

        for b_start in range(0, len(fens), batch_sz):
            b_fens = fens[b_start:b_start + batch_sz]
            b_cp = cp[b_start:b_start + batch_sz]

            # Fast STM check from FEN
            # FEN turn is active side: ' w ' -> STM is White, ' b ' -> STM is Black
            is_black = np.array([(' b ' in f) for f in b_fens], dtype=bool)
            cp_stm = np.where(is_black, -b_cp, b_cp)
            target_cp = np.clip(cp_stm, -2000.0, 2000.0)

            stm_idx, stm_off, opp_idx, opp_off = encode_positions(b_fens)
            stm_idx_t = torch.from_numpy(stm_idx).long()
            stm_off_t = torch.from_numpy(stm_off).long()
            opp_idx_t = torch.from_numpy(opp_idx).long()
            opp_off_t = torch.from_numpy(opp_off).long()

            with torch.no_grad():
                h_stm = model._l1_perspective(stm_idx_t, stm_off_t, w1, b1)
                h_opp = model._l1_perspective(opp_idx_t, opp_off_t, w1, b1)
                h_stm_q = (h_stm * QA_EFF).round().clamp(0, QA_EFF)
                h_opp_q = (h_opp * QA_EFF).round().clamp(0, QA_EFF)
                relu1 = torch.cat([h_stm_q, h_opp_q], dim=1).numpy() # [N, 512]

            N = len(relu1)
            X_b = np.hstack([relu1, np.ones((N, 1), dtype=np.float32)])

            AtA += X_b.T @ X_b
            Aty += X_b.T @ target_cp

            total_streamed += N

            now = time.time()
            if now - last_print >= 5.0 or total_streamed >= target_positions:
                pos_per_sec = total_streamed / (now - t0 + 1e-5)
                pct = (total_streamed / target_positions) * 100.0
                print(f"  [{pct:5.1f}%] Streamed: {total_streamed:,} / {target_positions:,} pos | Speed: {pos_per_sec:,.0f} pos/s")
                last_print = now

            if total_streamed >= target_positions:
                break

    print(f"\nAccumulation complete: {total_streamed:,} positions in {time.time()-t0:.1f}s.")
    print("Solving regularized normal equations: (AtA + alpha*I) w = Aty ...")

    reg_diag = np.full(D + 1, alpha_reg, dtype=np.float64)
    reg_diag[-1] = 1e-4  # minimal regularisation on bias
    AtA_reg = AtA + np.diag(reg_diag)

    sol = np.linalg.solve(AtA_reg, Aty)
    w_raw = sol[:D].astype(np.float32)
    bias_raw = float(sol[D])

    print(f"Raw solution: w min={w_raw.min():.4f}, max={w_raw.max():.4f}, mean={w_raw.mean():.4f}, bias={bias_raw:.2f} cp")

    # Quantize to int8
    max_abs = float(np.max(np.abs(w_raw)))
    scale = 127.0 / (max_abs + 1e-9)
    w_int8 = np.clip(np.round(w_raw * scale), -127, 127).astype(np.int8)
    inv_scale = float(1.0 / scale)

    # Validate on held-out 15k positions
    print("\nValidating quantized head on held-out set...")
    val_is_black = np.array([(' b ' in f) for f in val_fens], dtype=bool)
    val_cp_stm = np.where(val_is_black, -np.array(val_targets, dtype=np.float32), np.array(val_targets, dtype=np.float32))
    val_target = np.clip(val_cp_stm, -2000.0, 2000.0)

    stm_idx, stm_off, opp_idx, opp_off = encode_positions(val_fens)
    with torch.no_grad():
        h_stm = model._l1_perspective(torch.from_numpy(stm_idx).long(), torch.from_numpy(stm_off).long(), w1, b1)
        h_opp = model._l1_perspective(torch.from_numpy(opp_idx).long(), torch.from_numpy(opp_off).long(), w1, b1)
        h_stm_q = (h_stm * QA_EFF).round().clamp(0, QA_EFF)
        h_opp_q = (h_opp * QA_EFF).round().clamp(0, QA_EFF)
        val_relu1 = torch.cat([h_stm_q, h_opp_q], dim=1).numpy()

    # Fast dot product in quantized domain
    pred_fast = val_relu1.astype(np.float32) @ (w_int8.astype(np.float32) * inv_scale) + bias_raw
    mae_fast = float(np.mean(np.abs(pred_fast - val_target)))
    corr_fast = float(np.corrcoef(pred_fast, val_target)[0, 1])

    print("=" * 80)
    print(" NNU5 DUAL-HEAD VALIDATION METRICS:")
    print(f"  Validation Set:       {len(val_fens):,} positions")
    print(f"  Fast Head MAE:        {mae_fast:.1f} cp")
    print(f"  Fast Head Pearson r:  {corr_fast:.4f}")
    print(f"  Fast Head Bias:       {bias_raw:+.2f} cp")
    print(f"  Fast Head Inv Scale:  {inv_scale:.8f}")
    print("=" * 80)

    # Export C header
    header_path = OUT_DIR / "fast_head_weights_nnu5.h"
    lines = [
        "/* fast_head_weights_nnu5.h — Dual-NNUE Auxiliary Head for NNU5 (512 inputs) */",
        "#pragma once",
        "#include <stdint.h>",
        "",
        f"#define FAST_HEAD_DIM 512",
        f"#define FAST_HEAD_INV_SCALE ({inv_scale:.8f}f)",
        f"#define FAST_HEAD_BIAS ({bias_raw:.2f}f)",
        "",
        "static const int8_t FAST_HEAD_W[512] __attribute__((aligned(32))) = {",
    ]
    for r in range(0, 512, 16):
        chunk = ", ".join(f"{w_int8[i]:4d}" for i in range(r, r + 16))
        comma = "," if r + 16 < 512 else ""
        lines.append(f"    {chunk}{comma}")
    lines.append("};")
    lines.append("")

    header_text = "\n".join(lines)
    header_path.write_text(header_text, encoding="utf-8")
    print(f"\n[SUCCESS] Exported NNU5 auxiliary head weights to {header_path} ({header_path.stat().st_size:,} bytes)")
    return header_path

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--positions", type=int, default=1_000_000)
    p.add_argument("--alpha", type=float, default=200.0)
    p.add_argument("--batch-sz", type=int, default=5_000)
    args = p.parse_args()
    train_aux_head_nnu5(target_positions=args.positions, alpha_reg=args.alpha, batch_sz=args.batch_sz)
