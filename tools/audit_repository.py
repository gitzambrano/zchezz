"""Report source organization without changes to repository files."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {"root": ROOT, "output": ROOT / "artifacts/repository_organization/audit.json", "max_file_bytes": 2_000_000}
SOURCE_SUFFIXES = {".py", ".sh", ".bat", ".ps1", ".md", ".ipynb"}
HISTORY_PREFIXES = ("experimental/", "engine/old/", "engine/c/zchezz_v3")
AGENT_PREFIXES = (".agents/", ".claude/", "skills/")


def audit(root):
    """Distinguish compatibility and historical copies from duplicate active source."""
    root = Path(root)
    names = subprocess.check_output(["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], cwd=root).decode().split("\0")
    layout_path = root / "colab/layout.json"
    layout = json.loads(layout_path.read_text(encoding="utf-8")) if layout_path.is_file() else {}
    compatibility = layout.get("compatibility_entry_points", {})
    hashes, empty, colab_elsewhere = {}, [], []
    count = 0
    for name in sorted(set(names) - {""}):
        path = root / name
        if not path.is_file() or path.is_symlink() or path.suffix not in SOURCE_SUFFIXES or path.stat().st_size > CONFIG["max_file_bytes"]:
            continue
        content = path.read_bytes()
        count += 1
        if not content and path.name != "__init__.py":
            empty.append(name)
        if content and path.name != "__init__.py":
            hashes.setdefault(hashlib.sha256(content).hexdigest(), []).append(name)
        if "colab" in path.name.lower() and not name.startswith(("colab/", "tests/")):
            colab_elsewhere.append({"path": name, "kind": "compatibility" if name in compatibility else
                                   "historical_snapshot" if name.startswith(HISTORY_PREFIXES) else "review"})
    duplicates = []
    for paths in hashes.values():
        if len(paths) < 2:
            continue
        active = [p for p in paths if not p.startswith(HISTORY_PREFIXES + AGENT_PREFIXES)]
        kind = "review" if len(active) > 1 else "historical_or_agent_copy"
        duplicates.append({"paths": paths, "kind": kind})
    missing = [{"old": old, "canonical": new} for old, new in compatibility.items()
               if not (root / old).is_file() or not (root / new).is_file()]
    return {"source_files": count, "empty_sources": empty, "duplicates": duplicates,
            "colab_sources_elsewhere": colab_elsewhere, "missing_compatibility_targets": missing,
            "notes": ["No source or private profile directories were deleted.",
                      "Historical and agent integration copies require context before removal.",
                      "Ignored outputs and files over 2 MB are outside this source audit."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=CONFIG["output"])
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()
    if args.show_config:
        print(json.dumps(CONFIG, default=str, indent=2))
        return 0
    report = audit(CONFIG["root"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    review = sum(row["kind"] == "review" for row in report["duplicates"])
    print(f"Sources: {report['source_files']} | active duplicate groups for review: {review} | missing compatibility targets: {len(report['missing_compatibility_targets'])}")
    print(f"Report: {args.output}")
    return int(bool(report["missing_compatibility_targets"]))


if __name__ == "__main__":
    raise SystemExit(main())
