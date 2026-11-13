"""
tools/train_aux_head.py — Train and export ultra-fast auxiliary NNUE head.

Fits a 256 -> 1 linear head on the relu1 activations of v334's NNU3 network
using positions from lichess_cp_sf400k_filter.
Emits C header fast_head_weights.h with int8 weights and fixed-point scale.
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "train"))
from encoding_nnu3 import encode_chunk
from model_nnu3 import NNUE

def train_and_export():
    print("=== Training Auxiliary Linear Head for Dual-NNUE ===")
    parquets = sorted(glob.glob(str(ROOT / "data" / "lichess_cp_sf400k_filter" / "*.parquet")))
    if not parquets:
        raise FileNotFoundError("No parquets found in data/lichess_cp_sf400k_filter")
    
    all_fens = []
    all_cp = []
    for p in parquets:
        df = pd.read_parquet(p)
        all_fens.extend(df["fen"].tolist())
        all_cp.extend(df["cp"].tolist())
        if len(all_fens) >= 100_000:
            break
            
    fens = all_fens[:100_000]
    cp = np.array(all_cp[:100_000], dtype=np.float32)
    print(f"Loaded {len(fens):,} positions from dataset")

    # Encode positions
    print("Encoding positions...")
    x_np, is_black = encode_chunk(fens)
    cp_stm = np.where(is_black, -cp, cp)
    target_cp = np.clip(cp_stm, -2000.0, 2000.0)

    # Load NNU3 checkpoint
    ckpt_path = ROOT / "checkpoints" / "v334" / "latest.pt"
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    state = ckpt["model"] if "model" in ckpt else ckpt["state_dict"]
    model = NNUE()
    model.load_state_dict(state)
    model.eval()

    print("Extracting relu1 activations and NNU3 predictions...")
    with torch.no_grad():
        x = torch.from_numpy(x_np)
        w1, b1 = model.l1.weight, model.l1.bias
        h1 = F.linear(x, w1, b1).clamp(0.0, 1.0)
        relu1 = (h1 * 255.0).round().clamp(0.0, 255.0).numpy()
        pred_prob = model(x).squeeze().numpy()
        pred_cp = -320.0 * np.log(1.0 / np.clip(pred_prob, 1e-5, 1.0 - 1e-5) - 1.0)

    X = relu1
    y = pred_cp  # Both are side-to-move relative

    n_tr = 80_000
    X_tr, X_va = X[:n_tr], X[n_tr:]
    y_tr, y_va = y[:n_tr], y[n_tr:]

    print("Fitting Ridge regression (256 -> 1)...")
    ridge = Ridge(alpha=100.0)
    ridge.fit(X_tr, y_tr)

    w_float = ridge.coef_
    b_float = ridge.intercept_

    pred_va = ridge.predict(X_va)
    corr = np.corrcoef(pred_va, y_va)[0, 1]
    mae = np.mean(np.abs(pred_va - y_va))
    print(f"Unquantized Head: Corr = {corr:.4f}, MAE = {mae:.2f} cp")

    # Quantize to int8
    max_abs_w = np.max(np.abs(w_float))
    scale_w = 127.0 / max_abs_w
    w_int8 = np.clip(np.round(w_float * scale_w), -127, 127).astype(np.int8)

    pred_quant = (X_va @ w_int8.astype(np.float32)) / scale_w + b_float
    corr_q = np.corrcoef(pred_quant, y_va)[0, 1]
    mae_q = np.mean(np.abs(pred_quant - y_va))
    print(f"Quantized int8 Head: Corr = {corr_q:.4f}, MAE = {mae_q:.2f} cp")
    print(f"scale_w: {scale_w:.6f}, bias: {b_float:.4f}")

    # Generate C header
    c_header_content = f"""/* fast_head_weights.h — Auto-generated auxiliary NNUE linear head weights
 * Trained on 100k positions from lichess_cp_sf400k_filter.
 * Correlation with full NNU3: {corr_q:.4f}, MAE: {mae_q:.2f} cp.
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

    out_file = ROOT / "artifacts" / "fast_head_weights.h"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(c_header_content, encoding="utf-8")
    print(f"Exported C header to {out_file}")

if __name__ == "__main__":
    train_and_export()
