# WebAssembly Blob Worker

The standalone browser bundle creates its worker from embedded JavaScript/WASM payloads so the generated HTML can run from `file://` without a server.

The worker/bootstrap contract is shared build infrastructure; it must not assume NNU3 or NNU4 solely from the HTML template. The selected engine profile supplies the matching WASM module and NNUE bytes during bundling.

When changing worker bootstrap code, validate that:

- the worker can be created from the embedded blob;
- engine initialization reaches UCI readiness;
- the embedded NNUE payload is loaded for the selected profile;
- analysis continues beyond opening-book moves;
- no external network fetch is required by the standalone bundle.

See `tests/test_wasm_blob_worker.py`, `tests/test_wasm_wiring.py` and `docs/wasm.md`.
