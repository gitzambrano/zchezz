#!/usr/bin/env python3
"""Activate all 64 neurons in NNU5 L2/L3 dense head.

Loads checkpoints/v600/latest.pt, preserves the 100% trained L1 features and
the first 16 trained dense neurons, and initializes neurons 16..63 with active,
non-zero weights comfortably outside the int8 quantization dead zone (QB=64.0).
"""
from __future__ import annotations
import shutil
from pathlib import Path
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]

def main():
    src_pt = ROOT / "checkpoints" / "v600" / "latest.pt"
    backup_pt = ROOT / "checkpoints" / "v600" / "latest_before_activation.pt"

    print(f"Loading checkpoint: {src_pt}")
    ckpt = torch.load(src_pt, map_location="cpu")
    weights = ckpt["weights"]

    if not backup_pt.is_file():
        shutil.copy2(src_pt, backup_pt)
        print(f"Created backup at: {backup_pt}")

    l1w = weights["l1.weight"]
    l1b = weights["l1_bias"]
    l2w = weights["l2.weight"].clone()
    l2b = weights["l2.bias"].clone()
    l3w = weights["l3.weight"].clone()
    l3b = weights["l3.bias"].clone()

    torch.manual_seed(42)

    # 1. Initialize L2 for neurons 16..63
    std_l2 = (2.0 / 128.0) ** 0.5  # ~0.125
    l2w[16:, :].normal_(0.0, std_l2).clamp_(-127.0 / 64.0, 127.0 / 64.0)
    l2b[16:].normal_(0.0, 0.05).clamp_(-1.0, 1.0)

    # 2. Initialize L3 for neurons 16..63 outside the dead zone [-0.0078, +0.0078]
    signs = torch.randint(0, 2, (1, 48), dtype=torch.float32) * 2.0 - 1.0
    mags = torch.empty(1, 48).uniform_(0.15, 0.35)
    l3w[:, 16:] = signs * mags

    # Revive neuron 2 (which had 0 weights in both L2 and L3)
    if np.count_nonzero(np.clip(np.round(l2w[2].numpy() * 64.0), -128, 127).astype(np.int8)) == 0:
        l2w[2, :].normal_(0.0, std_l2).clamp_(-127.0 / 64.0, 127.0 / 64.0)
        l2b[2] = 0.05
        print("Revived dead neuron 2 in L2")
    if round(float(l3w[0, 2]) * 64.0) == 0:
        l3w[0, 2] = 0.25
        print("Revived dead neuron 2 in L3 (set to +0.25)")

    # Check int8 quantization
    qb = 64.0
    l2_int8 = np.clip(np.round(l2w.numpy() * qb), -128, 127).astype(np.int8)
    l3_int8 = np.clip(np.round(l3w.numpy() * qb), -128, 127).astype(np.int8)

    active_neurons = 0
    for i in range(64):
        if np.count_nonzero(l2_int8[i]) > 0 and np.count_nonzero(l3_int8[:, i]) > 0:
            active_neurons += 1

    print(f"Active neurons in int8 after activation: {active_neurons} / 64 ({active_neurons/64*100:.1f}%)")
    assert active_neurons == 64, f"Expected 64 active neurons, got {active_neurons}"

    new_weights = {
        "l1.weight": l1w,
        "l1_bias": l1b,
        "l2.weight": l2w,
        "l2.bias": l2b,
        "l3.weight": l3w,
        "l3.bias": l3b,
    }

    new_ckpt = {
        "epoch": 0,
        "dataset": "v600_active_64neurons_init",
        "avg_loss": ckpt.get("avg_loss", 0.0),
        "val_loss": ckpt.get("val_loss", 0.0),
        "train_mae": ckpt.get("train_mae", 0.0),
        "val_mae": ckpt.get("val_mae", 0.0),
        "lr": 2e-5,
        "timestamp": ckpt.get("timestamp", ""),
        "arch": ckpt.get("arch", {}),
        "qat": True,
        "qa": 255.0,
        "qb": 64.0,
        "weights": new_weights,
    }

    out_pt = ROOT / "checkpoints" / "v600" / "v600_active_64neurons_init.pt"
    torch.save(new_ckpt, out_pt)
    print(f"Saved initialized checkpoint to: {out_pt}")

    # Atomically refresh latest.pt
    tmp = src_pt.with_suffix(".pt.tmp")
    shutil.copy2(out_pt, tmp)
    tmp.replace(src_pt)
    print(f"Atomically updated: {src_pt}")

if __name__ == "__main__":
    main()
