# Zchezz Agent Instructions

These instructions are repository contracts. Follow them for every change.

## Supported engine profiles

- Treat `v333` as the repository default and released working line (NNU3).
- Keep `v332`, `v331`, `v328` and `v327` available as frozen NNU3 regression/comparison baselines; do not retarget them with current-release changes.
- Treat `v509` as a supported secondary line (NNU4); `v508` and `v507` remain available comparison baselines.
- Treat `v603` as the supported secondary line representing the NNU5 family (256 neurons, HalfKAv2 32-bucket); `v602` and `v601` remain available comparison baselines.
- Keep `engine/ACTIVE_ENGINE` equal to `v333` unless the user explicitly requests a promotion.
- Maintain the three active lineages (3xx, 5xx, and 60x) documented and accessible via their profile definitions.
- Do not create or restore `engine/c/zchezz_v4xx` directories.
- Resolve supported families through `utils/engine_profiles.py`; do not hard-code profile selection in orchestration scripts.
- Keep NNU3, NNU4, and NNU5 model, encoder, exporter, importer, and runtime code separate behind the profile interface.
- Treat `v314` through `v327` and version-named migration utilities as historical snapshots; `v328` and `v327` may remain selectable only for explicit regression and comparison work.

## Bare-run contract

- Every public operational script must run with no command-line arguments.
- A bare run must select `v333` unless the script is a family-specific implementation module whose profile is explicit in its file name.
- Optional CLI arguments may override defaults; they must not be required for normal execution.
- `--show-config` or an equivalent non-destructive inspection mode must not build engines, start games, train, delete files, or change repository state.
- Missing optional external prerequisites must produce a clear diagnostic. Scripts intended for inspection or orchestration must not fail merely because Stockfish, CUDA, tablebases, or an opening corpus is absent.

## Generic orchestration

- Build, self-play, data generation, teacher labeling, training orchestration, export orchestration, tournaments, benchmarks, and test orchestration must select behavior from an engine profile.
- Keep raw training data architecture-neutral. Store positions, side to move, game result, evaluation, move, and provenance; encode NNUE features only inside the selected trainer.
- Use UCI process boundaries for cross-family matches and generic engine-vs-engine tooling.
- Do not make a generic runner depend on NNU3 or NNU4 binary layout.
- Do not duplicate runners for individual versions or experimental rounds. Never create ad-hoc, version-specific, match-specific, or round-specific Python runner scripts (e.g., `run_vXXX_vs_vYYY.py` or temporary tournament scripts).
- Keep operational and test runners general and parameter-driven. All tournament formats, time controls (e.g. `--movetime`, `--depth`, `--nodes`), concurrency levels, engine binaries, and profile pairings must be configurable via CLI arguments or top-of-file constants in existing canonical scripts (`tests/run_tournament.py`, `tests/run_tournament_quick.py`, `train/run_selfplay.py`).
- Implement any new search effort, evaluation mode, or tournament feature as an option within the canonical runners, never as an isolated one-off script.

## Stockfish

- Use Stockfish as the canonical external teacher and benchmark opponent.
- Resolve Stockfish through `ZCHEZZ_STOCKFISH`, repository-local `engine/stockfish/`, or PATH.
- Teacher output must normalize scores to a documented common point of view before writing training data.
- Benchmark defaults are `movetime=200 ms`, engine `Threads=1`, one concurrent game, paired openings with colors reversed, and tablebases disabled unless the test explicitly targets tablebases.
- Fixed-node (`go nodes`) runs may be used for deterministic search-effort or labeling work, but they are not equivalent to the standard movetime strength protocol and must not replace it for promotion evidence.
- Do not use a hosted CI timing result as promotion evidence.

## Training checkpoints

- Maintain `checkpoints/<profile>/latest.pt` as the canonical resumable checkpoint for every trainable profile.
- Before training, create `latest.pt` from installed engine weights when no PyTorch checkpoint exists.
- After every successful training run, atomically refresh `latest.pt` from the newest completed checkpoint.
- Reject checkpoint architecture mismatches before loading weights.
- Keep installed engine weights and the corresponding importer sufficient to reconstruct a resumable checkpoint.
- Do not commit transient optimizer checkpoints unless the user explicitly requests tracked training artifacts.

## Builds and tests

- Bare native builds use `ENGINE=v333`.
- `ENGINE=v328` and `ENGINE=v327` remain available for frozen regression comparisons.
- `ENGINE=v509` must build independently without changing the default marker.
- `ENGINE=v603` must build independently without changing the default marker.
- Run deterministic local tests before considering a change complete.
- Test `v333`, `v509`, and `v603` for changes to shared build, UCI, dataset, training, checkpoint, or profile infrastructure; test `v327` when a change claims backward compatibility with the frozen NNU3 baseline.
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
- Historical source comments may retain the version they document; current `v333`/`v509` comments must not present an older family as the active implementation.
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

## Cloud operations and repository organization

- Keep current Colab implementations under `colab/` according to `colab/layout.json`.
- Read `colab/AGENTS.md` and `colab/README.md` before cloud operations.
- Use `docs/repository-layout.md` for source roles and compatibility rules.
- Keep generated reports and environments under ignored `artifacts/` directories.
- Preserve frozen snapshots and active experiments during source cleanup.
