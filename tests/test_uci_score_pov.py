"""Contract: every runner that records engine scores stores them White-relative.

Zchezz engines report ``score cp`` White-relative. The active lines (v335,
v510, v605) print ``score mate`` White-relative too; older builds print it with
no usable sign. Standard UCI engines report the side to move. The runners must
store the same White-relative value for the same position whichever engine
searched it. The integration cases use decisive positions (one side a queen
up) with both sides to move. A missing binary skips its case, which is missing
evidence, not a pass.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "utils"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))

import uci_score as us  # noqa: E402


# ── parser ───────────────────────────────────────────────────────────────────

def test_pov_detection():
    assert us.pov_from_id_name("Zchezz 3.35") == us.WHITE
    assert us.pov_from_id_name("Stockfish 17") == us.STM
    assert us.pov_from_id_name(None) == us.STM
    assert us.resolve_pov("stm", "Zchezz 3.35") == us.STM
    with pytest.raises(ValueError):
        us.resolve_pov("black", "x")


@pytest.mark.parametrize("pov,white_to_move,line,expected", [
    (us.STM,   True,  "info depth 9 score cp 120 pv e2e4", 120),
    (us.STM,   False, "info depth 9 score cp 120 pv e7e5", -120),
    (us.WHITE, True,  "info depth 9 score cp 120 pv e2e4", 120),
    (us.WHITE, False, "info depth 9 score cp 120 pv e7e5", 120),
    (us.STM,   False, "info depth 9 score mate 3 pv d8d1", -19000),
    (us.STM,   True,  "info depth 9 score mate -2 pv e1e2", -19000),
    (us.STM,   True,  "info depth 9 score mate 0", -19000),
])
def test_single_line(pov, white_to_move, line, expected):
    assert us.SearchScores(pov, white_to_move).feed(line) == expected


def test_zchezz_mate_takes_sign_from_last_cp():
    s = us.SearchScores(us.WHITE, white_to_move=False)
    assert s.feed("info depth 1 score mate 5 pv d8d1") is None   # no cp yet: sign unknown
    assert s.feed("info depth 16 score cp -1063 pv d8d3") == -1063
    assert s.feed("info depth 17 score mate 29 pv d8d3") == -19000
    m = us.SearchScores(us.WHITE, white_to_move=True)
    m.feed("info depth 3 multipv 2 score cp -40 pv a2a3")
    m.feed("info depth 3 multipv 1 score cp 900 pv d1d7")
    assert m.feed("info depth 4 multipv 2 score mate 7 pv a2a3") == -19000
    assert m.feed("info depth 4 multipv 1 score mate 7 pv d1d7") == 19000


def test_no_score():
    assert us.SearchScores(us.STM, True).feed("info string hello") is None


# ── runners with real engines ────────────────────────────────────────────────

POSITIONS = [  # (fen, expected White-relative sign)
    ("3qk3/8/8/8/8/8/8/4K3 b - - 0 1", -1),
    ("3qk3/8/8/8/8/8/8/4K3 w - - 0 1", -1),
    ("4k3/8/8/8/8/8/8/3QK3 b - - 0 1", +1),
    ("4k3/8/8/8/8/8/8/3QK3 w - - 0 1", +1),
]


def _engines():
    out = []
    for prof in ("v335", "v328", "v327", "v331", "v507", "v510", "v605"):
        out.append((prof, ROOT / "engine" / "c" / f"zchezz_{prof}" / "zchezz.exe"))
    sf = os.environ.get("ZCHEZZ_STOCKFISH") or str(ROOT / "engine" / "stockfish" / "stockfish.exe")
    out.append(("stockfish", Path(sf)))
    return out


def _sign(x):
    return (x > 0) - (x < 0)


@pytest.mark.parametrize("label,exe", _engines(), ids=[e[0] for e in _engines()])
@pytest.mark.parametrize("runner", ["selfplay", "tournament"])
def test_runner_stores_white_relative(runner, label, exe):
    if not exe.is_file():
        pytest.skip(f"{label} binary not built: {exe}")
    chess = pytest.importorskip("chess")
    if runner == "selfplay":
        import _run_selfplay_core as core
        eng = core.EngineInstance(str(exe), label, tc_mode="movetime", tc_value=100)
    else:
        import _run_tournament_quick_core as core
        eng = core.EngineInstance(str(exe), label, tc_mode="movetime", tc_value=100)
    assert eng.start(), f"{label} did not start"
    try:
        for fen, sign in POSITIONS:
            eng.start_fen = fen
            res = eng.get_move(chess.Board(fen))
            move, score = res[0], res[1]
            assert move, f"{label}: no move for {fen}"
            assert score is not None and _sign(score) == sign, \
                f"{runner}/{label}: {fen} stored {score}, expected sign {sign:+d}"
    finally:
        eng.stop()


def test_selfplay_bin_round_trip_is_white_relative():
    """A White-relative runner score survives the .bin (side-to-move) encoding."""
    chess = pytest.importorskip("chess")
    np = pytest.importorskip("numpy")
    import _run_selfplay_core as core
    from train.dataset import SAMPLE_DTYPE
    for fen, white_cp in (("3qk3/8/8/8/8/8/8/4K3 b - - 0 1", -900), ("4k3/8/8/8/8/8/8/3QK3 b - - 0 1", 900)):
        b = chess.Board(fen)
        mv = next(iter(b.legal_moves))
        rec = np.frombuffer(core.build_bin_records([{"fen": fen, "score": white_cp, "move": mv}], None),
                            dtype=SAMPLE_DTYPE)[0]
        stored_white = int(rec["eval_cp"]) if rec["stm"] == 0 else -int(rec["eval_cp"])
        assert stored_white == white_cp


@pytest.mark.parametrize("label,exe", _engines(), ids=[e[0] for e in _engines()])
def test_teaching_backend_is_white_relative(label, exe):
    """train/teaching/backends.py: search and static eval are White-relative."""
    if not exe.is_file():
        pytest.skip(f"{label} binary not built: {exe}")
    from train.teaching.backends import UciBackend
    with UciBackend(exe, 16, 1, 64) as be:
        for fen, sign in POSITIONS:
            white_to_move = fen.split()[1] == "w"
            lines = be.search(fen, white_to_move, movetime_ms=100, multipv=2)
            assert lines and _sign(lines[0].cp_white) == sign, f"search {label} {fen}: {lines}"
            st = be.static_eval(fen, white_to_move)
            assert _sign(st) == sign, f"static_eval {label} {fen}: {st}"


@pytest.mark.parametrize("module", ["process_positions", "generate_endgames"])
def test_stockfish_teachers_refuse_zchezz(module):
    """Teacher wrappers assume side-to-move scores and must refuse Zchezz."""
    exe = ROOT / "engine" / "c" / "zchezz_v335" / "zchezz.exe"
    if not exe.is_file():
        pytest.skip("v335 binary not built")
    sys.path.insert(0, str(ROOT / "train" / "labeling"))
    sys.path.insert(0, str(ROOT / "train"))
    mod = __import__(module)
    with pytest.raises(RuntimeError, match="standard UCI"):
        if module == "process_positions":
            mod._StockfishEngine(str(exe), 1000, 16, 20)
        else:
            mod.SF_PATH = str(exe)
            mod.StockfishEngine()


MATE_IN_1 = [  # (fen, White-relative sign of the mate)
    ("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", +1),      # Ra8#
    ("r5k1/8/8/8/8/8/5PPP/6K1 b - - 0 1", -1),      # Ra1#
]


@pytest.mark.parametrize("prof", ["v335", "v510", "v605"])
def test_active_engines_print_white_relative_mate(prof):
    """main.c uci_info_cb: mate_in > 0 when White mates, < 0 when Black mates."""
    import re
    import subprocess
    exe = ROOT / "engine" / "c" / f"zchezz_{prof}" / "zchezz.exe"
    if not exe.is_file():
        pytest.skip(f"{prof} binary not built: {exe}")
    for fen, sign in MATE_IN_1:
        cmds = f"uci\nisready\nposition fen {fen}\ngo depth 6\n"
        p = subprocess.Popen([str(exe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, cwd=str(exe.parent))
        p.stdin.write(cmds); p.stdin.flush()
        mates = []
        for line in p.stdout:
            m = re.search(r"score mate (-?\d+)", line)
            if m:
                mates.append(int(m.group(1)))
            if line.startswith("bestmove"):
                break
        p.stdin.write("quit\n"); p.stdin.flush(); p.wait(timeout=10)
        assert mates and mates[-1] == sign, f"{prof} {fen}: mate scores {mates}, expected {sign:+d}"
