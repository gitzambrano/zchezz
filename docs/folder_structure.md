# Folder Structure

This document describes the current supported repository surfaces. Historical version directories remain tracked as snapshots but are not the default operational target.

```text
.github/workflows/ci.yml       one small read-only smoke workflow
AGENTS.md / CLAUDE.md          repository operating contracts
Readme.md                      project overview

docs/                          maintained project documentation
engine/ACTIVE_ENGINE           `v325`
engine/build/                   shared build/bundle infrastructure
engine/c/zchezz_v325/          default UCI engine, NNU3
engine/c/zchezz_v500/          supported secondary UCI engine, NNU4
engine/c/zchezz_v314..v324/    historical v3 snapshots
engine/c/tools/                 native self-play/arena/GA tools, v500-host API
engine/c/tests/                 C invariant harness

train/                         architecture-neutral data + profile-specific NNUE code
train/labeling/                dataset import/normalization/labeling utilities
tests/                         correctness, UCI, benchmark and game runners
tools/                         repository/artifact checks + retained historical migration utilities
utils/                         profile, path, CLI and policy helpers
artifacts/                     generated test/evidence output
```

## Supported engine files

Both `zchezz_v325/` and `zchezz_v500/` contain the engine-facing source modules:

- `main.c` — UCI process, options and search-thread orchestration;
- `board.c/.h` — position representation, move generation/make-unmake, hashing;
- `search.c/.h` — search, TT and heuristics;
- `nnue.c/.h` — family-specific evaluator/runtime;
- `syzygy.c/.h` — tablebase bridge;
- `book.c/.h`, `poly_keys.h` — Polyglot opening book support;
- `nnue_weights.bin` — installed network for that profile.

The evaluator contracts differ; never copy an NNU3 binary into v500 or an NNU4 binary into v325.

## Training

`train/run.py` is the profile-aware training entry point. `train/_train_nnu3_core.py` and `train/_train_nnu4_core.py` are family implementations. `encoding_nnu3.py` / `model_nnu3.py` belong to v325; `encoding.py` / `model.py` belong to v500.

`checkpoints/v325/latest.pt` and `checkpoints/v500/latest.pt` are the canonical resumable checkpoints when present.

## Historical utilities

Version-named utilities such as `tools/v321_*`, `tools/v322_*` and `tools/apply_v320_source_upgrade.py` are retained historical migration/experiment helpers. Their version names are intentional and must not be interpreted as current defaults.
