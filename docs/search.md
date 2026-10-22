# Search

## v335

`engine/c/zchezz_v335/search.c` is the current default search implementation.

The search stack includes:

- iterative deepening with aspiration windows;
- negamax alpha-beta with principal-variation search (PVS);
- quiescence search with delta pruning;
- static exchange evaluation (SEE) and Quiet SEE pruning up to depth 6;
- Dual-NNUE auxiliary fast head for rapid evaluation and early branch pruning;
- refined Reverse Futility Pruning (RFP) with improving flag adaptation up to depth 10;
- Stockfish gravity history move ordering with quadratic cutoff bonuses;
- compact clustered transposition table (sf32: three 10-byte entries per 32-byte cache line) with pseudo-legality validation;
- move ordering: TT move, winning captures (MVV-LVA + SEE), killer moves, countermoves, quiet history, losing captures;
- late-move reductions (LMR) based on depth, move count, and history feedback;
- null-move pruning;
- futility and SEE-based pruning;
- repetition and draw handling;
- Syzygy tablebase probing when enabled;
- MultiPV root handling;
- time, node, and external-stop limits;
- Lazy SMP helper threads with thread-private mutable search and NNUE state;
- validated UCI pondering (`go ponder` / `ponderhit`).

The v335 Transposition Table uses three 10-byte entries inside a 32-byte aligned cluster. Entries store a 16-bit key fragment, compact depth, generation, bound metadata, compact move, score, and static evaluation. Hash size is dynamically allocated from the UCI `Hash` setting.

## v510

`engine/c/zchezz_v510/search.c` is the supported secondary search implementation for the NNU4 line. It incorporates Continuous Smooth History LMR, TT prefetch cache optimizations, and Quiet SEE pruning to depth 5. Do not assume its internal search state ABI is source-compatible with v335. Cross-family comparisons must use UCI processes.

## v605

`engine/c/zchezz_v605/search.c` is the supported secondary search implementation for the NNU5 line. It integrates a calibrated Dual-NNUE fast auxiliary head, staged move generation, AVX2 vectorized accumulator refresh, and the sf32 compact Transposition Table.

## Strength interpretation

Search-node reductions are useful engineering metrics, but a lower node count is not automatically stronger. Promotion uses the movetime game protocol in `docs/regression-testing.md`.
