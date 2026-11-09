"""Central configuration and worker registry for Colab automation in Zchezz.

This module defines worker profiles, notebook URLs, CDP ports, and the resilient
bootloader template executed on Google Colab virtual machines.
"""

from pathlib import Path
from typing import Dict, Any, List

PROFILES_DIR = Path(__file__).resolve().parent / "profiles"

# Resilient Python bootloaders executed inside the Colab cell when needed.
ZQUORIDOR_BOOTLOADER_TEMPLATE = """from google.colab import drive
import os
import shutil
import subprocess
from pathlib import Path

if not Path('/content/drive/MyDrive').is_dir():
    try:
        drive.mount('/content/drive')
    except Exception as e:
        print('Initial drive mount failed, attempting force remount:', e, flush=True)
        drive.mount('/content/drive', force_remount=True)

checkout = Path('/content/zquoridor')
if not checkout.exists():
    print('Cloning repository...', flush=True)
    subprocess.run(['git', 'clone', 'https://github.com/gitzambrano/zquoridor.git', str(checkout)], check=True)
else:
    print('Updating repository to latest main...', flush=True)
    subprocess.run(['git', '-C', str(checkout), 'fetch', 'origin', 'main'], check=True)
    subprocess.run(['git', '-C', str(checkout), 'reset', '--hard', 'origin/main'], check=True)

os.chdir(checkout)

runtime_dir = Path('/content/zquoridor_runtime')
runtime_dir.mkdir(parents=True, exist_ok=True)
zq_bin = runtime_dir / 'zquoridor_uci'
print('Compiling native C++ engine (version 4.10) with AVX2 and FMA...', flush=True)
subprocess.run(['g++', '-O3', '-std=c++17', '-mavx2', '-mfma',
                '-I', str(checkout / 'src'),
                str(checkout / 'tools/external/zquoridor_uci.cpp'),
                '-o', str(zq_bin)], check=True)
zq_bin.chmod(0o755)

# Verify version 4.10 in UCI identity
chk = subprocess.run([str(zq_bin)], input='uci\\nquit\\n', capture_output=True, text=True, check=True, cwd=str(checkout))
ver_lines = [l.strip() for l in chk.stdout.splitlines() if 'id name' in l]
print('Engine verification:', ver_lines, flush=True)

# Clean stale temporary/backup files and ensure targets.npz is synchronized
output_dir = Path('{output_dir}')
if output_dir.is_dir():
    for stale_tmp in output_dir.glob('*.tmp*'):
        try:
            stale_tmp.unlink()
            print('Cleaned stale temporary file:', stale_tmp.name, flush=True)
        except Exception:
            pass
    for stale_bak in output_dir.glob('*.bak*'):
        try:
            stale_bak.unlink()
            print('Cleaned old backup file:', stale_bak.name, flush=True)
        except Exception:
            pass
    if (output_dir / 'positions.jsonl').is_file() and (output_dir / 'targets.jsonl').is_file():
        print('Verifying and synchronizing targets.npz from canonical JSONL records...', flush=True)
        subprocess.run(['python', 'tools/rebuild_npz_from_jsonl.py', '--dir', str(output_dir), '--no-backup'], check=True)

print('Launching: {job_label}', flush=True)
!{cli_command}
"""

BOOTLOADER_TEMPLATE = """from google.colab import drive
import os

if not os.path.exists('/content/drive/MyDrive'):
    drive.mount('/content/drive')

if not os.path.exists('/content/Zchezz'):
    !git clone https://github.com/gitzambrano/zchezz.git /content/Zchezz

%cd /content/Zchezz
!git pull origin main
!pip -q install python-chess numpy
!make -C /content/Zchezz/engine/build TOOLS_ENGINE={profile} ENGINE={profile} STATIC_FLAG="" selfplay native
!PROFILE={profile} ACCOUNT_ID={account_id} TARGET_POSITIONS=50000000 NODES=5000 MOVETIME=50 bash colab/run_selfplay_colab.sh
"""

