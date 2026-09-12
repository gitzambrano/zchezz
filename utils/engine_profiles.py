"""Canonical supported engine profiles and external-engine resolution."""
from __future__ import annotations
import os, shutil
from dataclasses import dataclass
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = "v326"
@dataclass(frozen=True)
class EngineProfile:
    name:str; network_format:str; engine_dir:Path; checkpoint_dir:Path; trainer:Path; exporter:Path; importer:Path
    @property
    def weights(self)->Path: return self.engine_dir/"nnue_weights.bin"
    @property
    def latest_checkpoint(self)->Path: return self.checkpoint_dir/"latest.pt"
PROFILES={
 "v325":EngineProfile("v325","NNU3",ROOT/"engine/c/zchezz_v325",ROOT/"checkpoints/v325",ROOT/"train/_train_nnu3_core.py",ROOT/"train/_export_nnu3_core.py",ROOT/"train/import_nnu3.py"),
 "v326":EngineProfile("v326","NNU3",ROOT/"engine/c/zchezz_v326",ROOT/"checkpoints/v326",ROOT/"train/_train_nnu3_core.py",ROOT/"train/_export_nnu3_core.py",ROOT/"train/import_nnu3.py"),
 "v500":EngineProfile("v500","NNU4",ROOT/"engine/c/zchezz_v500",ROOT/"checkpoints/v500",ROOT/"train/_train_nnu4_core.py",ROOT/"train/export_nnu4.py",ROOT/"train/import_nnu4.py"),
}
def normalize_profile(value:str|None=None)->str:
    token=(value or os.environ.get("ZCHEZZ_ENGINE") or DEFAULT_PROFILE).strip().lower()
    if token.isdigit(): token="v"+token
    if token.startswith("zchezz_"): token=token[len("zchezz_"):]
    if token not in PROFILES: raise ValueError(f"unsupported engine profile {token!r}; choose {', '.join(PROFILES)}")
    return token
def profile(value:str|None=None)->EngineProfile: return PROFILES[normalize_profile(value)]
def stockfish_executable()->Path|None:
    explicit=os.environ.get("ZCHEZZ_STOCKFISH","").strip()
    if explicit:
        p=Path(explicit).expanduser(); return p if p.is_file() else None
    local=ROOT/"engine/stockfish"
    if local.is_dir():
        for name in ("stockfish.exe","stockfish"):
            p=local/name
            if p.is_file(): return p
        candidates=sorted(p for p in local.rglob("stockfish*") if p.is_file())
        if candidates: return candidates[0]
    found=shutil.which("stockfish"); return Path(found) if found else None
