/* nnue.h — Zchezz v500 NNU4 evaluation API
 *
 * Compact HalfKP-4-Bucket network:
 *   features  2560 sparse indices per perspective
 *   L1        2560 -> 48, incremental int16 accumulator
 *   SCReLU    clamp to QA, square, shift by 8
 *   concat    [stm 48 | opp 48] = 96
 *   L2        96 -> 20, int8
 *   L3        20 -> 1
 *   format    NNU4, 248,020-byte installed file
 *
 * Feature coordinates are part of the binary/model contract. Zchezz mailbox
 * squares are 0=a8..63=h1. White POV uses zsq^56; Black POV uses zsq. A king
 * selects one of four buckets, relative non-king piece planes select 0..9,
 * and feature = bucket*640 + relative_piece*64 + pov_square.
 *
 * Both perspectives share L1 weights and concat order is always [stm, opp].
 * If a king crosses a bucket boundary, every feature for that perspective is
 * invalid; the stack records bucket/dirty state and the evaluator rebuilds that
 * perspective lazily from the post-move board.
 *
 * Mutable accumulator state is per search thread. NnueNet owns read-only weights
 * and allows native tools to keep independent networks in one process.
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

#define NN_KING_BUCKETS      4
#define NN_FEAT_PER_BUCKET 640
#define NN_FEAT_IN        2560
#define NN_L1_IN          2560
#define NN_L1_OUT           48
#define NN_L2_IN            96
#define NN_L2_OUT           20
#define NN_L3_IN            20
#define NN_L3_OUT            1

#define NN_QA      255
#define NN_QB       64
#define NN_SHIFT     8
#define NN_QA_EFF  254   /* (255*255)>>8 after SCReLU */

/* P=0 N=1 B=2 R=3 Q=4; kings select buckets and are not feature planes. */
#define NN_NOTYPES  6
#define NN_NOCOLORS 2

#define NN_ACC_STACK 128
#define NN_ACC_DEPTH NN_ACC_STACK

/* Per-thread accumulator. The two 128x48 int16 stacks dominate the structure
 * (~24 KiB combined); metadata stores lazy materialization and bucket state. */
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

/* `board` is the pre-move position; bucket changes are materialized lazily. */
void nnue_push_na(NnueAccum *na, const uint8_t *board, const NNMove *m);
void nnue_pop_na(NnueAccum *na);

/* Global compatibility hooks for WASM/tests. */
void nnue_push(const uint8_t *board, const NNMove *m);
void nnue_pop(void);
void nnue_reset(NnueAccum *na);

/* Returns STM-relative centipawns. bb/hash are retained in nnue_eval_bb for
 * source compatibility; the NNU4 evaluator does not require the old extras cache. */
int  nnue_eval(NnueAccum *na, int stm, const uint8_t *board);
int  nnue_eval_bb(NnueAccum *na, int stm, const uint8_t *board,
                  const uint64_t bb[12], uint64_t board_hash);

int nnue_load_from_mem(const uint8_t *data, size_t len);
void nnue_reset_global(void);

/* Feature helpers exposed to parity/tests. */
int nnue_feature_index(uint8_t p, int zsq, int white_pov, int bucket);
int nnue_king_bucket_w(int wk_zsq);
int nnue_king_bucket_b(int bk_zsq);
