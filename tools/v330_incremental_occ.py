#!/usr/bin/env python3
from pathlib import Path

root=Path('engine/c/zchezz_v323')
main=root/'main.c'; s=main.read_text(encoding='utf-8')
old='#define ENGINE_VERSION "3.23"'
if s.count(old)!=1: raise SystemExit(f'version anchor count={s.count(old)}')
main.write_text(s.replace(old,'#define ENGINE_VERSION "3.30"',1),encoding='utf-8')

p=root/'board.c'; s=p.read_text(encoding='utf-8')
old='''static inline void uf_bb_clr(Board *b, UndoFrame *uf, int bi, int sq) {
    if ((unsigned)bi >= 12u) return;  /* SMP guard: P2BI[0]=-1 from corrupt TT move */
    int was = !!(b->bb[bi] & ((uint64_t)1<<sq));
    uf_bb_record(uf, bi, sq, was);
    b->bb[bi] &= ~((uint64_t)1<<sq);
}
static inline void uf_bb_set(Board *b, UndoFrame *uf, int bi, int sq) {
    if ((unsigned)bi >= 12u) return;  /* SMP guard */
    int was = !!(b->bb[bi] & ((uint64_t)1<<sq));
    uf_bb_record(uf, bi, sq, was);
    b->bb[bi] |= ((uint64_t)1<<sq);
}'''
new='''static inline void uf_bb_clr(Board *b, UndoFrame *uf, int bi, int sq) {
    if ((unsigned)bi >= 12u) return;  /* SMP guard: P2BI[0]=-1 from corrupt TT move */
    uint64_t bit = (uint64_t)1 << sq;
    int was = !!(b->bb[bi] & bit);
    uf_bb_record(uf, bi, sq, was);
    b->bb[bi] &= ~bit;
    if (was) {
        b->occ &= ~bit;
        if (bi < 6) b->occ_w &= ~bit;
        else        b->occ_b &= ~bit;
    }
}
static inline void uf_bb_set(Board *b, UndoFrame *uf, int bi, int sq) {
    if ((unsigned)bi >= 12u) return;  /* SMP guard */
    uint64_t bit = (uint64_t)1 << sq;
    int was = !!(b->bb[bi] & bit);
    uf_bb_record(uf, bi, sq, was);
    b->bb[bi] |= bit;
    if (!was) {
        b->occ |= bit;
        if (bi < 6) b->occ_w |= bit;
        else        b->occ_b |= bit;
    }
}'''
if s.count(old)!=1: raise SystemExit(f'bb helper anchor count={s.count(old)}')
s=s.replace(old,new,1)
old='''    /* Incremental occupancy update (Phase 4 v212B):
     * Instead of rebuilding from 12 ORs, compute occ from the old saved value.
     * The bb[] array has already been updated, so we can derive occ cheaply
     * by XOR-ing the from/to/capture bits. But it's even safer and simpler
     * to just compute from the 6 bb per side (only 5+5 ORs vs 12). */
    b->occ_w = b->bb[0]|b->bb[1]|b->bb[2]|b->bb[3]|b->bb[4]|b->bb[5];
    b->occ_b = b->bb[6]|b->bb[7]|b->bb[8]|b->bb[9]|b->bb[10]|b->bb[11];
    b->occ   = b->occ_w | b->occ_b;'''
new='''    /* v3.30: occupancy was maintained by uf_bb_clr/set above.
     * board_unmake restores uf->occ/occ_w/occ_b directly. */'''
if s.count(old)!=1: raise SystemExit(f'occupancy rebuild anchor count={s.count(old)}')
p.write_text(s.replace(old,new,1),encoding='utf-8')
print('applied v3.30 true incremental occupancy')
