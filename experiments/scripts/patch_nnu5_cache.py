#!/usr/bin/env python3
"""Promote existing valid HalfKAv2-32b encoded caches to official _encoded_nnu5.pt files.

This updates data/selfplay_lookahead_filter, data/selfplay_v331_filter, and
data/selfplay_v507_filter by adding 'encoding': 'halfka_v2_hm_32b' and saving
as <stem>_encoded_nnu5.pt.
"""
from __future__ import annotations
import glob
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import torch

ROOT = Path(__file__).resolve().parents[1]

def patch_file(fpath: str) -> bool:
    target_path = fpath.replace("_encoded.pt", "_encoded_nnu5.pt")
    if os.path.exists(target_path):
        return True
    try:
        data = torch.load(fpath, map_location="cpu", weights_only=False)
        if int(data["stm_idx"].max()) < 20000:
            return False  # Not an NNU5 cache
        data["encoding"] = "halfka_v2_hm_32b"
        torch.save(data, target_path)
        return True
    except Exception as e:
        print(f"Error on {fpath}: {e}")
        return False

def main():
    dirs = [
        ROOT / "data" / "selfplay_lookahead_filter",
        ROOT / "data" / "selfplay_v331_filter",
        ROOT / "data" / "selfplay_v507_filter",
    ]
    files = []
    for d in dirs:
        found = list(d.glob("*_encoded.pt"))
        files.extend([str(p) for p in found if not p.name.endswith("_encoded_nnu5.pt")])

    print(f"Found {len(files)} valid NNU5 cache files to promote...")
    t0 = time.time()
    success = 0
    with ProcessPoolExecutor(max_workers=4) as executor:
        for ok in executor.map(patch_file, files):
            if ok:
                success += 1

    elapsed = time.time() - t0
    print(f"Successfully promoted {success}/{len(files)} cache files to _encoded_nnu5.pt in {elapsed:.1f}s!")

if __name__ == "__main__":
    main()
