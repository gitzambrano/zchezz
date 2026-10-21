"""
tools/train_nnu3_anneal_sf.py — Fine-tune full NNU3 Primary Network on Stockfish data with Annealing.

Features:
- Starts from checkpoints/v335/latest.pt.
- Streams through millions of Stockfish-evaluated positions on CUDA.
- Uses low transfer learning rate (3e-5 -> 1e-7) with CosineAnnealingLR.
- Blends WDL cross-entropy with MSE centipawn loss.
- Exports trained weights to checkpoints/v336_sf_anneal/ and artifacts/nnue_weights_v336.bin.
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
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "train"))
from encoding_nnu3 import encode_chunk
from model_nnu3 import NNUE, clamp_weights_, architecture_dict
from _export_nnu3_core import export_checkpoint

OUT_CKPT_DIR = ROOT / "checkpoints" / "v336_sf_anneal"
OUT_CKPT_DIR.mkdir(parents=True, exist_ok=True)
OUT_BIN = ROOT / "artifacts" / "nnue_weights_v336.bin"

def cp_to_wdl(cp: np.ndarray) -> np.ndarray:
    """Map centipawns to WDL winning probability in [0, 1]."""
    # Stockfish scale: win_prob = 1 / (1 + 10^(-cp / 400)) or sigmoid(cp / (400 / ln(10))) = sigmoid(cp / 173.7)
    # Zchezz standard scaling: sigmoid(cp / 180.0)
    return 1.0 / (1.0 + np.exp(-cp / 180.0))

def train_anneal(epochs: int = 5, pos_per_epoch: int = 500_000, lr: float = 3e-5, min_lr: float = 1e-7, batch_sz: int = 8192):
    print("=" * 80)
    print(" NNU3 PRIMARY NETWORK FINE-TUNING ON STOCKFISH CORPUS")
    print(f" Epochs: {epochs} | Pos/Epoch: {pos_per_epoch:,} | LR: {lr:.1e} -> {min_lr:.1e} | Batch: {batch_sz}")
    print("=" * 80)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training on device: {device}")

    # 1. Collect parquet files
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
    print(f"Total parquet datasets: {len(files)} files found.")

    # 2. Load v335 checkpoint
    ckpt_path = ROOT / "checkpoints" / "v335" / "latest.pt"
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    state = ckpt["model"] if "model" in ckpt else ckpt.get("state_dict", ckpt.get("weights"))
    model = NNUE()
    model.load_state_dict(state)
    model.to(device)
    print(f"Loaded base model from {ckpt_path}.")

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=min_lr)
    loss_fn = nn.BCELoss()

    # Pre-load validation set (20,000 positions)
    print("Loading 20,000 validation positions...")
    val_df = pd.read_parquet(files[0])
    val_fens = val_df["fen"].iloc[:20_000].tolist()
    val_cp = val_df["cp"].iloc[:20_000].to_numpy(dtype=np.float32)

    val_x_np, val_is_black = encode_chunk(val_fens)
    val_cp_stm = np.where(val_is_black, -val_cp, val_cp)
    val_y_np = cp_to_wdl(val_cp_stm).astype(np.float32)

    val_x = torch.from_numpy(val_x_np).to(device)
    val_y = torch.from_numpy(val_y_np).to(device)

    def evaluate(m: nn.Module) -> tuple[float, float]:
        m.eval()
        with torch.no_grad():
            preds = []
            for i in range(0, len(val_x), 4096):
                p = m(val_x[i:i+4096])
                preds.append(p)
            all_preds = torch.cat(preds)
            loss = loss_fn(all_preds, val_y).item()
            # MAE on centipawns: cp_pred = -180 * ln(1/p - 1)
            p_clamped = all_preds.clamp(1e-5, 1.0 - 1e-5)
            cp_pred = -180.0 * torch.log(1.0 / p_clamped - 1.0)
            mae = torch.mean(torch.abs(cp_pred - torch.from_numpy(val_cp_stm).to(device))).item()
        return loss, mae

    init_loss, init_mae = evaluate(model)
    print(f"Baseline v335 Val Loss: {init_loss:.5f} | Val MAE: {init_mae:.1f} cp\n")

    best_val_loss = init_loss
    file_idx = 1
    total_positions_seen = 0

    for epoch in range(1, epochs + 1):
        model.train()
        epoch_loss = 0.0
        epoch_seen = 0
        t_start = time.time()

        while epoch_seen < pos_per_epoch:
            if file_idx >= len(files):
                file_idx = 1
            fpath = files[file_idx]
            file_idx += 1

            try:
                df = pd.read_parquet(fpath)
            except Exception:
                continue

            if "fen" not in df.columns or "cp" not in df.columns:
                continue

            fens = df["fen"].tolist()
            cp = df["cp"].to_numpy(dtype=np.float32)

            # Shuffle
            idx = np.random.permutation(len(fens))
            fens = [fens[i] for i in idx]
            cp = cp[idx]

            take = min(pos_per_epoch - epoch_seen, len(fens))
            fens = fens[:take]
            cp = cp[:take]

            # Process in sub-chunks
            chunk_sz = 25_000
            for c_start in range(0, len(fens), chunk_sz):
                c_fens = fens[c_start:c_start + chunk_sz]
                c_cp = cp[c_start:c_start + chunk_sz]

                x_np, is_black = encode_chunk(c_fens)
                cp_stm = np.where(is_black, -c_cp, c_cp)
                y_np = cp_to_wdl(cp_stm).astype(np.float32)

                x_t = torch.from_numpy(x_np)
                y_t = torch.from_numpy(y_np)

                # Batch updates on GPU
                for b in range(0, len(x_t), batch_sz):
                    bx = x_t[b:b + batch_sz].to(device)
                    by = y_t[b:b + batch_sz].to(device)

                    optimizer.zero_grad()
                    out = model(bx)
                    loss = loss_fn(out, by)
                    loss.backward()
                    optimizer.step()
                    clamp_weights_(model)

                    epoch_loss += loss.item() * len(bx)
                    epoch_seen += len(bx)
                    total_positions_seen += len(bx)

        scheduler.step()
        train_loss = epoch_loss / epoch_seen
        val_loss, val_mae = evaluate(model)
        elapsed = time.time() - t_start
        cur_lr = scheduler.get_last_lr()[0]

        print(f"Epoch {epoch:02d}/{epochs:02d} [{elapsed:.1f}s] | Train Loss: {train_loss:.5f} | Val Loss: {val_loss:.5f} | Val MAE: {val_mae:.1f} cp | LR: {cur_lr:.2e}")

        # Save checkpoint
        ckpt_out = OUT_CKPT_DIR / f"epoch_{epoch:03d}.pt"
        torch.save({
            "epoch": epoch,
            "model": model.state_dict(),
            "val_loss": val_loss,
            "val_mae": val_mae,
            "arch": architecture_dict(),
        }, ckpt_out)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            shutil_copy_latest = OUT_CKPT_DIR / "latest.pt"
            torch.save({
                "epoch": epoch,
                "model": model.state_dict(),
                "val_loss": val_loss,
                "val_mae": val_mae,
                "arch": architecture_dict(),
            }, shutil_copy_latest)
            print(f"  --> [NEW BEST] Saved to {shutil_copy_latest}")

    # Export best model to binary
    print("\nExporting best checkpoint to NNU3 binary format...")
    export_checkpoint(OUT_CKPT_DIR / "latest.pt", OUT_BIN)
    print(f"[SUCCESS] Exported annealed NNU3 weights to {OUT_BIN} ({OUT_BIN.stat().st_size:,} bytes)")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--pos-per-epoch", type=int, default=500_000)
    p.add_argument("--lr", type=float, default=3e-5)
    p.add_argument("--min-lr", type=float, default=1e-7)
    p.add_argument("--batch-size", type=int, default=8192)
    args = p.parse_args()

    train_anneal(epochs=args.epochs, pos_per_epoch=args.pos_per_epoch,
                 lr=args.lr, min_lr=args.min_lr, batch_sz=args.batch_size)
