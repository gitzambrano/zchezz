#!/usr/bin/env python3
"""Measure pre-history LMR reduction for positive/negative history cases without changing decisions."""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v326/search.c")

DECL = r'''

/* LMR_PREHIST_DIAGNOSTICS: counters only. */
typedef struct {
    unsigned long long samples[4];
    unsigned long long pos[4][5];
    unsigned long long neg1[4][5];
    unsigned long long neg2[4][5];
} LmrPreHistDiag;
static LmrPreHistDiag g_lmrph;
static int lmrph_dbucket(int d) { return d <= 3 ? 0 : d == 4 ? 1 : d == 5 ? 2 : 3; }
static int lmrph_rbucket(int r) { return r <= 0 ? 0 : r == 1 ? 1 : r == 2 ? 2 : r == 3 ? 3 : 4; }
static void lmrph_sample(int depth, int r, int ch) {
    int d=lmrph_dbucket(depth), q=lmrph_rbucket(r);
    g_lmrph.samples[d]++;
    if (ch > 512) g_lmrph.pos[d][q]++;
    if (ch < -512) g_lmrph.neg1[d][q]++;
    if (ch < -1024) g_lmrph.neg2[d][q]++;
}
static void lmrph_report(void) {
    static const char *dn[4]={"d3","d4","d5","d6plus"};
    for (int d=0;d<4;d++) {
        fprintf(stderr,"[LMR_PREHIST] depth=%s samples=%llu",dn[d],g_lmrph.samples[d]);
        for (int r=0;r<5;r++) fprintf(stderr," pos_r%d=%llu",r,g_lmrph.pos[d][r]);
        for (int r=0;r<5;r++) fprintf(stderr," neg1_r%d=%llu",r,g_lmrph.neg1[d][r]);
        for (int r=0;r<5;r++) fprintf(stderr," neg2_r%d=%llu",r,g_lmrph.neg2[d][r]);
        fputc('\n',stderr);
    }
}
#if defined(__GNUC__) || defined(__clang__)
__attribute__((constructor))
#endif
static void lmrph_register(void) { atexit(lmrph_report); }
'''

OLD = '''                            int ch = ss->mv_history[ft_idx];
                            if (cmh0 >= 0) ch += ss->cont_hist[0][cmh0][ft_idx];
                            if (cmh1 >= 0) ch += ss->cont_hist[1][cmh1][ft_idx];
                            if (ch < -512) reduce += 1;
                            if (ch < -1024) reduce += 1;
                            if (ch > 512 && reduce > 0) reduce -= 1;
'''
NEW = '''                            int ch = ss->mv_history[ft_idx];
                            if (cmh0 >= 0) ch += ss->cont_hist[0][cmh0][ft_idx];
                            if (cmh1 >= 0) ch += ss->cont_hist[1][cmh1][ft_idx];
                            lmrph_sample(depth, reduce, ch);
                            if (ch < -512) reduce += 1;
                            if (ch < -1024) reduce += 1;
                            if (ch > 512 && reduce > 0) reduce -= 1;
'''


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source",type=Path,default=SOURCE)
    a=ap.parse_args()
    text=a.source.read_text(encoding="utf-8")
    inc='#include <time.h>\n'
    if text.count(inc)!=1: raise RuntimeError('expected one time.h include')
    text=text.replace(inc,inc+DECL,1)
    if text.count(OLD)!=1: raise RuntimeError(f'expected one LMR history block, found {text.count(OLD)}')
    a.source.write_text(text.replace(OLD,NEW,1),encoding='utf-8')
    print(f'Instrumented pre-history LMR reduction in {a.source}')
    return 0

if __name__=='__main__': raise SystemExit(main())
