"""Central configuration and worker registry for Colab automation in Zchezz.

This module defines worker profiles, notebook URLs, CDP ports, and the resilient
bootloader template executed on Google Colab virtual machines.
"""

from typing import Dict, Any, List

# Worker configurations for distributed Google Colab self-play generation.
WORKERS: Dict[str, Dict[str, Any]] = {
    "v331": {
        "name": "Colab v331",
        "worker_id": "v331",
        "profile": "v331",
        "account_id": 2,
        "account": "zchezzproject@gmail.com",
        "profile_dir": r"C:\Projetos\TikTok\profiles\zchezzproject",
        "notebook_url": "https://colab.research.google.com/drive/1j8-gG7qApv--t2DBM8tf1gmgKjuUXiLC",
        "cdp_port": 9331,
        "target_keywords": ["Remessa 2", "sp_v331_r2", "v331", "run_colab_arena", "zchezz"],
        "target_shard_prefix": "sp_v331_r2",
    },
    "v507": {
        "name": "Colab v507",
        "worker_id": "v507",
        "profile": "v507",
        "account_id": 1,
        "account": "zbrainproject@gmail.com",
        "profile_dir": r"C:\Projetos\TikTok\profiles\zbrainproject",
        "notebook_url": "https://colab.research.google.com/drive/1WaoYFjPIl70cECrs9CGZEwEoMxVzBEp8",
        "cdp_port": 9507,
        "target_keywords": ["Remessa 2", "sp_v507_r2", "v507", "zchezz"],
        "target_shard_prefix": "sp_v507_r2",
    },
}

# Aliases mapping account IDs or numeric indexes to worker keys
WORKER_ALIASES: Dict[Any, str] = {
    1: "v507",
    "1": "v507",
    2: "v331",
    "2": "v331",
    "v331": "v331",
    "v507": "v507",
}


def resolve_worker_key(key: Any) -> str:
    """Normalize input worker identifier to canonical worker key."""
    if key in WORKER_ALIASES:
        return WORKER_ALIASES[key]
    key_str = str(key).strip().lower()
    if key_str in WORKER_ALIASES:
        return WORKER_ALIASES[key_str]
    if key_str in WORKERS:
        return key_str
    raise ValueError(f"Unknown worker identifier: {key}. Supported: {list(WORKERS.keys())}")


def get_all_worker_keys() -> List[str]:
    """Return all canonical worker keys."""
    return list(WORKERS.keys())


# Resilient Python bootloader executed inside the Colab cell when needed.
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
!PROFILE={profile} ACCOUNT_ID={account_id} bash colab/run_selfplay_colab.sh
"""
