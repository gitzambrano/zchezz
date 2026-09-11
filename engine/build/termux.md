# Zchezz on Termux

The repository default engine is v325. Termux builds should use the shared build entry point rather than assuming a historical version directory.

## Native build

From the repository root:

```bash
pkg update
pkg install git clang make python
make -C engine/build ENGINE=v325 STATIC_FLAG= ARCH_FLAGS= native
```

To build the supported secondary profile:

```bash
make -C engine/build ENGINE=v500 STATIC_FLAG= ARCH_FLAGS= native
```

`STATIC_FLAG=` and `ARCH_FLAGS=` are useful on Android because desktop-specific static/ISA defaults may not match the device toolchain.

## NNUE

The selected engine expects the network in its own engine directory:

- v325: NNU3, `engine/c/zchezz_v325/nnue_weights.bin`;
- v500: NNU4, `engine/c/zchezz_v500/nnue_weights.bin`.

Use `python tools/check_nnue.py --profile v325` or `--profile v500` before diagnosing an engine startup issue as a compiler problem.

## Tests

Run repository/Python checks that are practical on the device and at minimum verify the engine reaches UCI `uciok`/`readyok`. Do not compare Termux NPS directly with desktop CI unless compiler, architecture flags and hardware are controlled.
