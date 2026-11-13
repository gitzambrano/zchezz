"""
tools/setup_round11_clean_candidates.py — Pure Search Tuning (without flawed QS delta).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V335_DIR = ROOT / "engine" / "c" / "zchezz_v335"
EXP_ROOT = ROOT / "experiments" / "round11_clean"
EXP_ROOT.mkdir(parents=True, exist_ok=True)

base_search = (V335_DIR / "search.c").read_text(encoding="utf-8")

def build_cand4(s: str) -> str:
    # Pure LMR history scaling: ch / 768
    old_adj = """int hist_adj = ch / 1024;"""
    new_adj = """int hist_adj = ch / 768;"""
    assert old_adj in s
    return s.replace(old_adj, new_adj)

def build_cand5(s: str) -> str:
    # Clean depth <= 4 dual cutoff (safe margin)
    old_ab = """            if (!is_pv && depth <= 3 && beta < 18000) {
                int fast_val = eval_stm_fast(b);
                if (fast_val - (depth * 90) >= beta + 110) return beta;
            }"""
    new_ab = """            if (!is_pv && depth <= 4 && beta < 18000) {
                int fast_val = eval_stm_fast(b);
                if (fast_val - (depth * 85) >= beta + 115) return beta;
            }"""
    assert old_ab in s
    return s.replace(old_ab, new_ab)

def build_cand6(s: str) -> str:
    # Cand 4 + Cand 5 combined
    s = build_cand4(s)
    s = build_cand5(s)
    return s

CONFIGS = {
    "cand4_pure_lmr": {
        "desc": "v335 + Pure LMR History (ch / 768)",
        "search_c": build_cand4(base_search),
    },
    "cand5_clean_d4": {
        "desc": "v335 + Dual-NNUE Fast Cutoff up to depth <= 4",
        "search_c": build_cand5(base_search),
    },
    "cand6_combo_clean": {
        "desc": "v335 + LMR History + Dual-NNUE Depth 4",
        "search_c": build_cand6(base_search),
    },
}

def compile_candidate(edir: Path, name: str) -> bool:
    cmd = [
        "gcc", "-O3", "-ffast-math", "-D_GNU_SOURCE", "-std=c11", "-mavx2",
        f"-I{edir}",
        "-Wno-unused-variable", "-Wno-unused-but-set-variable", "-Wno-maybe-uninitialized",
        "-Wno-misleading-indentation", "-Wno-sign-compare", "-Wno-unused-function",
        "-Wno-parentheses", "-Wno-format-truncation", "-Wno-format-overflow",
        "-DNO_TABLEBASES",
        "-o", str(edir / "zchezz.exe"),
        str(edir / "main.c"), str(edir / "board.c"), str(edir / "search.c"),
        str(edir / "nnue.c"), str(edir / "syzygy.c"), str(edir / "book.c"),
        "-static", "-lm", "-pthread"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FAILED to compile {name}:\n{res.stderr}")
        return False
    print(f"  [OK] {name} compiled successfully ({os.path.getsize(edir / 'zchezz.exe'):,} bytes)")
    return True

def main():
    print("=" * 80)
    print(" SETTING UP ROUND 11 CLEAN CANDIDATES")
    print("=" * 80)
    for name, cfg in CONFIGS.items():
        cdir = EXP_ROOT / name
        cdir.mkdir(parents=True, exist_ok=True)
        for f in V335_DIR.iterdir():
            if f.is_file() and f.name not in ["zchezz.exe", "search.c"]:
                shutil.copy2(f, cdir / f.name)
        (cdir / "search.c").write_text(cfg["search_c"], encoding="utf-8")
        compile_candidate(cdir, name)

if __name__ == "__main__":
    main()
