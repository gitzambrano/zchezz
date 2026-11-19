# Zchezz Agent Instructions

## Engine profiles

| Profile | Role | Family |
|---|---|---|
| `v335` | Default and released line; `engine/ACTIVE_ENGINE` stays `v335` unless the user asks for a promotion | NNU3 |
| `v334` `v333` `v332` `v331` `v328` `v327` | Frozen regression/comparison baselines; never retarget them with current-release changes | NNU3 |
| `v510` | Supported secondary line | NNU4 |
| `v509` `v508` `v507` | Comparison baselines | NNU4 |
| `v605` | Supported secondary line (256 neurons, HalfKAv2 32-bucket) | NNU5 |
| `v604` `v603` `v602` `v601` | Comparison baselines | NNU5 |

- Resolve profiles through `utils/engine_profiles.py`; never hard-code a profile in an orchestration script.
- Keep NNU3, NNU4 and NNU5 model, encoder, exporter, importer and runtime code separate behind the profile interface.
- Do not create or restore `engine/c/zchezz_v4xx`.
- `v314`–`v327` and version-named migration utilities are historical snapshots. Select `v328`/`v327` only for explicit regression work.

## Bare-run contract

- Every public operational script runs with no arguments and selects `v335`, unless its file name states a family.
- CLI arguments only override defaults; none is required.
- `--show-config` (or an equivalent mode) must not build, play, train, delete or change repository state.
- A missing optional prerequisite (Stockfish, CUDA, tablebases, openings) gives a clear diagnostic. Inspection and orchestration scripts do not fail because of it.

## Generic orchestration

- Build, self-play, data generation, labeling, training, export, tournament, benchmark and test orchestration select behavior from an engine profile.
- Use UCI process boundaries for cross-family matches. A generic runner never depends on the NNU3 or NNU4 binary layout.
- Keep raw training data architecture-neutral (position, side to move, result, evaluation, move, provenance). Encode NNUE features only inside the selected trainer.
- Never create version-, match- or round-specific runner scripts (`run_vXXX_vs_vYYY.py`, temporary tournament scripts). Add a new search effort, evaluation mode or tournament feature as an option of a canonical runner.
- Make formats, time controls (`--movetime`, `--depth`, `--nodes`), concurrency, binaries and pairings configurable by CLI argument or top-of-file constant in the canonical scripts: `tests/run_tournament.py`, `tests/run_tournament_quick.py`, `tests/run_selfplay.py`, `experiments/run_experiment.py`.

## Stockfish and scores

- Stockfish is the canonical external teacher and benchmark opponent. Resolve it through `ZCHEZZ_STOCKFISH`, `engine/stockfish/` or PATH.
- Parse every UCI score through `utils/uci_score.py`. Zchezz engines print `score cp` White-relative; standard engines such as Stockfish print it relative to the side to move. Never assume one convention.
- Normalize teacher scores to a documented common point of view before they reach training data.
- Benchmark defaults: `movetime=200 ms`, `Threads=1`, one concurrent game, paired openings with colors reversed, tablebases off unless the test targets them.
- Fixed-node (`go nodes`) runs suit deterministic search-effort or labeling work. They do not replace the movetime protocol as promotion evidence, and neither does a hosted CI timing.

## Datasets

- Every stored `cp` is White-relative, except `eval_cp` in `.bin` shards, which is relative to the side to move. See `docs/datasets.md`.
- Run `python train/labeling/audit_datasets.py` before training on new or changed data. The Colab trainer audits the Drive shards it reads and stops on a failure.
- Withhold untrusted data and checkpoints in a `_quarantine/` directory. Directories that start with `_` are never read by trainers, the catalog or the audit.
- Never mix evaluation targets from different evaluators in one training column without provenance.

## Training checkpoints

- Keep `checkpoints/<profile>/latest.pt` as the resumable checkpoint of every trainable profile.
- Create it from the installed engine weights when no PyTorch checkpoint exists. After each successful run, refresh it atomically from the newest completed checkpoint.
- Reject an architecture mismatch before loading weights.
- Keep installed weights and the importer sufficient to rebuild a resumable checkpoint.
- Do not commit transient optimizer checkpoints unless the user asks for tracked training artifacts.

