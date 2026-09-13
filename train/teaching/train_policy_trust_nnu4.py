#!/usr/bin/env python3
"""Trust-region policy distillation for NNU4.

The policy teacher is allowed to reshape move ordering, but a frozen copy of
v5.06 acts as a functional trust region on replay positions.  This directly
penalizes catastrophic forgetting in centipawn/logit space while keeping the
runtime architecture unchanged.  The best validation epoch is exported rather
than blindly using the final epoch.
"""
from __future__ import annotations

import argparse
import copy
import random
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "train"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from train.import_nnu4 import read_nnu4  # noqa: E402
from train.model import NNUE, clamp_weights_  # noqa: E402
from train.teaching.format import TeachingDataset, record_to_fen  # noqa: E402
from train.teaching.train_policy_distill_nnu4 import (  # noqa: E402
    _forward_fens,
    batch_loss,
    build_groups,
    evaluate,
)


def normalized_logit_drift(student: torch.Tensor, base: torch.Tensor,
                           scale_cp: float) -> torch.Tensor:
    """MSE of student/base eval drift normalized by an intuitive cp scale."""
    s = torch.logit(student.clamp(1e-6, 1 - 1e-6))
    b = torch.logit(base.clamp(1e-6, 1 - 1e-6))
    cp_delta = (s - b) * 320.0
    return torch.mean((cp_delta / max(1e-6, float(scale_cp))) ** 2)


def replay_penalty(model: NNUE, base: NNUE, fens: list[str], device: torch.device,
                   scale_cp: float) -> tuple[torch.Tensor, float]:
    if not fens:
        z = torch.zeros((), device=device)
        return z, 0.0
    pred = _forward_fens(model, fens, device).clamp(1e-6, 1 - 1e-6)
    with torch.no_grad():
        ref = _forward_fens(base, fens, device).clamp(1e-6, 1 - 1e-6)
    pen = normalized_logit_drift(pred, ref, scale_cp)
    with torch.no_grad():
        drift_cp = torch.mean(torch.abs((torch.logit(pred) - torch.logit(ref)) * 320.0))
    return pen, float(drift_cp.cpu())


