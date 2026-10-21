"""
tools/setup_round9_experiments.py — Set up and compile Round 9 Experiments (Pushing towards 2900).

Candidates:
1. exp22_fast_delta_qs: Fast Delta Pruning in QS using Dual-NNUE (fast_val + delta_margin < alpha - 200).
2. exp23_quiet_see_ordering: Demote quiet blunders in move ordering if SEE < 0.
3. exp24_lmr_history_tuning: More responsive LMR history adjustment (ch / 768).
4. exp25_rfp_improving_tune: Dynamic RFP margin tuned with improving flag (depth*70 - (improving ? 45 : 0)).
5. exp26_combo_2900: Combined Grand Master candidate with all synergies.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V335_DIR = ROOT / "engine" / "c" / "zchezz_v335"
EXP_ROOT = ROOT / "experiments" / "round9_2900"
EXP_ROOT.mkdir(parents=True, exist_ok=True)

base_search = (V335_DIR / "search.c").read_text(encoding="utf-8")

def build_exp22(s: str) -> str:
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
    assert old_qs in s, "old_qs not found in build_exp22"
    return s.replace(old_qs, new_qs)

def build_exp23(s: str) -> str:
    # Demote quiet moves with negative SEE
    old_quiet_score = """    int ft = mfr*64 + mto;
    uint8_t piece = b[mfr];"""
    new_quiet_score = """    /* Bad quiet move demotion: demote quiet blunders below safe quiets */
    int sv = see_board(bd, mfr, mto, 0);
    if (sv < 0) return 150000 + sv;
    int ft = mfr*64 + mto;
    uint8_t piece = b[mfr];"""
    assert old_quiet_score in s, "old_quiet_score not found in build_exp23"
    return s.replace(old_quiet_score, new_quiet_score)

def build_exp24(s: str) -> str:
    # LMR history scaling
    old_adj = """int hist_adj = ch / 1024;"""
    new_adj = """int hist_adj = ch / 768;"""
    assert old_adj in s, "old_adj not found in build_exp24"
    return s.replace(old_adj, new_adj)

def build_exp25(s: str) -> str:
    # RFP improving tune
    old_rfp = """        int rfp_margin = depth*75 - (improving ? 40 : 0);"""
    new_rfp = """        int rfp_margin = depth*70 - (improving ? 45 : 0);"""
    assert old_rfp in s, "old_rfp not found in build_exp25"
    return s.replace(old_rfp, new_rfp)

def build_exp26(s: str) -> str:
    # Combo 2900: combines exp22 + exp23 + exp24 + exp25
    s = build_exp22(s)
    s = build_exp23(s)
    s = build_exp24(s)
    s = build_exp25(s)
    return s

CONFIGS = {
    "exp22_fast_delta_qs": {
        "desc": "Fast Delta Pruning in QS using Dual-NNUE",
        "search_c": build_exp22(base_search),
    },
    "exp23_quiet_see_ordering": {
        "desc": "Bad quiet move demotion in move ordering (SEE < 0)",
        "search_c": build_exp23(base_search),
    },
    "exp24_lmr_history_tuning": {
        "desc": "Enhanced LMR history adjustment (ch / 768)",
        "search_c": build_exp24(base_search),
    },
    "exp25_rfp_improving_tune": {
        "desc": "Tuned RFP margin with improving flag (depth*70 - 45)",
        "search_c": build_exp25(base_search),
    },
    "exp26_combo_2900": {
        "desc": "Grand Master Combo (Fast Delta + Quiet SEE Order + LMR History + RFP Tune)",
        "search_c": build_exp26(base_search),
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
    print(f"=== Setting up and compiling {len(CONFIGS)} Round 9 Candidates ===")
    for name, cfg in CONFIGS.items():
        edir = EXP_ROOT / name
        edir.mkdir(parents=True, exist_ok=True)
        for item in V335_DIR.glob("*"):
            if item.is_file() and item.name not in ("search.c", "zchezz.exe"):
                shutil.copy2(item, edir / item.name)
        (edir / "search.c").write_text(cfg["search_c"], encoding="utf-8")
        compile_candidate(edir, name)
    print("\nAll Round 9 Candidates ready!")

if __name__ == "__main__":
    main()
