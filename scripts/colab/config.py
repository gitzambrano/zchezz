"""Central configuration and worker registry for Colab automation in Zchezz.

This module defines worker profiles, notebook URLs, CDP ports, and the resilient
bootloader template executed on Google Colab virtual machines.
"""

from typing import Dict, Any, List

# Resilient Python bootloaders executed inside the Colab cell when needed.
ZQUORIDOR_BOOTLOADER_TEMPLATE = """from google.colab import drive
import os

if not os.path.exists('/content/drive/MyDrive'):
    drive.mount('/content/drive')

if not os.path.exists('/content/zquoridor'):
    !git clone https://github.com/gitzambrano/zquoridor.git /content/zquoridor

%cd /content/zquoridor
!git pull origin main
!bash build/build_selfplay.sh
!python tools/selfplay/run_colab_worker.py --worker-id {worker_id} --drive-dir {drive_dir} --positions {positions}
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
!PROFILE={profile} ACCOUNT_ID={account_id} TARGET_POSITIONS=20000000 NODES=5000 MOVETIME=50 bash colab/run_selfplay_colab.sh
"""

# Worker configurations for distributed Google Colab self-play generation in Zchezz & Zquoridor.
WORKERS: Dict[int, Dict[str, Any]] = {
    1: {
        "name": "Colab 1 (Zquoridor)",
        "worker_id": 1,
        "project": "zquoridor",
        "account": "gustavozambrano@gmail.com",
        "profile_dir": r"C:\Projetos\TikTok\profiles\gustavozambrano",
        "notebook_url": "https://colab.research.google.com/drive/13O4yYpM8ElgOFzo774Jps488DAPzIbDT",
        "cdp_port": 9001,
        "target_keywords": ["run_colab_worker.py", "selfplay_central", "zquoridor"],
        "target_shard_prefix": "c1_",
        "drive_dir": "/content/drive/MyDrive/zquoridor_data/selfplay_central",
        "positions": "tools/external/openings_center_rush_sound_5k.jsonl",
        "bootloader_template": ZQUORIDOR_BOOTLOADER_TEMPLATE,
    },
    2: {
        "name": "Colab 2 (Zquoridor)",
        "worker_id": 2,
        "project": "zquoridor",
        "account": "flightdyn@gmail.com",
        "profile_dir": r"C:\Projetos\TikTok\profiles\flightdyn",
        "notebook_url": "https://colab.research.google.com/drive/1rPSnvqg7stxwU5V8ITgpGVv02j7qVsD1",
        "cdp_port": 9002,
        "target_keywords": ["run_colab_worker.py", "selfplay_irregular", "zquoridor"],
        "target_shard_prefix": "c2_",
        "drive_dir": "/content/drive/MyDrive/zquoridor_data/selfplay_irregular",
        "positions": "tools/external/openings_irregular_bank.jsonl",
        "bootloader_template": ZQUORIDOR_BOOTLOADER_TEMPLATE,
    },
    3: {
        "name": "Colab 3",
        "worker_id": 3,
        "profile": "v507",
        "account_id": 3,
        "account": "zambraprojects@gmail.com",
        "profile_dir": r"C:\Projetos\TikTok\profiles\zambraprojects",
        "notebook_url": "https://colab.research.google.com/drive/1tTPVhIs4Jq0Qr1yHNPRfBDtohE3EjX9E",
        "cdp_port": 9003,
        "target_keywords": ["Remessa 2", "sp_v507", "zchezz", "run_selfplay_colab.sh", "run_colab_worker.py"],
        "target_shard_prefix": "sp_v507_a3_",
        "bootloader_template": BOOTLOADER_TEMPLATE,
    },
    4: {
        "name": "Colab 4",
        "worker_id": 4,
        "profile": "v507",
        "account_id": 4,
        "account": "zquoridor@gmail.com",
        "profile_dir": r"C:\Projetos\TikTok\profiles\zquoridor",
        "notebook_url": "https://colab.research.google.com/drive/1nC1LOjwFm1LyeJtx4kxg6T7wQXym9FnA",
        "cdp_port": 9004,
        "target_keywords": ["Remessa 2", "sp_v507", "zchezz", "run_selfplay_colab.sh", "run_colab_worker.py"],
        "target_shard_prefix": "sp_v507_a4_",
        "bootloader_template": BOOTLOADER_TEMPLATE,
    },
    5: {
        "name": "Colab 5",
        "worker_id": 5,
        "profile": "v507",
        "account_id": 5,
        "account": "gustati2201@gmail.com",
        "profile_dir": r"C:\Projetos\TikTok\profiles\gustati2201",
        "notebook_url": "https://colab.research.google.com/drive/1cPMl8_zEi-el5GAE8sv2Bw3T6uKDwK1i",
        "cdp_port": 9005,
        "target_keywords": ["Remessa 2", "sp_v507", "zchezz", "run_selfplay_colab.sh", "run_colab_worker.py"],
        "target_shard_prefix": "sp_v507_a5_",
        "bootloader_template": BOOTLOADER_TEMPLATE,
    },
    6: {
        "name": "Colab 6 (v331)",
        "worker_id": 6,
        "profile": "v331",
        "account_id": 2,
        "account": "zchezzproject@gmail.com",
        "profile_dir": r"C:\Projetos\TikTok\profiles\zchezzproject",
        "notebook_url": "https://colab.research.google.com/drive/1j8-gG7qApv--t2DBM8tf1gmgKjuUXiLC",
        "cdp_port": 9331,
        "target_keywords": ["Remessa 2", "sp_v331_r2", "zchezz", "run_selfplay_colab.sh"],
        "target_shard_prefix": "sp_v331_r2",
        "bootloader_template": BOOTLOADER_TEMPLATE,
    },
    7: {
        "name": "Colab 7 (v507)",
        "worker_id": 7,
        "profile": "v507",
        "account_id": 1,
        "account": "zbrainproject@gmail.com",
        "profile_dir": r"C:\Projetos\TikTok\profiles\zbrainproject",
        "notebook_url": "https://colab.research.google.com/drive/1WaoYFjPIl70cECrs9CGZEwEoMxVzBEp8",
        "cdp_port": 9507,
        "target_keywords": ["Remessa 2", "sp_v507_r2", "zchezz", "run_selfplay_colab.sh"],
        "target_shard_prefix": "sp_v507_r2",
        "bootloader_template": BOOTLOADER_TEMPLATE,
    },
}

# Aliases mapping account IDs or numeric/string keys to canonical integer IDs
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
    "zchezzproject": 6,
    7: 7,
    "7": 7,
    "c7": 7,
    "colab7": 7,
    "v507": 7,
    "zbrain": 7,
    "zbrainproject": 7,
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

