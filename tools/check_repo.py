#!/usr/bin/env python3
"""Fast local repository contract check; no builds, games, or network access."""
from __future__ import annotations
import ast, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"utils"))
from engine_profiles import DEFAULT_PROFILE, PROFILES
from repo_policy import new_absolute_root_files

ERRORS=[]
def error(x): ERRORS.append(x)

def main() -> int:
    required=("AGENTS.md","CLAUDE.md","engine/ACTIVE_ENGINE","engine/build/Makefile","utils/engine_profiles.py","utils/cliconf.py","tests/run_tests.py")
    for name in required:
        if not (ROOT/name).exists(): error(f"missing required path: {name}")
    if (ROOT/"engine/ACTIVE_ENGINE").read_text(encoding="utf-8").strip()!=DEFAULT_PROFILE: error(f"ACTIVE_ENGINE must be {DEFAULT_PROFILE}")
    if set(PROFILES)!={"v325","v326","v500"}: error(f"supported profiles drifted: {sorted(PROFILES)}")
    for p in PROFILES.values():
        if not p.engine_dir.is_dir(): error(f"missing engine profile: {p.engine_dir.relative_to(ROOT)}")
        if not p.weights.is_file(): error(f"missing NNUE weights: {p.weights.relative_to(ROOT)}")
    stale=sorted(p.name for p in (ROOT/"engine/c").glob("zchezz_v4*"))
    if stale: error(f"v4 engine trees are not supported: {stale}")
    workflows=sorted([*ROOT.joinpath('.github/workflows').glob('*.yml'),*ROOT.joinpath('.github/workflows').glob('*.yaml')])
    if [p.name for p in workflows] != ["ci.yml"]: error(f"Actions must contain only ci.yml: {[p.name for p in workflows]}")
    elif workflows:
        wf=workflows[0].read_text(encoding='utf-8').lower()
        for bad in ('contents: write','git push','git commit','playwright','emsdk','upload-artifact'):
            if bad in wf: error(f"ci.yml contains forbidden heavy/mutating behavior: {bad}")
    for top in ('tests','tools','utils','train'):
        if not (ROOT/top).exists(): continue
        for path in (ROOT/top).rglob('*.py'):
            try: ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
            except Exception as exc: error(f"Python syntax error in {path.relative_to(ROOT)}: {exc}")
    offenders=sorted(new_absolute_root_files(ROOT))
    if offenders: error(f"new hard-coded absolute repository roots: {offenders}")
    make=(ROOT/'engine/build/Makefile').read_text(encoding='utf-8')
    if not re.search(r'^ENGINE\s*\?=\s*v326\b',make,re.M): error('Makefile default must be v326')
    if not re.search(r'^TOOLS_ENGINE\s*\?=\s*v500\b',make,re.M): error('native tool host must be v500')
    for item in ERRORS: print('ERROR:',item)
    if ERRORS:
        print(f'FAILED: {len(ERRORS)} issue(s)'); return 1
    print('PASS: repository pre-flight checks'); return 0
if __name__=='__main__': raise SystemExit(main())
