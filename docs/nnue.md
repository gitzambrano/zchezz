# NNUE

Zchezz supports three separate NNUE architectures: NNU3 (official 3.x line), NNU4 (compact 5.x line), and NNU5 (deep 6.x line). Profile selection must happen before encoding, checkpoint loading, export, or engine startup.

## v335 / v334 / v333 / v332 / v331 / v330 / v328 / v325 — NNU3

Released installed file: `engine/c/zchezz_v335/nnue_weights.bin`

Supported comparison files:
- `engine/c/zchezz_v334/nnue_weights.bin`
- `engine/c/zchezz_v332/nnue_weights.bin`
- `engine/c/zchezz_v328/nnue_weights.bin` (frozen pre-v3.29 baseline)
- `engine/c/zchezz_v325/nnue_weights.bin` (frozen baseline)

### File contract

```text
magic       NNU3
size        426,864 bytes
dims        799, 256, 256, 64, 64
QA          255
QB          64
SHIFT       8
```

The 799 inputs are 768 half-mirror piece features plus 31 endgame features. Layer 1 is `799 -> 256`; the NNU3 file stores layer 2 as `256 -> 64` and layer 3 as `64 -> 1`.

### Runtime compaction

The current NNU3 file has 14 H2 neurons whose quantized L3 weight is zero. The loader therefore copies the 50 live H2 rows and their L3 weights into a compiled 52-slot runtime (`50 live + 2 zero padding`). This is exact dead-neuron elimination. The installed file remains the 64-neuron NNU3 format; exporters and importers must not rewrite the file header as 52.

### Accumulator model

Each search thread has its own `NnueAccum`. The half-mirror contribution is maintained incrementally through make/unmake. Extra endgame projections are cached per thread. The NNU3 runtime also maintains PK17 passed-pawn and king-distance state incrementally.

Weights are process-global read-only after load. Mutable accumulator and search state is never shared between helper threads.

### Dual-NNUE auxiliary head

In v335, an auxiliary fast linear head projects ReLU1 activations directly into a centipawn estimate. This head enables fast evaluations and early pruning for unpromising branches.

---

## v510 / v509 / v508 / v507 — NNU4 HalfKP-4-Bucket

Supported installed file: `engine/c/zchezz_v510/nnue_weights.bin`
Comparison files: `engine/c/zchezz_v509/nnue_weights.bin`, `engine/c/zchezz_v508/nnue_weights.bin`, `engine/c/zchezz_v507/nnue_weights.bin`

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

The sparse feature index combines king bucket, relative piece identity, and perspective-relative square. The two perspectives share layer 1 weights. Concat order is always `[stm, opp]`.

A king move that changes its bucket invalidates all features for that perspective. The accumulator tracks bucket and dirty state and rebuilds the affected perspective when required.

---

## v605 / v604 / v603 / v602 / v601 — NNU5 HalfKAv2-32-Bucket

Supported installed file: `engine/c/zchezz_v605/nnue_weights.bin`
Comparison files: `engine/c/zchezz_v604/nnue_weights.bin`, `engine/c/zchezz_v603/nnue_weights.bin`, `engine/c/zchezz_v602/nnue_weights.bin`, `engine/c/zchezz_v601/nnue_weights.bin`

```text
magic       NNU5
size        11,547,408 bytes
input       22528 per perspective (32 King Buckets)
H1          256
activation  SCReLU
H2          64
output      1
QA          255
QB          64
SHIFT       8
```

The NNU5 architecture uses HalfKAv2 half-mirror indexing with 32 king buckets, giving 22,528 sparse features per perspective. The accumulator uses AVX2 SIMD vectorization for accumulator refreshes.

### Dual-NNUE fast auxiliary head

In v605, a calibrated 256 -> 1 auxiliary linear head operates on SCReLU activations. Fitted via GPU Ridge regression directly on the network's internal features ($r = 0.7093$), this auxiliary evaluator cuts search nodes on quiet moves and allows fast early branch exit while sustaining 1.6M NPS throughput.

---

## Checkpoints

Canonical paths:

```text
checkpoints/v335/latest.pt
checkpoints/v334/latest.pt   # supported comparison baseline
checkpoints/v328/latest.pt   # frozen baseline if reconstructed explicitly
checkpoints/v510/latest.pt
checkpoints/v507/latest.pt   # supported comparison baseline
checkpoints/v605/latest.pt
checkpoints/v604/latest.pt   # supported comparison baseline
```

Checkpoint metadata must identify a compatible architecture before state tensors are loaded. Installed weights plus the corresponding importer must be sufficient to reconstruct a resumable checkpoint when no `.pt` exists.

## Tools

```bash
python tools/check_nnue.py                 # v335 default
python tools/check_nnue.py --profile v335
python tools/check_nnue.py --profile v510
python tools/check_nnue.py --profile v605
python tools/check_nnue.py --profile v328
python train/import_nnu3.py
python train/import_nnu4.py
python train/import_nnu5.py
python train/export_nnu3.py
python train/export_nnu4.py
python train/export_nnu5.py
```

Never mix importers, exporters, or models across families. NNU3, NNU4, and NNU5 maintain strict boundaries in encoder, runtime, and weights.
