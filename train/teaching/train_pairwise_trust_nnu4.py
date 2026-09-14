#!/usr/bin/env python3
"""Pairwise-only move-preference distillation for NNU4.

This trainer deliberately does not regress absolute centipawn values and does
not match a full soft policy distribution.  It only asks the student value
network to preserve teacher move ordering margins between selected children,
while a frozen starting network provides a functional trust region on replay
positions.  The intent is to improve search-relevant local ordering without
recalibrating the evaluator.
"""
from __future__ import annotations

import argparse
import copy
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "train"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from train.import_nnu4 import read_nnu4  # noqa: E402
from train.model import NNUE, clamp_weights_  # noqa: E402
from train.teaching.format import TeachingDataset, record_to_fen  # noqa: E402
from train.teaching.train_policy_distill_nnu4 import (  # noqa: E402
    _forward_fens,
    build_groups,
)
from train.teaching.train_policy_trust_nnu4 import (  # noqa: E402
    eval_trust,
    replay_penalty,
)


def pairwise_loss(model: NNUE, groups, device: torch.device,
                  min_margin_cp: float, margin_scale_cp: float):
    fens: list[str] = []
    boundaries = [0]
    ranks: list[float] = []
    for g in groups:
        fens.extend(g.child_fens)
        ranks.extend(g.rank_scores_cp.tolist())
        boundaries.append(len(fens))

    pred_child = _forward_fens(model, fens, device).clamp(1e-6, 1 - 1e-6)
    parent_logits = -torch.logit(pred_child)
    teacher = torch.as_tensor(ranks, dtype=torch.float32, device=device)

    terms = []
    correct = 0
    total_pairs = 0
    top1 = 0
    for gi in range(len(groups)):
        a, b = boundaries[gi], boundaries[gi + 1]
        s = parent_logits[a:b]
        t = teacher[a:b]
        if int(s.argmax()) == int(t.argmax()):
            top1 += 1
        n = len(t)
        for i in range(n):
            for j in range(i + 1, n):
                gap = float((t[i] - t[j]).detach().cpu())
                if abs(gap) < min_margin_cp:
                    continue
                sign = 1.0 if gap > 0 else -1.0
                required = min(2.0, abs(gap) / max(1e-6, margin_scale_cp))
                delta = sign * (s[i] - s[j])
                terms.append(F.softplus(torch.as_tensor(required, device=device) - delta))
                correct += int(float(delta.detach().cpu()) > 0.0)
                total_pairs += 1

    loss = torch.stack(terms).mean() if terms else torch.zeros((), device=device)
    return loss, correct, total_pairs, top1


