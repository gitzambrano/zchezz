"""
tools/build_v605_modern.py — Build modern v605 with sf32 TT, Staged Move Gen, and Bucket Invalidation Fix.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V335_DIR = ROOT / "engine" / "c" / "zchezz_v335"
V604_DIR = ROOT / "engine" / "c" / "zchezz_v604"
TARGET_DIR = ROOT / "experiments" / "v605_modern"
TARGET_DIR.mkdir(parents=True, exist_ok=True)

# 1. Copy book, poly_keys, stdendian, syzygy, tbconfig
for f in ["book.c", "book.h", "poly_keys.h", "stdendian.h", "syzygy.c", "syzygy.h", "tbconfig.h", "Makefile"]:
    src = V335_DIR / f
    if src.is_file():
        shutil.copy2(src, TARGET_DIR / f)

# 2. Copy NNU5 weights
shutil.copy2(V604_DIR / "nnue_weights.bin", TARGET_DIR / "nnue_weights.bin")

# 3. Copy fast_head_weights_nnu5.h as fast_head_weights.h
shutil.copy2(ROOT / "artifacts" / "fast_head_weights_nnu5.h", TARGET_DIR / "fast_head_weights.h")

# 4. Board files: take from v335 and adjust for NNU5
board_c = (V335_DIR / "board.c").read_text(encoding="utf-8")
board_c = board_c.replace(".ext_dirty = {1, 1}", "/* no ext features */")
old_push = """    if(nnue_ready() && b->nnue){
        NNMove nm; nm.from_sq=(uint8_t)f; nm.to_sq=(uint8_t)to;
        nm.prom=m->prom; nm.is_epc=m->epc; nm.castle=m->castle;
        nnue_push_na(b->nnue, b->b, &nm);
    }"""
new_push = """    if(nnue_ready() && b->nnue){
        NNMove nm; nm.from_sq=(uint8_t)f; nm.to_sq=(uint8_t)to;
        nm.prom=m->prom; nm.is_epc=m->epc; nm.castle=m->castle;
        nm.wk_sq=b->wk; nm.bk_sq=b->bk;
        nnue_push_na(b->nnue, b->b, &nm);
    }"""
assert old_push in board_c
board_c = board_c.replace(old_push, new_push)
(TARGET_DIR / "board.c").write_text(board_c, encoding="utf-8")
shutil.copy2(V335_DIR / "board.h", TARGET_DIR / "board.h")

# 5. Search files: take from v335 directly (sf32 TT + staged move gen + dynamic RFP)
shutil.copy2(V335_DIR / "search.c", TARGET_DIR / "search.c")
shutil.copy2(V335_DIR / "search.h", TARGET_DIR / "search.h")
shutil.copy2(V335_DIR / "main.c", TARGET_DIR / "main.c")

# 6. NNUE files: NNU5 with Bucket Invalidation Fix + AVX2 Vectorized Refresh + Dual-Head
nnue_h = (V604_DIR / "nnue.h").read_text(encoding="utf-8")
if "nnue_fast_eval_bb" not in nnue_h:
    nnue_h += "\nint nnue_fast_eval_bb(NnueAccum *na, int stm, const uint8_t *board, const uint64_t bb[12], uint64_t board_hash);\n"
(TARGET_DIR / "nnue.h").write_text(nnue_h, encoding="utf-8")

nnue_c = (V604_DIR / "nnue.c").read_text(encoding="utf-8")

# Fix _refresh_perspective with AVX2 vectorization
old_ref_loop = """            const int16_t *row = L1WT + (size_t)(bw * NN_FEAT_PER_BUCKET + rel * 64 + sq_pov) * NN_L1_OUT;
            for (int o = 0; o < NN_L1_OUT; o++) acc[o] += row[o];"""
new_ref_loop = """            const int16_t *row = L1WT + (size_t)(bw * NN_FEAT_PER_BUCKET + rel * 64 + sq_pov) * NN_L1_OUT;
#if defined(__AVX2__)
            for (int o = 0; o < NN_L1_OUT; o += 16) {
                __m256i a = _mm256_load_si256((const __m256i*)(acc + o));
                __m256i r = _mm256_load_si256((const __m256i*)(row + o));
                _mm256_store_si256((__m256i*)(acc + o), _mm256_add_epi16(a, r));
            }
#else
            for (int o = 0; o < NN_L1_OUT; o++) acc[o] += row[o];
