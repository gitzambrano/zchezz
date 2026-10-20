# Architecture

Zchezz has a released NNU3 profile, frozen NNU3 comparison baselines, and supported NNU4/NNU5 experimental profiles.

- `v332` is the default/released working line and uses NNU3 with Stockfish Gravity. `v331` is retained as an available baseline.
- `v328` is retained as the frozen pre-v3.29 NNU3 regression/comparison baseline.
- `v508` is a supported secondary line and uses compact NNU4 HalfKP-4-Bucket with Stockfish Gravity. `v507` is an available baseline.
- `v602` is a supported secondary line representing the NNU5 family (256 neurons, HalfKAv2 32-bucket).
- `engine/ACTIVE_ENGINE` is `v332`.

## Layering

### Engine core

Each engine directory contains its own `main.c`, board, search, NNUE, Syzygy and Polyglot integration. Engine state is versioned with the source so search/evaluator contracts cannot silently drift across families.

### Shared orchestration

`utils/engine_profiles.py` is the canonical profile registry. Build, test, benchmark, teacher and training entry points select a profile instead of hard-coding an engine directory.

Cross-family engine execution uses UCI subprocesses. Native in-process tools under `engine/c/tools/` compile against the host API and are not used as a generic cross-family ABI.

### v332

The v332 search provides iterative deepening, PVS/alpha-beta, aspiration, quiescence, TT, Stockfish Gravity move-ordering and history pruning, LMR, null-move/futility/SEE pruning, Syzygy integration, MultiPV and Lazy SMP.

Its evaluator is NNU3: 799 inputs, a 256-neuron first hidden layer and a 64-neuron H2 file representation. The file has 50 live H2 neurons; the C loader compacts those to 52 SIMD slots (50 live plus two zeros) without changing the file contract.

### v328

`v328` is frozen and remains available for explicit regression/comparison work against newer versions. It is not the bare/default orchestration target.

### v508

The v508 evaluator is NNU4 HalfKP-4-Bucket with 2560 sparse inputs per perspective, H1=48, `[stm, opp]` concat=96, H2=20 and scalar output. Its model, encoder, importer, exporter and C runtime remain separate from NNU3.

### Historical snapshots

Tracked `v314`-`v327` trees are historical snapshots. `v325` and `v328` are additionally retained as explicit frozen comparison baselines. Historical source-level comments are not rewritten as newer documentation.
