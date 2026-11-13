"""
tools/train_aux_head_v336.py — Train auxiliary head on top of the newly annealed v336 primary weights.
"""
from __future__ import annotations

import argparse
import glob
import re
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

OUT_HEADER = ROOT / "artifacts" / "fast_head_weights_v336.h"

def train_aux_head(target_positions: int = 1_500_000, alpha_reg: float = 200.0):
    print("=" * 80)
    print(" TRAINING DUAL-NNUE AUXILIARY HEAD FOR ANNEALED v336")
    print(f" Target Positions: {target_positions:,} | Alpha Reg: {alpha_reg}")
    print("=" * 80)

    source_patterns = [
        str(ROOT / "data" / "extraquiet_cp_sf5k_res_filter" / "*.parquet"),
        str(ROOT / "data" / "extraquiet_cp_sfd14_endgames_filter" / "*.parquet"),
        str(ROOT / "data" / "selfplay-lichess_cp_sf500k_res_filter_endgames" / "*.parquet"),
        str(ROOT / "data" / "synthetic_endgame_cp_sf_filter_data20260414" / "*.parquet"),
        str(ROOT / "data" / "lichess_cp_sf400k_filter" / "*.parquet"),
    ]
    files = []
    for pat in source_patterns:
        files.extend(sorted(glob.glob(pat)))

    ckpt_path = ROOT / "checkpoints" / "v336_sf_anneal" / "latest.pt"
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    state = ckpt["model"] if "model" in ckpt else ckpt["state_dict"]
    model = NNUE()
    model.load_state_dict(state)
    model.eval()
    w1, b1 = model.l1.weight, model.l1.bias

    print(f"Loaded v336 base model from {ckpt_path}.")

    D = 256
    AtA = np.zeros((D + 1, D + 1), dtype=np.float64)
    Aty = np.zeros(D + 1, dtype=np.float64)

    total_streamed = 0
    t0 = time.time()
    val_fens = []
    val_targets = []

    for fpath in files:
        if total_streamed >= target_positions:
            break
        try:
            df = pd.read_parquet(fpath)
        except Exception:
            continue

        if "fen" not in df.columns or "cp" not in df.columns:
            continue

        fens = df["fen"].tolist()
        cp = df["cp"].to_numpy(dtype=np.float32)

        if len(val_fens) < 20_000:
            take_val = min(20_000 - len(val_fens), len(fens))
            val_fens.extend(fens[:take_val])
            val_targets.extend(cp[:take_val])
            fens = fens[take_val:]
            cp = cp[take_val:]
            if not fens:
                continue

        if total_streamed + len(fens) > target_positions:
            fens = fens[:target_positions - total_streamed]
            cp = cp[:target_positions - total_streamed]

        chunk_sz = 25_000
        for b_start in range(0, len(fens), chunk_sz):
            b_fens = fens[b_start:b_start + chunk_sz]
            b_cp = cp[b_start:b_start + chunk_sz]

            x_np, is_black = encode_chunk(b_fens)
            cp_stm = np.where(is_black, -b_cp, b_cp)
            target_cp = np.clip(cp_stm, -2000.0, 2000.0)

            with torch.no_grad():
                x = torch.from_numpy(x_np)
                h1 = F.linear(x, w1, b1).clamp(0.0, 1.0)
                relu1 = (h1 * 255.0).round().clamp(0.0, 255.0).numpy()

            N = len(relu1)
            X_b = np.hstack([relu1, np.ones((N, 1), dtype=np.float32)])
            AtA += X_b.T @ X_b
            Aty += X_b.T @ target_cp
            total_streamed += N

    print(f"Streamed {total_streamed:,} positions in {time.time()-t0:.1f}s. Solving least-squares...")
    reg_diag = np.full(D + 1, alpha_reg, dtype=np.float64)
    reg_diag[-1] = 1e-4
    AtA_reg = AtA + np.diag(reg_diag)
    sol = np.linalg.solve(AtA_reg, Aty)
    w_raw = sol[:D].astype(np.float32)
    bias_raw = float(sol[D])

    # Quantize to int8
    max_abs = float(np.max(np.abs(w_raw)))
    scale = 127.0 / (max_abs + 1e-9)
    w_int8 = np.clip(np.round(w_raw * scale), -127, 127).astype(np.int8)
    inv_scale = float(1.0 / scale)

    # Validation
    val_x_np, val_is_black = encode_chunk(val_fens)
    val_cp_stm = np.where(val_is_black, -np.array(val_targets, dtype=np.float32), np.array(val_targets, dtype=np.float32))
    val_target = np.clip(val_cp_stm, -2000.0, 2000.0)

    with torch.no_grad():
        vx = torch.from_numpy(val_x_np)
        vh1 = F.linear(vx, w1, b1).clamp(0.0, 1.0)
        v_relu1 = (vh1 * 255.0).round().clamp(0.0, 255.0).numpy()

    pred_fast = v_relu1.astype(np.float32) @ (w_int8.astype(np.float32) * inv_scale) + bias_raw
    mae_fast = float(np.mean(np.abs(pred_fast - val_target)))
    corr_fast = float(np.corrcoef(pred_fast, val_target)[0, 1])

    print("=" * 80)
    print(" v336 DUAL-HEAD VALIDATION METRICS:")
    print(f"  Validation Set:       {len(val_fens):,} positions")
    print(f"  Fast Head MAE:        {mae_fast:.1f} cp")
    print(f"  Fast Head Pearson r:  {corr_fast:.4f}")
    print(f"  Fast Head Bias:       {bias_raw:+.2f} cp")
    print(f"  Fast Head Inv Scale:  {inv_scale:.8f}")
    print("=" * 80)

    # Export header
    lines = [
        "/* fast_head_weights_v336.h — Auxiliary Head for Annealed v336 */",
        "#pragma once",
        "#include <stdint.h>",
        "",
        "#define FAST_HEAD_DIM 256",
        f"#define FAST_HEAD_INV_SCALE ({inv_scale:.8f}f)",
        f"#define FAST_HEAD_BIAS ({bias_raw:.2f}f)",
        "",
        "static const int8_t FAST_HEAD_W[256] __attribute__((aligned(32))) = {",
    ]
    for r in range(0, 256, 16):
        chunk = ", ".join(f"{w_int8[i]:4d}" for i in range(r, r + 16))
        comma = "," if r + 16 < 256 else ""
        lines.append(f"    {chunk}{comma}")
    lines.append("};")
    lines.append("")

    OUT_HEADER.write_text("\n".join(lines), encoding="utf-8")
    print(f"[SUCCESS] Exported auxiliary head weights to {OUT_HEADER}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--positions", type=int, default=1_500_000)
    p.add_argument("--alpha", type=float, default=200.0)
    args = p.parse_args()
    train_aux_head(target_positions=args.positions, alpha_reg=args.alpha)
