"""train/model_nnu5.py — HalfKAv2_hm-32Bucket NNUE model + QAT helpers (Zchezz v6.00 NNU5)

Architecture:
    Features  : HalfKAv2_hm 32-Bucket, 22528 per perspective (train/encoding_nnu5.py)
    L1        : 22528 -> 64, SHARED between both perspectives
    Act L1    : SCReLU — c = clamp(x, 0, 1); out = c*c
    Concat    : [L1(stm) 64 | L1(opp) 64] = 128 (STM ALWAYS FIRST)
    L2        : 128 -> 16, ClippedReLU [0, 1]
    L3        : 16 -> 1, sigmoid -> WDL probability, STM-relative
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

QA = 255            # L1 weight/bias scale, int16 range
QB = 64             # L2/L3 weight scale, int8 range
NN_SHIFT = 8
QA_EFF = (QA * QA) >> NN_SHIFT   # = 254
assert QA_EFF == 254

INPUT_DIM = 22528   # 32 buckets * 704 features
HIDDEN1 = 64        # L1 output width per perspective
CONCAT_DIM = HIDDEN1 * 2   # 128
HIDDEN2 = 16        # L2 output width
HIDDEN3 = 1         # Scalar output


def fake_quant_int16(tensor: torch.Tensor, scale: float) -> torch.Tensor:
    limit = 32767.0 / scale
    x_clamp = tensor.clamp(-limit, limit)
    x_q = (x_clamp * scale).round() / scale
    return tensor + (x_q - tensor).detach()


def fake_quant_int8(tensor: torch.Tensor, scale: float) -> torch.Tensor:
    limit = 127.0 / scale
    x_clamp = tensor.clamp(-limit, limit)
    x_q = (x_clamp * scale).round() / scale
    return tensor + (x_q - tensor).detach()


def fake_quant_bias_int32(tensor: torch.Tensor, scale: float) -> torch.Tensor:
    x_q = (tensor * scale).round() / scale
    return tensor + (x_q - tensor).detach()


class SCReLU(nn.Module):
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        c = x.clamp(0.0, 1.0)
        return c * c


class ClippedReLU(nn.Module):
    def __init__(self, clip: float = 1.0):
        super().__init__()
        self.clip = clip

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x.clamp(0.0, self.clip)


class NNUE(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.l1 = nn.EmbeddingBag(INPUT_DIM, HIDDEN1, mode="sum")
        self.l1_bias = nn.Parameter(torch.zeros(HIDDEN1))
        self.act1 = SCReLU()

        self.l2 = nn.Linear(CONCAT_DIM, HIDDEN2)
        self.act2 = ClippedReLU(1.0)

        self.l3 = nn.Linear(HIDDEN2, HIDDEN3)

        nn.init.uniform_(self.l1.weight, -0.05, 0.05)
        nn.init.zeros_(self.l1_bias)

    def _l1_perspective(self, indices: torch.Tensor, offsets: torch.Tensor,
                         w1: torch.Tensor, b1: torch.Tensor) -> torch.Tensor:
        acc = F.embedding_bag(indices, w1, offsets, mode="sum")
        acc = acc + b1
        return self.act1(acc)

    def forward(self, stm_idx: torch.Tensor, stm_off: torch.Tensor,
                opp_idx: torch.Tensor, opp_off: torch.Tensor) -> torch.Tensor:
        w1 = fake_quant_int16(self.l1.weight, QA)
        b1 = fake_quant_bias_int32(self.l1_bias, float(QA))

        h_stm = self._l1_perspective(stm_idx, stm_off, w1, b1)
        h_opp = self._l1_perspective(opp_idx, opp_off, w1, b1)

        h_stm_q = (h_stm * QA_EFF).round().clamp(0, QA_EFF) / QA_EFF
        h_stm = h_stm + (h_stm_q - h_stm).detach()
        h_opp_q = (h_opp * QA_EFF).round().clamp(0, QA_EFF) / QA_EFF
        h_opp = h_opp + (h_opp_q - h_opp).detach()

        h = torch.cat([h_stm, h_opp], dim=1)

        w2 = fake_quant_int8(self.l2.weight, QB)
        b2 = fake_quant_bias_int32(self.l2.bias, float(QA_EFF * QB))
        h2 = self.act2(F.linear(h, w2, b2))

        h2_q = (h2 * QB).round().clamp(0, QB) / QB
        h2 = h2 + (h2_q - h2).detach()

        w3 = fake_quant_int8(self.l3.weight, QB)
        out = torch.sigmoid(F.linear(h2, w3, self.l3.bias))
        return out.squeeze(1)


def clamp_weights_(model: nn.Module) -> None:
    with torch.no_grad():
        limit_w1 = 32767.0 / QA
        model.l1.weight.clamp_(-limit_w1, limit_w1)
        limit_w2 = 127.0 / QB
        model.l2.weight.clamp_(-limit_w2, limit_w2)
        model.l3.weight.clamp_(-limit_w2, limit_w2)
