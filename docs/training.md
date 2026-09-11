# Training

## Architecture-neutral data

Raw datasets should store chess-domain information such as position/FEN, side to move, result, evaluation, move and evaluator provenance. NNU3/NNU4 feature encoding belongs inside the selected training family.

## Profile entry point

```bash
python train/run.py                    # v325
python train/run.py --profile v325
python train/run.py --profile v500
python train/run.py --show-config
```

A bare run defaults to v325. Inspection mode must not train or modify artifacts.

## v325 family

- `train/encoding_nnu3.py`
- `train/model_nnu3.py`
- `train/_train_nnu3_core.py`
- `train/_export_nnu3_core.py`
- `train/import_nnu3.py`
- `train/export_nnu3.py`

The installed runtime artifact is NNU3.

## v500 family

- `train/encoding.py`
- `train/model.py`
- `train/_train_nnu4_core.py`
- `train/import_nnu4.py`
- `train/export_nnu4.py`

The installed runtime artifact is compact NNU4.

## Checkpoints

`checkpoints/<profile>/latest.pt` is the canonical resumable checkpoint. Before loading tensors, training/export code must verify architecture metadata and fail on cross-family mismatches. When no checkpoint exists, the profile importer may reconstruct a resumable checkpoint from the installed engine weights.

## Teacher

`train/teacher.py` resolves Stockfish through the common profile helper and writes architecture-neutral labeled EPD. Teacher effort is independent of the 200 ms strength-promotion protocol; fixed depth/nodes may be appropriate for labeling when clearly recorded as labeling configuration.
