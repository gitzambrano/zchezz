#!/usr/bin/env python3
"""Materialize an experimental NNU4 runtime with an optional GLB1 side channel.

The source directory is copied verbatim, then nnue.c is patched so an optional
31x48 int16 trailer projects v3-style global features into each perspective's
48-value L1 accumulator before SCReLU.  With a missing or all-zero GLB1 trailer
the forward pass is exactly the ordinary NNU4 path.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"patch {label}: expected one match, got {n}")
    return text.replace(old, new, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--dest", type=Path, required=True)
    a = ap.parse_args()
    if a.dest.exists():
        shutil.rmtree(a.dest)
    shutil.copytree(a.source, a.dest)
    for name in ("zchezz", "zchezz.exe"):
        p = a.dest / name
        if p.exists():
            p.unlink()
    p = a.dest / "nnue.c"
    s = p.read_text(encoding="utf-8")

    s = once(s,
        "    float    OutScale;\n\n    int      ready;",
        "    float    OutScale;\n\n    /* Optional GLB1 side channel: [31 global features][48 L1 outputs], Q=255. */\n"
        "    int16_t *G1W;\n\n    int      ready;",
        "net-field")
    s = once(s,
        "    zfree32(net->L3W);\n    free(net);",
        "    zfree32(net->L3W);\n    zfree32(net->G1W);\n    free(net);",
        "destroy")
    s = once(s,
        "    zfree32(net->L2W);  zfree32(net->L2B);\n    zfree32(net->L3W);\n\n    net->L1WT =",
        "    zfree32(net->L2W);  zfree32(net->L2B);\n    zfree32(net->L3W);\n    zfree32(net->G1W); net->G1W = NULL;\n\n    net->L1WT =",
        "reload-free")
    s = once(s,
        "    memcpy(net->L3W,  buf+off, NN_L3_IN);      off += NN_L3_IN;\n    memcpy(&net->L3B, buf+off, 4);\n\n    net->ready = 1;",
        "    memcpy(net->L3W,  buf+off, NN_L3_IN);      off += NN_L3_IN;\n"
        "    memcpy(&net->L3B, buf+off, 4);             off += 4;\n\n"
        "    /* Optional backwards-compatible global projection trailer. */\n"
        "    enum { NN_GLOBAL = 31 };\n"
        "    if (len >= off + 12 && memcmp(buf + off, \"GLB1\", 4) == 0) {\n"
        "        uint32_t gdims[2]; memcpy(gdims, buf + off + 4, 8);\n"
        "        if (gdims[0] != NN_GLOBAL || gdims[1] != NN_L1_OUT) {\n"
        "            fprintf(stderr, \"[NNUE] GLB1 dim mismatch %u/%u\\n\", gdims[0], gdims[1]);\n"
        "            return -1;\n"
        "        }\n"
        "        off += 12;\n"
        "        size_t gsz = (size_t)NN_GLOBAL * NN_L1_OUT;\n"
        "        if (len < off + gsz * sizeof(int16_t)) {\n"
        "            fprintf(stderr, \"[NNUE] truncated GLB1 trailer\\n\"); return -1;\n"
        "        }\n"
        "        net->G1W = (int16_t *)zmalloc32(gsz * sizeof(int16_t));\n"
        "        if (!net->G1W) { fprintf(stderr, \"[NNUE] GLB1 malloc failed\\n\"); return -1; }\n"
        "        memcpy(net->G1W, buf + off, gsz * sizeof(int16_t));\n"
        "        fprintf(stderr, \"[NNUE] GLB1 global projection enabled (31->48)\\n\");\n"
        "    }\n\n"
        "    net->ready = 1;",
        "trailer-load")

    marker = "/* Shared forward pass. Returns centipawns from the point of view of `stm`.\n * The 96-byte L2 input is always concatenated as [stm 48 | opp 48]. */\n"
    helpers = r'''/* ── Optional GLB1 global feature projection ─────────────────────── */
#define NN_GLOBAL 31
static inline int _pcnt64(uint64_t x) { return __builtin_popcountll(x); }

static uint8_t _passed_file_mask_global(uint64_t own, uint64_t opp, int white) {
    uint8_t mask = 0;
    uint64_t x = own;
    while (x) {
        int sq = __builtin_ctzll(x); x &= x - 1;
        int f = sq & 7, r = sq >> 3;
        int passed = 1;
        uint64_t y = opp;
        while (y) {
            int osq = __builtin_ctzll(y); y &= y - 1;
            int of = osq & 7, orow = osq >> 3;
            if (of < f - 1 || of > f + 1) continue;
            if ((white && orow < r) || (!white && orow > r)) { passed = 0; break; }
        }
        if (passed) mask |= (uint8_t)(1u << f);
    }
    return mask;
}

static void _global_features_q(uint16_t q[NN_GLOBAL], const uint64_t bb[12], int perspective) {
    static const int maxc[6] = {8,2,2,2,1,1};
    static const int matv[6] = {1,3,3,5,9,0};
    int cw[6], cb[6];
    for (int i=0;i<6;i++) { cw[i]=_pcnt64(bb[i]); cb[i]=_pcnt64(bb[6+i]); }
    const int *own = perspective==0 ? cw : cb;
    const int *opp = perspective==0 ? cb : cw;
    for (int i=0;i<6;i++) {
        q[i]   = (uint16_t)((own[i]*256 + maxc[i]/2) / maxc[i]);
        q[6+i] = (uint16_t)((opp[i]*256 + maxc[i]/2) / maxc[i]);
    }
    int mat=0; for(int i=0;i<6;i++) mat += (cw[i]+cb[i])*matv[i];
    q[12]=(uint16_t)((mat*256 + 39)/78); q[13]=256;
    uint8_t pw=_passed_file_mask_global(bb[0],bb[6],1);
    uint8_t pb=_passed_file_mask_global(bb[6],bb[0],0);
    uint8_t po = perspective==0 ? pw : pb;
    uint8_t px = perspective==0 ? pb : pw;
    for(int f=0;f<8;f++){q[14+f]=(po&(1u<<f))?256:0;q[22+f]=(px&(1u<<f))?256:0;}
    if (bb[5] && bb[11]) {
        int wk=__builtin_ctzll(bb[5]), bk=__builtin_ctzll(bb[11]);
        int df=(wk&7)-(bk&7); if(df<0)df=-df;
        int dr=(wk>>3)-(bk>>3); if(dr<0)dr=-dr;
        int d=df>dr?df:dr; q[30]=(uint16_t)((d*256+3)/7);
    } else q[30]=0;
}

static void _board_to_bb_global(const uint8_t *board, uint64_t bb[12]) {
    memset(bb,0,12*sizeof(uint64_t));
    for(int sq=0;sq<64;sq++){
        uint8_t p=board[sq]; if(!p)continue;
        int t=PC_TYPE(p)-1; if(t<0||t>5)continue;
        int idx=(PC_COLOR(p)==COL_W)?t:6+t; bb[idx]|=1ULL<<sq;
    }
}

static void _apply_global_projection(int16_t out[NN_L1_OUT], const int16_t *base,
                                     const int16_t *gw, const uint16_t q[NN_GLOBAL]) {
    for(int o=0;o<NN_L1_OUT;o++){
        int64_t sum=0;
        for(int f=0;f<NN_GLOBAL;f++) sum += (int32_t)gw[f*NN_L1_OUT+o]*(int32_t)q[f];
        int32_t delta = sum>=0 ? (int32_t)((sum+128)/256) : -(int32_t)((-sum+128)/256);
        int32_t v=(int32_t)base[o]+delta;
        if(v>32767)v=32767; else if(v<-32768)v=-32768;
        out[o]=(int16_t)v;
    }
}

'''
    if marker not in s:
        raise SystemExit("forward marker not found")
    s = s.replace(marker, helpers + marker, 1)

    s = once(s,
        "static int _nnue_forward(NnueAccum *na, int stm, const uint8_t *board) {",
        "static int _nnue_forward(NnueAccum *na, int stm, const uint8_t *board, const uint64_t bb_in[12]) {",
        "forward-signature")
    old_acc = """    const int16_t *acc_stm = (stm == 0) ? na->acc_stack_w[ptr] : na->acc_stack_b[ptr];
    const int16_t *acc_opp = (stm == 0) ? na->acc_stack_b[ptr] : na->acc_stack_w[ptr];

    /* SCReLU -> relu1[96] = [stm 48 | opp 48]. */"""
    new_acc = """    const int16_t *acc_stm = (stm == 0) ? na->acc_stack_w[ptr] : na->acc_stack_b[ptr];
    const int16_t *acc_opp = (stm == 0) ? na->acc_stack_b[ptr] : na->acc_stack_w[ptr];
    int16_t gacc_stm[NN_L1_OUT] __attribute__((aligned(32)));
    int16_t gacc_opp[NN_L1_OUT] __attribute__((aligned(32)));
    if (net->G1W) {
        uint64_t local_bb[12]; const uint64_t *gbb = bb_in;
        if (!gbb) { _board_to_bb_global(board, local_bb); gbb = local_bb; }
        uint16_t qs[NN_GLOBAL], qo[NN_GLOBAL];
        _global_features_q(qs, gbb, stm);
        _global_features_q(qo, gbb, 1-stm);
        _apply_global_projection(gacc_stm, acc_stm, net->G1W, qs);
        _apply_global_projection(gacc_opp, acc_opp, net->G1W, qo);
        acc_stm=gacc_stm; acc_opp=gacc_opp;
    }

    /* SCReLU -> relu1[96] = [stm 48 | opp 48]. */"""
    s = once(s, old_acc, new_acc, "forward-global")
    s = once(s,
        "    return _nnue_forward(na, stm, board);\n}\n\n/* bb[] and board_hash are retained for the common search signature; compact\n * NNU4 does not use the NNU3 extra-feature cache that required them. */",
        "    return _nnue_forward(na, stm, board, NULL);\n}\n\n/* bb[] feeds the optional GLB1 global projection; board_hash remains unused. */",
        "eval-wrapper")
    s = once(s,
        "    (void)bb; (void)board_hash;\n    return _nnue_forward(na, stm, board);",
        "    (void)board_hash;\n    return _nnue_forward(na, stm, board, bb);",
        "eval-bb-wrapper")

    p.write_text(s, encoding="utf-8")
    print(f"materialized GLB1 runtime: {a.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
