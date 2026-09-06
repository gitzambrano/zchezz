#!/usr/bin/env python3
"""Apply a compact pawn-structure correction-history experiment to v3.23.

The NNUE output remains untouched.  A small per-thread table learns the
systematic residual (search score - raw static eval) for recurring pawn
structures and adjusts only the static eval consumed by forward-pruning.
TT stores keep the uncorrected raw evaluation.
"""
from pathlib import Path

p=Path('engine/c/zchezz_v323/search.c')
s=p.read_text(encoding='utf-8')

def one(old,new,label):
    global s
    n=s.count(old)
    if n!=1:
        raise SystemExit(f'{label}: expected one anchor, found {n}')
    s=s.replace(old,new,1)

one(
'''#define LMR_M 128
static uint8_t lmr_tab[LMR_D * LMR_M];
''',
'''#define LMR_M 128
static uint8_t lmr_tab[LMR_D * LMR_M];

/* v3.24 experiment: compact pawn-structure correction history. */
#define PAWN_CORR_SIZE 8192
#define PAWN_CORR_MAX  256

static inline unsigned pawn_corr_index(const Board *b) {
    uint64_t x = b->bb[0] * 0x9E3779B185EBCA87ULL;
    uint64_t q = b->bb[6];
    x ^= (q << 23) | (q >> 41);
    x ^= x >> 33;
    x *= 0xC2B2AE3D27D4EB4FULL;
    x ^= x >> 29;
    return (unsigned)x & (PAWN_CORR_SIZE - 1);
}
''','helper')

one(
'''    int16_t cont_hist[2][64][64*64];
    int prev_ft[MAX_PLY];
''',
'''    int16_t cont_hist[2][64][64*64];
    int16_t pawn_corr[2][PAWN_CORR_SIZE];
    int prev_ft[MAX_PLY];
''','state')

one(
'''    int static_eval = TT_EVAL_NONE;
    int raw_eval = TT_EVAL_NONE;  /* uncorrected eval for improving flag */
    if (!in_check) {
        raw_eval = (tte_hit && tte.static_eval != TT_EVAL_NONE)
                    ? tte.static_eval : eval_stm(b);
        static_eval = raw_eval;
''',
'''    int static_eval = TT_EVAL_NONE;
    int raw_eval = TT_EVAL_NONE;  /* NNUE/TT eval before correction history */
    int corr_idx = -1;
    if (!in_check) {
        raw_eval = (tte_hit && tte.static_eval != TT_EVAL_NONE)
                    ? tte.static_eval : eval_stm(b);
        corr_idx = (int)pawn_corr_index(b);
        int corr_side = b->turn == COL_W ? 0 : 1;
        static_eval = raw_eval + ss->pawn_corr[corr_side][corr_idx];
        if (static_eval > 18000) static_eval = 18000;
        if (static_eval < -18000) static_eval = -18000;
''','static eval correction')

one(
'''    /* No legal moves: checkmate (in check) or stalemate (not in check) */
    if (!legal_count) return in_check ? (-19000+ply) : 0;
    /* v3.20: do not poison a persistent TT with aborted-search bounds.
''',
'''    /* No legal moves: checkmate (in check) or stalemate (not in check) */
    if (!legal_count) return in_check ? (-19000+ply) : 0;

    /* Learn a conservative residual only from quiet resolved nodes.  Bound
     * direction must agree with the raw eval so fail-high/fail-low bounds do
     * not teach the table in the wrong direction.  The table stores centipawn
     * corrections directly and converges by a depth-weighted EWMA. */
    if (!in_check && !ss->time_up && corr_idx >= 0 && raw_eval != TT_EVAL_NONE &&
        best > -18000 && best < 18000 && (best_move.from || best_move.to)) {
        int bcapture = !!(b->b[best_move.to] || best_move.epc);
        int bquiet = !bcapture && !best_move.prom && !best_move.castle;
        int bound_ok = (flag == TT_EXACT) ||
                       (flag == TT_LOWER && best >= raw_eval) ||
                       (flag == TT_UPPER && best <= raw_eval);
        if (bquiet && bound_ok) {
            int target = best - raw_eval;
            if (target > PAWN_CORR_MAX) target = PAWN_CORR_MAX;
            if (target < -PAWN_CORR_MAX) target = -PAWN_CORR_MAX;
            int side = b->turn == COL_W ? 0 : 1;
            int oldc = ss->pawn_corr[side][corr_idx];
            int weight = depth * 8;
            if (weight < 8) weight = 8;
            if (weight > 64) weight = 64;
            int nc = oldc + ((target - oldc) * weight) / 64;
            if (nc > PAWN_CORR_MAX) nc = PAWN_CORR_MAX;
            if (nc < -PAWN_CORR_MAX) nc = -PAWN_CORR_MAX;
            ss->pawn_corr[side][corr_idx] = (int16_t)nc;
        }
    }

    /* v3.20: do not poison a persistent TT with aborted-search bounds.
''','correction update')

one(
'''void search_history_clear(SearchState *s) {
    memset(s->mv_history,   0, sizeof(s->mv_history));
    memset(s->counter_move, 0, sizeof(s->counter_move));
    memset(s->cont_hist,    0, sizeof(s->cont_hist));
}
''',
'''void search_history_clear(SearchState *s) {
    memset(s->mv_history,   0, sizeof(s->mv_history));
    memset(s->counter_move, 0, sizeof(s->counter_move));
    memset(s->cont_hist,    0, sizeof(s->cont_hist));
    memset(s->pawn_corr,    0, sizeof(s->pawn_corr));
}
''','history clear')

p.write_text(s,encoding='utf-8')
print('v3.24 pawn correction history patch applied')
