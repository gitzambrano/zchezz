"""Dataset manifest generation and validation for Zchezz training datasets.

Every dataset directory in data/ maintains a manifest.json file containing
machine-readable provenance, schema details, row counts, and outcome statistics.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1
VALID_FORMATS = {"parquet", "bin", "epd"}
WHITE_RELATIVE = "white_relative"


def scan_dataset_files(dataset_path: Path) -> Dict[str, Any]:
    """Scan dataset directory to determine file counts, formats, columns, and result statistics."""
    dataset_path = Path(dataset_path)
    if not dataset_path.is_dir():
        raise NotADirectoryError(f"Dataset path is not a directory: {dataset_path}")

    parquets = sorted(dataset_path.glob("*.parquet"))
    bins = sorted(dataset_path.glob("*.bin"))
    epds = sorted(dataset_path.glob("*.epd"))

    total_bytes = sum(f.stat().st_size for f in dataset_path.iterdir() if f.is_file())
    columns: List[str] = []
    positions = 0
    format_name = "unknown"
    files_count = 0
    res_rate: Optional[float] = None
    res_dist: Optional[Dict[str, Any]] = None

    if parquets:
        format_name = "parquet"
        files_count = len(parquets)
        try:
            import pyarrow.parquet as pq
            schema = pq.read_schema(parquets[0])
            columns = list(schema.names)
            positions = sum(pq.read_metadata(p).num_rows for p in parquets)

            if "result" in columns:
                tot_rows = 0
                val_rows = 0
                w, d, l = 0, 0, 0
                sample_p = parquets[:10] if len(parquets) > 10 else parquets
                for p in sample_p:
                    t = pq.read_table(p, columns=["result"])
                    col = t["result"]
                    tot_rows += len(col)
                    if col.type == "string" or col.type == "large_string":
                        vals = col.to_pylist()
                        for v in vals:
                            if v in ("1-0", "1.0", 1.0):
                                w += 1
                                val_rows += 1
                            elif v in ("0-1", "0.0", 0.0):
                                l += 1
                                val_rows += 1
                            elif v in ("1/2-1/2", "0.5", 0.5):
                                d += 1
                                val_rows += 1
                    else:
                        import numpy as np
                        arr = col.to_numpy()
                        finite = np.isfinite(arr)
                        val_rows += int(np.sum(finite))
                        sub = arr[finite]
                        w += int(np.sum(sub == 1.0))
                        d += int(np.sum(sub == 0.5))
                        l += int(np.sum(sub == 0.0))
                res_rate = round(val_rows / tot_rows, 4) if tot_rows else 0.0
                res_dist = {"wins": w, "draws": d, "losses": l, "sampled_rows": tot_rows}
        except Exception:
            pass
    elif bins:
        format_name = "bin"
        files_count = len(bins)
        columns = ["sample_struct"]
        positions = sum(f.stat().st_size // 75 for f in bins)
        res_rate = 1.0
        res_dist = {"note": "game_result packed inside 75-byte SAMPLE struct"}
    elif epds:
        format_name = "epd"
        files_count = len(epds)
        columns = ["epd_record"]
        for epd in epds:
            with open(epd, "rb") as f:
                positions += sum(1 for _ in f)

    # Check progress.json for supplementary metadata and raw input provenance
    progress_file = dataset_path / "progress.json"
    raw_source = None
    if progress_file.is_file():
        try:
            pj = json.loads(progress_file.read_text(encoding="utf-8"))
            if not positions:
                positions = pj.get("total_positions", pj.get("positions", pj.get("total_rows", 0)))
            raw_source = list(pj.keys())[0] if pj else None
        except Exception:
            pass

    return {
        "format": format_name,
        "files_count": files_count,
        "size_bytes": total_bytes,
        "columns": columns,
        "positions_count": positions,
        "result_rate": res_rate,
        "result_distribution": res_dist,
        "raw_source_input": raw_source,
    }


def infer_metadata_from_name(name: str) -> Dict[str, Any]:
    """Infer source, played_by, engine_version, evaluator, budget, filters, and date from name."""
    source = "unknown"
    played_by = "unknown"
    engine_ver = "not_applicable"
    stage = "finetune"

    if name.startswith("extraquiet_"):
        source = "human"
        played_by = "humans"
        stage = "warmup" if "sf5k" in name else "finetune"
    elif name.startswith("lichess_"):
        source = "lichess"
        played_by = "humans"
        stage = "warmup" if ("sf_" in name or "sfdb" in name) else "finetune"
    elif name.startswith("selfplay"):
        source = "selfplay"
        if "v331" in name:
            engine_ver = "v331"
            played_by = "Zchezz v331"
        elif "v507" in name:
            engine_ver = "v507"
            played_by = "Zchezz v507"
        elif "lichess" in name:
            engine_ver = "zchezz_dev"
            played_by = "Zchezz (from Lichess endgames)"
        else:
            engine_ver = "zchezz_dev"
            played_by = "Zchezz"
        stage = "finetune"
    elif name.startswith("synthetic_endgame_"):
        source = "synthetic"
        played_by = "procedural_generator"
        engine_ver = "none"
        stage = "finetune"
    elif name.startswith("lc0_"):
        source = "lc0"
        played_by = "Leela Chess Zero"
        engine_ver = "lc0_t91"
        stage = "finetune"
    elif name.startswith("viriformat_"):
        source = "virichess"
        played_by = "Virichess"
        engine_ver = "virichess_engine"
        stage = "excluded"
    elif name.startswith("miscelaneous_"):
        source = "mixed"
        played_by = "mixed"
        stage = "finetune"

    evaluator = "unrecorded"
    eval_budget = "unrecorded"
    if "_sfdb" in name:
        evaluator = "Stockfish DB"
        eval_budget = "varies"
    elif "_sf" in name:
        evaluator = "Stockfish"
        m = re.search(r"_sf([0-9]+[kM]?|d[0-9]+)", name)
        if m:
            b = m.group(1)
            eval_budget = f"depth {b[1:]}" if b.startswith("d") else f"{b} nodes"
    elif "_zchezz" in name:
        evaluator = f"Zchezz search ({engine_ver})"
        eval_budget = "search-time"
    elif "v331" in name:
        evaluator = "Zchezz v331 search"
        eval_budget = "search-time"
    elif "v507" in name:
        evaluator = "Zchezz v507 search"
        eval_budget = "search-time"
    elif name.startswith("lc0_"):
        evaluator = "Leela / Stockfish"
        eval_budget = "mixed"

    date_val = "unrecorded"
    date_match = re.search(r"_data(\d{8})", name)
    if date_match:
        d = date_match.group(1)
        date_val = f"{d[:4]}-{d[4:6]}-{d[6:]}"

    is_filtered = "_filter" in name or "_q" in name
    filter_type = "endgame+quiet" if "endgame" in name and is_filtered else ("quiet" if is_filtered else "none")

    return {
        "source": source,
        "played_by": played_by,
        "engine_version": engine_ver,
        "evaluator": evaluator,
        "eval_budget": eval_budget,
        "date": date_val,
        "stage": stage,
        "is_filtered": is_filtered,
        "filter_type": filter_type,
    }


def build_manifest(
    dataset_path: Path,
    *,
    engine_version: Optional[str] = None,
    engine_commit: str = "unrecorded",
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a manifest dictionary for a dataset directory."""
    dataset_path = Path(dataset_path)
    name = dataset_path.name
    scanned = scan_dataset_files(dataset_path)
    inferred = infer_metadata_from_name(name)

    cols = scanned["columns"]
    has_cp = "cp" in cols or "_cp" in name
    has_result = "result" in cols or scanned["result_rate"] is not None

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "format": scanned["format"],
        "source": inferred["source"],
        "played_by": inferred["played_by"],
        "engine_version": engine_version if engine_version is not None else inferred["engine_version"],
        "engine_commit": engine_commit,
        "evaluator": inferred["evaluator"],
        "eval_budget": inferred["eval_budget"],
        "point_of_view": WHITE_RELATIVE,
        "positions_count": scanned["positions_count"],
        "files_count": scanned["files_count"],
        "size_bytes": scanned["size_bytes"],
        "columns": cols,
        "has_cp": has_cp,
        "has_result": has_result,
        "result_rate": scanned["result_rate"],
        "result_distribution": scanned["result_distribution"],
        "is_filtered": inferred["is_filtered"],
        "filter_type": inferred["filter_type"],
        "date": inferred["date"],
        "stage": inferred["stage"],
        "raw_source_input": scanned["raw_source_input"],
    }

    if overrides:
        manifest.update(overrides)

    return manifest


