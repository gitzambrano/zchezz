#define _POSIX_C_SOURCE 200809L
/* nnue.c — Zchezz v600 NNU5 HalfKAv2_hm-32Bucket evaluator
 *
 * See nnue.h for the architecture specification:
 *   features  22528 per perspective
 *   L1        22528 -> 64
 *   SCReLU    clamp to QA, square, then >> 8
 *   concat    [stm 64 | opp 64] = 128
 *   L2        128 -> 16
 *   L3        16 -> 1
 */

#include "nnue.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#if defined(__AVX2__) || defined(__AVXVNNI__)
#  include <immintrin.h>
#elif defined(__wasm_simd128__)
#  include <wasm_simd128.h>
#endif

#define PC_COLOR(p)  ((p) & 24)
#define PC_TYPE(p)   ((p) &  7)
#define COL_W  8
#define COL_B 16
#define PT_KING 6

static void *zmalloc32(size_t bytes) {
    void *ptr = NULL;
#if defined(_WIN32)
    ptr = _aligned_malloc(bytes, 32);
#elif defined(__APPLE__) || defined(__linux__)
    if (posix_memalign(&ptr, 32, bytes) != 0) ptr = NULL;
#else
    ptr = malloc(bytes);
#endif
    return ptr;
}

static void zfree32(void *ptr) {
#if defined(_WIN32)
    _aligned_free(ptr);
#else
    free(ptr);
#endif
}

struct NnueNet {
    int16_t *L1WT;     /* [22528][64] int16 */
    int32_t *L1B;      /* [64] int32 */
    int8_t  *L2W;      /* [16][128] int8 */
    int32_t *L2B;      /* [16] int32 */
    int8_t  *L3W;      /* [16] int8 */
    float    L3B;
    float    OutScale;
    int      ready;
};

NnueNet *g_nnue_net = NULL;
extern NnueAccum g_nnue_accum;

NnueNet *nnue_net_create(void) {
    NnueNet *net = (NnueNet *)calloc(1, sizeof(NnueNet));
    return net;
}

void nnue_net_destroy(NnueNet *net) {
    if (!net) return;
    zfree32(net->L1WT);
    zfree32(net->L1B);
    zfree32(net->L2W);
    zfree32(net->L2B);
    zfree32(net->L3W);
    free(net);
}

int nnue_net_ready(const NnueNet *net) {
    return net && net->ready;
}

int nnue_ready(void) {
    return nnue_net_ready(g_nnue_net);
}

static inline int _king_bucket(int pov_sq, int *hm) {
    int rank = pov_sq >> 3;
    int file = pov_sq & 7;
    if (file >= 4) {
        *hm = 1;
        file = 7 - file;
    } else {
        *hm = 0;
    }
    return rank * 4 + file;
}

int nnue_king_bucket_w(int wk_zsq, int *hm) {
    return _king_bucket(wk_zsq ^ 56, hm);
}

int nnue_king_bucket_b(int bk_zsq, int *hm) {
    return _king_bucket(bk_zsq, hm);
}

static inline int _piece_rel(uint8_t p, int white_pov) {
    int pt = PC_TYPE(p);
    if (pt < 1 || pt > 6) return -1;
    int is_white = (PC_COLOR(p) == COL_W);
    int is_ally = (is_white == white_pov);
    if (is_ally) {
        if (pt == PT_KING) return -1;
        return pt - 1; /* 0..4 */
    } else {
        if (pt == PT_KING) return 10;
        return 5 + (pt - 1); /* 5..9 */
    }
}

int nnue_feature_index(uint8_t p, int zsq, int white_pov, int bucket, int hm) {
    int rel = _piece_rel(p, white_pov);
    if (rel < 0) return -1;
    int pov_sq = white_pov ? (zsq ^ 56) : zsq;
    if (hm) pov_sq ^= 7;
    return bucket * NN_FEAT_PER_BUCKET + rel * 64 + pov_sq;
}

