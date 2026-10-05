# WebAssembly

The shared WebAssembly build uses the selected engine profile and the common browser template.

## Build

```bash
make -C engine/build ENGINE=v331 wasm
make -C engine/build ENGINE=v331 bundle
```

The same targets can be used with `ENGINE=v507` when the v507 browser artifact is the intended output.

Emscripten is required. Web builds define `NO_TABLEBASES` and `NO_BOOK` for native file-I/O integrations.

## NNUE payload

The bundle must embed the NNUE matching the selected engine:

- v331 → NNU3, 426,864-byte installed file;
- v507 → compact NNU4, 248,020-byte installed file.

The HTML template is architecture-neutral. Do not hard-code network dimensions in generic bundling code when they can be derived from the selected profile/artifact.

## Runtime interface

The browser worker initializes the compiled engine, loads the embedded network and communicates through the engine's exported WASM/UCI-facing helpers. The single-threaded browser compatibility wrappers are distinct from the native Lazy-SMP per-thread state.

## Blob worker

The standalone browser bundle creates its Web Worker from embedded JavaScript and WASM payloads so the generated HTML can run directly from `file://` without an external HTTP server.

The worker and bootstrap contracts are shared build infrastructure; they do not assume NNU3 or NNU4 solely from the HTML template. The selected engine profile supplies the matching WASM module and NNUE bytes during bundling.

When modifying worker bootstrap code, verify that:

- the worker initializes from the embedded blob;
- engine initialization completes UCI readiness (`uciok`, `readyok`);
- the embedded NNUE payload is loaded for the selected profile;
- analysis continues beyond opening-book moves;
- no external network request is initiated by the standalone bundle.

## Validation

Use `tests/test_wasm_blob_worker.py` and `tests/test_wasm_wiring.py`, plus browser E2E (`tests/test_browser.py`) when Playwright is available. A successful native engine build does not prove the WebAssembly bundle works.