def evaluate(model: NNUE, groups, device: torch.device,
             min_margin_cp: float, margin_scale_cp: float,
             batch_groups: int = 64):
    model.eval()
    sum_loss = 0.0
    sum_correct = sum_pairs = sum_top1 = count_groups = 0
    batches = 0
    with torch.no_grad():
        for start in range(0, len(groups), max(1, batch_groups)):
            batch = groups[start:start + max(1, batch_groups)]
            loss, correct, pairs, top1 = pairwise_loss(
                model, batch, device, min_margin_cp, margin_scale_cp)
            sum_loss += float(loss.cpu())
            sum_correct += correct
            sum_pairs += pairs
            sum_top1 += top1
            count_groups += len(batch)
            batches += 1
    return {
        "pair_loss": sum_loss / max(1, batches),
        "pair_acc": sum_correct / max(1, sum_pairs),
        "top1": sum_top1 / max(1, count_groups),
        "pairs": sum_pairs,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--init-weights", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--reference-engine", default="")
    ap.add_argument("--reference-nodes", type=int, default=6000)
    ap.add_argument("--reference-weight", type=float, default=0.65)
    ap.add_argument("--reference-hash-mb", type=int, default=32)
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--batch-groups", type=int, default=64)
    ap.add_argument("--replay-per-group", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-6)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--temperature-cp", type=float, default=105.0)
    ap.add_argument("--min-margin-cp", type=float, default=22.0)
    ap.add_argument("--margin-scale-cp", type=float, default=320.0)
    ap.add_argument("--preserve-weight", type=float, default=0.55)
    ap.add_argument("--preserve-scale-cp", type=float, default=30.0)
    ap.add_argument("--freeze-l1-epochs", type=int, default=4)
    ap.add_argument("--val-frac", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=5072031)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--device", default="auto")
    a = ap.parse_args()

    if not 0.0 <= a.reference_weight <= 1.0:
        raise SystemExit("reference-weight must be in [0,1]")
    if a.preserve_weight < 0 or a.preserve_scale_cp <= 0 or a.margin_scale_cp <= 0:
        raise SystemExit("invalid preservation or margin scale")

    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    random.seed(a.seed)
    device = torch.device("cuda" if a.device == "auto" and torch.cuda.is_available()
                          else ("cpu" if a.device == "auto" else a.device))

    ds = TeachingDataset(a.input)
    groups = build_groups(
        ds, a.temperature_cp, max(0, a.limit),
        reference_engine=a.reference_engine,
        reference_nodes=max(1, a.reference_nodes),
        reference_weight=a.reference_weight,
        reference_hash_mb=max(1, a.reference_hash_mb))
    replay = [record_to_fen(r) for r in ds.positions]
    if len(groups) < 20 or len(replay) < 20:
        raise SystemExit(f"too little data: groups={len(groups)} replay={len(replay)}")

    rng = random.Random(a.seed)
    rng.shuffle(groups)
    rng.shuffle(replay)
    ngv = max(1, min(len(groups) - 1, round(len(groups) * a.val_frac)))
    nrv = max(1, min(len(replay) - 1, round(len(replay) * a.val_frac)))
    vg, tg = groups[:ngv], groups[ngv:]
    vr, tr = replay[:nrv], replay[nrv:]

    weights, arch, source_epoch = read_nnu4(a.init_weights)
    model = NNUE().to(device)
    model.load_state_dict(weights, strict=True)
    base = NNUE().to(device)
    base.load_state_dict(weights, strict=True)
    base.eval()
    for p in base.parameters():
        p.requires_grad_(False)

    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=a.weight_decay)
    initial = evaluate(model, vg, device, a.min_margin_cp, a.margin_scale_cp,
                       a.batch_groups)
    print(f"groups train={len(tg)} val={len(vg)} replay train={len(tr)} val={len(vr)} "
          f"source_epoch={source_epoch} initial={initial}")

    best_obj = float("inf")
    best_epoch = 0
    best_state = copy.deepcopy(model.state_dict())

    for epoch in range(1, a.epochs + 1):
        frozen = epoch <= a.freeze_l1_epochs
        model.l1.weight.requires_grad_(not frozen)
        model.l1_bias.requires_grad_(not frozen)
        model.train()
        rng.shuffle(tg)
        sum_pair = sum_preserve = sum_drift = 0.0
        sum_correct = sum_pairs = 0
        nb = 0

        for start in range(0, len(tg), max(1, a.batch_groups)):
            batch = tg[start:start + max(1, a.batch_groups)]
            nrep = max(1, len(batch) * max(1, a.replay_per_group))
            reps = rng.sample(tr, min(nrep, len(tr)))
            opt.zero_grad(set_to_none=True)
            rank_loss, correct, pairs, _ = pairwise_loss(
                model, batch, device, a.min_margin_cp, a.margin_scale_cp)
            preserve, drift = replay_penalty(model, base, reps, device,
                                             a.preserve_scale_cp)
            total = rank_loss + a.preserve_weight * preserve
            total.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            clamp_weights_(model)
            sum_pair += float(rank_loss.detach().cpu())
            sum_preserve += float(preserve.detach().cpu())
            sum_drift += drift
            sum_correct += correct
            sum_pairs += pairs
            nb += 1

        val = evaluate(model, vg, device, a.min_margin_cp, a.margin_scale_cp,
                       a.batch_groups)
        vpen, vdrift = eval_trust(model, base, vr, device, a.preserve_scale_cp)
        objective = float(val["pair_loss"]) + a.preserve_weight * vpen
        if objective < best_obj:
            best_obj = objective
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
        print(f"epoch={epoch} freeze_l1={frozen} pair={sum_pair/max(1,nb):.6f} "
              f"pair_acc={sum_correct/max(1,sum_pairs):.4f} preserve={sum_preserve/max(1,nb):.6f} "
              f"drift_cp={sum_drift/max(1,nb):.2f} val={val} val_preserve={vpen:.6f} "
              f"val_drift_cp={vdrift:.2f} objective={objective:.6f} best_epoch={best_epoch}")

    model.load_state_dict(best_state)
    final = evaluate(model, vg, device, a.min_margin_cp, a.margin_scale_cp,
                     a.batch_groups)
    fpen, fdrift = eval_trust(model, base, vr, device, a.preserve_scale_cp)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "epoch": source_epoch + best_epoch,
        "dataset": "v507_pairwise_trust_region",
        "arch": arch,
        "qat": True,
        "weights": model.state_dict(),
        "pairwise_distill": {
            "best_epoch": best_epoch,
            "teacher_dataset": str(a.input),
            "groups": len(groups),
            "reference_engine": str(a.reference_engine),
            "reference_nodes": a.reference_nodes,
            "reference_weight": a.reference_weight,
            "min_margin_cp": a.min_margin_cp,
            "margin_scale_cp": a.margin_scale_cp,
            "preserve_weight": a.preserve_weight,
            "preserve_scale_cp": a.preserve_scale_cp,
            "validation_drift_cp": fdrift,
            "validation_preserve": fpen,
            "validation_pairwise": final,
        },
    }, a.output)
    print(f"saved {a.output} best_epoch={best_epoch} val_drift_cp={fdrift:.2f} final={final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
