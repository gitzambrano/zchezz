import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(".").resolve()
V334_DIR = ROOT / "engine" / "c" / "zchezz_v334"
EXP_ROOT = ROOT / "experiments" / "search_improvements_round3"
EXP_ROOT.mkdir(parents=True, exist_ok=True)

base_search = (V334_DIR / "search.c").read_text(encoding="utf-8")

EXPERIMENTS = {}

# --------------------------------------------------------------------------
# 1. exp1_lmp_tight: Tighter Late Move Pruning
# --------------------------------------------------------------------------
s1 = base_search.replace(
    "static const int lmp_limit[8] = {0,12,22,32,44,58,74,94};",
    "static const int lmp_limit[8] = {0, 6, 12, 19, 28, 39, 52, 68};"
)
EXPERIMENTS["exp1_lmp_tight"] = s1

# --------------------------------------------------------------------------
# 2. exp2_nmp_eval_scale: Proportional Dynamic NMP
# --------------------------------------------------------------------------
old_nmp = """        int R = 3 + depth / 3;
        if (R > 6) R = 6;
        if (static_eval - beta > 134) R += 1;"""

new_nmp = """        int R = 3 + depth / 4 + (static_eval - beta) / 180;
        if (R > 6) R = 6;
        if (R < 3) R = 3;"""
assert old_nmp in base_search, "old_nmp not found"
s2 = base_search.replace(old_nmp, new_nmp)
EXPERIMENTS["exp2_nmp_eval_scale"] = s2

# --------------------------------------------------------------------------
# 3. exp3_asp_widening: Smooth Progressive Aspiration Window
# --------------------------------------------------------------------------
old_asp = """                /* Aspiration windows */
                int delta = 20, alpha2 = prev_score-delta, beta2 = prev_score+delta;
                int tries = 0; int exact = 0;
                while (tries < 6) {
                    tries++;
                    iter_len = 0;
                    score = alpha_beta(ss, b, depth, alpha2, beta2, iter_pv, &iter_len, 0, -1);
                    if (ss->time_up) break;
                    if      (score <= alpha2) { alpha2 -= delta; if(alpha2<-18000)alpha2=-18000; delta*=2; if(delta>500)delta=500; exact=0; }
                    else if (score >= beta2)  { beta2  += delta; if(beta2>18000)beta2=18000;   delta*=2; if(delta>500)delta=500; exact=0; }"""

new_asp = """                /* Aspiration windows */
                int delta = 16, alpha2 = prev_score-delta, beta2 = prev_score+delta;
                int tries = 0; int exact = 0;
                while (tries < 6) {
                    tries++;
                    iter_len = 0;
                    score = alpha_beta(ss, b, depth, alpha2, beta2, iter_pv, &iter_len, 0, -1);
                    if (ss->time_up) break;
                    if      (score <= alpha2) { alpha2 -= delta; if(alpha2<-18000)alpha2=-18000; delta += delta/2 + 8; if(delta>600)delta=600; exact=0; }
                    else if (score >= beta2)  { beta2  += delta; if(beta2>18000)beta2=18000;   delta += delta/2 + 8; if(delta>600)delta=600; exact=0; }"""
assert old_asp in base_search, "old_asp not found"
s3 = base_search.replace(old_asp, new_asp)
EXPERIMENTS["exp3_asp_widening"] = s3

# --------------------------------------------------------------------------
# 4. exp4_capture_lmr_dyn: Dynamic Negative SEE Capture LMR
# --------------------------------------------------------------------------
old_cap_lmr = """                /* LMR for losing captures */
                if (is_capture && !is_promo && depth>=3 && legal_count>=4 && !in_check) {
                    if (m->score >= 100000 && m->score <= 200000) reduce = 1;
                }"""

new_cap_lmr = """                /* Dynamic LMR for losing captures */
                if (is_capture && !is_promo && depth>=3 && legal_count>=3 && !in_check) {
                    if (m->score >= 100000 && m->score <= 200000) {
                        reduce = 1 + (depth >= 6 ? 1 : 0);
                    }
                }"""
assert old_cap_lmr in base_search, "old_cap_lmr not found"
s4 = base_search.replace(old_cap_lmr, new_cap_lmr)
EXPERIMENTS["exp4_capture_lmr_dyn"] = s4

