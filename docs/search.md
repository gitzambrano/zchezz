# Search

## v325

`engine/c/zchezz_v325/search.c` is the current default search implementation.

The search stack includes:

- iterative deepening;
- aspiration windows;
- negamax alpha-beta with principal-variation search;
- quiescence search;
- static exchange evaluation;
- compact clustered transposition table;
- TT/capture/killer/history/countermove/continuation move ordering;
- late-move reductions;
- null-move pruning;
- futility and SEE-based pruning;
- repetition/draw handling;
- Syzygy probing when enabled;
- MultiPV root handling;
- time, node and external-stop limits;
- Lazy SMP helper threads with thread-private mutable search/NNUE state.

The v325 TT uses three 10-byte entries inside a 32-byte aligned cluster. Entries store a 16-bit key fragment, compact depth/generation/bound metadata, compact move, score and static evaluation. Hash size is dynamically allocated from the UCI `Hash` setting.

## v500

v500 has its own search implementation/API. Do not assume its internal `SearchState`, TT or NNUE instance ABI is source-compatible with v325. Generic comparisons use UCI processes.

## Strength interpretation

Search-node reductions are useful engineering metrics, but a lower node count is not automatically stronger. Promotion uses the movetime game protocol in `docs/regression-testing.md`.