V507_BOOTLOADER_TEMPLATE = """from google.colab import drive
import os

if not os.path.exists('/content/drive/MyDrive'):
    drive.mount('/content/drive')

if not os.path.exists('/content/Zchezz'):
    !git clone https://github.com/gitzambrano/zchezz.git /content/Zchezz

%cd /content/Zchezz
!git pull origin main
!pip -q install python-chess numpy
!make -C /content/Zchezz/engine/build TOOLS_ENGINE=v507 ENGINE=v507 STATIC_FLAG="" selfplay native
!PROFILE=v507 ACCOUNT_ID=1 TARGET_POSITIONS=60000000 MOVETIME=200 MOVETIME_FINAL=50 MOVETIME_PLIES=60 MOVETIME_DECAY=linear NODES=0 TEMPERATURE=1.2 TEMP_DECAY=linear TEMP_PLIES=60 TEMP_FINAL=0.02 RANDOM_PLIES=0 bash colab/run_selfplay_colab.sh
"""

TRAINING_BOOTLOADER_TEMPLATE = """from google.colab import drive
import os

if not os.path.exists('/content/drive/MyDrive'):
    drive.mount('/content/drive')

if not os.path.exists('/content/Zchezz'):
    !git clone https://github.com/gitzambrano/zchezz.git /content/Zchezz

%cd /content/Zchezz
!git fetch origin main
!git reset --hard origin/main
!pip -q install python-chess numpy torch
!PROFILE={profile} EPOCHS=100 LR=1e-5 ETA_MIN=1e-7 K=0.1 bash colab/run_train_colab.sh
"""

