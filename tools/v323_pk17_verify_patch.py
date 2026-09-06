#!/usr/bin/env python3
"""Add test-only PK17 invariant verification to a generated v3.23 candidate."""
from pathlib import Path
import argparse


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    a = ap.parse_args()

    h = a.root / "nnue.h"
    hs = h.read_text(encoding="utf-8")
    decl = """
#ifdef PK17_VERIFY
int nnue_pk17_verify(const NnueAccum *na, const uint8_t *board);
#endif
"""
    if "nnue_pk17_verify" not in hs:
        h.write_text(hs + decl, encoding="utf-8")

    c = a.root / "nnue.c"
    cs = c.read_text(encoding="utf-8")
    impl = r'''

#ifdef PK17_VERIFY
/* Rebuild the PK17 state and both projected accumulators from the mailbox and
 * compare them with the live incremental state.  Return bitmask:
 *   1 state mismatch, 2 white projection mismatch, 4 black projection mismatch.
 * This is intentionally test-only and is never present in production builds. */
int nnue_pk17_verify(const NnueAccum *na, const uint8_t *board) {
    NnuePk17State s;
    int16_t aw[NN_L1_OUT] __attribute__((aligned(32)));
    int16_t ab[NN_L1_OUT] __attribute__((aligned(32)));
    int rc = 0;
    _pk17_from_board(&s, board);
    if (s.pawns_w != na->pk17_state.pawns_w ||
        s.pawns_b != na->pk17_state.pawns_b ||
        s.king_w != na->pk17_state.king_w ||
        s.king_b != na->pk17_state.king_b ||
        s.passed_w != na->pk17_state.passed_w ||
        s.passed_b != na->pk17_state.passed_b ||
        s.king_dist != na->pk17_state.king_dist)
        rc |= 1;
    _pk17_project_full(aw, &s, 0);
    _pk17_project_full(ab, &s, 1);
    if (memcmp(aw, na->pk17_acc_w, sizeof(aw)) != 0) rc |= 2;
    if (memcmp(ab, na->pk17_acc_b, sizeof(ab)) != 0) rc |= 4;
    return rc;
}
#endif
'''
    if "int nnue_pk17_verify(" not in cs:
        c.write_text(cs + impl, encoding="utf-8")


if __name__ == "__main__":
    main()
