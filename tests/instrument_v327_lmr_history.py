#!/usr/bin/env python3
"""Instrument v3.26 LMR history values without changing search decisions."""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE=Path('engine/c/zchezz_v326/search.c')

DECL=r'''

/* V327_LMR_HISTORY_DIAGNOSTICS: counters only; no search decision changes. */
typedef struct {
    unsigned long long samples[7];
    unsigned long long lt_m1024[7], lt_m768[7], lt_m640[7], lt_m512[7], lt_m384[7];
    unsigned long long gt_384[7], gt_512[7], gt_640[7], gt_768[7], gt_1024[7], gt_2048[7];
    long long sum[7];
    int minv[7], maxv[7];
} V327LmrHistDiag;
static V327LmrHistDiag g_v327_lmr_hist;

static void v327_lmr_hist_sample(int depth, int ch) {
    int d = depth >= 6 ? 6 : depth;
    if (d < 3) return;
    g_v327_lmr_hist.samples[d]++;
    g_v327_lmr_hist.sum[d] += ch;
    if (g_v327_lmr_hist.samples[d] == 1 || ch < g_v327_lmr_hist.minv[d]) g_v327_lmr_hist.minv[d] = ch;
    if (g_v327_lmr_hist.samples[d] == 1 || ch > g_v327_lmr_hist.maxv[d]) g_v327_lmr_hist.maxv[d] = ch;
    if (ch < -1024) g_v327_lmr_hist.lt_m1024[d]++;
    if (ch < -768)  g_v327_lmr_hist.lt_m768[d]++;
    if (ch < -640)  g_v327_lmr_hist.lt_m640[d]++;
    if (ch < -512)  g_v327_lmr_hist.lt_m512[d]++;
    if (ch < -384)  g_v327_lmr_hist.lt_m384[d]++;
    if (ch > 384)   g_v327_lmr_hist.gt_384[d]++;
    if (ch > 512)   g_v327_lmr_hist.gt_512[d]++;
    if (ch > 640)   g_v327_lmr_hist.gt_640[d]++;
    if (ch > 768)   g_v327_lmr_hist.gt_768[d]++;
    if (ch > 1024)  g_v327_lmr_hist.gt_1024[d]++;
    if (ch > 2048)  g_v327_lmr_hist.gt_2048[d]++;
}

static void v327_lmr_hist_report(void) {
    for (int d=3; d<=6; ++d) {
        fprintf(stderr,
            "[V327_LMR_HIST] depth=%s samples=%llu lt_m1024=%llu lt_m768=%llu lt_m640=%llu lt_m512=%llu lt_m384=%llu gt_384=%llu gt_512=%llu gt_640=%llu gt_768=%llu gt_1024=%llu gt_2048=%llu min=%d max=%d sum=%lld\n",
            d==6?"6+":(d==5?"5":(d==4?"4":"3")),
            g_v327_lmr_hist.samples[d],g_v327_lmr_hist.lt_m1024[d],g_v327_lmr_hist.lt_m768[d],
            g_v327_lmr_hist.lt_m640[d],g_v327_lmr_hist.lt_m512[d],g_v327_lmr_hist.lt_m384[d],
            g_v327_lmr_hist.gt_384[d],g_v327_lmr_hist.gt_512[d],g_v327_lmr_hist.gt_640[d],
            g_v327_lmr_hist.gt_768[d],g_v327_lmr_hist.gt_1024[d],g_v327_lmr_hist.gt_2048[d],
            g_v327_lmr_hist.minv[d],g_v327_lmr_hist.maxv[d],g_v327_lmr_hist.sum[d]);
    }
}
#if defined(__GNUC__) || defined(__clang__)
__attribute__((constructor))
#endif
static void v327_lmr_hist_register(void) { atexit(v327_lmr_hist_report); }
'''

OLD='''                            int ch = ss->mv_history[ft_idx];
                            if (cmh0 >= 0) ch += ss->cont_hist[0][cmh0][ft_idx];
                            if (cmh1 >= 0) ch += ss->cont_hist[1][cmh1][ft_idx];
                            if (ch < -512) reduce += 1;
'''
NEW='''                            int ch = ss->mv_history[ft_idx];
                            if (cmh0 >= 0) ch += ss->cont_hist[0][cmh0][ft_idx];
                            if (cmh1 >= 0) ch += ss->cont_hist[1][cmh1][ft_idx];
                            v327_lmr_hist_sample(depth, ch);
                            if (ch < -512) reduce += 1;
'''


def main()->int:
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,default=SOURCE);a=ap.parse_args()
    text=a.source.read_text(encoding='utf-8')
    if text.count('#include <time.h>\n')!=1: raise RuntimeError('include anchor mismatch')
    if text.count(OLD)!=1: raise RuntimeError(f'LMR anchor mismatch: {text.count(OLD)}')
    text=text.replace('#include <time.h>\n','#include <time.h>\n'+DECL,1).replace(OLD,NEW,1)
    a.source.write_text(text,encoding='utf-8');print(f'instrumented {a.source}');return 0

if __name__=='__main__':raise SystemExit(main())
