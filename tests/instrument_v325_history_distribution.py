#!/usr/bin/env python3
"""Instrument v3.25 quiet-history values without changing search decisions.

Samples the combined butterfly + two-ply continuation-history value at the exact
history-pruning site (depths 1..4) and at the LMR history-adjustment site. The
transform is diagnostic-only and intended for parity-gated CI benchmarks.
"""
from __future__ import annotations
import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v325/search.c")

BLOCK = r'''

/* HISTORY_DISTRIBUTION_DIAGNOSTICS: counters only. */
typedef struct {
    unsigned long long samples[5];
    unsigned long long neg[5];
    unsigned long long le16[5], le64[5], le256[5], le1024[5], le4096[5];
    unsigned long long current_threshold[5];
    long long sum[5];
    int minv[5], maxv[5];
    unsigned long long lmr_samples, lmr_lt_m4000, lmr_lt_m8000, lmr_gt_4000;
} HistoryDiag;
static HistoryDiag g_hdiag;

static void hdiag_sample(int depth, int v) {
    if (depth < 1 || depth > 4) return;
    g_hdiag.samples[depth]++;
    g_hdiag.sum[depth] += v;
    if (g_hdiag.samples[depth] == 1 || v < g_hdiag.minv[depth]) g_hdiag.minv[depth] = v;
    if (g_hdiag.samples[depth] == 1 || v > g_hdiag.maxv[depth]) g_hdiag.maxv[depth] = v;
    if (v < 0) g_hdiag.neg[depth]++;
    if (v <= -16) g_hdiag.le16[depth]++;
    if (v <= -64) g_hdiag.le64[depth]++;
    if (v <= -256) g_hdiag.le256[depth]++;
    if (v <= -1024) g_hdiag.le1024[depth]++;
    if (v <= -4096) g_hdiag.le4096[depth]++;
    if (v < -4000 * depth) g_hdiag.current_threshold[depth]++;
}
static void hdiag_lmr(int v) {
    g_hdiag.lmr_samples++;
    if (v < -4000) g_hdiag.lmr_lt_m4000++;
    if (v < -8000) g_hdiag.lmr_lt_m8000++;
    if (v > 4000) g_hdiag.lmr_gt_4000++;
}
static void hdiag_report(void) {
    for (int d=1; d<=4; ++d)
        fprintf(stderr,
            "[HISTORY_DIAG] depth=%d samples=%llu neg=%llu le16=%llu le64=%llu le256=%llu le1024=%llu le4096=%llu current=%llu min=%d max=%d sum=%lld\n",
            d,g_hdiag.samples[d],g_hdiag.neg[d],g_hdiag.le16[d],g_hdiag.le64[d],g_hdiag.le256[d],g_hdiag.le1024[d],g_hdiag.le4096[d],g_hdiag.current_threshold[d],g_hdiag.minv[d],g_hdiag.maxv[d],g_hdiag.sum[d]);
    fprintf(stderr,"[HISTORY_LMR] samples=%llu lt_m4000=%llu lt_m8000=%llu gt_4000=%llu\n",
        g_hdiag.lmr_samples,g_hdiag.lmr_lt_m4000,g_hdiag.lmr_lt_m8000,g_hdiag.lmr_gt_4000);
}
#if defined(__GNUC__) || defined(__clang__)
__attribute__((constructor))
#endif
static void hdiag_register(void) { atexit(hdiag_report); }
'''


def exact(text: str, old: str, new: str, count: int, label: str) -> str:
    n=text.count(old)
    if n != count: raise RuntimeError(f"{label}: expected {count} matches, found {n}")
    return text.replace(old,new)


def transform(text: str) -> str:
    text=exact(text,'#include <time.h>\n','#include <time.h>\n'+BLOCK,1,'declarations')
    hp='''                        int ch_hp = ss->mv_history[ft_hp];
                        if (cmh0 >= 0) ch_hp += ss->cont_hist[0][cmh0][ft_hp];
                        if (cmh1 >= 0) ch_hp += ss->cont_hist[1][cmh1][ft_hp];
                        int hp_thresh = -4000 * depth;
'''
    hp_new='''                        int ch_hp = ss->mv_history[ft_hp];
                        if (cmh0 >= 0) ch_hp += ss->cont_hist[0][cmh0][ft_hp];
                        if (cmh1 >= 0) ch_hp += ss->cont_hist[1][cmh1][ft_hp];
                        hdiag_sample(depth, ch_hp);
                        int hp_thresh = -4000 * depth;
'''
    text=exact(text,hp,hp_new,1,'history pruning sample')
    lmr='''                            int ch = ss->mv_history[ft_idx];
                            if (cmh0 >= 0) ch += ss->cont_hist[0][cmh0][ft_idx];
                            if (cmh1 >= 0) ch += ss->cont_hist[1][cmh1][ft_idx];
                            if (ch < -4000) reduce += 1;
'''
    lmr_new='''                            int ch = ss->mv_history[ft_idx];
                            if (cmh0 >= 0) ch += ss->cont_hist[0][cmh0][ft_idx];
                            if (cmh1 >= 0) ch += ss->cont_hist[1][cmh1][ft_idx];
                            hdiag_lmr(ch);
                            if (ch < -4000) reduce += 1;
'''
    text=exact(text,lmr,lmr_new,1,'LMR history sample')
    return text


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,default=SOURCE);a=ap.parse_args()
    old=a.source.read_text(encoding='utf-8');new=transform(old)
    a.source.write_text(new,encoding='utf-8');print(f'instrumented history distribution in {a.source}');return 0
if __name__=='__main__':raise SystemExit(main())
