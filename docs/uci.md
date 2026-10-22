# UCI Interface

The default engine is `engine/c/zchezz_v335/` and identifies itself as Zchezz 3.35.

## Core commands

The engine handles the normal UCI lifecycle: `uci`, `isready`, `ucinewgame`, `setoption`, `position`, `go`, `stop`, `ponderhit` and `quit`, plus diagnostic commands such as `d`, `bench` and evaluation output supported by the current engine.

`go` supports the standard search controls used by the repository runners, including depth, movetime, clock/increment, movestogo, nodes, mate, infinite, ponder and searchmoves.

## Options

The v335 UCI layer exposes at least:

- `Hash`
- `Threads`
- `NNUE`
- `Contempt`
- `MoveOverhead`
- `MultiPV`
- `Ponder`
- `UCI_AnalyseMode`
- `UCI_Chess960`
- `SyzygyPath`
- `SyzygyProbeDepth`
- `SyzygyProbeLimit`
- `Syzygy50MoveRule`
- `OwnBook`
- `BookFile`

Tests, not documentation prose, are authoritative for the exact option inventory: see `tests/data/golden_engine.json`, `tests/test_engine_golden.py` and `tests/test_uci_extended.py`.

## Cross-family use

Treat UCI as the stable boundary between v335, v510, v605, and external engines such as Stockfish. Do not link search or evaluator internals into one generic comparison process.
