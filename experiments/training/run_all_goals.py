"""Automated master orchestrator for training and fine-tuning all 3 networks (v600, v507, v331)."""

import glob
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def run_cmd(cmd, desc):
    print(f"\n{'='*75}")
    print(f" >>> [RUN] {desc}")
    print(f" {' '.join(cmd)}")
    print(f"{'='*75}")
    t0 = time.time()
    res = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = time.time() - t0
    if res.returncode != 0:
        print(f" [ERROR] {desc} failed with exit code {res.returncode} (took {elapsed:.1f}s)")
        raise RuntimeError(f"{desc} failed")
    print(f" >>> [SUCCESS] {desc} completed in {elapsed:.1f}s")
    return res

def refresh_latest(profile):
    ckpt_dir = ROOT / "checkpoints" / profile
    pts = [x for x in ckpt_dir.glob("*.pt") if x.name != "latest.pt"]
    if not pts:
        return
    newest = max(pts, key=lambda x: x.stat().st_mtime_ns)
    latest = ckpt_dir / "latest.pt"
    tmp = latest.with_suffix(".pt.tmp")
    shutil.copy2(newest, tmp)
    tmp.replace(latest)
    print(f"Atomically refreshed {latest} from {newest}")

def export_weights(profile):
    print(f"\n[Export] Exporting binary weights for {profile}...")
    cmd = [sys.executable, str(ROOT / "train" / "export.py"), "--profile", profile]
    run_cmd(cmd, f"Export binary weights for {profile}")
    weights_path = ROOT / "engine" / "c" / f"zchezz_{profile}" / "nnue_weights.bin"
    assert weights_path.is_file(), f"Expected binary weights at {weights_path}"
    size = weights_path.stat().st_size
    print(f"Verified weights: {weights_path} ({size:,} bytes)")

def step_wait_v600_base():
    print("\n[Step 1/4] Checking v600 Phase 1 (Base Warmup) status...")
    ckpt_dir = ROOT / "checkpoints" / "v600"
    for _ in range(120):
        ep10 = list(ckpt_dir.glob("*epoch10*.pt"))
        if ep10:
            print(f"Found Phase 1 completion checkpoint: {ep10[0].name}")
            refresh_latest("v600")
            return
        time.sleep(10)
    print("Warning: Timeout waiting for epoch10 checkpoint; checking newest checkpoint...")
    refresh_latest("v600")

def step_v600_finetune():
    print("\n[Step 2/4] Checking/Running v600 Phase 2: Fine-Tuning with recent selfplay data...")
    ckpt_dir = ROOT / "checkpoints" / "v600"
    for _ in range(400):
        ep20 = list(ckpt_dir.glob("*finetune*epoch20*.pt"))
        if ep20:
            print(f"Found Phase 2 completion checkpoint: {ep20[0].name}")
            refresh_latest("v600")
            export_weights("v600")
            return
        # Check if process is already running
        running = False
        try:
            import psutil
            for p in psutil.process_iter(['name', 'cmdline']):
                cmdline = " ".join(p.info.get('cmdline') or [])
                if 'train_v600_finetune' in cmdline or '_train_nnu5_core' in cmdline:
                    running = True
                    break
        except Exception:
            pass

        if not running:
            cmd = [sys.executable, "-u", str(ROOT / "train" / "train_v600_finetune.py")]
            run_cmd(cmd, "v600 Fine-Tuning (NNUE5)")
            refresh_latest("v600")
            export_weights("v600")
            return
        time.sleep(15)
    refresh_latest("v600")
    export_weights("v600")

