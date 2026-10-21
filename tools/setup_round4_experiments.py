"""
tools/setup_round4_experiments.py — Set up and compile Round 4 engine candidates.

Candidates:
1. exp11_move_ordering: Capture history table + 4-ply Continuation history + Searched captures malus.
2. exp12_aux_fast_nnue: Dual-NNUE Fast Evaluation linear head for QS stand-pat & shallow RFP cutoffs.
3. exp13_move_ordering_plus_r3: Move Ordering + R3 winners (SEE quiet d6 + Scaled history bonus).
4. exp14_grand_combo: Complete combination of Move Ordering + R3 winners + Dual-NNUE Fast Eval.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V334_DIR = ROOT / "engine" / "c" / "zchezz_v334"
EXP_ROOT = ROOT / "experiments" / "round4_optimizations"
EXP_ROOT.mkdir(parents=True, exist_ok=True)

# Copy fast_head_weights.h to artifacts if not present
FAST_HEAD_H = ROOT / "artifacts" / "fast_head_weights.h"
assert FAST_HEAD_H.is_file(), "fast_head_weights.h missing in artifacts!"

base_search = (V334_DIR / "search.c").read_text(encoding="utf-8")
base_nnue_c = (V334_DIR / "nnue.c").read_text(encoding="utf-8")

# -----------------------------------------------------------------------------
# 1. PREPARE CODE FOR MOVE ORDERING (Track 1)
# -----------------------------------------------------------------------------
def make_move_ordering_search(base: str, include_r3: bool = False) -> str:
    s = base

    # Replace SearchState struct definition
    old_ss = """    int32_t counter_move[64*64];
    int16_t cont_hist[2][64][64*64];
    int prev_ft[MAX_PLY];"""
    
    new_ss = """    int32_t counter_move[64*64];
    int16_t cont_hist[3][64][64*64];
    int16_t capture_history[2][6][64][6];
    int prev_ft[MAX_PLY];"""
    assert old_ss in s, "SearchState cont_hist not found"
    s = s.replace(old_ss, new_ss)

    # Replace score_move signature and implementation
    old_score_move = """static int score_move(SearchState *ss, const Move *m, const Board *bd, int ply,
                      const Move *pv_move, int ok_sq,
                      int prev_ft_val, int cmh0, int cmh1) {"""
    
    new_score_move = """static int score_move(SearchState *ss, const Move *m, const Board *bd, int ply,
                      const Move *pv_move, int ok_sq,
                      int prev_ft_val, int cmh0, int cmh1, int cmh2) {"""
    assert old_score_move in s, "score_move signature not found"
    s = s.replace(old_score_move, new_score_move)

    # Inside score_move: capture scoring with capture_history
    old_cap_score = """        if (MV_TAB[attacker] <= MV_TAB[victim])
            return 1600000 + 1000 + MVV_LVA[victim*7+attacker] + ep_bonus;
        int sv = see_board(bd, mfr, mto, m->epc);
        if (sv >= 0)
            return 1600000 + sv*10 + MVV_LVA[victim*7+attacker] + ep_bonus;
        else {
            /* Losing capture: 100000..200000 */
            int s = 200000 + sv*2;
            return s > 100000 ? s : 100000;
        }"""

    new_cap_score = """        int col_idx = (PC_COLOR(b[mfr]) == COL_W) ? 0 : 1;
        int cap_hist = 0;
        if (attacker >= 1 && attacker <= 6 && victim >= 1 && victim <= 6) {
            cap_hist = (int)ss->capture_history[col_idx][attacker-1][mto][victim-1] / 16;
        }
        if (MV_TAB[attacker] <= MV_TAB[victim])
            return 1600000 + 1000 + MVV_LVA[victim*7+attacker] + ep_bonus + cap_hist;
        int sv = see_board(bd, mfr, mto, m->epc);
        if (sv >= 0)
            return 1600000 + sv*10 + MVV_LVA[victim*7+attacker] + ep_bonus + cap_hist;
        else {
            /* Losing capture: 100000..200000 */
            int s = 200000 + sv*2 + (cap_hist / 2);
            return s > 100000 ? s : 100000;
        }"""
    assert old_cap_score in s, "old_cap_score not found"
    s = s.replace(old_cap_score, new_cap_score)

    # Inside score_move: quiet combined history with 4-ply continuation history
    old_quiet_score = """    int c0 = (cmh0 >= 0) ? ss->cont_hist[0][cmh0][ft] : 0;
    int c1 = (cmh1 >= 0) ? ss->cont_hist[1][cmh1][ft] : 0;
    int combined = h + c0 + c1;   /* range: -96000..96000 */"""

    new_quiet_score = """    int c0 = (cmh0 >= 0) ? ss->cont_hist[0][cmh0][ft] : 0;
    int c1 = (cmh1 >= 0) ? ss->cont_hist[1][cmh1][ft] : 0;
    int c2 = (cmh2 >= 0) ? ss->cont_hist[2][cmh2][ft] : 0;
    int combined = h + c0 + c1 + (c2 / 2);"""
    assert old_quiet_score in s, "old_quiet_score not found"
    s = s.replace(old_quiet_score, new_quiet_score)

    # Replace sort_moves signature and calls
    old_sort_moves = """static void sort_moves(SearchState *ss, Move *moves, int n, const Board *bd, int ply,
                       const Move *pv_move, int ok_sq, int prev_ft_val,
                       int cmh0, int cmh1) {
    for (int i = 0; i < n; i++)
        moves[i].score = score_move(ss, &moves[i], bd, ply, pv_move, ok_sq,
                                    prev_ft_val, cmh0, cmh1);"""

    new_sort_moves = """static void sort_moves(SearchState *ss, Move *moves, int n, const Board *bd, int ply,
                       const Move *pv_move, int ok_sq, int prev_ft_val,
                       int cmh0, int cmh1, int cmh2) {
    for (int i = 0; i < n; i++)
        moves[i].score = score_move(ss, &moves[i], bd, ply, pv_move, ok_sq,
                                    prev_ft_val, cmh0, cmh1, cmh2);"""
    assert old_sort_moves in s, "old_sort_moves not found"
    s = s.replace(old_sort_moves, new_sort_moves)

    # In qsearch:
    old_qs_sort1 = """        sort_moves(ss, moves, n, b, ply, NULL, ok_sq, -1, -1, -1);"""
    new_qs_sort1 = """        sort_moves(ss, moves, n, b, ply, NULL, ok_sq, -1, -1, -1, -1);"""
    assert old_qs_sort1 in s, "old_qs_sort1 not found"
    s = s.replace(old_qs_sort1, new_qs_sort1)

    old_qs_sort2 = """        moves[i].score = score_move(ss, &moves[i], b, ply, qs_pv, ok_sq, -1, -1, -1);"""
    new_qs_sort2 = """        moves[i].score = score_move(ss, &moves[i], b, ply, qs_pv, ok_sq, -1, -1, -1, -1);"""
    assert old_qs_sort2 in s, "old_qs_sort2 not found"
    s = s.replace(old_qs_sort2, new_qs_sort2)

    # In search_moves calls:
    old_pc_score = """        for (int pi = 0; pi < pc_n; pi++)
            pc_moves[pi].score = score_move(ss, &pc_moves[pi], b, ply,
                                            NULL, pc_ok, -1, -1, -1);"""
    new_pc_score = """        for (int pi = 0; pi < pc_n; pi++)
            pc_moves[pi].score = score_move(ss, &pc_moves[pi], b, ply,
                                            NULL, pc_ok, -1, -1, -1, -1);"""
    assert old_pc_score in s, "old_pc_score not found"
    s = s.replace(old_pc_score, new_pc_score)

    old_cap_call = """            caps[i].score = score_move(ss, &caps[i], b, ply, pv_ptr, ok_sq,
                                       cur_prev_ft, cmh0, cmh1);"""
    new_cap_call = """            caps[i].score = score_move(ss, &caps[i], b, ply, pv_ptr, ok_sq,
                                       cur_prev_ft, cmh0, cmh1, cmh2);"""
    assert old_cap_call in s, "old_cap_call not found"
    s = s.replace(old_cap_call, new_cap_call)

    old_quiet_call = """                quiets[i].score = score_move(ss, &quiets[i], b, ply, pv_ptr, ok_sq,
                                             cur_prev_ft, cmh0, cmh1);"""
    new_quiet_call = """                quiets[i].score = score_move(ss, &quiets[i], b, ply, pv_ptr, ok_sq,
                                             cur_prev_ft, cmh0, cmh1, cmh2);"""
    assert old_quiet_call in s, "old_quiet_call not found"
    s = s.replace(old_quiet_call, new_quiet_call)

    # In search(): cmh definitions:
    old_cmh_def = """    int cmh0 = ply >= 1 ? ss->prev_to_sq[ply-1] : -1;
    int cmh1 = ply >= 2 ? ss->prev_to_sq[ply-2] : -1;"""
    new_cmh_def = """    int cmh0 = ply >= 1 ? ss->prev_to_sq[ply-1] : -1;
    int cmh1 = ply >= 2 ? ss->prev_to_sq[ply-2] : -1;
    int cmh2 = ply >= 4 ? ss->prev_to_sq[ply-4] : -1;"""
    assert old_cmh_def in s, "old_cmh_def not found"
    s = s.replace(old_cmh_def, new_cmh_def)

    # In search(): add searched_caps declaration
    old_decl_quiets = """    /* Track quiet moves searched for history penalty */
    Move searched_quiets[64];
    int n_searched_quiets = 0;"""
    new_decl_quiets = """    /* Track quiet moves searched for history penalty */
    Move searched_quiets[64];
    int n_searched_quiets = 0;
    Move searched_caps[32];
    int n_searched_caps = 0;"""
    assert old_decl_quiets in s, "old_decl_quiets not found"
    s = s.replace(old_decl_quiets, new_decl_quiets)

    # In Stage 1: track searched captures
    old_stage1_track = """                    if (is_quiet && n_searched_quiets < 64 && sc <= alpha)
                        searched_quiets[n_searched_quiets++] = *m;"""
    new_stage1_track = """                    if (is_quiet && n_searched_quiets < 64 && sc <= alpha)
                        searched_quiets[n_searched_quiets++] = *m;
                    else if (!is_quiet && n_searched_caps < 32 && sc <= alpha)
                        searched_caps[n_searched_caps++] = *m;"""
    assert old_stage1_track in s, "old_stage1_track not found"
    s = s.replace(old_stage1_track, new_stage1_track)

    # In Stage 2: track searched captures
    old_stage2_track = """            board_unmake(b);

            if (sc > best) {"""
    new_stage2_track = """            board_unmake(b);
            if (n_searched_caps < 32 && sc <= alpha)
                searched_caps[n_searched_caps++] = *m;

            if (sc > best) {"""
    assert old_stage2_track in s, "old_stage2_track not found"
    s = s.replace(old_stage2_track, new_stage2_track)

    # In history updates on cutoff:
    bonus_formula = "int bonus = (depth <= 4) ? (depth * depth * 3) : (depth * depth * 5); if (bonus > 2400) bonus = 2400;" if include_r3 else "int bonus = depth*depth*4; if (bonus > 2000) bonus = 2000;"

    old_hist_update = """            int bonus = depth*depth*4;  /* responsive Stockfish-scaled bonus */
            if (bonus > 2000) bonus = 2000;

            /* Reward the cutoff move using Stockfish gravity formula */
            int ft = mfr*64 + mto;
            history_update(&ss->main_history[col_idx][ft], bonus);
            history_update(&ss->piece_history[p_idx][mto], bonus);
            if (cmh0 >= 0) history_update(&ss->cont_hist[0][cmh0][ft], bonus);
            if (cmh1 >= 0) history_update(&ss->cont_hist[1][cmh1][ft], bonus);

            /* Penalise all quiet moves that were searched before the cutoff
             * move but failed to produce a cutoff themselves. */
            for (int j = 0; j < n_searched_quiets; j++) {
                Move *pm = &searched_quiets[j];
                if (pm->from == mfr && pm->to == mto) continue;
                int pcol = (PC_COLOR(b->b[pm->from]) == COL_W) ? 0 : 1;
                int pp_idx = piece_index(b->b[pm->from]);
                int pft = pm->from*64 + pm->to;
                history_update(&ss->main_history[pcol][pft], -bonus);
                history_update(&ss->piece_history[pp_idx][pm->to], -bonus);
                if (cmh0 >= 0) history_update(&ss->cont_hist[0][cmh0][pft], -bonus);
                if (cmh1 >= 0) history_update(&ss->cont_hist[1][cmh1][pft], -bonus);
            }
        }"""

    new_hist_update = f"""            {bonus_formula}

            int ft = mfr*64 + mto;
            history_update(&ss->main_history[col_idx][ft], bonus);
            history_update(&ss->piece_history[p_idx][mto], bonus);
            if (cmh0 >= 0) history_update(&ss->cont_hist[0][cmh0][ft], bonus);
            if (cmh1 >= 0) history_update(&ss->cont_hist[1][cmh1][ft], bonus);
            if (cmh2 >= 0) history_update(&ss->cont_hist[2][cmh2][ft], bonus);

            for (int j = 0; j < n_searched_quiets; j++) {{
                Move *pm = &searched_quiets[j];
                if (pm->from == mfr && pm->to == mto) continue;
                int pcol = (PC_COLOR(b->b[pm->from]) == COL_W) ? 0 : 1;
                int pp_idx = piece_index(b->b[pm->from]);
                int pft = pm->from*64 + pm->to;
                history_update(&ss->main_history[pcol][pft], -bonus);
                history_update(&ss->piece_history[pp_idx][pm->to], -bonus);
                if (cmh0 >= 0) history_update(&ss->cont_hist[0][cmh0][pft], -bonus);
                if (cmh1 >= 0) history_update(&ss->cont_hist[1][cmh1][pft], -bonus);
                if (cmh2 >= 0) history_update(&ss->cont_hist[2][cmh2][pft], -bonus);
            }}
        }} else if (is_capture) {{
            {bonus_formula}
            int col_idx = (PC_COLOR(b->b[mfr]) == COL_W) ? 0 : 1;
            int att = PC_TYPE(b->b[mfr]);
            uint8_t cap = b->b[mto];
            int vic = cap ? PC_TYPE(cap) : 1;
            if (att >= 1 && att <= 6 && vic >= 1 && vic <= 6) {{
                history_update(&ss->capture_history[col_idx][att-1][mto][vic-1], bonus);
            }}
            for (int j = 0; j < n_searched_caps; j++) {{
                Move *pm = &searched_caps[j];
                if (pm->from == mfr && pm->to == mto) continue;
                int pcol = (PC_COLOR(b->b[pm->from]) == COL_W) ? 0 : 1;
                int patt = PC_TYPE(b->b[pm->from]);
                uint8_t pcap = b->b[pm->to];
                int pvic = pcap ? PC_TYPE(pcap) : 1;
                if (patt >= 1 && patt <= 6 && pvic >= 1 && pvic <= 6) {{
                    history_update(&ss->capture_history[pcol][patt-1][pm->to][pvic-1], -bonus);
                }}
            }}
        }}"""
    assert old_hist_update in s, "old_hist_update not found"
    s = s.replace(old_hist_update, new_hist_update)

    # In search_reset:
    old_reset_cont = """    for (int s = 0; s < 2; s++)
        for (int i = 0; i < 64; i++)
            for (int j = 0; j < 64*64; j++)
                ss->cont_hist[s][i][j] >>= 1;"""

    new_reset_cont = """    for (int s = 0; s < 3; s++)
        for (int i = 0; i < 64; i++)
            for (int j = 0; j < 64*64; j++)
                ss->cont_hist[s][i][j] >>= 1;
    for (int c = 0; c < 2; c++)
        for (int a = 0; a < 6; a++)
            for (int sq = 0; sq < 64; sq++)
                for (int v = 0; v < 6; v++)
                    ss->capture_history[c][a][sq][v] >>= 1;"""
    assert old_reset_cont in s, "old_reset_cont not found"
    s = s.replace(old_reset_cont, new_reset_cont)

    # In search_history_clear:
    old_clear_cont = """    memset(s->cont_hist,     0, sizeof(s->cont_hist));"""
    new_clear_cont = """    memset(s->cont_hist,       0, sizeof(s->cont_hist));
    memset(s->capture_history, 0, sizeof(s->capture_history));"""
    assert old_clear_cont in s, "old_clear_cont not found"
    s = s.replace(old_clear_cont, new_clear_cont)

    # If include_r3 is enabled, add see_quiet_d6 (+27.9 Elo from R3)
    if include_r3:
        old_quiet_prune = """                if (!in_check && !is_pv && is_quiet && legal_count > 0 && depth <= 5 &&
                    !is_killer &&
                    !(cur_prev_ft >= 0 && ss->counter_move[cur_prev_ft] == (mfr*64+mto)) &&
                    !move_gives_check_pre(b, m)) {
                    if (see_board(b, mfr, mto, 0) < -(depth * 45)) continue;
                }"""
        new_quiet_prune = """                if (!in_check && !is_pv && is_quiet && legal_count > 0 && depth <= 6 &&
                    !is_killer &&
                    !(cur_prev_ft >= 0 && ss->counter_move[cur_prev_ft] == (mfr*64+mto)) &&
                    !move_gives_check_pre(b, m)) {
                    if (see_board(b, mfr, mto, 0) < -(depth * 40)) continue;
                }"""
        assert old_quiet_prune in s, "old_quiet_prune not found"
        s = s.replace(old_quiet_prune, new_quiet_prune)

    return s

# -----------------------------------------------------------------------------
# 2. PREPARE CODE FOR DUAL-NNUE FAST EVAL (Track 2)
# -----------------------------------------------------------------------------
def make_dual_nnue_c():
    fast_impl = """
#include "fast_head_weights.h"

int nnue_fast_eval_bb(NnueAccum *na, int stm, const uint8_t *board,
                      const uint64_t bb[12], uint64_t board_hash)
{
    if (!_nnue_ready) return 0;
    if (na->acc_dirty) return 0;

    int cw[6],cb[6];
    for(int i=0;i<6;i++){cw[i]=__builtin_popcountll(bb[i]);cb[i]=__builtin_popcountll(bb[i+6]);}
    uint64_t key=_count14_key(cw,cb);
    uint32_t aux=0x80000000u | (uint32_t)stm;
    int slot=(int)((key ^ ((uint64_t)aux*0x9e3779b97f4a7c15ULL)) & (EXT_CACHE_SLOTS-1));
    const int16_t *ext;
    if(na->cache_key[slot]!=key || na->cache_aux[slot]!=aux){
        int16_t *buf=na->cache_buf[slot];_count14_project(buf,cw,cb,stm);
        na->cache_key[slot]=key;na->cache_aux[slot]=aux;ext=buf;
    } else ext=na->cache_buf[slot];
    const int16_t *pk=stm==0?na->pk17_acc_w:na->pk17_acc_b;
    (void)board;(void)board_hash;

    uint8_t relu1[NN_L1_OUT] __attribute__((aligned(32)));
    const int16_t *acc = stm==0 ? na->acc_stack_w[na->acc_ptr] : na->acc_stack_b[na->acc_ptr];

#ifdef __AVX2__
    {
        __m256i v255 = _mm256_set1_epi32(255);
        __m256i zero = _mm256_setzero_si256();
        for (int o = 0; o < NN_L1_OUT; o += 16) {
            __m128i a_lo = _mm_load_si128((const __m128i*)(acc + o));
            __m128i a_hi = _mm_load_si128((const __m128i*)(acc + o + 8));
            __m128i e_lo = _mm_add_epi16(_mm_load_si128((const __m128i*)(ext + o)),
                                           _mm_load_si128((const __m128i*)(pk + o)));
            __m128i e_hi = _mm_add_epi16(_mm_load_si128((const __m128i*)(ext + o + 8)),
                                           _mm_load_si128((const __m128i*)(pk + o + 8)));
            __m256i s_lo = _mm256_add_epi32(_mm256_cvtepi16_epi32(a_lo), _mm256_cvtepi16_epi32(e_lo));
            __m256i s_hi = _mm256_add_epi32(_mm256_cvtepi16_epi32(a_hi), _mm256_cvtepi16_epi32(e_hi));
            s_lo = _mm256_add_epi32(s_lo, _mm256_load_si256((const __m256i*)(_nnL1B + o)));
            s_hi = _mm256_add_epi32(s_hi, _mm256_load_si256((const __m256i*)(_nnL1B + o + 8)));
            s_lo = _mm256_min_epi32(_mm256_max_epi32(s_lo, zero), v255);
            s_hi = _mm256_min_epi32(_mm256_max_epi32(s_hi, zero), v255);
            __m256i p16 = _mm256_packus_epi32(s_lo, s_hi);
            p16 = _mm256_permute4x64_epi64(p16, _MM_SHUFFLE(3,1,2,0));
            __m128i lo16 = _mm256_castsi256_si128(p16);
            __m128i hi16 = _mm256_extracti128_si256(p16, 1);
            _mm_store_si128((__m128i*)(relu1 + o), _mm_packus_epi16(lo16, hi16));
        }
    }
    __m256i ones = _mm256_set1_epi16(1);
    __m256i sum = _mm256_setzero_si256();
    for (int i = 0; i < NN_L1_OUT; i += 32) {
        __m256i a = _mm256_load_si256((const __m256i*)(relu1 + i));
        __m256i w = _mm256_load_si256((const __m256i*)(FAST_HEAD_W + i));
        __m256i p = _mm256_maddubs_epi16(a, w);
        sum = _mm256_add_epi32(sum, _mm256_madd_epi16(p, ones));
    }
    int32_t dot = _hsum_epi32(sum);
#else
    for (int o = 0; o < NN_L1_OUT; o++) {
        int16_t ex=(int16_t)(ext[o]+pk[o]);
        int32_t v = (int32_t)acc[o] + (int32_t)ex + _nnL1B[o];
        relu1[o] = (uint8_t)(v < 0 ? 0 : v > 255 ? 255 : v);
    }
    int32_t dot = 0;
    for (int i = 0; i < NN_L1_OUT; i++) {
        dot += (int32_t)relu1[i] * FAST_HEAD_W[i];
    }
#endif
    float cp = (float)dot * FAST_HEAD_INV_SCALE + FAST_HEAD_BIAS;
    if (cp < -2000.f) cp = -2000.f;
    if (cp >  2000.f) cp =  2000.f;
    return (int)(cp + (cp >= 0.f ? 0.5f : -0.5f));
}
"""
    return base_nnue_c + fast_impl

def inject_fast_eval_search(base: str) -> str:
    s = base

    # Add nnue_fast_eval_bb prototype and eval_stm_fast definition after eval_stm
    old_eval_stm = """    return nnue_eval_bb(b->nnue, b->turn == COL_W ? 0 : 1, b->b, b->bb, b->hash);
}

/* ── SEE (pure bitboard — Phase 3)"""
    new_eval_stm = """    return nnue_eval_bb(b->nnue, b->turn == COL_W ? 0 : 1, b->b, b->bb, b->hash);
}

int nnue_fast_eval_bb(NnueAccum *na, int stm, const uint8_t *board,
                      const uint64_t bb[12], uint64_t board_hash);

static inline int eval_stm_fast(Board *b) {
    return nnue_fast_eval_bb(b->nnue, b->turn == COL_W ? 0 : 1, b->b, b->bb, b->hash);
}

/* ── SEE (pure bitboard — Phase 3)"""
    assert old_eval_stm in s, "eval_stm not found"
    s = s.replace(old_eval_stm, new_eval_stm)

    # In qsearch: fast stand-pat cutoff
    old_qs = """    /* Use TT-stored eval as stand-pat if available */
    int stand = (qs_tte_hit && qs_tte.static_eval != TT_EVAL_NONE)
                 ? qs_tte.static_eval : eval_stm(b);"""

    new_qs = """    /* Use TT-stored eval as stand-pat if available, with Dual-NNUE Fast Eval */
    int stand;
    if (qs_tte_hit && qs_tte.static_eval != TT_EVAL_NONE) {
        stand = qs_tte.static_eval;
    } else {
        int fast_val = eval_stm_fast(b);
        if (fast_val >= beta + 200) return beta;
        stand = eval_stm(b);
    }"""
    assert old_qs in s, "old_qs not found"
    s = s.replace(old_qs, new_qs)

    # In search: shallow fast RFP cutoff
    old_rfp = """    if (!in_check) {
        raw_eval = (tte_hit && tte.static_eval != TT_EVAL_NONE)
                    ? tte.static_eval : eval_stm(b);"""

    new_rfp = """    if (!in_check) {
        if (tte_hit && tte.static_eval != TT_EVAL_NONE) {
            raw_eval = tte.static_eval;
        } else {
            if (!is_pv && depth <= 3 && beta < 18000) {
                int fast_val = eval_stm_fast(b);
                if (fast_val - (depth * 90) >= beta + 120) return beta;
            }
            raw_eval = eval_stm(b);
        }"""
    assert old_rfp in s, "old_rfp not found"
    s = s.replace(old_rfp, new_rfp)

    return s

# -----------------------------------------------------------------------------
# BUILD CONFIGURATIONS
# -----------------------------------------------------------------------------
nc_dual = make_dual_nnue_c()

CONFIGS = {
    "exp11_move_ordering": {
        "desc": "Track 1: Capture History + 4-ply Continuation History + Searched Captures Malus",
        "search_c": make_move_ordering_search(base_search, include_r3=False),
        "custom_nnue": False,
        "needs_fast_head": False,
    },
    "exp12_aux_fast_nnue": {
        "desc": "Track 2: Dual-NNUE Fast Evaluation (Linear Aux Head for Fast QS & RFP cutoffs)",
        "search_c": inject_fast_eval_search(base_search),
        "custom_nnue": True,
        "needs_fast_head": True,
    },
    "exp13_move_ordering_plus_r3": {
        "desc": "Track 1 + R3 Best: Move Ordering + Quiet SEE Pruning d6 (-40*d) + Scaled Bonus",
        "search_c": make_move_ordering_search(base_search, include_r3=True),
        "custom_nnue": False,
        "needs_fast_head": False,
    },
    "exp14_grand_combo": {
        "desc": "Grand Combo: Move Ordering + R3 Best Search + Dual-NNUE Fast Evaluation",
        "search_c": inject_fast_eval_search(make_move_ordering_search(base_search, include_r3=True)),
        "custom_nnue": True,
        "needs_fast_head": True,
    },
}

def build_all():
    print(f"=== Setting up and compiling {len(CONFIGS)} Round 4 Candidates ===")
    for name, cfg in CONFIGS.items():
        edir = EXP_ROOT / name
        edir.mkdir(parents=True, exist_ok=True)
        
        # Remove any lingering nnue.h in edir
        if (edir / "nnue.h").is_file():
            (edir / "nnue.h").unlink()
            
        (edir / "search.c").write_text(cfg["search_c"], encoding="utf-8")
        
        if cfg["custom_nnue"]:
            (edir / "nnue.c").write_text(nc_dual, encoding="utf-8")
            nnue_src = str(edir / "nnue.c")
        else:
            if (edir / "nnue.c").is_file():
                (edir / "nnue.c").unlink()
            nnue_src = str(V334_DIR / "nnue.c")
        
        if not (edir / "nnue_weights.bin").is_file():
            shutil.copy2(V334_DIR / "nnue_weights.bin", edir / "nnue_weights.bin")
            
        if cfg["needs_fast_head"]:
            shutil.copy2(FAST_HEAD_H, edir / "fast_head_weights.h")

        cmd = [
            "gcc", "-O3", "-ffast-math", "-D_GNU_SOURCE", "-std=c11", "-mavx2",
            f"-I{V334_DIR}", f"-I{edir}", "-DNO_TABLEBASES",
            "-Wno-unused-variable", "-Wno-unused-but-set-variable", "-Wno-maybe-uninitialized",
            "-Wno-misleading-indentation", "-Wno-sign-compare", "-Wno-unused-function", "-Wno-parentheses",
            "-o", str(edir / "zchezz.exe"),
            str(V334_DIR / "main.c"),
            str(V334_DIR / "board.c"),
            str(edir / "search.c"),
            nnue_src,
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

    print("\nAll 4 Round 4 experiment candidates successfully built and benchmarked!")

if __name__ == "__main__":
    build_all()