def eval_trust(model: NNUE, base: NNUE, fens: list[str], device: torch.device,
               scale_cp: float, batch: int = 256) -> tuple[float, float]:
    if not fens:
        return 0.0, 0.0
    model.eval(); base.eval()
    sum_pen = sum_drift = 0.0; n = 0
    with torch.no_grad():
        for i in range(0, len(fens), batch):
            fs = fens[i:i + batch]
            p, d = replay_penalty(model, base, fs, device, scale_cp)
            m = len(fs)
            sum_pen += float(p.cpu()) * m
            sum_drift += d * m
            n += m
    return sum_pen / n, sum_drift / n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--init-weights", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--reference-engine", default="")
    ap.add_argument("--reference-nodes", type=int, default=2000)
    ap.add_argument("--reference-weight", type=float, default=0.45)
    ap.add_argument("--reference-hash-mb", type=int, default=32)
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--batch-groups", type=int, default=64)
    ap.add_argument("--replay-per-group", type=int, default=2)
    ap.add_argument("--lr", type=float, default=5e-6)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--temperature-cp", type=float, default=120.0)
    ap.add_argument("--value-weight", type=float, default=0.40)
    ap.add_argument("--rank-weight", type=float, default=0.15)
    ap.add_argument("--min-rank-margin-cp", type=float, default=20.0)
    ap.add_argument("--preserve-weight", type=float, default=0.35)
    ap.add_argument("--preserve-scale-cp", type=float, default=35.0)
    ap.add_argument("--freeze-l1-epochs", type=int, default=4)
    ap.add_argument("--val-frac", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=5072027)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--show-config", action="store_true")
    a = ap.parse_args()
    if a.show_config:
        for k, v in vars(a).items():
            print(f"{k}={v}")
        return 0
    if not 0 <= a.reference_weight <= 1:
        raise SystemExit("reference-weight must be in [0,1]")
    if a.preserve_scale_cp <= 0 or a.preserve_weight < 0:
        raise SystemExit("invalid trust-region parameters")

    torch.manual_seed(a.seed); np.random.seed(a.seed); random.seed(a.seed)
    device = torch.device("cuda" if a.device == "auto" and torch.cuda.is_available()
                          else ("cpu" if a.device == "auto" else a.device))
    ds = TeachingDataset(a.input)
    groups = build_groups(ds, a.temperature_cp, max(0, a.limit),
                          reference_engine=a.reference_engine,
                          reference_nodes=max(1, a.reference_nodes),
                          reference_weight=a.reference_weight,
                          reference_hash_mb=max(1, a.reference_hash_mb))
    if len(groups) < 20:
        raise SystemExit(f"too few policy groups: {len(groups)}")
    replay = [record_to_fen(r) for r in ds.positions]
    if len(replay) < 20:
        raise SystemExit("too few replay positions")

    rng = random.Random(a.seed)
    rng.shuffle(groups); rng.shuffle(replay)
    ngv = max(1, min(len(groups)-1, round(len(groups)*a.val_frac)))
    nrv = max(1, min(len(replay)-1, round(len(replay)*a.val_frac)))
    vg, tg = groups[:ngv], groups[ngv:]
    vr, tr = replay[:nrv], replay[nrv:]

    weights, arch, source_epoch = read_nnu4(a.init_weights)
    model = NNUE().to(device); model.load_state_dict(weights, strict=True)
    base = NNUE().to(device); base.load_state_dict(weights, strict=True); base.eval()
    for p in base.parameters(): p.requires_grad_(False)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=a.weight_decay)

    initial = evaluate(model, vg, device, a.temperature_cp, a.value_weight,
                       a.rank_weight, a.min_rank_margin_cp)
    print(f"groups train={len(tg)} val={len(vg)} replay train={len(tr)} val={len(vr)} "
          f"source_epoch={source_epoch} initial={initial}")
    best_obj = float("inf"); best_state = copy.deepcopy(model.state_dict()); best_epoch = 0

    for epoch in range(1, a.epochs + 1):
        frozen = epoch <= a.freeze_l1_epochs
        model.l1.weight.requires_grad_(not frozen); model.l1_bias.requires_grad_(not frozen)
        model.train(); rng.shuffle(tg)
        sums = np.zeros(6, dtype=np.float64); nb = 0
        for start in range(0, len(tg), max(1, a.batch_groups)):
            batch = tg[start:start + max(1, a.batch_groups)]
            nrep = max(1, len(batch) * max(1, a.replay_per_group))
            reps = rng.sample(tr, min(nrep, len(tr)))
            opt.zero_grad(set_to_none=True)
            vals = batch_loss(model, batch, device, a.temperature_cp, a.value_weight,
                              a.rank_weight, a.min_rank_margin_cp)
            preserve, drift = replay_penalty(model, base, reps, device, a.preserve_scale_cp)
            total = vals[0] + a.preserve_weight * preserve
            total.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step(); clamp_weights_(model)
            sums[:4] += [float(v.detach().cpu()) for v in vals[:4]]
            sums[4] += float(preserve.detach().cpu()); sums[5] += drift; nb += 1

        val = evaluate(model, vg, device, a.temperature_cp, a.value_weight,
                       a.rank_weight, a.min_rank_margin_cp)
        vpen, vdrift = eval_trust(model, base, vr, device, a.preserve_scale_cp)
        objective = float(val["loss"]) + a.preserve_weight * vpen
        if objective < best_obj:
            best_obj = objective; best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
        print(f"epoch={epoch} freeze_l1={frozen} teacher={sums[0]/nb:.6f} "
              f"preserve={sums[4]/nb:.6f} replay_drift_cp={sums[5]/nb:.2f} "
              f"val={val} val_preserve={vpen:.6f} val_drift_cp={vdrift:.2f} "
              f"objective={objective:.6f} best_epoch={best_epoch}")

    model.load_state_dict(best_state)
    fpen, fdrift = eval_trust(model, base, vr, device, a.preserve_scale_cp)
    final_val = evaluate(model, vg, device, a.temperature_cp, a.value_weight,
                         a.rank_weight, a.min_rank_margin_cp)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "epoch": source_epoch + best_epoch,
        "dataset": "v507_policy_trust_region",
        "arch": arch, "qat": True, "weights": model.state_dict(),
        "policy_distill": {
            "best_epoch": best_epoch, "teacher_dataset": str(a.input),
            "groups": len(groups), "reference_engine": str(a.reference_engine),
            "reference_nodes": a.reference_nodes, "reference_weight": a.reference_weight,
            "preserve_weight": a.preserve_weight, "preserve_scale_cp": a.preserve_scale_cp,
            "validation_drift_cp": fdrift, "validation_preserve": fpen,
            "validation_teacher": final_val,
        },
    }, a.output)
    print(f"saved {a.output} best_epoch={best_epoch} val_drift_cp={fdrift:.2f}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