static inline void _acc_add_piece(int16_t *accW, int16_t *accB,
                                  const int16_t *L1WT,
                                  uint8_t p, int zsq,
                                  int bkt_w, int hm_w,
                                  int bkt_b, int hm_b,
                                  int updW, int updB) {
    int relW = _piece_rel(p, 1);
    int relB = _piece_rel(p, 0);

    if (updW && relW >= 0) {
        int sqW = (zsq ^ 56) ^ (hm_w ? 7 : 0);
        const int16_t *wRow = L1WT + (size_t)(bkt_w * NN_FEAT_PER_BUCKET + relW * 64 + sqW) * NN_L1_OUT;
#ifdef __AVX2__
        _mm_prefetch((const char*)wRow, _MM_HINT_T0);
        for (int o = 0; o < NN_L1_OUT; o += 16) {
            __m256i aw = _mm256_load_si256((const __m256i*)(accW + o));
            aw = _mm256_add_epi16(aw, _mm256_load_si256((const __m256i*)(wRow + o)));
            _mm256_store_si256((__m256i*)(accW + o), aw);
        }
#else
        for (int o = 0; o < NN_L1_OUT; o++) accW[o] += wRow[o];
#endif
    }

    if (updB && relB >= 0) {
        int sqB = zsq ^ (hm_b ? 7 : 0);
        const int16_t *bRow = L1WT + (size_t)(bkt_b * NN_FEAT_PER_BUCKET + relB * 64 + sqB) * NN_L1_OUT;
#ifdef __AVX2__
        _mm_prefetch((const char*)bRow, _MM_HINT_T0);
        for (int o = 0; o < NN_L1_OUT; o += 16) {
            __m256i ab = _mm256_load_si256((const __m256i*)(accB + o));
            ab = _mm256_add_epi16(ab, _mm256_load_si256((const __m256i*)(bRow + o)));
            _mm256_store_si256((__m256i*)(accB + o), ab);
        }
#else
        for (int o = 0; o < NN_L1_OUT; o++) accB[o] += bRow[o];
#endif
    }
}

static inline void _acc_sub_piece(int16_t *accW, int16_t *accB,
                                  const int16_t *L1WT,
                                  uint8_t p, int zsq,
                                  int bkt_w, int hm_w,
                                  int bkt_b, int hm_b,
                                  int updW, int updB) {
    int relW = _piece_rel(p, 1);
    int relB = _piece_rel(p, 0);

    if (updW && relW >= 0) {
        int sqW = (zsq ^ 56) ^ (hm_w ? 7 : 0);
        const int16_t *wRow = L1WT + (size_t)(bkt_w * NN_FEAT_PER_BUCKET + relW * 64 + sqW) * NN_L1_OUT;
#ifdef __AVX2__
        _mm_prefetch((const char*)wRow, _MM_HINT_T0);
        for (int o = 0; o < NN_L1_OUT; o += 16) {
            __m256i aw = _mm256_load_si256((const __m256i*)(accW + o));
            aw = _mm256_sub_epi16(aw, _mm256_load_si256((const __m256i*)(wRow + o)));
            _mm256_store_si256((__m256i*)(accW + o), aw);
        }
#else
        for (int o = 0; o < NN_L1_OUT; o++) accW[o] -= wRow[o];
#endif
    }

    if (updB && relB >= 0) {
        int sqB = zsq ^ (hm_b ? 7 : 0);
        const int16_t *bRow = L1WT + (size_t)(bkt_b * NN_FEAT_PER_BUCKET + relB * 64 + sqB) * NN_L1_OUT;
#ifdef __AVX2__
        _mm_prefetch((const char*)bRow, _MM_HINT_T0);
        for (int o = 0; o < NN_L1_OUT; o += 16) {
            __m256i ab = _mm256_load_si256((const __m256i*)(accB + o));
            ab = _mm256_sub_epi16(ab, _mm256_load_si256((const __m256i*)(bRow + o)));
            _mm256_store_si256((__m256i*)(accB + o), ab);
        }
#else
        for (int o = 0; o < NN_L1_OUT; o++) accB[o] -= bRow[o];
#endif
    }
}

