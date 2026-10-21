#!/usr/bin/env python3
"""Safe repository cleanup utility.

Removes ephemeral, temporary, and obsolete generated artifacts while strictly
protecting source files, tracked git files, active weights, tablebases, opening
books, and filtered training datasets.

Usage:
  python tools/clean_repository.py              # Safe cleanup of ephemeral & obsolete targets
  python tools/clean_repository.py --dry-run    # Non-destructive inspection of cleanup targets
  python tools/clean_repository.py --show-config # Print cleanup configuration and exit
  python tools/clean_repository.py --all        # Deep cleanup including intermediate epoch checkpoints
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

# Immutable safety protections - these must NEVER be touched under any circumstance
PROTECTED_PATHS = {
    ROOT / "engine/ACTIVE_ENGINE",
    ROOT / "engine/build",
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
    ROOT / "Readme.md",
    ROOT / "tablebases",
    ROOT / "openings",
    ROOT / "endgames",
}

PROTECTED_PREFIXES = (
    str(ROOT / "engine/c"),
    str(ROOT / "tablebases"),
    str(ROOT / "openings"),
    str(ROOT / "endgames"),
)

CLEANUP_CONFIG = {
    "clean_caches": True,
    "clean_scratch": True,
    "clean_obsolete_artifacts": True,
    "clean_deprecated_checkpoints": True,
    "clean_intermediate_epochs": False,
    "clean_duplicate_stockfish": True,
    "clean_redundant_raw_data": False,
}


def get_tracked_files(root: Path) -> set[Path]:
    """Return absolute paths for all files tracked by git."""
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "-z"],
            cwd=root,
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="ignore")
        return {root / f for f in output.split("\0") if f}
    except Exception:
        return set()


def handle_remove_readonly(func, path, exc):
    """Clear Windows read-only attribute if permission error occurs."""
    excvalue = exc[1]
    if func in (os.rmdir, os.remove, os.unlink) and excvalue.errno in (5, 13):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    else:
        raise


def get_path_size(path: Path) -> int:
    """Calculate total size of file or directory in bytes."""
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            p = os.path.join(root, f)
            try:
                total += os.path.getsize(p)
            except OSError:
                pass
    return total


def collect_targets(
    root: Path,
    tracked: set[Path],
    clean_intermediate_epochs: bool = False,
    clean_redundant_raw_data: bool = False,
) -> list[tuple[Path, str, int]]:
    """Scan and collect safe deletion candidates."""
    targets: list[tuple[Path, str, int]] = []

    def is_safe(p: Path) -> bool:
        if p in PROTECTED_PATHS:
            return False
        p_str = str(p)
        for prefix in PROTECTED_PREFIXES:
            if p_str.startswith(prefix):
                # Ensure no source, Makefile, or active weights in engine/c are touched
                if p.suffix in (".c", ".h", ".bin", ".wasm", ".js") or p.name in ("Makefile", "zchezz.exe"):
                    return False
        # Never delete tracked git files
        if p in tracked:
            return False
        return True

    # 1. Python caches & bytecode
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirpath:
            continue
        base = os.path.basename(dirpath)
        if base in ("__pycache__", ".pytest_cache"):
            p = Path(dirpath)
            if is_safe(p):
                targets.append((p, "cache", get_path_size(p)))
            # Do not recurse or list files inside this cache dir
            dirnames.clear()
            continue
        for f in filenames:
            if f.endswith((".pyc", ".pyo")):
                p = Path(dirpath) / f
                if is_safe(p):
                    targets.append((p, "cache", get_path_size(p)))

    # 2. Scratch files & temporary files
    scratch_dir = root / "scratch"
    if scratch_dir.is_dir():
        for item in scratch_dir.iterdir():
            if is_safe(item):
                targets.append((item, "scratch", get_path_size(item)))

    for dirpath, _, filenames in os.walk(root):
        if any(skip in dirpath for skip in (".git", "tablebases", "openings", "endgames", "data")):
            continue
        for f in filenames:
            if f.endswith((".tmp", ".bak", ".swp", ".orig", ".rej")) or f.endswith("~"):
                p = Path(dirpath) / f
                if is_safe(p):
                    targets.append((p, "temp_file", get_path_size(p)))

    # 3. Obsolete artifacts & colab leftovers
    colab_art = root / "colab/artifacts"
    if colab_art.is_dir() and is_safe(colab_art):
        targets.append((colab_art, "obsolete_colab_artifacts", get_path_size(colab_art)))

    colab_venv = root / "artifacts/colab/cli/venv"
    if colab_venv.is_dir() and is_safe(colab_venv):
        targets.append((colab_venv, "transient_colab_venv", get_path_size(colab_venv)))

    # Stray debug screenshots in artifacts root
    artifacts_root = root / "artifacts"
    if artifacts_root.is_dir():
        for f in artifacts_root.iterdir():
            if f.is_file() and f.suffix.lower() == ".png" and is_safe(f):
                targets.append((f, "artifact_screenshot", get_path_size(f)))
            if f.is_file() and f.name == "test_v331_exp.bin" and is_safe(f):
                targets.append((f, "transient_test_weights", get_path_size(f)))

        # Obsolete match logs for deleted engine lines (v600, etc.)
        for d in artifacts_root.iterdir():
            if d.is_dir() and d.name.startswith("matches_v600") and is_safe(d):
                targets.append((d, "obsolete_matches", get_path_size(d)))

    # 4. Deprecated checkpoint lineages
    checkpoints_dir = root / "checkpoints"
    if checkpoints_dir.is_dir():
        for item in checkpoints_dir.iterdir():
            if item.is_dir() and (item.name in ("v600", "old") or item.name.startswith("v40")) and is_safe(item):
                targets.append((item, "deprecated_checkpoints", get_path_size(item)))
            elif item.is_file() and item.name.startswith("v40") and is_safe(item):
                targets.append((item, "deprecated_checkpoints", get_path_size(item)))

    # 5. Intermediate checkpoints in active profiles (keep latest.pt and the last completed epoch)
    if clean_intermediate_epochs and checkpoints_dir.is_dir():
        for profile in ("v331", "v331_exp1", "v331_exp2", "v331_exp3", "v332", "v333", "v334", "v507", "v507_exp1", "v507_exp2", "v508", "v509", "v510", "v601", "v602", "v603", "v604"):
            p_dir = checkpoints_dir / profile
            if p_dir.is_dir():
                epoch_files = sorted([f for f in p_dir.iterdir() if f.is_file() and f.name.endswith(".pt") and f.name != "latest.pt"])
                if len(epoch_files) > 1:
                    # Keep the last epoch; remove earlier intermediate ones
                    for f in epoch_files[:-1]:
                        # Preserve epoch035 if v331_exp3
                        if profile == "v331_exp3" and "epoch035" in f.name:
                            continue
                        if is_safe(f):
                            targets.append((f, "intermediate_epoch", get_path_size(f)))

    # 6. Duplicate Stockfish engine repository clone
    sf_fast = root / "engine/stockfish_fast"
    if sf_fast.is_dir() and is_safe(sf_fast):
        targets.append((sf_fast, "duplicate_stockfish_clone", get_path_size(sf_fast)))

    # 7. Redundant raw selfplay datasets that already have filtered versions
    if clean_redundant_raw_data:
        for raw_name in ("selfplay_v507", "selfplay_v331"):
            raw_dir = root / f"data/{raw_name}"
            filtered_dir = root / f"data/{raw_name}_filter"
            if raw_dir.is_dir() and filtered_dir.is_dir() and is_safe(raw_dir):
                targets.append((raw_dir, "redundant_raw_selfplay", get_path_size(raw_dir)))

    # De-duplicate targets
    seen = set()
    unique_targets = []
    for path, kind, size in targets:
        if path not in seen:
            seen.add(path)
            unique_targets.append((path, kind, size))
    return unique_targets


def execute_cleanup(targets: list[tuple[Path, str, int]], dry_run: bool = False) -> int:
    """Execute removal of collected targets."""
    total_bytes = 0
    action = "Would remove" if dry_run else "Removed"

    for path, kind, size in targets:
        if not path.exists():
            continue
        rel_path = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        size_mb = size / (1024 * 1024)
        print(f"[{action}] ({kind}) {rel_path} ({size_mb:.2f} MB)")
        total_bytes += size

        if not dry_run:
            try:
                if path.is_dir():
                    shutil.rmtree(path, onerror=handle_remove_readonly)
                else:
                    os.chmod(path, stat.S_IWRITE)
                    path.unlink()
            except Exception as exc:
                print(f"Warning: could not delete {rel_path}: {exc}", file=sys.stderr)

    total_mb = total_bytes / (1024 * 1024)
    print(f"\nTotal space {'identified' if dry_run else 'freed'}: {total_mb:.2f} MB ({total_mb / 1024:.2f} GB)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Perform inspection without deleting files")
    parser.add_argument("--show-config", action="store_true", help="Print configuration and exit")
    parser.add_argument("--all", action="store_true", help="Clean all categories including intermediate epochs and redundant raw data")
    parser.add_argument("--checkpoints", action="store_true", help="Clean intermediate epoch checkpoints in active profiles")
    parser.add_argument("--raw-data", action="store_true", help="Clean redundant raw selfplay datasets")

    args = parser.parse_args()

    if args.show_config:
        print(json.dumps(CLEANUP_CONFIG, indent=2))
        return 0

    clean_intermediate = args.all or args.checkpoints
    clean_raw = args.all or args.raw_data

    tracked = get_tracked_files(ROOT)
    targets = collect_targets(
        root=ROOT,
        tracked=tracked,
        clean_intermediate_epochs=clean_intermediate,
        clean_redundant_raw_data=clean_raw,
    )

    if not targets:
        print("Repository is already clean. No cleanup targets found.")
        return 0

    return execute_cleanup(targets, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
