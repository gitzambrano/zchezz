#!/usr/bin/env python3
"""Apply the v3.27 search-correctness bundle to promoted v3.26 search.c.

The bundle fixes check classification around forward pruning without changing
search tuning thresholds:

1. Pre-pruning check detection is exact for ordinary moves, including discovered
   slider checks and en-passant discoveries.
2. LMP/history pruning never discards a move solely because it is a late/bad
   quiet when that move actually gives check.
3. Quiet SEE pruning exempts actual checking moves and does not treat castling
   as an ordinary quiet.
4. Losing-capture SEE pruning exempts actual checking captures, replacing the
   old destination-near-king approximation.
5. Post-move gives_check fast paths include pawn discoveries and en-passant.
6. The stale IIR comment is corrected to the effective depth>=3 behavior.
"""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v326/search.c")

OLD_HELPER = r'''/* Cheap direct-check test ported from v4.02.  It intentionally detects
 * direct checks only; discovered checks remain outside this cheap prune gate. */
static inline int quiet_direct_check(const Board *bd, int from, int to) {
    int ksq = bd->turn == COL_W ? bd->bk : bd->wk;
    uint64_t occ = bd->occ & ~((uint64_t)1 << from);
    switch (PC_TYPE(bd->b[from])) {
        case 1: return (bd->turn == COL_W ? wpawn_attacks_bb((uint64_t)1 << to)
                                          : bpawn_attacks_bb((uint64_t)1 << to)) >> ksq & 1;
        case 2: return (NATK[to] >> ksq) & 1;
        case 3: return (bish_attacks(to, occ) >> ksq) & 1;
        case 4: case 5:
            return ((rook_attacks(to, occ) | bish_attacks(to, occ)) >> ksq) & 1;
        default: return 0;
    }
}
'''

NEW_HELPER = r'''/* Exact pre-move check test for pruning gates.
 *
 * This evaluates the post-move occupancy without make/unmake.  It handles
 * direct checks, slider discoveries created by vacating the origin square,
 * promotions, normal captures and en-passant (whose captured pawn disappears
 * from a third square).  Castling is conservatively reported as checking: the
 * pruning gates using this helper should never discard castles anyway, and a
 * castle can reveal a rook check that needs the full board_make path to model. */
static inline int move_gives_check_pre(const Board *bd, const Move *m) {
    if (m->castle) return 1;

    int from = m->from, to = m->to;
    int ksq = bd->turn == COL_W ? bd->bk : bd->wk;
    uint64_t from_bb = (uint64_t)1 << from;
    uint64_t to_bb   = (uint64_t)1 << to;
    uint64_t occ_after = (bd->occ & ~from_bb) | to_bb;
    if (m->epc) {
        int ep_sq = bd->turn == COL_W ? to + 8 : to - 8;
        occ_after &= ~((uint64_t)1 << ep_sq);
    }

    int moved_type = m->prom ? m->prom : PC_TYPE(bd->b[from]);
    int direct = 0;
    switch (moved_type) {
        case 1:
            direct = (int)(((bd->turn == COL_W ? wpawn_attacks_bb(to_bb)
                                                  : bpawn_attacks_bb(to_bb)) >> ksq) & 1);
            break;
        case 2:
            direct = (int)((NATK[to] >> ksq) & 1);
            break;
        case 3:
            direct = (int)((bish_attacks(to, occ_after) >> ksq) & 1);
            break;
        case 4:
            direct = (int)((rook_attacks(to, occ_after) >> ksq) & 1);
            break;
        case 5:
            direct = (int)(((rook_attacks(to, occ_after) |
                              bish_attacks(to, occ_after)) >> ksq) & 1);
            break;
        case 6:
            direct = (int)((KATK[to] >> ksq) & 1);
            break;
        default:
            break;
    }
    if (direct) return 1;

    /* Friendly sliders still live in the pre-move bitboards.  Remove the
     * moving piece from its origin; a moved slider's direct attack from `to`
     * was already handled above. */
    int base = bd->turn == COL_W ? 0 : 6;
    uint64_t rq = (bd->bb[base + 3] | bd->bb[base + 4]) & ~from_bb;
    uint64_t bq = (bd->bb[base + 2] | bd->bb[base + 4]) & ~from_bb;
    if (rook_attacks(ksq, occ_after) & rq) return 1;
    if (bish_attacks(ksq, occ_after) & bq) return 1;
    return 0;
}
'''

OLD_LMP = r'''                if (!in_check && is_quiet && depth<=7 && legal_count>0 && !is_killer) {
                    quiet_count++;
                    int lmp_lim = lmp_limit[depth<8?depth:7];
                    if (!improving) lmp_lim = (lmp_lim + 1) / 2;
                    if (quiet_count > lmp_lim) continue;

                    /* History pruning */
                    if (depth <= 4) {
                        int ft_hp = mfr * 64 + mto;
                        int ch_hp = ss->mv_history[ft_hp];
                        if (cmh0 >= 0) ch_hp += ss->cont_hist[0][cmh0][ft_hp];
                        if (cmh1 >= 0) ch_hp += ss->cont_hist[1][cmh1][ft_hp];
                        int hp_thresh = -64 * depth;
                        if (ch_hp < hp_thresh) continue;
                    }
                }
'''

