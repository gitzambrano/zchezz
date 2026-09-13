import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from train.teaching.train_policy_distill_nnu4 import (
    child_value_probability,
    mix_teacher_policy,
    parent_pov_score,
    soft_policy,
)


def test_soft_policy_prefers_higher_parent_score_and_normalizes():
    p = soft_policy([120, 0, -120], temperature_cp=120)
    assert np.isclose(float(p.sum()), 1.0)
    assert p[0] > p[1] > p[2]


def test_child_value_probability_reverses_parent_pov():
    p = child_value_probability([320, 0, -320])
    assert p[0] < 0.5
    assert np.isclose(float(p[1]), 0.5)
    assert p[2] > 0.5
    assert np.isclose(float(p[0] + p[2]), 1.0, atol=1e-6)


def test_parent_pov_score_uses_parent_color_not_child_stm():
    assert parent_pov_score(75, True) == 75
    assert parent_pov_score(75, False) == -75
    assert parent_pov_score(-40, True) == -40
    assert parent_pov_score(-40, False) == 40


def test_dual_teacher_policy_can_reverse_primary_preference_without_scale_leak():
    # Primary prefers move 0; in-family reference strongly prefers move 1.
    primary = np.array([90, 20, -150], dtype=np.float32)
    reference = np.array([-900, 2500, -1400], dtype=np.float32)
    mixed, rank = mix_teacher_policy(primary, reference, 120.0, 0.75)
    assert np.isclose(float(mixed.sum()), 1.0, atol=1e-6)
    assert int(np.argmax(mixed)) == 1
    assert int(np.argmax(rank)) == 1
    # Calibration is local: the 3400-cp reference gap must not survive raw.
    assert float(rank.max() - rank.min()) < 1000.0


def test_zero_reference_weight_is_primary_policy():
    primary = np.array([50, 0, -50], dtype=np.float32)
    reference = np.array([-500, 1000, 0], dtype=np.float32)
    mixed, rank = mix_teacher_policy(primary, reference, 120.0, 0.0)
    assert np.allclose(mixed, soft_policy(primary, 120.0))
    assert np.allclose(rank, primary - primary.max())
