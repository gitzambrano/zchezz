# Build

The shared build entry point is `engine/build/Makefile`.

## Defaults

```text
ENGINE ?= v325
TOOLS_ENGINE ?= v500
```

`ENGINE` selects the UCI engine build. `TOOLS_ENGINE` selects the native in-process tool host because the current tool API follows the v500/NNU4 family.

## Native engine

Linux/macOS:

```bash
make -C engine/build native
make -C engine/build ENGINE=v325 native
make -C engine/build ENGINE=v500 native
```

Windows:

```bat
mingw32-make -C engine/build native
mingw32-make -C engine/build ENGINE=v325 native
mingw32-make -C engine/build ENGINE=v500 native
```

A bare shared build means v325.

## Tablebases

If both Fathom source and header files are present for the selected profile, native builds may include tablebase support. If the pair is absent, the shared build defines `NO_TABLEBASES`. This allows a clean checkout to compile without local Fathom files.

The normal strength benchmark keeps tablebases disabled so results do not depend on a local TB installation.

## Other targets

```bash
make -C engine/build ENGINE=v325 debug
make -C engine/build ENGINE=v325 sanitize
make -C engine/build ENGINE=v325 test-c
make -C engine/build ENGINE=v325 wasm
make -C engine/build ENGINE=v325 bundle

make -C engine/build ENGINE=v500 debug
make -C engine/build ENGINE=v500 sanitize
make -C engine/build ENGINE=v500 test-c
```

Native in-process data/arena tools use the tool host:

```bash
make -C engine/build selfplay
make -C engine/build arena
make -C engine/build ga_tune
```

Do not use those native tools as a cross-family ABI; use the Python/UCI runners when v325 and v500 must play each other.

## CI portability

CI clears `STATIC_FLAG` and `ARCH_FLAGS` for the smoke builds so hosted runners are not required to support the local production ISA or static runtime. Performance comparisons must use the same compiler/flags on both sides.

## WebAssembly

`wasm` requires Emscripten. `bundle` combines the selected WASM/NNUE payload with the shared HTML template. Web builds disable native tablebase/book file I/O.

## Cleanup

Use the shared `clean` target. Cleanup must remove only generated build artifacts and must not delete datasets, checkpoints, openings, tablebases, external engines, or source files.
