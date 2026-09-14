#!/usr/bin/env python3
"""Train a cheap global-information side channel into frozen NNU4 L2.

The ordinary HalfKP NNU4 is frozen. A zero-initialized 30-informative-feature
projection contributes directly to the 20 L2 pre-activations. This costs only
31x20 scalar products in the simple runtime (versus two 31x48 projections for
the L1-side experiment) while still allowing nonlinear interaction through the
existing clipped L2 activation and L3.
"""
from __future__ import annotations

import argparse
import copy
import random
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "train"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from train.encoding import encode_positions  # noqa: E402
from train.global_features import GLOBAL_DIM, encode_global_features  # noqa: E402
from train.import_nnu4 import read_nnu4  # noqa: E402
from train.model import NNUE, QA, QA_EFF, QB, fake_quant_bias_int32, fake_quant_int16, fake_quant_int8  # noqa: E402
from train.teaching.format import TeachingDataset, record_to_fen  # noqa: E402
from train.teaching.train_policy_distill_nnu4 import Group, build_groups  # noqa: E402

FEATURE_SETS = {
    "all": [i for i in range(31) if i != 13],
    "aggregate": list(range(13)),
    "relational": list(range(14, 31)),
}


class GlobalL2NNU4(nn.Module):
    def __init__(self, base: NNUE, feature_set: str):
        super().__init__()
        self.base = base
        for p in self.base.parameters():
            p.requires_grad_(False)
        self.base.eval()
        self.global_l2 = nn.Parameter(torch.zeros(GLOBAL_DIM, 20))
        mask = torch.zeros(GLOBAL_DIM, 1)
        mask[FEATURE_SETS[feature_set], 0] = 1.0
        self.register_buffer("feature_mask", mask)

    def forward(self, stm_idx, stm_off, opp_idx, opp_off, g_stm):
        b = self.base
        w1 = fake_quant_int16(b.l1.weight, QA)
        b1 = fake_quant_bias_int32(b.l1_bias, float(QA))
        a_stm = F.embedding_bag(stm_idx, w1, stm_off, mode="sum") + b1
        a_opp = F.embedding_bag(opp_idx, w1, opp_off, mode="sum") + b1
        h_stm = b.act1(a_stm)
        h_opp = b.act1(a_opp)
        hs_q = (h_stm * QA_EFF).round().clamp(0, QA_EFF) / QA_EFF
        ho_q = (h_opp * QA_EFF).round().clamp(0, QA_EFF) / QA_EFF
        h_stm = h_stm + (hs_q - h_stm).detach()
        h_opp = h_opp + (ho_q - h_opp).detach()
        h = torch.cat([h_stm, h_opp], dim=1)

        w2 = fake_quant_int8(b.l2.weight, QB)
        b2 = fake_quant_bias_int32(b.l2.bias, float(QA_EFF * QB))
        z2 = F.linear(h, w2, b2)
        # Match a runtime representation where global features are Q=254 and
        # side weights are int8/QB, exactly the scale of the normal L2 sum.
        gq = torch.round(g_stm * QA_EFF) / QA_EFF
        gw = fake_quant_int8(self.global_l2 * self.feature_mask, QB)
        z2 = z2 + gq @ gw
        h2 = b.act2(z2)
        h2_q = (h2 * QB).round().clamp(0, QB) / QB
        h2 = h2 + (h2_q - h2).detach()
        w3 = fake_quant_int8(b.l3.weight, QB)
        return torch.sigmoid(F.linear(h2, w3, b.l3.bias)).squeeze(1)


def _encoded(fens: list[str], device: torch.device):
    si, so, oi, oo = encode_positions(fens)
    gs, _go = encode_global_features(fens)
    return (
        torch.as_tensor(si, dtype=torch.long, device=device),
        torch.as_tensor(so, dtype=torch.long, device=device),
        torch.as_tensor(oi, dtype=torch.long, device=device),
        torch.as_tensor(oo, dtype=torch.long, device=device),
        torch.as_tensor(gs, dtype=torch.float32, device=device),
    )


def forward_side(model: GlobalL2NNU4, fens: list[str], device: torch.device):
    return model(*_encoded(fens, device))


