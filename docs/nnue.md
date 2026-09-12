# NNUE

Zchezz deliberately supports two incompatible NNUE families. Profile selection must happen before encoding, checkpoint loading, export or engine startup.

## v326 / v325 — NNU3

Released installed file: `engine/c/zchezz_v326/nnue_weights.bin`

Frozen comparison file: `engine/c/zchezz_v325/nnue_weights.bin`

v3.26 reuses the v3.25 NNU3 weights unchanged; the release difference is in search selectivity, not evaluation.

### File contract

```text
magic       NNU3
size        426,864 bytes
dims        799, 256, 256, 64, 64
QA          255
QB          64
SHIFT       8
```

The 799 inputs are 768 half-mirror piece features plus 31 endgame features. L1 is `799 -> 256`; the NNU3 file stores L2 as `256 -> 64` and L3 as `64 -> 1`.

### Runtime compaction

The current NNU3 file has 14 H2 neurons whose quantized L3 weight is zero. The loader therefore copies the 50 live H2 rows and their L3 weights into a compiled 52-slot runtime (`50 live + 2 zero padding`). This is exact dead-neuron elimination. The installed file remains the 64-neuron NNU3 format; exporters/importers must not rewrite the file header as 52.

### Accumulator model

Each search thread has its own `NnueAccum`. The half-mirror contribution is maintained incrementally through make/unmake. Extra endgame projections are cached per thread. The NNU3 runtime also maintains PK17 passed-pawn/king-distance state incrementally.

Weights are process-global read-only after load; mutable accumulator/search state is not shared between helpers.

## v500 — NNU4 HalfKP-4-Bucket

Installed file: `engine/c/zchezz_v500/nnue_weights.bin`

```text
magic       NNU4
size        248,020 bytes
input       2560 per perspective
H1          48
concat      96 = [stm 48 | opp 48]
H2          20
output      1
QA          255
QB          64
SHIFT       8
```

The sparse feature index combines king bucket, relative piece identity and perspective-relative square. The two perspectives share L1 weights. Concat order is always `[stm, opp]`.

A king move that changes its bucket invalidates all features for that perspective, so the accumulator tracks bucket/dirty state and rebuilds the affected perspective when required.

## Checkpoints

Canonical paths:

```text
checkpoints/v326/latest.pt
checkpoints/v325/latest.pt   # frozen baseline if reconstructed explicitly
checkpoints/v500/latest.pt
```

Checkpoint metadata must identify a compatible architecture before state tensors are loaded. Installed weights plus the corresponding importer must be sufficient to reconstruct a resumable checkpoint when no `.pt` exists.

## Tools

```bash
python tools/check_nnue.py                 # v326 default
python tools/check_nnue.py --profile v326
python tools/check_nnue.py --profile v325
python tools/check_nnue.py --profile v500
python train/import_nnu3.py
python train/import_nnu4.py
python train/export_nnu3.py
python train/export_nnu4.py
```

Never use an NNU3 importer/exporter/model with v500 or an NNU4 path with v325/v326.
