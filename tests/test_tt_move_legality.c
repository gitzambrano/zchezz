#include <stdio.h>
#include <stdint.h>
#include "board.h"

static int same_move(const Move *a, const Move *b) {
    return a->from == b->from && a->to == b->to && a->prom == b->prom &&
           a->epc == b->epc && a->castle == b->castle;
}

static int generated_has(const Move *moves, int n, const Move *m) {
    for (int i = 0; i < n; ++i)
        if (same_move(&moves[i], m)) return 1;
    return 0;
}

static int check_position(const char *fen) {
    Board b;
    if (board_load_fen(&b, fen) != 0) return 0;
    Move moves[MAX_MOVES];
    int n = board_gen_moves(&b, moves);

    for (int i = 0; i < n; ++i) {
        if (!board_move_is_pseudo_legal(&b, &moves[i])) {
            char u[6]; move_to_uci(&moves[i], u);
            fprintf(stderr, "false negative: %s in %s\n", u, fen);
            return 0;
        }
    }

    static const int promos[] = {0, 2, 3, 4, 5};
    for (int from = 0; from < 64; ++from) {
        for (int to = 0; to < 64; ++to) {
            for (unsigned pi = 0; pi < sizeof(promos) / sizeof(promos[0]); ++pi) {
                Move m = {(uint8_t)from, (uint8_t)to, (uint8_t)promos[pi], 0, 0, 0};
                int actual = board_move_is_pseudo_legal(&b, &m);
                int expected = generated_has(moves, n, &m);
                if (actual != expected) {
                    char u[6]; move_to_uci(&m, u);
                    fprintf(stderr, "normal/prom mismatch: %s actual=%d expected=%d in %s\n",
                            u, actual, expected, fen);
                    return 0;
                }
            }

            Move ep = {(uint8_t)from, (uint8_t)to, 0, 1, 0, 0};
            if (board_move_is_pseudo_legal(&b, &ep) != generated_has(moves, n, &ep)) {
                fprintf(stderr, "ep mismatch from=%d to=%d in %s\n", from, to, fen);
                return 0;
            }

            for (int cs = 1; cs <= 4; ++cs) {
                Move c = {(uint8_t)from, (uint8_t)to, 0, 0, (uint8_t)cs, 0};
                if (board_move_is_pseudo_legal(&b, &c) != generated_has(moves, n, &c)) {
                    fprintf(stderr, "castle mismatch from=%d to=%d cs=%d in %s\n",
                            from, to, cs, fen);
                    return 0;
                }
            }
        }
    }
    return 1;
}

int main(void) {
    board_init();
    static const char *fens[] = {
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        "8/1p4k1/3q2bp/3n4/4pR2/PBP3P1/1P3PK1/8 w - - 0 40",
        "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1",
        "7k/P7/8/8/8/8/8/7K w - - 0 1",
        "7k/8/8/8/8/8/p7/7K b - - 0 1",
        "8/8/8/3Pp3/8/8/8/4K2k w - e6 0 1",
        "8/8/8/8/3pP3/8/8/4K2k b - e3 0 1",
        "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
        NULL
    };
    for (int i = 0; fens[i]; ++i)
        if (!check_position(fens[i])) return 1;

    Board b;
    board_load_fen(&b, "8/1p4k1/3q2bp/3n4/4pR2/PBP3P1/1P3PK1/8 w - - 0 40");
    Move bad = {49, 57, 5, 0, 0, 0}; /* b2b1q: impossible for a white pawn */
    if (board_move_is_pseudo_legal(&b, &bad)) {
        fprintf(stderr, "regression: b2b1q accepted\n");
        return 1;
    }

    puts("TT move pseudo-legality parity: PASS");
    return 0;
}
