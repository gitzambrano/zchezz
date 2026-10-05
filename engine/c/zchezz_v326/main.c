/* main.c — Zchezz v3.26 UCI engine
 *
 * Full UCI protocol implementation with Syzygy tablebase + Polyglot book support.
 *
 * v3.13 CHANGES (thread safety + TB performance):
 *
 *   1. NNUE THREAD SAFETY (Component A):
 *      Each search thread (main + Lazy SMP helpers) now has its own NnueAccum
 *      struct containing private accumulator buffers (acc_w, acc_b), extra-feature
 *      caches, and dirty flags.  This eliminates the data race where concurrent
 *      nnue_eval_bb calls clobbered shared global accumulator state.
 *
 *      - Main thread: uses g_nnue_accum (defined in board.c, bound via
 *        board_bind_nnue_global in board_load_fen).
 *      - Helper threads: each allocates its own NnueAccum on the heap with
 *        zmalloc32 (32-byte aligned for AVX2), bound to the thread's private
 *        Board copy via board.nnue = my_nnue.
 *      - Weight arrays (_nnL1WT, _nnL2W, etc.) remain global and read-only
 *        after nnue_load, so they are inherently thread-safe.
 *
 *   2. TT PERFORMANCE FIX:
 *      Moved TT probe BEFORE TB probe in alpha_beta.  In v3.12, the TT probe
 *      was AFTER the TB probe, so depth-127 TT entries from previous TB hits
 *      were never consulted on revisits — each TB position triggered a fresh
 *      Fathom mmap read.  This caused massive cache thrashing and -41 ELO.
 *      With TT-first ordering, the first TB probe caches at depth=127 in TT,
 *      and all subsequent visits find the cached entry with zero disk I/O.
 *
 * Compile (Windows / Linux):
 *   gcc -O3 -ffast-math -D_GNU_SOURCE -std=c11 -mavxvnni -mavx2 \
 *       -o zchezz main.c board.c search.c nnue.c syzygy.c tbprobe.c book.c \
 *       -static -lm -pthread
 *
 * WebAssembly (Emscripten):
 *   emcc -O3 -msimd128 -DNO_TABLEBASES main.c board.c search.c nnue.c -o zchezz.js ...
 *
 * Usage:
 *   ./zchezz                        — interactive UCI mode
 *   ./zchezz --nnue path/to/weights.bin
 *   ./zchezz bench [depth]          — run benchmark (20 positions)
 *
 * UCI commands handled:
 *   uci, debug [on|off], isready, ucinewgame, register,
 *   setoption name <name> value <value>,
 *   position startpos|fen <fen> [moves ...],
 *   go [depth|movetime|wtime|btime|winc|binc|movestogo|nodes|mate|
 *       infinite|ponder|searchmoves ...],
 *   stop, ponderhit, quit, d, bench [depth]
 */

#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <time.h>
#include "board.h"
#include "search.h"
#include "nnue.h"
#include "syzygy.h"
#include "book.h"
#include <pthread.h>

#if defined(__EMSCRIPTEN__) || !defined(_POSIX_C_SOURCE)
static int z_strcasecmp(const char *a, const char *b) {
    while (*a && *b) {
        int d = tolower((unsigned char)*a) - tolower((unsigned char)*b);
        if (d) return d;
        a++; b++;
    }
    return tolower((unsigned char)*a) - tolower((unsigned char)*b);
}
static int z_strncasecmp(const char *a, const char *b, size_t n) {
    for (size_t i = 0; i < n; i++) {
        int d = tolower((unsigned char)a[i]) - tolower((unsigned char)b[i]);
        if (d) return d;
        if (!a[i]) return 0;
    }
    return 0;
}
#define strcasecmp  z_strcasecmp
#define strncasecmp z_strncasecmp
#endif

#define ENGINE_NAME    "Zchezz"
#define ENGINE_VERSION "3.26"
#define ENGINE_AUTHOR  "Gustavo Zambrano"

static Board  g_board;
static int    g_has_position = 0;
static int    g_debug = 0;

static int    g_opt_contempt    = 15;
static int    g_opt_move_overhead = 50;
static int    g_opt_multi_pv   = 1;
static int    g_opt_ponder     = 0;
static int    g_opt_analyse    = 0;
static int    g_opt_threads    = 1;
static int    g_opt_hash_mb    = 64;

static char   g_opt_syzygy_path[512] = "";
static int    g_opt_syzygy_probe_depth = 1;
static int    g_opt_syzygy_probe_limit = 6;
static int    g_opt_syzygy_50move = 1;

