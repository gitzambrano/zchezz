#!/usr/bin/env python3
"""Apply the v3.23 full-accumulator experiment to a copied v3.22 engine tree.

The candidate keeps the exact NNU3 799->256->64->1 architecture and weights.
Only the implementation of the 31 manual features changes:

- HM accumulator remains stacked per ply as in v3.22.
- Manual-feature projection becomes a thread-local incremental accumulator.
- A compact feature state is stacked per ply.
- Ordinary non-pawn/non-king non-captures do zero manual-feature work.
- Pawn structure changes recompute only passed-pawn file masks.
- King moves recompute only king distance.
- Captures/promotions update piece counts/material incrementally.
- nnue_eval_bb() performs no extra-feature scan/hash/cache lookup.

Because feature quantisation and L1 rows are unchanged, the candidate should be
numerically/search-tree identical to v3.22 for the same weights. The workflow
therefore treats tree parity as a hard gate before looking at NPS/Elo.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {n}")
    return text.replace(old, new, 1)


def patch_header(root: Path) -> None:
    p = root / "nnue.h"
    text = p.read_text(encoding="utf-8")

    old = """typedef struct {\n    int16_t  acc_stack_w[NN_ACC_STACK][NN_L1_OUT] __attribute__((aligned(32)));\n"""
    new = """typedef struct {\n    uint8_t  cnt_w[6], cnt_b[6];\n    uint64_t pawns_w, pawns_b;\n    uint8_t  king_w, king_b;\n    uint8_t  passed_w, passed_b, king_dist;\n} NnueExtraState;\n\ntypedef struct {\n    int16_t  acc_stack_w[NN_ACC_STACK][NN_L1_OUT] __attribute__((aligned(32)));\n"""
    text = replace_once(text, old, new, "nnue.h: extra-state type")

    old = """    int8_t   ext_dirty[2];\n    int      acc_dirty;\n"""
    new = """    int8_t   ext_dirty[2];\n\n    /* v3.23 experiment: full incremental manual-feature projection.\n     * ext_acc_w/b always represent the CURRENT ply; ext_state_stack stores\n     * only compact chess state so unmake can apply the inverse projection\n     * delta without copying another 2x256 int16 buffer per ply. */\n    NnueExtraState ext_state_stack[NN_ACC_STACK];\n    uint8_t   ext_changed[NN_ACC_STACK];\n    int16_t   ext_acc_w[NN_L1_OUT]          __attribute__((aligned(32)));\n    int16_t   ext_acc_b[NN_L1_OUT]          __attribute__((aligned(32)));\n\n    int      acc_dirty;\n"""
    text = replace_once(text, old, new, "nnue.h: fullacc fields")
    p.write_text(text, encoding="utf-8")


def patch_source(root: Path, fast_negative_binary: bool) -> None:
    p = root / "nnue.c"
    text = p.read_text(encoding="utf-8")

    # Optional micro-optimisation: a passed-pawn flag turning off produces -256.
    if fast_negative_binary:
        old = """    if (fj_16 == 256) {\n        /* Binary feature: just add row directly, no multiply */\n        for (int o=0; o<NN_L1_OUT; o+=16) {\n            __m256i r = _mm256_load_si256((const __m256i*)(row + o));\n            __m256i v = _mm256_load_si256((const __m256i*)(out + o));\n            _mm256_store_si256((__m256i*)(out + o), _mm256_add_epi16(v, r));\n        }\n    } else {\n"""
        new = """    if (fj_16 == 256) {\n        /* Binary feature on: add the row directly. */\n        for (int o=0; o<NN_L1_OUT; o+=16) {\n            __m256i r = _mm256_load_si256((const __m256i*)(row + o));\n            __m256i v = _mm256_load_si256((const __m256i*)(out + o));\n            _mm256_store_si256((__m256i*)(out + o), _mm256_add_epi16(v, r));\n        }\n    } else if (fj_16 == -256) {\n        /* Binary feature off: subtract the row directly. */\n        for (int o=0; o<NN_L1_OUT; o+=16) {\n            __m256i r = _mm256_load_si256((const __m256i*)(row + o));\n            __m256i v = _mm256_load_si256((const __m256i*)(out + o));\n            _mm256_store_si256((__m256i*)(out + o), _mm256_sub_epi16(v, r));\n        }\n    } else {\n"""
        text = replace_once(text, old, new, "nnue.c: AVX2 -256 fast path")

    marker = """/* ── Rebuild accumulator from scratch (v3.13: per-thread NnueAccum) ── */\n"""
    helper = r'''/* ── v3.23 experiment: full incremental manual-feature state ────────── */
static inline uint8_t _fullacc_passed_w(uint64_t wp, uint64_t bp) {
    uint8_t mask = 0;
    uint64_t tmp = wp;
    while (tmp) {
        int sq = __builtin_ctzll(tmp); tmp &= tmp - 1;
        if (!(_pp_span_w[sq] & bp)) mask |= (uint8_t)(1u << (sq & 7));
    }
    return mask;
}

static inline uint8_t _fullacc_passed_b(uint64_t wp, uint64_t bp) {
    uint8_t mask = 0;
    uint64_t tmp = bp;
    while (tmp) {
        int sq = __builtin_ctzll(tmp); tmp &= tmp - 1;
        if (!(_pp_span_b[sq] & wp)) mask |= (uint8_t)(1u << (sq & 7));
    }
    return mask;
}

static inline uint8_t _fullacc_king_dist(uint8_t wk, uint8_t bk) {
    if (wk >= 64 || bk >= 64) return 0;
    int df = (wk & 7) - (bk & 7); if (df < 0) df = -df;
    int dr = (wk >> 3) - (bk >> 3); if (dr < 0) dr = -dr;
    return (uint8_t)(df > dr ? df : dr);
}

static void _fullacc_state_from_board(NnueExtraState *s, const uint8_t *board) {
    uint64_t bb[12];
    _build_bb_from_board(board, bb);
    if (!_extra_masks_init) _init_extra_masks();
    for (int t = 0; t < 6; ++t) {
        s->cnt_w[t] = (uint8_t)__builtin_popcountll(bb[t]);
        s->cnt_b[t] = (uint8_t)__builtin_popcountll(bb[t + 6]);
    }
    s->pawns_w = bb[0]; s->pawns_b = bb[6];
    s->king_w = bb[5]  ? (uint8_t)__builtin_ctzll(bb[5])  : 255;
    s->king_b = bb[11] ? (uint8_t)__builtin_ctzll(bb[11]) : 255;
    s->passed_w = _fullacc_passed_w(s->pawns_w, s->pawns_b);
    s->passed_b = _fullacc_passed_b(s->pawns_w, s->pawns_b);
    s->king_dist = _fullacc_king_dist(s->king_w, s->king_b);
}

/* Quantise exactly like _project_feat_full: each feature is independently
 * converted by (int16_t)(feature * 256.0f).  We compare quantised parent and
 * child values, not raw floats, so incremental deltas reproduce a full
 * projection modulo the existing int16 accumulator arithmetic. */
static void _fullacc_q(const NnueExtraState *s, int stm, int16_t q[NN_EXTRA]) {
    static const float MC[6] = {8.f,2.f,2.f,2.f,1.f,1.f};
    static const float MV[6] = {1.f,3.f,3.f,5.f,9.f,0.f};
    const uint8_t *own = stm == 0 ? s->cnt_w : s->cnt_b;
    const uint8_t *opp = stm == 0 ? s->cnt_b : s->cnt_w;
    for (int i = 0; i < 6; ++i) {
        q[i]   = (int16_t)(((float)own[i] / MC[i]) * 256.0f);
        q[6+i] = (int16_t)(((float)opp[i] / MC[i]) * 256.0f);
    }
    float mat = 0.f;
    for (int i = 0; i < 6; ++i)
        mat += (float)(s->cnt_w[i] + s->cnt_b[i]) * MV[i];
    q[12] = (int16_t)((mat / 78.f) * 256.0f);
    q[13] = 256;
    uint8_t own_pass = stm == 0 ? s->passed_w : s->passed_b;
    uint8_t opp_pass = stm == 0 ? s->passed_b : s->passed_w;
    for (int i = 0; i < 8; ++i) {
        q[14+i] = (own_pass & (1u << i)) ? 256 : 0;
        q[22+i] = (opp_pass & (1u << i)) ? 256 : 0;
    }
    q[30] = (int16_t)(((float)s->king_dist / 7.f) * 256.0f);
}

static void _fullacc_apply_delta(int16_t *out,
                                 const NnueExtraState *from,
                                 const NnueExtraState *to,
                                 int stm) {
    int16_t a[NN_EXTRA], b[NN_EXTRA];
    _fullacc_q(from, stm, a);
    _fullacc_q(to,   stm, b);
    for (int j = 0; j < NN_EXTRA; ++j) {
        int16_t d = (int16_t)(b[j] - a[j]);
        if (d) _project_feat_add(out, j, d);
    }
}

/* Derive child feature state from the PRE-MOVE mailbox plus compact parent
 * state. Returns 1 iff any of the 31 manual features can have changed. */
static int _fullacc_child_state(NnueExtraState *dst,
                                const NnueExtraState *src,
                                const uint8_t *board,
                                const NNMove *m) {
    *dst = *src;
    int f = m->from_sq, to = m->to_sq;
    uint8_t p = board[f], cap = board[to];
    int pt = piece_type_idx(p);
    if (pt < 0) return 0;

    int pawn_changed = 0, king_changed = 0, changed = 0;
    uint64_t fm = (uint64_t)1 << f, tm = (uint64_t)1 << to;
    int isw = (PC_COLOR(p) == COL_W);

    if (m->castle) {
        if (isw) dst->king_w = (uint8_t)to;
        else     dst->king_b = (uint8_t)to;
        king_changed = changed = 1;
    } else {
        if (pt == 0) {
            uint64_t *pawns = isw ? &dst->pawns_w : &dst->pawns_b;
            *pawns &= ~fm;
            if (!m->prom) *pawns |= tm;
            pawn_changed = changed = 1;
        }
        if (pt == 5) {
            if (isw) dst->king_w = (uint8_t)to;
            else     dst->king_b = (uint8_t)to;
            king_changed = changed = 1;
        }

        if (cap) {
            int cpt = piece_type_idx(cap);
            if (cpt >= 0) {
                uint8_t *cc = (PC_COLOR(cap) == COL_W) ? dst->cnt_w : dst->cnt_b;
                if (cc[cpt]) --cc[cpt];
                if (cpt == 0) {
                    if (PC_COLOR(cap) == COL_W) dst->pawns_w &= ~tm;
                    else                        dst->pawns_b &= ~tm;
                    pawn_changed = 1;
                }
                changed = 1;
            }
        }

        if (m->is_epc) {
            int epsq = isw ? to + 8 : to - 8;
            uint64_t em = (uint64_t)1 << epsq;
            if (isw) {
                if (dst->cnt_b[0]) --dst->cnt_b[0];
                dst->pawns_b &= ~em;
            } else {
                if (dst->cnt_w[0]) --dst->cnt_w[0];
                dst->pawns_w &= ~em;
            }
            pawn_changed = changed = 1;
        }

        if (m->prom) {
            uint8_t *cc = isw ? dst->cnt_w : dst->cnt_b;
            if (cc[0]) --cc[0];
            int npt = (int)m->prom - 1;  /* prom: N=2 B=3 R=4 Q=5 */
            if ((unsigned)npt < 5u) ++cc[npt];
            changed = 1;
        }
    }

    if (pawn_changed) {
        dst->passed_w = _fullacc_passed_w(dst->pawns_w, dst->pawns_b);
        dst->passed_b = _fullacc_passed_b(dst->pawns_w, dst->pawns_b);
    }
    if (king_changed)
        dst->king_dist = _fullacc_king_dist(dst->king_w, dst->king_b);
    return changed;
}

'''
    if marker not in text:
        raise SystemExit("nnue.c: rebuild marker missing")
    text = text.replace(marker, helper + marker, 1)

    old = """    /* Seed extra-feature arrays in NnueAccum for both stm directions */\n    for (int stm=0; stm<2; stm++) {\n        _compute_extra_feat(na->ext_feat[stm], board, stm);\n        memset(na->ext_buf[stm], 0, NN_L1_OUT*sizeof(int16_t));\n        _project_feat_full(na->ext_buf[stm], na->ext_feat[stm]);\n        na->ext_dirty[stm] = 0;\n    }\n}\n"""
    new = """    /* Seed legacy extra buffers plus the v3.23 full accumulator. */\n    for (int stm=0; stm<2; stm++) {\n        _compute_extra_feat(na->ext_feat[stm], board, stm);\n        memset(na->ext_buf[stm], 0, NN_L1_OUT*sizeof(int16_t));\n        _project_feat_full(na->ext_buf[stm], na->ext_feat[stm]);\n        na->ext_dirty[stm] = 0;\n    }\n    _fullacc_state_from_board(&na->ext_state_stack[0], board);\n    memcpy(na->ext_acc_w, na->ext_buf[0], NN_L1_OUT*sizeof(int16_t));\n    memcpy(na->ext_acc_b, na->ext_buf[1], NN_L1_OUT*sizeof(int16_t));\n    memset(na->ext_changed, 0, sizeof(na->ext_changed));\n}\n"""
    text = replace_once(text, old, new, "nnue.c: rebuild seed")

    old = """    na->acc_ptr = dst;\n    na->ext_dirty[0] = 1;\n    na->ext_dirty[1] = 1;\n}\n\nvoid nnue_pop_na(NnueAccum *na) { if (na->acc_ptr > 0) na->acc_ptr--; }\n"""
    new = """    int extchg = _fullacc_child_state(&na->ext_state_stack[dst],\n                                             &na->ext_state_stack[src], board, m);\n    na->ext_changed[dst] = (uint8_t)extchg;\n    if (extchg) {\n        _fullacc_apply_delta(na->ext_acc_w, &na->ext_state_stack[src], &na->ext_state_stack[dst], 0);\n        _fullacc_apply_delta(na->ext_acc_b, &na->ext_state_stack[src], &na->ext_state_stack[dst], 1);\n    }\n    na->acc_ptr = dst;\n    na->ext_dirty[0] = 1;\n    na->ext_dirty[1] = 1;\n}\n\nvoid nnue_pop_na(NnueAccum *na) {\n    int cur = na->acc_ptr;\n    if (cur <= 0) return;\n    if (na->ext_changed[cur]) {\n        _fullacc_apply_delta(na->ext_acc_w, &na->ext_state_stack[cur], &na->ext_state_stack[cur-1], 0);\n        _fullacc_apply_delta(na->ext_acc_b, &na->ext_state_stack[cur], &na->ext_state_stack[cur-1], 1);\n    }\n    na->acc_ptr = cur - 1;\n}\n"""
    text = replace_once(text, old, new, "nnue.c: push/pop fullacc")

    old = """    ExtraState322 es; _extra_state322(&es, bb);\n    uint64_t key=_extra_key322(&es);\n    uint32_t aux=(uint32_t)es.pw | ((uint32_t)es.pb<<8) | ((uint32_t)es.kd<<16) | ((uint32_t)stm<<20);\n    int slot=(int)((key ^ ((uint64_t)aux*0x9e3779b97f4a7c15ULL)) & (EXT_CACHE_SLOTS-1));\n    const int16_t *ext;\n    if (na->cache_key[slot] != key || na->cache_aux[slot] != aux) {\n        float feat[NN_EXTRA]; _extra_feat322(feat,&es,stm);\n        int16_t *buf=na->cache_buf[slot]; _project_feat_full(buf,feat);\n        na->cache_key[slot]=key; na->cache_aux[slot]=aux; ext=buf;\n    } else ext=na->cache_buf[slot];\n\n    /* Read HM accumulator from per-thread stack (v3.14) */\n"""
    new = """    /* v3.23 full accumulator: all manual-feature work happened in push/pop.\n     * Search eval is now a pair of aligned accumulator loads; board/bb/hash are\n     * intentionally unused here. */\n    (void)board; (void)bb; (void)board_hash;\n    const int16_t *ext = stm==0 ? na->ext_acc_w : na->ext_acc_b;\n\n    /* Read HM accumulator from per-thread stack (v3.14) */\n"""
    text = replace_once(text, old, new, "nnue.c: eval_bb cache removal")

    old = """    memset(na->cache_key, 0, sizeof(na->cache_key));\n    memset(na->cache_aux, 0, sizeof(na->cache_aux));\n"""
    new = """    memset(na->cache_key, 0, sizeof(na->cache_key));\n    memset(na->cache_aux, 0, sizeof(na->cache_aux));\n    memset(na->ext_changed, 0, sizeof(na->ext_changed));\n"""
    text = replace_once(text, old, new, "nnue.c: reset changed flags")

    p.write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("variant", choices=("fullacc31", "fullacc31_pm256"))
    ap.add_argument("--root", type=Path, required=True)
    args = ap.parse_args()
    patch_header(args.root)
    patch_source(args.root, fast_negative_binary=args.variant == "fullacc31_pm256")
    print(f"applied {args.variant} to {args.root}")


if __name__ == "__main__":
    main()