def write_manifest(dataset_path: Path, manifest: Optional[Dict[str, Any]] = None) -> Path:
    """Write manifest.json inside the specified dataset directory."""
    dataset_path = Path(dataset_path)
    if manifest is None:
        manifest = build_manifest(dataset_path)

    out_path = dataset_path / "manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path


def validate_manifest(manifest: Dict[str, Any]) -> bool:
    """Validate manifest structure against required constraints."""
    required = {
        "schema_version",
        "name",
        "format",
        "point_of_view",
        "positions_count",
        "columns",
        "has_cp",
        "has_result",
    }
    for field in required:
        if field not in manifest:
            raise ValueError(f"Missing required manifest field: {field}")

    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema version: {manifest['schema_version']}")

    if manifest["format"] not in VALID_FORMATS:
        raise ValueError(f"Invalid format '{manifest['format']}'; must be one of {VALID_FORMATS}")

    if manifest["point_of_view"] != WHITE_RELATIVE:
        raise ValueError(f"Point of view must be '{WHITE_RELATIVE}', got '{manifest['point_of_view']}'")

    return True


def generate_all_manifests(data_root: Optional[Path] = None) -> List[Path]:
    """Generate manifest.json for all dataset directories in data_root."""
    if data_root is None:
        data_root = Path(__file__).resolve().parents[2] / "data"

    written: List[Path] = []
    if not data_root.is_dir():
        return written

    for item in sorted(data_root.iterdir()):
        if item.is_dir():
            p = write_manifest(item)
            written.append(p)
    return written


if __name__ == "__main__":
    written_paths = generate_all_manifests()
    print(f"Generated {len(written_paths)} manifest.json files in data directory.")
