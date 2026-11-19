#!/usr/bin/env python3
"""Canonical declarative experiment runner for Zchezz.

A spec in ``experiments/specs/<id>.json`` names two engines and a protocol.
The runner resolves both engines, plays the match through the canonical UCI
harness (``tests/_run_tournament_quick_core.py``) and writes one isolated run
directory per execution:

    artifacts/experiments/<id>/<UTC timestamp>/
        spec.json       resolved spec (after CLI overrides)
        summary.json    provenance + W/D/L + trinomial and pentanomial Elo
        *.pgn, *.log    raw harness output (PGN carries a PairId tag)
        build/<label>/  candidate sources and binary, when a spec builds one

``artifacts/experiments/<id>/latest.json`` points at the newest run.

Engine forms (``engine_a`` / ``engine_b``):

- ``{"profile": "v335"}``            installed profile binary
- ``{"path": "path/to/zchezz.exe"}`` explicit binary
- ``{"target": "stockfish"}``        Stockfish via utils/engine_profiles.py
- ``{"candidate": {"base_profile": "v335", "patch": "experiments/patches/x.diff"}}``
  copies the base profile's engine directory into the run directory, applies
  the patch (paths relative to that engine directory, ``git diff`` style with
  ``a/``/``b/`` prefixes), and builds it with ``engine/build/Makefile`` and the
  spec's ``build.arch_flags`` (default ``-march=native``). Both a candidate and
  its opponent should be built with the same flags for performance claims.

Every engine may carry ``label`` and ``options`` (UCI ``setoption`` values).

A suite spec ``{"id": ..., "suite": ["spec_a", "spec_b"]}`` runs each member.

Protocol defaults follow the benchmark contract: movetime 200 ms, Threads=1,
one concurrent game, paired openings with colors reversed. ``nodes`` selects
fixed-node search, which is not promotion evidence. ``seed`` (0 = fresh) fixes
opening order and schedule; the seed actually used is recorded.

Bare execution runs ``experiments/specs/default.json``. ``--show-config`` and
``--dry-run`` resolve everything without building or playing.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SPECS_DIR = ROOT / "experiments" / "specs"
RESULTS_ROOT = ROOT / "artifacts" / "experiments"
sys.path.insert(0, str(ROOT / "utils"))
sys.path.insert(0, str(ROOT / "tests"))

from engine_profiles import profile, stockfish_executable  # noqa: E402
from elo_calc import elo_difference, elo_difference_pentanomial  # noqa: E402

PROTOCOL_DEFAULTS = {
    "movetime_ms": 200,
    "nodes": 0,
    "threads": 1,
    "games": 10,
    "concurrency": 1,
    "color_swap": True,
    "max_plies": 400,
    "seed": 0,
    "openings": None,
    "opening_files": None,
}
DEFAULT_ARCH_FLAGS = "-march=native"


# ── spec loading ─────────────────────────────────────────────────────────────

def load_spec(identifier: str) -> dict[str, Any]:
    for candidate in (Path(identifier), SPECS_DIR / f"{identifier}.json", SPECS_DIR / identifier):
        if candidate.is_file():
            data = json.loads(candidate.read_text(encoding="utf-8"))
            data.setdefault("id", candidate.stem)
            return data
    raise FileNotFoundError(f"experiment spec not found: {identifier}")


def validate_spec(spec: dict[str, Any]) -> None:
    """Raise ValueError when `spec` is not a valid experiment: a suite must be a non-empty list of spec
    ids; a run needs the required keys and only known protocol keys.
    """
    if "suite" in spec:
        if not isinstance(spec["suite"], list) or not spec["suite"]:
            raise ValueError(f"{spec.get('id')}: 'suite' must be a non-empty list of spec ids")
        return
    for key in ("id", "engine_a", "engine_b"):
        if key not in spec:
            raise ValueError(f"{spec.get('id', '?')}: missing '{key}'")
    unknown = set(spec.get("protocol", {})) - set(PROTOCOL_DEFAULTS)
    if unknown:
        raise ValueError(f"{spec['id']}: unknown protocol keys {sorted(unknown)}")
    for side in ("engine_a", "engine_b"):
        cfg = spec[side]
        forms = [k for k in ("profile", "path", "target", "candidate") if k in cfg]
        if len(forms) != 1:
            raise ValueError(f"{spec['id']}.{side}: exactly one of profile/path/target/candidate required")
    if spec["engine_a"].get("label", "a") == spec["engine_b"].get("label", "b"):
        raise ValueError(f"{spec['id']}: engine labels must differ")


def protocol_of(spec: dict[str, Any]) -> dict[str, Any]:
    proto = dict(PROTOCOL_DEFAULTS)
    proto.update(spec.get("protocol", {}))
    return proto


# ── engine resolution ────────────────────────────────────────────────────────

def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
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


def _profile_binary(name: str) -> Path:
    p = profile(name)
    for exe in ("zchezz.exe", "zchezz"):
        if (p.engine_dir / exe).is_file():
            return p.engine_dir / exe
    return p.engine_dir / "zchezz.exe"


def describe_engine(cfg: dict[str, Any], default_label: str) -> dict[str, Any]:
    """Resolve an engine entry without building or running anything."""
    label = cfg.get("label") or cfg.get("profile") or default_label
    info: dict[str, Any] = {"label": label, "options": dict(cfg.get("options", {}))}
    if "profile" in cfg:
        p = profile(cfg["profile"])
        info.update(kind="profile", profile=p.name, network_format=p.network_format,
                    binary=_profile_binary(p.name))
    elif "path" in cfg:
        info.update(kind="path", binary=(ROOT / cfg["path"]) if not Path(cfg["path"]).is_absolute()
                    else Path(cfg["path"]))
    elif cfg.get("target") == "stockfish":
        info.update(kind="stockfish", binary=stockfish_executable())
    elif "candidate" in cfg:
        cand = cfg["candidate"]
        base = profile(cand["base_profile"])
        patch = ROOT / cand["patch"] if cand.get("patch") else None
        info.update(kind="candidate", profile=base.name, network_format=base.network_format,
                    base_dir=base.engine_dir, patch=patch, binary=None)
    else:
        raise ValueError(f"unsupported engine entry: {cfg}")
    return info


def _make_executable() -> str | None:
    return shutil.which("make") or shutil.which("mingw32-make")


def _compiler_version() -> str:
    cc = os.environ.get("CC", "gcc")
    try:
        out = subprocess.run([cc, "--version"], capture_output=True, text=True, timeout=10)
        return out.stdout.splitlines()[0] if out.returncode == 0 and out.stdout else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def build_candidate(info: dict[str, Any], run_dir: Path, arch_flags: str) -> None:
    """Copy base sources, apply the patch, and compile into run_dir/build/<label>."""
    make = _make_executable()
    if not make:
        raise RuntimeError("no make/mingw32-make on PATH; cannot build candidate")
    dest = run_dir / "build" / info["label"]
    shutil.copytree(info["base_dir"], dest, ignore=shutil.ignore_patterns("*.exe", "*.o", "*.wasm", "*.js"))
    if info["patch"] is not None:
        if not info["patch"].is_file():
            raise FileNotFoundError(f"candidate patch not found: {info['patch']}")
        res = subprocess.run(
            ["git", "apply", "--unsafe-paths", f"--directory={_rel(dest)}", "-p1", str(info["patch"])],
            cwd=str(ROOT), capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"patch {info['patch'].name} does not apply to {info['profile']}:\n{res.stderr}")
    edir = os.path.relpath(dest, ROOT / "engine" / "build").replace(os.sep, "/")
    res = subprocess.run([make, "-C", str(ROOT / "engine" / "build"), "native",
                          f"EDIR={edir}", f"ARCH_FLAGS={arch_flags}", f"ENGINE={info['label']}"],
                         capture_output=True, text=True)
    (dest / "build.log").write_text(res.stdout + res.stderr, encoding="utf-8")
    binary = dest / "zchezz.exe"
    if res.returncode != 0 or not binary.is_file():
        raise RuntimeError(f"candidate build failed; see {dest / 'build.log'}")
    info["binary"] = binary
    info["source_dir"] = dest


def engine_record(info: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in info.items() if k not in ("binary", "base_dir", "patch", "source_dir")}
    binary = info.get("binary")
    out["binary"] = _rel(binary) if binary else None
    out["binary_sha256"] = _sha256(binary) if binary else None
    if info.get("kind") == "candidate":
        out["base_dir"] = _rel(info["base_dir"])
        out["patch"] = _rel(info["patch"]) if info["patch"] else None
        out["patch_sha256"] = _sha256(info["patch"]) if info["patch"] else None
    return out


# ── result parsing ───────────────────────────────────────────────────────────

_TAG = re.compile(r'^\[(\w+) "([^"]*)"\]', re.M)


def parse_pgn(pgn: Path, label_a: str) -> dict[str, Any]:
    """Return W/D/L for label_a plus per-pair scores keyed by the PairId tag."""
    wins = draws = losses = 0
    pairs: dict[str, list[float]] = {}
    if not pgn.is_file():
        return {"wins": 0, "draws": 0, "losses": 0, "pairs": []}
    for block in re.split(r"\n(?=\[Event )", pgn.read_text(encoding="utf-8", errors="replace")):
        tags = dict(_TAG.findall(block))
        white, black, res = tags.get("White"), tags.get("Black"), tags.get("Result")
        if label_a not in (white, black) or res not in ("1-0", "0-1", "1/2-1/2"):
            continue
        score = 0.5 if res == "1/2-1/2" else (1.0 if (res == "1-0") == (white == label_a) else 0.0)
        wins += score == 1.0
        draws += score == 0.5
        losses += score == 0.0
        if "PairId" in tags:
            pairs.setdefault(tags["PairId"], []).append(score)
    return {"wins": wins, "draws": draws, "losses": losses,
            "pairs": [tuple(v) for v in pairs.values() if len(v) == 2]}


def _num(x: float, nd: int):
    return round(x, nd) if x not in (float("inf"), float("-inf")) else None


def _seed_from_log(log: Path) -> int | None:
    if log.is_file():
        m = re.search(r"Seed\s*:\s*(\d+)", log.read_text(encoding="utf-8", errors="replace"))
        if m:
            return int(m.group(1))
    return None


# ── execution ────────────────────────────────────────────────────────────────

def harness_command(spec, proto, a, b, run_dir: Path) -> list[str]:
    """Return the command line of the tournament harness for engines `a` and `b` under the protocol
    `proto`, writing its output to `run_dir`.
    """
    cmd = [sys.executable, str(ROOT / "tests" / "_run_tournament_quick_core.py"),
           "--engine-a", str(a["binary"]), "--label-a", a["label"],
           "--engine-b", str(b["binary"]), "--label-b", b["label"],
           "--movetime", str(proto["movetime_ms"]),
           "--threads", str(proto["threads"]),
           "--games", str(proto["games"]),
           "--concurrency", str(proto["concurrency"]),
           "--max-plies", str(proto["max_plies"]),
           "--seed", str(proto["seed"]),
           "--results-dir", str(run_dir),
           "--pgn", "--self-play",
           "--color-swap" if proto["color_swap"] else "--no-color-swap"]
    if proto["nodes"]:
        cmd += ["--nodes", str(proto["nodes"])]
    if proto["openings"]:
        cmd += ["--openings", proto["openings"]]
    if proto["opening_files"]:
        cmd += ["--opening-file", *proto["opening_files"]]
    for flag, eng in (("--options-a", a), ("--options-b", b)):
        if eng["options"]:
            cmd += [flag, ",".join(f"{k}={v}" for k, v in eng["options"].items())]
    return cmd


def run_one(spec: dict[str, Any], *, dry_run: bool) -> int:
    """Run one experiment spec and return 0 on success, 1 on a failure.

    It writes into `RESULTS_ROOT/<id>/<UTC stamp>/`. With `dry_run` it validates the spec and prints
    the plan only.
    """
    validate_spec(spec)
    proto = protocol_of(spec)
    arch_flags = spec.get("build", {}).get("arch_flags", DEFAULT_ARCH_FLAGS)
    a = describe_engine(spec["engine_a"], "engine_a")
    b = describe_engine(spec["engine_b"], "engine_b")

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RESULTS_ROOT / spec["id"] / stamp
    print(f"\n{'=' * 72}\n EXPERIMENT {spec['id']}: {spec.get('description', '')}")
    for side in (a, b):
        print(f"  {side['label']:<20} {side['kind']:<10} {side.get('binary') or side.get('base_dir')}")
    print(f"  protocol: {proto}\n  run dir : {run_dir}\n{'=' * 72}")
    if dry_run:
        print("Dry run: nothing built or played.")
        return 0

    for side in (a, b):
        if side["kind"] != "candidate" and (not side["binary"] or not Path(side["binary"]).is_file()):
            print(f"Error: {side['label']}: binary not found ({side['binary']}). Build it first.")
            return 1

    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "spec.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    try:
        for side in (a, b):
            if side["kind"] == "candidate":
                build_candidate(side, run_dir, arch_flags)
    except (RuntimeError, FileNotFoundError) as e:
        print(f"Error: {e}")
        _write_summary(run_dir, spec, proto, a, b, arch_flags, status="build_failed", rc=None)
        return 1

    rc = subprocess.run(harness_command(spec, proto, a, b, run_dir), cwd=str(ROOT)).returncode
    status = "completed" if rc == 0 else "harness_failed"
    summary = _write_summary(run_dir, spec, proto, a, b, arch_flags, status=status, rc=rc)
    r = summary["results"]
    print(f"\n{spec['id']}: {r['wins']}W/{r['draws']}D/{r['losses']}L  "
          f"Elo {r['elo']} ± {r['elo_ci95']} (pentanomial {r['elo_pentanomial']} ± {r['elo_pentanomial_ci95']})  "
          f"status={status}\nSummary: {run_dir / 'summary.json'}")
    return 0 if rc == 0 else 1


def _write_summary(run_dir, spec, proto, a, b, arch_flags, *, status, rc) -> dict[str, Any]:
    """Write `summary.json` into `run_dir` (spec, protocol, engines, build flags, win/draw/loss counts,
    `status` and `rc`) and `latest.json` next to it; return the summary dict.
    """
    pgns = sorted(run_dir.glob("*.pgn"))
    logs = sorted(run_dir.glob("*.log"))
    parsed = parse_pgn(pgns[-1], a["label"]) if pgns else {"wins": 0, "draws": 0, "losses": 0, "pairs": []}
    w, d, l = parsed["wins"], parsed["draws"], parsed["losses"]
    n = w + d + l
    elo, ci, _ = elo_difference(w, d, l) if n else (0.0, float("inf"), 0.0)
    pelo, pci, _ = elo_difference_pentanomial(parsed["pairs"])
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True,
                                text=True, timeout=5).stdout.strip() or "unknown"
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=str(ROOT),
                                    capture_output=True, text=True, timeout=10).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        commit, dirty = "unknown", None
    summary = {
        "schema_version": 2,
        "experiment_id": spec["id"],
        "description": spec.get("description", ""),
        "status": status,
        "harness_returncode": rc,
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "git_commit": commit,
        "git_dirty": dirty,
        "host": {"platform": platform.platform(), "machine": platform.machine(),
                 "compiler": _compiler_version(), "arch_flags": arch_flags},
        "protocol": dict(proto, seed_used=_seed_from_log(logs[-1]) if logs else None,
                         standard_movetime_protocol=not proto["nodes"]),
        "engine_a": engine_record(a),
        "engine_b": engine_record(b),
        "results": {
            "games_played": n, "wins": w, "draws": d, "losses": l,
            "score_pct": round(100.0 * (w + 0.5 * d) / n, 2) if n else None,
            "elo": _num(elo, 1), "elo_ci95": _num(ci, 1),
            "pairs": len(parsed["pairs"]),
            "elo_pentanomial": _num(pelo, 1), "elo_pentanomial_ci95": _num(pci, 1),
        },
        "files": [p.name for p in pgns + logs],
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (run_dir.parent / "latest.json").write_text(
        json.dumps({"run": run_dir.name, "status": status}, indent=2) + "\n", encoding="utf-8")
    return summary


def show_config(spec: dict[str, Any]) -> None:
    """Print the resolved experiment specification without running anything."""
    validate_spec(spec)
    print("Resolved Experiment Specification:")
    print(f"  ID         : {spec['id']}")
    print(f"  Description: {spec.get('description', '')}")
    if "suite" in spec:
        print(f"  Suite      : {', '.join(spec['suite'])}")
        return
    for key in ("engine_a", "engine_b"):
        info = describe_engine(spec[key], key)
        where = info.get("binary") or info.get("base_dir")
        state = "present" if (info["kind"] == "candidate" or (where and Path(where).is_file())) else "MISSING"
        extra = f" patch={info['patch']}" if info["kind"] == "candidate" else ""
        print(f"  {key:<11}: {info['label']} [{info['kind']}] {where} ({state}){extra} {info['options'] or ''}")
    print(f"  Protocol   : {protocol_of(spec)}")
    print(f"  Results    : {RESULTS_ROOT / spec['id']}/<UTC timestamp>/")


def expand(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the list of specs to run: the members of a suite, or the spec itself."""
    if "suite" in spec:
        validate_spec(spec)
        out = []
        for member in spec["suite"]:
            child = load_spec(member)
            if "protocol" in spec:
                child["protocol"] = dict(child.get("protocol", {}), **spec["protocol"])
            out.extend(expand(child))
        return out
    return [spec]


