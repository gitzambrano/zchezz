/* ThreadSanitizer harness for NNUE/PK17 per-thread state.
 * The weight tables are loaded before worker creation and then read-only.
 * Each worker owns its Board/NnueAccum/undo stack.  Any TSan report therefore
 * points at accidental mutable globals in the NNUE path or initialization.
 */
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "board.h"
#include "nnue.h"

#define NTH 8
#define ITERS 250

static pthread_barrier_t barrier;
static const char *roots[NTH] = {
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "8/5pk1/6p1/8/7P/6P1/5PK1/8 w - - 0 1",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "8/8/3p4/2pPp3/4P3/8/4K3/6k1 w - c6 0 1",
    "r3k2r/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/R3K2R w KQkq - 0 1",
    "7k/P7/8/8/8/8/6p1/K7 w - - 0 1",
    "4k3/8/8/2pP4/8/8/8/4K3 w - - 0 1",
    "4k3/pp3ppp/8/8/8/8/PPP3PP/4K3 b - - 0 1"
};

typedef struct { int id; int rc; } Arg;

static void *worker(void *vp) {
    Arg *a = (Arg *)vp;
    Board b;
    NnueAccum *na = aligned_alloc(32, (sizeof(NnueAccum)+31u)&~31u);
    UndoFrame *undo = calloc(STACK_SIZE, sizeof(UndoFrame));
    int top = 0;
    if (!na || !undo) { a->rc = 2; return NULL; }
    memset(na, 0, sizeof(*na));
    board_load_fen(&b, roots[a->id]);
    b.nnue = na; b.undo = undo; b.undo_top = &top;

    /* Simultaneous first reset/rebuild deliberately stresses process-global
     * mutable state such as lazy lookup-table initialization. */
    pthread_barrier_wait(&barrier);
    for (int it = 0; it < ITERS; ++it) {
        nnue_reset(na);
        nnue_rebuild(na, b.b);
#ifdef PK17_VERIFY
        if (nnue_pk17_verify(na, b.b)) { a->rc = 3; break; }
#endif
        Move mv[MAX_MOVES];
        int n = board_gen_moves(&b, mv);
        if (n > 0) {
            Move m = mv[(it + a->id * 7) % n];
            board_make(&b, &m);
#ifdef PK17_VERIFY
            if (!na->acc_dirty && nnue_pk17_verify(na, b.b)) { a->rc = 4; break; }
#endif
            board_unmake(&b);
#ifdef PK17_VERIFY
            if (!na->acc_dirty && nnue_pk17_verify(na, b.b)) { a->rc = 5; break; }
#endif
        }
    }
    free(undo); free(na);
    return NULL;
}

int main(int argc, char **argv) {
    const char *weights = argc > 1 ? argv[1] : "nnue_weights.bin";
    board_init();
    if (nnue_load(weights) != 0) return 2;
    pthread_barrier_init(&barrier, NULL, NTH);
    pthread_t th[NTH]; Arg a[NTH];
    for (int i=0;i<NTH;i++) { a[i].id=i; a[i].rc=0; pthread_create(&th[i],NULL,worker,&a[i]); }
    int rc=0;
    for (int i=0;i<NTH;i++) { pthread_join(th[i],NULL); if(a[i].rc) rc=a[i].rc; }
    pthread_barrier_destroy(&barrier);
    if (rc) { fprintf(stderr,"PK17_MT_FAIL rc=%d\n",rc); return rc; }
    puts("PK17_MT_OK threads=8 iterations=250");
    return 0;
}
