# Architecture

Zchezz has a released NNU3 profile, frozen NNU3 comparison baselines, and a supported NNU4 experimental profile.

- `v329` is the default/released working line and uses NNU3.
- `v328` is retained as the frozen pre-v3.29 NNU3 regression/comparison baseline.
- `v506` is a supported secondary experimental line and uses compact NNU4 HalfKP-4-Bucket.
- `engine/ACTIVE_ENGINE` is `v329`.

## Layering

### Engine core

Each engine directory contains its own `main.c`, board, search, NNUE, Syzygy and Polyglot integration. Engine state is versioned with the source so search/evaluator contracts cannot silently drift across families.

### Shared orchestration

`utils/engine_profiles.py` is the canonical profile registry. Build, test, benchmark, teacher and training entry points select a profile instead of hard-coding an engine directory.

Cross-family engine execution uses UCI subprocesses. Native in-process tools under `engine/c/tools/` compile against the v506-compatible host API and are not used as a generic cross-family ABI.

### v329

The v329 board/state and NNU3 evaluator are inherited from v328/v325. Search provides iterative deepening, PVS/alpha-beta, aspiration, quiescence, TT, move-ordering heuristics, LMR, null-move/futility/SEE pruning, Syzygy integration, MultiPV and Lazy SMP.

The v3.29 release adds pawn-structure correction history to static evaluation. The installed NNU3 weights are unchanged from v328/v325. Across 500 independent paired UHO confirmation games at 200 ms/move, `Threads=1`, Hash 64 MB and tablebases disabled, v3.29 scored 155 wins, 226 draws and 119 losses (~53.6%, about +25 Elo) against v3.28.

Its evaluator is NNU3: 799 inputs, a 256-neuron first hidden layer and a 64-neuron H2 file representation. The file has 50 live H2 neurons; the C loader compacts those to 52 SIMD slots (50 live plus two zeros) without changing the file contract.

### v328

`v328` is frozen and remains available for explicit regression/comparison work against v329. It is not the bare/default orchestration target.

### v325

`v325` is frozen and remains available for explicit regression/comparison work. It is not the bare/default orchestration target.

### v506

The v506 evaluator is NNU4 HalfKP-4-Bucket with 2560 sparse inputs per perspective, H1=48, `[stm, opp]` concat=96, H2=20 and scalar output. Its model, encoder, importer, exporter and C runtime remain separate from NNU3.

## Historical sources

Tracked `v314`-`v327` trees are historical snapshots. `v325` and `v328` are additionally retained as explicit frozen comparison baselines. Historical source-level comments are not rewritten as v329 documentation.
