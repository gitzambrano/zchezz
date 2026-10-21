# Architecture

Zchezz has a released NNU3 profile, frozen NNU3 comparison baselines, and supported NNU4/NNU5 experimental profiles.

- `v335` is the default/released working line and uses NNU3 with Dual-NNUE auxiliary head, Quiet SEE d6 pruning, Dynamic RFP, and Compact sf32 TT. `v334`, `v333`, `v332` and `v331` are retained as available baselines.
- `v328` is retained as the frozen pre-v3.29 NNU3 regression/comparison baseline.
- `v510` is a supported secondary line and uses compact NNU4 HalfKP-4-Bucket with Quiet SEE d5, Continuous Smooth History LMR and TT Prefetch cache fix. `v509`, `v508` and `v507` are available baselines.
- `v605` is a supported secondary line representing the NNU5 family (256 neurons, HalfKAv2 32-bucket) with fixed King Bucket invalidation, AVX2 vectorized accumulator refresh, sf32 compact TT, staged move generation and Dual-NNUE auxiliary head. `v604`, `v603`, `v602` and `v601` are available baselines.
- `engine/ACTIVE_ENGINE` is `v335`.

## Layering

### Engine core

Each engine directory contains its own `main.c`, board, search, NNUE, Syzygy and Polyglot integration. Engine state is versioned with the source so search/evaluator contracts cannot silently drift across families.

### Shared orchestration

`utils/engine_profiles.py` is the canonical profile registry. Build, test, benchmark, teacher and training entry points select a profile instead of hard-coding an engine directory.

Cross-family engine execution uses UCI subprocesses. Native in-process tools under `engine/c/tools/` compile against the host API and are not used as a generic cross-family ABI.

### v335

The v335 search provides iterative deepening, PVS/alpha-beta, aspiration, quiescence, TT with sf32 compact 32-byte cache-aligned buckets, Quiet SEE pruning extended to depth <= 6, Dynamic RFP with improving flag, staged move generation, Dual-NNUE auxiliary head, Syzygy integration, MultiPV and Lazy SMP.

Its evaluator is NNU3: 799 inputs, a 256-neuron first hidden layer and a 64-neuron H2 file representation. The file has 50 live H2 neurons; the C loader compacts those to 52 SIMD slots (50 live plus two zeros) without changing the file contract. `v334`, `v333`, `v332` and `v331` are retained as available frozen comparison baselines.

### v328

`v328` is frozen and remains available for explicit regression/comparison work against newer versions. It is not the bare/default orchestration target.

### v510

The v510 evaluator is NNU4 HalfKP-4-Bucket with 2560 sparse inputs per perspective, H1=48, `[stm, opp]` concat=96, H2=20 and scalar output. Its model, encoder, importer, exporter and C runtime remain separate from NNU3. `v509`, `v508` and `v507` remain available baselines.

### v605

The v605 evaluator is NNU5 HalfKAv2-32-Bucket with 256 neurons, featuring fixed king bucket invalidation, AVX2 vectorized accumulator refresh, sf32 compact TT, staged move generation and Dual-NNUE auxiliary head. `v604`, `v603`, `v602` and `v601` remain available baselines.

### Historical snapshots

Tracked `v314`-`v327` trees are historical snapshots. `v325` and `v328` are additionally retained as explicit frozen comparison baselines. Historical source-level comments are not rewritten as newer documentation.
