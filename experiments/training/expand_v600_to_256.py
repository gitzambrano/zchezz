#!/usr/bin/env python3
"""train/expand_v600_to_256.py — Net2Net expansion of NNU5 L1 from 64 to 256 neurons."""
from __future__ import annotations
import shutil
from pathlib import Path
import torch

ROOT = Path(__file__).resolve().parents[1]

def expand_to_256():
    src_pt = ROOT / "checkpoints" / "v600" / "latest.pt"
    backup_pt = ROOT / "checkpoints" / "v600" / "latest_64neurons_backup.pt"

    print(f"Loading checkpoint: {src_pt}")
    ckpt = torch.load(src_pt, map_location="cpu", weights_only=False)
    old_arch = ckpt.get("arch", {})
    old_weights = ckpt["weights"]

    print(f"Current architecture: {old_arch}")
    if not backup_pt.is_file():
        shutil.copy2(src_pt, backup_pt)
        print(f"Backed up 64-neuron checkpoint to: {backup_pt}")

    old_l1w = old_weights["l1.weight"]
    old_l1b = old_weights["l1_bias"]
    old_l2w = old_weights["l2.weight"]
    old_l2b = old_weights["l2.bias"]
    old_l3w = old_weights["l3.weight"]
    old_l3b = old_weights["l3.bias"]

    # 1. Expand L1 from 64 to 256
    new_h1 = 256
    new_concat = 512
    new_l1w = torch.empty(22528, new_h1, dtype=torch.float32)
    new_l1b = torch.zeros(new_h1, dtype=torch.float32)

    torch.manual_seed(42)
    # Copy existing 64 neurons
    new_l1w[:, :64] = old_l1w
    new_l1b[:64] = old_l1b

    # Initialize new 192 neurons with small normal weights
    new_l1w[:, 64:].normal_(0.0, 0.02)
    print(f"L1 expanded: (22528, 64) -> {tuple(new_l1w.shape)}")

    # 2. Expand L2 from (64, 128) to (64, 512)
    std_l2 = (2.0 / new_concat) ** 0.5  # ~0.0625
    new_l2w = torch.empty(64, new_concat, dtype=torch.float32)
    new_l2b = old_l2b.clone()

    # STM perspective: 0..63 is old, 64..255 is new
    new_l2w[:, 0:64] = old_l2w[:, 0:64]
    new_l2w[:, 64:256].normal_(0.0, std_l2).clamp_(-127.0 / 64.0, 127.0 / 64.0)

    # OPP perspective: 256..319 is old (64..127 in old), 320..511 is new
    new_l2w[:, 256:320] = old_l2w[:, 64:128]
    new_l2w[:, 320:512].normal_(0.0, std_l2).clamp_(-127.0 / 64.0, 127.0 / 64.0)
    print(f"L2 expanded: (64, 128) -> {tuple(new_l2w.shape)}")

    # 3. L3 remains (1, 64)
    new_l3w = old_l3w.clone()
    new_l3b = old_l3b.clone()

    new_arch = {
        "input": 22528,
        "h1": new_h1,
        "concat": new_concat,
        "h2": 64,
        "encoding": "halfka_v2_hm_32b",
    }

    new_ckpt = {
        "epoch": 0,
        "dataset": "v600_256neurons_init",
        "avg_loss": ckpt.get("avg_loss", 0.0),
        "val_loss": ckpt.get("val_loss", 0.0),
        "train_mae": ckpt.get("train_mae", 0.0),
        "val_mae": ckpt.get("val_mae", 0.0),
        "lr": 2e-4,
        "timestamp": ckpt.get("timestamp", ""),
        "arch": new_arch,
        "qat": True,
        "qa": 255.0,
        "qb": 64.0,
        "weights": {
            "l1.weight": new_l1w,
            "l1_bias": new_l1b,
            "l2.weight": new_l2w,
            "l2.bias": new_l2b,
            "l3.weight": new_l3w,
            "l3.bias": new_l3b,
        },
    }

    out_pt = ROOT / "checkpoints" / "v600" / "v600_256neurons_init.pt"
    torch.save(new_ckpt, out_pt)
    print(f"Saved expanded checkpoint: {out_pt}")

    # Atomically refresh latest.pt
    tmp = src_pt.with_suffix(".pt.tmp")
    shutil.copy2(out_pt, tmp)
    tmp.replace(src_pt)
    print(f"Atomically updated {src_pt} to 256-neuron architecture!")

if __name__ == "__main__":
    expand_to_256()
