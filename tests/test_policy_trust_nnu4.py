import sys
from pathlib import Path
import torch

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from train.teaching.train_policy_trust_nnu4 import normalized_logit_drift


def test_trust_penalty_is_zero_for_identical_outputs():
    p=torch.tensor([0.2,0.5,0.8],dtype=torch.float32)
    v=normalized_logit_drift(p,p.clone(),35.0)
    assert float(v) < 1e-12


def test_trust_penalty_grows_with_eval_drift():
    base=torch.tensor([0.4,0.5,0.6],dtype=torch.float32)
    near=torch.tensor([0.41,0.51,0.61],dtype=torch.float32)
    far=torch.tensor([0.55,0.65,0.75],dtype=torch.float32)
    a=float(normalized_logit_drift(near,base,35.0))
    b=float(normalized_logit_drift(far,base,35.0))
    assert a>0
    assert b>a


def test_cp_scale_controls_penalty_strength():
    base=torch.tensor([0.5],dtype=torch.float32)
    student=torch.tensor([0.6],dtype=torch.float32)
    tight=float(normalized_logit_drift(student,base,20.0))
    loose=float(normalized_logit_drift(student,base,80.0))
    assert tight>loose
