"""Verify current dual-family documentation facts."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_current_docs_name_supported_profiles():
    for rel in ('AGENTS.md','CLAUDE.md','docs/architecture.md','docs/nnue.md','docs/repository-layout.md'):
        text=(ROOT/rel).read_text(encoding='utf-8'); assert 'v325' in text and 'v500' in text
def test_current_docs_do_not_name_v4_as_supported():
    for rel in ('AGENTS.md','CLAUDE.md','docs/architecture.md','docs/nnue.md','docs/repository-layout.md'):
        text=(ROOT/rel).read_text(encoding='utf-8').lower(); assert 'v403 core' not in text; assert 'active development candidate: `engine/c/zchezz_v403/`' not in text
