#!/usr/bin/env python3
"""Fix rook direct-check classification used by quiet SEE pruning."""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE = Path("engine/c/zchezz_v326/search.c")
OLD = '''        case 3: return (bish_attacks(to, occ) >> ksq) & 1;
        case 4: case 5:
            return ((rook_attacks(to, occ) | bish_attacks(to, occ)) >> ksq) & 1;
'''
NEW = '''        case 3: return (bish_attacks(to, occ) >> ksq) & 1;
        case 4: return (rook_attacks(to, occ) >> ksq) & 1;
        case 5:
            return ((rook_attacks(to, occ) | bish_attacks(to, occ)) >> ksq) & 1;
'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=SOURCE)
    args = ap.parse_args()
    text = args.source.read_text(encoding="utf-8")
    count = text.count(OLD)
    if count != 1:
        raise RuntimeError(f"expected one quiet_direct_check rook/queen block, found {count}")
    args.source.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print(f"Fixed rook direct-check classification in {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