def forward_base(base: NNUE, fens: list[str], device: torch.device):
    si, so, oi, oo = encode_positions(fens)
    return base(
        torch.as_tensor(si, dtype=torch.long, device=device),
        torch.as_tensor(so, dtype=torch.long, device=device),
        torch.as_tensor(oi, dtype=torch.long, device=device),
        torch.as_tensor(oo, dtype=torch.long, device=device),
    )


def policy_rank_loss(model, groups: list[Group], device, temperature_cp: float,
                     rank_weight: float, min_rank_margin_cp: float):
    fens: list[str] = []
    boundaries = [0]
    rank_scores = []
    target_policy = []
    for g in groups:
        fens.extend(g.child_fens)
        rank_scores.extend(g.rank_scores_cp.tolist())
        target_policy.extend(g.target_policy.tolist())
        boundaries.append(len(fens))
    p = forward_side(model, fens, device).clamp(1e-6, 1 - 1e-6)
    parent_logit = -torch.logit(p)
    ranks = torch.as_tensor(rank_scores, dtype=torch.float32, device=device)
    q_all = torch.as_tensor(target_policy, dtype=torch.float32, device=device)
    scale = 320.0 / max(1e-6, float(temperature_cp))
    policy_terms = []
    rank_terms = []
    top1 = 0
    for gi in range(len(groups)):
        a, b = boundaries[gi], boundaries[gi + 1]
        s = parent_logit[a:b]
        q = q_all[a:b]
        policy_terms.append(-(q * F.log_softmax(s * scale, dim=0)).sum())
        if int(s.argmax()) == int(q.argmax()):
            top1 += 1
        t = ranks[a:b]
        best = int(t.argmax())
        for j in range(len(t)):
            if j == best:
                continue
            margin = float((t[best] - t[j]).detach().cpu())
            if margin < min_rank_margin_cp:
                continue
            required = min(2.0, margin / 320.0)
            rank_terms.append(F.softplus(torch.as_tensor(required, device=device) - (s[best] - s[j])))
    policy = torch.stack(policy_terms).mean()
    rank = torch.stack(rank_terms).mean() if rank_terms else torch.zeros((), device=device)
    return policy + rank_weight * rank, policy.detach(), rank.detach(), top1


def trust_penalty(model, base, fens: list[str], device, scale_cp: float):
    pg = forward_side(model, fens, device).clamp(1e-6, 1 - 1e-6)
    with torch.no_grad():
        pb = forward_base(base, fens, device).clamp(1e-6, 1 - 1e-6)
    delta = (torch.logit(pg) - torch.logit(pb)) * 320.0
    return torch.mean((delta / scale_cp) ** 2), float(torch.mean(torch.abs(delta)).detach().cpu())