# Worker configurations for distributed Google Colab self-play generation in Zchezz & Zquoridor.
WORKERS: Dict[int, Dict[str, Any]] = {
    1: {
        "name": "Colab 1 (Wall Drops v4.10)",
        "worker_id": 1,
        "project": "zquoridor",
        "account": 'worker-1@example.invalid',
        "profile_dir": str(PROFILES_DIR / 'worker-1'),
        "notebook_url": 'https://colab.research.google.com/drive/NOTEBOOK_ID_1',
        "cdp_port": 9001,
        "job_label": "Wall Drops v4.10 (Medium Mazes: 3-8 walls) [Target: 1,000,000]",
        "output_dir": "/content/drive/MyDrive/zquoridor_data/wall_drops_v410/worker_1",
        "drive_dir": "/content/drive/MyDrive/zquoridor_data/wall_drops_v410/worker_1",
        "cli_command": "python -u tools/generate_wall_drops.py --count 1000000 --min-walls 3 --max-walls 8 --pawn-walk-plies 4 --move-time-ms 20 --teacher zquoridor-4.10 --zq-executable /content/zquoridor_runtime/zquoridor_uci --output /content/drive/MyDrive/zquoridor_data/wall_drops_v410/worker_1 --seed 1000001",
        "target_keywords": ["generate_wall_drops.py", "wall_drops_v410", "zquoridor", "Medium Mazes"],
        "target_shard_prefix": "wd_w1_",
        "bootloader_template": ZQUORIDOR_BOOTLOADER_TEMPLATE,
    },
    2: {
        "name": "Colab 2 (Wall Drops v4.10)",
        "worker_id": 2,
        "project": "zquoridor",
        "account": 'worker-2@example.invalid',
        "profile_dir": str(PROFILES_DIR / 'worker-2'),
        "notebook_url": 'https://colab.research.google.com/drive/NOTEBOOK_ID_2',
        "cdp_port": 9002,
        "job_label": "Wall Drops v4.10 (Extreme Mazes: 8-14 walls) [Target: 1,000,000]",
        "output_dir": "/content/drive/MyDrive/zquoridor_data/wall_drops_v410/worker_2",
        "drive_dir": "/content/drive/MyDrive/zquoridor_data/wall_drops_v410/worker_2",
        "cli_command": "python -u tools/generate_wall_drops.py --count 1000000 --min-walls 8 --max-walls 14 --pawn-walk-plies 4 --move-time-ms 20 --teacher zquoridor-4.10 --zq-executable /content/zquoridor_runtime/zquoridor_uci --output /content/drive/MyDrive/zquoridor_data/wall_drops_v410/worker_2 --seed 2000002",
        "target_keywords": ["generate_wall_drops.py", "wall_drops_v410", "zquoridor", "Extreme Mazes"],
        "target_shard_prefix": "wd_w2_",
        "bootloader_template": ZQUORIDOR_BOOTLOADER_TEMPLATE,
    },
    3: {
        "name": "Colab 3 (Gumbel Sims v4.10)",
        "worker_id": 3,
        "project": "zquoridor",
        "account": 'worker-3@example.invalid',
        "profile_dir": str(PROFILES_DIR / 'worker-3'),
        "notebook_url": 'https://colab.research.google.com/drive/NOTEBOOK_ID_3',
        "cdp_port": 9003,
        "job_label": "Gumbel AlphaZero Sequential Halving v4.10 (Top-K=8, 15ms) [Target: 50,000]",
        "output_dir": "/content/drive/MyDrive/zquoridor_data/gumbel_sims_v410/worker_3",
        "drive_dir": "/content/drive/MyDrive/zquoridor_data/gumbel_sims_v410/worker_3",
        "cli_command": "python -u tools/generate_gumbel_sims.py --count 50000 --top-k 8 --c-scale 2.0 --move-time-ms 15 --teacher zquoridor-4.10-gumbel --zq-executable /content/zquoridor_runtime/zquoridor_uci --output /content/drive/MyDrive/zquoridor_data/gumbel_sims_v410/worker_3 --seed 3000003",
        "target_keywords": ["generate_gumbel_sims.py", "gumbel_sims_v410", "zquoridor", "Sequential Halving"],
        "target_shard_prefix": "gs_w3_",
        "bootloader_template": ZQUORIDOR_BOOTLOADER_TEMPLATE,
    },
    4: {
        "name": "Colab 4 (Gumbel Sims v4.10)",
        "worker_id": 4,
        "project": "zquoridor",
        "account": 'worker-4@example.invalid',
        "profile_dir": str(PROFILES_DIR / 'worker-4'),
        "notebook_url": 'https://colab.research.google.com/drive/NOTEBOOK_ID_4',
        "cdp_port": 9004,
        "job_label": "Gumbel AlphaZero Sequential Halving v4.10 (Top-K=8, 15ms) [Target: 50,000]",
        "output_dir": "/content/drive/MyDrive/zquoridor_data/gumbel_sims_v410/worker_4",
        "drive_dir": "/content/drive/MyDrive/zquoridor_data/gumbel_sims_v410/worker_4",
        "cli_command": "python -u tools/generate_gumbel_sims.py --count 50000 --top-k 8 --c-scale 2.0 --move-time-ms 15 --teacher zquoridor-4.10-gumbel --zq-executable /content/zquoridor_runtime/zquoridor_uci --output /content/drive/MyDrive/zquoridor_data/gumbel_sims_v410/worker_4 --seed 4000004",
        "target_keywords": ["generate_gumbel_sims.py", "gumbel_sims_v410", "zquoridor", "Sequential Halving"],
        "target_shard_prefix": "gs_w4_",
        "bootloader_template": ZQUORIDOR_BOOTLOADER_TEMPLATE,
    },
    5: {
        "name": "Colab 5 (Gumbel Deep Planning v4.10)",
        "worker_id": 5,
        "project": "zquoridor",
        "account": 'worker-5@example.invalid',
        "profile_dir": str(PROFILES_DIR / 'worker-5'),
        "notebook_url": 'https://colab.research.google.com/drive/NOTEBOOK_ID_5',
        "cdp_port": 9005,
        "job_label": "Gumbel Deep Planning v4.10 (Top-K=16, 20ms) [Target: 50,000]",
        "output_dir": "/content/drive/MyDrive/zquoridor_data/gumbel_sims_v410/worker_5",
        "drive_dir": "/content/drive/MyDrive/zquoridor_data/gumbel_sims_v410/worker_5",
        "cli_command": "python -u tools/generate_gumbel_sims.py --count 50000 --top-k 16 --c-scale 2.5 --move-time-ms 20 --teacher zquoridor-4.10-gumbel --zq-executable /content/zquoridor_runtime/zquoridor_uci --output /content/drive/MyDrive/zquoridor_data/gumbel_sims_v410/worker_5 --seed 5000005",
        "target_keywords": ["generate_gumbel_sims.py", "gumbel_sims_v410", "zquoridor", "Deep Planning"],
        "target_shard_prefix": "gs_w5_",
        "bootloader_template": ZQUORIDOR_BOOTLOADER_TEMPLATE,
    },
}

