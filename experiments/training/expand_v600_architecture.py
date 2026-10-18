#!/usr/bin/env python3
"""train/expand_v600_architecture.py — Net2Net expansion of NNU5 L2 layer from 16 to 64 neurons."""
from __future__ import annotations
import shutil
import sys
from pathlib import Path
import torch

ROOT = Path(__file__).resolve().parents[1]

def expand_checkpoint():
    src_pt = ROOT / "checkpoints" / "v600" / "latest.pt"
    backup_pt = ROOT / "checkpoints" / "v600" / "latest_16neurons.pt"

    print(f"Loading foundation checkpoint: {src_pt}")
    ckpt = torch.load(src_pt, map_location="cpu")
    old_arch = ckpt.get("arch", {})
    old_weights = ckpt.get("weights", ckpt)

    print(f"Current architecture: {old_arch}")
    h1 = old_arch.get("h1", 64)
    concat = old_arch.get("concat", 128)
    old_h2 = old_arch.get("h2", 16)
    new_h2 = 64

    if not backup_pt.is_file():
        shutil.copy2(src_pt, backup_pt)
        print(f"Backed up 16-neuron checkpoint to: {backup_pt}")

    # Build new expanded state_dict
    new_weights = {}

    # L1 weights & bias (100% preserved)
    new_weights["l1.weight"] = old_weights["l1.weight"].clone()
    new_weights["l1_bias"] = old_weights["l1_bias"].clone()

    # L2 weights & bias (expand rows from 16 to 64)
    old_l2w = old_weights["l2.weight"]
    old_l2b = old_weights["l2.bias"]
    new_l2w = torch.empty(new_h2, concat, dtype=torch.float32)
    new_l2b = torch.zeros(new_h2, dtype=torch.float32)

    # Copy existing 16 neurons
    new_l2w[:old_h2, :] = old_l2w
    new_l2b[:old_h2] = old_l2b

    # Kaiming normal init for new 48 neurons
    std = (2.0 / concat) ** 0.5
    torch.manual_seed(1234)
    new_l2w[old_h2:, :].normal_(0.0, std).clamp_(-127.0 / 64.0, 127.0 / 64.0)

    new_weights["l2.weight"] = new_l2w
    new_weights["l2.bias"] = new_l2b

    # L3 weights & bias (expand columns from 16 to 64)
    old_l3w = old_weights["l3.weight"]
    new_l3w = torch.zeros(1, new_h2, dtype=torch.float32)
    # Net2Net: zero-init the new columns so initial forward output is 100% identical!
    new_l3w[:, :old_h2] = old_l3w
    new_weights["l3.weight"] = new_l3w
    new_weights["l3.bias"] = old_weights["l3.bias"].clone()

    new_arch = {
        "input": 22528,
        "h1": 64,
        "concat": 128,
        "h2": new_h2,
        "encoding": "halfka_v2_hm_32b",
    }

    new_ckpt = {
        "epoch": 0,
        "dataset": "v600_expanded_64neurons",
        "avg_loss": ckpt.get("avg_loss", 0.0),
        "val_loss": ckpt.get("val_loss", 0.0),
        "train_mae": ckpt.get("train_mae", 0.0),
        "val_mae": ckpt.get("val_mae", 0.0),
        "lr": 1e-5,
        "timestamp": ckpt.get("timestamp", ""),
        "arch": new_arch,
        "qat": True,
        "qa": 255.0,
        "qb": 64.0,
        "weights": new_weights,
    }

    torch.save(new_ckpt, src_pt)
    print(f"[SUCCESS] Expanded checkpoint saved to {src_pt}")
    print(f"New architecture: {new_arch}")
    for k, v in new_weights.items():
        print(f"  {k}: {v.shape}")

if __name__ == "__main__":
    expand_checkpoint()
