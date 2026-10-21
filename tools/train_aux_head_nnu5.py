"""
tools/train_aux_head_nnu5.py — Train Dual-NNUE Auxiliary Head for NNU5 (v6xx Lineage).

Architecture:
- Inputs: 512 activations from SCReLU L1 [stm 256 | opp 256] (values 0..254).
- Out-of-core streaming covariance accumulation directly from *_encoded_nnu5.pt tensors.
- GPU-accelerated Ridge regression across 1,000,000+ positions.
- Quantizes to int8_t for ultra-fast AVX2 dot-product (16 instructions, ~8ns).
- Exports engine/c/zchezz_v605/fast_head_weights.h.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "train"))
from model_nnu5 import NNUE, fake_quant_int16, fake_quant_bias_int32, QA, QA_EFF

OUT_DIR = ROOT / "engine" / "c" / "zchezz_v605"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def train_aux_head_nnu5(target_positions: int = 1_000_000, alpha_reg: float = 200.0, ckpt_path: str | None = None):
    print("=" * 80)
    print(" TRAINING DUAL-NNUE AUXILIARY HEAD FOR NNU5 (6xx FAMILY - GPU ACCELERATED)")
    print(f" Target Positions: {target_positions:,} | Ridge Alpha: {alpha_reg}")
    print("=" * 80)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # 1. Collect pre-encoded NNU5 tensor chunks
    pts = sorted(list((ROOT / "data").rglob("*_encoded_nnu5.pt")))
    print(f"Total encoded NNU5 chunks found: {len(pts)}")
    if not pts:
        raise FileNotFoundError("No *_encoded_nnu5.pt datasets found in data/!")

    # 2. Load NNU5 checkpoint
    if ckpt_path is None:
        ckpt_path = str(ROOT / "checkpoints" / "v605" / "latest.pt")
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    weights = ckpt["weights"] if "weights" in ckpt else ckpt.get("model", ckpt)
    model = NNUE()
    model.load_state_dict(weights)
    model.to(device).eval()

    w1 = fake_quant_int16(model.l1.weight, QA).to(device)
    b1 = fake_quant_bias_int32(model.l1_bias, float(QA)).to(device)

    print(f"NNU5 Model loaded from {ckpt_path}. Starting GPU streaming covariance...\n")

    D = 512
    AtA = torch.zeros((D + 1, D + 1), dtype=torch.float64, device=device)
    Aty = torch.zeros(D + 1, dtype=torch.float64, device=device)

    val_relu1_list = []
    val_target_list = []

    total_streamed = 0
    t0 = time.time()
    last_print = t0

    for pt_file in pts:
        if total_streamed >= target_positions:
            break
        try:
            d = torch.load(pt_file, map_location="cpu", weights_only=False)
        except Exception:
            continue

        if "stm_idx" not in d or "cp" not in d or d["cp"] is None:
            continue

        n_rows = d["n_rows"]
        cp = d["cp"]
        is_black = d.get("is_black", np.zeros(n_rows, dtype=bool))
        cp_stm = np.where(is_black, -cp, cp)
        target_cp = np.clip(cp_stm, -2000.0, 2000.0)

        # Slice into chunks for memory safety
        stm_idx = torch.from_numpy(d["stm_idx"]).long().to(device)
        stm_off = torch.from_numpy(d["stm_off"]).long().to(device)
        opp_idx = torch.from_numpy(d["opp_idx"]).long().to(device)
        opp_off = torch.from_numpy(d["opp_off"]).long().to(device)
        y_target = torch.from_numpy(target_cp).float().to(device)

        with torch.no_grad():
            h_stm = model._l1_perspective(stm_idx, stm_off, w1, b1)
            h_opp = model._l1_perspective(opp_idx, opp_off, w1, b1)
            h_stm_q = (h_stm * QA_EFF).round().clamp(0, QA_EFF)
            h_opp_q = (h_opp * QA_EFF).round().clamp(0, QA_EFF)
            relu1 = torch.cat([h_stm_q, h_opp_q], dim=1) # [N, 512]

        N = len(relu1)
        if len(val_relu1_list) * 50_000 < 20_000:
            val_relu1_list.append(relu1[:2000].cpu())
            val_target_list.append(y_target[:2000].cpu())

        ones = torch.ones((N, 1), device=device, dtype=relu1.dtype)
        X_b = torch.cat([relu1, ones], dim=1).double()

        AtA += X_b.T @ X_b
        Aty += X_b.T @ y_target.double()

        total_streamed += N
        now = time.time()
        if now - last_print >= 2.0 or total_streamed >= target_positions:
            pos_per_sec = total_streamed / (now - t0 + 1e-5)
            pct = (total_streamed / target_positions) * 100.0
            print(f"  [{pct:5.1f}%] Streamed: {total_streamed:,} / {target_positions:,} pos | Speed: {pos_per_sec:,.0f} pos/s")
            last_print = now

    print(f"\nAccumulation complete: {total_streamed:,} positions in {time.time()-t0:.2f}s.")
    print("Solving regularized normal equations: (AtA + alpha*I) w = Aty ...")

    reg_diag = torch.full((D + 1,), alpha_reg, dtype=torch.float64, device=device)
    reg_diag[-1] = 1e-4  # minimal regularization on bias
    AtA_reg = AtA + torch.diag(reg_diag)

    sol = torch.linalg.solve(AtA_reg, Aty).cpu().numpy()
    w_raw = sol[:D].astype(np.float32)
    bias_raw = float(sol[D])

    print(f"Raw solution: w min={w_raw.min():.4f}, max={w_raw.max():.4f}, mean={w_raw.mean():.4f}, bias={bias_raw:+.2f} cp")

    # Quantize to int8
    max_abs = float(np.max(np.abs(w_raw)))
    scale = 127.0 / (max_abs + 1e-9)
    w_int8 = np.clip(np.round(w_raw * scale), -127, 127).astype(np.int8)
    inv_scale = float(1.0 / scale)

    # Validate on held-out positions
    if val_relu1_list:
        val_relu1 = torch.cat(val_relu1_list, dim=0).numpy().astype(np.float32)
        val_target = torch.cat(val_target_list, dim=0).numpy()
        pred_fast = val_relu1 @ (w_int8.astype(np.float32) * inv_scale) + bias_raw
        mae_fast = float(np.mean(np.abs(pred_fast - val_target)))
        corr_fast = float(np.corrcoef(pred_fast, val_target)[0, 1])

        print("=" * 80)
        print(" NNU5 DUAL-HEAD VALIDATION METRICS:")
        print(f"  Validation Set:       {len(val_relu1):,} positions")
        print(f"  Fast Head MAE:        {mae_fast:.1f} cp")
        print(f"  Fast Head Pearson r:  {corr_fast:.4f}")
        print(f"  Fast Head Bias:       {bias_raw:+.2f} cp")
        print(f"  Fast Head Inv Scale:  {inv_scale:.8f}")
        print("=" * 80)

    # Export C headers to both engine/c/zchezz_v605 and artifacts
    for out_path in [
        OUT_DIR / "fast_head_weights.h",
        ROOT / "artifacts" / "fast_head_weights_nnu5.h",
    ]:
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

        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"[SUCCESS] Exported NNU5 auxiliary head weights to {out_path} ({out_path.stat().st_size:,} bytes)")

    return inv_scale, bias_raw


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--positions", type=int, default=1_000_000)
    p.add_argument("--alpha", type=float, default=200.0)
    p.add_argument("--checkpoint", type=str, default=None)
    args = p.parse_args()
    train_aux_head_nnu5(target_positions=args.positions, alpha_reg=args.alpha, ckpt_path=args.checkpoint)
