# Regression and Strength Testing

Correctness tests and playing-strength tests answer different questions. A build/perft/UCI pass is required, but it does not establish Elo.

## Standard strength protocol

Unless a specific experiment states otherwise, Zchezz strength evidence uses:

```text
movetime        200 ms per move
Threads         1 per engine
concurrency     1 game at a time
openings        paired; same opening with colors reversed
tablebases      off
```

Record the exact engine SHA/profile, NNUE SHA, opening source, game count, W/D/L, Elo estimate/interval and any deviation from these defaults.

## Fixed-node tests

`go nodes` is useful for deterministic search-effort comparisons, debugging and some data-labeling workflows. It is not equivalent to the 200 ms movetime promotion protocol because different versions may convert nodes to wall-clock work at different rates.

Do not promote a strength claim by replacing movetime H2H evidence with fixed-node results.

## Quick sanity vs promotion evidence

A short paired H2H can detect catastrophic regressions. Promotion requires enough paired games for the uncertainty to be decision-useful. Report W/D/L and confidence/uncertainty rather than only a point Elo estimate.

## Cross-family matches

Use UCI subprocesses for v325-v500 or Zchezz-vs-Stockfish comparisons. Native in-process `arena` uses the v500-compatible host ABI and is intended for same-family native experiments.

## Stockfish

`tests/benchmark.py` resolves Stockfish through `ZCHEZZ_STOCKFISH`, repository-local `engine/stockfish/`, or PATH and uses the same 200 ms / one-thread / one-game-at-a-time defaults.

Hosted CI timing is smoke evidence only; do not use hosted-runner NPS/timing as promotion evidence.
