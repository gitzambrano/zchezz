/* search.h — Zchezz v500 search API
 *
 * The secondary profile owns its search/TT ABI. SearchParams carries an explicit
 * TTable pointer so native self-play/arena workers can isolate tables while UCI
 * Lazy-SMP helpers intentionally share the process-wide default table.
 */
#pragma once
#include <stddef.h>
#include "board.h"

typedef struct SearchState SearchState;

#define MAX_PLY     64
#ifdef __EMSCRIPTEN__
#define TT_SIZE     (1 << 19)
#else
#define TT_SIZE     (1 << 22)
#endif
#define TT_BUCKETS  2
#define TT_SLOTS    (TT_SIZE / TT_BUCKETS)
#define TT_MASK     (TT_SLOTS - 1)
#define TT_EVAL_NONE 32001

#define TT_EXACT  0
#define TT_LOWER  1
#define TT_UPPER  2

/* Packed 24-byte entries; two entries form the logical replacement bucket. */
typedef struct {
    uint64_t hash;
    int32_t  score;
    int32_t  move;
    int32_t  eval;
    uint16_t gen;
    int16_t  dflag;
} TTEntry;

typedef struct {
    TTEntry *e;
    uint16_t gen;
    size_t   size;
    size_t   slots;
} TTable;

TTable *tt_create(size_t n_entries);
void    tt_destroy(TTable *tt);
void    tt_clear(TTable *tt);
void    tt_new_generation(TTable *tt);
int     tt_resize_mb(TTable **tt, int mb);
extern TTable *g_tt;

#define MAX_MULTI_PV 6

typedef struct {
    Move    best;
    int     score;          /* White-relative */
    int     depth;
    long    nodes;
    long    tb_hits;
    char    pv[256];
    int     num_pvs;
    int     scores[MAX_MULTI_PV];
    char    pvs[MAX_MULTI_PV][256];
    Move    bests[MAX_MULTI_PV];
} SearchResult;

typedef struct {
    int  max_depth;
    int  start_depth;
    int  time_limit_ms;
    long node_limit;
    int  multi_pv;
    int  threads;
    volatile int *stop;
    SearchState *search_state;
    void (*info_cb)(int depth, int score, long nodes, const char *pv, int turn, int multipv);
    TTable *tt;             /* NULL uses g_tt */
    /* When nonzero, divide one MultiPV time budget across all returned lines.
     * UCI analysis leaves this zero; data-generation callers may enable it. */
    int  mpv_share_budget;
} SearchParams;

/* Thread-local pruning/reduction constants used by native tuning tools. */
typedef struct {
    int    razor_margin;
    int    rfp_mult;
    int    rfp_improving_bonus;
    int    nmp_base;
    int    nmp_depth_div;
    int    nmp_max_r;
    int    nmp_eval_bonus_threshold;
    int    probcut_margin;
    double lmr_divisor;
    int    fut_mult;
    int    fut_improving_adj;
    int    asp_delta_init;
    int    asp_delta_max;
} SearchTunables;

extern _Thread_local SearchTunables g_tune;
void search_tunables_apply(const SearchTunables *t);
SearchTunables search_tunables_defaults(void);

extern int g_tb_probe_depth;
extern int g_tb_probe_limit;

void search_init(void);
void search_reset(SearchState *ss);

/* Fully zero ordering state between independent generated games. */
void search_clear_ordering(SearchState *ss);
void search_history_clear(SearchState *s);

extern SearchState g_ss;
SearchState *search_state_new(void);
void search_state_free(SearchState *state);

SearchResult search_best(Board *b, const SearchParams *p);
int eval_stm(Board *b);

void search_best_sret(SearchResult *out, Board *b, const SearchParams *p);
void board_apply_moves(Board *b, const char *moves_str);
