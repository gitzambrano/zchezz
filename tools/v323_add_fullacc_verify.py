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
            fprintf(stderr,
                    "V323_FULLACC_MISMATCH stm=%d ptr=%d hash=%016llx "
                    "pw=%02x pb=%02x kd=%u wp=%016llx bp=%016llx\n",
                    stm, na->acc_ptr, (unsigned long long)board_hash,
                    s->passed_w, s->passed_b, (unsigned)s->king_dist,
                    (unsigned long long)s->pawns_w, (unsigned long long)s->pawns_b);
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
