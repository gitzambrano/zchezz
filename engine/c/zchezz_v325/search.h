/* search.h — Zchezz v3.25 search API
 *
 * Public search contract for the default engine profile. search_best() performs
 * iterative deepening and leaves the caller's Board logically unchanged because
 * every make is balanced by an unmake. Mutable ordering/search state is owned by
 * SearchState; Lazy-SMP helpers therefore use separate SearchState instances.
 *
 * The v3.25 TT is process-wide and dynamically sized. Three compact 10-byte
 * entries occupy each aligned 32-byte cluster. SearchParams carries time/node,
 * MultiPV, thread, stop and callback controls.
 */
#pragma once
#include "board.h"

/* Per-thread mutable search state; definition is private to search.c. */
typedef struct SearchState SearchState;

#define MAX_PLY     64
#define TT_EVAL_NONE 32001

/* TT entry bounds. */
#define TT_EXACT  0
#define TT_LOWER  1
#define TT_UPPER  2

/* Compact clustered TT owned by search.c. */
extern uint16_t TT_GEN;
int  tt_resize_mb(int mb);
void tt_clear(void);
int  tt_hashfull_permille(void);

#define MAX_MULTI_PV 6

typedef struct {
    Move    best;           /* best move found (PV 1) */
    int     score;          /* score in cp (PV 1), White-relative */
    int     depth;          /* actual depth searched */
    long    nodes;
    long    tb_hits;        /* tablebase probes that returned a result */
    char    pv[256];        /* PV string for line 1 (UCI notation) */
    int     num_pvs;        /* actual PVs returned (1..MAX_MULTI_PV) */
    int     scores[MAX_MULTI_PV];
    char    pvs[MAX_MULTI_PV][256];
    Move    bests[MAX_MULTI_PV];
} SearchResult;

/* Search limits and per-call dependencies. */
typedef struct {
    int  max_depth;         /* hard depth limit */
    int  start_depth;       /* 0 or 1 starts iterative deepening at depth 1 */
    int  time_limit_ms;     /* 0 = no time limit */
    long node_limit;        /* 0 = unlimited */
    int  multi_pv;          /* 1..MAX_MULTI_PV */
    int  threads;           /* 1 = single-threaded; >1 enables Lazy SMP */
    volatile int *stop;     /* optional shared external stop flag */
    SearchState *search_state;  /* NULL selects the default main-thread state */
    void (*info_cb)(int depth, int score, long nodes, const char *pv, int turn, int multipv);
} SearchParams;

/* Syzygy WDL probing controls populated by the UCI layer. */
extern int g_tb_probe_depth;
extern int g_tb_probe_limit;

/* One-time process initialization: LMR/MVV-LVA tables and TT setup. */
void search_init(void);

/* Per-search reset. History is aged rather than globally destroyed. */
void search_reset(SearchState *ss);

/* Fully clear learned move-ordering history, e.g. for ucinewgame. */
void search_history_clear(SearchState *s);

/* Main-thread/default state used when SearchParams.search_state is NULL. */
extern SearchState g_ss;

SearchState *search_state_new(void);
void search_state_free(SearchState *state);

/* Search a position without leaving Board modified. */
SearchResult search_best(Board *b, const SearchParams *p);

/* Static evaluation from the side-to-move search interface. */
int eval_stm(Board *b);

/* WebAssembly ABI wrapper for a structure return. */
void search_best_sret(SearchResult *out, Board *b, const SearchParams *p);

/* Apply a space-separated UCI move list after board_load_fen(). The helper
 * seeds repetition history so browser searches preserve threefold semantics. */
void board_apply_moves(Board *b, const char *moves_str);
