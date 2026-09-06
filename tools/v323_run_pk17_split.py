#!/usr/bin/env python3
"""Generate the v3.23 PK17 split candidate.

By default this applies both the PK17 split and the multithread hardening found
while validating the experiment.  Use --raw only in diagnostic workflows that
need to reproduce the original unsafe candidate (for example TSan isolation).

The PK17 source patcher needs one bootstrap adjustment: the scalar accumulator
expression occurs in both nnue_eval and nnue_eval_bb, while PK17 changes only
the search fast path.  We therefore patch the second occurrence.
"""
from pathlib import Path
import argparse
import subprocess
import sys


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--raw", action="store_true",
                    help="generate PK17 without the multithread hardening")
    args = ap.parse_args()

    src_path = Path(__file__).with_name("v323_apply_pk17_split.py")
    src = src_path.read_text(encoding="utf-8")
    needle = '    t = one(t, old, new, "nnue.c scalar split sum")\n'
    replacement = '''    n=t.count(old)\n    if n!=2:\n        raise SystemExit(f"nnue.c scalar split sum: expected two matches, found {n}")\n    pos=t.rfind(old)\n    t=t[:pos]+new+t[pos+len(old):]\n'''
    if src.count(needle) != 1:
        raise SystemExit("PK17 patcher bootstrap target not unique")
    src = src.replace(needle, replacement, 1)

    saved_argv = sys.argv
    try:
        sys.argv = [str(src_path), "--root", str(args.root)]
        ns = {"__name__": "__main__", "__file__": str(src_path)}
        exec(compile(src, str(src_path), "exec"), ns, ns)
    finally:
        sys.argv = saved_argv

    if not args.raw:
        hardening = Path(__file__).with_name("v323_apply_mt_hardening.py")
        subprocess.run(
            [sys.executable, str(hardening), "--root", str(args.root)],
            check=True,
        )
        print(f"PK17 candidate includes multithread hardening: {args.root}")


if __name__ == "__main__":
    main()
