# Architecture

Zchezz has a released NNU3 profile, a frozen NNU3 comparison baseline, and a supported NNU4 experimental profile.

- `v326` is the default/released working line and uses NNU3.
- `v325` is retained unchanged as the frozen pre-v3.26 NNU3 regression/comparison baseline.
- `v500` is a supported secondary experimental line and uses compact NNU4 HalfKP-4-Bucket.
- `engine/ACTIVE_ENGINE` is `v326`.

## Layering

### Engine core

Each engine directory contains its own `main.c`, board, search, NNUE, Syzygy and Polyglot integration. Engine state is versioned with the source so search/evaluator contracts cannot silently drift across families.

### Shared orchestration

`utils/engine_profiles.py` is the canonical profile registry. Build, test, benchmark, teacher and training entry points select a profile instead of hard-coding an engine directory.

Cross-family engine execution uses UCI subprocesses. Native in-process tools under `engine/c/tools/` compile against the v500-compatible host API and are not used as a generic cross-family ABI.

### v326

The v326 board/state and NNU3 evaluator are inherited from v325. Search provides iterative deepening, PVS/alpha-beta, aspiration, quiescence, TT, move-ordering heuristics, LMR, null-move/futility/SEE pruning, Syzygy integration, MultiPV and Lazy SMP.

The v3.26 release changes search selectivity only: it removes the blanket in-check depth extension, enables measured shallow history pruning at `-64 * depth`, and retunes LMR history feedback to `-512/-1024/+512`. The evaluator and installed NNU3 weights are unchanged from v325.

Its evaluator remains NNU3: 799 inputs, a 256-neuron first hidden layer and a 64-neuron H2 file representation. The current file has 50 live H2 neurons; the C loader compacts those to 52 SIMD slots (50 live plus two zeros) without changing the file contract.

### v325

`v325` is frozen and remains available for explicit regression/comparison work. It is not the bare/default orchestration target.

### v500

The v500 evaluator is NNU4 HalfKP-4-Bucket with 2560 sparse inputs per perspective, H1=48, `[stm, opp]` concat=96, H2=20 and scalar output. Its model, encoder, importer, exporter and C runtime remain separate from NNU3.

## Historical sources

Tracked `v314`-`v325` trees are historical snapshots. `v325` is additionally retained as the explicit pre-v3.26 comparison baseline. Historical source-level comments are not rewritten as v326 documentation.
