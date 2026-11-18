# Historical Tools and Archives

This directory stores historical migration scripts, previous experimental campaign runners, and round-specific setups.

## Organization

- `migrations/`: One-time upgrade and retargeting scripts from older versions (`v320`, `v321`, `v322`).
- `rounds/`: Version-specific and round-specific search experiments, campaign runners and candidate builders (`round3` through `round11`, `cand6`, `hybrid`, `build_v605_modern.py`). Their output now lives under `artifacts/experiments/legacy_campaigns/`.
- `train/`: Historical variants of auxiliary head training (`train_aux_head_*.py`). `train/train_aux_head.py` replaces them for NNU3 and NNU5 profiles. `train/make_pt_from_nnu4.py` rebuilds a checkpoint for the v402 NNU4 layout only; `train/import_nnu4.py` covers current NNU4 profiles.

## Policy

These scripts remain in the repository for historical inspection and experiment reproducibility.
They are not active maintenance targets. All current experiments must use the declarative framework via `experiments/run_experiment.py`: a spec in `experiments/specs/`, and for source changes a patch in `experiments/patches/` built as a `candidate` engine.
