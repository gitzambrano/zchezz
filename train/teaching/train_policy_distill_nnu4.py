#!/usr/bin/env python3
"""Explicit move-policy distillation into the existing NNU4 value network.

No policy head is added at inference.  For each teacher-labelled parent, the
network evaluates selected child positions.  Child STM probabilities are
converted back to parent-POV logits and optimized against the teacher's soft
move distribution, with auxiliary child-value and pairwise ranking losses.
The shipped engine therefore pays exactly the same NNU4 runtime cost.
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "train") not in sys.path:
    sys.path.insert(0, str(ROOT / "train"))

from train.encoding import encode_positions  # noqa: E402
from train.import_nnu4 import read_nnu4  # noqa: E402
from train.model import NNUE, clamp_weights_  # noqa: E402
from train.teaching.export_policy_children import select_policy_children  # noqa: E402
from train.teaching.format import TeachingDataset, record_to_fen, unpack_move_uci  # noqa: E402

INPUT = ROOT / "data" / "teaching" / "v507_teacher"
INIT_WEIGHTS = ROOT / "engine" / "c" / "zchezz_v506" / "nnue_weights.bin"
OUTPUT = ROOT / "checkpoints" / "v507" / "policy_distill.pt"
EPOCHS = 8
BATCH_GROUPS = 64
LR = 1.5e-5
WEIGHT_DECAY = 1e-4
TEMPERATURE_CP = 120.0
VALUE_WEIGHT = 0.35
RANK_WEIGHT = 0.15
MIN_RANK_MARGIN_CP = 20.0
FREEZE_L1_EPOCHS = 2
VAL_FRAC = 0.10
SEED = 5072026
LIMIT = 0


@dataclass
class Group:
    child_fens: list[str]
    parent_scores_cp: np.ndarray
    target_policy: np.ndarray


def soft_policy(scores_cp, temperature_cp: float = TEMPERATURE_CP) -> np.ndarray:
    scores = np.asarray(scores_cp, dtype=np.float64)
    if scores.size == 0:
        return np.empty(0, dtype=np.float32)
    temp = max(1e-6, float(temperature_cp))
    z = (scores - scores.max()) / temp
    p = np.exp(z)
    p /= p.sum()
    return p.astype(np.float32)


def child_value_probability(parent_pov_cp) -> np.ndarray:
    """Teacher probability from the post-move side-to-move perspective."""
    x = -np.asarray(parent_pov_cp, dtype=np.float64) / 320.0
    x = np.clip(x, -60.0, 60.0)
    return (1.0 / (1.0 + np.exp(-x))).astype(np.float32)


def build_groups(dataset: TeachingDataset, temperature_cp: float,
                 limit: int = 0) -> list[Group]:
    import chess

    groups: list[Group] = []
    for index, row in enumerate(dataset.positions):
        selected = select_policy_children(row, dataset.moves_for(index))
        if len(selected) < 2:
            continue
        board = chess.Board(record_to_fen(row))
        child_fens, scores = [], []
        for packed, _cp_white, parent_pov_cp in selected:
            try:
                move = chess.Move.from_uci(unpack_move_uci(packed))
            except ValueError:
                continue
            if move not in board.legal_moves:
                continue
            board.push(move)
            child_fens.append(board.fen())
            scores.append(float(parent_pov_cp))
            board.pop()
        if len(child_fens) >= 2:
            s = np.asarray(scores, dtype=np.float32)
            groups.append(Group(child_fens, s, soft_policy(s, temperature_cp)))
            if limit and len(groups) >= limit:
                break
    return groups


def _forward_fens(model: NNUE, fens: list[str], device: torch.device) -> torch.Tensor:
    si, so, oi, oo = encode_positions(fens)
    return model(
        torch.as_tensor(si, dtype=torch.long, device=device),
        torch.as_tensor(so, dtype=torch.long, device=device),
        torch.as_tensor(oi, dtype=torch.long, device=device),
        torch.as_tensor(oo, dtype=torch.long, device=device),
    )


def batch_loss(model: NNUE, groups: list[Group], device: torch.device,
               temperature_cp: float, value_weight: float, rank_weight: float,
               min_rank_margin_cp: float):
    fens: list[str] = []
    boundaries = [0]
    teacher_scores = []
    teacher_policy = []
    for group in groups:
        fens.extend(group.child_fens)
        teacher_scores.extend(group.parent_scores_cp.tolist())
        teacher_policy.extend(group.target_policy.tolist())
        boundaries.append(len(fens))

    pred_child = _forward_fens(model, fens, device).clamp(1e-6, 1 - 1e-6)
    scores = torch.as_tensor(teacher_scores, dtype=torch.float32, device=device)
    q_all = torch.as_tensor(teacher_policy, dtype=torch.float32, device=device)
    value_targets = torch.sigmoid(-scores / 320.0)
    value_loss = F.binary_cross_entropy(pred_child, value_targets)

    child_logit = torch.logit(pred_child)
    parent_logit = -child_logit
    scale = 320.0 / max(1e-6, float(temperature_cp))
    policy_terms = []
    rank_terms = []
    top1_ok = 0
    for gi in range(len(groups)):
        a, b = boundaries[gi], boundaries[gi + 1]
        student = parent_logit[a:b]
        q = q_all[a:b]
        policy_terms.append(-(q * F.log_softmax(student * scale, dim=0)).sum())
        if int(student.argmax()) == int(q.argmax()):
            top1_ok += 1
        teacher = scores[a:b]
        best = int(teacher.argmax())
        for j in range(len(teacher)):
            if j == best:
                continue
            margin_cp = float((teacher[best] - teacher[j]).detach().cpu())
            if margin_cp < min_rank_margin_cp:
                continue
            required = min(2.0, margin_cp / 320.0)
            rank_terms.append(F.softplus(
                torch.as_tensor(required, device=device) - (student[best] - student[j])))

    policy_loss = torch.stack(policy_terms).mean()
    rank_loss = (torch.stack(rank_terms).mean() if rank_terms
                 else torch.zeros((), device=device))
    total = policy_loss + value_weight * value_loss + rank_weight * rank_loss
    return total, policy_loss.detach(), value_loss.detach(), rank_loss.detach(), top1_ok


def evaluate(model: NNUE, groups: list[Group], device: torch.device,
             temperature_cp: float, value_weight: float, rank_weight: float,
             min_rank_margin_cp: float):
    if not groups:
        return None
    model.eval()
    totals = np.zeros(5, dtype=np.float64)
    n = 0
    with torch.no_grad():
        for start in range(0, len(groups), BATCH_GROUPS):
            batch = groups[start:start + BATCH_GROUPS]
            vals = batch_loss(model, batch, device, temperature_cp, value_weight,
                              rank_weight, min_rank_margin_cp)
            totals[:4] += [float(v.cpu()) for v in vals[:4]]
            totals[4] += vals[4]
            n += 1
    return {
        "loss": totals[0] / n, "policy_ce": totals[1] / n,
        "value_bce": totals[2] / n, "rank": totals[3] / n,
        "top1": totals[4] / len(groups),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=INPUT)
    p.add_argument("--init-weights", type=Path, default=INIT_WEIGHTS)
    p.add_argument("--output", type=Path, default=OUTPUT)
    p.add_argument("--epochs", type=int, default=EPOCHS)
    p.add_argument("--batch-groups", type=int, default=BATCH_GROUPS)
    p.add_argument("--lr", type=float, default=LR)
    p.add_argument("--weight-decay", type=float, default=WEIGHT_DECAY)
    p.add_argument("--temperature-cp", type=float, default=TEMPERATURE_CP)
    p.add_argument("--value-weight", type=float, default=VALUE_WEIGHT)
    p.add_argument("--rank-weight", type=float, default=RANK_WEIGHT)
    p.add_argument("--min-rank-margin-cp", type=float, default=MIN_RANK_MARGIN_CP)
    p.add_argument("--freeze-l1-epochs", type=int, default=FREEZE_L1_EPOCHS)
    p.add_argument("--val-frac", type=float, default=VAL_FRAC)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--limit", type=int, default=LIMIT)
    p.add_argument("--device", default="auto")
    p.add_argument("--show-config", action="store_true")
    a = p.parse_args()
    if a.show_config:
        for k, v in vars(a).items():
            print(f"{k}={v}")
        return 0
    if not (a.input / "metadata.json").is_file():
        raise SystemExit(f"teaching dataset not found: {a.input}")

    torch.manual_seed(a.seed); np.random.seed(a.seed); random.seed(a.seed)
    device = torch.device("cuda" if a.device == "auto" and torch.cuda.is_available()
                          else ("cpu" if a.device == "auto" else a.device))
    dataset = TeachingDataset(a.input)
    groups = build_groups(dataset, a.temperature_cp, max(0, a.limit))
    if len(groups) < 10:
        raise SystemExit(f"too few policy groups: {len(groups)}")
    rng = random.Random(a.seed)
    rng.shuffle(groups)
    n_val = min(len(groups) - 1, max(1, int(round(len(groups) * a.val_frac))))
    val_groups = groups[:n_val]
    train_groups = groups[n_val:]

    weights, arch, source_epoch = read_nnu4(a.init_weights)
    model = NNUE().to(device)
    model.load_state_dict(weights, strict=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=a.weight_decay)
    print(f"groups train={len(train_groups)} val={len(val_groups)} source_epoch={source_epoch} device={device}")

    freeze_epochs = max(0, a.freeze_l1_epochs)
    for epoch in range(1, max(1, a.epochs) + 1):
        frozen = epoch <= freeze_epochs
        model.l1.weight.requires_grad_(not frozen)
        model.l1_bias.requires_grad_(not frozen)
        model.train()
        rng.shuffle(train_groups)
        sums = np.zeros(5, dtype=np.float64); nb = 0
        for start in range(0, len(train_groups), max(1, a.batch_groups)):
            batch = train_groups[start:start + max(1, a.batch_groups)]
            optimizer.zero_grad(set_to_none=True)
            vals = batch_loss(model, batch, device, a.temperature_cp, a.value_weight,
                              a.rank_weight, a.min_rank_margin_cp)
            vals[0].backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step(); clamp_weights_(model)
            sums[:4] += [float(v.detach().cpu()) for v in vals[:4]]
            sums[4] += vals[4]; nb += 1
        val = evaluate(model, val_groups, device, a.temperature_cp, a.value_weight,
                       a.rank_weight, a.min_rank_margin_cp)
        train_top1 = sums[4] / len(train_groups)
        print(
            f"epoch={epoch} freeze_l1={frozen} loss={sums[0]/nb:.6f} "
            f"policy={sums[1]/nb:.6f} value={sums[2]/nb:.6f} rank={sums[3]/nb:.6f} "
            f"top1={train_top1:.4f} val={val}")

    a.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "epoch": source_epoch + max(1, a.epochs),
        "dataset": "v507_explicit_policy_distill",
        "arch": arch,
        "qat": True,
        "weights": model.state_dict(),
        "policy_distill": {
            "teacher_dataset": str(a.input), "groups": len(groups),
            "temperature_cp": a.temperature_cp, "value_weight": a.value_weight,
            "rank_weight": a.rank_weight, "freeze_l1_epochs": freeze_epochs,
            "seed": a.seed,
        },
    }, a.output)
    print(f"saved {a.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
