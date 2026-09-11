# Architecture

Zchezz has two supported engine profiles and one default.

- `v325` is the default/released working line and uses NNU3.
- `v500` is a supported secondary experimental line and uses compact NNU4 HalfKP-4-Bucket.
- `engine/ACTIVE_ENGINE` remains `v325` until an explicit promotion.

## Layering

### Engine core

Each engine directory contains its own `main.c`, board, search, NNUE, Syzygy and Polyglot integration. Engine state is versioned with the source so search/evaluator contracts cannot silently drift across families.

### Shared orchestration

`utils/engine_profiles.py` is the canonical profile registry. Build, test, benchmark, teacher and training entry points select a profile instead of hard-coding an engine directory.

Cross-family engine execution uses UCI subprocesses. Native in-process tools under `engine/c/tools/` compile against the v500-compatible host API and are not used as a generic cross-family ABI.

### v325

The v325 board maintains mailbox + bitboards + cached occupancies + incremental Zobrist state. Search provides iterative deepening, PVS/alpha-beta, aspiration, quiescence, TT, move-ordering heuristics, LMR, null-move/futility/SEE pruning, Syzygy integration, MultiPV and Lazy SMP.

Its evaluator is NNU3: a 799-input network with a 256-neuron first hidden layer and a 64-neuron H2 file representation. The current file has 50 live H2 neurons; the C loader compacts those to 52 SIMD slots (50 live plus two zeros) without changing the file contract.

### v500

The v500 evaluator is NNU4 HalfKP-4-Bucket with 2560 sparse inputs per perspective, H1=48, `[stm, opp]` concat=96, H2=20 and scalar output. Its model, encoder, importer, exporter and C runtime remain separate from NNU3.

## Historical sources

Tracked `v314`-`v324` trees are historical snapshots. Their source-level version comments describe those snapshots and are intentionally not rewritten as v325 documentation.
