# WebAssembly

The shared WebAssembly build uses the selected engine profile and the common browser template.

## Build

```bash
make -C engine/build ENGINE=v335 wasm
make -C engine/build ENGINE=v335 bundle
```

The same targets can be used with `ENGINE=v510` or other profiles when a different browser artifact is the intended output.

Emscripten is required. Web builds define `NO_TABLEBASES` and `NO_BOOK` for native file-I/O integrations.

## Pages synchronization and browser release gate

The canonical Pages source is `index.html` in the repository root. It must
match `engine/c/zchezz_v335/zchezz_bundle.html` byte-for-byte.
A successful CI compile **does not** automatically mean that GitHub Pages
serves that version; the `main` branch must receive the synchronized page
commit, and Pages must use `main` / `/(root)` as its source.

```bash
make -C engine/build ENGINE=v335 bundle
python tests/test_browser_html.py --html engine/c/zchezz_v335/zchezz_bundle.html
python tests/test_book.py --html engine/c/zchezz_v335/zchezz_bundle.html
python tests/test_browser.py --version v335 --headless   # requires Chromium/Playwright
python tools/publish_web.py --mode sync                   # only after tests pass
python tools/publish_web.py --mode check                  # ensures index == v335 bundle
```

The dedicated `.github/workflows/publish-pages.yml` automates this sequence
after relevant pushes to `main`, commits only the verified bundle and
`index.html`, then explicitly requests a Pages rebuild using the Pages API:
`GITHUB_TOKEN` commits alone do not trigger Pages builds. It skips re-running on
generated bundle-only changes and never
promotes other engine profiles. The regular CI remains read-only.

The browser target always uses Emscripten `-msimd128`; native
`-march=native` / `-mavx2` flags do not apply to WebAssembly.

## NNUE payload

The bundle must embed the NNUE matching the selected engine:

- v335 → NNU3, 426,864-byte installed file;
- v510 → compact NNU4, 248,020-byte installed file.

The HTML template is architecture-neutral. Do not hard-code network dimensions in generic bundling code when they can be derived from the selected profile and artifact.

## Runtime interface

The browser worker initializes the compiled engine, loads the embedded network, and communicates through the engine's exported WASM/UCI-facing helpers. The single-threaded browser compatibility wrappers are distinct from the native Lazy-SMP per-thread state.

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

Use `tests/test_browser_html.py` and `tests/test_book.py`, plus browser E2E (`tests/test_browser.py`) when Playwright is available. A successful native engine build does not prove the WebAssembly bundle works.
