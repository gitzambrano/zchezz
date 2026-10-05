/* nnue.h — Zchezz v3.25 NNU3 evaluation API
 *
 * Installed-file contract:
 *   input      799 = 768 half-mirror piece features + 31 endgame features
 *   L1         799 -> 256
 *   H2 on disk 256 -> 64
 *   output     64 -> 1
 *   format     NNU3, int16/int8 quantized
 *
 * Runtime contract:
 *   the tracked network has 50 H2 neurons with non-zero quantized L3 weights.
 *   The loader copies those 50 live rows into 52 SIMD slots (two zero padding
 *   rows). This is exact dead-neuron elimination; the NNU3 file stays 64-wide.
 *
 * Threading:
 *   every search thread owns an NnueAccum. Weight arrays are loaded once and
 *   then read-only. The 768 half-mirror contribution is maintained on a
 *   per-thread accumulator stack; the 31 extra features use cached projections.
 *   PK17 passed-pawn/king-distance state is maintained incrementally as part of
 *   the current v3.25 accumulator.
 */
#pragma once
#include <stdint.h>
#include <stddef.h>

/* File/input and compact runtime layer dimensions. */
#define NN_L1_IN   799   /* 768 half-mirror + 31 endgame features */
#define NN_L1_OUT  256
#define NN_L2_IN   256
#define NN_L2_OUT   52   /* runtime: 50 live H2 + 2 zero SIMD padding */
#define NN_L3_IN    52
#define NN_L3_OUT    1

#define NN_HM_IN   768
#define NN_EXTRA    31

/* Quantization constants shared with the NNU3 exporter/runtime. */
#define NN_QA      255
#define NN_QB      64
#define NN_SHIFT   8

/* Piece-type indexing used by feature code: P,N,B,R,Q,K -> 0..5. */
#define NN_NOTYPES  6
#define NN_NOCOLORS 2

/* Per-thread accumulator stack must exceed search MAX_PLY (64). */
#define NN_ACC_STACK 128

/* Legacy global stack used only by compatibility/test entry points. */
#define NN_ACC_DEPTH 512

/* Direct-mapped cache for projected endgame-feature contributions. */
#define EXT_CACHE_SLOTS 16

/* Incremental PK17 state used by the v3.25 endgame feature path. */
typedef struct {
    uint64_t pawns_w, pawns_b;
    uint8_t  king_w, king_b;
    uint8_t  passed_w, passed_b, king_dist;
} NnuePk17State;

/* Mutable NNUE state owned by one search thread / Board binding. */
typedef struct {
    int16_t  acc_stack_w[NN_ACC_STACK][NN_L1_OUT] __attribute__((aligned(32)));
    int16_t  acc_stack_b[NN_ACC_STACK][NN_L1_OUT] __attribute__((aligned(32)));
    int      acc_ptr;
    int16_t  acc_w[NN_L1_OUT]                __attribute__((aligned(32)));
    int16_t  acc_b[NN_L1_OUT]                __attribute__((aligned(32)));
    int16_t  ext_buf[2][NN_L1_OUT]           __attribute__((aligned(32)));
    float    ext_feat[2][NN_EXTRA];
    int8_t   ext_dirty[2];

    NnuePk17State pk17_state;
    NnuePk17State pk17_undo[NN_ACC_STACK];
    uint8_t  pk17_changed[NN_ACC_STACK];
    int16_t  pk17_acc_w[NN_L1_OUT] __attribute__((aligned(32)));
    int16_t  pk17_acc_b[NN_L1_OUT] __attribute__((aligned(32)));

    int      acc_dirty;
    uint64_t cache_key[EXT_CACHE_SLOTS];
    uint32_t cache_aux[EXT_CACHE_SLOTS];
    int16_t  cache_buf[EXT_CACHE_SLOTS][NN_L1_OUT] __attribute__((aligned(32)));
} NnueAccum;

/* Load the process-wide NNU3 weights. Call before launching search threads. */
int  nnue_load(const char *path);
int  nnue_ready(void);

/* Rebuild the thread accumulator from the current board position. */
void nnue_rebuild(NnueAccum *na, const uint8_t *board);

/* Move metadata consumed by the incremental accumulator update. */
typedef struct {
    uint8_t from_sq;
    uint8_t to_sq;
    uint8_t prom;       /* 0 = not a promotion */
    uint8_t is_epc;     /* en-passant capture */
    uint8_t castle;     /* 0|1|2|3|4 */
} NNMove;

/* Native search make/unmake hooks; each thread passes its own NnueAccum. */
void nnue_push_na(NnueAccum *na, const uint8_t *board, const NNMove *m);
void nnue_pop_na(NnueAccum *na);

/* Legacy global compatibility hooks used by WASM/tests, not native search. */
void nnue_push(const uint8_t *board, const NNMove *m);
void nnue_pop(void);

/* Mark the supplied accumulator dirty and reset its caches/stack state. */
void nnue_reset(NnueAccum *na);

/* Forward passes return White-relative centipawns, clamped by the runtime. */
int  nnue_eval(NnueAccum *na, int stm, const uint8_t *board);
int  nnue_eval_bb(NnueAccum *na, int stm, const uint8_t *board,
                  const uint64_t bb[12], uint64_t board_hash);

/* In-memory NNU3 load used by the browser bundle. */
int nnue_load_from_mem(const uint8_t *data, size_t len);

/* Single-threaded/WASM compatibility reset for the global accumulator. */
void nnue_reset_global(void);
