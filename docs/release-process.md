# Release Process

A release is an evidence package, not just a successful compile.

## 1. Identify the profile and exact inputs

Record candidate Git SHA/profile, baseline SHA/profile, installed NNUE SHA-256 and relevant local resources. The repository default is v325; v500 remains secondary until explicitly promoted.

## 2. Repository and deterministic checks

At minimum:

```bash
python tools/check_repo.py
python -m pytest tests/test_agent_instructions.py tests/test_repository_contracts.py tests/test_repo_paths.py tests/test_repo_policy.py tests/test_cliconf.py -q
make -C engine/build ENGINE=v325 STATIC_FLAG= ARCH_FLAGS= native
make -C engine/build ENGINE=v500 STATIC_FLAG= ARCH_FLAGS= native
python tools/check_nnue.py --profile v325
python tools/check_nnue.py --profile v500
```

Run additional perft, UCI, C-invariant, sanitizer or web gates relevant to the changed surface. A skipped gate is missing evidence, not a pass.

## 3. Strength evidence

For a strength-affecting candidate, follow `docs/regression-testing.md`. Do not substitute deterministic tests, NPS or fixed-node matches for movetime Elo evidence.

## 4. Web evidence

If browser/WASM delivery changed, build the selected bundle and run the browser/static checks available on the validation platform. State explicitly when Emscripten or browser automation was unavailable.

## 5. Provenance

Retain SHA/profile/network hash, compiler/platform/flags, test summaries and strength artifact references together. A release result without reproducible inputs is incomplete.

## 6. Source immutability

Do not modify historical engine directories to make a new release. New engine behavior belongs in the active supported line or a new explicit profile. Repository-only documentation/infrastructure fixes may be applied without changing historical engine snapshots.

## 7. Promotion

Promotion changes `engine/ACTIVE_ENGINE` and profile/documentation defaults only after the user explicitly requests it and the required correctness + strength evidence exists.
