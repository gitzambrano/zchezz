#!/usr/bin/env python3
"""Fine-Tuning orchestrator for Zchezz v331_exp3 (NNU3: 799 -> 256 -> 64 -> 1).

Configuração de Treinamento:
  - Base: Melhores pesos do v331_exp1 (checkpoints/v331_exp1/latest.pt)
  - Dataset: 100% Selfplay Lookahead Quiet (data/selfplay_lookahead_filter)
  - Sem professores externos (puro selfplay da engine)
  - LR: 1e-5 -> 1e-7 (Cosine Annealing)
  - Saída: checkpoints/v331_exp3/ e artifacts/engines/v331_exp3/
"""
from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def refresh_latest():
    ckpt_dir = ROOT / "checkpoints" / "v331_exp3"
    pts = [x for x in ckpt_dir.glob("*.pt") if x.name != "latest.pt"]
    if not pts:
        return None
    newest = max(pts, key=lambda x: x.stat().st_mtime_ns)
    latest = ckpt_dir / "latest.pt"
    tmp = latest.with_suffix(".pt.tmp")
    shutil.copy2(newest, tmp)
    tmp.replace(latest)
    print(f"Atomically refreshed {latest} from {newest.name}")
    return latest

def export_weights(ckpt_path: Path):
    print("\n[Export] Exporting binary weights for v331_exp3...")
    out_dir = ROOT / "artifacts" / "engines" / "v331_exp3"
    out_dir.mkdir(parents=True, exist_ok=True)
    weights_path = out_dir / "nnue_weights.bin"

    sys.path.insert(0, str(ROOT / "train"))
    from _export_nnu3_core import export_checkpoint
    export_checkpoint(ckpt_path, weights_path)
    print(f"Exported v331_exp3 weights: {weights_path} ({weights_path.stat().st_size:,} bytes)")

    # Copy engine binary if available
    v331_src = ROOT / "artifacts" / "engines" / "v331_exp" / "zchezz.exe"
    if not v331_src.is_file():
        v331_src = ROOT / "engine" / "c" / "zchezz_v331" / "zchezz.exe"
    if v331_src.is_file():
        dst_exe = out_dir / "zchezz.exe"
        shutil.copy2(v331_src, dst_exe)
        print(f"Copied engine executable: {dst_exe}")

def parse_args():
    parser = argparse.ArgumentParser(description="Zchezz v331_exp3 Fine-Tuning (Puro Selfplay)")
    parser.add_argument("--epochs", type=int, default=40, help="Número de épocas (default: 40)")
    parser.add_argument("--batch-size", type=int, default=65536, help="Minibatch size (default: 65536)")
    parser.add_argument("--lr", type=float, default=1e-5, help="Learning rate inicial (default: 1e-5)")
    parser.add_argument("--eta-min", type=float, default=1e-7, help="Learning rate mínimo (default: 1e-7)")
    default_ckpt = "checkpoints/v331_exp3/latest.pt" if (ROOT / "checkpoints" / "v331_exp3" / "latest.pt").is_file() else "checkpoints/v331_exp1/latest.pt"
    parser.add_argument("--checkpoint", type=str, default=default_ckpt, help="Checkpoint base de partida")
    parser.add_argument("--dataset-name", type=str, default="v331_exp3_puro_selfplay", help="Dataset name tag")
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default="cpu", help="Compute device (default: cpu)")
    parser.add_argument("--workers", type=int, default=8, help="Encoding workers (default: 8)")
    return parser.parse_args()

def main():
    args = parse_args()

    print("=" * 80)
    print(" Zchezz v331_exp3 (NNU3) — Fine-Tuning Puro Selfplay")
    print(f" Base: {args.checkpoint}")
    print(f" LR: {args.lr:.1e} -> eta_min={args.eta_min:.1e} (Cosine Annealing)")
    print(" Dataset: 100% Selfplay Lookahead Quiet (data/selfplay_lookahead_filter)")
    print(f" Batch: {args.batch_size} | Dispositivo: {args.device} | Workers: {args.workers}")
    print("=" * 80)

    base_ckpt = ROOT / args.checkpoint
    if not base_ckpt.is_file():
        print(f"[ERROR] Checkpoint não encontrado: {base_ckpt}")
        return 1

    selfplay_dir = ROOT / "data" / "selfplay_lookahead_filter"
    if not selfplay_dir.is_dir():
        print(f"[ERROR] Diretório de selfplay não encontrado: {selfplay_dir}")
        return 1

    files = list(selfplay_dir.glob("*.parquet"))
    if not files:
        print("[ERROR] Nenhum arquivo parquet de selfplay encontrado")
        return 1
    print(f"  [+] Dataset Selfplay: {len(files)} shards parquet (~11.8M posições quiet)")

    sources = [
        "--source",
        "kind=parquet,path=data/selfplay_lookahead_filter,train_pct=0.60,mode=sample-files,name=selfplay_lookahead",
    ]

    ckpt_out = ROOT / "checkpoints" / "v331_exp3"
    ckpt_out.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "train" / "_train_nnu3_core.py"),
        *sources,
        "--ckpt-dir", str(ckpt_out),
        "--checkpoint-source", str(base_ckpt),
        "--dataset-name", str(args.dataset_name),
        "--epochs", str(args.epochs),
        "--batch-size", str(args.batch_size),
        "--max-positions-chunk", "250000",
        "--parquet-chunk-rows", "100000",
        "--device", str(args.device),
        "--workers", str(args.workers),
        "--lr", str(args.lr),
        "--transfer-lr", str(args.lr),
        "--eta-min", str(args.eta_min),
    ]

    print(f"\nDisparando {args.epochs} épocas de fine-tuning para v331_exp3...")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - t0

    if res.returncode != 0:
        print(f"\n[ERROR] v331_exp3 fine-tuning encerrou com erro {res.returncode}")
        return res.returncode

    print(f"\n[SUCESSO] v331_exp3 concluído em {elapsed:.1f}s ({elapsed/3600:.2f}h)!")
    latest = refresh_latest()
    if latest:
        export_weights(latest)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