static int _load_weights(NnueNet *net, const uint8_t *buf, size_t len) {
    if (len < 8 || buf[0]!='N'||buf[1]!='N'||buf[2]!='U'||buf[3]!='5') {
        fprintf(stderr, "[NNUE] Bad magic (expected NNU5)\n"); return -1;
    }
    size_t off = 4 + 4;

    uint32_t dims[5];
    memcpy(dims, buf + off, 5 * sizeof(uint32_t)); off += 5 * 4;
    const uint32_t want[5] = { NN_L1_IN, NN_L1_OUT, NN_L2_IN, NN_L2_OUT, NN_L3_IN };
    for (int i = 0; i < 5; i++) {
        if (dims[i] != want[i]) {
            fprintf(stderr, "[NNUE] Dim mismatch at %d: file=%u expected=%u\n", i, dims[i], want[i]);
            return -1;
        }
    }

    float scales[4];
    memcpy(scales, buf + off, 4 * sizeof(float)); off += 16;
    net->OutScale = scales[3];

    const size_t L1_SZ = (size_t)NN_L1_IN  * NN_L1_OUT;
    const size_t L2_SZ = (size_t)NN_L2_OUT * NN_L2_IN;
    size_t need = off + L1_SZ * 2 + NN_L1_OUT * 4 + L2_SZ + NN_L2_OUT * 4 + NN_L3_IN + 4;
    if (len < need) {
        fprintf(stderr, "[NNUE] File too small (%zu < %zu)\n", len, need); return -1;
    }

    zfree32(net->L1WT); zfree32(net->L1B);
    zfree32(net->L2W);  zfree32(net->L2B);
    zfree32(net->L3W);

    net->L1WT = (int16_t *)zmalloc32(L1_SZ     * sizeof(int16_t));
    net->L1B  = (int32_t *)zmalloc32(NN_L1_OUT * sizeof(int32_t));
    net->L2W  = (int8_t  *)zmalloc32(L2_SZ     * sizeof(int8_t));
    net->L2B  = (int32_t *)zmalloc32(NN_L2_OUT * sizeof(int32_t));
    net->L3W  = (int8_t  *)zmalloc32(NN_L3_IN  * sizeof(int8_t));

    if (!net->L1WT || !net->L1B || !net->L2W || !net->L2B || !net->L3W) {
        fprintf(stderr, "[NNUE] malloc failed\n"); return -1;
    }

    memcpy(net->L1WT, buf + off, L1_SZ * 2);     off += L1_SZ * 2;
    memcpy(net->L1B,  buf + off, NN_L1_OUT * 4); off += NN_L1_OUT * 4;
    memcpy(net->L2W,  buf + off, L2_SZ);         off += L2_SZ;
    memcpy(net->L2B,  buf + off, NN_L2_OUT * 4); off += NN_L2_OUT * 4;
    memcpy(net->L3W,  buf + off, NN_L3_IN);      off += NN_L3_IN;
    memcpy(&net->L3B, buf + off, 4);

    net->ready = 1;
    return 0;
}

int nnue_load_from_mem(const uint8_t *data, size_t len) {
    if (!g_nnue_net) {
        g_nnue_net = nnue_net_create();
        if (!g_nnue_net) return -1;
    }
    int r = _load_weights(g_nnue_net, data, len);
    if (r == 0) g_nnue_accum.net = g_nnue_net;
    return r;
}

int nnue_load(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "[NNUE] Cannot open: %s\n", path); return -1; }
    fseek(f, 0, SEEK_END); long fsize = ftell(f); fseek(f, 0, SEEK_SET);
    if (fsize <= 0) { fclose(f); return -1; }
    uint8_t *buf = (uint8_t *)malloc((size_t)fsize);
    if (!buf) { fclose(f); return -1; }
    if ((long)fread(buf, 1, (size_t)fsize, f) != fsize) { free(buf); fclose(f); return -1; }
    fclose(f);
    int r = nnue_load_from_mem(buf, (size_t)fsize);
    free(buf);
    if (r == 0)
        fprintf(stderr, "[NNUE] Loaded: %s (NNU5 HalfKAv2_hm-32B %d->%d->%d->1)\n",
                path, NN_L1_IN, NN_L1_OUT, NN_L2_OUT);
    return r;
}

void nnue_reset(NnueAccum *na) {
    na->acc_dirty = 1;
    na->acc_ptr   = 0;
    memset(na->acc_valid_w, 0, sizeof(na->acc_valid_w));
    memset(na->acc_valid_b, 0, sizeof(na->acc_valid_b));
}

