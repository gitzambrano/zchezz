"""Protect the non-blocking WASM pondering contract."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_template_ponder_uses_bounded_worker_slices():
    text = _text("engine/build/zchezz_wasm.html")
    assert "window.zchezzPonderStart" in text
    assert "window.zchezzPonderCancel" in text
    assert "const PONDER_SLICE_MS = 80;" in text
    assert "const PONDER_YIELD_MS = 20;" in text
    assert "new Worker(" in text
    assert "timeLimitMs: PONDER_SLICE_MS" in text


def test_bundle_generator_preserves_ponder_api():
    text = _text("engine/build/bundle.py")
    assert "window.zchezzPonderStart" in text
    assert "window.zchezzPonderCancel" in text
    assert "PONDER_SLICE_MS = 80" in text
    assert "PONDER_YIELD_MS = 20" in text


def test_game_ponder_uses_pv_reply_and_stops_on_user_move():
    text = _text("engine/build/zchezz_wasm.html")
    assert "function startGamePonder(msg)" in text
    assert "const expected = pv[1];" in text
    assert "stopGamePonder('');" in text
    assert "startGamePonder(msg);" in text


def test_normal_search_cancels_future_ponder_slices():
    for relative in ("engine/build/zchezz_wasm.html", "engine/build/bundle.py"):
        text = _text(relative)
        assert "window.zchezzSearch = (p, cb)" in text
        assert "cancelPonder(); sendSearch(p, cb);" in text
