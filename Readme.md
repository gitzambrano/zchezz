# Zchezz ♟️

**Zchezz** is an original UCI chess engine written from scratch in C11, featuring a custom-trained NNUE neural network evaluator, multi-threaded search, Syzygy endgame tablebases, and a WebAssembly build that runs entirely in the browser. It plays at approximately **2900 Elo** strength.

Zchezz was vibe-coded using **Claude**, **Gemini**, and **Codex** — a fully AI-assisted development experiment, from the engine core to the neural network training pipeline.

🌐 **[Play against Zchezz in your browser — no install needed](https://gitzambrano.github.io/zchezz/)**

---

## Download and play

### Using a chess GUI (recommended)

Zchezz works with any UCI-compatible chess GUI: [Arena](http://www.playwitharena.de/), [CuteChess](https://cutechess.com/), [Banksia](https://banksiagui.com/), [Scid vs. PC](https://scidvspc.sourceforge.net/), [ChessBase](https://www.chessbase.com/), and others.

1. Download the latest `zchezz.exe` from the [Releases](https://github.com/gitzambrano/zchezz/releases) page.
2. In your GUI, add a new engine and point it to `zchezz.exe`.
3. Start a game — no extra configuration needed.

### Play in the browser

No installation required. Open **[gitzambrano.github.io/zchezz](https://gitzambrano.github.io/zchezz/)** and play directly against the engine, powered by a WebAssembly build with the full NNUE network embedded.

---

## Features

### Search

Zchezz implements a mature alpha-beta search stack:

- **Iterative deepening** with aspiration windows for efficient time use
- **Principal Variation Search (PVS)** — full-window search on the first child, zero-window on the rest
- **Quiescence search** with delta pruning, stopping the horizon effect on tactical positions
- **Static Exchange Evaluation (SEE)** — accurate capture sequence evaluation used in move ordering and pruning
- **Late Move Reductions (LMR)** — reduces search depth on moves unlikely to be best, based on move history feedback
- **Null-move pruning** — forward pruning when the position is strong enough to pass a move
- **Futility pruning** — prunes losing moves near the leaves using static evaluation margins
- **SEE-based pruning** — drops losing captures and quiet moves that SEE predicts to fail badly
- **Refined Reverse Futility Pruning (RFP)** *(v3.33, v5.09, v6.03)* — tightens the fail-high margin (`75 * depth - (improving ? 40 : 0)`) and extends depth cutoff to $d \le 10$, safely pruning settled branches to allocate node budget to deeply contested lines (+12.2 Elo H2H, record 108 wins against Stockfish 2900)
- **Dual-NNUE Auxiliary Fast Head** *(v3.35, v6.05)* — evaluates hidden-layer activations using an auxiliary linear head for early branch pruning before full evaluation
- **Quiet SEE depth extension** *(v3.35)* — extends static exchange pruning on quiet moves up to depth 6, reducing unpromising branch growth
- **Stockfish Gravity Move Ordering** *(v3.32, v5.08, v6.02)* — applies gravity decay to quiet move history with quadratic cutoff bonuses
- **Pawn-structure correction history** *(v3.29)* — adjusts static evaluation using a per-pawn-hash correction term, improving positional consistency across similar structures
- **Compact clustered Transposition Table** — 32-byte aligned clusters, each holding three 10-byte entries; supports age-based replacement, hash score correction, and TT-move ordering
- **TT-move pseudo-legality validation** *(v3.30)* — rejects stale or colliding compact-TT moves whose geometry or special-move fields are impossible in the current position before they reach make/unmake
- **Move ordering**: TT move → winning captures (MVV-LVA + SEE) → killer moves → counter moves → quiet history → losing captures
- **MultiPV** — analyse multiple lines simultaneously (up to 6)
- **Lazy SMP** — multi-threaded parallel search with per-thread private search state and NNUE accumulators; no shared mutable state between helpers

### NNUE Evaluation

Zchezz uses a fully custom-trained **NNU3** neural network (released engine, 3.x family):

```
Architecture:   NNU3 (custom half-mirror + endgame extension)
Input layer:    799 features
                └─ 768 half-mirror piece features  (12 piece types × 64 squares)
                └─ 31 endgame features             (passed pawns, king distance, etc.)
Hidden layer 1: 799 → 256 neurons  (ClippedReLU)
Hidden layer 2: 256 → 64 neurons
Output layer:   64 → 1 scalar (centipawn score)
File size:      426,864 bytes
Quantisation:   int16 (L1 weights), int8 (L2/L3), QA=255, QB=64, SHIFT=8
```

**Runtime compaction:** 14 of the 64 H2 neurons have zero quantised L3 weights. The loader eliminates them at startup, compacting the runtime to 52 SIMD slots (50 live + 2 padding). This reduces dot-product work without changing the on-disk file format.

**Incremental accumulator:** The half-mirror L1 accumulator is updated incrementally on every make/unmake move — only the features that change (piece additions and removals) are recalculated. Passed-pawn and king-distance state (PK17) is also maintained incrementally. Each search thread has its own `NnueAccum`, so Lazy SMP threads never share mutable evaluation state.

The network was trained on positions labeled by Stockfish and also through direct selfplay.

### Endgame Tablebases

Syzygy tablebase probing via [Fathom](https://github.com/jdart1/Fathom), supporting up to **7-piece tablebases**. When enabled:

- TT probe happens before TB probe — cached TB scores are served from the TT on revisits, eliminating redundant disk I/O
- TB results are stored in the TT at `depth=127` for fast retrieval
- Probing is skipped at PV nodes (following Stockfish convention) so full search depth is preserved for principal variation accuracy

### Opening Book

Built-in **Polyglot** (`.bin`) opening book support. Load your own book via `BookFile` UCI option, or activate the built-in book with `OwnBook = true`.

### WebAssembly

Zchezz compiles to **WebAssembly** via Emscripten. The browser build embeds the full NNUE weights (~417 KB) and communicates through exported UCI-facing WASM helpers. The browser version runs single-threaded (no Lazy SMP) but uses the same search and evaluation code as the native engine version from which that published bundle was built.

---

## UCI options

| Option | Type | Default | Description |
| -------------------- | ------ | ------- | --------------------------------------------------------------------- |
| `Hash` | spin | 64 MB | Transposition table size (1–1024 MB). Larger = better in long games. |
| `Threads` | spin | 1 | Search threads via Lazy SMP (1–128). |
| `MultiPV` | spin | 1 | Number of alternative lines to show (1–6). Useful for analysis. |
| `Contempt` | spin | 15 | Draw avoidance offset in centipawns (−100 to +100). |
| `MoveOverhead` | spin | 50 ms | Clock safety buffer for move management. |
| `Ponder` | check | false | Think on opponent's time. |
| `UCI_AnalyseMode` | check | false | Optimise for analysis rather than game play. |
| `UCI_Chess960` | check | false | Enable Chess960 (Fischer Random) castling rules. |
| `OwnBook` | check | false | Use the built-in Polyglot opening book. |
| `BookFile` | string | — | Path to an external Polyglot`.bin` book file. |
| `SyzygyPath` | string | — | Path to Syzygy tablebase files. |
| `SyzygyProbeDepth` | spin | 1 | Minimum depth to start probing tablebases. |
| `SyzygyProbeLimit` | spin | 6 | Maximum piece count for tablebase probing (0–7). |
| `Syzygy50MoveRule` | check | true | Respect the 50-move rule in tablebase probes. |
| `NNUE` | string | — | Override the NNUE weights path (uses built-in network by default). |

### Recommended settings for play

```
Hash      = 256
Threads   = 4        # match your CPU core count
OwnBook   = true
```

### Recommended settings for analysis

```
Hash             = 512
Threads          = 8
MultiPV          = 3
UCI_AnalyseMode  = true
Contempt         = 0
```

---

## Build from source

**Prerequisites:** GCC (MinGW-W64 on Windows, system GCC on Linux/macOS), GNU Make.

### Local native-optimized build (recommended for your own CPU)

**Always use `-march=native` when the compiler and local CPU support it.** The
default Makefile and the explicit `Makefile.native` do this automatically.
On an AVX2-capable CPU, `-march=native` enables AVX2 (plus other supported
instructions); do **not** add `-mavx2` on CPUs without AVX2.

```bash
make -C engine/build                           # default: v335, -O3 -ffast-math -march=native
make -C engine/build -f Makefile.native         # explicit host-optimized build
make -C engine/build -f Makefile.native native-active     # v335, v510, v605
make -C engine/build -f Makefile.native native-supported  # all 23 profiles
make -C engine/c/zchezz_v335                    # same optimized shared default
```

Host-native binaries are `engine/c/zchezz_<profile>/zchezz.exe` (a Linux ELF
on Linux despite the historical extension). **They are not universally portable.**
If `-march=native` is unsupported by the selected toolchain, use the portable
Makefile, rather than silently changing native build flags.

### Portable / distribution build (separate Makefile and executable)

```bash
make -C engine/build -f Makefile.portable
make -C engine/build -f Makefile.portable native-active
make -C engine/build -f Makefile.portable native-supported
```

The portable Makefile uses `-O3 -ffast-math` with **no `-march=native` and
no forced AVX2**, producing `zchezz.portable.exe`, distinct from `zchezz.exe`.
Distribute that binary for compatible OS/ABI and baseline ISA; provide separate
AVX2-specific builds only with explicit CPU compatibility. For an explicitly
AVX2-targeted, machine-specific test use
`ARCH_FLAGS="-march=native -mavx2"` **only** on a verified AVX2 machine.

### Windows (MinGW)

```bat
mingw32-make -C engine/build -f Makefile.native
mingw32-make -C engine/build -f Makefile.portable
```

### With Syzygy tablebase support

Place `tbprobe.c` and `tbprobe.h` (from [Fathom](https://github.com/jdart1/Fathom)) inside `engine/c/zchezz_v335/`. The build system detects them automatically — no flags required.

### WebAssembly

```bash
# Requires Emscripten (emcc on PATH)
make -C engine/build wasm
make -C engine/build bundle           # produces engine/c/zchezz_v335/zchezz_bundle.html
make -C engine/build bundle-active    # bundles v335, v510 and v605
# After Chromium E2E is successful, sync the versioned bundle with Pages index:
python tools/publish_web.py --mode sync   # copies v335 bundle to index.html
```

The dedicated `.github/workflows/publish-pages.yml` rebuilds v335 using
Emscripten SIMD128, verifies static bundle/book and real Chromium browser
behavior, then synchronizes **both** the versioned bundle and root `index.html`
on `main`. GitHub Pages must be configured to serve `main` from `/(root)`.
Generic CI is read-only; the publisher is the only narrowly scoped exception.
WASM uses `-msimd128`, not native CPU `-march=native` or x86 AVX2.

---

## Engine families and baselines

Zchezz maintains three active engine families, each with its own evaluation architecture and baseline champion:

| Family | Current Baseline | Evaluator Architecture | Memory Footprint | Speed & Depth | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **3.x** | **v335 (v3.35)** | NNU3 (799 inputs, 256-neuron L1, 52 SIMD slots) | ~427 KB weights | ~1.1M NPS, depth 16+ | **Official release champion, ~2900 Elo** |
| **5.x** | **v510 (v5.10)** | NNU4 HalfKP-4-Bucket (2560 sparse inputs/perspective) | ~248 KB weights | ~1.4M NPS, depth 16+ | Supported secondary line |
| **6.x** | **v605 (v6.05)** | NNU5 HalfKAv2-32-Bucket (22528 sparse inputs/perspective) | ~11.5 MB weights | ~1.6M NPS, depth 16.8 | Supported secondary line |
| **3.x** | v334 (v3.34) | NNU3 (799 inputs, 256-neuron L1) | ~427 KB weights | ~1.0M NPS | Supported comparison baseline |
| **5.x** | v509 (v5.09) | NNU4 HalfKP-4-Bucket (2560 sparse inputs/perspective) | ~248 KB weights | ~1.4M NPS | Supported comparison baseline |
| **6.x** | v604 (v6.04) | NNU5 HalfKAv2-32-Bucket (256 neurons) | ~11.5 MB weights | ~1.5M NPS | Supported comparison baseline |
| **3.x** | v328 (v3.28) | NNU3 (pre-v3.29 historical state) | ~427 KB weights | ~0.9M NPS | Frozen comparison baseline |

### Baseline explanations

#### 1. Official release champion: v335 (3.x line)
- **Role:** The official tournament engine, repository default (`engine/ACTIVE_ENGINE`), and WebAssembly build target.
- **Evaluator:** NNU3 architecture with 799 features (768 half-mirror piece squares and 31 endgame features), a 256-neuron first hidden layer, and runtime compaction to 52 SIMD slots through dead-neuron elimination.
- **Search stack:** Features a Dual-NNUE auxiliary fast head for rapid evaluation, Quiet SEE pruning extended to depth 6, dynamic Reverse Futility Pruning (RFP) with improving flag adaptation, 32-byte cache-aligned compact Transposition Table with pseudo-legality filtering, and Stockfish gravity move ordering.
- **Performance:** Balances high tactical accuracy and compact footprint, achieving ~2900 Elo strength and winning against Stockfish 2900 with a record 108 wins.

#### 2. Supported secondary line: v510 (5.x line)
- **Role:** The supported low-footprint secondary line designed for memory-constrained and fast-eval environments.
- **Evaluator:** NNU4 HalfKP-4-Bucket architecture with 2560 sparse inputs per perspective, 48 hidden neurons per perspective concatenated to 96 `[stm, opp]`, 20 neurons in H2, and a scalar output (~248 KB weights).
- **Search stack:** Incorporates Quiet SEE pruning to depth 5, Continuous Smooth History LMR, TT prefetch cache optimizations, and validated UCI pondering.
- **Performance:** Provides rapid evaluation throughput with minimal memory requirements.

#### 3. Supported secondary line: v605 (6.x line)
- **Role:** The high-capacity secondary line representing the deep HalfKAv2 32-bucket architecture.
- **Evaluator:** NNU5 architecture with 22,528 sparse inputs per perspective, 256 hidden neurons with SCReLU activation, and 64 neurons in layer 2. Retrained for 20 deep epochs on GPU across 300M+ positions (validation loss 0.507), scoring +107.5 Elo over v604.
- **Search stack:** Features a Dual-NNUE Fast Auxiliary Head calibrated via GPU Ridge regression ($r = 0.7093$), fixed king-bucket invalidation logic, AVX2 vectorized accumulator refresh, staged move generation, and compact sf32 Transposition Table.
- **Performance:** Achieves search throughput exceeding 1.6M NPS and an average depth of 16.8 plies at 100 ms movetime.

#### 4. Baseline hierarchy and comparison roles
- **Default resolution:** All repository scripts, test runners, and bare builds resolve `v335` by default without required command-line arguments.
- **Active family baselines:** `v510` and `v605` are the active reference baselines for their respective architecture families.
- **Frozen comparison baselines:** Older milestone versions (`v334`, `v333`, `v332`, `v331`, `v328`, `v327` in 3.x; `v509`, `v508`, `v507` in 5.x; `v604`, `v603`, `v602`, `v601` in 6.x) remain permanently frozen to guarantee reproducible regression testing.

The **3.x family** is the released working engine for play and tournaments with **v335 (v3.35)** as repository default. The **5.x family** (`v510`) is a supported secondary line based on NNU4 HalfKP-4-Bucket. The **6.x family** (`v605`) is a supported secondary line representing NNU5 (HalfKAv2 32-Bucket with AVX2 SCReLU). Released binaries are always from the 3.x family unless explicitly labelled otherwise.

For contributor and developer documentation see the [`docs/`](docs/) directory.

---

## Author

**Gustavo José Zambrano**

## Repository organization and Colab operations

See [repository layout](docs/repository-layout.md) for source roles and
[Colab operations](colab/README.md) for the CLI and browser transports.
All seven accounts use private local identity configuration. Source organization
and privacy checks are available through `tools/audit_repository.py` and
`python -m colab.privacy_check`.
