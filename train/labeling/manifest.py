"""Dataset manifests: machine-readable provenance for every ``data/<dataset>/``.

Each dataset directory carries ``manifest.json`` (schema version 2). The
manifests are tracked in git even though the data files are not, so the
provenance record survives the loss of the data. ``docs/datasets.md`` renders
its catalog table from them (``--catalog``) and a test keeps the two in sync.

Field groups and how they are filled:

- **measured** (``format``, ``files_count``, ``positions_count``,
  ``size_bytes``, ``columns``, ``has_cp``, ``has_result``, ``result_rate``,
  ``result_distribution``): recomputed from the files on every refresh. Result
  statistics cover every row, not a sample.
- **provenance** (``source``, ``played_by``, ``engine_version``,
  ``engine_commit``, ``evaluator``, ``eval_budget``, ``date``, ``filter_type``,
  ``raw_source_input``) and **usage** (``stage``): each value carries an
  evidence level in ``evidence[field]``.

Evidence levels, strongest first: ``recorded`` (written by the producing tool
at generation time), ``owner`` (stated by the project owner), ``measured``,
``inferred`` (parsed from the directory name), ``unknown``. A refresh never
replaces a value with one of weaker evidence, so curated and producer-recorded
values survive ``--generate``. ``producer`` holds the producing tool's
configuration when the tool supplied it.

All scores are White-relative (``point_of_view == "white_relative"``).

Bare run: report manifest status for ``data/`` without writing. ``--generate``
refreshes manifests; ``--catalog`` rewrites the generated table in
``docs/datasets.md``.
"""
from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 2
VALID_FORMATS = {"parquet", "bin", "epd"}
WHITE_RELATIVE = "white_relative"
EVIDENCE_RANK = {"unknown": 0, "inferred": 1, "measured": 2, "owner": 3, "recorded": 3}
PROVENANCE_FIELDS = ("source", "played_by", "engine_version", "engine_commit", "evaluator",
                     "eval_budget", "date", "filter_type", "raw_source_input", "stage")
MEASURED_FIELDS = ("format", "files_count", "positions_count", "size_bytes", "columns",
                   "has_cp", "has_result", "result_rate", "result_distribution")

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "data"
CATALOG_DOC = ROOT / "docs" / "datasets.md"
CATALOG_BEGIN = "<!-- BEGIN GENERATED CATALOG (python train/labeling/manifest.py --catalog) -->"
CATALOG_END = "<!-- END GENERATED CATALOG -->"


# ── measurement ──────────────────────────────────────────────────────────────

def _result_stats_parquet(files: List[Path]) -> tuple[Optional[float], Optional[Dict[str, int]]]:
    import numpy as np
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    rows = valid = w = d = l = 0
    for f in files:
        col = pq.read_table(f, columns=["result"])["result"]
        rows += len(col)
        if col.type in ("string", "large_string"):
            vals = col.to_pylist()
            w += sum(v in ("1-0", "1.0", "1") for v in vals)
            l += sum(v in ("0-1", "0.0", "0") for v in vals)
            d += sum(v in ("1/2-1/2", "0.5") for v in vals)
        else:
            arr = pc.cast(col, "float64").to_numpy(zero_copy_only=False)
            arr = arr[np.isfinite(arr)]
            w += int(np.sum(arr == 1.0)); d += int(np.sum(arr == 0.5)); l += int(np.sum(arr == 0.0))
    valid = w + d + l
    if not rows:
        return None, None
    return round(valid / rows, 4), {"white_wins": w, "draws": d, "black_wins": l, "rows": rows}


