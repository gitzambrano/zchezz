# v5 NNUE Research Status and Ledger

This document tracks the experimental investigation and baseline status of the NNU4 (v5.x) engine line.

## Baselines

- **Experimental v5 baseline:** `v507`, NNU4 HalfKP-4Bucket (`2560 -> 48/perspective -> 20 -> 1`), weight SHA-256 `5e6cca42f11823505edefb3ee068e0e9bb3a8576f8fb5b0b7a688736ed377150`. Adds validated UCI pondering (`go ponder` / `ponderhit`) and serves as native host for in-process C tools (`arena`, `selfplay`, `ga_tune`).
- **Repository default line:** `v331` (NNU3).
- **Rule:** Cross-family comparisons are diagnostic only. Any v5 candidate must demonstrate empirical strength gains directly against the v5 baseline under the standard 200 ms movetime protocol.

## Summary of Completed Investigations

### 1. Root-Probe Teaching (v5.06 / b0)
- **Screen vs Gate:** An initial 64-game screen suggested +82.97 Elo. A 400-game independent gate invalidated the result: 112W/159D/129L (-14.77 Elo, CI95 [-40.13, +10.43]).
- **Conclusion:** Root-probe labeling is valid infrastructure, but the distillation objective does not yield robust playing strength.

### 2. Capacity Scaling / NNU5 Diagnostic (v5.21)
- **Setup:** HalfKP-8Bucket (`5120 -> 192 -> 32 -> 1`, ~1.98 MB weights) trained on 2.4M phase-balanced positions.
- **Fixed-Node Results (200k nodes/move):**
  - vs v5.06: -70.44 Elo (15W/2D/23L).
  - vs v3.28: -136.97 Elo (12W/1D/27L).
- **Conclusion:** Capacity scaling rejected under the current training formulation.

### 3. Static Evaluation Calibration (v5.22)
- Evaluated on 480 independent positions against Stockfish 19 at 16,384 nodes:
  - v5.06: MAE 162.12 cp, RMSE 273.51 cp, Pearson 0.8246.
  - v3.28: MAE 141.21 cp, RMSE 249.05 cp, Pearson 0.8779.
- **Conclusion:** Weakness is structural rather than an output scale error.

### 4. Runtime-Exact QAT (v5.23 / v5.24)
- Fixed discrepancy between PyTorch training forward pass and C runtime right-shift integer arithmetic.
- Verified 0 mismatches against C evaluator.
- **Conclusion:** Exact QAT retained as required training infrastructure.

### 5. Global-to-L2 Side Channel (GLB2)
- Added 31 -> 20 global projection into L2 (~620 int8 weights).
- All feature sets selected epoch 0; throughput dropped ~25% (2.28M to 1.71M NPS).
- **Status:** Closed and rejected.

### 6. Discrete Weight Optimization (v5.25 - v5.31)
Systematic local edits to int8 weights were tested to escape local minima:
- **v5.25 (Centered delta):** L3 epoch 1 showed +43.66 Elo in 96 games, but exact inspection proved 0 integer evaluation changes across all 325,121 reachable inputs (pure match noise control).
- **v5.26 (Ridge regression on L3):** Improved held-out RMSE (+1.4%), but degraded teacher top-1 agreement and Elo (-10 to -14 Elo).
- **v5.27 (Discrete ranking repair in L3):** Converged at step 0 (0/20 weights changed).
- **v5.28 (Multi-coordinate L3 beam search):** Found alternative weights, but 0.00% top-1 gain.
- **v5.30 (Sparse L2 ranking search):** All pools converged at step 0 (0/1920 weights changed).
- **v5.31 (Paired sparse L2 escape):** Coordinated distance-two edits worsened the training objective and held-out top-1.
- **Conclusion:** The compact architecture is at a discrete local minimum under root-probe objectives. Local integer micro-surgery is exhausted.

## Established Experimental Rules

1. 48-96 game H2H screens are triage only; they can fluctuate by tens of Elo even for identical evaluators.
2. Epoch 0 must always be an eligible checkpoint. `best_epoch > 0` is insufficient: exported weights must differ in deployed integer behavior.
3. Verify deployed integer weights and binary payload before spending match compute.
4. Use paired openings and paired-bootstrap confidence intervals.
5. Gates use deterministic shuffled openings with disjoint offsets across shards.
6. Lower training loss or teacher RMSE does not imply higher playing strength.
7. Runtime-exact QAT or direct discrete optimization is required for NNU4 training.
8. Avoid adding runtime architecture complexity without demonstrated strength gain.
9. Isolate variables: do not mix architecture, teacher, search and objective changes in one experiment.
10. Promotion requires a direct large gate against the baseline engine.

## Current Direction

Local NNUE micro-surgery is closed. Future improvements require either search-side mechanisms (correction history, pruning-aware residuals) or global retraining on large-scale datasets (10M+ positions). v507 remains the stable secondary NNU4 experimental baseline.
