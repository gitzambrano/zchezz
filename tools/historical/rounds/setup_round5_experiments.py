"""
tools/setup_round5_experiments.py — Set up and compile Round 5 Candidates.

Builds 4 synergistic combinations on top of exp16_dual_nnue_tuned_margins (+56.1 Elo):
1. exp18_exp16_fast_delta: exp16 + Fast Delta Pruning in QS using Dual-NNUE.
2. exp19_exp16_hist_scale: exp16 + Scaled History Gravity Bonus at mid depths.
3. exp20_exp16_rfp_d4: exp16 + Dual-NNUE Fast RFP extended to depth 4.
4. exp21_exp16_counter_lmr: exp16 + Countermove LMR reduction exemption.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP16_DIR = ROOT / "experiments" / "round4_optimizations" / "exp16_dual_nnue_tuned_margins"
EXP_ROOT = ROOT / "experiments" / "round5_combinations"
EXP_ROOT.mkdir(parents=True, exist_ok=True)

base_search = (EXP16_DIR / "search.c").read_text(encoding="utf-8")
base_nnue_c = (EXP16_DIR / "nnue.c").read_text(encoding="utf-8")
fast_head_h = (EXP16_DIR / "fast_head_weights.h").read_text(encoding="utf-8")

# 1. exp18_exp16_fast_delta
old_qs = """    /* Use TT-stored eval as stand-pat if available, with Dual-NNUE Fast Eval */
    int stand;
    if (qs_tte_hit && qs_tte.static_eval != TT_EVAL_NONE) {
        stand = qs_tte.static_eval;
    } else {
        int fast_val = eval_stm_fast(b);
        if (fast_val >= beta + 160) return beta;
        stand = eval_stm(b);
    }"""

new_qs_delta = """    /* Use TT-stored eval as stand-pat if available, with Dual-NNUE Fast Eval */
    int stand;
    if (qs_tte_hit && qs_tte.static_eval != TT_EVAL_NONE) {
        stand = qs_tte.static_eval;
    } else {
        int fast_val = eval_stm_fast(b);
        if (fast_val >= beta + 160) return beta;
        int has_passer = (b->turn==COL_W) ? !!(b->bb[0] & 0x000000000000FF00ULL)
                                           : !!(b->bb[6] & 0x00FF000000000000ULL);
        int delta_margin = has_passer ? MV_TAB[5]*2+50 : MV_TAB[5]+50;
        if (fast_val + delta_margin < alpha - 80) return alpha;
        stand = eval_stm(b);
    }"""
assert old_qs in base_search, "old_qs not found"
s18 = base_search.replace(old_qs, new_qs_delta)

# 2. exp19_exp16_hist_scale
old_bonus = """            int bonus = depth*depth*4;  /* responsive Stockfish-scaled bonus */
            if (bonus > 2000) bonus = 2000;"""
new_bonus = """            int bonus = (depth <= 4) ? (depth * depth * 3) : (depth * depth * 5);
            if (bonus > 2400) bonus = 2400;"""
assert old_bonus in base_search, "old_bonus not found"
s19 = base_search.replace(old_bonus, new_bonus)

# 3. exp20_exp16_rfp_d4
old_rfp = """            if (!is_pv && depth <= 3 && beta < 18000) {
                int fast_val = eval_stm_fast(b);
                if (fast_val - (depth * 90) >= beta + 100) return beta;
            }"""
new_rfp_d4 = """            if (!is_pv && depth <= 4 && beta < 18000) {
                int fast_val = eval_stm_fast(b);
                int rfp_m = (depth <= 3) ? 100 : 130;
                if (fast_val - (depth * 90) >= beta + rfp_m) return beta;
            }"""
assert old_rfp in base_search, "old_rfp not found"
s20 = base_search.replace(old_rfp, new_rfp_d4)

# 4. exp21_exp16_counter_lmr
old_lmr = """                        if (is_pv) reduce = reduce>0?reduce-1:0;
                        if (!improving) reduce += 1;"""
new_counter_lmr = """                        if (is_pv) reduce = reduce>0?reduce-1:0;
                        if (!improving) reduce += 1;
                        if (cur_prev_ft >= 0 && ss->counter_move[cur_prev_ft] == (mfr*64+mto)) {
                            reduce = reduce > 0 ? reduce - 1 : 0;
                        }"""
assert old_lmr in base_search, "old_lmr not found"
s21 = base_search.replace(old_lmr, new_counter_lmr)

CONFIGS = {
    "exp18_exp16_fast_delta": {
        "desc": "exp16 + Fast Delta Pruning in QS using Dual-NNUE",
        "search_c": s18,
    },
    "exp19_exp16_hist_scale": {
        "desc": "exp16 + Scaled History Gravity Bonus at mid depths",
        "search_c": s19,
    },
    "exp20_exp16_rfp_d4": {
        "desc": "exp16 + Dual-NNUE Fast RFP extended to depth 4",
        "search_c": s20,
    },
    "exp21_exp16_counter_lmr": {
        "desc": "exp16 + Countermove LMR reduction exemption",
        "search_c": s21,
    },
}

V334_DIR = ROOT / "engine" / "c" / "zchezz_v334"

def build_all():
    print(f"=== Setting up and compiling {len(CONFIGS)} Round 5 Candidates ===")
    for name, cfg in CONFIGS.items():
        edir = EXP_ROOT / name
        edir.mkdir(parents=True, exist_ok=True)
        
        (edir / "search.c").write_text(cfg["search_c"], encoding="utf-8")
        (edir / "nnue.c").write_text(base_nnue_c, encoding="utf-8")
        (edir / "fast_head_weights.h").write_text(fast_head_h, encoding="utf-8")
        
        if not (edir / "nnue_weights.bin").is_file():
            shutil.copy2(V334_DIR / "nnue_weights.bin", edir / "nnue_weights.bin")

        cmd = [
            "gcc", "-O3", "-ffast-math", "-D_GNU_SOURCE", "-std=c11", "-mavx2",
            f"-I{V334_DIR}", f"-I{edir}", "-DNO_TABLEBASES",
            "-Wno-unused-variable", "-Wno-unused-but-set-variable", "-Wno-maybe-uninitialized",
            "-Wno-misleading-indentation", "-Wno-sign-compare", "-Wno-unused-function", "-Wno-parentheses",
            "-o", str(edir / "zchezz.exe"),
            str(V334_DIR / "main.c"),
            str(V334_DIR / "board.c"),
            str(edir / "search.c"),
            str(edir / "nnue.c"),
            str(V334_DIR / "syzygy.c"),
            str(V334_DIR / "book.c"),
            "-static", "-lm", "-pthread"
        ]
        
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0, f"Build failed for {name}:\n{res.stderr}"
        
        bench = subprocess.run([str(edir / "zchezz.exe"), "bench", "11"], capture_output=True, text=True)
        nps_line = [l for l in bench.stdout.splitlines() if "Nodes/sec" in l]
        nodes_line = [l for l in bench.stdout.splitlines() if "Total nodes" in l]
        print(f"[{name:<25}] BUILT OK: {nodes_line[0] if nodes_line else ''} | {nps_line[0] if nps_line else ''}")

    print("\nAll 4 Round 5 experiment candidates successfully built and benchmarked!")

if __name__ == "__main__":
    build_all()