def evaluate(model, base, groups, replay, device, args):
    model.eval()
    with torch.no_grad():
        loss, pol, rank, top1 = policy_rank_loss(
            model, groups, device, args.temperature_cp, args.rank_weight, args.min_rank_margin_cp)
        pen, drift = trust_penalty(model, base, replay, device, args.preserve_scale_cp)
    return {
        "objective": float(loss.cpu()) + args.preserve_weight * float(pen.cpu()),
        "policy": float(pol.cpu()), "rank": float(rank.cpu()),
        "top1": top1 / max(1, len(groups)), "preserve": float(pen.cpu()),
        "drift_cp": drift,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--init-weights", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--feature-set", choices=tuple(FEATURE_SETS), default="all")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch-groups", type=int, default=64)
    ap.add_argument("--replay-per-group", type=int, default=2)
    ap.add_argument("--lr", type=float, default=0.001)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--temperature-cp", type=float, default=110.0)
    ap.add_argument("--rank-weight", type=float, default=0.15)
    ap.add_argument("--min-rank-margin-cp", type=float, default=20.0)
    ap.add_argument("--preserve-weight", type=float, default=0.20)
    ap.add_argument("--preserve-scale-cp", type=float, default=28.0)
    ap.add_argument("--val-frac", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=5073201)
    ap.add_argument("--device", default="auto")
    a = ap.parse_args()

    torch.manual_seed(a.seed); np.random.seed(a.seed); random.seed(a.seed)
    device = torch.device("cuda" if a.device == "auto" and torch.cuda.is_available()
                          else ("cpu" if a.device == "auto" else a.device))
    ds = TeachingDataset(a.input)
    groups = build_groups(ds, a.temperature_cp, reference_engine="", reference_weight=0.0)
    replay = [record_to_fen(r) for r in ds.positions]
    if len(groups) < 50 or len(replay) < 100:
        raise SystemExit("dataset too small")
    rng = random.Random(a.seed)
    rng.shuffle(groups); rng.shuffle(replay)
    ngv = max(1, min(len(groups)-1, round(len(groups)*a.val_frac)))
    nrv = max(1, min(len(replay)-1, round(len(replay)*a.val_frac)))
    vg, tg = groups[:ngv], groups[ngv:]
    vr, tr = replay[:nrv], replay[nrv:]

    weights, arch, source_epoch = read_nnu4(a.init_weights)
    base = NNUE().to(device); base.load_state_dict(weights, strict=True); base.eval()
    for p in base.parameters(): p.requires_grad_(False)
    model = GlobalL2NNU4(base, a.feature_set).to(device)

    probe = vr[:min(64, len(vr))]
    with torch.no_grad():
        p0 = forward_side(model, probe, device)
        pb = forward_base(base, probe, device)
        err = float(torch.max(torch.abs(p0-pb)).cpu())
    print(f"zero_projection_max_probability_error={err:.12g}")
    if err > 1e-7:
        raise SystemExit(f"zero L2 side channel is not base-identical: {err}")

    opt = torch.optim.AdamW([model.global_l2], lr=a.lr, weight_decay=a.weight_decay)
    best = evaluate(model, base, vg, vr, device, a)
    best_state = copy.deepcopy(model.global_l2.detach().cpu())
    best_epoch = 0
    print(f"groups train={len(tg)} val={len(vg)} replay train={len(tr)} val={len(vr)} "
          f"feature_set={a.feature_set} initial={best}")

    for epoch in range(1, a.epochs + 1):
        model.train(); rng.shuffle(tg)
        sum_pol = sum_rank = sum_drift = 0.0; nb = 0
        for start in range(0, len(tg), max(1, a.batch_groups)):
            batch = tg[start:start+a.batch_groups]
            reps = rng.sample(tr, min(len(tr), max(1, len(batch)*a.replay_per_group)))
            opt.zero_grad(set_to_none=True)
            teacher, pol, rank, _ = policy_rank_loss(
                model, batch, device, a.temperature_cp, a.rank_weight, a.min_rank_margin_cp)
            pen, drift = trust_penalty(model, base, reps, device, a.preserve_scale_cp)
            reg = torch.mean((model.global_l2 * model.feature_mask) ** 2)
            loss = teacher + a.preserve_weight * pen + 1e-4 * reg
            loss.backward()
            if model.global_l2.grad is not None:
                model.global_l2.grad.mul_(model.feature_mask)
            torch.nn.utils.clip_grad_norm_([model.global_l2], 5.0)
            opt.step()
            with torch.no_grad():
                model.global_l2.mul_(model.feature_mask)
                model.global_l2.clamp_(-127.0/QB, 127.0/QB)
            sum_pol += float(pol.cpu()); sum_rank += float(rank.cpu()); sum_drift += drift; nb += 1
        val = evaluate(model, base, vg, vr, device, a)
        if val["objective"] < best["objective"]:
            best = val; best_epoch = epoch
            best_state = copy.deepcopy(model.global_l2.detach().cpu())
        print(f"epoch={epoch} policy={sum_pol/nb:.6f} rank={sum_rank/nb:.6f} "
              f"train_drift_cp={sum_drift/nb:.3f} val={val} best_epoch={best_epoch}")

    with torch.no_grad():
        model.global_l2.copy_(best_state.to(device))
    final = evaluate(model, base, vg, vr, device, a)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "epoch": source_epoch + best_epoch, "source_epoch": source_epoch,
        "feature_set": a.feature_set, "global_l2": model.global_l2.detach().cpu(),
        "best_epoch": best_epoch, "validation": final, "arch": arch,
    }, a.output)
    print(f"saved {a.output} best_epoch={best_epoch} validation={final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
