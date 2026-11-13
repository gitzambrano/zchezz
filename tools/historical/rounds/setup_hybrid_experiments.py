"""
tools/setup_hybrid_experiments.py — Set up and compile Hybrid Dual-NNUE Candidates.

Candidates:
1. exp_hybrid_gold: Dual-NNUE 2M Head with balanced margins (QS stand-pat +180cp, RFP +110cp) + Quiet SEE d6 (-40*d).
2. exp_hybrid_safe: Dual-NNUE 2M Head with safe QS margin (+200cp) and tuned RFP (+110cp) + Quiet SEE d6 (-40*d).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V334_DIR = ROOT / "engine" / "c" / "zchezz_v334"
EXP_ROOT = ROOT / "experiments" / "hybrid_candidates"
EXP_ROOT.mkdir(parents=True, exist_ok=True)

MILLION_HEAD_H = ROOT / "artifacts" / "fast_head_weights_million.h"
assert MILLION_HEAD_H.is_file(), "fast_head_weights_million.h missing!"

base_search = (V334_DIR / "search.c").read_text(encoding="utf-8")
base_nnue_c = (V334_DIR / "nnue.c").read_text(encoding="utf-8")

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

def build_search_hybrid(base: str, qs_margin: int, rfp_margin: int) -> str:
    s = base

    # Prototype and eval_stm_fast
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

    new_qs = f"""    /* Use TT-stored eval as stand-pat if available, with Dual-NNUE Fast Eval */
    int stand;
    if (qs_tte_hit && qs_tte.static_eval != TT_EVAL_NONE) {{
        stand = qs_tte.static_eval;
    }} else {{
        int fast_val = eval_stm_fast(b);
        if (fast_val >= beta + {qs_margin}) return beta;
        stand = eval_stm(b);
    }}"""
    assert old_qs in s, "old_qs not found"
    s = s.replace(old_qs, new_qs)

    # In search: shallow fast RFP cutoff
    old_rfp = """    if (!in_check) {
        raw_eval = (tte_hit && tte.static_eval != TT_EVAL_NONE)
                    ? tte.static_eval : eval_stm(b);"""

    new_rfp = f"""    if (!in_check) {{
        if (tte_hit && tte.static_eval != TT_EVAL_NONE) {{
            raw_eval = tte.static_eval;
        }} else {{
            if (!is_pv && depth <= 3 && beta < 18000) {{
                int fast_val = eval_stm_fast(b);
                if (fast_val - (depth * 90) >= beta + {rfp_margin}) return beta;
            }}
            raw_eval = eval_stm(b);
        }}"""
    assert old_rfp in s, "old_rfp not found"
    s = s.replace(old_rfp, new_rfp)

    # Quiet move SEE pruning extended to depth 6 (-40*d)
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

nc_dual = make_dual_nnue_c()

CONFIGS = {
    "exp_hybrid_gold": {
        "desc": "Dual-NNUE 2M Golden Balance: QS +180cp, RFP +110cp, Quiet SEE d6 (-40*d)",
        "search_c": build_search_hybrid(base_search, qs_margin=180, rfp_margin=110),
    },
    "exp_hybrid_safe": {
        "desc": "Dual-NNUE 2M Safe Balance: QS +200cp, RFP +110cp, Quiet SEE d6 (-40*d)",
        "search_c": build_search_hybrid(base_search, qs_margin=200, rfp_margin=110),
    },
}

def build_all():
    print(f"=== Setting up and compiling {len(CONFIGS)} Hybrid Candidates ===")
    for name, cfg in CONFIGS.items():
        edir = EXP_ROOT / name
        edir.mkdir(parents=True, exist_ok=True)
        
        (edir / "search.c").write_text(cfg["search_c"], encoding="utf-8")
        (edir / "nnue.c").write_text(nc_dual, encoding="utf-8")
        
        if not (edir / "nnue_weights.bin").is_file():
            shutil.copy2(V334_DIR / "nnue_weights.bin", edir / "nnue_weights.bin")
            
        shutil.copy2(MILLION_HEAD_H, edir / "fast_head_weights.h")

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
        print(f"[{name:<20}] BUILT OK: {nodes_line[0] if nodes_line else ''} | {nps_line[0] if nps_line else ''}")

    print("\nAll Hybrid candidates successfully built and benchmarked!")

if __name__ == "__main__":
    build_all()