## Builds and flags

- Local native builds use `-march=native` when the compiler supports it; never force AVX2 on an unsupported CPU. Bare `make -C engine/build` and `-f Makefile.native` build host-optimized `v335` with `ARCH_FLAGS=-march=native`; do not blank it for local performance work.
- Use `make -C engine/build -f Makefile.portable` for distribution, unknown CPUs, CI and regression controls. It writes `zchezz.portable.exe`, separate from the host `zchezz.exe`. The build matrix keeps the `.portable.exe` suffix. Never ship a host-native executable as universal.
- If `-march=native` is unavailable, build portable and record why.
- Compare native performance with both candidates built with the same compiler, `-O3`, `-ffast-math`, `ARCH_FLAGS` and CPU, and record the flags. Never infer speed or Elo from portable CI NPS.
- WebAssembly uses Emscripten `-msimd128`, not `-march=native` or x86 AVX2.

## Tests

- Bare native builds use `ENGINE=v335`. `ENGINE=v510` and `ENGINE=v605` each build independently without changing the default marker. `ENGINE=v328` and `ENGINE=v327` stay available for frozen comparisons.
- Run the deterministic local tests before you call a change complete: perft, UCI smoke, NNUE artifact validation, C invariants and Python contract tests, when their dependencies exist.
- Test `v335`, `v510` and `v605` for changes to build, UCI, dataset, training, checkpoint or profile infrastructure. Test `v327` when a change claims backward compatibility.
- A skipped test is missing evidence, not a pass.
- Keep test evidence under `artifacts/`. A test must not overwrite source files.

## Git and branches

- Do not delete, create, rename, merge, rebase or force-update unrelated branches as a side effect of testing.
- Experiment branches do not depend on workflow files or branch-name patterns. Isolate experimental rounds by branch, output directory or configuration, never by copying workflows.
- Do not auto-promote experimental code to `main`.
- Preserve user work that is unrelated to the request.

## GitHub Actions

- Keep Actions minimal and generic. CI runs on `main` and pull requests, never because a branch name starts with a version prefix.
- `.github/workflows/ci.yml` is read-only: it never writes source, releases or branches.
- `.github/workflows/publish-pages.yml` is the only source-writing exception. After it regenerates v335 WASM and passes the Chromium browser E2E, it may atomically sync `index.html` from `engine/c/zchezz_v335/zchezz_bundle.html` and commit those two web artifacts to `main` (no force push). It never publishes untested WASM, advances `ACTIVE_ENGINE` or merges experimental changes. It requests a Pages rebuild through the REST API, because `GITHUB_TOKEN` pushes do not trigger Pages. Its triggers cover web and build changes only, and generated bundles must not retrigger it.
- Do not add version- or round-specific workflows or widen the write permissions of generic CI.
- Local scripts are the authority for tests and experiments; Actions are optional verification.

## Source and documentation

- Comments are technical, current and conditional: state what must be true and what a caller may rely on. Every module has a docstring and every non-trivial function states its contract.
- Historical source comments may keep the version they document. Current `v335`/`v510` comments do not present an older family as active.
- `AGENTS.md` holds no project history, migration narrative or reason for a past design change.
- `CLAUDE.md` and `AGENTS.md` have identical bodies; only the first title line differs.
- Update comments, tests and docs when a public contract changes.
- Use repository-relative paths in tracked configuration.

## Safety invariants

- Validate engine/profile compatibility before a long run starts.
- Fail before games or training start when an artifact has the wrong magic, dimensions, size or profile.
- Never reinterpret NNU3 data as NNU4 weights or the reverse.
- Keep deterministic seeds, paired openings and test parameters in output metadata.

## Cloud and repository organization

- Keep current Colab code under `colab/` as `colab/layout.json` defines. Read `colab/AGENTS.md` and `colab/README.md` before cloud operations.
- `docs/repository-layout.md` gives source roles and compatibility rules.
- Keep generated reports and environments under the ignored `artifacts/`.
- Preserve frozen snapshots and active experiments during cleanup.
