# Generated Artifacts

Generated files are evidence or build output, not source-of-truth configuration.

## Engine builds

Native executables, WASM glue/binaries and generated bundle output are produced by `engine/build/`. The selected profile owns its generated engine artifact.

## Test evidence

Longer test runners place summaries and logs under `artifacts/`. Generated evidence may be deleted and reproduced; it must not overwrite engine source or installed NNUE weights.

## Training

Training checkpoints live under `checkpoints/<profile>/`. `latest.pt` is the canonical resumable checkpoint for a supported profile. Large datasets and transient optimizer outputs are local or generated resources unless explicitly promoted to tracked artifacts.

## Installed NNUE weights

`engine/c/zchezz_v335/nnue_weights.bin`, `engine/c/zchezz_v510/nnue_weights.bin`, and `engine/c/zchezz_v605/nnue_weights.bin` are runtime inputs tracked with their engine profiles. They are not disposable build output. Comparison baselines (`zchezz_v334`, `zchezz_v328`, `zchezz_v507`, `zchezz_v604`, etc.) also track their installed networks.

## Browser bundle

A bundled HTML file embeds the WASM engine and NNUE payload. It is generated from the selected engine plus the shared web template; do not infer its evaluator architecture from the template alone.
