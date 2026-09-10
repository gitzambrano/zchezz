# Zchezz Claude Instructions

These instructions are repository contracts. Follow them for every change.

## Supported engine profiles

- Treat `v325` as the repository default and released working line.
- Treat `v500` as a supported secondary experimental line.
- Keep `engine/ACTIVE_ENGINE` equal to `v325` unless the user explicitly requests a promotion.
- Do not create or restore `engine/c/zchezz_v4xx` directories.
- Resolve supported families through `utils/engine_profiles.py`; do not hard-code profile selection in orchestration scripts.
- Keep NNU3 and NNU4 model, encoder, exporter, importer, and runtime code separate behind the profile interface.

## Bare-run contract

- Every public operational script must run with no command-line arguments.
- A bare run must select `v325` unless the script is a family-specific implementation module whose profile is explicit in its file name.
- Optional CLI arguments may override defaults; they must not be required for normal execution.
- `--show-config` or an equivalent non-destructive inspection mode must not build engines, start games, train, delete files, or change repository state.
- Missing optional external prerequisites must produce a clear diagnostic. Scripts intended for inspection or orchestration must not fail merely because Stockfish, CUDA, tablebases, or an opening corpus is absent.

## Generic orchestration

- Build, self-play, data generation, teacher labeling, training orchestration, export orchestration, tournaments, benchmarks, and test orchestration must select behavior from an engine profile.
- Keep raw training data architecture-neutral. Store positions, side to move, game result, evaluation, move, and provenance; encode NNUE features only inside the selected trainer.
- Use UCI process boundaries for cross-family matches and generic engine-vs-engine tooling.
- Do not make a generic runner depend on NNU3 or NNU4 binary layout.
- Do not duplicate runners for individual versions or experimental rounds.

## Stockfish

- Use Stockfish as the canonical external teacher and benchmark opponent.
- Resolve Stockfish through `ZCHEZZ_STOCKFISH`, repository-local `engine/stockfish/`, or PATH.
- Teacher output must normalize scores to a documented common point of view before writing training data.
- Benchmark defaults are `movetime=200 ms`, engine `Threads=1`, one concurrent game, paired openings with colors reversed, and tablebases disabled unless the test explicitly targets tablebases.
- Do not use a hosted CI timing result as promotion evidence.

## Training checkpoints

- Maintain `checkpoints/<profile>/latest.pt` as the canonical resumable checkpoint for every supported profile.
- Before training, create `latest.pt` from installed engine weights when no PyTorch checkpoint exists.
- After every successful training run, atomically refresh `latest.pt` from the newest completed checkpoint.
- Reject checkpoint architecture mismatches before loading weights.
- Keep installed engine weights and the corresponding importer sufficient to reconstruct a resumable checkpoint.
- Do not commit transient optimizer checkpoints unless the user explicitly requests tracked training artifacts.

## Builds and tests

- Bare native builds use `ENGINE=v325`.
- `ENGINE=v500` must build independently without changing the default marker.
- Run deterministic local tests before considering a change complete.
- Test both supported profiles for changes to shared build, UCI, dataset, training, checkpoint, or profile infrastructure.
- Run perft, UCI smoke, NNUE artifact validation, C invariants, and Python contract tests when their dependencies are available.
- Treat skipped tests as missing evidence, not as passes.
- Keep generated test evidence under `artifacts/`; do not overwrite source files as a test side effect.

## Git and branches

- Do not delete, create, rename, merge, rebase, or force-update unrelated branches as a side effect of testing.
- Do not make experiment branches depend on workflow files or branch-name patterns.
- Do not auto-promote experimental code to `main`.
- Keep experimental rounds isolated by branch, data/output directory, or explicit configuration rather than by copying workflows.
- Preserve user work that is unrelated to the requested change.

## GitHub Actions

- Keep Actions minimal and generic.
- Automatic CI may run on `main` and pull requests. Do not trigger broad automatic jobs solely because a branch name starts with a version prefix.
- Workflows must not commit, push, merge, delete branches, create branches, publish releases, or modify source files.
- Workflows use read-only repository permissions unless a user-requested publishing task requires a separate explicit workflow.
- Do not create version-specific or round-specific workflow files.
- Local scripts remain the authoritative way to run tests and experiments; Actions are optional verification.

## Source and documentation

- Keep comments technical, current, and conditional. State what must be true and what a caller may rely on.
- In `AGENTS.md`, do not include project history, migration narratives, or explanations of why a previous design changed.
- Keep `CLAUDE.md` and `AGENTS.md` bodies identical; only the first title line may differ.
- Update comments, tests, and docs when a public contract changes.
- Use repository-relative paths in tracked configuration whenever possible.

## Safety invariants

- Validate engine/profile compatibility before a long run starts.
- Never silently mix evaluation targets from different evaluators in a training column without provenance.
- Never silently reinterpret NNU3 data as NNU4 weights or vice versa.
- Fail before games or training begin when a required artifact has the wrong magic, dimensions, size, or profile.
- Keep deterministic seeds, paired openings, and test parameters in output metadata for reproducibility.