# --------------------------------------------------------------------------
# 5. exp5_history_bonus_scale: Responsive History Scaling at Mid Depths
# --------------------------------------------------------------------------
old_hist_bonus = """            int bonus = depth*depth*4;  /* responsive Stockfish-scaled bonus */
            if (bonus > 2000) bonus = 2000;"""

new_hist_bonus = """            int bonus = depth <= 12 ? (16 * depth * depth - 16 * depth) : 2100;
            if (bonus > 2100) bonus = 2100;
            if (bonus < 0) bonus = 0;"""
assert old_hist_bonus in base_search, "old_hist_bonus not found"
s5 = base_search.replace(old_hist_bonus, new_hist_bonus)
EXPERIMENTS["exp5_history_bonus_scale"] = s5

# --------------------------------------------------------------------------
# 6. exp6_rfp_tight_improving: Asymmetric RFP with Fine-Grained Margin
# --------------------------------------------------------------------------
old_rfp = """        int rfp_margin = depth*75 - (improving ? 40 : 0);
        if (static_eval - rfp_margin >= beta) return static_eval;"""

new_rfp = """        int rfp_margin = depth*70 - (improving ? 45 : 15);
        if (static_eval - rfp_margin >= beta) return static_eval;"""
assert old_rfp in base_search, "old_rfp not found"
s6 = base_search.replace(old_rfp, new_rfp)
EXPERIMENTS["exp6_rfp_tight_improving"] = s6

# --------------------------------------------------------------------------
# 7. exp7_see_quiet_d6: Quiet SEE Pruning Extended to Depth 6
# --------------------------------------------------------------------------
old_see_q = """                if (!in_check && !is_pv && is_quiet && legal_count > 0 && depth <= 5 &&
                    !is_killer &&
                    !(cur_prev_ft >= 0 && ss->counter_move[cur_prev_ft] == (mfr*64+mto)) &&
                    !move_gives_check_pre(b, m)) {
                    if (see_board(b, mfr, mto, 0) < -(depth * 45)) continue;
                }"""

new_see_q = """                if (!in_check && !is_pv && is_quiet && legal_count > 0 && depth <= 6 &&
                    !is_killer &&
                    !(cur_prev_ft >= 0 && ss->counter_move[cur_prev_ft] == (mfr*64+mto)) &&
                    !move_gives_check_pre(b, m)) {
                    if (see_board(b, mfr, mto, 0) < -(depth * 40)) continue;
                }"""
assert old_see_q in base_search, "old_see_q not found"
s7 = base_search.replace(old_see_q, new_see_q)
EXPERIMENTS["exp7_see_quiet_d6"] = s7

# --------------------------------------------------------------------------
# 8. exp8_counter_virtual_hist: Countermove Virtual History Bonus in LMR
# --------------------------------------------------------------------------
old_lmr_hist = """                            int ch = ((int)ss->main_history[col_lmr][ft_idx] + (int)ss->piece_history[pidx_lmr][mto]) / 2;
                            if (cmh0 >= 0) ch += ss->cont_hist[0][cmh0][ft_idx];
                            if (cmh1 >= 0) ch += ss->cont_hist[1][cmh1][ft_idx];
                            int hist_adj = ch / 1024;
                            if (hist_adj > 2) hist_adj = 2;
                            if (hist_adj < -2) hist_adj = -2;
                            reduce -= hist_adj;"""

new_lmr_hist = """                            int ch = ((int)ss->main_history[col_lmr][ft_idx] + (int)ss->piece_history[pidx_lmr][mto]) / 2;
                            if (cmh0 >= 0) ch += ss->cont_hist[0][cmh0][ft_idx];
                            if (cmh1 >= 0) ch += ss->cont_hist[1][cmh1][ft_idx];
                            if (cur_prev_ft >= 0 && ss->counter_move[cur_prev_ft] == (mfr*64+mto)) ch += 768;
                            int hist_adj = ch / 1024;
                            if (hist_adj > 2) hist_adj = 2;
                            if (hist_adj < -2) hist_adj = -2;
                            reduce -= hist_adj;"""
assert old_lmr_hist in base_search, "old_lmr_hist not found"
s8 = base_search.replace(old_lmr_hist, new_lmr_hist)
EXPERIMENTS["exp8_counter_virtual_hist"] = s8

