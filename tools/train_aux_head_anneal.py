"""
tools/train_aux_head_anneal.py — Fine-tune Auxiliary NNUE Head on Stockfish data with Annealing.

Features:
- Collects ALL Stockfish parquet datasets in data/ (192 files, tens of millions of positions).
- Warms up from current million-head weights.
- Uses low learning rate with Cosine Annealing (1e-4 -> 1e-6) to refine weights smoothly.
- Blends Stockfish ground-truth CP with NNU3 network predictions.
- Validates on 20,000 held-out positions.
- Exports quantized int8 weights to artifacts/fast_head_weights_annealed.h.
"""
from __future__ import annotations

import argparse
import glob
import math
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "train"))
from encoding_nnu3 import encode_chunk
from model_nnu3 import NNUE

def load_initial_weights(header_path: Path) -> tuple[np.ndarray, float]:
    """Parse W and bias from fast_head_weights header."""
    text = header_path.read_text(encoding="utf-8")
    bias_m = re.search(r"FAST_HEAD_BIAS\s+\(([+-]?[\d\.]+)f\)", text)
    scale_m = re.search(r"FAST_HEAD_INV_SCALE\s+\(([+-]?[\d\.]+)f\)", text)
    bias = float(bias_m.group(1)) if bias_m else 0.0
    inv_scale = float(scale_m.group(1)) if scale_m else 1.0

    w_match = re.search(r"FAST_HEAD_W\[256\].*?=\s*\{([^}]+)\}", text, re.DOTALL)
    if not w_match:
        raise ValueError("Could not find FAST_HEAD_W in header")
    raw_nums = re.findall(r"[-+]?\d+", w_match.group(1))
    int8_w = np.array([int(x) for x in raw_nums[:256]], dtype=np.float32)
    # Reconstruct float weights: w_float = int8_w * inv_scale
    w_float = int8_w * inv_scale
    return w_float, bias

class AuxHeadModel(nn.Module):
    def __init__(self, init_w: np.ndarray, init_bias: float):
        super().__init__()
        self.w = nn.Parameter(torch.from_numpy(init_w).float().unsqueeze(1)) # [256, 1]
        self.b = nn.Parameter(torch.tensor([init_bias], dtype=torch.float32))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x is [B, 256]
        return torch.matmul(x, self.w) + self.b

