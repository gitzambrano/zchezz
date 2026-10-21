# Architecture

Zchezz has a released NNU3 profile, frozen NNU3 comparison baselines, and supported NNU4/NNU5 experimental profiles.

- `v334` is the default/released working line and uses NNU3 with Quiet SEE d5 pruning, Continuous Smooth History LMR and TT Prefetch cache fix. `v333`, `v332` and `v331` are retained as available baselines.
- `v328` is retained as the frozen pre-v3.29 NNU3 regression/comparison baseline.
- `v510` is a supported secondary line and uses compact NNU4 HalfKP-4-Bucket with Quiet SEE d5, Continuous Smooth History LMR and TT Prefetch cache fix. `v509`, `v508` and `v507` are available baselines.
- `v604` is a supported secondary line representing the NNU5 family (256 neurons, HalfKAv2 32-bucket) with Quiet SEE d5, Continuous Smooth History LMR and TT Prefetch cache fix. `v603`, `v602` and `v601` are available baselines.
- `engine/ACTIVE_ENGINE` is `v334`.

## Layering

### Engine core

Each engine directory contains its own `main.c`, board, search, NNUE, Syzygy and Polyglot integration. Engine state is versioned with the source so search/evaluator contracts cannot silently drift across families.

### Shared orchestration

`utils/engine_profiles.py` is the canonical profile registry. Build, test, benchmark, teacher and training entry points select a profile instead of hard-coding an engine directory.

Cross-family engine execution uses UCI subprocesses. Native in-process tools under `engine/c/tools/` compile against the host API and are not used as a generic cross-family ABI.

### v334

The v334 search provides iterative deepening, PVS/alpha-beta, aspiration, quiescence, TT with fixed prefetch hash, Quiet SEE pruning extended to depth <= 5 with -45*depth margin, Continuous Smooth History LMR (clamp(ch/1024, -2, 2)), refined Reverse Futility Pruning, Stockfish Gravity move-ordering, Syzygy integration, MultiPV and Lazy SMP.

Its evaluator is NNU3: 799 inputs, a 256-neuron first hidden layer and a 64-neuron H2 file representation. The file has 50 live H2 neurons; the C loader compacts those to 52 SIMD slots (50 live plus two zeros) without changing the file contract. `v333`, `v332` and `v331` are retained as available frozen comparison baselines.

### v328

`v328` is frozen and remains available for explicit regression/comparison work against newer versions. It is not the bare/default orchestration target.

### v510

The v509 evaluator is NNU4 HalfKP-4-Bucket with 2560 sparse inputs per perspective, H1=48, `[stm, opp]` concat=96, H2=20 and scalar output, sharing the v333 refined RFP search parameters. Its model, encoder, importer, exporter and C runtime remain separate from NNU3.

### v604

The v604 evaluator is NNU5 HalfKAv2-32-Bucket with 256 neurons, sharing the v334 search improvements. `v603`, `v602` and `v601` remain available baselines.

### Historical snapshots

Tracked `v314`-`v327` trees are historical snapshots. `v325` and `v328` are additionally retained as explicit frozen comparison baselines. Historical source-level comments are not rewritten as newer documentation.
