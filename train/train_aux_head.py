#!/usr/bin/env python3
"""Fit the auxiliary linear "fast head" for the selected engine profile.

The fast head is a linear readout of the network's first hidden layer. The C
runtime includes it as ``fast_head_weights.h`` and reads exactly these symbols:

- NNU3 (``nnue.c`` of v3xx): ``FAST_HEAD_BIAS``, ``FAST_HEAD_INV_SCALE`` and
  ``int8_t FAST_HEAD_W[256]`` over the clipped L1 activations (0..255).
- NNU5 (``nnue.c`` of v60x): the same symbols plus ``FAST_HEAD_DIM 512`` over
  the ``[stm | opp]`` SCReLU activations (0..254).

NNU4 has no fast head; the script refuses NNU4 profiles before loading data.

Inputs are architecture-neutral parquet datasets with ``fen`` and White-relative
``cp``. Targets are converted to side-to-move centipawns before fitting. The
fit is a closed-form ridge regression accumulated in a single streaming pass,
so the result is deterministic for a given dataset order and position limit.

Outputs go to ``artifacts/aux_head/<profile>/`` by default: the header plus a
``fast_head_weights.json`` provenance record. ``--install`` additionally copies
the header into the profile's engine directory; without it, tracked engine
source is never modified.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "utils"))
sys.path.insert(0, str(ROOT / "train"))

from engine_profiles import DEFAULT_PROFILE, profile  # noqa: E402

# Editable defaults (bare run).
DEFAULT_DATASETS = [
    "data/extraquiet_cp_sf5k_res_filter",
    "data/extraquiet_cp_sfd14_endgames_filter",
    "data/selfplay-lichess_cp_sf500k_res_filter_endgames",
    "data/synthetic_endgame_cp_sf_filter_data20260414",
]
DEFAULT_POSITIONS = 1_000_000
DEFAULT_VALIDATION = 20_000
DEFAULT_ALPHA = 200.0
DEFAULT_BATCH = 8192
CP_CLIP = 2000.0

HEAD_DIMS = {"NNU3": 256, "NNU5": 512}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def iter_fen_cp(datasets: list[Path], limit: int, batch: int):
    """Yield (fens, white_cp) batches from parquet files in sorted order."""
    import numpy as np
    import pyarrow.parquet as pq

    seen = 0
    for ds in datasets:
        for f in sorted(ds.glob("*.parquet")):
            pf = pq.ParquetFile(f)
            if not {"fen", "cp"} <= set(pf.schema_arrow.names):
                continue
            for rb in pf.iter_batches(batch_size=batch, columns=["fen", "cp"]):
                fens = rb.column(0).to_pylist()
                cp = rb.column(1).to_numpy(zero_copy_only=False).astype(np.float64)
                keep = np.isfinite(cp)
                if not keep.all():
                    fens = [x for x, k in zip(fens, keep) if k]
                    cp = cp[keep]
                if seen + len(fens) > limit:
                    n = limit - seen
                    fens, cp = fens[:n], cp[:n]
                if fens:
                    seen += len(fens)
                    yield fens, cp
                if seen >= limit:
                    return


class Nnu3Features:
    """Clipped L1 activations of an NNU3 network, quantized to 0..255."""

    def __init__(self, prof, checkpoint: Path | None):
        """Load the NNU3 checkpoint (the profile's installed weights when `checkpoint` is None) and
        prepare its hidden layer; raise FileNotFoundError when it is missing.
        """
        import torch
        from model_nnu3 import NNUE, assert_compatible_arch

        net = NNUE()
        ckpt_path = checkpoint or prof.latest_checkpoint
        if ckpt_path.is_file():
            ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
            assert_compatible_arch(ckpt.get("arch"))
            net.load_state_dict(ckpt["model"])
            self.source = _rel(ckpt_path)
        elif prof.weights.is_file():
            from import_nnu3 import read_nnu3
            state, _arch, _epoch = read_nnu3(prof.weights)
            net.load_state_dict(state)
            self.source = _rel(prof.weights)
        else:
            raise FileNotFoundError(
                f"{prof.name}: no checkpoint ({ckpt_path}) and no installed weights ({prof.weights})")
        net.eval()
        self.w1, self.b1 = net.l1.weight.detach(), net.l1.bias.detach()

    def __call__(self, fens, white_cp):
        """Return (quantized hidden activations as float64, target) for the positions `fens`.

        The target is `white_cp` seen from the side to move (negated for Black to move).
        """
        import numpy as np
        import torch
        import torch.nn.functional as F
        from encoding_nnu3 import encode_chunk

        x, is_black = encode_chunk(fens)
        with torch.no_grad():
            h = F.linear(torch.from_numpy(x), self.w1, self.b1).clamp(0.0, 1.0)
            h = (h * 255.0).round()
        y = np.where(is_black, -white_cp, white_cp)
        return h.double().numpy(), y


class Nnu5Features:
    """[stm | opp] SCReLU activations of an NNU5 network, quantized to 0..254."""

    def __init__(self, prof, checkpoint: Path | None):
        """Load the NNU5 checkpoint (the profile's installed weights when `checkpoint` is None); raise
        ValueError for another architecture and FileNotFoundError when it is missing.
        """
        import torch
        from model_nnu5 import NNUE, CONCAT_DIM

        net = NNUE()
        ckpt_path = checkpoint or prof.latest_checkpoint
        if ckpt_path.is_file():
            ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
            arch = ckpt.get("arch") or {}
            if arch.get("encoding") != "halfka_v2_hm_32b" or arch.get("concat") != CONCAT_DIM:
                raise ValueError(f"{ckpt_path}: incompatible NNU5 checkpoint architecture {arch!r}")
            net.load_state_dict(ckpt["weights"])
            self.source = _rel(ckpt_path)
        elif prof.weights.is_file():
            from import_nnu5 import read_nnu5
            weights, _arch, _epoch = read_nnu5(prof.weights)
            net.load_state_dict(weights)
            self.source = _rel(prof.weights)
        else:
            raise FileNotFoundError(
                f"{prof.name}: no checkpoint ({ckpt_path}) and no installed weights ({prof.weights})")
        net.eval()
        self.net = net

    def __call__(self, fens, white_cp):
        """Return (quantized hidden activations of both perspectives, concatenated, as float64; target)
        for the positions `fens`.

        The target is `white_cp` seen from the side to move (negated for Black to move).
        """
        import chess
        import numpy as np
        import torch
        from encoding_nnu5 import encode_positions
        from model_nnu5 import QA, QA_EFF, fake_quant_bias_int32, fake_quant_int16

        stm_idx, stm_off, opp_idx, opp_off = encode_positions(fens)
        is_black = np.array([chess.Board(f).turn == chess.BLACK for f in fens])
        net = self.net
        with torch.no_grad():
            w1 = fake_quant_int16(net.l1.weight, QA)
            b1 = fake_quant_bias_int32(net.l1_bias, float(QA))
            hs = net._l1_perspective(torch.from_numpy(stm_idx).long(), torch.from_numpy(stm_off).long(), w1, b1)
            ho = net._l1_perspective(torch.from_numpy(opp_idx).long(), torch.from_numpy(opp_off).long(), w1, b1)
            h = torch.cat([(hs * QA_EFF).round().clamp(0, QA_EFF),
                           (ho * QA_EFF).round().clamp(0, QA_EFF)], dim=1)
        y = np.where(is_black, -white_cp, white_cp)
        return h.double().numpy(), y


FEATURES = {"NNU3": Nnu3Features, "NNU5": Nnu5Features}


def render_header(fmt: str, w_int8, inv_scale: float, bias: float, note: str) -> str:
    """Return the C header text of the quantized fast head: int8 weights `w_int8`, `inv_scale`, `bias`
    and a `note`.
    """
    dim = len(w_int8)
    lines = [
        f"/* fast_head_weights.h — auxiliary {fmt} linear head ({dim} inputs).",
        f" * Generated by train/train_aux_head.py. {note}",
        " */",
        "#pragma once",
        "#include <stdint.h>",
        "",
    ]
    if fmt == "NNU5":
        lines.append(f"#define FAST_HEAD_DIM {dim}")
    lines += [
        f"#define FAST_HEAD_BIAS   ({bias:.4f}f)",
        f"#define FAST_HEAD_INV_SCALE ({inv_scale:.8f}f)",
        "",
        f"static const int8_t FAST_HEAD_W[{dim}] __attribute__((aligned(32))) = {{",
    ]
    for r in range(0, dim, 16):
        lines.append("    " + ", ".join(f"{int(v):4d}" for v in w_int8[r:r + 16]) + ",")
    lines += ["};", ""]
    return "\n".join(lines)


def fit(features, batches, dim: int, n_val: int, alpha: float):
    """Stream normal equations; hold out the first n_val rows for validation."""
    import numpy as np

    ata = np.zeros((dim + 1, dim + 1))
    aty = np.zeros(dim + 1)
    vx, vy = [], []
    held = n_seen = 0
    for fens, wcp in batches:
        x, y = features(fens, wcp)
        y = np.clip(y, -CP_CLIP, CP_CLIP)
        if held < n_val:
            k = min(n_val - held, len(y))
            vx.append(x[:k]); vy.append(y[:k]); held += k
            x, y = x[k:], y[k:]
        if len(y):
            xb = np.hstack([x, np.ones((len(y), 1))])
            ata += xb.T @ xb
            aty += xb.T @ y
            n_seen += len(y)
    if n_seen == 0:
        raise ValueError("no training rows after validation hold-out")
    reg = np.full(dim + 1, alpha)
    reg[-1] = 1e-4
    sol = np.linalg.solve(ata + np.diag(reg), aty)
    w, bias = sol[:dim], float(sol[dim])
    scale = 127.0 / (np.max(np.abs(w)) + 1e-12)
    w_int8 = np.clip(np.round(w * scale), -127, 127).astype(np.int8)
    inv_scale = float(1.0 / scale)
    metrics = {"train_rows": int(n_seen), "validation_rows": int(held)}
    if held:
        X = np.vstack(vx); Y = np.concatenate(vy)
        pred = X @ (w_int8.astype(np.float64) * inv_scale) + bias
        metrics["val_mae_cp"] = round(float(np.mean(np.abs(pred - Y))), 2)
        metrics["val_pearson"] = round(float(np.corrcoef(pred, Y)[0, 1]), 4) if held > 1 else None
    return w_int8, inv_scale, bias, metrics


def main() -> int:
    """Fit the auxiliary linear head on the selected datasets and write its C header. Returns 0 on
    success (also for `--show-config`), 2 on a bad argument and 1 on a failure.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--dataset", action="append", default=None,
                    help="parquet dataset directory (repeatable); default: Stockfish-labelled corpus")
    ap.add_argument("--positions", type=int, default=DEFAULT_POSITIONS)
    ap.add_argument("--validation", type=int, default=DEFAULT_VALIDATION)
    ap.add_argument("--alpha", type=float, default=DEFAULT_ALPHA, help="ridge regularization")
    ap.add_argument("--checkpoint", type=Path, default=None, help="override checkpoints/<profile>/latest.pt")
    ap.add_argument("--output-dir", type=Path, default=None, help="default: artifacts/aux_head/<profile>")
    ap.add_argument("--install", action="store_true",
                    help="also copy the header into the profile's engine directory")
    ap.add_argument("--show-config", action="store_true")
    args = ap.parse_args()

    prof = profile(args.profile)
    fmt = prof.network_format
    datasets = [ROOT / d for d in (args.dataset or DEFAULT_DATASETS)]
    out_dir = args.output_dir or (ROOT / "artifacts" / "aux_head" / prof.name)
    install_path = prof.engine_dir / "fast_head_weights.h"

    if args.show_config:
        print("Auxiliary head configuration:")
        print(f"  profile     = {prof.name} ({fmt})")
        print(f"  supported   = {fmt in HEAD_DIMS}")
        print(f"  checkpoint  = {args.checkpoint or prof.latest_checkpoint}")
        for d in datasets:
            print(f"  dataset     = {d} ({'present' if d.is_dir() else 'missing'})")
        print(f"  positions   = {args.positions:,} (validation {args.validation:,})")
        print(f"  alpha       = {args.alpha}")
        print(f"  output_dir  = {out_dir}")
        print(f"  install     = {install_path if args.install else 'no'}")
        return 0

    if fmt not in HEAD_DIMS:
        print(f"Error: {prof.name} uses {fmt}, which has no fast head. Supported: {', '.join(HEAD_DIMS)}.")
        return 2
    present = [d for d in datasets if d.is_dir() and any(d.glob("*.parquet"))]
    missing = [d for d in datasets if d not in present]
    if missing:
        print("Error: missing parquet datasets: " + ", ".join(_rel(d) for d in missing))
        return 1

    features = FEATURES[fmt](prof, args.checkpoint)
    print(f"Fitting {fmt} fast head for {prof.name} from {features.source} on up to {args.positions:,} positions...")
    batches = iter_fen_cp(present, args.positions + args.validation, DEFAULT_BATCH)
    w_int8, inv_scale, bias, metrics = fit(features, batches, HEAD_DIMS[fmt], args.validation, args.alpha)

    note = (f"{metrics['train_rows']:,} train rows; val MAE {metrics.get('val_mae_cp')} cp, "
            f"r={metrics.get('val_pearson')}.")
    out_dir.mkdir(parents=True, exist_ok=True)
    header = out_dir / "fast_head_weights.h"
    tmp = header.with_suffix(".h.tmp")
    tmp.write_text(render_header(fmt, w_int8, inv_scale, bias, note), encoding="utf-8")
    tmp.replace(header)
    record = {
        "profile": prof.name,
        "network_format": fmt,
        "network_source": features.source,
        "datasets": [_rel(d) for d in present],
        "target": "stm_relative_cp_clipped_2000",
        "positions_limit": args.positions,
        "alpha": args.alpha,
        "metrics": metrics,
        "bias": bias,
        "inv_scale": inv_scale,
        "header_sha256": _sha256(header),
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "installed_to": _rel(install_path) if args.install else None,
    }
    (out_dir / "fast_head_weights.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {header} ({note})")
    if args.install:
        shutil.copy2(header, install_path)
        print(f"Installed into {install_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
