#!/usr/bin/env python3
"""Instrument a patched v3.23 candidate to verify ext accumulator at every eval."""
from __future__ import annotations
import argparse
from pathlib import Path

OLD = r'''    const int16_t *ext = stm==0 ? na->ext_acc_w : na->ext_acc_b;

    /* Read HM accumulator from per-thread stack (v3.14) */
'''
NEW = r'''    const int16_t *ext = stm==0 ? na->ext_acc_w : na->ext_acc_b;

#ifdef V323_VERIFY_FULLACC
    {
        float vf[NN_EXTRA];
        int16_t check[NN_L1_OUT] __attribute__((aligned(32)));
        _compute_extra_feat_bb(vf, bb, stm);
        _project_feat_full(check, vf);
        if (memcmp(check, ext, NN_L1_OUT*sizeof(int16_t)) != 0) {
            const NnueExtraState *s = &na->ext_state_stack[na->acc_ptr];
            NnueExtraState real;
            _fullacc_state_from_board(&real, board);
            fprintf(stderr,
                    "V323_FULLACC_MISMATCH stm=%d ptr=%d hash=%016llx\n"
                    " stored: pw=%02x pb=%02x kd=%u wp=%016llx bp=%016llx kw=%u kb=%u\n"
                    " actual: pw=%02x pb=%02x kd=%u wp=%016llx bp=%016llx kw=%u kb=%u\n",
                    stm, na->acc_ptr, (unsigned long long)board_hash,
                    s->passed_w, s->passed_b, (unsigned)s->king_dist,
                    (unsigned long long)s->pawns_w, (unsigned long long)s->pawns_b,
                    (unsigned)s->king_w, (unsigned)s->king_b,
                    real.passed_w, real.passed_b, (unsigned)real.king_dist,
                    (unsigned long long)real.pawns_w, (unsigned long long)real.pawns_b,
                    (unsigned)real.king_w, (unsigned)real.king_b);
            fprintf(stderr, " stored counts W=%u,%u,%u,%u,%u,%u B=%u,%u,%u,%u,%u,%u\n",
                    s->cnt_w[0],s->cnt_w[1],s->cnt_w[2],s->cnt_w[3],s->cnt_w[4],s->cnt_w[5],
                    s->cnt_b[0],s->cnt_b[1],s->cnt_b[2],s->cnt_b[3],s->cnt_b[4],s->cnt_b[5]);
            fprintf(stderr, " actual counts W=%u,%u,%u,%u,%u,%u B=%u,%u,%u,%u,%u,%u\n",
                    real.cnt_w[0],real.cnt_w[1],real.cnt_w[2],real.cnt_w[3],real.cnt_w[4],real.cnt_w[5],
                    real.cnt_b[0],real.cnt_b[1],real.cnt_b[2],real.cnt_b[3],real.cnt_b[4],real.cnt_b[5]);
            for (int k=0;k<NN_L1_OUT;k++) if (check[k] != ext[k]) {
                fprintf(stderr, " first_lane=%d expected=%d got=%d delta=%d\n",
                        k, (int)check[k], (int)ext[k], (int)ext[k]-(int)check[k]);
                break;
            }
            abort();
        }
    }
#endif

    /* Read HM accumulator from per-thread stack (v3.14) */
'''

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,required=True); a=ap.parse_args()
    p=a.root/'nnue.c'; t=p.read_text(encoding='utf-8')
    if t.count(OLD)!=1: raise SystemExit(f'verifier anchor count={t.count(OLD)}')
    p.write_text(t.replace(OLD,NEW,1),encoding='utf-8')
    print('added V323_VERIFY_FULLACC instrumentation')
if __name__=='__main__': main()
