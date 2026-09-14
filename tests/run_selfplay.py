#!/usr/bin/env python3
"""Simple architecture-neutral self-play entrypoint.

A registered ``--profile`` remains the default path. Experimental engines can
instead use ``--exe`` plus an optional ``--engine-label`` so branches do not
need to edit the global profile registry just to generate on-policy data.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'utils'))
from engine_profiles import DEFAULT_PROFILE, profile


def _profile_exe(p):
    for name in ('zchezz.exe', 'zchezz'):
        x = p.engine_dir / name
        if x.is_file():
            return x
    return p.engine_dir / 'zchezz.exe'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', default=DEFAULT_PROFILE)
    ap.add_argument('--exe', default='')
    ap.add_argument('--engine-label', default='')
    ap.add_argument('--show-config', action='store_true')
    a, rest = ap.parse_known_args()

    if a.exe:
        exe = Path(a.exe)
        if not exe.is_absolute():
            exe = ROOT / exe
        exe = exe.resolve()
        if not exe.is_file():
            ap.error(f'engine executable not found: {exe}')
        label = a.engine_label or exe.parent.name.removeprefix('zchezz_')
        source = 'explicit'
    else:
        p = profile(a.profile)
        exe = _profile_exe(p)
        label = a.engine_label or p.name
        source = f'profile:{p.name}'

    if a.show_config:
        print(f'source={source}\nengine={exe}\nengine_label={label}\nmovetime_ms=200\nconcurrency=1')
        return 0

    return subprocess.run([
        sys.executable,
        str(ROOT / 'tests/_run_selfplay_core.py'),
        '--engine', str(exe),
        '--engine-label', label,
        '--movetime', '200',
        '--concurrency', '1',
        *rest,
    ], cwd=ROOT).returncode


if __name__ == '__main__':
    raise SystemExit(main())