# --------------------------------------------------------------------------
# 9. exp9_iir_pv_relaxed: Subtle IIR on Depth >= 4 when TT Move Missing
# --------------------------------------------------------------------------
old_iir = """    /* ── IIR (Internal Iterative Reduction) ───────────────────────
     * If we have no TT move (pv_move is null) at a deep node, the move
     * ordering will be poor.  Rather than wasting time on a full-depth
     * search with bad ordering, reduce depth by 1.  The shallow search
     * will populate the TT with a move for next time.  Conditions:
     *   depth >= 4, not in check, reduced depth still >= 2 */
    if (!pv_move.from && !pv_move.to && depth>=3 && !in_check && depth-1>=2) depth--;"""

new_iir = """    /* ── Subtle IIR: PV and non-PV when TT move missing at depth >= 4 ── */
    if (!tte_hit && !pv_move.from && !pv_move.to && depth>=4 && !in_check) depth--;"""
assert old_iir in base_search, "old_iir not found"
s9 = base_search.replace(old_iir, new_iir)
EXPERIMENTS["exp9_iir_pv_relaxed"] = s9

# --------------------------------------------------------------------------
# 10. exp10_history_pruning_deep: History Pruning Extended to Depth 5
# --------------------------------------------------------------------------
old_hp = """                    /* History pruning */
                    if (depth <= 4) {
                        int ft_hp = mfr * 64 + mto;
                        uint8_t p_hp = b->b[mfr];
                        int col_hp = (PC_COLOR(p_hp) == COL_W) ? 0 : 1;
                        int pidx_hp = piece_index(p_hp);
                        int ch_hp = ((int)ss->main_history[col_hp][ft_hp] + (int)ss->piece_history[pidx_hp][mto]) / 2;
                        if (cmh0 >= 0) ch_hp += ss->cont_hist[0][cmh0][ft_hp];
                        if (cmh1 >= 0) ch_hp += ss->cont_hist[1][cmh1][ft_hp];
                        int hp_thresh = -64 * depth;
                        if (ch_hp < hp_thresh && !move_gives_check_pre(b, m)) continue;
                    }"""

new_hp = """                    /* History pruning up to depth 5 */
                    if (depth <= 5) {
                        int ft_hp = mfr * 64 + mto;
                        uint8_t p_hp = b->b[mfr];
                        int col_hp = (PC_COLOR(p_hp) == COL_W) ? 0 : 1;
                        int pidx_hp = piece_index(p_hp);
                        int ch_hp = ((int)ss->main_history[col_hp][ft_hp] + (int)ss->piece_history[pidx_hp][mto]) / 2;
                        if (cmh0 >= 0) ch_hp += ss->cont_hist[0][cmh0][ft_hp];
                        if (cmh1 >= 0) ch_hp += ss->cont_hist[1][cmh1][ft_hp];
                        int hp_thresh = -48 * depth;
                        if (ch_hp < hp_thresh && !move_gives_check_pre(b, m)) continue;
                    }"""
assert old_hp in base_search, "old_hp not found"
s10 = base_search.replace(old_hp, new_hp)
EXPERIMENTS["exp10_history_pruning_deep"] = s10

# --------------------------------------------------------------------------
# BUILD EACH ENGINE
# --------------------------------------------------------------------------
print(f"Building {len(EXPERIMENTS)} Round 3 search candidates...")

for name, code in EXPERIMENTS.items():
    edir = EXP_ROOT / name
    edir.mkdir(parents=True, exist_ok=True)
    (edir / "search.c").write_text(code, encoding="utf-8")
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
        str(V334_DIR / "nnue.c"),
        str(V334_DIR / "syzygy.c"),
        str(V334_DIR / "book.c"),
        "-static", "-lm", "-pthread"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Build failed for {name}:\n{res.stderr}"
    
    bench = subprocess.run([str(edir / "zchezz.exe"), "bench", "11"], capture_output=True, text=True)
    nps_line = [l for l in bench.stdout.splitlines() if "Nodes/sec" in l]
    nodes_line = [l for l in bench.stdout.splitlines() if "Total nodes" in l]
    print(f"[{name:<28}] BUILT OK: {nodes_line[0] if nodes_line else ''} | {nps_line[0] if nps_line else ''}")

print("\nAll 10 Round 3 experiment candidates successfully built and benchmarked!")
