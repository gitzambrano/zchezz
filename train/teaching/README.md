# Zchezz teaching pipeline

This directory turns large chess corpora into reusable architecture-neutral teacher datasets. Expensive teacher work is performed once; v325/NNU3, v500/NNU4, and future networks can consume the same labels.

## Bare run

All public Python tools have editable defaults at the top of the file and work without mandatory CLI arguments:

```bash
python train/teacher.py
python train/teaching/inspect.py
python train/teaching/seeds.py
```

CLI flags only override defaults. `--show-config` is non-destructive.

## Default cascade

1. `static_value`: Stockfish `eval`, i.e. direct evaluator/NNUE without normal tree search. If unsupported, the backend falls back to a tiny fixed-node search.
2. `gap_mining`: compares teacher output with `source_cp` already present in an existing Zchezz corpus. This makes disagreement mining almost free.
3. `static_policy`: evaluates every legal child only on hard positions plus a deterministic uniform sample (`POLICY_SAMPLE_RATE`).
4. `gap_mining`: adds policy margin and normalized entropy to the interest score.
5. `adaptive_search`: shallow MultiPV only for interesting positions, then deeper search only for the hardest subset.

`METHODS` is an ordered tuple, not hard-coded control flow. New methods register with `@register("name")`. External modules can register methods and be loaded with `PLUGIN_MODULES` or repeated `--plugin` flags.

## Binary format

A teaching dataset directory contains:

- `metadata.json`: format version, provenance, configuration and run statistics;
- `positions.bin`: fixed-size position/value records;
- `moves.bin`: sparse move labels referenced by offset/count from each position.

All scores are **White-relative centipawns**. The board uses standard chess-domain square/piece codes, not NNU3/NNU4 features.

Move labels store raw `static_cp`, optional refined `search_cp`, and ranks. The dataset deliberately does **not** store a fixed softmax policy. Training can later choose temperature, top-K, best-move classification, pairwise ranking, or another policy loss without relabeling.

## Existing data

`teacher.py` recursively streams `.bin`, `.epd`, `.fen`, and `.pgn` inputs. Zchezz packed `.bin` files are memory-mapped. Existing `eval_cp` is converted from side-to-move POV to White POV and becomes `source_cp`, which is reused as the student signal for gap mining.

Set `INPUTS` to a file, glob, or directory containing millions of positions. The output writer is resumable. Worker processes keep long-lived Stockfish instances, so engines are not restarted per position.

## New data and active learning

Set `SOURCE_MODE = "random"` or `"mixed"` to add newly generated legal positions.

More importantly, `python train/teaching/seeds.py` exports hard/high-interest positions to `hard_seeds.epd`. They can be reused as starting/opening seeds for targeted self-play. Optional `EXPAND_PLIES` and `BRANCHES_PER_SEED` perturb hard roots into nearby legal positions.

This creates an active-learning loop: find where Zchezz disagrees with the teacher, spend search only there, generate nearby games, retrain, and repeat.

## Quiet filtering

`QUIET_MODE` supports:

- `all`: keep everything;
- `quiet-only`: keep only positions with no check/capture/promotion activity;
- `stratified` (default): keep all positions and tag quiet/tactical/check/terminal categories.

For stricter legacy quiet filtering, `train/labeling/process_positions.py` remains available as a preprocessing stage.

## Cost controls

For very large runs tune these first:

- `POLICY_SAMPLE_RATE` — child-policy coverage outside hard cases;
- `GAP_HARD_CP` — source/teacher residual that forces hard handling;
- `SEARCH_INTEREST` — shallow-search gate;
- `DEEP_INTEREST` — deep-search gate;
- `WORKERS` — long-lived Stockfish processes;
- `SF_THREADS = 1` — normally parallelize across positions rather than inside one teacher.

Run a pilot shard, inspect it with `inspect.py`, then tune the gates before committing compute to the full corpus.
