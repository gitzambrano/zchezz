#!/usr/bin/env python3
"""Instrument false-negative gives_check hints without changing search decisions."""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v326/search.c")

DECL = r'''

/* GIVES_CHECK_DIAGNOSTICS: counters only; search decisions remain baseline. */
static unsigned long long g_gc_moves;
static unsigned long long g_gc_unprobed;
static unsigned long long g_gc_false_negative;
static unsigned long long g_gc_pawn_false_negative;
static unsigned long long g_gc_ep_false_negative;
static void gcheck_diag_report(void) {
    fprintf(stderr,
        "[GCHECK_DIAG] moves=%llu unprobed=%llu false_negative=%llu pawn_false_negative=%llu ep_false_negative=%llu\n",
        g_gc_moves, g_gc_unprobed, g_gc_false_negative,
        g_gc_pawn_false_negative, g_gc_ep_false_negative);
}
#if defined(__GNUC__) || defined(__clang__)
__attribute__((constructor))
#endif
static void gcheck_diag_register(void) { atexit(gcheck_diag_report); }
'''

OLD = '''int gives_check = 0;
                    { uint8_t gpt=b->b[m->to]&7,gksq=b->turn==COL_W?b->wk:b->bk;
                      int gdr=((m->to>>3)-(gksq>>3)); if(gdr<0)gdr=-gdr;
                      int gdc=((m->to&7)-(gksq&7));   if(gdc<0)gdc=-gdc;
                      if (gpt>=3||gpt==2||m->prom||(gdr>gdc?gdr:gdc)<=2)
                          gives_check = board_in_check(b);
                    }'''

# Same body with neutral indentation. We replace the condition/body rather than
# relying on the surrounding indentation, which differs between move stages.
COND_BODY = '''if (gpt>=3||gpt==2||m->prom||(gdr>gdc?gdr:gdc)<=2)
                          gives_check = board_in_check(b);'''

NEW_BODY = '''int fast_probe = (gpt>=3||gpt==2||m->prom||(gdr>gdc?gdr:gdc)<=2);
                      int exact_check_diag = board_in_check(b);
                      g_gc_moves++;
                      if (!fast_probe) {
                          g_gc_unprobed++;
                          if (exact_check_diag) {
                              g_gc_false_negative++;
                              if (gpt == 1) g_gc_pawn_false_negative++;
                              if (m->epc) g_gc_ep_false_negative++;
                          }
                      }
                      if (fast_probe) gives_check = exact_check_diag;'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    args = ap.parse_args()
    text = args.source.read_text(encoding="utf-8")

    inc = '#include <time.h>\n'
    if text.count(inc) != 1:
        raise RuntimeError("expected one time.h include")
    text = text.replace(inc, inc + DECL, 1)

    count = text.count(COND_BODY)
    if count != 4:
        raise RuntimeError(f"expected four gives_check fast paths, found {count}")
    text = text.replace(COND_BODY, NEW_BODY)

    args.source.write_text(text, encoding="utf-8")
    print(f"Instrumented {count} gives_check fast paths in {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
