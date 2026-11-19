#!/usr/bin/env python3
"""Audit every file of every training dataset under data/ for wrong labels.

Read-only for data/. Writes a report to artifacts/data_audit/<UTC stamp>/.
A bare run audits all datasets. ``--dataset NAME`` (repeatable) limits it.
The exit code is 1 when any file fails.

Checks per file (parquet and .bin):
  * FEN syntax (move counters optional; Shredder/Chess960 castling letters allowed)
    and one king per side;
  * ``cp`` finite and ``|cp| <= 32000``; a row without ``cp`` is a warning when it
    has a ``result`` (trainers then use the result alone) and a failure otherwise;
  * ``result`` in {0, 0.5, 1} or {"1-0", "0-1", "1/2-1/2"} (missing is allowed);
  * point of view, for each side to move separately:
      - material sign: in positions where one side is at least a rook ahead and
        ``|cp| >= 50``, cp must have the sign of the material balance;
      - result: corr(tanh(cp/400), result) must be positive.
    A White-relative dataset passes both for White to move and for Black to
    move. A dataset with cp relative to the side to move fails on Black.
``data/_quarantine/`` is never audited as training data.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DATA_ROOT = ROOT / "data"
OUT_ROOT = ROOT / "artifacts" / "data_audit"

MATERIAL_MIN = 5          # pawns of material edge for the material-sign check
CP_MIN = 50               # ignore near-zero evaluations in the material-sign check
MIN_ROWS = 200            # minimum rows per side to move before a check can fail
MATERIAL_AGREE_MIN = 0.85 # minimum share of rows whose cp has the material sign
CORR_MIN = 0.05           # minimum corr(tanh(cp/400), result) per side to move
CP_ABS_MAX = 32000          # int16 .bin writers clamp mate scores to ±32000

FEN_RE = (r"^([pnbrqkPNBRQK1-8]{1,8}/){7}[pnbrqkPNBRQK1-8]{1,8} [wb] "
          r"(-|[KQkqA-Ha-h]{1,4}) (-|[a-h][36])( \d+ \d+)?$")   # move counters are optional (EPD style)
PIECE_VALUE = {"p": 1, "n": 3, "b": 3, "r": 5, "q": 9}


def _side_stats(cp, mat, res, white_mask):
    """Per-side statistics from White-relative `cp`, material balance `mat`, optional White result
    `res` and the White-to-move mask.

    For each side to move: rows and agreement of the `cp` sign with the material sign, and
    corr(tanh(cp/400), result) when results exist.
    """
    out = {}
    for side, m in (("white", white_mask), ("black", ~white_mask)):
        s = {}
        k = m & (np.abs(mat) >= MATERIAL_MIN) & (np.abs(cp) >= CP_MIN)
        s["material_rows"] = int(k.sum())
        s["material_agree"] = float(np.mean(np.sign(cp[k]) == np.sign(mat[k]))) if k.any() else None
        if res is not None:
            r = m & ~np.isnan(res)
            s["result_rows"] = int(r.sum())
            ok = r.sum() >= 3 and np.std(res[r]) > 0 and np.std(cp[r]) > 0
            s["result_corr"] = float(np.corrcoef(np.tanh(cp[r] / 400.0), res[r])[0, 1]) if ok else None
        out[side] = s
    return out


def _problems(st):
    """Return the failure messages for one file's statistics: a point-of-view check below its
    threshold, or a non-zero invalid-row count.
    """
    probs = []
    for side in ("white", "black"):
        s = st["pov"][side]
        if s["material_rows"] >= MIN_ROWS and s["material_agree"] < MATERIAL_AGREE_MIN:
            probs.append(f"{side} to move: cp has the material sign in only {s['material_agree']:.1%}")
        if s.get("result_rows", 0) >= MIN_ROWS and s.get("result_corr") is not None and s["result_corr"] < CORR_MIN:
            probs.append(f"{side} to move: corr(cp, result) = {s['result_corr']:+.2f}")
    for key in ("fen_invalid", "king_count_invalid", "cp_nonfinite", "cp_out_of_range", "result_invalid",
                "label_missing"):
        if st.get(key):
            probs.append(f"{key} = {st[key]}")
    return probs


def _aggregate(results) -> dict:
    """Material-sign agreement over all files of a dataset, per side to move.

    Small files can stay under MIN_ROWS one by one; the total still must pass.
    """
    out = {"problems": []}
    for side in ("white", "black"):
        n = agree = 0
        for r in results:
            s = (r.get("pov") or {}).get(side)
            if s and s["material_rows"]:
                n += s["material_rows"]
                agree += s["material_agree"] * s["material_rows"]
        out[side] = {"material_rows": n, "material_agree": (agree / n) if n else None}
        if n >= MIN_ROWS and agree / n < MATERIAL_AGREE_MIN:
            out["problems"].append(f"{side} to move: cp has the material sign in only {agree / n:.1%}")
    return out


def audit_parquet(path: str) -> dict:
    """Audit one parquet shard (columns ``fen``, ``cp``, optional ``result``).

    Returns a dict with ``rows``, per-side ``pov`` statistics and ``problems``
    (failures) and ``warnings``. A shard without ``cp`` has no point of view to
    check and passes when it has a ``fen`` column.
    """
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    t = pq.read_table(path)
    names = t.schema.names
    st = {"file": path, "rows": t.num_rows, "columns": names}
    if "fen" not in names or "cp" not in names:
        st["problems"] = [] if "fen" in names else ["no fen column"]
        st["pov"] = None
        st["note"] = "no cp column: point of view not applicable"
        return st
    fen = t["fen"].combine_chunks()
    st["fen_invalid"] = int(pc.sum(pc.invert(pc.match_substring_regex(fen, FEN_RE))).as_py() or 0)
    parts = pc.split_pattern(fen, " ")
    board = pc.list_element(parts, 0)
    stm = pc.list_element(parts, 1)
    white = np.asarray(pc.equal(stm, "w").to_numpy(zero_copy_only=False), dtype=bool)
    kw = pc.count_substring(board, "K").to_numpy(zero_copy_only=False)
    kb = pc.count_substring(board, "k").to_numpy(zero_copy_only=False)
    st["king_count_invalid"] = int(np.sum((kw != 1) | (kb != 1)))
    mat = np.zeros(t.num_rows, dtype=np.int64)
    for ch, v in PIECE_VALUE.items():
        mat += v * (pc.count_substring(board, ch.upper()).to_numpy(zero_copy_only=False).astype(np.int64)
                    - pc.count_substring(board, ch).to_numpy(zero_copy_only=False).astype(np.int64))
    cpcol = t["cp"].combine_chunks()
    st["cp_missing"] = int(cpcol.null_count)
    cp = np.asarray(pc.fill_null(pc.cast(cpcol, "float64"), np.nan).to_numpy(zero_copy_only=False), dtype=float)
    st["cp_nonfinite"] = int(np.sum(~np.isfinite(cp)) - st["cp_missing"])
    st["cp_out_of_range"] = int(np.sum(np.abs(np.nan_to_num(cp)) > CP_ABS_MAX))
    res = None
    if "result" in names:
        rc = t["result"].combine_chunks()
        if str(rc.type) in ("string", "large_string"):
            vals = rc.to_pylist()
            mp = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}
            res = np.array([np.nan if v is None else mp.get(v, -1.0) for v in vals], dtype=float)
        else:
            res = np.asarray(pc.fill_null(pc.cast(rc, "float64"), np.nan).to_numpy(zero_copy_only=False), dtype=float)
        bad = ~np.isnan(res) & ~np.isin(res, (0.0, 0.5, 1.0))
        st["result_invalid"] = int(bad.sum())
        res = np.where(bad, np.nan, res)
        st["result_rows"] = int(np.sum(~np.isnan(res)))
    fin = np.isfinite(cp)
    # A row without cp trains on its result alone (blend_target falls back per
    # cell), so it is a warning. A row with neither cp nor result has no label.
    if st["cp_missing"]:
        st["warnings"] = [f"{st['cp_missing']} rows without cp (trained on result only)"]
    no_res = np.ones(t.num_rows, dtype=bool) if res is None else np.isnan(res)
    st["label_missing"] = int(np.sum(np.isnan(cp) & no_res))
    st["pov"] = _side_stats(cp[fin], mat[fin], None if res is None else res[fin], white[fin])
    st["problems"] = _problems(st)
    return st


def audit_bin(path: str) -> dict:
    """Audit one ``.bin`` self-play shard.

    ``eval_cp`` and ``game_result`` in these shards are relative to the side to
    move (``stm``). The function converts both to White-relative and runs the
    same point-of-view checks as ``audit_parquet``. A shard whose Black-to-move
    rows carry the wrong sign fails the Black checks. ``problems`` is also
    non-empty when the file size is not a multiple of the record size.
    """
    from train.dataset import SAMPLE_DTYPE, read_bin_header
    off, _ = read_bin_header(path)
    size = os.path.getsize(path) - off
    st = {"file": path, "format": "bin"}
    if size % SAMPLE_DTYPE.itemsize:
        st["problems"] = [f"size {size} is not a multiple of the record size"]
        return st
    a = np.fromfile(path, dtype=SAMPLE_DTYPE, offset=off)
    st["rows"] = int(len(a))
    b = a["board"].astype(np.int64)
    typ, col = b & 7, b & 24
    val = np.select([typ == 1, typ == 2, typ == 3, typ == 4, typ == 5], [1, 3, 3, 5, 9], 0)
    mat = (val * (col == 8)).sum(1) - (val * (col == 16)).sum(1)
    st["king_count_invalid"] = int(np.sum(((typ == 6) & (col == 8)).sum(1) != 1) +
                                   np.sum(((typ == 6) & (col == 16)).sum(1) != 1))
    white = a["stm"] == 0
    stm_cp = a["eval_cp"].astype(float)
    cp = np.where(white, stm_cp, -stm_cp)                      # White-relative
    gr = a["game_result"].astype(float)
    res_white = np.where(white, gr, -gr) * 0.5 + 0.5           # White result 0 / 0.5 / 1
    st["result_invalid"] = int(np.sum(~np.isin(a["game_result"], (-1, 0, 1))))
    st["cp_out_of_range"] = int(np.sum(np.abs(stm_cp) > CP_ABS_MAX))
    st["pov"] = _side_stats(cp, mat, res_white, white)
    st["problems"] = _problems(st)
    return st


def audit_file(path: str) -> dict:
    try:
        return audit_bin(path) if path.endswith(".bin") else audit_parquet(path)
    except Exception as exc:  # a file that cannot be read is a failure
        return {"file": path, "problems": [f"unreadable: {exc!r}"]}


def dataset_files(name: str, root: Path | None = None):
    d = (root or DATA_ROOT) / name
    return sorted(str(p) for p in d.iterdir() if p.suffix in (".parquet", ".bin"))


def main() -> int:
    """Audit the selected datasets in parallel and write ``report.json``.

    Returns 0 when every file passes and 1 when any file fails. ``--show-config``
    prints the settings and returns 0 without reading data.
    """
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dataset", action="append", help="dataset directory name (repeatable; default: all)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--data-root", type=Path, default=DATA_ROOT,
                    help="directory that holds the dataset directories (for example a mounted Google Drive)")
    ap.add_argument("--show-config", action="store_true", help="print settings and exit")
    args = ap.parse_args()
    data_root = args.data_root
    def is_dataset(p: Path) -> bool:
        return (p.is_dir() and not p.name.startswith("_")
                and (any(p.glob("*.parquet")) or any(p.glob("*.bin"))))
    if args.dataset:
        names = [n for n in args.dataset if not n.startswith("_")]
    else:
        names = sorted(p.name for p in data_root.iterdir() if is_dataset(p)) if data_root.is_dir() else []
    if args.show_config:
        print(f"data_root={data_root}\ndatasets={names}\nworkers={args.workers}\n"
              f"material_min={MATERIAL_MIN} cp_min={CP_MIN} material_agree_min={MATERIAL_AGREE_MIN} "
              f"corr_min={CORR_MIN} min_rows={MIN_ROWS}\noutput={OUT_ROOT}/<UTC>/report.json")
        return 0
    if not names:
        print(f"No datasets under {data_root}; nothing to audit.")
        return 0
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = OUT_ROOT / stamp
    out.mkdir(parents=True, exist_ok=True)
    report, failed = {}, 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for name in names:
            files = dataset_files(name, data_root)
            results = list(ex.map(audit_file, files, chunksize=4))
            bad = [r for r in results if r.get("problems")]
            failed += len(bad)
            rows = sum(r.get("rows", 0) for r in results)
            agg = _aggregate(results)
            if agg["problems"]:
                failed += 1
            report[name] = {"files": len(files), "rows": rows, "failed_files": len(bad),
                            "aggregate": agg, "results": results}
            status = "OK  " if not bad and not agg["problems"] else "FAIL"
            print(f"{status} {name:55s} files={len(files):5d} rows={rows:12,d} failed={len(bad)}", flush=True)
            for p in agg["problems"]:
                print(f"       dataset total: {p}")
            for r in bad[:5]:
                print(f"       {os.path.basename(r['file'])}: {'; '.join(r['problems'])}")
            if len(bad) > 5:
                print(f"       ... {len(bad) - 5} more failing files")
    (out / "report.json").write_text(json.dumps({"utc": stamp, "thresholds": {
        "material_min": MATERIAL_MIN, "cp_min": CP_MIN, "material_agree_min": MATERIAL_AGREE_MIN,
        "corr_min": CORR_MIN, "min_rows": MIN_ROWS}, "datasets": report}, indent=1), encoding="utf-8")
    print(f"\nReport: {out / 'report.json'}  ({failed} failing file(s))")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
