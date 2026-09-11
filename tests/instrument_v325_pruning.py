#!/usr/bin/env python3
"""Add counter-only pruning/qsearch diagnostics to a CI copy of v3.25 search.c."""
from __future__ import annotations
import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v325/search.c")
BLOCK = r'''

/* PRUNING_DIAGNOSTICS: counters only; no search decision depends on them. */
typedef struct {
 unsigned long long razor_attempts,razor_cutoffs,rfp_attempts,rfp_cutoffs;
 unsigned long long nmp_attempts,nmp_cutoffs,probcut_attempts,probcut_moves,probcut_qhits,probcut_cutoffs;
 unsigned long long iir_applied,singular_attempts,singular_extensions,singular_multicuts;
 unsigned long long main_caps_generated,main_quiets_generated,main_caps_searched,main_quiets_searched;
 unsigned long long lmp_pruned,history_pruned,quiet_see_pruned,quiet_futility_pruned,capture_see_pruned;
 unsigned long long q_standpat_cutoffs,q_whole_delta_cutoffs,q_caps_generated,q_see_pruned,q_delta_pruned,q_caps_searched,q_capture_cutoffs;
} PruneDiag;
static PruneDiag g_prune;
static void prune_diag_report(void){
 fprintf(stderr,"[PRUNE_DIAG] razor_attempts=%llu razor_cutoffs=%llu rfp_attempts=%llu rfp_cutoffs=%llu nmp_attempts=%llu nmp_cutoffs=%llu probcut_attempts=%llu probcut_moves=%llu probcut_qhits=%llu probcut_cutoffs=%llu iir_applied=%llu singular_attempts=%llu singular_extensions=%llu singular_multicuts=%llu main_caps_generated=%llu main_quiets_generated=%llu main_caps_searched=%llu main_quiets_searched=%llu lmp_pruned=%llu history_pruned=%llu quiet_see_pruned=%llu quiet_futility_pruned=%llu capture_see_pruned=%llu q_standpat_cutoffs=%llu q_whole_delta_cutoffs=%llu q_caps_generated=%llu q_see_pruned=%llu q_delta_pruned=%llu q_caps_searched=%llu q_capture_cutoffs=%llu\n",
 g_prune.razor_attempts,g_prune.razor_cutoffs,g_prune.rfp_attempts,g_prune.rfp_cutoffs,g_prune.nmp_attempts,g_prune.nmp_cutoffs,g_prune.probcut_attempts,g_prune.probcut_moves,g_prune.probcut_qhits,g_prune.probcut_cutoffs,g_prune.iir_applied,g_prune.singular_attempts,g_prune.singular_extensions,g_prune.singular_multicuts,g_prune.main_caps_generated,g_prune.main_quiets_generated,g_prune.main_caps_searched,g_prune.main_quiets_searched,g_prune.lmp_pruned,g_prune.history_pruned,g_prune.quiet_see_pruned,g_prune.quiet_futility_pruned,g_prune.capture_see_pruned,g_prune.q_standpat_cutoffs,g_prune.q_whole_delta_cutoffs,g_prune.q_caps_generated,g_prune.q_see_pruned,g_prune.q_delta_pruned,g_prune.q_caps_searched,g_prune.q_capture_cutoffs);}
#if defined(__GNUC__) || defined(__clang__)
__attribute__((constructor))
#endif
static void prune_diag_register(void){atexit(prune_diag_report);}
'''

def r(t,o,n,c,label):
    got=t.count(o)
    if got!=c: raise RuntimeError(f"{label}: expected {c} matches, found {got}")
    return t.replace(o,n)

