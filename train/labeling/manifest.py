"""Dataset manifest generation and validation for Zchezz training datasets.

Every dataset directory in data/ maintains a manifest.json file containing
machine-readable provenance, schema details, and row counts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1
VALID_FORMATS = {"parquet", "bin", "epd"}
WHITE_RELATIVE = "white_relative"


def scan_dataset_files(dataset_path: Path) -> Dict[str, Any]:
    """Scan dataset directory to determine file counts, formats, and columns."""
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

    if parquets:
        format_name = "parquet"
        files_count = len(parquets)
        try:
            import pyarrow.parquet as pq
            schema = pq.read_schema(parquets[0])
            columns = list(schema.names)
            positions = sum(pq.read_metadata(p).num_rows for p in parquets)
        except Exception:
            # Fall back to progress.json if pyarrow reading fails
            pass
    elif bins:
        format_name = "bin"
        files_count = len(bins)
        columns = ["sample_struct"]
        # SAMPLE_DTYPE itemsize is 75 bytes
        positions = sum(f.stat().st_size // 75 for f in bins)
    elif epds:
        format_name = "epd"
        files_count = len(epds)
        columns = ["epd_record"]
        # Count lines across epds
        for epd in epds:
            with open(epd, "rb") as f:
                positions += sum(1 for _ in f)

    # Check progress.json for supplementary metadata
    progress_file = dataset_path / "progress.json"
    if progress_file.is_file():
        try:
            pj = json.loads(progress_file.read_text(encoding="utf-8"))
            if not positions:
                positions = pj.get("total_positions", pj.get("positions", pj.get("total_rows", 0)))
        except Exception:
            pass

    return {
        "format": format_name,
        "files_count": files_count,
        "size_bytes": total_bytes,
        "columns": columns,
        "positions_count": positions,
    }


def infer_metadata_from_name(name: str) -> Dict[str, Any]:
    """Infer source, evaluator, budget, filters, and date from standard directory name."""
    source = "unknown"
    evaluator = "unrecorded"
    eval_budget = "unrecorded"
    date_val = "unrecorded"
    stage = "finetune"

    if name.startswith("extraquiet_"):
        source = "human"
        stage = "warmup" if "sf5k" in name else "finetune"
    elif name.startswith("lichess_"):
        source = "lichess"
        stage = "warmup" if ("sf_" in name or "sfdb" in name) else "finetune"
    elif name.startswith("selfplay"):
        source = "selfplay"
        stage = "finetune"
    elif name.startswith("synthetic_endgame_"):
        source = "synthetic"
        stage = "finetune"
    elif name.startswith("lc0_"):
        source = "lc0"
        stage = "finetune"
    elif name.startswith("viriformat_"):
        source = "virichess"
        stage = "excluded"
    elif name.startswith("miscelaneous_"):
        source = "mixed"
        stage = "finetune"

    if "_sfdb" in name:
        evaluator = "Stockfish DB"
        eval_budget = "varies"
    elif "_sf" in name:
        evaluator = "Stockfish"
        # Extract budget if present: e.g. sf5k, sf60k, sf50k, sf100k, sf400k, sf500k, sf1M, sfd12, sfd14
        import re
        m = re.search(r"_sf([0-9]+[kM]?|d[0-9]+)", name)
        if m:
            b = m.group(1)
            eval_budget = f"depth {b[1:]}" if b.startswith("d") else f"{b} nodes"
    elif "_zchezz" in name:
        evaluator = "Zchezz search"
        eval_budget = "search-time"
    elif "v331" in name:
        evaluator = "Zchezz v331"
        eval_budget = "search-time"
    elif "v507" in name:
        evaluator = "Zchezz v507"
        eval_budget = "search-time"

    import re
    date_match = re.search(r"_data(\d{8})", name)
    if date_match:
        d = date_match.group(1)
        date_val = f"{d[:4]}-{d[4:6]}-{d[6:]}"

    return {
        "source": source,
        "evaluator": evaluator,
        "eval_budget": eval_budget,
        "date": date_val,
        "stage": stage,
    }


def build_manifest(
    dataset_path: Path,
    *,
    engine_version: str = "v335",
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
    has_result = "result" in cols or "_res" in name
    is_filtered = "_filter" in name or "_q" in name

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "format": scanned["format"],
        "source": inferred["source"],
        "engine_version": engine_version,
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
        "is_filtered": is_filtered,
        "filter_type": "quiet" if is_filtered else "none",
        "date": inferred["date"],
        "stage": inferred["stage"],
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
