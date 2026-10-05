"""Unit tests for fast repository-quality tools."""
from __future__ import annotations
import importlib.util,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def _load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); assert spec and spec.loader; mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod
EPD=_load("zchezz_check_epd",ROOT/"tools/check_epd.py"); NNUE=_load("zchezz_check_nnue",ROOT/"tools/check_nnue.py")
def test_epd_accepts_valid_fen_prefix(): ok,reason=EPD.valid_fen_prefix("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - bm e4;"); assert ok,reason
def test_epd_rejects_bad_rank_width(): ok,_=EPD.valid_fen_prefix("7/8/8/8/8/8/8/8 w - -"); assert not ok
def test_epd_scan_detects_duplicate(tmp_path):
    p=tmp_path/"suite.epd"; line="8/8/8/8/8/8/4K3/4k3 w - -"; p.write_text(line+"\n"+line+"\n",encoding="utf-8"); count,failures=EPD.scan(p); assert count==2 and any("duplicate position" in x for x in failures)
def _write_nnu4(path):
    dims=(2560,48,96,20,20); header=b"NNU4"+struct.pack("<I",1)+struct.pack("<5I",*dims)+struct.pack("<4f",255.0,64.0,8.0,320.0/4096.0); path.write_bytes(header+bytes(248020-len(header)))
def test_nnue_inspector_accepts_compact_nnu4(tmp_path):
    p=tmp_path/"weights.bin"; _write_nnu4(p); info=NNUE.inspect(p); assert info["dims"]==(2560,48,96,20,20) and info["bytes"]==248020
def test_nnue_inspector_rejects_bad_magic(tmp_path):
    p=tmp_path/"weights.bin"; p.write_bytes(b"BAD!"+bytes(100))
    try: NNUE.inspect(p)
    except ValueError as exc: assert "magic" in str(exc)
    else: raise AssertionError("bad magic was accepted")
