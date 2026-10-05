# Architecture

Zchezz has a released NNU3 profile, frozen NNU3 comparison baselines, and a supported NNU4 experimental profile.

- `v331` is the default/released working line and uses NNU3. It is v3.30 plus validated pondering.
- `v328` is retained as the frozen pre-v3.29 NNU3 regression/comparison baseline.
- `v507` is a supported secondary experimental line and uses compact NNU4 HalfKP-4-Bucket. It is v5.06 plus validated pondering.
- `engine/ACTIVE_ENGINE` is `v331`.

## Layering

### Engine core

Each engine directory contains its own `main.c`, board, search, NNUE, Syzygy and Polyglot integration. Engine state is versioned with the source so search/evaluator contracts cannot silently drift across families.

### Shared orchestration

`utils/engine_profiles.py` is the canonical profile registry. Build, test, benchmark, teacher and training entry points select a profile instead of hard-coding an engine directory.

Cross-family engine execution uses UCI subprocesses. Native in-process tools under `engine/c/tools/` compile against the v507-compatible host API and are not used as a generic cross-family ABI.

### v331

The v331 board/state and NNU3 evaluator are inherited from v3.30; the NNUE weights are unchanged. Search provides iterative deepening, PVS/alpha-beta, aspiration, quiescence, TT, move-ordering heuristics, LMR, null-move/futility/SEE pruning, Syzygy integration, MultiPV and Lazy SMP.

The v3.31 release adds validated UCI pondering. `go ponder` holds `bestmove` until `stop` or `ponderhit`; on a hit, timed search resumes with warm TT/history state. The 3+2 promotion gate scored 1W/11D/0L against the identical engine with pondering disabled. The browser implementation uses bounded Worker slices so pondering does not block the UI thread.

Its evaluator is NNU3: 799 inputs, a 256-neuron first hidden layer and a 64-neuron H2 file representation. The file has 50 live H2 neurons; the C loader compacts those to 52 SIMD slots (50 live plus two zeros) without changing the file contract.

### v328

`v328` is frozen and remains available for explicit regression/comparison work against v331. It is not the bare/default orchestration target.

### v325

`v325` is frozen and remains available for explicit regression/comparison work. It is not the bare/default orchestration target.

### v507

The v507 evaluator is NNU4 HalfKP-4-Bucket with 2560 sparse inputs per perspective, H1=48, `[stm, opp]` concat=96, H2=20 and scalar output. Its model, encoder, importer, exporter and C runtime remain separate from NNU3.

## Historical sources

Tracked `v314`-`v327` trees are historical snapshots. `v325` and `v328` are additionally retained as explicit frozen comparison baselines. Historical source-level comments are not rewritten as v331 documentation.