def main() -> int:
    """Run the selected specs (`--spec`, default `default`). `--list` and `--show-config` do not run
    anything. Returns 1 when any run fails, otherwise 0.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", action="append", default=None,
                    help="spec id or JSON path (repeatable; default: default)")
    ap.add_argument("--list", action="store_true", help="list available specs and exit")
    ap.add_argument("--show-config", action="store_true", help="print the resolved spec and exit")
    ap.add_argument("--dry-run", action="store_true", help="resolve and print without building or playing")
    for key, typ in (("movetime", int), ("nodes", int), ("games", int), ("concurrency", int),
                     ("threads", int), ("seed", int), ("max-plies", int)):
        ap.add_argument(f"--{key}", type=typ, default=None, help=f"override protocol {key}")
    args = ap.parse_args()

    if args.list:
        for p in sorted(SPECS_DIR.glob("*.json")):
            s = json.loads(p.read_text(encoding="utf-8"))
            print(f"  {p.stem:<32} {s.get('description', '')}")
        return 0

    overrides = {k: v for k, v in {
        "movetime_ms": args.movetime, "nodes": args.nodes, "games": args.games,
        "concurrency": args.concurrency, "threads": args.threads, "seed": args.seed,
        "max_plies": args.max_plies}.items() if v is not None}

    specs = []
    for ident in args.spec or ["default"]:
        for s in expand(load_spec(ident)):
            s["protocol"] = dict(s.get("protocol", {}), **overrides)
            specs.append(s)

    if args.show_config:
        for s in specs:
            show_config(s)
        return 0
    failures = sum(run_one(s, dry_run=args.dry_run) for s in specs)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