NEW_LMP = r'''                if (!in_check && is_quiet && depth<=7 && legal_count>0 && !is_killer) {
                    quiet_count++;
                    int lmp_lim = lmp_limit[depth<8?depth:7];
                    if (!improving) lmp_lim = (lmp_lim + 1) / 2;
                    if (quiet_count > lmp_lim && !move_gives_check_pre(b, m)) continue;

                    /* History pruning */
                    if (depth <= 4) {
                        int ft_hp = mfr * 64 + mto;
                        int ch_hp = ss->mv_history[ft_hp];
                        if (cmh0 >= 0) ch_hp += ss->cont_hist[0][cmh0][ft_hp];
                        if (cmh1 >= 0) ch_hp += ss->cont_hist[1][cmh1][ft_hp];
                        int hp_thresh = -64 * depth;
                        if (ch_hp < hp_thresh && !move_gives_check_pre(b, m)) continue;
                    }
                }
'''

OLD_QSEE = r'''                if (!in_check && !is_pv && legal_count > 0 && depth <= 4 &&
                    !is_killer &&
                    !(cur_prev_ft >= 0 && ss->counter_move[cur_prev_ft] == (mfr*64+mto)) &&
                    !quiet_direct_check(b, mfr, mto)) {
                    if (see_board(b, mfr, mto, 0) < -(depth * 60)) continue;
                }
'''

NEW_QSEE = r'''                if (!in_check && !is_pv && is_quiet && legal_count > 0 && depth <= 4 &&
                    !is_killer &&
                    !(cur_prev_ft >= 0 && ss->counter_move[cur_prev_ft] == (mfr*64+mto))) {
                    if (see_board(b, mfr, mto, 0) < -(depth * 60) &&
                        !move_gives_check_pre(b, m)) continue;
                }
'''

OLD_BAD_CAPTURE = r'''                int see_thresh = depth<=4 ? -80 : depth<=6 ? -120 : -160;
                if (sv < see_thresh) {
                    int tr=mto>>3,tc=mto&7,kr=ok_sq>>3,kc=ok_sq&7;
                    int dr=tr-kr;if(dr<0)dr=-dr;
                    int dc=tc-kc;if(dc<0)dc=-dc;
                    if ((dr>dc?dr:dc) > 1) continue;
                }
'''

NEW_BAD_CAPTURE = r'''                int see_thresh = depth<=4 ? -80 : depth<=6 ? -120 : -160;
                if (sv < see_thresh && !move_gives_check_pre(b, m)) continue;
'''

OLD_GC = r'''                int gives_check = 0;
                { uint8_t gpt=b->b[m->to]&7,gksq=b->turn==COL_W?b->wk:b->bk;
                  int gdr=((m->to>>3)-(gksq>>3)); if(gdr<0)gdr=-gdr;
                  int gdc=((m->to&7)-(gksq&7));   if(gdc<0)gdc=-gdc;
                  if (gpt>=3||gpt==2||m->prom||(gdr>gdc?gdr:gdc)<=2)
                      gives_check = board_in_check(b);
                }
'''

NEW_GC = r'''                int gives_check = 0;
                { uint8_t gpt=b->b[m->to]&7,gksq=b->turn==COL_W?b->wk:b->bk;
                  int gdr=((m->to>>3)-(gksq>>3)); if(gdr<0)gdr=-gdr;
                  int gdc=((m->to&7)-(gksq&7));   if(gdc<0)gdc=-gdc;
                  int pawn_discovery = 0;
                  if (gpt == 1) {
                      int gfr=m->from>>3, gfc=m->from&7, gkr=gksq>>3, gkc=gksq&7;
                      int gfdr=gfr-gkr; if(gfdr<0)gfdr=-gfdr;
                      int gfdc=gfc-gkc; if(gfdc<0)gfdc=-gfdc;
                      pawn_discovery = (gfr==gkr) || (gfc==gkc) || (gfdr==gfdc);
                  }
                  if (gpt>=3||gpt==2||m->prom||m->epc||(gdr>gdc?gdr:gdc)<=2||pawn_discovery)
                      gives_check = board_in_check(b);
                }
'''


def replace_exact(text: str, old: str, new: str, expected: int, label: str) -> str:
    n = text.count(old)
    if n != expected:
        raise RuntimeError(f"{label}: expected {expected} exact matches, found {n}")
    return text.replace(old, new)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    args = ap.parse_args()

    s = args.source.read_text(encoding="utf-8")
    s = replace_exact(s, OLD_HELPER, NEW_HELPER, 1, "check helper")
    s = replace_exact(s, OLD_LMP, NEW_LMP, 1, "LMP/history block")
    s = replace_exact(s, OLD_QSEE, NEW_QSEE, 1, "quiet SEE block")
    s = replace_exact(s, OLD_BAD_CAPTURE, NEW_BAD_CAPTURE, 1, "losing-capture SEE block")
    s = replace_exact(s, OLD_GC, NEW_GC, 4, "post-move gives_check blocks")

    old_iir = "     *   depth >= 4, not in check, reduced depth still >= 2 */"
    new_iir = "     *   depth >= 3, not in check, reduced depth still >= 2 */"
    s = replace_exact(s, old_iir, new_iir, 1, "IIR comment")

    args.source.write_text(s, encoding="utf-8")
    print(f"Applied search correctness bundle to {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
