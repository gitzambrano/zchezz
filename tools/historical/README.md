# Historical Tools and Archives

This directory stores historical migration scripts, previous experimental campaign runners, and round-specific setups.

## Organization

- `migrations/`: One-time upgrade and retargeting scripts from older versions (`v320`, `v321`, `v322`).
- `rounds/`: Version-specific and round-specific search experiments and campaign runners (`round3` through `round11`, `cand6`, `hybrid`).
- `train/`: Historical variants of auxiliary head training (`train_aux_head_*.py`).

## Policy

These scripts remain in the repository for historical inspection and experiment reproducibility.
They are not active maintenance targets. All current experiments must use the declarative framework via `experiments/run_experiment.py`.
