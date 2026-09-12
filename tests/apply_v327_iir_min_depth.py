#!/usr/bin/env python3
"""Raise Zchezz IIR minimum depth while keeping all other IIR semantics fixed."""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v326/search.c")
OLD = "if (!pv_move.from && !pv_move.to && depth>=3 && !in_check && depth-1>=2) depth--;"


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-depth",type=int,choices=(4,5,6),required=True)
    ap.add_argument("--source",type=Path,default=SOURCE)
    a=ap.parse_args()
    text=a.source.read_text(encoding="utf-8")
    if text.count(OLD)!=1:
        raise RuntimeError(f"expected one IIR condition, found {text.count(OLD)}")
    new=f"if (!pv_move.from && !pv_move.to && depth>={a.min_depth} && !in_check) depth--;"
    a.source.write_text(text.replace(OLD,new,1),encoding="utf-8")
    print(f"Raised IIR minimum depth to {a.min_depth} in {a.source}")
    return 0

if __name__=='__main__': raise SystemExit(main())
