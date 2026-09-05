#!/usr/bin/env python3
"""Make v3.23 full-accumulator transitions exactly match v3.22 projection math.

Important subtlety: v3.22's AVX2/WASM fractional projection uses int16 mullo
followed by >>8. Therefore projection(q_new-q_old) is not generally equal to
projection(q_new)-projection(q_old). Fullacc must compute the latter.
"""
from __future__ import annotations
import argparse
from pathlib import Path

OLD = r'''static void _fullacc_apply_delta(int16_t *out,
                                 const NnueExtraState *from,
                                 const NnueExtraState *to,
                                 int stm) {
    int16_t a[NN_EXTRA], b[NN_EXTRA];
    _fullacc_q(from, stm, a);
    _fullacc_q(to,   stm, b);
    for (int j = 0; j < NN_EXTRA; ++j) {
        int16_t d = (int16_t)(b[j] - a[j]);
        if (d) _project_feat_add(out, j, d);
    }
}
'''

NEW = r'''/* Apply contribution(q_new) - contribution(q_old), reproducing the exact
 * architecture-specific arithmetic used by _project_feat_add().  In
 * particular, AVX2/WASM fractional features intentionally use int16 mullo
 * before >>8, so multiplying the signed delta would NOT be equivalent. */
static inline void _fullacc_q_transition(int16_t *out, int j,
                                         int16_t q_old, int16_t q_new) {
    const int16_t *row = _nnL1WT + (NN_HM_IN+j)*NN_L1_OUT;
#ifdef __AVX2__
    __m256i qo = _mm256_set1_epi16(q_old);
    __m256i qn = _mm256_set1_epi16(q_new);
    __m256i z = _mm256_setzero_si256();
    for (int o=0; o<NN_L1_OUT; o+=16) {
        __m256i r = _mm256_load_si256((const __m256i*)(row + o));
        __m256i co = q_old == 0 ? z : (q_old == 256 ? r :
                     _mm256_srai_epi16(_mm256_mullo_epi16(qo, r), 8));
        __m256i cn = q_new == 0 ? z : (q_new == 256 ? r :
                     _mm256_srai_epi16(_mm256_mullo_epi16(qn, r), 8));
        __m256i v = _mm256_load_si256((const __m256i*)(out + o));
        v = _mm256_add_epi16(v, _mm256_sub_epi16(cn, co));
        _mm256_store_si256((__m256i*)(out + o), v);
    }
#elif defined(__wasm_simd128__)
    v128_t qo = wasm_i16x8_splat(q_old);
    v128_t qn = wasm_i16x8_splat(q_new);
    v128_t z = wasm_i16x8_splat(0);
    for (int o=0; o<NN_L1_OUT; o+=8) {
        v128_t r = wasm_v128_load(row + o);
        v128_t co = q_old == 0 ? z : (q_old == 256 ? r :
                     wasm_i16x8_shr(wasm_i16x8_mul(qo, r), 8));
        v128_t cn = q_new == 0 ? z : (q_new == 256 ? r :
                     wasm_i16x8_shr(wasm_i16x8_mul(qn, r), 8));
        v128_t v = wasm_v128_load(out + o);
        wasm_v128_store(out + o, wasm_i16x8_add(v, wasm_i16x8_sub(cn, co)));
    }
#else
    for (int o=0; o<NN_L1_OUT; ++o) {
        int16_t co = q_old == 0 ? 0 : (q_old == 256 ? row[o] :
                     (int16_t)(((int32_t)q_old * row[o]) >> 8));
        int16_t cn = q_new == 0 ? 0 : (q_new == 256 ? row[o] :
                     (int16_t)(((int32_t)q_new * row[o]) >> 8));
        out[o] = (int16_t)(out[o] + (int16_t)(cn - co));
    }
#endif
}

static void _fullacc_apply_delta(int16_t *out,
                                 const NnueExtraState *from,
                                 const NnueExtraState *to,
                                 int stm) {
    int16_t a[NN_EXTRA], b[NN_EXTRA];
    _fullacc_q(from, stm, a);
    _fullacc_q(to,   stm, b);
    for (int j = 0; j < NN_EXTRA; ++j)
        if (a[j] != b[j]) _fullacc_q_transition(out, j, a[j], b[j]);
}
'''


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',type=Path,required=True)
    a=ap.parse_args()
    p=a.root/'nnue.c'
    t=p.read_text(encoding='utf-8')
    n=t.count(OLD)
    if n != 1:
        raise SystemExit(f'expected one old fullacc delta block, found {n}')
    p.write_text(t.replace(OLD,NEW,1),encoding='utf-8')
    print('patched exact quantized fullacc transitions')

if __name__=='__main__':
    main()