void nnue_reset_global(void) { nnue_reset(&g_nnue_accum); }

static inline void _find_kings(const uint8_t *board, int *wk, int *bk) {
    *wk = 0; *bk = 0;
    for (int sq = 0; sq < 64; sq++) {
        uint8_t p = board[sq];
        if (PC_TYPE(p) != PT_KING) continue;
        if (PC_COLOR(p) == COL_W) *wk = sq; else *bk = sq;
    }
}

void nnue_rebuild(NnueAccum *na, const uint8_t *board) {
    if (!na->net) { na->acc_dirty = 1; return; }
    const int16_t *L1WT = na->net->L1WT;

    int wk, bk;
    _find_kings(board, &wk, &bk);
    int hm_w = 0, hm_b = 0;
    int bw = nnue_king_bucket_w(wk, &hm_w);
    int bb = nnue_king_bucket_b(bk, &hm_b);

    int16_t *dW = na->acc_w, *dB = na->acc_b;
    memset(dW, 0, NN_L1_OUT * sizeof(int16_t));
    memset(dB, 0, NN_L1_OUT * sizeof(int16_t));
    for (int sq = 0; sq < 64; sq++) {
        uint8_t p = board[sq];
        if (!p) continue;
        _acc_add_piece(dW, dB, L1WT, p, sq, bw, hm_w, bb, hm_b, 1, 1);
    }

    na->acc_ptr   = 0;
    na->acc_dirty = 0;
    memcpy(na->acc_stack_w[0], dW, NN_L1_OUT * sizeof(int16_t));
    memcpy(na->acc_stack_b[0], dB, NN_L1_OUT * sizeof(int16_t));
    na->bucket_w_stack[0] = (uint8_t)bw;
    na->bucket_b_stack[0] = (uint8_t)bb;
    na->hm_w_stack[0]     = (uint8_t)hm_w;
    na->hm_b_stack[0]     = (uint8_t)hm_b;
    na->dirty_w_stack[0]  = 0;
    na->dirty_b_stack[0]  = 0;
    memset(na->acc_valid_w, 0, sizeof(na->acc_valid_w));
    memset(na->acc_valid_b, 0, sizeof(na->acc_valid_b));
    na->acc_valid_w[0] = 1;
    na->acc_valid_b[0] = 1;
    na->delta_n[0] = 0;
}

static void _refresh_perspective(NnueAccum *na, const uint8_t *board, int white_pov) {
    if (!na->net) return;
    const int16_t *L1WT = na->net->L1WT;

    int wk, bk;
    _find_kings(board, &wk, &bk);
    int ptr = na->acc_ptr;

    if (white_pov) {
        int hm_w = 0;
        int bw = nnue_king_bucket_w(wk, &hm_w);
        int16_t *acc = na->acc_stack_w[ptr];
        memset(acc, 0, NN_L1_OUT * sizeof(int16_t));
        for (int sq = 0; sq < 64; sq++) {
            uint8_t p = board[sq];
            if (!p) continue;
            int rel = _piece_rel(p, 1);
            if (rel < 0) continue;
            int sq_pov = (sq ^ 56) ^ (hm_w ? 7 : 0);
            const int16_t *row = L1WT + (size_t)(bw * NN_FEAT_PER_BUCKET + rel * 64 + sq_pov) * NN_L1_OUT;
            for (int o = 0; o < NN_L1_OUT; o++) acc[o] += row[o];
        }
        na->bucket_w_stack[ptr] = (uint8_t)bw;
        na->hm_w_stack[ptr]     = (uint8_t)hm_w;
        na->dirty_w_stack[ptr]  = 0;
        na->acc_valid_w[ptr]    = 1;
    } else {
        int hm_b = 0;
        int bb = nnue_king_bucket_b(bk, &hm_b);
        int16_t *acc = na->acc_stack_b[ptr];
        memset(acc, 0, NN_L1_OUT * sizeof(int16_t));
        for (int sq = 0; sq < 64; sq++) {
            uint8_t p = board[sq];
            if (!p) continue;
            int rel = _piece_rel(p, 0);
            if (rel < 0) continue;
            int sq_pov = sq ^ (hm_b ? 7 : 0);
            const int16_t *row = L1WT + (size_t)(bb * NN_FEAT_PER_BUCKET + rel * 64 + sq_pov) * NN_L1_OUT;
            for (int o = 0; o < NN_L1_OUT; o++) acc[o] += row[o];
        }
        na->bucket_b_stack[ptr] = (uint8_t)bb;
        na->hm_b_stack[ptr]     = (uint8_t)hm_b;
        na->dirty_b_stack[ptr]  = 0;
        na->acc_valid_b[ptr]    = 1;
    }
}