def scan_dataset_files(dataset_path: Path) -> Dict[str, Any]:
    """Measure format, counts, columns and outcome statistics from the files."""
    dataset_path = Path(dataset_path)
    if not dataset_path.is_dir():
        raise NotADirectoryError(f"Dataset path is not a directory: {dataset_path}")

    parquets = sorted(dataset_path.glob("*.parquet"))
    bins = sorted(dataset_path.glob("*.bin"))
    epds = sorted(dataset_path.glob("*.epd"))
    out: Dict[str, Any] = {
        "format": "unknown", "files_count": 0, "positions_count": 0, "columns": [],
        "result_rate": None, "result_distribution": None, "bin_provenance": None,
        "size_bytes": sum(f.stat().st_size for f in dataset_path.iterdir()
                          if f.is_file() and f.name != "manifest.json"),
    }
    if parquets:
        import pyarrow.parquet as pq
        out["format"] = "parquet"
        out["files_count"] = len(parquets)
        out["columns"] = list(pq.read_schema(parquets[0]).names)
        out["positions_count"] = sum(pq.read_metadata(p).num_rows for p in parquets)
        if "result" in out["columns"]:
            out["result_rate"], out["result_distribution"] = _result_stats_parquet(parquets)
    elif bins:
        import sys
        sys.path.insert(0, str(ROOT / "train"))
        from dataset import SAMPLE_DTYPE, read_bin_header  # noqa: E402
        out["format"] = "bin"
        out["files_count"] = len(bins)
        out["columns"] = [name for name in SAMPLE_DTYPE.names]
        provs = set()
        for f in bins:
            offset, prov = read_bin_header(str(f))
            out["positions_count"] += (f.stat().st_size - offset) // SAMPLE_DTYPE.itemsize
            provs.add((prov.engine_version, prov.weight_path) if prov.known else ("unknown", ""))
        out["bin_provenance"] = sorted(provs)
    elif epds:
        out["format"] = "epd"
        out["files_count"] = len(epds)
        out["columns"] = ["epd_record"]
        for epd in epds:
            with open(epd, "rb") as f:
                out["positions_count"] += sum(1 for _ in f)

    progress = dataset_path / "progress.json"
    out["raw_source_input"] = None
    if progress.is_file():
        try:
            pj = json.loads(progress.read_text(encoding="utf-8"))
            out["raw_source_input"] = next(iter(pj), None)
        except (ValueError, OSError):
            pass
    return out


# ── name inference (weakest evidence) ────────────────────────────────────────

def infer_metadata_from_name(name: str) -> Dict[str, Any]:
    """Guess provenance from the directory-name convention; values are 'inferred'."""
    if name.startswith("extraquiet_"):
        source, played_by = "human", "humans"
    elif name.startswith("lichess_"):
        source, played_by = "lichess", "humans"
    elif name.startswith("selfplay"):
        source, played_by = "selfplay", "Zchezz"
    elif name.startswith("synthetic_endgame_"):
        source, played_by = "synthetic", "none (generated positions)"
    elif name.startswith("lc0_"):
        source, played_by = "lc0", "Leela Chess Zero"
    elif name.startswith("viriformat_"):
        source, played_by = "virichess", "Virichess"
    else:
        source = played_by = "unknown"

    m = re.search(r"_v(\d{3})(?:_|$)", name)
    engine_version = f"v{m.group(1)}" if m else "unknown"

    evaluator = eval_budget = "unknown"
    if "_sfdb" in name:
        evaluator, eval_budget = "Stockfish (bundled with lichess database)", "varies"
    elif re.search(r"_sf(\d|d\d|_|$)", name):
        evaluator = "Stockfish"
        b = re.search(r"_sf(\d+[kM]?|d\d+)(?:_|$)", name)
        if b:
            v = b.group(1)
            eval_budget = f"depth {v[1:]}" if v.startswith("d") else f"{v} nodes"
    elif "_zchezz" in name:
        evaluator, eval_budget = "Zchezz search during self-play", "search-time"

    date = "unknown"
    dm = re.search(r"_data(\d{8})", name)
    if dm:
        d = dm.group(1)
        date = f"{d[:4]}-{d[4:6]}-{d[6:]}"

    quiet = "_filter" in name or name.endswith("_q")
    filter_type = ("endgame+quiet" if quiet else "endgame") if "endgame" in name else ("quiet" if quiet else "none")
    return {"source": source, "played_by": played_by, "engine_version": engine_version,
            "engine_commit": "unknown", "evaluator": evaluator, "eval_budget": eval_budget,
            "date": date, "filter_type": filter_type, "raw_source_input": None, "stage": "unknown"}


# ── build / merge ────────────────────────────────────────────────────────────

