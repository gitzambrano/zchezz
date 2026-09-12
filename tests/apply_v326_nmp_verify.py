#!/usr/bin/env python3
"""Add high-depth verification to the v3.26 NMP+2 candidate.

Run this after applying the combined base and ``nmp-plus2`` with
``tests/apply_v326_candidate.py``. Defaults are useful without CLI flags.
"""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v325/search.c")
VERIFY_DEPTH = 12


def exact(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {n}")
    return text.replace(old, new, 1)


def apply(text: str, verify_depth: int) -> str:
    text = exact(
        text,
        "    int prev_static_eval[MAX_PLY];\n",
        "    int prev_static_eval[MAX_PLY];\n    int nmp_min_ply;\n",
        "SearchState NMP verification state",
    )
    text = exact(
        text,
        "    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta) {\n",
        "    if (!in_check && !is_pv && depth>=3 && ply>0 && not_endgame && static_eval>=beta &&\n"
        "        ply >= ss->nmp_min_ply) {\n",
        "NMP verification eligibility guard",
    )
    text = exact(
        text,
        "        if (null_score >= beta) return beta;\n",
        f"""        if (null_score >= beta) {{
            /* Verify high-depth null cutoffs on the original position.  While
             * verification is active, suppress recursive NMP until the search
             * has descended far enough; this mirrors the architectural idea
             * used by Stockfish without copying its tuned depth constants. */
            if (ss->nmp_min_ply || depth < {verify_depth}) return beta;

            int vdepth = depth - 1 - R;
            if (vdepth < 1) vdepth = 1;
            int span = (3 * vdepth) / 4;
            if (span < 1) span = 1;
            int saved_nmp_min_ply = ss->nmp_min_ply;
            ss->nmp_min_ply = ply + span;

            Move verify_pv[MAX_PLY]; int verify_len = 0;
            int verify_score = alpha_beta(ss, b, vdepth, beta-1, beta,
                                          verify_pv, &verify_len, ply, -1);
            ss->nmp_min_ply = saved_nmp_min_ply;
            if (verify_score >= beta) return beta;
        }}
""",
        "NMP verification search",
    )
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--verify-depth", type=int, default=VERIFY_DEPTH)
    args = ap.parse_args()
    if args.verify_depth < 4:
        raise SystemExit("--verify-depth must be >= 4")
    before = args.source.read_text(encoding="utf-8")
    after = apply(before, args.verify_depth)
    args.source.write_text(after, encoding="utf-8")
    print(f"applied nmp-plus2 verification depth={args.verify_depth} to {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
