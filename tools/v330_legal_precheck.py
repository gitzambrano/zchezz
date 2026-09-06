#!/usr/bin/env python3
from pathlib import Path

root = Path('engine/c/zchezz_v323')
main = root / 'main.c'
s = main.read_text(encoding='utf-8')
old = '#define ENGINE_VERSION "3.23"'
if s.count(old) != 1:
    raise SystemExit(f'version anchor count={s.count(old)}')
main.write_text(s.replace(old, '#define ENGINE_VERSION "3.30"', 1), encoding='utf-8')

p = root / 'search.c'
s = p.read_text(encoding='utf-8')
anchor = 'static int qsearch(SearchState *ss, Board *b, int alpha, int beta, int ply) {'
if s.count(anchor) != 1:
    raise SystemExit(f'qsearch anchor count={s.count(anchor)}')
helper = r'''
/* v3.30 experiment: prove pseudo-legal qsearch moves legal BEFORE board_make().
 * Uses post-move occupancy plus enemy bitboards with the captured piece masked.
 * qsearch never needs castling: in-check castling is illegal and normal QS only
 * generates captures/promotions. */
static inline int qmove_legal_precheck(const Board *b, const Move *m) {
    if (m->castle) return 0;
    uint8_t pc = b->b[m->from];
    if (!pc) return 0;
    int us = b->turn;
    int ksq = PC_TYPE(pc) == 6 ? (int)m->to : (us == COL_W ? b->wk : b->bk);
    uint64_t fromb = (uint64_t)1 << m->from;
    uint64_t tob   = (uint64_t)1 << m->to;
    uint64_t occ = (b->occ & ~fromb) | tob;
    uint64_t captured = 0;
    if (m->epc) {
        int csq = us == COL_W ? (int)m->to + 8 : (int)m->to - 8;
        captured = (uint64_t)1 << csq;
        occ &= ~captured;
    } else if (b->b[m->to] && PC_COLOR(b->b[m->to]) != us) {
        captured = tob;
    }
    uint64_t km = (uint64_t)1 << ksq;
    if (us == COL_W) {
        uint64_t bp = b->bb[6]  & ~captured;
        uint64_t bn = b->bb[7]  & ~captured;
        uint64_t bb = b->bb[8]  & ~captured;
        uint64_t br = b->bb[9]  & ~captured;
        uint64_t bq = b->bb[10] & ~captured;
        uint64_t bk = b->bb[11] & ~captured;
        if (wpawn_attacks_bb(km) & bp) return 0;
        if (NATK[ksq] & bn) return 0;
        if (bish_attacks(ksq, occ) & (bb | bq)) return 0;
        if (rook_attacks(ksq, occ) & (br | bq)) return 0;
        if (KATK[ksq] & bk) return 0;
    } else {
        uint64_t wp = b->bb[0] & ~captured;
        uint64_t wn = b->bb[1] & ~captured;
        uint64_t wb = b->bb[2] & ~captured;
        uint64_t wr = b->bb[3] & ~captured;
        uint64_t wq = b->bb[4] & ~captured;
        uint64_t wk = b->bb[5] & ~captured;
        if (bpawn_attacks_bb(km) & wp) return 0;
        if (NATK[ksq] & wn) return 0;
        if (bish_attacks(ksq, occ) & (wb | wq)) return 0;
        if (rook_attacks(ksq, occ) & (wr | wq)) return 0;
        if (KATK[ksq] & wk) return 0;
    }
    return 1;
}

'''
s = s.replace(anchor, helper + anchor, 1)
old1 = '''            board_make(b, &moves[i]);
            int prev_turn = b->turn ^ 24;
            if (board_is_attacked(b, prev_turn==COL_W ? b->wk : b->bk, b->turn)) {
                board_unmake(b); continue;
            }
            legal++;'''
new1 = '''            if (!qmove_legal_precheck(b, &moves[i])) continue;
            board_make(b, &moves[i]);
            legal++;'''
if s.count(old1) != 1:
    raise SystemExit(f'check-evasion legality anchor count={s.count(old1)}')
s = s.replace(old1, new1, 1)
old2 = '''        board_make(b, &moves[i]);
        int mover_col = b->turn ^ 24;
        int king_sq   = mover_col == COL_W ? b->wk : b->bk;
        if (board_is_attacked(b, king_sq, b->turn)) { board_unmake(b); continue; }
        int sc = -qsearch(ss, b, -beta, -alpha, ply+1);'''
new2 = '''        if (!qmove_legal_precheck(b, &moves[i])) continue;
        board_make(b, &moves[i]);
        int sc = -qsearch(ss, b, -beta, -alpha, ply+1);'''
if s.count(old2) != 1:
    raise SystemExit(f'capture legality anchor count={s.count(old2)}')
p.write_text(s.replace(old2, new2, 1), encoding='utf-8')
print('applied v3.30 legality precheck')
