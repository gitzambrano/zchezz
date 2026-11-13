"""
tools/setup_round10_candidates.py — Set up and compile Round 10 Candidates (Pushing towards 2900).

Candidates:
1. cand1_fast_delta_qs: Base v335 + Fast Delta Pruning in QS (fast_val + delta < alpha - 200).
2. cand2_extended_dual: Base v335 + Fast Delta QS + Extended Fast Cutoff in alpha-beta (depth <= 5).
3. cand3_gm_combo: Base v335 + Fast Delta QS + Extended Fast Cutoff + LMR History (ch / 768).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V335_DIR = ROOT / "engine" / "c" / "zchezz_v335"
EXP_ROOT = ROOT / "experiments" / "round10_2900"
EXP_ROOT.mkdir(parents=True, exist_ok=True)

base_search = (V335_DIR / "search.c").read_text(encoding="utf-8")

def build_cand1(s: str) -> str:
    # Fast Delta Pruning in QS
    old_qs = """        int fast_val = eval_stm_fast(b);
        if (fast_val >= beta + 200) return beta;
        stand = eval_stm(b);"""
    new_qs = """        int fast_val = eval_stm_fast(b);
        if (fast_val >= beta + 200) return beta;
        int has_passer = (b->turn==COL_W) ? !!(b->bb[0] & 0x000000000000FF00ULL)
                                           : !!(b->bb[6] & 0x00FF000000000000ULL);
        int delta_margin = has_passer ? MV_TAB[5]*2+50 : MV_TAB[5]+50;
        if (fast_val + delta_margin < alpha - 200) return alpha;
        stand = eval_stm(b);"""
    assert old_qs in s, "old_qs not found in build_cand1"
    return s.replace(old_qs, new_qs)

def build_cand2(s: str) -> str:
    # Cand 1 + Extended Fast Cutoff in alpha_beta up to depth 5
    s = build_cand1(s)
    old_ab = """            if (!is_pv && depth <= 3 && beta < 18000) {
                int fast_val = eval_stm_fast(b);
                if (fast_val - (depth * 90) >= beta + 110) return beta;
            }"""
    new_ab = """            if (!is_pv && depth <= 5 && beta < 18000) {
                int fast_val = eval_stm_fast(b);
                if (fast_val - (depth * 80) >= beta + 115) return beta;
            }"""
    assert old_ab in s, "old_ab not found in build_cand2"
    return s.replace(old_ab, new_ab)

def build_cand3(s: str) -> str:
    # Cand 2 + LMR history scaling (ch / 768)
    s = build_cand2(s)
    old_adj = """int hist_adj = ch / 1024;"""
    new_adj = """int hist_adj = ch / 768;"""
    assert old_adj in s, "old_adj not found in build_cand3"
    return s.replace(old_adj, new_adj)

CONFIGS = {
    "cand1_fast_delta_qs": {
        "desc": "Base v335 + Fast Delta Pruning in QS",
        "search_c": build_cand1(base_search),
    },
    "cand2_extended_dual": {
        "desc": "Cand1 + Extended Fast Cutoff in alpha_beta (depth <= 5)",
        "search_c": build_cand2(base_search),
    },
    "cand3_gm_combo": {
        "desc": "Cand2 + Dynamic LMR History scaling (ch / 768)",
        "search_c": build_cand3(base_search),
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
    print(" SETTING UP ROUND 10 (2900 PUSH) CANDIDATES")
    print("=" * 80)

    for name, cfg in CONFIGS.items():
        cdir = EXP_ROOT / name
        cdir.mkdir(parents=True, exist_ok=True)
        # Copy common files from v335
        for f in V335_DIR.iterdir():
            if f.is_file() and f.name not in ["zchezz.exe", "search.c"]:
                shutil.copy2(f, cdir / f.name)
        # Write modified search.c
        (cdir / "search.c").write_text(cfg["search_c"], encoding="utf-8")
        # Compile
        ok = compile_candidate(cdir, name)
        status = "COMPILED OK" if ok else "COMPILE ERROR"
        print(f"  {name:25s}: {cfg['desc']:55s} -> {status}")

    print("=" * 80)
    print(" Round 10 candidates setup complete.")

if __name__ == "__main__":
    main()
