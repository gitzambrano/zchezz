/* nnue.h — Zchezz v600 NNU5 evaluation API
 *
 * HalfKAv2_hm-32Bucket network:
 *   features  22528 sparse indices per perspective
 *   L1        22528 -> 64, incremental int16 accumulator
 *   SCReLU    clamp to QA, square, shift by 8
 *   concat    [stm 64 | opp 64] = 128
 *   L2        128 -> 16, int8
 *   L3        16 -> 1
 *   format    NNU5, 2,886,016-byte installed file
 *
 * Feature coordinates:
 *   White POV: sq_w = zsq ^ 56 (0=a1..63=h8).
 *   Black POV: sq_b = zsq      (rank flipped).
 *   King bucket: 4 files (horizontal mirror e-h to d-a) x 8 ranks = 32 buckets.
 *   Relative pieces (11 types):
 *     Ally P,N,B,R,Q -> 0..4; Enemy P,N,B,R,Q -> 5..9; Enemy King -> 10.
 *     Ally King selects bucket and is not a feature plane.
 *   feature = bucket * 704 + rel_piece * 64 + pov_sq (with HM if king mirrored).
 */
#pragma once
#include <stdint.h>
#include <stddef.h>

typedef struct NnueNet NnueNet;

/* Per-instance network lifecycle for native self-play/A-B tools. */
NnueNet *nnue_net_create(void);
NnueNet *nnue_net_load(const char *path);
NnueNet *nnue_net_load_from_mem(const uint8_t *data, size_t len);
void nnue_net_destroy(NnueNet *net);
int  nnue_net_ready(const NnueNet *net);

/* Process-wide default network used by the UCI/WASM compatibility API. */
extern NnueNet *g_nnue_net;

#define NN_KING_BUCKETS      32
#define NN_FEAT_PER_BUCKET  704
#define NN_FEAT_IN        22528
#define NN_L1_IN          22528
#define NN_L1_OUT            64
#define NN_L2_IN            128
#define NN_L2_OUT            16
#define NN_L3_IN             16
#define NN_L3_OUT             1

#define NN_QA      255
#define NN_QB       64
#define NN_SHIFT     8
#define NN_QA_EFF  254   /* (255*255)>>8 after SCReLU */

#define NN_NOTYPES  6
#define NN_NOCOLORS 2

#define NN_ACC_STACK 128
#define NN_ACC_DEPTH NN_ACC_STACK

/* Per-thread accumulator. */
typedef struct {
    int16_t  acc_stack_w[NN_ACC_STACK][NN_L1_OUT] __attribute__((aligned(32)));
    int16_t  acc_stack_b[NN_ACC_STACK][NN_L1_OUT] __attribute__((aligned(32)));
    int      acc_ptr;
    uint8_t  acc_valid_w[NN_ACC_STACK];
    uint8_t  acc_valid_b[NN_ACC_STACK];
    uint8_t  delta_n[NN_ACC_STACK];
    uint8_t  delta_piece[NN_ACC_STACK][4];
    uint8_t  delta_sq[NN_ACC_STACK][4];
    int8_t   delta_sign[NN_ACC_STACK][4];
    int16_t  acc_w[NN_L1_OUT]                     __attribute__((aligned(32)));
    int16_t  acc_b[NN_L1_OUT]                     __attribute__((aligned(32)));
    uint8_t  bucket_w_stack[NN_ACC_STACK];
    uint8_t  bucket_b_stack[NN_ACC_STACK];
    uint8_t  hm_w_stack[NN_ACC_STACK];
    uint8_t  hm_b_stack[NN_ACC_STACK];
    uint8_t  dirty_w_stack[NN_ACC_STACK];
    uint8_t  dirty_b_stack[NN_ACC_STACK];
    int      acc_dirty;
    const NnueNet *net;
} NnueAccum;

/* Default-network compatibility API used by the UCI engine. */
int  nnue_load(const char *path);
int  nnue_ready(void);
void nnue_rebuild(NnueAccum *na, const uint8_t *board);

typedef struct {
    uint8_t from_sq;
    uint8_t to_sq;
    uint8_t prom;
    uint8_t is_epc;
    uint8_t castle;
    uint8_t wk_sq;      /* white king mailbox square before the move */
    uint8_t bk_sq;      /* black king mailbox square before the move */
} NNMove;

void nnue_push_na(NnueAccum *na, const uint8_t *board, const NNMove *m);
void nnue_pop_na(NnueAccum *na);

void nnue_push(const uint8_t *board, const NNMove *m);
void nnue_pop(void);
void nnue_reset(NnueAccum *na);

int  nnue_eval(NnueAccum *na, int stm, const uint8_t *board);
int  nnue_eval_bb(NnueAccum *na, int stm, const uint8_t *board,
                  const uint64_t bb[12], uint64_t board_hash);

int nnue_load_from_mem(const uint8_t *data, size_t len);
void nnue_reset_global(void);

int nnue_feature_index(uint8_t p, int zsq, int white_pov, int bucket, int hm);
int nnue_king_bucket_w(int wk_zsq, int *hm);
int nnue_king_bucket_b(int bk_zsq, int *hm);
