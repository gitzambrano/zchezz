# Build

The shared build entry point is `engine/build/Makefile`.

## Defaults

```text
ENGINE ?= v335
TOOLS_ENGINE ?= v510
```

`ENGINE` selects the UCI engine build (`v335` by default). `TOOLS_ENGINE` selects the native in-process tool host because the tool API follows the NNU4 family (`v510` by default). `v510` and `v605` can be built by explicitly passing their profile names. `v328` remains available as the frozen pre-v3.29 NNU3 regression baseline.

## Native engine

Linux/macOS:

```bash
make -C engine/build native
make -C engine/build ENGINE=v335 native
make -C engine/build ENGINE=v510 native
make -C engine/build ENGINE=v605 native
make -C engine/build ENGINE=v328 native
```

Windows (MinGW):

```bat
mingw32-make -C engine/build native
mingw32-make -C engine/build ENGINE=v335 native
mingw32-make -C engine/build ENGINE=v510 native
mingw32-make -C engine/build ENGINE=v605 native
mingw32-make -C engine/build ENGINE=v328 native
```

A bare shared build targets v335.

## Tablebases

If both Fathom source and header files are present for the selected profile, native builds may include tablebase support. If the pair is absent, the shared build defines `NO_TABLEBASES`. This allows a clean checkout to compile without local Fathom files.

The normal strength benchmark keeps tablebases disabled so results do not depend on a local TB installation.

## Other targets

```bash
make -C engine/build ENGINE=v335 debug
make -C engine/build ENGINE=v335 sanitize
make -C engine/build ENGINE=v335 test-c
make -C engine/build ENGINE=v335 wasm
make -C engine/build ENGINE=v335 bundle

make -C engine/build ENGINE=v510 debug
make -C engine/build ENGINE=v510 sanitize
make -C engine/build ENGINE=v510 test-c

make -C engine/build ENGINE=v605 debug
make -C engine/build ENGINE=v605 sanitize
make -C engine/build ENGINE=v605 test-c
```

Native in-process data and arena tools use the v510 tool host:

```bash
make -C engine/build selfplay
make -C engine/build arena
make -C engine/build ga_tune
```

Do not use those native tools as a cross-family ABI. Use the Python/UCI runners when v335, v510, and v605 must play each other. Use `ENGINE=v328` or `ENGINE=v327` only when an explicit frozen-baseline comparison is needed.

## CI portability

CI clears `STATIC_FLAG` and `ARCH_FLAGS` for smoke builds so hosted runners are not required to support the local production ISA or static runtime. Performance comparisons must use the same compiler and flags on both sides.

## WebAssembly

`wasm` requires Emscripten. `bundle` combines the selected WASM/NNUE payload with the shared HTML template. Web builds disable native tablebase and book file I/O.

## Cleanup

Use the shared `clean` target. Cleanup must remove only generated build artifacts and must not delete datasets, checkpoints, openings, tablebases, external engines, or source files.
