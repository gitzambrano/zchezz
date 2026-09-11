# Testing

Zchezz separates repository contracts, deterministic engine correctness and statistical playing strength.

## Minimal automatic CI

`.github/workflows/ci.yml` is intentionally one small read-only smoke job. It performs:

```bash
pip install -e ".[dev]"
python tools/check_repo.py
python -m pytest tests/test_agent_instructions.py tests/test_repository_contracts.py tests/test_repo_paths.py tests/test_repo_policy.py tests/test_cliconf.py -q
make -C engine/build ENGINE=v325 STATIC_FLAG= ARCH_FLAGS= native
make -C engine/build ENGINE=v500 STATIC_FLAG= ARCH_FLAGS= native
python tools/check_nnue.py --profile v325
python tools/check_nnue.py --profile v500
```

CI does not commit/push, train networks, play long tournaments, publish releases, run heavyweight browser setup or mutate branches.

## Local tests

Local execution is authoritative for deeper validation. Relevant checks include:

- `engine/c/tests/test_engine_invariants.c` through `make ... test-c`;
- `tests/test_perft.py` for legal move generation/make-unmake;
- `tests/test_uci.py` / `tests/test_uci_extended.py` for protocol behavior;
- `tests/test_engine_golden.py` for stable externally visible UCI contracts;
- `tests/test_nnue_accumulator.py` and profile-specific NNUE checks;
- WebAssembly/static/browser checks when Emscripten/browser dependencies exist;
- self-play/tournament/benchmark runners for game-level evidence.

## Default profile

Public orchestration defaults to v325. Use explicit `--profile v500` or `ENGINE=v500` only when the v500 family is the intended subject.

## Result semantics

- **PASS**: the command actually ran and succeeded.
- **FAIL**: the command ran and violated a required assertion.
- **SKIP**: a prerequisite was unavailable; this is missing evidence, not success.

## Strength

The normal promotion protocol is 200 ms/move, `Threads=1`, concurrency 1, paired color-swapped openings and tablebases off. See `docs/regression-testing.md`.

A fixed-node search is useful deterministic evidence but is not equivalent to movetime playing strength.

## Bare-run behavior

Public scripts are intended to have safe no-argument behavior. `--show-config` must inspect configuration without starting builds, games or training.
