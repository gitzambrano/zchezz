#!/usr/bin/env python3
"""Apply isolated v3.26 search candidates to a CI working copy of v3.25.

The default candidate removes the blanket one-ply extension applied to every
in-check alpha-beta node. Modern Stockfish does not use a blanket check
extension; check evasions are handled normally and qsearch handles checks at the
horizon. Keeping candidates as deterministic source transforms lets us compare
one architectural change at a time without altering main.
"""
from __future__ import annotations
import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v325/search.c")
CANDIDATE = "no-check-extension"


def exact(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {n}")
    return text.replace(old, new, 1)


def no_check_extension(text: str) -> str:
    return exact(
        text,
        "    if (in_check) depth++;\n\n    int is_pv = (beta - alpha > 1);\n",
        "    /* v3.26 candidate: no blanket check extension. Check evasions remain\n"
        "     * fully searched, and qsearch handles in-check horizon nodes. */\n\n"
        "    int is_pv = (beta - alpha > 1);\n",
        "blanket check extension",
    )


def stale_miss(text: str) -> str:
    old = """        if (tt_age(e, gen) != 0) {
            out->score = TT_EVAL_NONE;
            out->depth = 0;
            out->flag = TT_UPPER;
            out->static_eval = TT_EVAL_NONE;
            return 2;
        }
"""
    return exact(text, old, "        if (tt_age(e, gen) != 0) continue;\n", "stale TT move-only")


TRANSFORMS = {
    "no-check-extension": no_check_extension,
    "stale-miss": stale_miss,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--candidate", choices=sorted(TRANSFORMS), default=CANDIDATE)
    args = ap.parse_args()
    before = args.source.read_text(encoding="utf-8")
    after = TRANSFORMS[args.candidate](before)
    args.source.write_text(after, encoding="utf-8")
    print(f"applied candidate={args.candidate} to {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
