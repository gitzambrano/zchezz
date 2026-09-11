# WebAssembly

The shared WebAssembly build uses the selected engine profile and the common browser template.

## Build

```bash
make -C engine/build ENGINE=v325 wasm
make -C engine/build ENGINE=v325 bundle
```

The same targets can be used with `ENGINE=v500` when the v500 browser artifact is the intended output.

Emscripten is required. Web builds define `NO_TABLEBASES` and `NO_BOOK` for native file-I/O integrations.

## NNUE payload

The bundle must embed the NNUE matching the selected engine:

- v325 → NNU3, 426,864-byte installed file;
- v500 → compact NNU4, 248,020-byte installed file.

The HTML template is architecture-neutral. Do not hard-code network dimensions in generic bundling code when they can be derived from the selected profile/artifact.

## Runtime interface

The browser worker initializes the compiled engine, loads the embedded network and communicates through the engine's exported WASM/UCI-facing helpers. The single-threaded browser compatibility wrappers are distinct from the native Lazy-SMP per-thread state.

## Validation

Use the static wiring/blob-worker tests plus browser E2E when Playwright is available. A successful native engine build does not prove the WebAssembly bundle works.
