#include "small_nnue.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <immintrin.h>

#define S_NN_KING_BUCKETS      4
#define S_NN_FEAT_PER_BUCKET 640
#define S_NN_FEAT_IN        2560
#define S_NN_L1_IN          2560
#define S_NN_L1_OUT           48
#define S_NN_L2_IN            96
#define S_NN_L2_OUT           20
#define S_NN_L3_IN            20
#define S_NN_L3_OUT            1
#define S_NN_QA              255
#define S_NN_QB               64
#define S_NN_SHIFT             8

#define S_PC_COLOR(p)  ((p) & 24)
#define S_PC_TYPE(p)   ((p) &  7)
#define S_COL_W  8
#define S_COL_B 16
#define S_PT_KING 6

typedef struct {
    int16_t *L1WT;
    int32_t *L1B;
    int8_t  *L2W;
    int32_t *L2B;
    int8_t  *L3W;
    float    L3B;
    float    OutScale;
    int      ready;
} SmallNet;

static SmallNet g_small_net = {0};

static void *zmalloc32(size_t bytes) {
#if defined(_WIN32)
    return _aligned_malloc(bytes, 32);
#else
    void *p = NULL;
    if (posix_memalign(&p, 32, bytes) != 0) p = NULL;
    return p;
#endif
}

static void zfree32(void *ptr) {
#if defined(_WIN32)
    _aligned_free(ptr);
#else
    free(ptr);
#endif
}

int small_nnue_ready(void) {
    return g_small_net.ready;
}

void small_nnue_destroy(void) {
    if (g_small_net.L1WT) zfree32(g_small_net.L1WT);
    if (g_small_net.L1B)  zfree32(g_small_net.L1B);
    if (g_small_net.L2W)  zfree32(g_small_net.L2W);
    if (g_small_net.L2B)  zfree32(g_small_net.L2B);
    if (g_small_net.L3W)  zfree32(g_small_net.L3W);
    memset(&g_small_net, 0, sizeof(g_small_net));
}

int small_nnue_load(const char *path) {
    small_nnue_destroy();
    FILE *f = fopen(path, "rb");
    if (!f) {
        fprintf(stderr, "[SmallNNUE] Cannot open: %s\n", path);
        return -1;
    }
    fseek(f, 0, SEEK_END);
    long fsize = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (fsize < 248000) {
        fclose(f);
        return -1;
    }

    uint8_t *buf = (uint8_t *)malloc((size_t)fsize);
    if (!buf) { fclose(f); return -1; }
    if ((long)fread(buf, 1, (size_t)fsize, f) != fsize) {
        free(buf); fclose(f); return -1;
    }
    fclose(f);

    if (buf[0]!='N' || buf[1]!='N' || buf[2]!='U' || buf[3]!='4') {
        fprintf(stderr, "[SmallNNUE] Bad magic (expected NNU4)\n");
        free(buf); return -1;
    }

    size_t off = 8; /* magic + epoch */
    uint32_t dims[5];
    memcpy(dims, buf + off, 5 * sizeof(uint32_t));
    off += 5 * 4;

    float scales[4];
    memcpy(scales, buf + off, 4 * sizeof(float));
    off += 16;
    g_small_net.OutScale = scales[3];

    const size_t L1_SZ = (size_t)S_NN_L1_IN * S_NN_L1_OUT;
    const size_t L2_SZ = (size_t)S_NN_L2_OUT * S_NN_L2_IN;

    g_small_net.L1WT = (int16_t *)zmalloc32(L1_SZ * sizeof(int16_t));
    g_small_net.L1B  = (int32_t *)zmalloc32(S_NN_L1_OUT * sizeof(int32_t));
    g_small_net.L2W  = (int8_t  *)zmalloc32(L2_SZ * sizeof(int8_t));
    g_small_net.L2B  = (int32_t *)zmalloc32(S_NN_L2_OUT * sizeof(int32_t));
    g_small_net.L3W  = (int8_t  *)zmalloc32(S_NN_L3_IN * sizeof(int8_t));

    memcpy(g_small_net.L1WT, buf + off, L1_SZ * 2); off += L1_SZ * 2;
    memcpy(g_small_net.L1B,  buf + off, S_NN_L1_OUT * 4); off += S_NN_L1_OUT * 4;
    memcpy(g_small_net.L2W,  buf + off, L2_SZ); off += L2_SZ;
    memcpy(g_small_net.L2B,  buf + off, S_NN_L2_OUT * 4); off += S_NN_L2_OUT * 4;
    memcpy(g_small_net.L3W,  buf + off, S_NN_L3_IN); off += S_NN_L3_IN;
    memcpy(&g_small_net.L3B, buf + off, sizeof(float));

    free(buf);
    g_small_net.ready = 1;
    fprintf(stderr, "[SmallNNUE] Loaded NNU4 (%s): 2560->48->20->1 (OutScale=%g)\n",
            path, g_small_net.OutScale);
    return 0;
}

