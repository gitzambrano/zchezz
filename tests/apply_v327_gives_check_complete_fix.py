#!/usr/bin/env python3
"""Apply the complete v3.27 gives_check correctness fix.

Pawn moves can uncover slider checks by vacating their origin square. En-passant
can additionally uncover a line by removing the captured pawn from a third
square, so every EP capture is verified with board_in_check().
"""
from pathlib import Path

p = Path("engine/c/zchezz_v326/search.c")
s = p.read_text(encoding="utf-8")
cond = "if (gpt>=3||gpt==2||m->prom||(gdr>gdc?gdr:gdc)<=2)"
count = s.count(cond)
if count != 4:
    raise RuntimeError(f"expected four gives_check fast paths, found {count}")

repl = """int pawn_discovery = 0;
              if (gpt == 1) {
                  int gfr=m->from>>3, gfc=m->from&7, gkr=gksq>>3, gkc=gksq&7;
                  int gfdr=gfr-gkr; if(gfdr<0)gfdr=-gfdr;
                  int gfdc=gfc-gkc; if(gfdc<0)gfdc=-gfdc;
                  pawn_discovery = (gfr==gkr) || (gfc==gkc) || (gfdr==gfdc);
              }
              if (gpt>=3||gpt==2||m->prom||m->epc||(gdr>gdc?gdr:gdc)<=2||pawn_discovery)"""

p.write_text(s.replace(cond, repl), encoding="utf-8")
print(f"patched {count} gives_check fast paths")
