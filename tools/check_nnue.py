#!/usr/bin/env python3
"""Validate the installed NNUE artifact for a supported profile."""
from __future__ import annotations
import argparse, hashlib, struct, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "utils"))
from engine_profiles import profile
FORMATS = {"NNU3": {"dims": (799,256,256,64,64), "size": 426_864}, "NNU4": {"dims": (2560,48,96,20,20), "size": 248_020}}

def inspect(path: Path, expected_format: str | None = None) -> dict[str, object]:
    data=path.read_bytes()
    if len(data)<44: raise ValueError(f"file is too small: {len(data)} bytes")
    magic=data[:4].decode("ascii",errors="replace")
    if magic not in FORMATS: raise ValueError(f"unsupported NNUE magic {magic!r}")
    if expected_format and magic!=expected_format: raise ValueError(f"profile expects {expected_format}, artifact is {magic}")
    epoch=struct.unpack_from("<I",data,4)[0]; dims=struct.unpack_from("<5I",data,8); scales=struct.unpack_from("<4f",data,28)
    spec=FORMATS[magic]
    if dims!=spec["dims"]: raise ValueError(f"{magic} dimension mismatch: {dims} != {spec['dims']}")
    if len(data)!=spec["size"]: raise ValueError(f"{magic} size mismatch: {len(data)} != {spec['size']}")
    return {"path":str(path),"format":magic,"bytes":len(data),"epoch":epoch,"dims":dims,"scales":scales,"sha256":hashlib.sha256(data).hexdigest()}

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("path",nargs="?",default=""); p.add_argument("--profile","--version",dest="profile_name",default="")
    a=p.parse_args(); selected=profile(a.profile_name or None); path=Path(a.path) if a.path else selected.weights
    try: result=inspect(path,selected.network_format)
    except (OSError,ValueError) as exc: print(f"FAIL: {exc}"); return 1
    for k,v in result.items(): print(f"{k}: {v}")
    return 0
if __name__=="__main__": raise SystemExit(main())
