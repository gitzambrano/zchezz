import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from train.teaching.train_policy_distill_nnu4 import child_value_probability, soft_policy


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
