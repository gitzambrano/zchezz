#!/usr/bin/env python3
"""Materialize NNU4 with an optional cheap GLB2 global-to-L2 side channel.

GLB2 adds one perspective-relative 31-feature vector to the 20 L2 integer
pre-activations.  Feature scale is QA_EFF=254 and side weights use the native
L2 QB=64 int8 scale, so the product lands in exactly the same accumulator units
as ordinary L2. Missing/all-zero GLB2 is bit-identical to the base engine.
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
        q = a.dest / name
        if q.exists():
            q.unlink()
    p = a.dest / "nnue.c"
    s = p.read_text(encoding="utf-8")

    s = once(s,
        "    float    OutScale;\n\n    int      ready;",
        "    float    OutScale;\n\n    /* Optional GLB2: [31 global features][20 L2 outputs], int8/QB. */\n"
        "    int8_t  *G2W;\n\n    int      ready;",
        "net-field")
    s = once(s,
        "    zfree32(net->L3W);\n    free(net);",
        "    zfree32(net->L3W);\n    zfree32(net->G2W);\n    free(net);",
        "destroy")
    s = once(s,
        "    zfree32(net->L2W);  zfree32(net->L2B);\n    zfree32(net->L3W);\n\n    net->L1WT =",
        "    zfree32(net->L2W);  zfree32(net->L2B);\n    zfree32(net->L3W);\n    zfree32(net->G2W); net->G2W = NULL;\n\n    net->L1WT =",
        "reload-free")
    s = once(s,
        "    memcpy(net->L3W,  buf+off, NN_L3_IN);      off += NN_L3_IN;\n    memcpy(&net->L3B, buf+off, 4);\n\n    net->ready = 1;",
        "    memcpy(net->L3W,  buf+off, NN_L3_IN);      off += NN_L3_IN;\n"
        "    memcpy(&net->L3B, buf+off, 4);             off += 4;\n\n"
        "    enum { NN_GLOBAL = 31 };\n"
        "    if (len >= off + 12 && memcmp(buf + off, \"GLB2\", 4) == 0) {\n"
        "        uint32_t gdims[2]; memcpy(gdims, buf + off + 4, 8);\n"
        "        if (gdims[0] != NN_GLOBAL || gdims[1] != NN_L2_OUT) {\n"
        "            fprintf(stderr, \"[NNUE] GLB2 dim mismatch %u/%u\\n\", gdims[0], gdims[1]);\n"
        "            return -1;\n"
        "        }\n"
        "        off += 12;\n"
        "        size_t gsz = (size_t)NN_GLOBAL * NN_L2_OUT;\n"
        "        if (len < off + gsz) { fprintf(stderr, \"[NNUE] truncated GLB2 trailer\\n\"); return -1; }\n"
        "        net->G2W = (int8_t *)zmalloc32(gsz);\n"
        "        if (!net->G2W) { fprintf(stderr, \"[NNUE] GLB2 malloc failed\\n\"); return -1; }\n"
        "        memcpy(net->G2W, buf + off, gsz);\n"
        "        fprintf(stderr, \"[NNUE] GLB2 global L2 projection enabled (31->20)\\n\");\n"
        "    }\n\n"
        "    net->ready = 1;",
        "trailer-load")

    marker = "/* Shared forward pass. Returns centipawns from the point of view of `stm`.\n * The 96-byte L2 input is always concatenated as [stm 48 | opp 48]. */\n"
    helpers = r'''/* ── Optional GLB2 global features, Q=QA_EFF=254 ─────────────── */
#define NN_GLOBAL 31
static inline int _g2_pcnt64(uint64_t x) { return __builtin_popcountll(x); }

static uint8_t _g2_passed_files(uint64_t own, uint64_t opp, int white) {
    uint8_t mask=0; uint64_t x=own;
    while(x){
        int sq=__builtin_ctzll(x); x&=x-1;
        int f=sq&7, r=sq>>3, passed=1; uint64_t y=opp;
        while(y){
            int osq=__builtin_ctzll(y); y&=y-1;
            int of=osq&7, orow=osq>>3;
            if(of<f-1||of>f+1) continue;
            if((white&&orow<r)||(!white&&orow>r)){passed=0;break;}
        }
        if(passed) mask|=(uint8_t)(1u<<f);
    }
    return mask;
}

static void _g2_features(uint16_t q[NN_GLOBAL], const uint64_t bb[12], int perspective) {
    static const int maxc[6]={8,2,2,2,1,1};
    static const int matv[6]={1,3,3,5,9,0};
    int cw[6],cb[6];
    for(int i=0;i<6;i++){cw[i]=_g2_pcnt64(bb[i]);cb[i]=_g2_pcnt64(bb[6+i]);}
    const int *own=perspective==0?cw:cb, *opp=perspective==0?cb:cw;
    for(int i=0;i<6;i++){
        q[i]=(uint16_t)((own[i]*NN_QA_EFF+maxc[i]/2)/maxc[i]);
        q[6+i]=(uint16_t)((opp[i]*NN_QA_EFF+maxc[i]/2)/maxc[i]);
    }
    int mat=0; for(int i=0;i<6;i++) mat+=(cw[i]+cb[i])*matv[i];
    q[12]=(uint16_t)((mat*NN_QA_EFF+39)/78); q[13]=NN_QA_EFF;
    uint8_t pw=_g2_passed_files(bb[0],bb[6],1), pb=_g2_passed_files(bb[6],bb[0],0);
    uint8_t po=perspective==0?pw:pb, px=perspective==0?pb:pw;
    for(int f=0;f<8;f++){q[14+f]=(po&(1u<<f))?NN_QA_EFF:0;q[22+f]=(px&(1u<<f))?NN_QA_EFF:0;}
    if(bb[5]&&bb[11]){
        int wk=__builtin_ctzll(bb[5]),bk=__builtin_ctzll(bb[11]);
        int df=(wk&7)-(bk&7);if(df<0)df=-df; int dr=(wk>>3)-(bk>>3);if(dr<0)dr=-dr;
        int d=df>dr?df:dr;q[30]=(uint16_t)((d*NN_QA_EFF+3)/7);
    }else q[30]=0;
}

static void _g2_board_bb(const uint8_t *board,uint64_t bb[12]){
    memset(bb,0,12*sizeof(uint64_t));
    for(int sq=0;sq<64;sq++){
        uint8_t pc=board[sq];if(!pc)continue;int t=PC_TYPE(pc)-1;if(t<0||t>5)continue;
        int idx=(PC_COLOR(pc)==COL_W)?t:6+t;bb[idx]|=1ULL<<sq;
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
    s = once(s,
        "    const float    OutScale = net->OutScale;",
        "    const float    OutScale = net->OutScale;\n    const int8_t  *G2W      = net->G2W;",
        "hot-pointer")

    inject_marker = """#endif

    /* Shift + ClippedReLU -> 20 uint8 values in [0,QB]. */"""
    inject = """#endif

    if (G2W) {
        uint64_t local_bb[12]; const uint64_t *gbb=bb_in;
        if(!gbb){_g2_board_bb(board,local_bb);gbb=local_bb;}
        uint16_t q[NN_GLOBAL]; _g2_features(q,gbb,stm);
        for(int o=0;o<NN_L2_OUT;o++){
            int32_t gs=0;
            for(int f=0;f<NN_GLOBAL;f++) gs+=(int32_t)q[f]*(int32_t)G2W[f*NN_L2_OUT+o];
            acc2[o]+=gs;
        }
    }

    /* Shift + ClippedReLU -> 20 uint8 values in [0,QB]. */"""
    s = once(s, inject_marker, inject, "l2-global")
    s = once(s,
        "    return _nnue_forward(na, stm, board);\n}\n\n/* bb[] and board_hash are retained for the common search signature; compact\n * NNU4 does not use the NNU3 extra-feature cache that required them. */",
        "    return _nnue_forward(na, stm, board, NULL);\n}\n\n/* bb[] feeds the optional GLB2 global L2 side channel; board_hash remains unused. */",
        "eval-wrapper")
    s = once(s,
        "    (void)bb; (void)board_hash;\n    return _nnue_forward(na, stm, board);",
        "    (void)board_hash;\n    return _nnue_forward(na, stm, board, bb);",
        "eval-bb-wrapper")

    p.write_text(s, encoding="utf-8")
    print(f"materialized GLB2 runtime: {a.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