static inline int _s_king_bucket(int s) {
    return ((s & 7) >= 4 ? 1 : 0) | ((s >> 3) >= 4 ? 2 : 0);
}

static inline int _s_piece_rel(uint8_t p, int white_pov) {
    int t = S_PC_TYPE(p) - 1;
    if (t < 0 || t >= 5) return -1;
    int is_white = (S_PC_COLOR(p) == S_COL_W);
    return (is_white == white_pov ? 0 : 5) + t;
}

int small_nnue_evaluate(const uint8_t *board, int stm, int wk_sq, int bk_sq, uint64_t occ) {
    if (!g_small_net.ready) return 0;

    int bkt_w = _s_king_bucket(wk_sq ^ 56);
    int bkt_b = _s_king_bucket(bk_sq);

    int16_t accW[S_NN_L1_OUT] __attribute__((aligned(32)));
    int16_t accB[S_NN_L1_OUT] __attribute__((aligned(32)));
    memset(accW, 0, sizeof(accW));
    memset(accB, 0, sizeof(accB));

    const int16_t *L1WT = g_small_net.L1WT;

    /* Iterate pieces */
    uint64_t pieces = occ & ~(((uint64_t)1 << wk_sq) | ((uint64_t)1 << bk_sq));
    while (pieces) {
        int zsq = __builtin_ctzll(pieces);
        pieces &= pieces - 1;
        uint8_t p = board[zsq];
        int relW = _s_piece_rel(p, 1);
        if (relW < 0) continue;
        int relB = relW < 5 ? relW + 5 : relW - 5;

        const int16_t *wRow = L1WT + (size_t)(bkt_w * S_NN_FEAT_PER_BUCKET + relW * 64 + (zsq ^ 56)) * S_NN_L1_OUT;
        const int16_t *bRow = L1WT + (size_t)(bkt_b * S_NN_FEAT_PER_BUCKET + relB * 64 +  zsq       ) * S_NN_L1_OUT;

        for (int o = 0; o < S_NN_L1_OUT; o += 16) {
            __m256i aw = _mm256_load_si256((const __m256i*)(accW + o));
            aw = _mm256_add_epi16(aw, _mm256_load_si256((const __m256i*)(wRow + o)));
            _mm256_store_si256((__m256i*)(accW + o), aw);

            __m256i ab = _mm256_load_si256((const __m256i*)(accB + o));
            ab = _mm256_add_epi16(ab, _mm256_load_si256((const __m256i*)(bRow + o)));
            _mm256_store_si256((__m256i*)(accB + o), ab);
        }
    }

    /* SCReLU activation */
    const __m256i zero = _mm256_setzero_si256();
    const __m256i v255 = _mm256_set1_epi32(255);
    const int32_t *L1B = g_small_net.L1B;

    uint8_t reluW[S_NN_L1_OUT], reluB[S_NN_L1_OUT];
    for (int o = 0; o < S_NN_L1_OUT; o += 16) {
        /* White */
        __m128i a_lo = _mm_load_si128((const __m128i*)(accW + o));
        __m128i a_hi = _mm_load_si128((const __m128i*)(accW + o + 8));
        __m256i s_lo = _mm256_add_epi32(_mm256_cvtepi16_epi32(a_lo), _mm256_load_si256((const __m256i*)(L1B + o)));
        __m256i s_hi = _mm256_add_epi32(_mm256_cvtepi16_epi32(a_hi), _mm256_load_si256((const __m256i*)(L1B + o + 8)));
        s_lo = _mm256_min_epi32(_mm256_max_epi32(s_lo, zero), v255);
        s_hi = _mm256_min_epi32(_mm256_max_epi32(s_hi, zero), v255);
        s_lo = _mm256_srli_epi32(_mm256_mullo_epi32(s_lo, s_lo), 8);
        s_hi = _mm256_srli_epi32(_mm256_mullo_epi32(s_hi, s_hi), 8);
        __m256i p16 = _mm256_packs_epi32(s_lo, s_hi);
        p16 = _mm256_permute4x64_epi64(p16, _MM_SHUFFLE(3, 1, 2, 0));
        __m128i p8 = _mm_packus_epi16(_mm256_castsi256_si128(p16), _mm256_extracti128_si256(p16, 1));
        _mm_storeu_si128((__m128i*)(reluW + o), p8);

        /* Black */
        a_lo = _mm_load_si128((const __m128i*)(accB + o));
        a_hi = _mm_load_si128((const __m128i*)(accB + o + 8));
        s_lo = _mm256_add_epi32(_mm256_cvtepi16_epi32(a_lo), _mm256_load_si256((const __m256i*)(L1B + o)));
        s_hi = _mm256_add_epi32(_mm256_cvtepi16_epi32(a_hi), _mm256_load_si256((const __m256i*)(L1B + o + 8)));
        s_lo = _mm256_min_epi32(_mm256_max_epi32(s_lo, zero), v255);
        s_hi = _mm256_min_epi32(_mm256_max_epi32(s_hi, zero), v255);
        s_lo = _mm256_srli_epi32(_mm256_mullo_epi32(s_lo, s_lo), 8);
        s_hi = _mm256_srli_epi32(_mm256_mullo_epi32(s_hi, s_hi), 8);
        p16 = _mm256_packs_epi32(s_lo, s_hi);
        p16 = _mm256_permute4x64_epi64(p16, _MM_SHUFFLE(3, 1, 2, 0));
        p8 = _mm_packus_epi16(_mm256_castsi256_si128(p16), _mm256_extracti128_si256(p16, 1));
        _mm_storeu_si128((__m128i*)(reluB + o), p8);
    }

    uint8_t relu1[S_NN_L2_IN] __attribute__((aligned(32)));
    if (stm == 0) {
        memcpy(relu1, reluW, S_NN_L1_OUT);
        memcpy(relu1 + S_NN_L1_OUT, reluB, S_NN_L1_OUT);
    } else {
        memcpy(relu1, reluB, S_NN_L1_OUT);
        memcpy(relu1 + S_NN_L1_OUT, reluW, S_NN_L1_OUT);
    }

    /* L2 Forward Pass */
    const int8_t  *L2W = g_small_net.L2W;
    const int32_t *L2B = g_small_net.L2B;
    int32_t acc2[S_NN_L2_OUT];

    const __m256i r0 = _mm256_load_si256((const __m256i*)(relu1 +  0));
    const __m256i r1 = _mm256_load_si256((const __m256i*)(relu1 + 32));
    const __m256i r2 = _mm256_load_si256((const __m256i*)(relu1 + 64));
    const __m256i ones = _mm256_set1_epi16(1);

    for (int o = 0; o < S_NN_L2_OUT; o += 4) {
        const int8_t *w0 = L2W + (size_t)(o + 0) * S_NN_L2_IN;
        const int8_t *w1 = L2W + (size_t)(o + 1) * S_NN_L2_IN;
        const int8_t *w2 = L2W + (size_t)(o + 2) * S_NN_L2_IN;
        const int8_t *w3 = L2W + (size_t)(o + 3) * S_NN_L2_IN;

        __m256i p0_0 = _mm256_maddubs_epi16(r0, _mm256_loadu_si256((const __m256i*)(w0 +  0)));
        __m256i p0_1 = _mm256_maddubs_epi16(r1, _mm256_loadu_si256((const __m256i*)(w0 + 32)));
        __m256i p0_2 = _mm256_maddubs_epi16(r2, _mm256_loadu_si256((const __m256i*)(w0 + 64)));
        __m256i d0 = _mm256_add_epi32(_mm256_madd_epi16(p0_0, ones),
                     _mm256_add_epi32(_mm256_madd_epi16(p0_1, ones), _mm256_madd_epi16(p0_2, ones)));

        __m256i p1_0 = _mm256_maddubs_epi16(r0, _mm256_loadu_si256((const __m256i*)(w1 +  0)));
        __m256i p1_1 = _mm256_maddubs_epi16(r1, _mm256_loadu_si256((const __m256i*)(w1 + 32)));
        __m256i p1_2 = _mm256_maddubs_epi16(r2, _mm256_loadu_si256((const __m256i*)(w1 + 64)));
        __m256i d1 = _mm256_add_epi32(_mm256_madd_epi16(p1_0, ones),
                     _mm256_add_epi32(_mm256_madd_epi16(p1_1, ones), _mm256_madd_epi16(p1_2, ones)));

        __m256i p2_0 = _mm256_maddubs_epi16(r0, _mm256_loadu_si256((const __m256i*)(w2 +  0)));
        __m256i p2_1 = _mm256_maddubs_epi16(r1, _mm256_loadu_si256((const __m256i*)(w2 + 32)));
        __m256i p2_2 = _mm256_maddubs_epi16(r2, _mm256_loadu_si256((const __m256i*)(w2 + 64)));
        __m256i d2 = _mm256_add_epi32(_mm256_madd_epi16(p2_0, ones),
                     _mm256_add_epi32(_mm256_madd_epi16(p2_1, ones), _mm256_madd_epi16(p2_2, ones)));

        __m256i p3_0 = _mm256_maddubs_epi16(r0, _mm256_loadu_si256((const __m256i*)(w3 +  0)));
        __m256i p3_1 = _mm256_maddubs_epi16(r1, _mm256_loadu_si256((const __m256i*)(w3 + 32)));
        __m256i p3_2 = _mm256_maddubs_epi16(r2, _mm256_loadu_si256((const __m256i*)(w3 + 64)));
        __m256i d3 = _mm256_add_epi32(_mm256_madd_epi16(p3_0, ones),
                     _mm256_add_epi32(_mm256_madd_epi16(p3_1, ones), _mm256_madd_epi16(p3_2, ones)));

        __m128i h0 = _mm_add_epi32(_mm256_castsi256_si128(d0), _mm256_extracti128_si256(d0, 1));
        __m128i h1 = _mm_add_epi32(_mm256_castsi256_si128(d1), _mm256_extracti128_si256(d1, 1));
        __m128i h2 = _mm_add_epi32(_mm256_castsi256_si128(d2), _mm256_extracti128_si256(d2, 1));
        __m128i h3 = _mm_add_epi32(_mm256_castsi256_si128(d3), _mm256_extracti128_si256(d3, 1));

        __m128i s01 = _mm_hadd_epi32(h0, h1);
        __m128i s23 = _mm_hadd_epi32(h2, h3);
        __m128i s0123 = _mm_hadd_epi32(s01, s23);

        __m128i sum4 = _mm_add_epi32(_mm_loadu_si128((const __m128i*)(L2B + o)), s0123);
        _mm_storeu_si128((__m128i*)(acc2 + o), sum4);
    }

    uint8_t relu2[S_NN_L2_OUT];
    for (int o = 0; o < S_NN_L2_OUT; o++) {
        int32_t v = acc2[o] >> S_NN_SHIFT;
        relu2[o] = (uint8_t)(v < 0 ? 0 : v > S_NN_QB ? S_NN_QB : v);
    }

    /* L3 */
    const int8_t *L3W = g_small_net.L3W;
    int32_t l3_sum = 0;
    for (int i = 0; i < S_NN_L3_IN; i++) l3_sum += (int32_t)L3W[i] * relu2[i];

    float cp = (float)l3_sum * g_small_net.OutScale + g_small_net.L3B * 320.0f;
    if (cp < -2000.f) cp = -2000.f;
    if (cp >  2000.f) cp =  2000.f;
    return (int)(cp + (cp >= 0.f ? 0.5f : -0.5f));
}
