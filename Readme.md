# Zchezz ♟️

Zchezz is a C11 UCI chess engine with custom NNUE evaluation, native and WebAssembly builds, self-play/training tooling, and reproducible strength testing.

▶ **[Play against Zchezz in your browser](https://gitzambrano.github.io/zchezz/)**

## Current engines

| Profile | Role | Evaluation |
|---|---|---|
| `v328` | **official/default engine** | NNU3 |
| `v327` | retained previous 3.x baseline for regression work | NNU3 |
| `v506` | current 5.x/NNU4 development family | NNU4 HalfKP-4-Bucket |
| `v505` | retained previous 5.x baseline for regression work | NNU4 |

`engine/ACTIVE_ENGINE` is `v328`. Generic orchestration resolves profiles through `utils/engine_profiles.py`. The 3.x and 5.x families remain separate: v3.28 evolves v3.27; v5.06 evolves v5.05.

## v3.28 official line

The official engine lives in `engine/c/zchezz_v328/`. It carries the validated v3.27 NNU3 network and search line plus the final search-correctness fixes for exact check detection across pruning gates. The release gate against v3.27 used paired UHO openings at 200 ms/move, `Threads=1`, Hash 64 MB and tablebases disabled: 28 wins, 50 draws and 22 losses (53.0%, about +20.9 Elo), with no abnormal termination.

## v5.06 NNU4 line

The current NNU4 line lives in `engine/c/zchezz_v506/`. It evolves v5.05 and uses exact pre-move check detection in quiet SEE/futility pruning. Its 100-game release gate against v5.05 finished 29-44-27 (51.0%, about +6.9 Elo) under the same protocol, with no abnormal termination.

## Build

```bash
make -C engine/build native                  # default: v328
make -C engine/build ENGINE=v328 native
make -C engine/build ENGINE=v506 native
```

The native in-process tools default to `TOOLS_ENGINE=v506` because they require the NNU4 per-instance API. Cross-family comparisons use UCI process boundaries.

## WebAssembly

The browser build comes from the official 3.x engine by default:

```bash
make -C engine/build wasm                    # v328
make -C engine/build bundle                  # standalone v328 HTML bundle
```

`index.html` is the tested standalone v3.28 bundle published by GitHub Pages. On Windows, `engine/build/build_wasm.bat` resolves `engine/ACTIVE_ENGINE`, tests the web profile against its previous version, and promotes the tested bundle to `index.html`.

## Tests

```bash
python tools/check_repo.py
python -m pytest tests/test_repository_contracts.py tests/test_repo_paths.py tests/test_repo_policy.py -q
make -C engine/build ENGINE=v328 STATIC_FLAG= ARCH_FLAGS= native
make -C engine/build ENGINE=v506 STATIC_FLAG= ARCH_FLAGS= native
python tools/check_nnue.py --profile v328
python tools/check_nnue.py --profile v506
```

For strength work, the standard protocol is 200 ms/move, engine `Threads=1`, one concurrent game per runner, paired openings with colors reversed, Hash 64 MB, and tablebases off unless tablebases are the feature under test.

## Training and documentation

Raw training data is architecture-neutral. NNU3 and NNU4 import/export paths remain architecture-specific. `python train/run.py` defaults to v3.28 through `DEFAULT_PROFILE`; use `--profile` for a retained comparison profile.

See `docs/build.md`, `docs/testing.md`, `docs/nnue.md`, `docs/wasm.md`, `docs/repository-layout.md`, and `docs/release-process.md`.

## Author

**Gustavo José Zambrano**
