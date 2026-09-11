# Zchezz ♟️

Zchezz is a C11 UCI chess engine with custom NNUE evaluation, native and WebAssembly builds, self-play/training tooling, and a test/benchmark stack designed for reproducible engine work.

▶ **[Play against Zchezz in your browser](https://gitzambrano.github.io/zchezz/)**

The browser build is designed to run fully client-side through WebAssembly. The project can also produce a standalone HTML bundle for offline play, with the engine, NNUE weights and UI packaged together.

## Highlights

| | |
|---|---|
| **Default engine** | `v325` — current released working line |
| **Experimental engine** | `v500` — supported compact NNU4 development line |
| **Search** | iterative-deepening alpha-beta/PVS, aspiration windows, pruning/reductions, staged ordering and Lazy SMP |
| **Evaluation** | custom quantized NNUE with native SIMD and WebAssembly support |
| **Endgames** | Syzygy probing when tablebase support is available |
| **Opening book** | Polyglot book support in native builds |
| **Analysis** | MultiPV and engine-analysis support; browser UI supports interactive play/analysis workflows |
| **Platforms** | Windows, Linux, Android/Termux and WebAssembly in modern browsers |
| **Offline** | standalone bundled HTML can run locally without a server |
| **Protocol** | UCI engine for use with compatible chess GUIs and tooling |

## What you can do

- Play against Zchezz directly in the browser from the GitHub Pages link above.
- Run the native UCI engine from a chess GUI or from the command line.
- Use analysis features such as MultiPV and standard UCI search controls.
- Build a self-contained WebAssembly/HTML version for offline use.
- Generate self-play data, label positions, train NNUE networks and benchmark engine changes with the repository tooling.
- Work with two supported engine/network families without mixing their NNUE formats: v325/NNU3 and v500/NNU4.

## Supported engine profiles

| Profile | Role | Evaluation |
|---|---|---|
| `v325` | default and current released working line | NNU3, 799 inputs, 256 hidden-1, 64 hidden-2 neurons on disk; runtime compacts the 50 non-zero H2 neurons into 52 SIMD slots |
| `v500` | supported secondary experimental line | NNU4 HalfKP-4-Bucket, 2560 inputs per perspective, H1=48, concat=96, H2=20 |

`engine/ACTIVE_ENGINE` is `v325`. Generic scripts resolve these profiles through `utils/engine_profiles.py`; they must not infer the active architecture from a filename or NNUE magic.

Older `v3xx` directories are retained as historical source snapshots. They are not the default orchestration target. The removed v4 family is not a supported line.

## v325 engine architecture

The v325 engine lives in `engine/c/zchezz_v325/` and exposes a standard UCI process in `main.c`.

### Board and state

`board.c` / `board.h` maintain the mailbox, piece bitboards, cached occupancies, king-square state, castling/en-passant state, halfmove counters, move history, Zobrist hash, and the per-board NNUE accumulator pointer. Make/unmake must restore the complete logical position and incremental hash.

### Search

`search.c` / `search.h` implement iterative deepening alpha-beta/negamax with principal-variation search, aspiration windows, quiescence search, static exchange evaluation, transposition-table lookup/storage, move ordering, history/killer/countermove/continuation heuristics, null-move pruning, late-move reductions, futility/SEE-based pruning, Syzygy probing, MultiPV support, time/node limits, and Lazy SMP search threads.

The v325 transposition table uses 32-byte clusters with three compact 10-byte entries plus padding. Hash size is selected through the UCI `Hash` option.

### v325 NNUE

The installed file is `engine/c/zchezz_v325/nnue_weights.bin` and uses NNU3.

The on-disk contract is:

```text
input           799 = 768 half-mirror piece features + 31 endgame features
L1              799 -> 256
L2 file         256 -> 64
L3 file         64 -> 1
quantization    QA=255, QB=64, SHIFT=8
```

At load time the current network has 14 H2 neurons whose quantized L3 weights are exactly zero. The runtime therefore copies the 50 live H2 rows into a compact 52-slot SIMD layout (50 live + 2 zero-padding slots). This is algebraically equivalent to the tracked 64-neuron file; the binary remains NNU3 and remains 426,864 bytes.

Each search thread owns mutable NNUE accumulator state. The 768 half-mirror feature contribution is updated incrementally; the extra endgame features are evaluated through cached projections. PK17-derived passed-pawn/king-distance state is also kept incrementally in the current v325 accumulator.

See `docs/nnue.md` for the exact file/runtime distinction.

### UCI

The v325 executable identifies itself as Zchezz 3.25. Supported options include `Hash`, `Threads`, `NNUE`, `Contempt`, `MoveOverhead`, `MultiPV`, `Ponder`, `UCI_AnalyseMode`, `UCI_Chess960`, Syzygy options, and Polyglot book options. Common `go` modes include depth, movetime, clock controls, nodes, mate, infinite, ponder, and searchmoves.

See `docs/uci.md`.

## v500

`engine/c/zchezz_v500/` is a supported secondary engine used to develop the NNU4 family. It is intentionally separate from v325 at the evaluator/model boundary. Its installed NNU4 is the compact `2560 -> 48 -> [96 concat] -> 20 -> 1` network, 248,020 bytes.

Cross-family matches always use UCI process boundaries. Native in-process tools under `engine/c/tools/` use the v500-compatible API and must not be treated as the abstraction for v325-v500 comparison.

## Build

From the repository root:

```bash
make -C engine/build native                  # default: v325
make -C engine/build ENGINE=v325 native
make -C engine/build ENGINE=v500 native
```

On Windows use `mingw32-make` with the same targets. If the Fathom source/header pair is unavailable the shared Makefile builds with `NO_TABLEBASES` rather than depending on local tablebase source.

See `docs/build.md`.

## Tests

The repository's automatic CI is deliberately small and read-only. Local tests remain the authoritative test surface.

```bash
python tools/check_repo.py
python -m pytest tests/test_agent_instructions.py tests/test_repository_contracts.py tests/test_repo_paths.py tests/test_repo_policy.py tests/test_cliconf.py tests/test_documentation.py -q
make -C engine/build ENGINE=v325 STATIC_FLAG= ARCH_FLAGS= native
make -C engine/build ENGINE=v500 STATIC_FLAG= ARCH_FLAGS= native
python tools/check_nnue.py --profile v325
python tools/check_nnue.py --profile v500
```

For strength work, the standard comparison defaults are 200 ms/move, engine `Threads=1`, one concurrent game, paired openings with colors reversed, and tablebases off unless tablebases are the feature under test. A `go nodes` run is deterministic work-unit evidence; it is not equivalent to movetime strength evidence.

See `docs/testing.md` and `docs/regression-testing.md`.

## Training

Raw data is architecture-neutral. Feature encoding occurs only after selecting a profile.

- `python train/run.py` defaults to v325.
- `python train/run.py --profile v500` selects the NNU4 family.
- `checkpoints/<profile>/latest.pt` is the canonical resumable checkpoint.
- `train/import_nnu3.py` and `train/import_nnu4.py` reconstruct profile checkpoints from installed engine weights.
- `train/export_nnu3.py` / `train/export_nnu4.py` produce architecture-specific binaries.
- `train/teacher.py` provides a Stockfish-based architecture-neutral EPD labeling path.

See `docs/training.md`.

## WebAssembly

The shared build can compile a selected engine to WebAssembly and bundle the engine, NNUE payload and UI into a standalone HTML artifact. Web builds define `NO_TABLEBASES` and `NO_BOOK` for native file-I/O paths.

See `docs/wasm.md`.

## Repository map

See `docs/repository-layout.md` and `docs/folder_structure.md`.

## Author

**Gustavo José Zambrano**