static int    g_opt_own_book = 0;
static char   g_opt_book_file[512] = "";

#define DEFAULT_DEPTH 8

static pthread_mutex_t g_io_mutex = PTHREAD_MUTEX_INITIALIZER;

static long long wc_now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)(ts.tv_sec * 1000LL + ts.tv_nsec / 1000000LL);
}

static char *trim(char *s) {
    while (isspace((unsigned char)*s)) s++;
    char *e = s + strlen(s) - 1;
    while (e >= s && isspace((unsigned char)*e)) *e-- = '\0';
    return s;
}

static int eat(const char **ptr, const char *tok) {
    const char *p = *ptr;
    while (isspace((unsigned char)*p)) p++;
    int len = (int)strlen(tok);
    if (strncasecmp(p, tok, len) == 0 &&
        (p[len] == '\0' || isspace((unsigned char)p[len]))) {
        *ptr = p + len;
        return 1;
    }
    return 0;
}

static int next_token(const char **ptr, char *buf, int bufsz) {
    const char *p = *ptr;
    while (isspace((unsigned char)*p)) p++;
    if (!*p) return 0;
    int i = 0;
    while (*p && !isspace((unsigned char)*p) && i < bufsz-1)
        buf[i++] = *p++;
    buf[i] = '\0';
    *ptr = p;
    return 1;
}

static int tt_hashfull(void) {
    return tt_hashfull_permille();
}

static void auto_load_nnue(void);

static pthread_t g_search_thread;
static int       g_searching = 0;
static volatile int g_stop_flag = 0;

static void cmd_uci(void) {
    printf("id name %s %s\n", ENGINE_NAME, ENGINE_VERSION);
    printf("id author %s\n", ENGINE_AUTHOR);
    printf("option name Hash type spin default 64 min 1 max 1024\n");
    printf("option name Threads type spin default 1 min 1 max 128\n");
    printf("option name NNUE type string default \"\"\n");
    printf("option name Contempt type spin default 15 min -100 max 100\n");
    printf("option name MoveOverhead type spin default 50 min 0 max 5000\n");
    printf("option name MultiPV type spin default 1 min 1 max 6\n");
    printf("option name Ponder type check default false\n");
    printf("option name UCI_AnalyseMode type check default false\n");
    printf("option name UCI_Chess960 type check default false\n");
    printf("option name SyzygyPath type string default \"\"\n");
    printf("option name SyzygyProbeDepth type spin default 1 min 1 max 100\n");
    printf("option name SyzygyProbeLimit type spin default 6 min 0 max 7\n");
    printf("option name Syzygy50MoveRule type check default true\n");
    printf("option name OwnBook type check default false\n");
    printf("option name BookFile type string default \"\"\n");
    printf("uciok\n");
    fflush(stdout);
}

static void cmd_isready(void) {
    if (g_searching) {
        g_stop_flag = 1;
        pthread_join(g_search_thread, NULL);
        g_searching = 0;
    }
    if (!nnue_ready()) auto_load_nnue();
    printf("readyok\n");
    fflush(stdout);
}

static void cmd_ucinewgame(void) {
    TT_GEN = (TT_GEN + 1) & 0xFFFF;
    if ((TT_GEN & 0xFF) == 0) tt_clear();
    search_history_clear(&g_ss);
    g_has_position = 0;
    nnue_reset(&g_nnue_accum);
}

