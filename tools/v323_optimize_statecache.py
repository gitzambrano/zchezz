#!/usr/bin/env python3
"""Turn sparse-undo fullacc into an incremental-state / lazy-projection cache.

The compact state (counts, pawn bitboards, passed-file masks, king squares and
king distance) remains incrementally maintained through make/unmake. The costly
256-wide projection is NOT touched during make/unmake. nnue_eval_bb hashes the
already-maintained compact state into the existing 16-slot projection cache.

This isolates the remaining question: is maintaining the *semantic* extra
state incrementally cheaper than recomputing it from 12 board bitboards at
every eval, while retaining v3.22's very effective projection cache?
"""
from __future__ import annotations
import argparse
from pathlib import Path


def one(t,old,new,label):
    n=t.count(old)
    if n!=1: raise SystemExit(f'{label}: expected 1 match, found {n}')
    return t.replace(old,new,1)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); a=ap.parse_args()
    p=a.root/'nnue.c'; t=p.read_text(encoding='utf-8')

    old='''            na->ext_undo[dst]=na->ext_state;
            _sparse_apply_delta(na,&na->ext_state,&child);
            na->ext_state=child;
            na->ext_changed[dst]=1;
'''
    new='''            na->ext_undo[dst]=na->ext_state;
            na->ext_state=child;
            na->ext_changed[dst]=1;
'''
    t=one(t,old,new,'remove make projection')

    old='''    if (na->ext_changed[cur]) {
        const NnueExtraState *parent=&na->ext_undo[cur];
        _sparse_apply_delta(na,&na->ext_state,parent);
        na->ext_state=*parent;
    }
'''
    new='''    if (na->ext_changed[cur]) {
        const NnueExtraState *parent=&na->ext_undo[cur];
        na->ext_state=*parent;
    }
'''
    t=one(t,old,new,'remove unmake projection')

    # Insert compact-state feature conversion/key helpers before eval_bb.
    marker='''int nnue_eval_bb(NnueAccum *na, int stm, const uint8_t *board,
                 const uint64_t bb[12], uint64_t board_hash)
'''
    helper=r'''static inline uint64_t _statecache_key(const NnueExtraState *s) {
    uint64_t k=0; int sh=0;
    for(int i=0;i<6;i++,sh+=5) k|=((uint64_t)(s->cnt_w[i]&31))<<sh;
    for(int i=0;i<6;i++,sh+=5) k|=((uint64_t)(s->cnt_b[i]&31))<<sh;
    return k;
}

static void _statecache_feat(float *f,const NnueExtraState *s,int stm) {
    static const float MC[6]={8.f,2.f,2.f,2.f,1.f,1.f};
    static const float MV[6]={1.f,3.f,3.f,5.f,9.f,0.f};
    const uint8_t *own=stm==0?s->cnt_w:s->cnt_b;
    const uint8_t *opp=stm==0?s->cnt_b:s->cnt_w;
    for(int i=0;i<6;i++){f[i]=(float)own[i]/MC[i]; f[6+i]=(float)opp[i]/MC[i];}
    float mat=0.f; for(int i=0;i<6;i++) mat+=(float)(s->cnt_w[i]+s->cnt_b[i])*MV[i];
    f[12]=mat/78.f; f[13]=1.f;
    uint8_t opass=stm==0?s->passed_w:s->passed_b;
    uint8_t xpass=stm==0?s->passed_b:s->passed_w;
    for(int i=0;i<8;i++){f[14+i]=(opass>>i)&1; f[22+i]=(xpass>>i)&1;}
    f[30]=(float)s->king_dist/7.f;
}

'''
    t=one(t,marker,helper+marker,'insert statecache helpers')

    old='''    /* v3.23 full accumulator: all manual-feature work happened in push/pop.
     * Search eval is now a pair of aligned accumulator loads; board/bb/hash are
     * intentionally unused here. */
    (void)board; (void)bb; (void)board_hash;
    const int16_t *ext = stm==0 ? na->ext_acc_w : na->ext_acc_b;

    /* Read HM accumulator from per-thread stack (v3.14) */
'''
    new='''    /* Lazy projection: semantic extra state is already current, so eval
     * only packs its exact cache key. On a hit there is no feature scan and no
     * 31x256 projection; on a miss we project from the compact state. */
    (void)board; (void)bb; (void)board_hash;
    const NnueExtraState *es=&na->ext_state;
    uint64_t key=_statecache_key(es);
    uint32_t aux=(uint32_t)es->passed_w | ((uint32_t)es->passed_b<<8)
               | ((uint32_t)es->king_dist<<16) | ((uint32_t)stm<<20);
    int slot=(int)((key ^ ((uint64_t)aux*0x9e3779b97f4a7c15ULL)) & (EXT_CACHE_SLOTS-1));
    const int16_t *ext;
    if (na->cache_key[slot] != key || na->cache_aux[slot] != aux) {
        float feat[NN_EXTRA];
        _statecache_feat(feat,es,stm);
        int16_t *buf=na->cache_buf[slot];
        _project_feat_full(buf,feat);
        na->cache_key[slot]=key; na->cache_aux[slot]=aux; ext=buf;
    } else ext=na->cache_buf[slot];

    /* Read HM accumulator from per-thread stack (v3.14) */
'''
    t=one(t,old,new,'restore lazy cached projection')
    p.write_text(t,encoding='utf-8')
    print('applied incremental-state lazy projection cache')

if __name__=='__main__': main()