WORKERS.update({
    6: {
        "name": "Colab 6 (Zchezz v331)",
        "worker_id": 6,
        "project": "zchezz",
        "profile": "v331",
        "account_id": 2,
        "account": 'worker-6@example.invalid',
        "profile_dir": str(PROFILES_DIR / "worker-6"),
        "notebook_url": 'https://colab.research.google.com/drive/NOTEBOOK_ID_6',
        "cdp_port": 9331,
        "job_label": "Zchezz v331 Selfplay [Target: 50,000,000]",
        "output_dir": "/content/drive/MyDrive/zchezz_data/selfplay_v331",
        "drive_dir": "/content/drive/MyDrive/zchezz_data/selfplay_v331",
        "target_keywords": ["Remessa 2", "sp_v331", "zchezz", "run_selfplay_colab.sh"],
        "target_shard_prefix": "sp_v331_",
        "bootloader_template": BOOTLOADER_TEMPLATE,
    },
    7: {
        "name": "Colab 7 (Zchezz v507)",
        "worker_id": 7,
        "project": "zchezz",
        "profile": "v507",
        "account_id": 1,
        "account": 'worker-7@example.invalid',
        "profile_dir": str(PROFILES_DIR / "worker-7"),
        "notebook_url": 'https://colab.research.google.com/drive/NOTEBOOK_ID_7',
        "cdp_port": 9507,
        "job_label": "Zchezz v507 Selfplay [Target: 60,000,000]",
        "output_dir": "/content/drive/MyDrive/zchezz_data/selfplay_v507",
        "drive_dir": "/content/drive/MyDrive/zchezz_data/selfplay_v507",
        "target_keywords": ["Remessa 2", "sp_v507", "zchezz", "run_selfplay_colab.sh"],
        "target_shard_prefix": "sp_v507_",
        "bootloader_template": V507_BOOTLOADER_TEMPLATE,
    },
})

# Aliases mapping worker strings/names to canonical integer IDs
WORKER_ALIASES: Dict[Any, int] = {
    1: 1,
    "1": 1,
    "c1": 1,
    "colab1": 1,
    2: 2,
    "2": 2,
    "c2": 2,
    "colab2": 2,
    3: 3,
    "3": 3,
    "c3": 3,
    "colab3": 3,
    4: 4,
    "4": 4,
    "c4": 4,
    "colab4": 4,
    5: 5,
    "5": 5,
    "c5": 5,
    "colab5": 5,
    6: 6,
    "6": 6,
    "c6": 6,
    "colab6": 6,
    "v331": 6,
    "zchezz": 6,
    'worker-6': 6,
    7: 7,
    "7": 7,
    "c7": 7,
    "colab7": 7,
    "v507": 7,
    "zbrain": 7,
    'worker-7': 7,
}


def resolve_worker_key(key: Any) -> int:
    """Normalize input worker identifier to canonical integer worker ID."""
    if key in WORKER_ALIASES:
        return WORKER_ALIASES[key]
    key_str = str(key).strip().lower()
    if key_str in WORKER_ALIASES:
        return WORKER_ALIASES[key_str]
    try:
        val = int(key_str)
        if val in WORKERS:
            return val
    except ValueError:
        pass
    raise ValueError(f"Unknown worker identifier: {key}. Supported: {list(WORKERS.keys())}")


def get_all_worker_keys() -> List[int]:
    """Return all canonical worker IDs."""
    return list(WORKERS.keys())



from colab.private import apply_accounts
apply_accounts(WORKERS, 'zchezz')
