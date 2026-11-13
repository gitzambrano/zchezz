"""
tools/setup_v605_promote.py — Promote v605 as the supported secondary line representing the NNU5 family.
"""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP_DIR = ROOT / "experiments" / "v605_modern"
TARGET_DIR = ROOT / "engine" / "c" / "zchezz_v605"

# 1. Update ENGINE_VERSION in experiments/v605_modern/main.c
main_c = EXP_DIR / "main.c"
content = main_c.read_text(encoding="utf-8")
content = content.replace('#define ENGINE_VERSION "3.35"', '#define ENGINE_VERSION "6.05"')
main_c.write_text(content, encoding="utf-8")
print("[1/5] Updated ENGINE_VERSION to 6.05 in main.c")

# 2. Create engine/c/zchezz_v605 and copy engine files
TARGET_DIR.mkdir(parents=True, exist_ok=True)
files_to_copy = [
    "board.c", "board.h", "book.c", "book.h", "fast_head_weights.h",
    "main.c", "nnue.c", "nnue.h", "nnue_weights.bin", "poly_keys.h",
    "search.c", "search.h", "stdendian.h", "syzygy.c", "syzygy.h", "tbconfig.h"
]
for f in files_to_copy:
    src = EXP_DIR / f
    if src.is_file():
        shutil.copy2(src, TARGET_DIR / f)
print(f"[2/5] Copied {len(files_to_copy)} files to {TARGET_DIR.relative_to(ROOT)}")

# 3. Create checkpoints/v605 and copy latest.pt from v604
ckpt_dir = ROOT / "checkpoints" / "v605"
ckpt_dir.mkdir(parents=True, exist_ok=True)
src_pt = ROOT / "checkpoints" / "v604" / "latest.pt"
if src_pt.is_file():
    shutil.copy2(src_pt, ckpt_dir / "latest.pt")
    print(f"[3/5] Copied checkpoint to {ckpt_dir.relative_to(ROOT)}/latest.pt")
else:
    print(f"[3/5] Warning: {src_pt} not found!")

# 4. Compile zchezz_v605
print("[4/5] Compiling zchezz_v605 natively...")
cmd = [
    "gcc", "-O3", "-ffast-math", "-D_GNU_SOURCE", "-std=c11", "-mavx2",
    f"-I{TARGET_DIR}",
    "-Wno-unused-variable", "-Wno-unused-but-set-variable", "-Wno-maybe-uninitialized",
    "-Wno-misleading-indentation", "-Wno-sign-compare", "-Wno-unused-function",
    "-Wno-parentheses", "-Wno-format-truncation", "-Wno-format-overflow",
    "-DNO_TABLEBASES",
    "-o", str(TARGET_DIR / "zchezz.exe"),
    str(TARGET_DIR / "main.c"), str(TARGET_DIR / "board.c"), str(TARGET_DIR / "search.c"),
    str(TARGET_DIR / "nnue.c"), str(TARGET_DIR / "syzygy.c"), str(TARGET_DIR / "book.c"),
    "-static", "-lm", "-pthread"
]
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode != 0:
    print(f"FAILED to compile zchezz_v605:\n{res.stderr}")
    exit(1)
print(f"Compiled {TARGET_DIR / 'zchezz.exe'} ({TARGET_DIR.stat().st_size:,} bytes)")

# 5. Verify UCI output
proc = subprocess.run([str(TARGET_DIR / "zchezz.exe")], input="uci\nquit\n", capture_output=True, text=True)
print(f"[5/5] UCI output verification:\n{proc.stdout.strip()[:200]}")
