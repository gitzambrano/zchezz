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
- **Pawn-structure correction history** *(v3.29)* — adjusts static evaluation using a per-pawn-hash correction term, improving positional consistency across similar structures
- **Compact clustered Transposition Table** — 32-byte aligned clusters, each holding three 10-byte entries; supports age-based replacement, hash score correction, and TT-move ordering
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

Zchezz compiles to **WebAssembly** via Emscripten. The browser build embeds the full NNUE weights (~417 KB) and communicates through exported UCI-facing WASM helpers. The browser version runs single-threaded (no Lazy SMP) but uses the same search and evaluation code as the native engine.

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

### Linux / macOS

```bash
make -C engine/build native
# → engine/c/zchezz_v329/zchezz
```

### Windows (MinGW)

```bat
mingw32-make -C engine/build native
:: → engine\c\zchezz_v329\zchezz.exe
```

### With Syzygy tablebase support

Place `tbprobe.c` and `tbprobe.h` (from [Fathom](https://github.com/jdart1/Fathom)) inside `engine/c/zchezz_v329/`. The build system detects them automatically — no flags required.

### WebAssembly

```bash
# Requires Emscripten (emcc on PATH)
make -C engine/build wasm
make -C engine/build bundle    # produces standalone index.html with embedded NNUE
```

---

## Engine families

Zchezz maintains two engine families in parallel:

| Family | Current | Evaluator | Status |
| ------------- | ------- | ------------------------------------------------------------- | ------------------------------------- |
| **3.x** | v3.29 | NNU3 — 799 inputs, 256-neuron L1 | **Official release, ~2900 Elo** |
| **5.x** | v5.06 | NNU4 HalfKP-4-Bucket — 2560 sparse inputs/perspective, H1=48 | Experimental development |

The **3.x family** is the released engine for play and tournaments. The **5.x family** is an experimental line with a richer, bucket-based NNUE architecture under active development. Released binaries are always from the 3.x family unless explicitly labelled otherwise.

For contributor and developer documentation see the [`docs/`](docs/) directory.

---

## Author

**Gustavo José Zambrano**
