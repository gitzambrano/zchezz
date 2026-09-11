from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from train.teaching.backends import UciBackend  # noqa: E402
from train.teaching.format import FLAG_DISAGREEMENT  # noqa: E402
from train.teaching.methods import (  # noqa: E402
    TeachingContext, compute_interest, stable_fraction,
)


class Board:
    turn = True


def cfg():
    return SimpleNamespace(
        GAP_FULL_SCALE_CP=400,
        GAP_HARD_CP=120,
        W_GAP=1.0,
        MARGIN_FULL_SCALE_CP=180,
        LOW_MARGIN_CP=35,
        W_MARGIN=0.35,
        POLICY_TEMPERATURE_CP=120.0,
        HIGH_ENTROPY=0.75,
        W_ENTROPY=0.35,
        HARD_INTEREST=0.9,
    )


def test_gap_mining_detects_large_teacher_student_residual():
    context = TeachingContext(
        Board(), None, cfg(), source_cp=0, student_cp=0, static_cp=400)
    score = compute_interest(context)
    assert score >= 1.0
    assert context.flags & FLAG_DISAGREEMENT


def test_stable_fraction_is_deterministic():
    fen = "8/8/8/8/8/8/8/K6k w - - 0 1"
    assert stable_fraction(fen) == stable_fraction(fen)
    assert 0 <= stable_fraction(fen) < 1


def test_uci_backend_static_eval_and_search_pov(tmp_path):
    fake = tmp_path / "fake_uci.py"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "for raw in sys.stdin:\n"
        "    cmd=raw.strip()\n"
        "    if cmd=='uci': print('id name FakeTeacher'); print('uciok'); sys.stdout.flush()\n"
        "    elif cmd=='isready': print('readyok'); sys.stdout.flush()\n"
        "    elif cmd=='eval': print('Final evaluation +0.42 (white side)'); sys.stdout.flush()\n"
        "    elif cmd.startswith('go '):\n"
        "        print('info depth 1 multipv 1 score cp 50 pv e7e5'); print('bestmove e7e5'); sys.stdout.flush()\n"
        "    elif cmd=='quit': break\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    with UciBackend(fake) as backend:
        assert backend.static_eval(
            "8/8/8/8/8/8/8/K6k w - - 0 1", True) == 42
        lines = backend.search(
            "8/8/8/8/8/8/8/K6k b - - 0 1", False, nodes=1, multipv=1)
        assert len(lines) == 1
        assert lines[0].move == "e7e5"
        assert lines[0].cp_white == -50
