#!/usr/bin/env python3
"""Build selected canonical Zchezz profiles through the shared Makefile.

Bare invocation builds v335; active builds v335/v510/v605; supported builds
every profile registered in utils/engine_profiles.py. Generated files remain
ignored local outputs; this script never edits source or Git refs.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "engine" / "build"
sys.path.insert(0, str(ROOT / "utils"))
from engine_profiles import DEFAULT_PROFILE, PROFILES  # noqa: E402


def selected_profiles(scope: str) -> list[str]:
    if scope == "default":
        return [DEFAULT_PROFILE]
    if scope == "supported":
        return sorted(PROFILES, key=lambda p: int(p[1:]))
    chosen = [DEFAULT_PROFILE]
    for family in ("NNU4", "NNU5"):
        members = [p.name for p in PROFILES.values() if p.network_format == family]
        if not members:
            raise RuntimeError(f"no registered engine for {family}")
        chosen.append(max(members, key=lambda name: int(name[1:])))
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("default", "active", "supported"), default="default")
    parser.add_argument("--target", choices=("native", "bundle"), default="native")
    parser.add_argument("--arch-flags", default=None)
    parser.add_argument("--static-flag", default=None)
    parser.add_argument("--output-suffix", choices=("", ".portable"), default="")
    parser.add_argument("--show-config", action="store_true")
    args = parser.parse_args()
    profiles = selected_profiles(args.scope)
    if args.show_config:
        print(f"scope={args.scope} target={args.target} profiles={','.join(profiles)}")
        return 0

    make = shutil.which("make") or shutil.which("mingw32-make")
    if not make:
        print("ERROR: GNU make not found in PATH", file=sys.stderr)
        return 2
    if args.target == "bundle" and not shutil.which("emcc"):
        print("ERROR: Emscripten emcc not found in PATH", file=sys.stderr)
        return 2

    for name in profiles:
        p = PROFILES[name]
        if not p.weights.is_file():
            print(f"ERROR: missing {name} weights: {p.weights}", file=sys.stderr)
            return 2
        cmd = [make, "-C", str(BUILD), f"ENGINE={name}"]
        if args.arch_flags is not None:
            cmd.append(f"ARCH_FLAGS={args.arch_flags}")
        if args.static_flag is not None:
            cmd.append(f"STATIC_FLAG={args.static_flag}")
        if args.output_suffix and args.target == "native":
            cmd.append(f"OUTPUT_SUFFIX={args.output_suffix}")
        cmd.append(args.target)
        print(f"BUILD profile={name} format={p.network_format} target={args.target}", flush=True)
        result = subprocess.run(cmd, check=False)
        if result.returncode:
            print(f"FAIL profile={name} target={args.target}: exit {result.returncode}", file=sys.stderr)
            return result.returncode
        output = p.engine_dir / (f"zchezz{args.output_suffix}.exe" if args.target == "native" else "zchezz_bundle.html")
        if not output.is_file() or output.stat().st_size == 0:
            print(f"ERROR: missing or empty build output {output}", file=sys.stderr)
            return 1
        print(f"PASS profile={name} output={output.relative_to(ROOT)} bytes={output.stat().st_size}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
