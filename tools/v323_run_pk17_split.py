#!/usr/bin/env python3
"""Run the PK17 patcher with the scalar fallback edit scoped to nnue_eval_bb.

The source has the same scalar accumulator expression in nnue_eval and
nnue_eval_bb. The PK17 experiment only changes the search fast path, so patch
the second occurrence instead of requiring the expression to be unique.
"""
from pathlib import Path

src_path = Path(__file__).with_name("v323_apply_pk17_split.py")
src = src_path.read_text(encoding="utf-8")
needle = '    t = one(t, old, new, "nnue.c scalar split sum")\n'
replacement = '''    n=t.count(old)\n    if n!=2:\n        raise SystemExit(f"nnue.c scalar split sum: expected two matches, found {n}")\n    pos=t.rfind(old)\n    t=t[:pos]+new+t[pos+len(old):]\n'''
if src.count(needle) != 1:
    raise SystemExit("PK17 patcher bootstrap target not unique")
src = src.replace(needle, replacement, 1)
ns = {"__name__": "__main__", "__file__": str(src_path)}
exec(compile(src, str(src_path), "exec"), ns, ns)
