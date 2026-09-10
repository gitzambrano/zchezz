"""Protect the shared WebAssembly build and JS/C ABI contracts."""
from __future__ import annotations
import importlib.util,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"utils"))
from repo_paths import build_root,wasm_source
def _runner():
    spec=importlib.util.spec_from_file_location("zchezz_web_runner",ROOT/"tests"/"run_tests.py"); assert spec and spec.loader; m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m); return m
def test_shared_wasm_template_exists(): assert (build_root()/"zchezz_wasm.html").is_file()
def test_wasm_source_is_shared():
    expected=build_root()/"zchezz_wasm.html"; assert wasm_source("v325")==expected; assert wasm_source("v500")==expected
def test_makefile_exports_frontend_reset_symbol():
    text=(ROOT/"engine/build/Makefile").read_text(encoding="utf-8"); assert '"_nnue_reset_global"' in text and "WASM_TEMPLATE = zchezz_wasm.html" in text and "bundle_shared.py" in text
def test_browser_e2e_targets_generated_bundle():
    m=_runner(); command=next(s.command for s in m.profiles("v500","v325")["web"] if s.name=="browser e2e"); assert "--html" in command and "zchezz_bundle.html" in command
def test_browser_searchparams_abi():
    for rel in ("engine/build/bundle.py","engine/build/zchezz_wasm.html"):
        text=(ROOT/rel).read_text(encoding="utf-8"); assert "const SP_SZ=44;" in text; assert "Mod._malloc(SP_SZ)" in text; assert "pp+SP_SZ" in text; assert "pp,SP_SZ" in text
def test_bundled_worker_preserves_start_depth():
    text=(ROOT/"engine/build/bundle.py").read_text(encoding="utf-8"); assert "msg.startDepth||0" in text and "pdv.setInt32(4,startDepth||0,true);" in text
