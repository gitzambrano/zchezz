"""
tools/setup_v605_candidate.py — Setup and compile v605 (NNU5 Dual-Head Candidate).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V604_DIR = ROOT / "engine" / "c" / "zchezz_v604"
CAND_DIR = ROOT / "experiments" / "v605_dual_candidate"
CAND_DIR.mkdir(parents=True, exist_ok=True)

# 1. Copy base files
for f in V604_DIR.iterdir():
    if f.is_file() and f.name != "zchezz.exe":
        shutil.copy2(f, CAND_DIR / f.name)

# 2. Copy fast_head_weights
shutil.copy2(ROOT / "artifacts" / "fast_head_weights_nnu5.h", CAND_DIR / "fast_head_weights.h")

# 3. Patch nnue.h
nnue_h = (CAND_DIR / "nnue.h").read_text(encoding="utf-8")
if "nnue_fast_eval_bb" not in nnue_h:
    nnue_h += "\nint nnue_fast_eval_bb(NnueAccum *na, int stm, const uint8_t *board, const uint64_t bb[12], uint64_t board_hash);\n"
    (CAND_DIR / "nnue.h").write_text(nnue_h, encoding="utf-8")

# 4. Patch nnue.c
nnue_c = (CAND_DIR / "nnue.c").read_text(encoding="utf-8")
fast_eval_code = """
#include "fast_head_weights.h"

int nnue_fast_eval_bb(NnueAccum *na, int stm, const uint8_t *board,
                      const uint64_t bb[12], uint64_t board_hash) {
    (void)bb; (void)board_hash;
    if (!na) na = &g_nnue_accum;
    const NnueNet *net = na->net;
    if (!net || !net->ready) return 0;
    if (na->acc_dirty) return 0;

    int ptr = na->acc_ptr;
    if (!na->dirty_w_stack[ptr]) _ensure_lazy_perspective(na, 1);
    if (!na->dirty_b_stack[ptr]) _ensure_lazy_perspective(na, 0);
    if (na->dirty_w_stack[ptr]) _refresh_perspective(na, board, 1);
    if (na->dirty_b_stack[ptr]) _refresh_perspective(na, board, 0);

    const int16_t *acc_stm = (stm == 0) ? na->acc_stack_w[ptr] : na->acc_stack_b[ptr];
    const int16_t *acc_opp = (stm == 0) ? na->acc_stack_b[ptr] : na->acc_stack_w[ptr];

    uint8_t relu1[NN_L2_IN] __attribute__((aligned(32)));
    _screlu_perspective(acc_stm, net->L1B, relu1);
    _screlu_perspective(acc_opp, net->L1B, relu1 + NN_L1_OUT);

#if defined(__AVX2__)
    const __m256i ones = _mm256_set1_epi16(1);
    __m256i sum = _mm256_setzero_si256();
    for (int i = 0; i < NN_L2_IN; i += 32) {
        __m256i a = _mm256_load_si256((const __m256i*)(relu1 + i));
        __m256i w = _mm256_load_si256((const __m256i*)(FAST_HEAD_W + i));
        __m256i p = _mm256_maddubs_epi16(a, w);
        sum = _mm256_add_epi32(sum, _mm256_madd_epi16(p, ones));
    }
    __m128i hi128 = _mm256_extracti128_si256(sum, 1);
    __m128i lo128 = _mm256_castsi256_si128(sum);
    __m128i s128 = _mm_add_epi32(lo128, hi128);
    s128 = _mm_hadd_epi32(s128, s128);
    s128 = _mm_hadd_epi32(s128, s128);
    int32_t dot = _mm_cvtsi128_si32(s128);
#else
    int32_t dot = 0;
    for (int i = 0; i < NN_L2_IN; i++) {
        dot += (int32_t)relu1[i] * FAST_HEAD_W[i];
    }
#endif
    float cp = (float)dot * FAST_HEAD_INV_SCALE + FAST_HEAD_BIAS;
    if (cp < -2000.f) cp = -2000.f;
    if (cp >  2000.f) cp =  2000.f;
    return (int)(cp + (cp >= 0.f ? 0.5f : -0.5f));
}
"""
if "nnue_fast_eval_bb" not in nnue_c:
    nnue_c += fast_eval_code
    (CAND_DIR / "nnue.c").write_text(nnue_c, encoding="utf-8")

# 5. Patch search.c
search_c = (CAND_DIR / "search.c").read_text(encoding="utf-8")

# Add eval_stm_fast
eval_stm_target = "int eval_stm(Board *b) {"
new_eval_stm_decl = """int nnue_fast_eval_bb(NnueAccum *na, int stm, const uint8_t *board,
                      const uint64_t bb[12], uint64_t board_hash);

static inline int eval_stm_fast(Board *b) {
    return nnue_fast_eval_bb(b->nnue, b->turn == COL_W ? 0 : 1, b->b, b->bb, b->hash);
}

int eval_stm(Board *b) {"""
if "eval_stm_fast" not in search_c:
    assert eval_stm_target in search_c, "eval_stm_target not found"
    search_c = search_c.replace(eval_stm_target, new_eval_stm_decl, 1)

# Patch qsearch
old_qs = """    int stand = (qs_tte_hit && qs_tte.static_eval != TT_EVAL_NONE)
                 ? qs_tte.static_eval : eval_stm(b);"""
new_qs = """    int stand;
    if (qs_tte_hit && qs_tte.static_eval != TT_EVAL_NONE) {
        stand = qs_tte.static_eval;
    } else {
        int fast_val = eval_stm_fast(b);
        if (fast_val >= beta + 200) return beta;
        stand = eval_stm(b);
    }"""
assert old_qs in search_c, "old_qs not found"
search_c = search_c.replace(old_qs, new_qs)

# Patch alpha_beta
old_ab = """        raw_eval = (tte_hit && tte.static_eval != TT_EVAL_NONE)
                    ? tte.static_eval : eval_stm(b);"""
new_ab = """        if (tte_hit && tte.static_eval != TT_EVAL_NONE) {
            raw_eval = tte.static_eval;
        } else {
            if (!is_pv && depth <= 3 && beta < 18000) {
                int fast_val = eval_stm_fast(b);
                if (fast_val - (depth * 90) >= beta + 110) return beta;
            }
            raw_eval = eval_stm(b);
        }"""
assert old_ab in search_c, "old_ab not found"
search_c = search_c.replace(old_ab, new_ab)

# Patch RFP tunables
search_c = search_c.replace(".rfp_mult                  = TUNE_RFP_MULT_DEFAULT,", ".rfp_mult                  = 70,")
search_c = search_c.replace(".rfp_improving_bonus       = TUNE_RFP_IMPROVING_BONUS_DEFAULT,", ".rfp_improving_bonus       = 45,")

(CAND_DIR / "search.c").write_text(search_c, encoding="utf-8")

# 6. Compile
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
print("Compiling v605 candidate...")
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode != 0:
    print(f"FAILED to compile v605 candidate:\n{res.stderr}")
else:
    print(f"[OK] v605 candidate compiled successfully ({os.path.getsize(CAND_DIR / 'zchezz.exe'):,} bytes)")
