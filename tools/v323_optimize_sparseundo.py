#!/usr/bin/env python3
"""Optimise the v3.23 full accumulator after the exactness patches.

The first C31 implementation was exact but ~16% slower because it copied a
compact state on every make and projected generic 31-feature deltas on every
relevant make *and* unmake. This patch keeps one live compact state plus an
undo stack and specialises projection updates by feature class.

Fast path for ordinary non-capture N/B/R/Q moves:
  - one piece-type/capture check
  - ext_changed[ply] = 0
  - no compact-state copy
  - no passed-pawn scan
  - no projection work

Relevant moves (pawn, king, capture, promotion, castle) copy only the compact
state once, then update only changed feature rows: piece-count/material,
passed-pawn file bits, and king distance. Unmake restores from the undo slot.
"""
from __future__ import annotations
import argparse
from pathlib import Path


def one(t: str, old: str, new: str, label: str) -> str:
    n=t.count(old)
    if n!=1:
        raise SystemExit(f'{label}: expected 1 match, found {n}')
    return t.replace(old,new,1)


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); a=ap.parse_args()
    hp=a.root/'nnue.h'; h=hp.read_text(encoding='utf-8')
    h=one(h,
'''    NnueExtraState ext_state_stack[NN_ACC_STACK];
    uint8_t   ext_changed[NN_ACC_STACK];
''',
'''    /* Sparse-undo fullacc: current compact state is unique. Ordinary
     * quiet piece moves do not copy it; relevant moves save one parent state
     * in ext_undo[ply] for exact inverse restoration. */
    NnueExtraState ext_state;
    NnueExtraState ext_undo[NN_ACC_STACK];
    uint8_t   ext_changed[NN_ACC_STACK];
''','header sparse state')
    hp.write_text(h,encoding='utf-8')

    cp=a.root/'nnue.c'; t=cp.read_text(encoding='utf-8')

    marker='''/* Derive child feature state from the PRE-MOVE mailbox plus compact parent
 * state. Returns 1 iff any of the 31 manual features can have changed. */
'''
    helper=r'''/* Specialised exact transition used by sparse-undo fullacc.  Unlike the
 * generic C31 transition, this never builds two q[31] arrays and never scans
 * unchanged feature columns. */
static inline int16_t _sparse_count_q(uint8_t n, int pt) {
    static const float MC[6] = {8.f,2.f,2.f,2.f,1.f,1.f};
    return (int16_t)(((float)n / MC[pt]) * 256.0f);
}

static inline int16_t _sparse_material_q(const NnueExtraState *s) {
    static const float MV[6] = {1.f,3.f,3.f,5.f,9.f,0.f};
    float mat=0.f;
    for (int i=0;i<6;i++) mat += (float)(s->cnt_w[i]+s->cnt_b[i])*MV[i];
    return (int16_t)((mat/78.f)*256.0f);
}

static inline int16_t _sparse_kd_q(uint8_t d) {
    return (int16_t)(((float)d/7.f)*256.0f);
}

static void _sparse_apply_delta(NnueAccum *na,
                                const NnueExtraState *old,
                                const NnueExtraState *nw) {
    int count_changed=0;
    for (int pt=0;pt<6;pt++) {
        if (old->cnt_w[pt] != nw->cnt_w[pt]) {
            int16_t qo=_sparse_count_q(old->cnt_w[pt],pt);
            int16_t qn=_sparse_count_q(nw->cnt_w[pt],pt);
            _fullacc_q_transition(na->ext_acc_w, pt,   qo, qn);
            _fullacc_q_transition(na->ext_acc_b, 6+pt, qo, qn);
            count_changed=1;
        }
        if (old->cnt_b[pt] != nw->cnt_b[pt]) {
            int16_t qo=_sparse_count_q(old->cnt_b[pt],pt);
            int16_t qn=_sparse_count_q(nw->cnt_b[pt],pt);
            _fullacc_q_transition(na->ext_acc_w, 6+pt, qo, qn);
            _fullacc_q_transition(na->ext_acc_b, pt,   qo, qn);
            count_changed=1;
        }
    }
    if (count_changed) {
        int16_t qo=_sparse_material_q(old), qn=_sparse_material_q(nw);
        if (qo!=qn) {
            _fullacc_q_transition(na->ext_acc_w,12,qo,qn);
            _fullacc_q_transition(na->ext_acc_b,12,qo,qn);
        }
    }

    uint8_t dw=(uint8_t)(old->passed_w ^ nw->passed_w);
    while (dw) {
        int f=__builtin_ctz((unsigned)dw); dw &= (uint8_t)(dw-1);
        int16_t qo=(old->passed_w&(1u<<f))?256:0;
        int16_t qn=(nw->passed_w &(1u<<f))?256:0;
        _fullacc_q_transition(na->ext_acc_w,14+f,qo,qn);
        _fullacc_q_transition(na->ext_acc_b,22+f,qo,qn);
    }
    uint8_t db=(uint8_t)(old->passed_b ^ nw->passed_b);
    while (db) {
        int f=__builtin_ctz((unsigned)db); db &= (uint8_t)(db-1);
        int16_t qo=(old->passed_b&(1u<<f))?256:0;
        int16_t qn=(nw->passed_b &(1u<<f))?256:0;
        _fullacc_q_transition(na->ext_acc_w,22+f,qo,qn);
        _fullacc_q_transition(na->ext_acc_b,14+f,qo,qn);
    }
    if (old->king_dist != nw->king_dist) {
        int16_t qo=_sparse_kd_q(old->king_dist), qn=_sparse_kd_q(nw->king_dist);
        _fullacc_q_transition(na->ext_acc_w,30,qo,qn);
        _fullacc_q_transition(na->ext_acc_b,30,qo,qn);
    }
}

'''
    t=one(t,marker,helper+marker,'insert sparse helper')

    t=one(t,
'''    _fullacc_state_from_board(&na->ext_state_stack[0], board);
    memcpy(na->ext_acc_w, na->ext_buf[0], NN_L1_OUT*sizeof(int16_t));
''',
'''    _fullacc_state_from_board(&na->ext_state, board);
    memcpy(na->ext_acc_w, na->ext_buf[0], NN_L1_OUT*sizeof(int16_t));
''','rebuild live state')

    old='''    int extchg = _fullacc_child_state(&na->ext_state_stack[dst],
                                             &na->ext_state_stack[src], board, m);
    na->ext_changed[dst] = (uint8_t)extchg;
    if (extchg) {
        _fullacc_apply_delta(na->ext_acc_w, &na->ext_state_stack[src], &na->ext_state_stack[dst], 0);
        _fullacc_apply_delta(na->ext_acc_b, &na->ext_state_stack[src], &na->ext_state_stack[dst], 1);
    }
    na->acc_ptr = dst;
    na->ext_dirty[0] = 1;
    na->ext_dirty[1] = 1;
}

void nnue_pop_na(NnueAccum *na) {
    int cur = na->acc_ptr;
    if (cur <= 0) return;
    if (na->ext_changed[cur]) {
        _fullacc_apply_delta(na->ext_acc_w, &na->ext_state_stack[cur], &na->ext_state_stack[cur-1], 0);
        _fullacc_apply_delta(na->ext_acc_b, &na->ext_state_stack[cur], &na->ext_state_stack[cur-1], 1);
    }
    na->acc_ptr = cur - 1;
}
'''
    new='''    /* Manual features can change only on pawn/king moves, captures,
     * promotions and castling. The overwhelmingly common quiet N/B/R/Q move
     * pays no state-copy or projection cost. */
    int fext=m->from_sq, text=m->to_sq;
    uint8_t pext=board[fext], capext=board[text];
    int ptext=piece_type_idx(pext);
    int relevant=(ptext==0 || ptext==5 || capext || m->is_epc || m->prom || m->castle);
    na->ext_changed[dst]=0;
    if (relevant) {
        NnueExtraState child;
        int extchg=_fullacc_child_state(&child,&na->ext_state,board,m);
        if (extchg) {
            na->ext_undo[dst]=na->ext_state;
            _sparse_apply_delta(na,&na->ext_state,&child);
            na->ext_state=child;
            na->ext_changed[dst]=1;
        }
    }
    na->acc_ptr = dst;
    na->ext_dirty[0] = 1;
    na->ext_dirty[1] = 1;
}

void nnue_pop_na(NnueAccum *na) {
    int cur=na->acc_ptr;
    if (cur<=0) return;
    if (na->ext_changed[cur]) {
        const NnueExtraState *parent=&na->ext_undo[cur];
        _sparse_apply_delta(na,&na->ext_state,parent);
        na->ext_state=*parent;
    }
    na->acc_ptr=cur-1;
}
'''
    t=one(t,old,new,'push/pop sparse undo')
    cp.write_text(t,encoding='utf-8')
    print('applied sparse-undo fullacc optimisation')

if __name__=='__main__': main()
