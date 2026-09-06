#!/usr/bin/env python3
from pathlib import Path

root=Path('engine/c/zchezz_v323')
main=root/'main.c'; s=main.read_text(encoding='utf-8')
old='#define ENGINE_VERSION "3.23"'
if s.count(old)!=1: raise SystemExit(f'version anchor count={s.count(old)}')
main.write_text(s.replace(old,'#define ENGINE_VERSION "3.30"',1),encoding='utf-8')

p=root/'nnue.c'; s=p.read_text(encoding='utf-8')
anchor='void nnue_push_na(NnueAccum *na, const uint8_t *board, const NNMove *m) {'
if s.count(anchor)!=1: raise SystemExit(f'push anchor count={s.count(anchor)}')
helper=r'''/* v3.30 experiment: baseline copies two aligned 512-byte HM accumulators
 * on every make. Force one interleaved, fully unrolled AVX2 copy path. */
static inline void nnue_copy_acc_pair(int16_t *restrict dw, int16_t *restrict db,
                                      const int16_t *restrict sw, const int16_t *restrict sb) {
#ifdef __AVX2__
    for (int i = 0; i < NN_L1_OUT; i += 64) {
        __m256i w0=_mm256_load_si256((const __m256i*)(sw+i+ 0));
        __m256i b0=_mm256_load_si256((const __m256i*)(sb+i+ 0));
        __m256i w1=_mm256_load_si256((const __m256i*)(sw+i+16));
        __m256i b1=_mm256_load_si256((const __m256i*)(sb+i+16));
        __m256i w2=_mm256_load_si256((const __m256i*)(sw+i+32));
        __m256i b2=_mm256_load_si256((const __m256i*)(sb+i+32));
        __m256i w3=_mm256_load_si256((const __m256i*)(sw+i+48));
        __m256i b3=_mm256_load_si256((const __m256i*)(sb+i+48));
        _mm256_store_si256((__m256i*)(dw+i+ 0),w0);
        _mm256_store_si256((__m256i*)(db+i+ 0),b0);
        _mm256_store_si256((__m256i*)(dw+i+16),w1);
        _mm256_store_si256((__m256i*)(db+i+16),b1);
        _mm256_store_si256((__m256i*)(dw+i+32),w2);
        _mm256_store_si256((__m256i*)(db+i+32),b2);
        _mm256_store_si256((__m256i*)(dw+i+48),w3);
        _mm256_store_si256((__m256i*)(db+i+48),b3);
    }
#else
    memcpy(dw, sw, NN_L1_OUT*sizeof(int16_t));
    memcpy(db, sb, NN_L1_OUT*sizeof(int16_t));
#endif
}

'''
s=s.replace(anchor,helper+anchor,1)
old='''    memcpy(na->acc_stack_w[dst], na->acc_stack_w[src], NN_L1_OUT*sizeof(int16_t));
    memcpy(na->acc_stack_b[dst], na->acc_stack_b[src], NN_L1_OUT*sizeof(int16_t));'''
new='''    nnue_copy_acc_pair(na->acc_stack_w[dst], na->acc_stack_b[dst],
                       na->acc_stack_w[src], na->acc_stack_b[src]);'''
if s.count(old)!=1: raise SystemExit(f'acc-copy anchor count={s.count(old)}')
p.write_text(s.replace(old,new,1),encoding='utf-8')
print('applied v3.30 NNUE accumulator AVX2 hot path')