static void cmd_setoption(const char *line) {
    const char *p = line;
    if (!eat(&p, "name")) return;
    char name[64] = {0};
    while (1) {
        char tok[64];
        if (!next_token(&p, tok, sizeof(tok))) break;
        if (strcasecmp(tok, "value") == 0) break;
        if (name[0]) strncat(name, " ", sizeof(name)-strlen(name)-1);
        strncat(name, tok, sizeof(name)-strlen(name)-1);
    }
    char value[512] = {0};
    const char *v = p;
    while (isspace((unsigned char)*v)) v++;
    strncpy(value, v, sizeof(value)-1);

    if (strcasecmp(name, "nnue") == 0 && value[0]) {
        if (nnue_load(value) != 0)
            fprintf(stderr, "[UCI] NNUE load failed: %s\n", value);
    }
    else if (strcasecmp(name, "Contempt") == 0) {
        g_opt_contempt = atoi(value);
    }
    else if (strcasecmp(name, "MoveOverhead") == 0) {
        g_opt_move_overhead = atoi(value);
        if (g_opt_move_overhead < 0) g_opt_move_overhead = 0;
        if (g_opt_move_overhead > 5000) g_opt_move_overhead = 5000;
    }
    else if (strcasecmp(name, "MultiPV") == 0) {
        g_opt_multi_pv = atoi(value);
        if (g_opt_multi_pv < 1) g_opt_multi_pv = 1;
        if (g_opt_multi_pv > 6) g_opt_multi_pv = 6;
    }
    else if (strcasecmp(name, "Ponder") == 0) {
        g_opt_ponder = (strcasecmp(value, "true") == 0) ? 1 : 0;
    }
    else if (strcasecmp(name, "UCI_AnalyseMode") == 0) {
        g_opt_analyse = (strcasecmp(value, "true") == 0) ? 1 : 0;
    }
    else if (strcasecmp(name, "SyzygyPath") == 0) {
        strncpy(g_opt_syzygy_path, value, sizeof(g_opt_syzygy_path)-1);
        if (value[0]) {
            int loaded = syzygy_init(value);
            if (loaded > 0) {
                g_tb_probe_depth = 1;
                g_tb_probe_limit = loaded < 7 ? loaded : 6;
            }
            fprintf(stderr, "info string Syzygy %d-piece tables loaded (probe_depth=%d)\n",
                    loaded, g_tb_probe_depth);
            fflush(stderr);
        } else {
            g_tb_probe_depth = 99;
            g_tb_probe_limit = 0;
        }
    }
    else if (strcasecmp(name, "SyzygyProbeDepth") == 0) {
        g_opt_syzygy_probe_depth = atoi(value);
        if (g_opt_syzygy_probe_depth < 1) g_opt_syzygy_probe_depth = 1;
        g_tb_probe_depth = g_opt_syzygy_probe_depth;
    }
    else if (strcasecmp(name, "SyzygyProbeLimit") == 0) {
        g_opt_syzygy_probe_limit = atoi(value);
        if (g_opt_syzygy_probe_limit < 0) g_opt_syzygy_probe_limit = 0;
        if (g_opt_syzygy_probe_limit > 7) g_opt_syzygy_probe_limit = 7;
        g_tb_probe_limit = g_opt_syzygy_probe_limit;
    }
    else if (strcasecmp(name, "Syzygy50MoveRule") == 0) {
        g_opt_syzygy_50move = (strcasecmp(value, "true") == 0) ? 1 : 0;
    }
    else if (strcasecmp(name, "OwnBook") == 0) {
        g_opt_own_book = (strcasecmp(value, "true") == 0) ? 1 : 0;
    }
    else if (strcasecmp(name, "BookFile") == 0) {
        strncpy(g_opt_book_file, value, sizeof(g_opt_book_file)-1);
        if (value[0]) {
            int loaded = book_open(value);
            if (g_debug)
                fprintf(stderr, "info string BookFile set to %s (%d entries loaded)\n",
                        value, loaded);
        }
    }
    else if (strcasecmp(name, "Threads") == 0) {
        g_opt_threads = atoi(value);
        if (g_opt_threads < 1) g_opt_threads = 1;
        if (g_opt_threads > 128) g_opt_threads = 128;
    }
    else if (strcasecmp(name, "Hash") == 0) {
        int mb = atoi(value);
        if (mb < 1) mb = 1;
        if (mb > 1024) mb = 1024;
        if (g_searching) {
            g_stop_flag = 1;
            pthread_join(g_search_thread, NULL);
            g_searching = 0;
        }
        if (tt_resize_mb(mb)) g_opt_hash_mb = mb;
    }
}

static void apply_moves(const char *moves_str) {
    const char *p = moves_str;
    char tok[8];
    while (next_token(&p, tok, sizeof(tok))) {
        Move m;
        if (!move_from_uci(&g_board, tok, &m)) {
            fprintf(stderr, "[UCI] Illegal move in position: %s\n", tok);
            break;
        }
        board_make(&g_board, &m);
    }
}

