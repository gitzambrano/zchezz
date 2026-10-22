# Release History and Empirical Gates

This document records the validated release milestones and empirical gates for the Zchezz engine families.

---

## 3.x Family (NNU3 — Main Released Line)

### v3.35 (Official Release Champion & Repository Default)
- **Engine Directory:** `engine/c/zchezz_v335/`
- **Evaluator:** NNU3 (`799 -> 256 -> 64 -> 1`, 426,864 bytes).
- **Key Enhancements:**
  - Dual-NNUE auxiliary fast head: projects hidden-layer activations to an auxiliary evaluation score for rapid early branch pruning.
  - Quiet SEE pruning extended to depth 6, safely cutting branches on unpromising quiet moves.
  - Refined Reverse Futility Pruning (RFP) with improving flag adaptation (`75 * depth - (improving ? 40 : 0)`) up to depth 10.
  - Compact sf32 Transposition Table with pseudo-legality validation.
  - Stockfish gravity move ordering with quadratic history cutoff bonuses.
  - Official WebAssembly release bundle (`engine/c/zchezz_v335/zchezz_bundle.html` and root `index.html`).
- **Performance:** Achieves ~2900 Elo strength, ~1.1M NPS on single core, and an average depth of 16+ plies at 100 ms.

### v3.34 (Supported Comparison Baseline)
- **Engine Directory:** `engine/c/zchezz_v334/`
- **Key Enhancements:** Refined RFP depth thresholds and move ordering parameter tuning.

### v3.33 (Supported Comparison Baseline)
- **Engine Directory:** `engine/c/zchezz_v333/`
- **Key Enhancements:** Refined Reverse Futility Pruning margin tightening.
- **Evidence:** +12.2 Elo H2H in benchmark testing, record 108 wins against Stockfish 2900.

### v3.32 (Supported Comparison Baseline)
- **Engine Directory:** `engine/c/zchezz_v332/`
- **Key Enhancements:** Stockfish gravity decay on quiet history with quadratic cutoff bonuses.

### v3.31 (Supported Comparison Baseline)
- **Engine Directory:** `engine/c/zchezz_v331/`
- **Evaluator:** NNU3 (`799 -> 256 -> 64 -> 1`, 426,864 bytes). Weights identical to v3.30.
- **Key Enhancements:**
  - Validated UCI pondering support (`go ponder` holds search until `stop` or `ponderhit`).
  - Warm hash and history preservation on hit for seamless transition into timed search.
  - WebAssembly Worker slicing for responsive browser execution without UI thread blocking.
- **Evidence:** 3+2 TC match scored 1W / 11D / 0L against the identical engine without pondering. Passes ponder protocol validation suite.

### v3.30
- **Key Enhancements:**
  - TT-move pseudo-legality validation: rejects corrupted or colliding compact-TT entries whose geometry or special-move fields are invalid in the current position before make/unmake.
  - Lazy SMP stability improvements.

### v3.29
- **Key Enhancements:**
  - Pawn-structure correction history: adds a per-pawn-hash correction term to static evaluation, improving positional consistency across similar pawn structures.

### v3.28 (Frozen Baseline)
- **Engine Directory:** `engine/c/zchezz_v328/`
- **Role:** Frozen regression and comparison baseline representing the pre-v3.29 engine state.

### v3.27 (Frozen Baseline)
- **Engine Directory:** `engine/c/zchezz_v327/`
- **Role:** Frozen comparison baseline for earlier NNU3 architecture and move ordering contracts.

### v3.26
- **Key Enhancements:**
  - Search selectivity overhaul: removed blanket `depth++` on check nodes; quiescence search handles in-check horizons.
  - Shallow quiet history pruning retuned from `-4000 * depth` to `-64 * depth`.
  - Quiet LMR history feedback retuned to `-512 / -1024 / +512`.
- **Strength Gate (vs v3.25):**
  - Protocol: 800 games, 200 ms/move, 1 thread, paired UHO openings, tablebases off.
  - Result: 249W / 346D / 205L (52.75%), **+19.13 ± 18.14 Elo** (95% CI).

### v3.25 (Frozen Baseline)
- **Engine Directory:** `engine/c/zchezz_v325/`
- **Role:** Earlier frozen baseline introducing compact clustered TT32 (three 10-byte entries in a 32-byte cache line).

---

## 5.x Family (NNU4 — Supported Low-Footprint Line)

### v5.10 (Supported Secondary Line Baseline)
- **Engine Directory:** `engine/c/zchezz_v510/`
- **Evaluator:** NNU4 HalfKP-4Bucket (`2560 -> 48 -> 96 -> 20 -> 1`, 248,020 bytes).
- **Key Enhancements:**
  - Continuous Smooth History Late Move Reductions (LMR).
  - Transposition table prefetch cache optimizations.
  - Quiet SEE pruning extended to depth 5.
  - Validated UCI pondering support.

### v5.09 (Supported Comparison Baseline)
- **Engine Directory:** `engine/c/zchezz_v509/`
- **Key Enhancements:** Refined RFP margin tuning for NNU4.

### v5.08 (Supported Comparison Baseline)
- **Engine Directory:** `engine/c/zchezz_v508/`
- **Key Enhancements:** Stockfish gravity history move ordering for NNU4.

### v5.07 (Supported Comparison Baseline)
- **Engine Directory:** `engine/c/zchezz_v507/`
- **Evaluator:** NNU4 HalfKP-4Bucket (`2560 -> 48 -> 96 -> 20 -> 1`, 248,020 bytes).
- **Role:** Primary host for native in-process C tooling (`arena`, `selfplay`, `ga_tune`). Adds validated UCI pondering.

---

## 6.x Family (NNU5 — Supported High-Capacity Line)

### v6.05 (Supported Secondary Line Baseline)
- **Engine Directory:** `engine/c/zchezz_v605/`
- **Evaluator:** NNU5 HalfKAv2-32-Bucket (`22528 -> 256 -> 64 -> 1`, 11,547,408 bytes), SCReLU activation.
- **Training:** Retrained 20 deep epochs on GPU across 300M+ positions (validation loss 0.507).
  - Direct head-to-head vs v604: 13.0 - 7.0 (+107.5 Elo) in pure evaluation; 11.5 - 8.5 (+52.5 Elo) with fast head enabled.
- **Key Enhancements:**
  - Dual-NNUE Fast Auxiliary Head: calibrated via GPU Ridge regression on internal SCReLU activations ($r = 0.7093$).
  - Corrected king-bucket invalidation logic for accumulator refreshes.
  - AVX2 vectorized accumulator refresh and SIMD forward pass.
  - Staged move generation and sf32 compact Transposition Table.
- **Performance:** Achieves search throughput exceeding 1.6M NPS and an average depth of 16.8 plies at 100 ms movetime.

### v6.04 (Supported Comparison Baseline)
- **Engine Directory:** `engine/c/zchezz_v604/`
- **Key Enhancements:** Staged move generation and sf32 compact TT integration on NNU5.

### v6.03 (Supported Comparison Baseline)
- **Engine Directory:** `engine/c/zchezz_v603/`
- **Key Enhancements:** Refined Reverse Futility Pruning for NNU5.

### v6.02 (Supported Comparison Baseline)
- **Engine Directory:** `engine/c/zchezz_v602/`
- **Key Enhancements:** Stockfish gravity history move ordering for NNU5.

### v6.01 (Supported Comparison Baseline)
- **Engine Directory:** `engine/c/zchezz_v601/`
- **Key Enhancements:** Initial HalfKAv2 32-bucket architecture and AVX2 accumulator implementation.
