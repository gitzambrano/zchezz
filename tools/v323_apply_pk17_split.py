#!/usr/bin/env python3
"""Apply the v3.23 PK17 split-accumulator experiment to a copied v3.22 tree.

The 31 manual features are NOT removed. They are split by update frequency:

  features  0..13: piece counts, material phase, constant
                   -> lazy 16-slot cache keyed only by counts + stm
  features 14..30: 8 own passed-pawn files, 8 opponent passed-pawn files,
                   king distance
                   -> exact incremental full accumulator (PK17)

The candidate uses the existing NNU3 weights unchanged. Therefore search score,
best move and node tree must be bit-for-bit identical to v3.22. This makes NPS
a clean architecture measurement without retraining noise.
"""
from __future__ import annotations
import argparse
from pathlib import Path


def one(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {n}")
    return text.replace(old, new, 1)


def patch_header(root: Path) -> None:
    p = root / "nnue.h"
    t = p.read_text(encoding="utf-8")
    old = """typedef struct {\n    int16_t  acc_stack_w[NN_ACC_STACK][NN_L1_OUT] __attribute__((aligned(32)));\n"""
    new = """typedef struct {\n    uint64_t pawns_w, pawns_b;\n    uint8_t  king_w, king_b;\n    uint8_t  passed_w, passed_b, king_dist;\n} NnuePk17State;\n\ntypedef struct {\n    int16_t  acc_stack_w[NN_ACC_STACK][NN_L1_OUT] __attribute__((aligned(32)));\n"""
    t = one(t, old, new, "nnue.h pk17 state")

    old = """    float    ext_feat[2][NN_EXTRA];\n    int8_t   ext_dirty[2];\n    int      acc_dirty;\n"""
    new = """    float    ext_feat[2][NN_EXTRA];\n    int8_t   ext_dirty[2];\n\n    /* v3.23 PK17 experiment. Passed-pawn files + king distance are kept\n     * incrementally in their own first-layer accumulator. Undo state is only\n     * written on moves that can change PK17, so ordinary quiet piece moves\n     * pay essentially no extra-feature cost. */\n    NnuePk17State pk17_state;\n    NnuePk17State pk17_undo[NN_ACC_STACK];\n    uint8_t  pk17_changed[NN_ACC_STACK];\n    int16_t  pk17_acc_w[NN_L1_OUT] __attribute__((aligned(32)));\n    int16_t  pk17_acc_b[NN_L1_OUT] __attribute__((aligned(32)));\n\n    int      acc_dirty;\n"""
    t = one(t, old, new, "nnue.h pk17 fields")
    p.write_text(t, encoding="utf-8")


def patch_source(root: Path) -> None:
    p = root / "nnue.c"
    t = p.read_text(encoding="utf-8")

    # Reset per-search PK17 undo flags as well as the count cache.
    old = """    memset(na->cache_key, 0, sizeof(na->cache_key));\n    memset(na->cache_aux, 0, sizeof(na->cache_aux));\n"""
    new = """    memset(na->cache_key, 0, sizeof(na->cache_key));\n    memset(na->cache_aux, 0, sizeof(na->cache_aux));\n    memset(na->pk17_changed, 0, sizeof(na->pk17_changed));\n"""
    t = one(t, old, new, "nnue.c reset pk17")

    marker = """/* Incremental update: given old_feat[] stored in parent slot and new_feat[]\n"""
    helper = r'''/* ── v3.23 PK17 split accumulator ─────────────────────────────────── */
static inline uint8_t _pk17_passed_w(uint64_t wp, uint64_t bp) {
    uint8_t m=0; uint64_t x=wp;
    while(x){int q=__builtin_ctzll(x);x&=x-1;if(!(_pp_span_w[q]&bp))m|=(uint8_t)(1u<<(q&7));}
    return m;
}
static inline uint8_t _pk17_passed_b(uint64_t wp, uint64_t bp) {
    uint8_t m=0; uint64_t x=bp;
    while(x){int q=__builtin_ctzll(x);x&=x-1;if(!(_pp_span_b[q]&wp))m|=(uint8_t)(1u<<(q&7));}
    return m;
}
static inline uint8_t _pk17_kd(uint8_t wk,uint8_t bk) {
    if(wk>=64||bk>=64)return 0;
    int df=(wk&7)-(bk&7);if(df<0)df=-df;
    int dr=(wk>>3)-(bk>>3);if(dr<0)dr=-dr;
    return (uint8_t)(df>dr?df:dr);
}
static void _pk17_from_board(NnuePk17State *s,const uint8_t *board) {
    if(!_extra_masks_init)_init_extra_masks();
    s->pawns_w=s->pawns_b=0; s->king_w=s->king_b=255;
    for(int q=0;q<64;q++){
        uint8_t p=board[q]; if(!p)continue;
        int pt=piece_type_idx(p); if(pt<0)continue;
        if(pt==0){if(PC_COLOR(p)==COL_W)s->pawns_w|=1ULL<<q;else s->pawns_b|=1ULL<<q;}
        else if(pt==5){if(PC_COLOR(p)==COL_W)s->king_w=(uint8_t)q;else s->king_b=(uint8_t)q;}
    }
    s->passed_w=_pk17_passed_w(s->pawns_w,s->pawns_b);
    s->passed_b=_pk17_passed_b(s->pawns_w,s->pawns_b);
    s->king_dist=_pk17_kd(s->king_w,s->king_b);
}

/* Exact contribution transition. Fractional king-distance projection in the
 * existing NNU3 path uses int16 mullo before >>8, so contribution(new)-
 * contribution(old) must be formed explicitly; projecting q_new-q_old is not
 * numerically equivalent. */
static inline void _pk17_transition(int16_t *out,int j,int16_t qo16,int16_t qn16) {
    const int16_t *row=_nnL1WT+(NN_HM_IN+j)*NN_L1_OUT;
#ifdef __AVX2__
    __m256i qo=_mm256_set1_epi16(qo16),qn=_mm256_set1_epi16(qn16),z=_mm256_setzero_si256();
    for(int o=0;o<NN_L1_OUT;o+=16){
        __m256i r=_mm256_load_si256((const __m256i*)(row+o));
        __m256i co=qo16==0?z:(qo16==256?r:_mm256_srai_epi16(_mm256_mullo_epi16(qo,r),8));
        __m256i cn=qn16==0?z:(qn16==256?r:_mm256_srai_epi16(_mm256_mullo_epi16(qn,r),8));
        __m256i v=_mm256_load_si256((const __m256i*)(out+o));
        _mm256_store_si256((__m256i*)(out+o),_mm256_add_epi16(v,_mm256_sub_epi16(cn,co)));
    }
#elif defined(__wasm_simd128__)
    v128_t qo=wasm_i16x8_splat(qo16),qn=wasm_i16x8_splat(qn16),z=wasm_i16x8_splat(0);
    for(int o=0;o<NN_L1_OUT;o+=8){
        v128_t r=wasm_v128_load(row+o);
        v128_t co=qo16==0?z:(qo16==256?r:wasm_i16x8_shr(wasm_i16x8_mul(qo,r),8));
        v128_t cn=qn16==0?z:(qn16==256?r:wasm_i16x8_shr(wasm_i16x8_mul(qn,r),8));
        v128_t v=wasm_v128_load(out+o);
        wasm_v128_store(out+o,wasm_i16x8_add(v,wasm_i16x8_sub(cn,co)));
    }
#else
    for(int o=0;o<NN_L1_OUT;o++){
        int16_t co=qo16==0?0:(qo16==256?row[o]:(int16_t)(((int32_t)qo16*row[o])>>8));
        int16_t cn=qn16==0?0:(qn16==256?row[o]:(int16_t)(((int32_t)qn16*row[o])>>8));
        out[o]=(int16_t)(out[o]+(int16_t)(cn-co));
    }
#endif
}

static void _pk17_apply(int16_t *aw,int16_t *ab,const NnuePk17State *a,const NnuePk17State *b) {
    uint8_t d=(uint8_t)(a->passed_w^b->passed_w);
    while(d){int f=__builtin_ctz((unsigned)d);d=(uint8_t)(d&(d-1));int16_t qo=(a->passed_w>>f&1)?256:0,qn=(b->passed_w>>f&1)?256:0;
        _pk17_transition(aw,14+f,qo,qn); _pk17_transition(ab,22+f,qo,qn);}
    d=(uint8_t)(a->passed_b^b->passed_b);
    while(d){int f=__builtin_ctz((unsigned)d);d=(uint8_t)(d&(d-1));int16_t qo=(a->passed_b>>f&1)?256:0,qn=(b->passed_b>>f&1)?256:0;
        _pk17_transition(aw,22+f,qo,qn); _pk17_transition(ab,14+f,qo,qn);}
    if(a->king_dist!=b->king_dist){
        int16_t qo=(int16_t)(((float)a->king_dist/7.f)*256.f);
        int16_t qn=(int16_t)(((float)b->king_dist/7.f)*256.f);
        _pk17_transition(aw,30,qo,qn); _pk17_transition(ab,30,qo,qn);
    }
}

static void _pk17_project_full(int16_t *out,const NnuePk17State *s,int stm) {
    memset(out,0,NN_L1_OUT*sizeof(int16_t));
    uint8_t own=stm==0?s->passed_w:s->passed_b,opp=stm==0?s->passed_b:s->passed_w;
    for(int f=0;f<8;f++)if(own&(1u<<f))_project_feat_add(out,14+f,256);
    for(int f=0;f<8;f++)if(opp&(1u<<f))_project_feat_add(out,22+f,256);
    int16_t q=(int16_t)(((float)s->king_dist/7.f)*256.f);
    if(q)_project_feat_add(out,30,q);
}

/* Derive child PK state from the pre-move mailbox. Only pawn/king changes,
 * pawn captures/EP/promotions, and the deliberately-supported captured-king
 * stress case can alter PK17. */
static int _pk17_child(NnuePk17State *dst,const NnuePk17State *src,const uint8_t *board,const NNMove *m) {
    *dst=*src;
    int f=m->from_sq,to=m->to_sq; uint8_t p=board[f],cap=board[to]; int pt=piece_type_idx(p);
    if(pt<0)return 0; int isw=PC_COLOR(p)==COL_W,pawnchg=0,kingchg=0;
    uint64_t fm=1ULL<<f,tm=1ULL<<to;
    if(m->castle){if(isw)dst->king_w=(uint8_t)to;else dst->king_b=(uint8_t)to;kingchg=1;}
    else {
        if(pt==0){uint64_t *pp=isw?&dst->pawns_w:&dst->pawns_b;*pp&=~fm;if(!m->prom)*pp|=tm;pawnchg=1;}
        if(pt==5){if(isw)dst->king_w=(uint8_t)to;else dst->king_b=(uint8_t)to;kingchg=1;}
        if(cap){int ct=piece_type_idx(cap);if(ct==0){if(PC_COLOR(cap)==COL_W)dst->pawns_w&=~tm;else dst->pawns_b&=~tm;pawnchg=1;}
            else if(ct==5){if(PC_COLOR(cap)==COL_W)dst->king_w=255;else dst->king_b=255;kingchg=1;}}
        if(m->is_epc){int e=isw?to+8:to-8;uint64_t em=1ULL<<e;if(isw)dst->pawns_b&=~em;else dst->pawns_w&=~em;pawnchg=1;}
    }
    if(pawnchg){dst->passed_w=_pk17_passed_w(dst->pawns_w,dst->pawns_b);dst->passed_b=_pk17_passed_b(dst->pawns_w,dst->pawns_b);}
    if(kingchg)dst->king_dist=_pk17_kd(dst->king_w,dst->king_b);
    return pawnchg||kingchg;
}

/* The remaining 14 manual features depend only on piece counts + stm. Their
 * projected contribution is cached separately; passed-pawn and king work is
 * intentionally absent from the eval path. */
static inline uint64_t _count14_key(const int cw[6],const int cb[6]) {
    uint64_t k=0;int sh=0;for(int i=0;i<6;i++,sh+=5)k|=((uint64_t)(cw[i]&31))<<sh;
    for(int i=0;i<6;i++,sh+=5)k|=((uint64_t)(cb[i]&31))<<sh;return k;
}
static void _count14_project(int16_t *out,const int cw[6],const int cb[6],int stm) {
    static const float MC[6]={8.f,2.f,2.f,2.f,1.f,1.f},MV[6]={1.f,3.f,3.f,5.f,9.f,0.f};
    memset(out,0,NN_L1_OUT*sizeof(int16_t)); const int *own=stm==0?cw:cb,*opp=stm==0?cb:cw;
    for(int i=0;i<6;i++){int16_t q=(int16_t)(((float)own[i]/MC[i])*256.f);if(q)_project_feat_add(out,i,q);}
    for(int i=0;i<6;i++){int16_t q=(int16_t)(((float)opp[i]/MC[i])*256.f);if(q)_project_feat_add(out,6+i,q);}
    float mat=0.f;for(int i=0;i<6;i++)mat+=(float)(cw[i]+cb[i])*MV[i];
    int16_t mq=(int16_t)((mat/78.f)*256.f);if(mq)_project_feat_add(out,12,mq);
    _project_feat_add(out,13,256);
}

'''
    if marker not in t:
        raise SystemExit("nnue.c helper marker missing")
    t = t.replace(marker, helper + marker, 1)

    # Seed PK17 state/accumulators at every full HM rebuild.
    old = """    for (int stm=0; stm<2; stm++) {\n        _compute_extra_feat(na->ext_feat[stm], board, stm);\n        memset(na->ext_buf[stm], 0, NN_L1_OUT*sizeof(int16_t));\n        _project_feat_full(na->ext_buf[stm], na->ext_feat[stm]);\n        na->ext_dirty[stm] = 0;\n    }\n}\n"""
    new = """    for (int stm=0; stm<2; stm++) {\n        _compute_extra_feat(na->ext_feat[stm], board, stm);\n        memset(na->ext_buf[stm], 0, NN_L1_OUT*sizeof(int16_t));\n        _project_feat_full(na->ext_buf[stm], na->ext_feat[stm]);\n        na->ext_dirty[stm] = 0;\n    }\n    _pk17_from_board(&na->pk17_state,board);\n    _pk17_project_full(na->pk17_acc_w,&na->pk17_state,0);\n    _pk17_project_full(na->pk17_acc_b,&na->pk17_state,1);\n    memset(na->pk17_changed,0,sizeof(na->pk17_changed));\n}\n"""
    t = one(t, old, new, "nnue.c rebuild pk17 seed")

    # Sparse PK17 make: common piece quiets write only a zero changed flag.
    old = """    na->acc_ptr = dst;\n    na->ext_dirty[0] = 1;\n    na->ext_dirty[1] = 1;\n}\n\nvoid nnue_pop_na(NnueAccum *na) { if (na->acc_ptr > 0) na->acc_ptr--; }\n"""
    new = """    NnuePk17State child;\n    int pkchg=_pk17_child(&child,&na->pk17_state,board,m);\n    na->pk17_changed[dst]=(uint8_t)pkchg;\n    if(pkchg){\n        na->pk17_undo[dst]=na->pk17_state;\n        _pk17_apply(na->pk17_acc_w,na->pk17_acc_b,&na->pk17_state,&child);\n        na->pk17_state=child;\n    }\n    na->acc_ptr = dst;\n    na->ext_dirty[0] = 1;\n    na->ext_dirty[1] = 1;\n}\n\nvoid nnue_pop_na(NnueAccum *na) {\n    int cur=na->acc_ptr;if(cur<=0)return;\n    if(na->pk17_changed[cur]){\n        const NnuePk17State *parent=&na->pk17_undo[cur];\n        _pk17_apply(na->pk17_acc_w,na->pk17_acc_b,&na->pk17_state,parent);\n        na->pk17_state=*parent;\n    }\n    na->acc_ptr=cur-1;\n}\n"""
    t = one(t, old, new, "nnue.c push pop pk17")

    # Replace the full 31-feature state/cache in search eval with count14-only
    # cache. PK17 comes from the exact incremental accumulator.
    old = """    ExtraState322 es; _extra_state322(&es, bb);\n    uint64_t key=_extra_key322(&es);\n    uint32_t aux=(uint32_t)es.pw | ((uint32_t)es.pb<<8) | ((uint32_t)es.kd<<16) | ((uint32_t)stm<<20);\n    int slot=(int)((key ^ ((uint64_t)aux*0x9e3779b97f4a7c15ULL)) & (EXT_CACHE_SLOTS-1));\n    const int16_t *ext;\n    if (na->cache_key[slot] != key || na->cache_aux[slot] != aux) {\n        float feat[NN_EXTRA]; _extra_feat322(feat,&es,stm);\n        int16_t *buf=na->cache_buf[slot]; _project_feat_full(buf,feat);\n        na->cache_key[slot]=key; na->cache_aux[slot]=aux; ext=buf;\n    } else ext=na->cache_buf[slot];\n\n    /* Read HM accumulator from per-thread stack (v3.14) */\n"""
    new = """    int cw[6],cb[6];\n    for(int i=0;i<6;i++){cw[i]=__builtin_popcountll(bb[i]);cb[i]=__builtin_popcountll(bb[i+6]);}\n    uint64_t key=_count14_key(cw,cb);\n    uint32_t aux=0x80000000u | (uint32_t)stm; /* nonzero sentinel after reset */\n    int slot=(int)((key ^ ((uint64_t)aux*0x9e3779b97f4a7c15ULL)) & (EXT_CACHE_SLOTS-1));\n    const int16_t *ext;\n    if(na->cache_key[slot]!=key || na->cache_aux[slot]!=aux){\n        int16_t *buf=na->cache_buf[slot];_count14_project(buf,cw,cb,stm);\n        na->cache_key[slot]=key;na->cache_aux[slot]=aux;ext=buf;\n    } else ext=na->cache_buf[slot];\n    const int16_t *pk=stm==0?na->pk17_acc_w:na->pk17_acc_b;\n    (void)board;(void)board_hash;\n\n    /* Read HM accumulator from per-thread stack (v3.14) */\n"""
    t = one(t, old, new, "nnue.c eval count14 cache")

    # Preserve exact int16 ext arithmetic: combine count14 + PK17 with wrapping
    # 16-bit addition before sign-extension, exactly as the monolithic ext buf.
    old = """            __m128i e_lo = _mm_load_si128((const __m128i*)(ext + o));\n            __m128i e_hi = _mm_load_si128((const __m128i*)(ext + o + 8));\n            __m256i s_lo = _mm256_add_epi32(_mm256_cvtepi16_epi32(a_lo), _mm256_cvtepi16_epi32(e_lo));\n            __m256i s_hi = _mm256_add_epi32(_mm256_cvtepi16_epi32(a_hi), _mm256_cvtepi16_epi32(e_hi));\n"""
    new = """            __m128i e_lo = _mm_add_epi16(_mm_load_si128((const __m128i*)(ext + o)),\n                                           _mm_load_si128((const __m128i*)(pk + o)));\n            __m128i e_hi = _mm_add_epi16(_mm_load_si128((const __m128i*)(ext + o + 8)),\n                                           _mm_load_si128((const __m128i*)(pk + o + 8)));\n            __m256i s_lo = _mm256_add_epi32(_mm256_cvtepi16_epi32(a_lo), _mm256_cvtepi16_epi32(e_lo));\n            __m256i s_hi = _mm256_add_epi32(_mm256_cvtepi16_epi32(a_hi), _mm256_cvtepi16_epi32(e_hi));\n"""
    t = one(t, old, new, "nnue.c avx split sum")

    old = """        int32_t v = (int32_t)acc[o] + (int32_t)ext[o] + _nnL1B[o];\n"""
    new = """        int16_t ex=(int16_t)(ext[o]+pk[o]);\n        int32_t v = (int32_t)acc[o] + (int32_t)ex + _nnL1B[o];\n"""
    t = one(t, old, new, "nnue.c scalar split sum")

    p.write_text(t, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    a = ap.parse_args()
    patch_header(a.root)
    patch_source(a.root)
    print(f"applied PK17 split accumulator to {a.root}")


if __name__ == "__main__":
    main()