def step_v507_finetune():
    print("\n[Step 3/4] Running v507 Fine-Tuning with recent selfplay data...")
    ckpt_dir = ROOT / "checkpoints" / "v507"
    latest = ckpt_dir / "latest.pt"
    assert latest.is_file(), f"Missing {latest}"

    # Selfplay sources for NNU4
    bin_patterns = ["data/lc0_t91_big_q/*.bin", "data/lc0_t91_big_res4/*.bin"]
    sources = []
    for pat in bin_patterns:
        if glob.glob(str(ROOT / pat)):
            sources.extend(["--source", f"kind=bin,path={pat},k=0.1,name={Path(pat).parent.name}"])
    sources.extend([
        "--source", "kind=parquet,path=data/selfplay_cp_sf50k_res_filter_data20260410,train_pct=0.25,name=selfplay_sf50k",
        "--source", "kind=parquet,path=data/selfplay_cp_sf100k_res_endgames_filter_data20260414,train_pct=0.50,name=selfplay_endgames_100k",
        "--source", "kind=parquet,path=data/synthetic_endgame_cp_sf_filter_data20260414,train_pct=1.00,name=synth_endgames",
    ])

    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "train" / "_train_nnu4_core.py"),
        *sources,
        "--ckpt-dir", "checkpoints/v507",
        "--checkpoint-source", str(latest),
        "--dataset-name", "v507_finetune_recent",
        "--epochs", "20",
        "--batch-size", "32768",
        "--device", "cuda",
        "--lr", "1e-5",
        "--transfer-lr", "1e-5",
        "--eta-min", "1e-7",
    ]
    run_cmd(cmd, "v507 Fine-Tuning (NNU4)")
    refresh_latest("v507")
    export_weights("v507")

def step_v331_finetune():
    print("\n[Step 4/4] Running v331 Fine-Tuning with recent selfplay data...")
    ckpt_dir = ROOT / "checkpoints" / "v331"
    latest = ckpt_dir / "latest.pt"
    assert latest.is_file(), f"Missing {latest}"

    bin_patterns = ["data/lc0_t91_big_q/*.bin", "data/lc0_t91_big_res4/*.bin"]
    sources = []
    for pat in bin_patterns:
        if glob.glob(str(ROOT / pat)):
            sources.extend(["--source", f"kind=bin,path={pat},pct=0.2,k=0.1"])
    sources.extend([
        "--source", "kind=parquet,path=data/selfplay_cp_sf50k_res_filter_data20260410,pct=0.2,mode=sample-files,lam=0.0",
        "--source", "kind=parquet,path=data/selfplay_cp_sf100k_res_endgames_filter_data20260414,pct=0.5,mode=sample-files,lam=0.0",
    ])

    cmd = [
        sys.executable,
        "-u",
        str(ROOT / "train" / "_train_nnu3_core.py"),
        *sources,
        "--ckpt-dir", "checkpoints/v331",
        "--checkpoint-source", str(latest),
        "--dataset-name", "v331_finetune_recent",
        "--epochs", "20",
        "--batch-size", "16384",
        "--device", "cuda",
        "--lr", "1e-5",
        "--transfer-lr", "1e-5",
        "--eta-min", "1e-7",
    ]
    run_cmd(cmd, "v331 Fine-Tuning (NNU3)")
    refresh_latest("v331")
    export_weights("v331")

def main():
    print("=======================================================================")
    print(" Zchezz Master Multi-Architecture Training Pipeline (v600, v507, v331)")
    print("=======================================================================")
    
    # 1. Wait for Phase 1 of v600
    step_wait_v600_base()

    # 2. Run Phase 2 fine-tuning for v600
    step_v600_finetune()

    # 3. Run fine-tuning for v507
    step_v507_finetune()

    # 4. Run fine-tuning for v331
    step_v331_finetune()

    # 5. Contract tests validation
    print("\n[Validation] Running repository contract tests...")
    test_cmd = [sys.executable, str(ROOT / "tests" / "test_repository_contracts.py")]
    run_cmd(test_cmd, "Repository Contract Tests")

    print("\n=======================================================================")
    print(" ALL 3 ARCHITECTURES (v600, v507, v331) FULLY TRAINED AND EXPORTED!")
    print("=======================================================================")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