def transform(t):
    t=r(t,'#include <time.h>\n','#include <time.h>\n'+BLOCK,1,'decl')
    t=r(t,'    if (stand >= beta) return beta;\n','    if (stand >= beta) { g_prune.q_standpat_cutoffs++; return beta; }\n',1,'q standpat')
    t=r(t,'        if (stand + delta_margin < alpha) return alpha;\n','        if (stand + delta_margin < alpha) { g_prune.q_whole_delta_cutoffs++; return alpha; }\n',1,'q whole delta')
    t=r(t,'    int n = board_gen_captures(b, moves);\n','    int n = board_gen_captures(b, moves);\n    g_prune.q_caps_generated += (unsigned)n;\n',1,'q gen')
    t=r(t,'            if (sv < 0) { moves[i].score = -99999; continue; }\n','            if (sv < 0) { g_prune.q_see_pruned++; moves[i].score = -99999; continue; }\n',1,'q see')
    t=r(t,'        if (stand + gain + 50 < alpha && !moves[i].prom) { moves[i].score = -99999; continue; }\n','        if (stand + gain + 50 < alpha && !moves[i].prom) { g_prune.q_delta_pruned++; moves[i].score = -99999; continue; }\n',1,'q delta')
    qanchor='        if (board_is_attacked(b, king_sq, b->turn)) { board_unmake(b); continue; }\n        int sc = -qsearch(ss, b, -beta, -alpha, ply+1);\n'
    t=r(t,qanchor,'        if (board_is_attacked(b, king_sq, b->turn)) { board_unmake(b); continue; }\n        g_prune.q_caps_searched++;\n        int sc = -qsearch(ss, b, -beta, -alpha, ply+1);\n',1,'q searched')
    t=r(t,'        if (sc >= beta) {\n            if (!ss->time_up) tt_store(b->hash, qs_best, 0, TT_LOWER, &best_move_qs, ply, stand);\n','        if (sc >= beta) {\n            g_prune.q_capture_cutoffs++;\n            if (!ss->time_up) tt_store(b->hash, qs_best, 0, TT_LOWER, &best_move_qs, ply, stand);\n',1,'q cutoff')
    t=r(t,'    if (!in_check && !is_pv && depth==1 && static_eval+200 < alpha) {\n        int qs = qsearch(ss, b, alpha-1, alpha, ply);\n        if (qs < alpha) return qs;\n    }\n','    if (!in_check && !is_pv && depth==1 && static_eval+200 < alpha) {\n        g_prune.razor_attempts++;\n        int qs = qsearch(ss, b, alpha-1, alpha, ply);\n        if (qs < alpha) { g_prune.razor_cutoffs++; return qs; }\n    }\n',1,'razor')
    t=r(t,'    if (!in_check && !is_pv && depth>=2 && depth<=9 && beta<18000 && static_eval<18000) {\n        int rfp_margin = depth*90 - (improving ? 50 : 0);\n        if (static_eval - rfp_margin >= beta) return static_eval;\n    }\n','    if (!in_check && !is_pv && depth>=2 && depth<=9 && beta<18000 && static_eval<18000) {\n        g_prune.rfp_attempts++;\n        int rfp_margin = depth*90 - (improving ? 50 : 0);\n        if (static_eval - rfp_margin >= beta) { g_prune.rfp_cutoffs++; return static_eval; }\n    }\n',1,'rfp')
    t=r(t,'    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta) {\n','    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta) {\n        g_prune.nmp_attempts++;\n',1,'nmp attempt')
    t=r(t,'        if (null_score >= beta) return beta;\n','        if (null_score >= beta) { g_prune.nmp_cutoffs++; return beta; }\n',1,'nmp cutoff')
    t=r(t,'    if (!in_check && !is_pv && depth >= 5 && beta < 18000 && ply > 0) {\n','    if (!in_check && !is_pv && depth >= 5 && beta < 18000 && ply > 0) {\n        g_prune.probcut_attempts++;\n',1,'prob attempt')
    t=r(t,'        for (int pi = 0; pi < pc_n; pi++) {\n            Move *pm = &pc_moves[pi];\n','        for (int pi = 0; pi < pc_n; pi++) {\n            Move *pm = &pc_moves[pi];\n            g_prune.probcut_moves++;\n',1,'prob moves')
    t=r(t,'            if (pc_sc >= pc_beta) {\n                Move pc_pv[MAX_PLY]; int pc_len = 0;\n','            if (pc_sc >= pc_beta) {\n                g_prune.probcut_qhits++;\n                Move pc_pv[MAX_PLY]; int pc_len = 0;\n',1,'prob qhit')
    t=r(t,'            if (pc_sc >= pc_beta) return pc_sc;\n','            if (pc_sc >= pc_beta) { g_prune.probcut_cutoffs++; return pc_sc; }\n',1,'prob cutoff')
    t=r(t,'    if (!pv_move.from && !pv_move.to && depth>=3 && !in_check && depth-1>=2) depth--;\n','    if (!pv_move.from && !pv_move.to && depth>=3 && !in_check && depth-1>=2) { g_prune.iir_applied++; depth--; }\n',1,'iir')
    t=r(t,'    if (!in_check && depth>=7 && tte_hit && tte.depth>=depth-4 &&\n        ss->sing_from[ply]<0 && ply>0 && (tte.flag==TT_EXACT||tte.flag==TT_LOWER)) {\n','    if (!in_check && depth>=7 && tte_hit && tte.depth>=depth-4 &&\n        ss->sing_from[ply]<0 && ply>0 && (tte.flag==TT_EXACT||tte.flag==TT_LOWER)) {\n        g_prune.singular_attempts++;\n',1,'sing attempt')
    t=r(t,'        if (se_score < s_beta) sing_ext = 1;    /* TT move is singular → extend */\n        else if (s_beta >= beta) return s_beta;  /* multi-cut → prune */\n','        if (se_score < s_beta) { g_prune.singular_extensions++; sing_ext = 1; }    /* TT move is singular → extend */\n        else if (s_beta >= beta) { g_prune.singular_multicuts++; return s_beta; }  /* multi-cut → prune */\n',1,'sing outcomes')
    t=r(t,'        int n_caps = board_gen_captures(b, caps);\n','        int n_caps = board_gen_captures(b, caps);\n        g_prune.main_caps_generated += (unsigned)n_caps;\n',1,'main cap gen')
    t=r(t,'            int sc;\n            child_len = 0;\n            if (legal_count == 1) {\n','            g_prune.main_caps_searched++;\n            int sc;\n            child_len = 0;\n            if (legal_count == 1) {\n',2,'main cap search')
    t=r(t,'            int n_quiets = board_gen_quiets(b, quiets);\n','            int n_quiets = board_gen_quiets(b, quiets);\n            g_prune.main_quiets_generated += (unsigned)n_quiets;\n',1,'main quiet gen')
    t=r(t,'                    if (quiet_count > lmp_lim) continue;\n','                    if (quiet_count > lmp_lim) { g_prune.lmp_pruned++; continue; }\n',1,'lmp')
    t=r(t,'                        if (ch_hp < hp_thresh) continue;\n','                        if (ch_hp < hp_thresh) { g_prune.history_pruned++; continue; }\n',1,'history')
    t=r(t,'                    if (see_board(b, mfr, mto, 0) < -(depth * 60)) continue;\n','                    if (see_board(b, mfr, mto, 0) < -(depth * 60)) { g_prune.quiet_see_pruned++; continue; }\n',1,'quiet see')
    t=r(t,'                    if (static_eval + fut_base[fd] + fut_adj <= alpha) { board_unmake(b); continue; }\n','                    if (static_eval + fut_base[fd] + fut_adj <= alpha) { g_prune.quiet_futility_pruned++; board_unmake(b); continue; }\n',1,'futility')
    t=r(t,'                int sc;\n                child_len = 0;\n                if (legal_count == 1) {\n','                g_prune.main_quiets_searched++;\n                int sc;\n                child_len = 0;\n                if (legal_count == 1) {\n',1,'main quiet search')
    t=r(t,'                    if ((dr>dc?dr:dc) > 1) continue;\n','                    if ((dr>dc?dr:dc) > 1) { g_prune.capture_see_pruned++; continue; }\n',2,'cap see')
    return t

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--source',type=Path,default=SOURCE); a=ap.parse_args()
    old=a.source.read_text(encoding='utf-8'); new=transform(old)
    if new==old: raise RuntimeError('no changes applied')
    a.source.write_text(new,encoding='utf-8'); print(f'instrumented pruning diagnostics in {a.source}'); return 0
if __name__=='__main__': raise SystemExit(main())
