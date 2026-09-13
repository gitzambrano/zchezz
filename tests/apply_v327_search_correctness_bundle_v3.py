#!/usr/bin/env python3
"""Apply the v3.27 search-correctness bundle robustly to promoted v3.26.

This version keeps the v2 pruning fixes but replaces all post-move gives_check
fast paths independent of indentation.  Promoted v3.26 contains eight such
paths, not four.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import apply_v327_search_correctness_bundle as v2

SOURCE = Path("engine/c/zchezz_v326/search.c")

GC_PATTERN = re.compile(
    r"(?m)^(?P<i>[ \t]*)int gives_check = 0;\n"
    r"(?P=i)\{ uint8_t gpt=b->b\[m->to\]&7,gksq=b->turn==COL_W\?b->wk:b->bk;\n"
    r"(?P=i)  int gdr=\(\(m->to>>3\)-\(gksq>>3\)\); if\(gdr<0\)gdr=-gdr;\n"
    r"(?P=i)  int gdc=\(\(m->to&7\)-\(gksq&7\)\);   if\(gdc<0\)gdc=-gdc;\n"
    r"(?P=i)  if \(gpt>=3\|\|gpt==2\|\|m->prom\|\|\(gdr>gdc\?gdr:gdc\)<=2\)\n"
    r"(?P=i)      gives_check = board_in_check\(b\);\n"
    r"(?P=i)\}\n"
)


def replace_gc(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        i = m.group("i")
        return (
            f"{i}int gives_check = 0;\n"
            f"{i}{{ uint8_t gpt=b->b[m->to]&7,gksq=b->turn==COL_W?b->wk:b->bk;\n"
            f"{i}  int gdr=((m->to>>3)-(gksq>>3)); if(gdr<0)gdr=-gdr;\n"
            f"{i}  int gdc=((m->to&7)-(gksq&7));   if(gdc<0)gdc=-gdc;\n"
            f"{i}  int pawn_discovery = 0;\n"
            f"{i}  if (gpt == 1) {{\n"
            f"{i}      int gfr=m->from>>3, gfc=m->from&7, gkr=gksq>>3, gkc=gksq&7;\n"
            f"{i}      int gfdr=gfr-gkr; if(gfdr<0)gfdr=-gfdr;\n"
            f"{i}      int gfdc=gfc-gkc; if(gfdc<0)gfdc=-gfdc;\n"
            f"{i}      pawn_discovery = (gfr==gkr) || (gfc==gkc) || (gfdr==gfdc);\n"
            f"{i}  }}\n"
            f"{i}  if (gpt>=3||gpt==2||m->prom||m->epc||(gdr>gdc?gdr:gdc)<=2||pawn_discovery)\n"
            f"{i}      gives_check = board_in_check(b);\n"
            f"{i}}}\n"
        )

    out, n = GC_PATTERN.subn(repl, text)
    if n != 8:
        raise RuntimeError(f"post-move gives_check blocks: expected 8 matches, found {n}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    args = ap.parse_args()

    s = args.source.read_text(encoding="utf-8")
    s = v2.replace_exact(s, v2.OLD_HELPER, v2.NEW_HELPER, 1, "check helper")
    s = v2.replace_exact(s, v2.OLD_LMP, v2.NEW_LMP, 1, "LMP/history block")
    s = v2.replace_exact(s, v2.OLD_QSEE, v2.NEW_QSEE, 1, "quiet SEE block")
    s = v2.replace_exact(s, v2.OLD_BAD_CAPTURE, v2.NEW_BAD_CAPTURE, 1, "losing-capture SEE block")
    s = replace_gc(s)

    old_iir = "     *   depth >= 4, not in check, reduced depth still >= 2 */"
    new_iir = "     *   depth >= 3, not in check, reduced depth still >= 2 */"
    s = v2.replace_exact(s, old_iir, new_iir, 1, "IIR comment")

    args.source.write_text(s, encoding="utf-8")
    print(f"Applied v3 search correctness bundle to {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