def _load(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def build_manifest(dataset_path: Path, *, provenance: Optional[Dict[str, Any]] = None,
                   evidence: str = "recorded", producer: Optional[Dict[str, Any]] = None,
                   previous: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merge measured values, inferred guesses, the previous manifest and new provenance.

    ``provenance`` values are stored with evidence level ``evidence``. For each
    provenance field the strongest available evidence wins; ties keep the newest.
    """
    dataset_path = Path(dataset_path)
    if evidence not in EVIDENCE_RANK:
        raise ValueError(f"unknown evidence level {evidence!r}")
    scanned = scan_dataset_files(dataset_path)
    inferred = infer_metadata_from_name(dataset_path.name)
    if previous is None:
        previous = _load(dataset_path / "manifest.json")
    prev_ev = previous.get("evidence", {}) if previous.get("schema_version") == SCHEMA_VERSION else {}

    values: Dict[str, Any] = {}
    ev: Dict[str, str] = {}
    for field in PROVENANCE_FIELDS:
        val, lvl = inferred.get(field), "inferred"
        if val in (None, "unknown"):
            lvl = "unknown"
        if field == "raw_source_input" and scanned["raw_source_input"]:
            val, lvl = scanned["raw_source_input"], "measured"
        if field in prev_ev and EVIDENCE_RANK[prev_ev[field]] >= EVIDENCE_RANK[lvl]:
            val, lvl = previous.get(field), prev_ev[field]
        if provenance and field in provenance and EVIDENCE_RANK[evidence] >= EVIDENCE_RANK[lvl]:
            val, lvl = provenance[field], evidence
        values[field], ev[field] = val, lvl
    if scanned["bin_provenance"] and len(scanned["bin_provenance"]) == 1:
        ver, wpath = scanned["bin_provenance"][0]
        if ver != "unknown" and EVIDENCE_RANK[ev["engine_version"]] < EVIDENCE_RANK["recorded"]:
            values["engine_version"], ev["engine_version"] = f"{ver} ({wpath})", "recorded"

    cols = scanned["columns"]
    manifest: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "name": dataset_path.name,
        "point_of_view": WHITE_RELATIVE,
        "format": scanned["format"],
        "files_count": scanned["files_count"],
        "positions_count": scanned["positions_count"],
        "size_bytes": scanned["size_bytes"],
        "columns": cols,
        "has_cp": "cp" in cols or "eval_cp" in cols,
        "has_result": "result" in cols or "game_result" in cols,
        "result_rate": scanned["result_rate"],
        "result_distribution": scanned["result_distribution"],
        **values,
        "evidence": dict(ev, **{f: "measured" for f in MEASURED_FIELDS}),
        "producer": producer if producer is not None else previous.get("producer"),
        "notes": previous.get("notes"),
        "scanned_utc": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
    }
    return manifest


def write_manifest(dataset_path: Path, manifest: Optional[Dict[str, Any]] = None, **kwargs) -> Path:
    """Build (unless given) and atomically write ``manifest.json``."""
    dataset_path = Path(dataset_path)
    if manifest is None:
        manifest = build_manifest(dataset_path, **kwargs)
    validate_manifest(manifest)
    out = dataset_path / "manifest.json"
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, out)
    return out


def validate_manifest(manifest: Dict[str, Any]) -> bool:
    required = {"schema_version", "name", "format", "point_of_view", "positions_count",
                "columns", "has_cp", "has_result", "evidence"}
    missing = required - set(manifest)
    if missing:
        raise ValueError(f"Missing required manifest field(s): {sorted(missing)}")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema version: {manifest['schema_version']}")
    if manifest["format"] not in VALID_FORMATS:
        raise ValueError(f"Invalid format '{manifest['format']}'; must be one of {sorted(VALID_FORMATS)}")
    if manifest["point_of_view"] != WHITE_RELATIVE:
        raise ValueError(f"Point of view must be '{WHITE_RELATIVE}', got '{manifest['point_of_view']}'")
    for field, lvl in manifest["evidence"].items():
        if lvl not in EVIDENCE_RANK:
            raise ValueError(f"{manifest['name']}: evidence for {field} is {lvl!r}")
    return True


def dataset_dirs(data_root: Path = DATA_ROOT) -> List[Path]:
    if not data_root.is_dir():
        return []
    def is_dataset(p: Path) -> bool:
        return p.is_dir() and any(any(p.glob(g)) for g in ("*.parquet", "*.bin", "*.epd"))
    return sorted(p for p in data_root.iterdir() if is_dataset(p))


def load_manifests(data_root: Path = DATA_ROOT) -> List[Dict[str, Any]]:
    return [_load(p) for p in sorted(data_root.glob("*/manifest.json"))]


# ── catalog rendering ────────────────────────────────────────────────────────

_TAG = {"recorded": "R", "owner": "O", "measured": "M", "inferred": "I", "unknown": "?"}


def _cell(m: Dict[str, Any], field: str) -> str:
    val = m.get(field)
    lvl = m.get("evidence", {}).get(field, "unknown")
    if val in (None, "", "unknown"):
        return "? [?]"
    return f"{val} [{_TAG[lvl]}]"


def render_catalog(manifests: List[Dict[str, Any]]) -> str:
    rows = ["| Dataset | Format | Positions | MB | Played by | Evaluator | Budget | Result % | Date | Stage |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    total_pos = total_mb = 0.0
    for m in sorted(manifests, key=lambda x: x["name"]):
        mb = m.get("size_bytes", 0) / 1e6
        total_pos += m.get("positions_count", 0)
        total_mb += mb
        rr = m.get("result_rate")
        rows.append("| `{}` | {} | {:,} | {:,.0f} | {} | {} | {} | {} | {} | {} |".format(
            m["name"], m["format"], m["positions_count"], mb, _cell(m, "played_by"),
            _cell(m, "evaluator"), _cell(m, "eval_budget"),
            f"{rr * 100:.1f}%" if rr is not None else "—", _cell(m, "date"), _cell(m, "stage")))
    rows.append("")
    rows.append(f"**{len(manifests)} datasets, {int(total_pos):,} positions, {total_mb:,.0f} MB.** "
                "Evidence: [R] recorded by the producing tool, [O] stated by the owner, "
                "[M] measured, [I] inferred from the directory name, [?] unknown.")
    return "\n".join(rows)


def update_catalog_doc(manifests: List[Dict[str, Any]], doc: Path = CATALOG_DOC) -> bool:
    text = doc.read_text(encoding="utf-8")
    if CATALOG_BEGIN not in text or CATALOG_END not in text:
        raise ValueError(f"{doc} lacks the generated-catalog markers")
    head, rest = text.split(CATALOG_BEGIN, 1)
    _, tail = rest.split(CATALOG_END, 1)
    new = f"{head}{CATALOG_BEGIN}\n{render_catalog(manifests)}\n{CATALOG_END}{tail}"
    if new != text:
        doc.write_text(new, encoding="utf-8")
        return True
    return False


def catalog_in_doc(doc: Path = CATALOG_DOC) -> str:
    text = doc.read_text(encoding="utf-8")
    return text.split(CATALOG_BEGIN, 1)[1].split(CATALOG_END, 1)[0].strip()


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", type=Path, default=DATA_ROOT)
    ap.add_argument("--show-config", action="store_true", help="print configuration and exit")
    ap.add_argument("--generate", action="store_true", help="refresh manifest.json in every dataset directory")
    ap.add_argument("--catalog", action="store_true", help="re-render the table in docs/datasets.md")
    args = ap.parse_args()

    if args.show_config:
        print(f"data_root={args.data_root}\nschema_version={SCHEMA_VERSION}\n"
              f"evidence_levels={list(EVIDENCE_RANK)}\npoint_of_view={WHITE_RELATIVE}\ncatalog={CATALOG_DOC}")
        return 0
    dirs = dataset_dirs(args.data_root)
    if args.generate:
        for d in dirs:
            write_manifest(d)
            print(f"  wrote {d.name}/manifest.json")
    if args.catalog:
        changed = update_catalog_doc(load_manifests(args.data_root))
        print(f"{CATALOG_DOC.relative_to(ROOT)}: {'updated' if changed else 'unchanged'}")
    if not (args.generate or args.catalog):
        for d in dirs:
            m = _load(d / "manifest.json")
            state = ("missing" if not m else f"schema v{m.get('schema_version')}"
                     if m.get("schema_version") != SCHEMA_VERSION else "ok")
            print(f"  {d.name:<56} {state}")
        print("Read-only status. Use --generate to refresh manifests, --catalog to refresh docs/datasets.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
