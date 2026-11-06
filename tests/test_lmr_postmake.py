"""Regression: LMR history must index the moved piece after board_make."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_lmr_uses_destination_occupied_after_make():
    src=(ROOT/"engine/c/zchezz_v335/search.c").read_text(encoding="utf-8")
    first=src.index("board_make(b, m);", src.index("/* ── STAGE 3"))
    lmr=src.index("uint8_t p_lmr =", first)
    unmake=src.index("board_unmake(b);", lmr)
    assert first < lmr < unmake
    assert "uint8_t p_lmr = b->b[mto];" in src[lmr:lmr+120]
    assert "uint8_t p_lmr = b->b[mfr];" not in src
    assert "piece_index(p_lmr)" in src[lmr:lmr+300]
