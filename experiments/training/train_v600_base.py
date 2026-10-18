"""train/train_v600_base.py — Phase 1: Train fresh NNUE5 architecture on base/warmup data."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def main():
    print("=================================================================")
    print(" Zchezz v600 (NNUE5) — Phase 1: Base Warmup Training on CUDA")
    print("=================================================================")
    
    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "train" / "_train_nnu5_core.py"),
        "--source", "kind=parquet,path=data/extraquiet_cp_sf5k_res_filter,train_pct=0.15,name=extraquiet_5k",
        "--source", "kind=parquet,path=data/lichess_cp_sfdb_filter,train_pct=0.20,name=lichess_sfdb",
        "--source", "kind=parquet,path=data/extraquiet_cp_sfd14_endgames_filter,train_pct=1.0,name=endgames_d14",
        "--ckpt-dir", "checkpoints/v600",
        "--dataset-name", "v600_base_warmup",
        "--epochs", "10",
        "--batch-size", "32768",
        "--device", "cuda",
        "--lr", "1e-3",
        "--transfer-lr", "1e-3",
        "--eta-min", "1e-5",
    ]
    
    print("Executing command:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=str(ROOT))
    if res.returncode != 0:
        print(f"Error: Phase 1 training exited with code {res.returncode}")
        return res.returncode
        
    # Refresh latest.pt atomically
    ckpt_dir = ROOT / "checkpoints" / "v600"
    pts = [x for x in ckpt_dir.glob("*.pt") if x.name != "latest.pt"]
    if pts:
        newest = max(pts, key=lambda x: x.stat().st_mtime_ns)
        latest = ckpt_dir / "latest.pt"
        tmp = latest.with_suffix(".pt.tmp")
        shutil.copy2(newest, tmp)
        tmp.replace(latest)
        print(f"Successfully refreshed {latest} from {newest}")

    print("=================================================================")
    print(" Phase 1: Base Warmup Training Complete!")
    print("=================================================================")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
