/* Differential/invariant stress test for the v3.23 PK17 split accumulator.
 * Compile only against a generated PK17 candidate with -DPK17_VERIFY.
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "board.h"
#include "nnue.h"

static uint64_t g_rng = 0x32317d15ULL;
static long long g_checks = 0;
static long long g_makes = 0;

static uint32_t rnd32(void) {
    g_rng ^= g_rng << 13;
    g_rng ^= g_rng >> 7;
    g_rng ^= g_rng << 17;
    return (uint32_t)(g_rng >> 16);
}

static void fail_pos(const Board *b, const char *where, const char *why,
                     int a, int c) {
    char fen[256];
    board_to_fen(b, fen);
    fprintf(stderr, "PK17 FAIL [%s]: %s (%d vs %d)\nFEN: %s\n",
            where, why, a, c, fen);
    exit(2);
}

static void verify(Board *b, const char *where) {
    int rc = nnue_pk17_verify(b->nnue, b->b);
    if (rc) fail_pos(b, where, "incremental state/projection mismatch", rc, 0);

    /* nnue_eval() is the untouched monolithic 31-feature reference path.
     * nnue_eval_bb() is the PK17 split search path.  Compare both perspectives,
     * not just the actual side to move. */
    int ref_w = nnue_eval(b->nnue, 0, b->b);
    int got_w = nnue_eval_bb(b->nnue, 0, b->b, b->bb, b->hash);
    if (ref_w != got_w) fail_pos(b, where, "white-perspective eval mismatch", ref_w, got_w);
    int ref_b = nnue_eval(b->nnue, 1, b->b);
    int got_b = nnue_eval_bb(b->nnue, 1, b->b, b->bb, b->hash);
    if (ref_b != got_b) fail_pos(b, where, "black-perspective eval mismatch", ref_b, got_b);
    g_checks++;
}

static void fresh(Board *b, NnueAccum *na, UndoFrame *undo, int *top,
                  const char *fen) {
    memset(na, 0, sizeof(*na));
    memset(undo, 0, STACK_SIZE * sizeof(*undo));
    *top = 0;
    if (board_load_fen(b, fen) != 0) {
        fprintf(stderr, "bad FEN: %s\n", fen);
        exit(2);
    }
    b->nnue = na;
    b->undo = undo;
    b->undo_top = top;
    nnue_reset(na);
    nnue_rebuild(na, b->b);
    verify(b, "fresh");
}

static void make_checked(Board *b, const Move *m, const char *where) {
    board_make(b, m);
    g_makes++;
    verify(b, where);
}

static int mover_legal_after_make(const Board *b) {
    int mover = b->turn ^ 24;
    if (!b->bb[5] || !b->bb[11]) return 0; /* never continue after king capture */
    int ksq = mover == COL_W ? b->wk : b->bk;
    return !board_is_attacked(b, ksq, b->turn);
}

static void play_sequence(const char *fen, const char *const *moves, int n,
                          const char *name) {
    Board b; NnueAccum na; UndoFrame undo[STACK_SIZE]; int top = 0;
    fresh(&b, &na, undo, &top, fen);
    for (int i = 0; i < n; i++) {
        Move m;
        if (!move_from_uci(&b, moves[i], &m)) {
            fprintf(stderr, "sequence %s: move not generated: %s\n", name, moves[i]);
            exit(2);
        }
        make_checked(&b, &m, name);
    }
    while (top > 0) {
        board_unmake(&b);
        verify(&b, name);
    }
}

/* At each ply, probe several pseudo-legal moves.  We verify immediately after
 * every make, including positions later rejected for leaving the mover in
 * check.  Then we undo and verify the exact parent again.  One legal move is
 * selected for deeper recursion.  This stresses both transition directions
 * much harder than ordinary legal-game sampling. */