static const int _castle_sq[5][4] = {
    {0,0,0,0},{60,62,63,61},{60,58,56,59},{4,6,7,5},{4,2,0,3},
};

void nnue_push_na(NnueAccum *na, const uint8_t *board, const NNMove *m) {
    if (!na->net) { na->acc_dirty = 1; return; }

    int src = na->acc_ptr, dst = src + 1;
    if (dst >= NN_ACC_STACK) { na->acc_dirty = 1; return; }
    if (na->acc_dirty) { nnue_rebuild(na, board); src = 0; dst = 1; }

    int bw = na->bucket_w_stack[src], bb = na->bucket_b_stack[src];
    int hmw = na->hm_w_stack[src],    hmb = na->hm_b_stack[src];
    int dw = na->dirty_w_stack[src],  db = na->dirty_b_stack[src];
    int n = 0;

#define LDOP(pc_, sq_, sign_) do { \
        uint8_t _pc=(uint8_t)(pc_); \
        if (_pc && PC_TYPE(_pc) != PT_KING && n < 4) { \
            na->delta_piece[dst][n]=_pc; na->delta_sq[dst][n]=(uint8_t)(sq_); \
            na->delta_sign[dst][n]=(int8_t)(sign_); n++; \
        } \
    } while (0)

    if (m->castle) {
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
    }
#undef LDOP

    na->delta_n[dst] = (uint8_t)n;
    na->bucket_w_stack[dst] = (uint8_t)bw;
    na->bucket_b_stack[dst] = (uint8_t)bb;
    na->hm_w_stack[dst]     = (uint8_t)hmw;
    na->hm_b_stack[dst]     = (uint8_t)hmb;
    na->dirty_w_stack[dst]  = (uint8_t)dw;
    na->dirty_b_stack[dst]  = (uint8_t)db;
    na->acc_valid_w[dst]    = 0;
    na->acc_valid_b[dst]    = 0;
    na->acc_ptr             = dst;
}

static inline void _ensure_lazy_perspective(NnueAccum *na, int white_pov) {
    int p = na->acc_ptr;
    uint8_t *valid = white_pov ? na->acc_valid_w : na->acc_valid_b;
    uint8_t *dirty = white_pov ? na->dirty_w_stack : na->dirty_b_stack;
    if (valid[p] || dirty[p]) return;

    int q = p;
    while (q > 0 && !valid[q] && !dirty[q]) q--;
    if (!valid[q] || dirty[q]) return;

    const int16_t *L1WT = na->net->L1WT;
    int16_t (*stack)[NN_L1_OUT] = white_pov ? na->acc_stack_w : na->acc_stack_b;

    for (int step = q + 1; step <= p; step++) {
        memcpy(stack[step], stack[step - 1], NN_L1_OUT * sizeof(int16_t));
        int bw = na->bucket_w_stack[step], bb = na->bucket_b_stack[step];
        int hmw = na->hm_w_stack[step],    hmb = na->hm_b_stack[step];
        int dn = na->delta_n[step];
        for (int i = 0; i < dn; i++) {
            uint8_t pc = na->delta_piece[step][i];
            int sq     = na->delta_sq[step][i];
            int sgn    = na->delta_sign[step][i];
            if (sgn > 0)
                _acc_add_piece(stack[step], stack[step], L1WT, pc, sq, bw, hmw, bb, hmb, white_pov, !white_pov);
            else
                _acc_sub_piece(stack[step], stack[step], L1WT, pc, sq, bw, hmw, bb, hmb, white_pov, !white_pov);
        }
        valid[step] = 1;
    }
}

