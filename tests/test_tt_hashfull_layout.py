"""TT hashfull samples real packed entries, not padding between clusters."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_hashfull_samples_three_entries_per_32_byte_cluster():
    source=(ROOT/"engine/c/zchezz_v335/search.c").read_text(encoding="utf-8")
    begin=source.index("int tt_hashfull_permille(void)")
    end=source.index("static inline void tt_prefetch", begin)
    fn=source[begin:end]
    assert "TTEntry10 *e = &g_tt[i / 3].e[i % 3]" in fn
    assert "TTEntry10 *flat = (TTEntry10 *)g_tt" not in fn
    assert "tt_age(e, gen)" in fn
