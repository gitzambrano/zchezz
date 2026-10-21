"""
tools/setup_cand_v336.py — Setup and compile cand_v336_sf_anneal.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V335_DIR = ROOT / "engine" / "c" / "zchezz_v335"
CAND_DIR = ROOT / "experiments" / "cand_v336_sf_anneal"
CAND_DIR.mkdir(parents=True, exist_ok=True)

# 1. Copy common files from v335
for f in V335_DIR.iterdir():
    if f.is_file() and f.name not in ["zchezz.exe", "nnue_weights.bin", "fast_head_weights.h"]:
        shutil.copy2(f, CAND_DIR / f.name)

# 2. Copy new primary weights and auxiliary head weights
shutil.copy2(ROOT / "artifacts" / "nnue_weights_v336.bin", CAND_DIR / "nnue_weights.bin")
shutil.copy2(ROOT / "artifacts" / "fast_head_weights_v336.h", CAND_DIR / "fast_head_weights.h")

# 3. Compile
cmd = [
    "gcc", "-O3", "-ffast-math", "-D_GNU_SOURCE", "-std=c11", "-mavx2",
    f"-I{CAND_DIR}",
    "-Wno-unused-variable", "-Wno-unused-but-set-variable", "-Wno-maybe-uninitialized",
    "-Wno-misleading-indentation", "-Wno-sign-compare", "-Wno-unused-function",
    "-Wno-parentheses", "-Wno-format-truncation", "-Wno-format-overflow",
    "-DNO_TABLEBASES",
    "-o", str(CAND_DIR / "zchezz.exe"),
    str(CAND_DIR / "main.c"), str(CAND_DIR / "board.c"), str(CAND_DIR / "search.c"),
    str(CAND_DIR / "nnue.c"), str(CAND_DIR / "syzygy.c"), str(CAND_DIR / "book.c"),
    "-static", "-lm", "-pthread"
]

print("Compiling cand_v336_sf_anneal...")
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode != 0:
    print(f"FAILED to compile:\n{res.stderr}")
else:
    print(f"[OK] cand_v336_sf_anneal compiled successfully ({os.path.getsize(CAND_DIR / 'zchezz.exe'):,} bytes)")
