#!/usr/bin/env python3
"""Fix false-negative gives_check hints for pawn-discovered checks.

The move has already been made when the patched code runs. The existing fast
path asks board_in_check() for every non-pawn move, promotions, and moves whose
destination is near the enemy king. A pawn move far from the king can still give
check by vacating a rook/bishop/queen line. En-passant can additionally uncover
a line by removing the captured pawn from a third square.
"""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v326/search.c")


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
                  /* Vacating the FROM square can uncover a slider. En-passant
                   * can also uncover one by removing the captured pawn from a
                   * third square, so verify every EP capture exactly. */
                  pawn_discovery = m->epc || (gfr==gkr) || (gfc==gkc) || (gfdr==gfdc);
              }
              if (gpt>=3||gpt==2||m->prom||(gdr>gdc?gdr:gdc)<=2||pawn_discovery)"""

    text = text.replace(condition, replacement)
    args.source.write_text(text, encoding="utf-8")
    print(f"Patched {count} gives_check fast paths in {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
