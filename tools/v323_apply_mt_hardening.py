#!/usr/bin/env python3
"""Apply thread-safety hardening needed by the PK17 candidate.

Two inherited NNU3 races are fixed:
1. nnue_reset(NnueAccum*) is a per-thread API but also writes legacy global
   accumulator state. Lazy-SMP workers therefore race on _acc_ptr/_acc_dirty
   and _ext_dirty_legacy.
2. passed-pawn masks are initialized lazily from nnue_rebuild(), so the first
   simultaneous helper rebuilds can race on _pp_span_* and _extra_masks_init.

Legacy globals are now reset only by nnue_reset_global() (the WASM compatibility
entry point), and passed-pawn masks are initialized once during NNUE load,
before search threads exist.
"""
from pathlib import Path
import argparse


def one(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {n}")
    return text.replace(old, new, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    a = ap.parse_args()
    p = a.root / "nnue.c"
    t = p.read_text(encoding="utf-8")

    old = """int _acc_dirty = 1;\nint _acc_ptr   = 0;\n\n/* ── NNU3 binary loader ──────────────────────────────────────────── */\n"""
    new = """int _acc_dirty = 1;\nint _acc_ptr   = 0;\n\n/* Passed-pawn lookup masks are process-global/read-only after NNUE load.\n * Initialize them before Lazy-SMP threads are launched. */\nstatic void _init_extra_masks(void);\n\n/* ── NNU3 binary loader ──────────────────────────────────────────── */\n"""
    t = one(t, old, new, "forward-declare mask init")

    old = """    _nnue_ready = 1;\n    _acc_dirty  = 1;\n    _acc_ptr    = 0;\n    return 0;\n}\n"""
    new = """    /* Eager one-time initialization avoids a first-search race between\n     * Lazy-SMP workers in _init_extra_masks(). */\n    _init_extra_masks();\n    _nnue_ready = 1;\n    _acc_dirty  = 1;\n    _acc_ptr    = 0;\n    return 0;\n}\n"""
    t = one(t, old, new, "eager mask init")

    old = """    memset(na->cache_key, 0, sizeof(na->cache_key));\n    memset(na->cache_aux, 0, sizeof(na->cache_aux));\n    memset(na->pk17_changed, 0, sizeof(na->pk17_changed));\n    /* Legacy globals (for WASM/test push/pop API) */\n    _acc_ptr   = 0;\n    _acc_dirty = 1;\n    memset(_ext_dirty_legacy, 1, sizeof(_ext_dirty_legacy));\n}\n\n/* WASM backward-compatibility: JS worker calls nnue_reset() with no args.\n * This wrapper passes the global accumulator.  Exported as _nnue_reset\n * in the WASM build. */\nvoid nnue_reset_global(void) {\n    nnue_reset(&g_nnue_accum);\n}\n"""
    new = """    memset(na->cache_key, 0, sizeof(na->cache_key));\n    memset(na->cache_aux, 0, sizeof(na->cache_aux));\n    memset(na->pk17_changed, 0, sizeof(na->pk17_changed));\n}\n\n/* WASM backward-compatibility wrapper.  The native per-thread reset above\n * must not touch these legacy globals; only the single-threaded legacy entry\n * point owns them. */\nvoid nnue_reset_global(void) {\n    nnue_reset(&g_nnue_accum);\n    _acc_ptr   = 0;\n    _acc_dirty = 1;\n    memset(_ext_dirty_legacy, 1, sizeof(_ext_dirty_legacy));\n}\n"""
    t = one(t, old, new, "separate per-thread and legacy reset")

    p.write_text(t, encoding="utf-8")
    print(f"applied v3.23 NNUE multithread hardening to {a.root}")


if __name__ == "__main__":
    main()