void nnue_pop_na(NnueAccum *na) {
    if (na->acc_ptr > 0) na->acc_ptr--;
}

void nnue_push(const uint8_t *board, const NNMove *m) {
    nnue_push_na(&g_nnue_accum, board, m);
}

void nnue_pop(void) {
    nnue_pop_na(&g_nnue_accum);
}

static inline void _screlu_perspective(const int16_t *acc, const int32_t *L1B, uint8_t *dst) {
#if defined(__AVX2__)
    const __m256i zero = _mm256_setzero_si256();
    const __m256i v255 = _mm256_set1_epi32(255);
    for (int o = 0; o < NN_L1_OUT; o += 16) {
        __m128i a_lo = _mm_load_si128((const __m128i*)(acc + o));
        __m128i a_hi = _mm_load_si128((const __m128i*)(acc + o + 8));
        __m256i s_lo = _mm256_add_epi32(_mm256_cvtepi16_epi32(a_lo),
                                        _mm256_load_si256((const __m256i*)(L1B + o)));
        __m256i s_hi = _mm256_add_epi32(_mm256_cvtepi16_epi32(a_hi),
                                        _mm256_load_si256((const __m256i*)(L1B + o + 8)));
        s_lo = _mm256_min_epi32(_mm256_max_epi32(s_lo, zero), v255);
        s_hi = _mm256_min_epi32(_mm256_max_epi32(s_hi, zero), v255);
        s_lo = _mm256_srli_epi32(_mm256_mullo_epi32(s_lo, s_lo), 8);
        s_hi = _mm256_srli_epi32(_mm256_mullo_epi32(s_hi, s_hi), 8);
        __m256i p16 = _mm256_packus_epi32(s_lo, s_hi);
        p16 = _mm256_permute4x64_epi64(p16, _MM_SHUFFLE(3,1,2,0));
        __m128i lo16 = _mm256_castsi256_si128(p16);
        __m128i hi16 = _mm256_extracti128_si256(p16, 1);
        _mm_store_si128((__m128i*)(dst + o), _mm_packus_epi16(lo16, hi16));
    }
#else
    for (int o = 0; o < NN_L1_OUT; o++) {
        int32_t v = (int32_t)acc[o] + L1B[o];
        if (v < 0) v = 0; else if (v > 255) v = 255;
        dst[o] = (uint8_t)((v * v) >> 8);
    }
#endif
}

#if defined(__AVX2__)
static inline int32_t _hsum_epi32(__m256i v) {
    __m128i lo = _mm256_castsi256_si128(v);
    __m128i hi = _mm256_extracti128_si256(v, 1);
    __m128i s1 = _mm_add_epi32(lo, hi);
    __m128i s2 = _mm_hadd_epi32(s1, s1);
    __m128i s3 = _mm_hadd_epi32(s2, s2);
    return _mm_cvtsi128_si32(s3);
}
#endif