#endif"""
assert old_ref_loop in nnue_c
nnue_c = nnue_c.replace(old_ref_loop, new_ref_loop)

# Fix black refresh loop too
old_bref_loop = """            const int16_t *row = L1WT + (size_t)(bb * NN_FEAT_PER_BUCKET + rel * 64 + sq_pov) * NN_L1_OUT;
            for (int o = 0; o < NN_L1_OUT; o++) acc[o] += row[o];"""
new_bref_loop = """            const int16_t *row = L1WT + (size_t)(bb * NN_FEAT_PER_BUCKET + rel * 64 + sq_pov) * NN_L1_OUT;
#if defined(__AVX2__)
            for (int o = 0; o < NN_L1_OUT; o += 16) {
                __m256i a = _mm256_load_si256((const __m256i*)(acc + o));
                __m256i r = _mm256_load_si256((const __m256i*)(row + o));
                _mm256_store_si256((__m256i*)(acc + o), _mm256_add_epi16(a, r));
            }
#else
            for (int o = 0; o < NN_L1_OUT; o++) acc[o] += row[o];
#endif"""
assert old_bref_loop in nnue_c
nnue_c = nnue_c.replace(old_bref_loop, new_bref_loop)

# Fix King Bucket Invalidation Bug in nnue_push_na
old_push_body = """    if (m->castle) {
        dw = 1; db = 1;
    } else {
        int f = m->from_sq, to = m->to_sq;
        uint8_t p = board[f], cap = board[to];
        if (PC_TYPE(p) == PT_KING) {
            dw = 1; db = 1;
        } else {
            LDOP(p, f, -1);
            if (cap) LDOP(cap, to, -1);
            if (m->is_epc) {
                int e = (PC_COLOR(p) == COL_W) ? to + 8 : to - 8;
                if (board[e]) LDOP(board[e], e, -1);
            }
            uint8_t land = m->prom ? (uint8_t)(PC_COLOR(p) | m->prom) : p;
            LDOP(land, to, +1);
        }
    }"""

new_push_body = """    if (m->castle) {
        if (m->castle == 1 || m->castle == 2) {
            dw = 1;
            /* In black POV, king and rook are pieces (black bucket unaffected) */
            const int *csq = _castle_sq[m->castle];
            LDOP(board[csq[0]], csq[0], -1);
            LDOP(board[csq[0]], csq[1], +1);
            LDOP(board[csq[2]], csq[2], -1);
            LDOP(board[csq[2]], csq[3], +1);
        } else {
            db = 1;
            /* In white POV, king and rook are pieces (white bucket unaffected) */
            const int *csq = _castle_sq[m->castle];
            LDOP(board[csq[0]], csq[0], -1);
            LDOP(board[csq[0]], csq[1], +1);
            LDOP(board[csq[2]], csq[2], -1);
            LDOP(board[csq[2]], csq[3], +1);
        }
    } else {
        int f = m->from_sq, to = m->to_sq;
        uint8_t p = board[f], cap = board[to];
        if (PC_TYPE(p) == PT_KING) {
            if (PC_COLOR(p) == COL_W) {
                dw = 1;
                /* Black king didn't move: update white king as piece in black perspective */
                LDOP(p, f, -1);
                if (cap) LDOP(cap, to, -1);
                LDOP(p, to, +1);
            } else {
                db = 1;
                /* White king didn't move: update black king as piece in white perspective */
                LDOP(p, f, -1);
                if (cap) LDOP(cap, to, -1);
                LDOP(p, to, +1);
            }
        } else {
            LDOP(p, f, -1);
            if (cap) LDOP(cap, to, -1);
            if (m->is_epc) {
                int e = (PC_COLOR(p) == COL_W) ? to + 8 : to - 8;
                if (board[e]) LDOP(board[e], e, -1);
            }
            uint8_t land = m->prom ? (uint8_t)(PC_COLOR(p) | m->prom) : p;
            LDOP(land, to, +1);
        }
    }"""
assert old_push_body in nnue_c
nnue_c = nnue_c.replace(old_push_body, new_push_body)

# Add Dual-NNUE fast evaluation to nnue.c
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
(TARGET_DIR / "nnue.c").write_text(nnue_c, encoding="utf-8")

# 7. Compile
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
print("Compiling modern v605...")
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode != 0:
    print(f"FAILED to compile modern v605:\n{res.stderr}")
else:
    print(f"[OK] Modern v605 compiled successfully ({os.path.getsize(TARGET_DIR / 'zchezz.exe'):,} bytes)")
