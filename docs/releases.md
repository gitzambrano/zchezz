# Release History and Empirical Gates

This document records the validated release milestones and empirical gates for the Zchezz engine families.

---

## 3.x Family (NNU3 — Main Released Line)

### v3.31 (Current Default Release)
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

### v3.26
- **Key Enhancements:**
  - Search selectivity overhaul: removed blanket `depth++` on check nodes; quiescence search handles in-check horizons.
  - Shallow quiet history pruning retuned from `-4000 * depth` to `-64 * depth`.
  - Quiet LMR history feedback retuned to `-512 / -1024 / +512`.
- **Strength Gate (vs v3.25):**
  - Protocol: 800 games, 200 ms/move, 1 thread, paired UHO openings, tablebases off.
  - Result: 249W / 346D / 205L (52.75%), **+19.13 ± 18.14 Elo** (95% CI).
  - Search efficiency: ~20% reduction in depth-12 nodes on standard 20-position test suite.

### v3.25 (Frozen Baseline)
- **Engine Directory:** `engine/c/zchezz_v325/`
- **Role:** Earlier frozen baseline introducing compact clustered TT32 (three 10-byte entries in a 32-byte cache line).

---

## 5.x Family (NNU4 — Supported Experimental Line)

### v5.07 (Current Experimental Line)
- **Engine Directory:** `engine/c/zchezz_v507/`
- **Evaluator:** NNU4 HalfKP-4Bucket (`2560 -> 48 -> 96 -> 20 -> 1`, 248,020 bytes). Deployed weights identical to v5.06.
- **Role:** Primary host for native in-process C tooling (`arena`, `selfplay`, `ga_tune`). Adds validated UCI pondering.

### v5.02
- **Training:** Direct Stockfish 19 NNUE distillation over 1,255,843 usable positions from v5 self-play. Warm start from v5.01.
- **Strength Gate (vs v5.01):**
  - Protocol: 128 games, 200 ms/move, 1 thread, 64 MB TT, paired EPD openings.
  - Result: 63W / 28D / 37L (60.16%), **+71.6 ± 54.2 Elo** (95% CI).

### v5.01
- **Training:** Direct Stockfish 19 NNUE distillation over 100,000 quiet positions.
- **Strength Gate:**
  - vs v5.00: 704W / 333D / 595L over 1,632 games, **+23.2 ± 15.1 Elo** (95% CI).
  - vs pinned v3.24: 163W / 79D / 270L over 512 games, **-73.7 ± 28.2 Elo**. Established that NNU4 line lagged behind v3.x.