static void random_branch(Board *b, int depth, int probes) {
    if (depth <= 0) return;
    Move mv[MAX_MOVES];
    int n = board_gen_moves(b, mv);
    if (n <= 0) return;

    int order[MAX_MOVES];
    for (int i = 0; i < n; i++) order[i] = i;
    for (int i = n - 1; i > 0; i--) {
        int j = (int)(rnd32() % (uint32_t)(i + 1));
        int t = order[i]; order[i] = order[j]; order[j] = t;
    }

    int chosen = -1;
    int lim = probes < n ? probes : n;
    for (int k = 0; k < lim; k++) {
        int idx = order[k];
        make_checked(b, &mv[idx], "random-probe-child");
        int legal = mover_legal_after_make(b);
        board_unmake(b);
        verify(b, "random-probe-parent");
        if (chosen < 0 && legal) chosen = idx;
    }

    if (chosen < 0) {
        for (int k = lim; k < n; k++) {
            int idx = order[k];
            make_checked(b, &mv[idx], "random-find-child");
            int legal = mover_legal_after_make(b);
            board_unmake(b);
            verify(b, "random-find-parent");
            if (legal) { chosen = idx; break; }
        }
    }
    if (chosen < 0) return;

    make_checked(b, &mv[chosen], "random-descend");
    random_branch(b, depth - 1, probes);
    board_unmake(b);
    verify(b, "random-ascend");
}

static void targeted(void) {
    static const char *castle[] = {
        "e2e4","e7e5","g1f3","b8c6","f1e2","g8f6","e1g1","f8e7","d2d3","e8g8"
    };
    play_sequence("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                  castle, (int)(sizeof(castle)/sizeof(castle[0])), "castle-both");

    static const char *epw[] = {"e2e4","a7a6","e4e5","d7d5","e5d6"};
    play_sequence("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                  epw, 5, "ep-white");

    static const char *epb[] = {"a2a3","e7e5","a3a4","e5e4","d2d4","e4d3"};
    play_sequence("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                  epb, 6, "ep-black");

    static const char *prom[] = {"a7a8q","h2h1q"};
    play_sequence("7k/P7/8/8/8/8/7p/K7 w - - 0 1", prom, 2, "promotion-both");

    static const char *promcap[] = {"a7b8n"};
    play_sequence("1r5k/P7/8/8/8/8/8/K7 w - - 0 1", promcap, 1, "promotion-capture");

    /* Quiet pawn advance changes passed-file status without capture. */
    static const char *passed_toggle[] = {"e5e6"};
    play_sequence("7k/8/3p4/4P3/8/8/8/K7 w - - 0 1",
                  passed_toggle, 1, "passed-toggle");

    /* Deliberately illegal king-capture stress: _pk17_child claims to support
     * the captured-king stress case, so verify it explicitly. */
    static const char *kingcap[] = {"e1e2"};
    play_sequence("8/8/8/8/8/8/4k3/4K3 w - - 0 1",
                  kingcap, 1, "captured-king-stress");
}

int main(int argc, char **argv) {
    int rounds = argc > 2 ? atoi(argv[2]) : 200;
    int depth  = argc > 3 ? atoi(argv[3]) : 36;
    int probes = argc > 4 ? atoi(argv[4]) : 8;
    const char *weights = argc > 1 ? argv[1] : "nnue_weights.bin";

    board_init();
    if (nnue_load(weights) != 0) return 2;
    targeted();

    static const char *roots[] = {
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "8/5pk1/6p1/8/7P/6P1/5PK1/8 w - - 0 1",
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
        "8/8/3p4/2pPp3/4P3/8/4K3/6k1 w - c6 0 1",
        "r3k2r/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/R3K2R w KQkq - 0 1",
        "8/P6k/8/8/8/8/6p1/K7 w - - 0 1"
    };

    for (int r = 0; r < rounds; r++) {
        Board b; NnueAccum na; UndoFrame undo[STACK_SIZE]; int top = 0;
        g_rng ^= (uint64_t)(r + 1) * 0x9e3779b97f4a7c15ULL;
        fresh(&b, &na, undo, &top, roots[r % (int)(sizeof(roots)/sizeof(roots[0]))]);
        random_branch(&b, depth, probes);
        if (top != 0) {
            fprintf(stderr, "undo stack did not return to root: %d\n", top);
            return 2;
        }
        verify(&b, "round-root-restored");
    }

    printf("PK17_STRESS_OK checks=%lld makes=%lld rounds=%d depth=%d probes=%d\n",
           g_checks, g_makes, rounds, depth, probes);
    return 0;
}
