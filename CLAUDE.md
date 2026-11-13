# Zchezz Development Instructions

# Supported engine profiles

- Treat `v335` as the repository default and released working line (NNU3).
- Keep `v334`, `v333`, `v332`, `v331`, `v328` and `v327` available as frozen NNU3 regression/comparison baselines; do not retarget them with current-release changes.
- Treat `v510` as a supported secondary line (NNU4); `v509`, `v508` and `v507` remain available comparison baselines.
- Treat `v605` as the supported secondary line representing the NNU5 family (256 neurons, HalfKAv2 32-bucket); `v604`, `v603`, `v602` and `v601` remain available comparison baselines.
- Keep `engine/ACTIVE_ENGINE` equal to `v335` unless the user explicitly requests a promotion.
- Maintain the three active lineages (3xx, 5xx, and 60x) documented and accessible via their profile definitions.
- Do not create or restore `engine/c/zchezz_v4xx` directories.
- Resolve supported families through `utils/engine_profiles.py`; do not hard-code profile selection in orchestration scripts.
- Keep NNU3, NNU4, and NNU5 model, encoder, exporter, importer, and runtime code separate behind the profile interface.
- Treat `v314` through `v327` and version-named migration utilities as historical snapshots; `v328` and `v327` may remain selectable only for explicit regression and comparison work.

## Bare-run contract

- Every public operational script must run with no command-line arguments.
- A bare run must select `v335` unless the script is a family-specific implementation module whose profile is explicit in its file name.
- Optional CLI arguments may override defaults; they must not be required for normal execution.
- `--show-config` or an equivalent non-destructive inspection mode must not build engines, start games, train, delete files, or change repository state.
- Missing optional external prerequisites must produce a clear diagnostic. Scripts intended for inspection or orchestration must not fail merely because Stockfish, CUDA, tablebases, or an opening corpus is absent.

## Generic orchestration

- Build, self-play, data generation, teacher labeling, training orchestration, export orchestration, tournaments, benchmarks, and test orchestration must select behavior from an engine profile.
- Keep raw training data architecture-neutral. Store positions, side to move, game result, evaluation, move, and provenance; encode NNUE features only inside the selected trainer.
- Use UCI process boundaries for cross-family matches and generic engine-vs-engine tooling.
- Do not make a generic runner depend on NNU3 or NNU4 binary layout.
- Do not duplicate runners for individual versions or experimental rounds. Never create ad-hoc, version-specific, match-specific, or round-specific Python runner scripts (e.g., `run_vXXX_vs_vYYY.py` or temporary tournament scripts).
- Keep operational and test runners general and parameter-driven. All tournament formats, time controls (e.g. `--movetime`, `--depth`, `--nodes`), concurrency levels, engine binaries, and profile pairings must be configurable via CLI arguments or top-of-file constants in existing canonical scripts (`tests/run_tournament.py`, `tests/run_tournament_quick.py`, `tests/run_selfplay.py`, `experiments/run_experiment.py`).
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

## Architecture flags and reproducible builds

- **Always prefer `-march=native` for local native builds when the host compiler supports it.** This automatically enables AVX2 and other supported instructions on CPUs that implement them; never force AVX2 on an unsupported CPU.
- The bare `make -C engine/build` and explicit `-f Makefile.native` select a host-optimized v335 build using `ARCH_FLAGS=-march=native` by default. Do not silently override it with blank `ARCH_FLAGS` for local performance work.
- Use `make -C engine/build -f Makefile.portable` when building for distribution, heterogeneous machines, unknown CPUs, CI portability or regression controls. Its `ARCH_FLAGS` is empty and its output is `zchezz.portable.exe`, separate from host `zchezz.exe`.
- The shared build matrix supports the same two flavors for all supported profiles; preserve the `.portable.exe` suffix in portable multi-engine builds.
- For native performance comparisons compile BOTH candidates with the same compiler, `-O3`, `-ffast-math`, `ARCH_FLAGS` and CPU; record compiler/host flags. Do not infer CPU speed gains or Elo from portable CI NPS.
- When `-march=native` is unavailable, use the portable flavor explicitly and record why. Never ship a host-native executable as universally compatible.
- WebAssembly uses Emscripten `-msimd128`, not `-march=native` or x86 AVX2; retain this separation.

## Builds and tests

- Bare native builds use `ENGINE=v335`.
- `ENGINE=v328` and `ENGINE=v327` remain available for frozen regression comparisons.
- `ENGINE=v510` must build independently without changing the default marker.
- `ENGINE=v605` must build independently without changing the default marker.
- Run deterministic local tests before considering a change complete.
- Test `v335`, `v510`, and `v605` for changes to shared build, UCI, dataset, training, checkpoint, or profile infrastructure; test `v327` when a change claims backward compatibility with the frozen NNU3 baseline.
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
- Generic CI (`.github/workflows/ci.yml`) remains read-only and never writes source, releases or branches.
- The specifically authorized `.github/workflows/publish-pages.yml` is the **only** source-writing exception: after regenerating v335 WASM and passing real Chromium browser E2E, it may atomically synchronize `index.html` from `engine/c/zchezz_v335/zchezz_bundle.html` and commit just these two web artifacts to `main` (no force pushes).
- The Pages publisher must never publish untested WASM, advance `ACTIVE_ENGINE`, or merge experimental changes. Request a Pages rebuild via the Pages REST API after a bot-authored commit because `GITHUB_TOKEN` pushes do not trigger Pages. Set its triggers to relevant web/build changes only; prevent self-trigger loops from generated bundles.
- Do not create version-specific or round-specific workflow files or broaden write permissions in generic CI.
- Local scripts remain the authoritative way to run tests and experiments; Actions are optional verification.

## Source and documentation

- Keep comments technical, current, and conditional. State what must be true and what a caller may rely on.
- Historical source comments may retain the version they document; current `v335`/`v510` comments must not present an older family as the active implementation.
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