static void cmd_position(const char *line) {
    if (g_searching) {
        g_stop_flag = 1;
        pthread_join(g_search_thread, NULL);
        g_searching = 0;
    }
    g_undo_top = 0;
    const char *p = line;

    if (eat(&p, "startpos")) {
        board_load_fen(&g_board,
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1");
    } else if (eat(&p, "fen")) {
        while (isspace((unsigned char)*p)) p++;
        const char *moves_kw = NULL;
        {
            const char *q = p;
            while (*q) {
                if (strncasecmp(q, "moves", 5) == 0 &&
                    (q == p || isspace((unsigned char)*(q-1))) &&
                    (*(q+5)=='\0' || isspace((unsigned char)*(q+5)))) {
                    moves_kw = q; break;
                }
                q++;
            }
        }
        char fen_buf[256] = {0};
        if (moves_kw) {
            int len = (int)(moves_kw - p);
            while (len > 0 && isspace((unsigned char)p[len-1])) len--;
            strncpy(fen_buf, p, len < 255 ? len : 255);
            p = moves_kw;
        } else {
            strncpy(fen_buf, p, 255);
            p += strlen(p);
        }
        board_load_fen(&g_board, trim(fen_buf));
    } else {
        return;
    }
    g_has_position = 1;
    if (eat(&p, "moves")) apply_moves(p);
}

static int estimate_movetime(int wtime, int btime, int winc, int binc,
                              int is_white, int fullmove, int movestogo) {
    int my_time = is_white ? wtime : btime;
    int my_inc  = is_white ? winc  : binc;
    if (my_time <= 0) my_time = 10000;
    int moves_rem;
    if (movestogo > 0) moves_rem = movestogo;
    else {
        if (fullmove < 15) moves_rem = 40 - fullmove / 3;
        else if (fullmove < 40) moves_rem = 30 - (fullmove - 15) / 5;
        else moves_rem = 22 - (fullmove - 40) / 8;
        if (moves_rem < 12) moves_rem = 12;
    }
    int movetime = my_time / moves_rem + (int)(my_inc * 0.75);
    movetime -= g_opt_move_overhead;
    int hard_cap = my_time / 4;
    if (movetime > hard_cap) movetime = hard_cap;
    if (movetime < 10) movetime = 10;
    return movetime;
}

static long long g_search_start_ms = 0;

static void uci_info_cb(int depth, int score, long nodes, const char *pv, int turn, int multipv) {
    (void)turn;
    long long elapsed = wc_now_ms() - g_search_start_ms;
    if (elapsed <= 0) elapsed = 1;
    long long nps = nodes * 1000LL / elapsed;
    int hf = tt_hashfull();
    extern long s_tb_hits;
    pthread_mutex_lock(&g_io_mutex);
    int is_mate = (score > 9000 || score < -9000);
    if (is_mate) {
        int plies = score > 0 ? (19000 - score) : -(19000 + score);
        int mate_in = (plies + 1) / 2;
        if (score < 0) mate_in = -mate_in;
        printf("info depth %d seldepth %d", depth, depth);
        if (g_opt_multi_pv > 1) printf(" multipv %d", multipv);
        printf(" score mate %d nodes %ld nps %lld time %lld hashfull %d tbhits %ld",
               mate_in, nodes, nps, elapsed, hf, s_tb_hits);
    } else {
        printf("info depth %d seldepth %d", depth, depth);
        if (g_opt_multi_pv > 1) printf(" multipv %d", multipv);
        printf(" score cp %d nodes %ld nps %lld time %lld hashfull %d tbhits %ld",
               score, nodes, nps, elapsed, hf, s_tb_hits);
    }
    if (pv && pv[0]) printf(" pv %s", pv);
    printf("\n");
    fflush(stdout);
    pthread_mutex_unlock(&g_io_mutex);
}

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

typedef struct {
    Board board;
    SearchParams params;
    volatile int done;
} HelperArgs;

static pthread_t g_helper_threads[127];
static HelperArgs g_helper_args[127];
static int g_num_helpers = 0;

static void *helper_thread_fn(void *arg) {
    HelperArgs *ha = (HelperArgs *)arg;
    pthread_setcanceltype(PTHREAD_CANCEL_ASYNCHRONOUS, NULL);
    UndoFrame *my_undo = (UndoFrame *)malloc(STACK_SIZE * sizeof(UndoFrame));
    int my_undo_top = 0;
    ha->board.undo = my_undo;
    ha->board.undo_top = &my_undo_top;
    NnueAccum *my_nnue = (NnueAccum *)zmalloc32(sizeof(NnueAccum));
    if (my_nnue) {
        memset(my_nnue, 0, sizeof(NnueAccum));
        ha->board.nnue = my_nnue;
    }
    SearchState *my_ss = search_state_new();
    if (my_ss && my_undo && my_nnue) {
        ha->params.search_state = my_ss;
        search_best(&ha->board, &ha->params);
        search_state_free(my_ss);
    }
    if (my_nnue) zfree32(my_nnue);
    free(my_undo);
    ha->done = 1;
    return NULL;
}

typedef struct {
    Board board;
    SearchParams params;
    int own_book;
    int book_loaded;
} SearchThreadArgs;

static SearchThreadArgs g_sta;

static void *search_thread_fn(void *arg) {
    SearchThreadArgs *sta = (SearchThreadArgs *)arg;
    if (sta->own_book && sta->book_loaded) {
        Move book_move;
        if (book_probe(&sta->board, &book_move)) {
            char uci_bk[6];
            move_to_uci(&book_move, uci_bk);
            pthread_mutex_lock(&g_io_mutex);
            printf("info string book move %s\n", uci_bk);
            printf("bestmove %s\n", uci_bk);
            fflush(stdout);
            pthread_mutex_unlock(&g_io_mutex);
            g_searching = 0;
            return NULL;
        }
    }

    int n_helpers = sta->params.threads - 1;
    if (n_helpers > 127) n_helpers = 127;
    g_num_helpers = n_helpers;
    for (int i = 0; i < n_helpers; i++) {
        g_helper_args[i].board = sta->board;
        g_helper_args[i].params = sta->params;
        g_helper_args[i].params.info_cb = NULL;
        g_helper_args[i].params.multi_pv = 1;
        g_helper_args[i].params.stop = sta->params.stop;
        int sd;
        if (i < 2) sd = i + 2;
        else       sd = 2 * i + 1;
        if (sd > sta->params.max_depth) sd = sta->params.max_depth;
        g_helper_args[i].done = 0;
        g_helper_args[i].params.start_depth = sd;
        pthread_attr_t attr;
        pthread_attr_init(&attr);
        pthread_attr_setstacksize(&attr, 8 * 1024 * 1024);
        pthread_create(&g_helper_threads[i], &attr, helper_thread_fn, &g_helper_args[i]);
        pthread_attr_destroy(&attr);
    }

    sta->params.start_depth = 0;
    SearchResult r = search_best(&sta->board, &sta->params);
    g_stop_flag = 1;
    long long join_deadline = wc_now_ms() + 5000;
    for (int i = 0; i < n_helpers; i++) {
        while (!g_helper_args[i].done && wc_now_ms() < join_deadline) {
            struct timespec ts = {0, 1000000};
            nanosleep(&ts, NULL);
        }
        if (g_helper_args[i].done) {
            pthread_join(g_helper_threads[i], NULL);
        } else {
            pthread_cancel(g_helper_threads[i]);
            pthread_join(g_helper_threads[i], NULL);
        }
    }
    g_num_helpers = 0;

    char uci[6];
    move_to_uci(&r.best, uci);
    char ponder_move[6] = {0};
    if (r.pv[0]) {
        const char *pv_ptr = r.pv;
        char first[8];
        if (next_token(&pv_ptr, first, sizeof(first))) {
            char second[8];
            if (next_token(&pv_ptr, second, sizeof(second))) strncpy(ponder_move, second, 5);
        }
    }
    pthread_mutex_lock(&g_io_mutex);
    if (ponder_move[0] && g_opt_ponder) printf("bestmove %s ponder %s\n", uci, ponder_move);
    else printf("bestmove %s\n", uci);
    fflush(stdout);
    pthread_mutex_unlock(&g_io_mutex);
    g_searching = 0;
    return NULL;
}

static void cmd_go(const char *line) {
    if (!g_has_position) {
        board_load_fen(&g_board,
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1");
        g_has_position = 1;
    }
    if (g_searching) {
        g_stop_flag = 1;
        pthread_join(g_search_thread, NULL);
        g_searching = 0;
    }
    SearchParams p = {0};
    p.max_depth = DEFAULT_DEPTH;
    const char *ptr = line;
    int wtime=0,btime=0,winc=0,binc=0;
    int movetime=0, infinite=0, movestogo=0;
    int ponder=0, mate=0;
    char tok[32];
    char searchmoves[1024] = {0};
    while (next_token(&ptr, tok, sizeof(tok))) {
        if      (!strcasecmp(tok,"depth"))     { char v[16]; next_token(&ptr,v,sizeof(v)); p.max_depth=atoi(v); }
        else if (!strcasecmp(tok,"movetime"))  { char v[16]; next_token(&ptr,v,sizeof(v)); movetime=atoi(v); }
        else if (!strcasecmp(tok,"wtime"))     { char v[16]; next_token(&ptr,v,sizeof(v)); wtime=atoi(v); }
        else if (!strcasecmp(tok,"btime"))     { char v[16]; next_token(&ptr,v,sizeof(v)); btime=atoi(v); }
        else if (!strcasecmp(tok,"winc"))      { char v[16]; next_token(&ptr,v,sizeof(v)); winc=atoi(v); }
        else if (!strcasecmp(tok,"binc"))      { char v[16]; next_token(&ptr,v,sizeof(v)); binc=atoi(v); }
        else if (!strcasecmp(tok,"nodes"))     { char v[16]; next_token(&ptr,v,sizeof(v)); p.node_limit=atol(v); }
        else if (!strcasecmp(tok,"movestogo")){ char v[16]; next_token(&ptr,v,sizeof(v)); movestogo=atoi(v); }
        else if (!strcasecmp(tok,"mate"))      { char v[16]; next_token(&ptr,v,sizeof(v)); mate=atoi(v); }
        else if (!strcasecmp(tok,"infinite"))  { infinite=1; }
        else if (!strcasecmp(tok,"ponder"))    { ponder=1; }
        else if (!strcasecmp(tok,"searchmoves")) {
            while (next_token(&ptr, tok, sizeof(tok))) {
                if (searchmoves[0]) strncat(searchmoves, " ", sizeof(searchmoves)-strlen(searchmoves)-1);
                strncat(searchmoves, tok, sizeof(searchmoves)-strlen(searchmoves)-1);
            }
        }
    }
    if (infinite || ponder) {
        p.max_depth     = MAX_PLY - 1;
        p.time_limit_ms = 0;
    } else if (movetime > 0) {
        p.time_limit_ms = movetime;
        p.max_depth     = MAX_PLY - 1;
        p.node_limit    = 0;
    } else if (mate > 0) {
        p.max_depth = mate * 2;
        p.time_limit_ms = 0;
    } else if (p.node_limit > 0) {
        p.max_depth = MAX_PLY - 1;
        p.time_limit_ms = 0;
    } else if (wtime > 0 || btime > 0) {
        int is_white = (g_board.turn == COL_W);
        p.time_limit_ms = estimate_movetime(wtime, btime, winc, binc,
                                             is_white, (int)g_board.fm, movestogo);
        p.max_depth = MAX_PLY - 1;
    }
    g_search_start_ms = wc_now_ms();
    g_stop_flag = 0;
    p.info_cb = uci_info_cb;
    p.multi_pv = g_opt_multi_pv;
    p.threads = g_opt_threads;
    p.stop = &g_stop_flag;
    g_sta.board = g_board;
    g_sta.params = p;
    g_sta.own_book = g_opt_own_book;
    g_sta.book_loaded = book_is_loaded();
    g_searching = 1;
    pthread_create(&g_search_thread, NULL, search_thread_fn, &g_sta);
}

static const char *BENCH_FENS[] = {
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
    "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
    "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
    "r1bqkbnr/pppppppp/2n5/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 1 2",
    "r1bqkb1r/pppppppp/2n2n2/8/2PP4/8/PP2PPPP/RNBQKBNR w KQkq - 2 3",
    "r1bqkb1r/1ppp1ppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4",
    "r1b1kb1r/ppppqppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
    "2r3k1/p4pp1/1p2pn1p/2p5/3P4/2P1PNP1/P3KPBP/R7 w - - 0 24",
    "r2qr1k1/pp1nbppp/3p1n2/2pP4/4P3/2N5/PP3PPP/R1BQRNK1 w - - 3 13",
    "3r1rk1/pp3ppp/2n1bn2/4N3/1bBPP3/8/PP3PPP/RNB1R1K1 w - - 3 11",
    "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
    "8/8/4kpp1/3p1b2/p6P/2B5/6P1/6K1 w - - 0 47",
    "8/5pk1/7p/3p1Rp1/p2P2P1/1r5P/1P3PK1/8 w - - 2 40",
    "r2q1rk1/ppp2ppp/2n1bn2/2b1p3/3pP3/3P1NP1/PPP1NPBP/R1BQ1RK1 b - - 0 8",
    "r1bq1rk1/pp2npbp/2np2p1/2p1p3/4P3/2PP1NP1/PP1N1PBP/R1BQ1RK1 w - - 0 9",
    "4rrk1/1ppq1p1p/p2p1bp1/8/3Pp3/PPQ1P1P1/3N1PBP/1R3RK1 b - - 6 20",
    "r4rk1/1bqnbppp/pp2pn2/2p1N3/P1PP4/1BN1P3/1PQ2PPP/R1B2RK1 w - - 0 13",
    NULL
};

static void cmd_bench(int depth) {
    if (depth <= 0) depth = 13;
    Board bb;
    long long total_nodes = 0;
    long long t0 = wc_now_ms();
    for (int i = 0; BENCH_FENS[i]; i++) {
        board_load_fen(&bb, BENCH_FENS[i]);
        SearchParams sp = {0};
        sp.max_depth = depth;
        sp.info_cb = NULL;
        SearchResult r = search_best(&bb, &sp);
        total_nodes += r.nodes;
        char mv[6]; move_to_uci(&r.best, mv);
        printf("Position %2d: depth=%2d nodes=%10lld best=%s score=%d\n",
               i+1, r.depth, (long long)r.nodes, mv, r.score);
        fflush(stdout);
    }
    long long elapsed = wc_now_ms() - t0;
    if (elapsed <= 0) elapsed = 1;
    long long nps = total_nodes * 1000LL / elapsed;
    printf("\n===========================\n");
    printf("Total nodes : %lld\n", total_nodes);
    printf("Elapsed     : %lld ms\n", elapsed);
    printf("Nodes/sec   : %lld\n", nps);
    printf("===========================\n");
    fflush(stdout);
}

static void cmd_display(void) {
    char fen[128]; board_to_fen(&g_board, fen);
    printf("\n +---+---+---+---+---+---+---+---+\n");
    for (int r = 0; r < 8; r++) {
        printf(" |");
        for (int c = 0; c < 8; c++) {
            int sq = r * 8 + c;
            uint8_t p = g_board.b[sq];
            char ch = '.';
            if (p) {
                const char *pieces = ".PNBRQK";
                int t = PC_TYPE(p);
                ch = pieces[t];
                if (PC_COLOR(p) == COL_B) ch = tolower(ch);
            }
            printf(" %c |", ch);
        }
        printf(" %d\n +---+---+---+---+---+---+---+---+\n", 8 - r);
    }
    printf("   a   b   c   d   e   f   g   h\n\n");
    printf("Fen: %s\n", fen);
    printf("Turn: %s\n", g_board.turn==COL_W?"white":"black");
    printf("Castling: %c%c%c%c\n",
           (g_board.ca & CA_WK) ? 'K' : '-',
           (g_board.ca & CA_WQ) ? 'Q' : '-',
           (g_board.ca & CA_BK) ? 'k' : '-',
           (g_board.ca & CA_BQ) ? 'q' : '-');
    printf("EP: %s\n", g_board.ep >= 0 ?
           (char[]){'a' + (g_board.ep & 7), '1' + (7 - (g_board.ep >> 3)), 0} : "-");
    printf("Halfmove: %d  Fullmove: %d\n", g_board.hm, g_board.fm);
    printf("Hash: 0x%016llx\n", (unsigned long long)g_board.hash);
    if (nnue_ready() && g_board.nnue) nnue_rebuild(g_board.nnue, g_board.b);
    printf("Eval: %d cp\n", nnue_ready() ? eval_stm(&g_board) : 0);
    printf("Hashfull: %d permille\n", tt_hashfull());
    fflush(stdout);
}

static char g_exe_dir[512] = "";

static void auto_load_nnue(void) {
    if (nnue_ready()) return;
    if (nnue_load("nnue_weights.bin") == 0) return;
    if (g_exe_dir[0]) {
        char path[1024];
        snprintf(path, sizeof(path), "%s/nnue_weights.bin", g_exe_dir);
        if (nnue_load(path) == 0) return;
    }
    nnue_load("chess_test/nnue_weights.bin");
}

static long long perft_inner(Board *b, int depth) {
    if (depth == 0) return 1;
    Move moves[256];
    int n = board_gen_moves(b, moves);
    long long total = 0;
    for (int i = 0; i < n; i++) {
        board_make(b, &moves[i]);
        int mover_col = b->turn ^ 24;
        int king_sq = mover_col == COL_W ? b->wk : b->bk;
        if (!board_is_attacked(b, king_sq, b->turn)) total += perft_inner(b, depth - 1);
        board_unmake(b);
    }
    return total;
}

int main(int argc, char **argv) {
    board_init();
    search_init();
    if (argc > 0 && argv[0][0]) {
        strncpy(g_exe_dir, argv[0], sizeof(g_exe_dir)-1);
        char *sep = NULL;
        for (char *p = g_exe_dir; *p; p++) if (*p == '/' || *p == '\\') sep = p;
        if (sep) *sep = '\0';
        else g_exe_dir[0] = '\0';
    }
    int do_bench = 0;
    int bench_depth = 13;
    for (int i = 1; i < argc; i++) {
        if ((strcmp(argv[i], "--nnue") == 0 || strcmp(argv[i], "-n") == 0) && i+1 < argc) {
            nnue_load(argv[++i]);
        } else if (strstr(argv[i], ".bin")) {
            nnue_load(argv[i]);
        } else if (strcmp(argv[i], "bench") == 0) {
            do_bench = 1;
            if (i+1 < argc && argv[i+1][0] >= '0' && argv[i+1][0] <= '9') bench_depth = atoi(argv[++i]);
        }
    }
    if (!nnue_ready()) auto_load_nnue();
    if (do_bench) {
        cmd_bench(bench_depth);
        return 0;
    }
    setvbuf(stdout, NULL, _IOLBF, 0);
    char line[4096];
    while (fgets(line, sizeof(line), stdin)) {
        char *l = trim(line);
        if (!*l) continue;
        const char *p = l;
        if      (eat(&p, "uci"))        { cmd_uci(); }
        else if (eat(&p, "debug"))      {
            char v[8];
            if (next_token(&p, v, sizeof(v))) g_debug = (strcasecmp(v, "on") == 0) ? 1 : 0;
        }
        else if (eat(&p, "isready"))    { cmd_isready(); }
        else if (eat(&p, "ucinewgame")) { cmd_ucinewgame(); }
        else if (eat(&p, "register"))   { printf("registration ok\n"); fflush(stdout); }
        else if (eat(&p, "setoption"))  { cmd_setoption(p); }
        else if (eat(&p, "position"))   { cmd_position(p); }
        else if (eat(&p, "go"))         { cmd_go(p); }
        else if (eat(&p, "stop"))       {
            if (g_searching) { g_stop_flag = 1; pthread_join(g_search_thread, NULL); g_searching = 0; }
        }
        else if (eat(&p, "ponderhit"))  { }
        else if (eat(&p, "quit"))       {
            if (g_searching) { g_stop_flag = 1; pthread_join(g_search_thread, NULL); g_searching = 0; }
            book_close(); break;
        }
        else if (eat(&p, "bench"))      {
            int bd = 13;
            char v[16];
            if (next_token(&p, v, sizeof(v))) bd = atoi(v);
            cmd_bench(bd);
        }
        else if (eat(&p, "d")) { cmd_display(); }
        else if (eat(&p, "eval")) {
            if (g_has_position && nnue_ready()) {
                if (g_board.nnue) nnue_rebuild(g_board.nnue, g_board.b);
                int ev = eval_stm(&g_board);
                printf("info string eval %d cp (STM-relative)\n", ev);
            } else printf("info string No position loaded or NNUE not ready\n");
            fflush(stdout);
        }
        else if (eat(&p, "perft")) {
            char v[16];
            int pd = 5;
            if (next_token(&p, v, sizeof(v))) pd = atoi(v);
            if (pd < 1) pd = 1;
            if (pd > 7) pd = 7;
            if (!g_has_position) {
                board_load_fen(&g_board,
                    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1");
                g_has_position = 1;
            }
            printf("info string Perft(%d) running...\n", pd);
            fflush(stdout);
            long long t0 = wc_now_ms();
            Move moves[256];
            int n = board_gen_moves(&g_board, moves);
            long long total = 0;
            for (int i = 0; i < n; i++) {
                board_make(&g_board, &moves[i]);
                int mover_col = g_board.turn ^ 24;
                int king_sq = mover_col == COL_W ? g_board.wk : g_board.bk;
                if (!board_is_attacked(&g_board, king_sq, g_board.turn)) {
                    long long cnt = perft_inner(&g_board, pd - 1);
                    total += cnt;
                    char uci_m[6];
                    move_to_uci(&moves[i], uci_m);
                    printf("%s: %lld\n", uci_m, cnt);
                }
                board_unmake(&g_board);
            }
            long long elapsed = wc_now_ms() - t0;
            if (elapsed <= 0) elapsed = 1;
            printf("\nNodes searched: %lld\n", total);
            printf("Time: %lld ms\n", elapsed);
            printf("NPS: %lld\n", total * 1000LL / elapsed);
            fflush(stdout);
        }
    }
    if (g_searching) {
        pthread_join(g_search_thread, NULL);
        g_searching = 0;
    }
    book_close();
    return 0;
}
