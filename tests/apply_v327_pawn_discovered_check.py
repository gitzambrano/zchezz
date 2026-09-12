#!/usr/bin/env python3
"""Fix false-negative gives_check hints for pawn moves that uncover slider checks."""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v326/search.c")

OLD = """int gdr=((m->to>>3)-(gksq>>3)); if(gdr<0)gdr=-gdr;
"""
OLD2 = """int gdc=((m->to&7)-(gksq&7));   if(gdc<0)gdc=-gdc;
"""
COND = """if (gpt>=3||gpt==2||m->prom||(gdr>gdc?gdr:gdc)<=2)
"""


def transform_block(text: str) -> str:
    # The move has already been made. For pawns, the existing proximity test
    # detects direct pawn checks near the enemy king but can miss a discovered
    # rook/bishop/queen check when the pawn vacates a line far from the king.
    # A discovered slider check is possible only if the pawn FROM square lay on
    # the enemy king's rank, file, or diagonal. In that case pay for the exact
    # board_in_check() call; otherwise retain the cheap existing fast path.
    needle = OLD + "              " + OLD2 + "              " + COND
    # Indentation differs among the four staged-move blocks, so use a smaller
    # indentation-agnostic textual replacement of the condition itself after
    # inserting the alignment computation between gdc and the condition.
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    args = ap.parse_args()

    text = args.source.read_text(encoding="utf-8")
    condition = "if (gpt>=3||gpt==2||m->prom||(gdr>gdc?gdr:gdc)<=2)"
    count = text.count(condition)
    if count != 4:
        raise RuntimeError(f"expected four gives_check fast paths, found {count}")

    replacement = """int pawn_discovery = 0;
              if (gpt == 1) {
                  int gfr=m->from>>3, gfc=m->from&7, gkr=gksq>>3, gkc=gksq&7;
                  int gfdr=gfr-gkr; if(gfdr<0)gfdr=-gfdr;
                  int gfdc=gfc-gkc; if(gfdc<0)gfdc=-gfdc;
                  pawn_discovery = (gfr==gkr) || (gfc==gkc) || (gfdr==gfdc);
              }
              if (gpt>=3||gpt==2||m->prom||(gdr>gdc?gdr:gdc)<=2||pawn_discovery)"""
    text = text.replace(condition, replacement)
    args.source.write_text(text, encoding="utf-8")
    print(f"Patched {count} gives_check fast paths in {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
