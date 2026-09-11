# Training

## Architecture-neutral data

Raw datasets should store chess-domain information such as position/FEN, side to move, result, evaluation, move and evaluator provenance. NNU3/NNU4 feature encoding belongs inside the selected training family.

The reusable teaching format under `train/teaching/` follows the same rule. It stores a standard chess-domain board, White-relative raw scores, sparse move labels, method flags, and provenance. It deliberately does not bake NNU3/NNU4 features or a fixed policy softmax into the dataset.

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

## Teaching and distillation

`train/teacher.py` is the public architecture-neutral teacher entry point. Its implementation lives in `train/teaching/teacher.py` and follows the repository bare-run convention: all defaults are editable constants near the top of the file and CLI arguments are optional overrides.

The default teaching cascade is designed for very large corpora:

1. direct Stockfish evaluator/NNUE (`eval`) on every position;
2. teacher/source disagreement mining using an existing Zchezz `eval_cp` when available;
3. static child policy on all hard cases plus a deterministic uniform sample;
4. policy margin/entropy scoring;
5. shallow MultiPV only when the cheap interest score passes a gate;
6. deeper search only on the hardest subset.

If a Stockfish binary does not expose the non-standard `eval` command, the backend falls back to a tiny fixed-node search. Fixed-node work here is labeling effort, not strength-promotion evidence; the standard 200 ms protocol remains the strength comparison rule.

The finished teaching dataset is a directory containing `metadata.json`, `positions.bin`, and sparse `moves.bin`. All centipawn labels are White-relative. `moves.bin` stores raw move scores and ranks so policy temperature, top-K, pairwise ranking, or future policy-head losses can be changed without relabeling. Metadata includes a teacher SHA-256 and a recipe signature; resume refuses incompatible teacher or labeling settings while allowing throughput-only changes such as worker count and batch size.

Supported position sources are Zchezz `.bin`, `.epd`, `.fen`, and `.pgn`, recursively from files/directories/globs. Zchezz `.bin` files are memory-mapped and their side-to-move `eval_cp` is converted to White POV. `SOURCE_MODE = "random"` or `"mixed"` can also generate new legal positions. Parquet archives can first be streamed through `train/labeling/process_positions.py` into packed `.bin`.

Teaching methods are extensible. Built-in methods register by name in `train/teaching/methods.py`; external modules can register additional methods and be loaded through `PLUGIN_MODULES` or `--plugin` without changing the core runner.

`train/teaching/loader.py` derives value probabilities, soft policy targets, and pairwise move-order targets from the raw teaching corpus at training time. New policy/value architectures should consume this adapter directly.

For the existing v325/NNU3 and v500/NNU4 value trainers, `train/teaching/export_eval_bin.py` writes a compatibility `SAMPLE_DTYPE` `.bin`. Because the export is evaluator supervision and a real outcome may be unknown, pass it to the current trainers with `k=0`:

```bash
python train/teaching/export_eval_bin.py
python train/run.py --profile v325 --source kind=bin,path=data/teaching/stockfish_eval.bin,k=0
python train/run.py --profile v500 --source kind=bin,path=data/teaching/stockfish_eval.bin,k=0
```

Useful teaching commands:

```bash
python train/teacher.py --show-config
python train/teacher.py
python train/teacher.py --methods static_value,gap_mining
python train/teacher.py --policy-sample-rate 1.0 --limit 100000
python train/teaching/inspect_dataset.py
python train/teaching/seeds.py
python train/teaching/export_eval_bin.py --show-config
```

`train/teaching/seeds.py` exports hard/high-interest roots for targeted self-play and can optionally expand each root by a few random legal plies. This supports an active-learning loop in which teacher compute and new self-play concentrate on regions where the current student disagrees most.

See `train/teaching/README.md` for format details, quiet-position modes, cost knobs, trainer adapters, and extension points.