def train_anneal(target_positions: int = 3_000_000, initial_lr: float = 1e-4, min_lr: float = 1e-6):
    print("=" * 80)
    print(" DUAL-NNUE AUXILIARY HEAD ANNEALING ON STOCKFISH CORPUS")
    print(f" Target Positions: {target_positions:,} | LR: {initial_lr:.1e} -> {min_lr:.1e}")
    print("=" * 80)

    # 1. Collect all Stockfish parquet files
    source_patterns = [
        str(ROOT / "data" / "extraquiet_cp_sf5k_res_filter" / "*.parquet"),
        str(ROOT / "data" / "extraquiet_cp_sfd14_endgames_filter" / "*.parquet"),
        str(ROOT / "data" / "selfplay-lichess_cp_sf500k_res_filter_endgames" / "*.parquet"),
        str(ROOT / "data" / "synthetic_endgame_cp_sf_filter_data20260414" / "*.parquet"),
    ]
    files = []
    for pat in source_patterns:
        found = sorted(glob.glob(pat))
        files.extend(found)
        print(f"  {len(found):3d} files: {pat}")
    print(f"Total Stockfish parquet files: {len(files)}")
    if not files:
        raise FileNotFoundError("No Stockfish parquet datasets found in data/!")

    # 2. Load NNU3 model for L1 feature extraction and teacher labels
    ckpt_path = ROOT / "checkpoints" / "v335" / "latest.pt"
    if not ckpt_path.is_file():
        ckpt_path = ROOT / "checkpoints" / "v334" / "latest.pt"
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    state = ckpt["model"] if "model" in ckpt else ckpt["state_dict"]
    nnu3 = NNUE()
    nnu3.load_state_dict(state)
    nnu3.eval()
    w1, b1 = nnu3.l1.weight, nnu3.l1.bias

    # 3. Initialize Aux Head from existing million weights
    init_header = ROOT / "artifacts" / "fast_head_weights_million.h"
    init_w, init_b = load_initial_weights(init_header)
    print(f"Loaded initial weights from {init_header.name} (bias={init_b:.2f}, max_w={np.max(np.abs(init_w)):.4f})")

    aux_model = AuxHeadModel(init_w, init_b)
    optimizer = torch.optim.AdamW(aux_model.parameters(), lr=initial_lr, weight_decay=1e-4)

    # Reserve 20,000 validation positions
    val_fens, val_targets = [], []
    val_set_ready = False
    vx_relu1 = None
    v_target_cp = None
    v_nnu3_cp = None

    total_seen = 0
    t0 = time.time()
    steps_total = math.ceil(target_positions / 25_000)

    print("\nStarting streaming annealing...")
    for f_idx, fpath in enumerate(files):
        if total_seen >= target_positions:
            break
        try:
            df = pd.read_parquet(fpath)
        except Exception as e:
            continue

        if "fen" not in df.columns or "cp" not in df.columns:
            continue

        fens = df["fen"].tolist()
        cps = np.array(df["cp"], dtype=np.float32)

        # Populate validation set first
        if len(val_fens) < 20_000:
            need = 20_000 - len(val_fens)
            take = min(need, len(fens))
            val_fens.extend(fens[:take])
            val_targets.extend(cps[:take])
            fens = fens[take:]
            cps = cps[take:]
            if len(val_fens) == 20_000 and not val_set_ready:
                print(f"Validation set prepared: {len(val_fens):,} positions.")
                vx_np, v_is_black = encode_chunk(val_fens)
                v_cp_stm = np.where(v_is_black, -np.array(val_targets, dtype=np.float32), np.array(val_targets, dtype=np.float32))
                v_target_cp = torch.from_numpy(np.clip(v_cp_stm, -2000.0, 2000.0)).float().unsqueeze(1)
                with torch.no_grad():
                    vx_t = torch.from_numpy(vx_np)
                    vh1 = F.linear(vx_t, w1, b1).clamp(0.0, 1.0)
                    vx_relu1 = (vh1 * 255.0).round().clamp(0.0, 255.0)
                    v_prob = nnu3(vx_t).squeeze()
                    v_nnu3_cp = (-320.0 * torch.log(1.0 / torch.clamp(v_prob, 1e-5, 1.0 - 1e-5) - 1.0)).unsqueeze(1)
                val_set_ready = True
            if not fens:
                continue

        # Process in batches of 25,000
        batch_size = 25_000
        for i in range(0, len(fens), batch_size):
            if total_seen >= target_positions:
                break
            batch_fens = fens[i:i + batch_size]
            batch_cps = cps[i:i + batch_size]

            # Encode features
            x_np, is_black = encode_chunk(batch_fens)
            cp_stm = np.where(is_black, -batch_cps, batch_cps)
            target_sf = torch.from_numpy(np.clip(cp_stm, -2000.0, 2000.0)).float().unsqueeze(1)

            # L1 extraction
            with torch.no_grad():
                x_t = torch.from_numpy(x_np)
                h1 = F.linear(x_t, w1, b1).clamp(0.0, 1.0)
                relu1 = (h1 * 255.0).round().clamp(0.0, 255.0)
                nnu3_prob = nnu3(x_t).squeeze()
                target_nnu3 = (-320.0 * torch.log(1.0 / torch.clamp(nnu3_prob, 1e-5, 1.0 - 1e-5) - 1.0)).unsqueeze(1)

            # Cosine annealing LR schedule
            progress = min(1.0, total_seen / target_positions)
            current_lr = min_lr + 0.5 * (initial_lr - min_lr) * (1.0 + math.cos(math.pi * progress))
            for g in optimizer.param_groups:
                g["lr"] = current_lr

            # Forward aux head
            pred = aux_model(relu1)

            # Combined loss: 70% Stockfish truth + 30% NNU3 teacher
            loss_sf = F.smooth_l1_loss(pred, target_sf, beta=50.0)
            loss_nnu3 = F.smooth_l1_loss(pred, target_nnu3, beta=30.0)
            loss = 0.70 * loss_sf + 0.30 * loss_nnu3

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_seen += len(batch_fens)

            if total_seen % 250_000 < batch_size or total_seen >= target_positions:
                # Validation check
                with torch.no_grad():
                    v_pred = aux_model(vx_relu1)
                    mae_sf = torch.mean(torch.abs(v_pred - v_target_cp)).item()
                    mae_nnu3 = torch.mean(torch.abs(v_pred - v_nnu3_cp)).item()
                    corr_sf = np.corrcoef(v_pred.squeeze().numpy(), v_target_cp.squeeze().numpy())[0, 1]
                    corr_nnu3 = np.corrcoef(v_pred.squeeze().numpy(), v_nnu3_cp.squeeze().numpy())[0, 1]

                elapsed = time.time() - t0
                speed = total_seen / elapsed if elapsed > 0 else 0
                print(f"[{total_seen:9,d} / {target_positions:,d}] ({progress*100:5.1f}%) | "
                      f"LR={current_lr:.2e} | Loss={loss.item():.2f} | "
                      f"Corr SF={corr_sf:.4f} (MAE={mae_sf:5.1f}cp) | "
                      f"Corr NNU3={corr_nnu3:.4f} (MAE={mae_nnu3:5.1f}cp) | "
                      f"{speed:7,.0f} pos/s")

    # Final Validation and Quantization
    print("\n" + "=" * 80)
    print(" TRAINING COMPLETE — FINAL VALIDATION & INT8 QUANTIZATION")
    print("=" * 80)

    with torch.no_grad():
        w_float = aux_model.w.squeeze().numpy()
        b_float = float(aux_model.b.item())
        v_pred_unquant = aux_model(vx_relu1).squeeze().numpy()

    v_sf_np = v_target_cp.squeeze().numpy()
    v_nnu3_np = v_nnu3_cp.squeeze().numpy()

    corr_unquant_sf = np.corrcoef(v_pred_unquant, v_sf_np)[0, 1]
    corr_unquant_nnu3 = np.corrcoef(v_pred_unquant, v_nnu3_np)[0, 1]
    mae_unquant_sf = np.mean(np.abs(v_pred_unquant - v_sf_np))

    print(f"Unquantized Head: Corr SF = {corr_unquant_sf:.4f}, Corr NNU3 = {corr_unquant_nnu3:.4f}, MAE SF = {mae_unquant_sf:.1f} cp")

    # Quantize to int8
    max_abs_w = np.max(np.abs(w_float))
    scale_w = 127.0 / max_abs_w
    w_int8 = np.clip(np.round(w_float * scale_w), -127, 127).astype(np.int8)

    vx_relu1_np = vx_relu1.numpy()
    v_pred_quant = (vx_relu1_np @ w_int8.astype(np.float32)) / scale_w + b_float
    corr_q_sf = np.corrcoef(v_pred_quant, v_sf_np)[0, 1]
    corr_q_nnu3 = np.corrcoef(v_pred_quant, v_nnu3_np)[0, 1]
    mae_q_sf = np.mean(np.abs(v_pred_quant - v_sf_np))

    print(f"Quantized int8 Head: Corr SF = {corr_q_sf:.4f}, Corr NNU3 = {corr_q_nnu3:.4f}, MAE SF = {mae_q_sf:.1f} cp")
    print(f"scale_w = {scale_w:.6f}, bias = {b_float:.4f}")

    # Generate C header
    c_header_content = f"""/* fast_head_weights.h — Auxiliary NNUE linear head weights (Annealed)
 * Annealed with Cosine Schedule on {total_seen:,} Stockfish positions.
 * Corr with SF: {corr_q_sf:.4f}, Corr with NNU3: {corr_q_nnu3:.4f}, MAE SF: {mae_q_sf:.2f} cp.
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

    out_file = ROOT / "artifacts" / "fast_head_weights_annealed.h"
    out_file.write_text(c_header_content, encoding="utf-8")
    print(f"\nExported annealed weights to {out_file} successfully!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--positions", type=int, default=3_000_000)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--min-lr", type=float, default=1e-6)
    args = parser.parse_args()
    train_anneal(args.positions, args.lr, args.min_lr)
