# Zchezz on Termux

The repository default engine is v328. Termux builds should use the shared build entry point rather than assuming a historical version directory. `v325` remains available only as the frozen NNU3 comparison baseline.

## Native build

From the repository root:

```bash
pkg update
pkg install git clang make python
make -C engine/build ENGINE=v328 STATIC_FLAG= ARCH_FLAGS= native
```

To build the frozen baseline or supported secondary profile:

```bash
make -C engine/build ENGINE=v325 STATIC_FLAG= ARCH_FLAGS= native
make -C engine/build ENGINE=v506 STATIC_FLAG= ARCH_FLAGS= native
```

`STATIC_FLAG=` and `ARCH_FLAGS=` are useful on Android because desktop-specific static/ISA defaults may not match the device toolchain.

## NNUE

The selected engine expects the network in its own engine directory:

- v328: NNU3, `engine/c/zchezz_v328/nnue_weights.bin`;
- v325: frozen NNU3 baseline, `engine/c/zchezz_v325/nnue_weights.bin`;
- v506: NNU4, `engine/c/zchezz_v506/nnue_weights.bin`.

Use `python tools/check_nnue.py --profile v328`, `--profile v325`, or `--profile v506` before diagnosing an engine startup issue as a compiler problem.

## Tests

Run repository/Python checks that are practical on the device and at minimum verify the engine reaches UCI `uciok`/`readyok`. Do not compare Termux NPS directly with desktop CI unless compiler, architecture flags, and hardware are controlled.