static int _nnue_forward(NnueAccum *na, int stm, const uint8_t *board) {
    const NnueNet *net = na->net;
    if (!net || !net->ready) return 0;
    if (na->acc_dirty) return 0;

    const int16_t *L1WT     = net->L1WT;
    const int32_t *L1B      = net->L1B;
    const int8_t  *L2W      = net->L2W;
    const int32_t *L2B      = net->L2B;
    const int8_t  *L3W      = net->L3W;
    const float    L3B      = net->L3B;
    const float    OutScale = net->OutScale;

    int ptr = na->acc_ptr;
    if (!na->dirty_w_stack[ptr]) _ensure_lazy_perspective(na, 1);
    if (!na->dirty_b_stack[ptr]) _ensure_lazy_perspective(na, 0);
    if (na->dirty_w_stack[ptr]) _refresh_perspective(na, board, 1);
    if (na->dirty_b_stack[ptr]) _refresh_perspective(na, board, 0);

    const int16_t *acc_stm = (stm == 0) ? na->acc_stack_w[ptr] : na->acc_stack_b[ptr];
    const int16_t *acc_opp = (stm == 0) ? na->acc_stack_b[ptr] : na->acc_stack_w[ptr];

    uint8_t relu1[NN_L2_IN] __attribute__((aligned(32)));
    _screlu_perspective(acc_stm, L1B, relu1);
    _screlu_perspective(acc_opp, L1B, relu1 + NN_L1_OUT);

    int32_t acc2[NN_L2_OUT] __attribute__((aligned(32)));
#if defined(__AVX2__)
    const __m256i ones = _mm256_set1_epi16(1);
    for (int o = 0; o < NN_L2_OUT; o += 4) {
        const int8_t *row0 = L2W + (size_t)(o+0) * NN_L2_IN;
        const int8_t *row1 = L2W + (size_t)(o+1) * NN_L2_IN;
        const int8_t *row2 = L2W + (size_t)(o+2) * NN_L2_IN;
        const int8_t *row3 = L2W + (size_t)(o+3) * NN_L2_IN;
        __m256i sum0 = _mm256_setzero_si256();
        __m256i sum1 = _mm256_setzero_si256();
        __m256i sum2 = _mm256_setzero_si256();
        __m256i sum3 = _mm256_setzero_si256();
        for (int i = 0; i < NN_L2_IN; i += 32) {
            __m256i a  = _mm256_load_si256((const __m256i*)(relu1 + i));
            __m256i p0 = _mm256_maddubs_epi16(a, _mm256_load_si256((const __m256i*)(row0 + i)));
            __m256i p1 = _mm256_maddubs_epi16(a, _mm256_load_si256((const __m256i*)(row1 + i)));
            __m256i p2 = _mm256_maddubs_epi16(a, _mm256_load_si256((const __m256i*)(row2 + i)));
            __m256i p3 = _mm256_maddubs_epi16(a, _mm256_load_si256((const __m256i*)(row3 + i)));
            sum0 = _mm256_add_epi32(sum0, _mm256_madd_epi16(p0, ones));
            sum1 = _mm256_add_epi32(sum1, _mm256_madd_epi16(p1, ones));
            sum2 = _mm256_add_epi32(sum2, _mm256_madd_epi16(p2, ones));
            sum3 = _mm256_add_epi32(sum3, _mm256_madd_epi16(p3, ones));
        }
        acc2[o+0] = L2B[o+0] + _hsum_epi32(sum0);
        acc2[o+1] = L2B[o+1] + _hsum_epi32(sum1);
        acc2[o+2] = L2B[o+2] + _hsum_epi32(sum2);
        acc2[o+3] = L2B[o+3] + _hsum_epi32(sum3);
    }
#else
    for (int o = 0; o < NN_L2_OUT; o++) {
        int32_t sum = L2B[o];
        const int8_t *row = L2W + (size_t)o * NN_L2_IN;
        for (int i = 0; i < NN_L2_IN; i++) sum += (int32_t)relu1[i] * (int32_t)row[i];
        acc2[o] = sum;
    }
#endif

    int8_t relu2[NN_L2_OUT];
    for (int o = 0; o < NN_L2_OUT; o++) {
        int32_t v = acc2[o] / (NN_QA_EFF * NN_QB);
        if (v < 0) v = 0; else if (v > 127) v = 127;
        relu2[o] = (int8_t)v;
    }

    int32_t sum3 = 0;
    for (int i = 0; i < NN_L3_IN; i++) sum3 += (int32_t)relu2[i] * (int32_t)L3W[i];

    float raw3 = (float)sum3 + L3B * (float)(NN_QB * NN_QB);
    float p = 1.0f / (1.0f + expf(-raw3 * (1.0f / (float)(NN_QB * NN_QB))));
    float cp = -320.0f * logf((1.0f - p + 1e-7f) / (p + 1e-7f));

    if (cp > 32000.0f) cp = 32000.0f;
    if (cp < -32000.0f) cp = -32000.0f;
    return (int)lroundf(cp);
}

int nnue_eval(NnueAccum *na, int stm, const uint8_t *board) {
    if (!na) na = &g_nnue_accum;
    return _nnue_forward(na, stm, board);
}

int nnue_eval_bb(NnueAccum *na, int stm, const uint8_t *board,
                  const uint64_t bb[12], uint64_t board_hash) {
    (void)bb; (void)board_hash;
    return nnue_eval(na, stm, board);
}
