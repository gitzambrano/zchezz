# Repository Layout

```text
.github/workflows/       one minimal read-only CI workflow
engine/ACTIVE_ENGINE     default profile marker (`v331`)
engine/build/            shared build + WebAssembly/bundle infrastructure
engine/c/zchezz_v332/    default released engine; NNU3
engine/c/zchezz_v331/    previous released engine; NNU3
engine/c/zchezz_v328/    frozen NNU3 regression/comparison baseline (pre-v3.29)
engine/c/zchezz_v327/    frozen NNU3 regression/comparison baseline
engine/c/zchezz_v508/    secondary supported engine; NNU4
engine/c/zchezz_v507/    previous secondary engine; NNU4
engine/c/zchezz_v3xx/    retained historical v3 snapshots
engine/c/tools/          native v508-host self-play/arena/GA tooling
engine/c/tests/          C invariant harness
train/                   architecture-neutral data + family-specific NNUE code
tests/                   correctness/UCI/game/benchmark harnesses
tools/                   repository checks and historical migration utilities
utils/engine_profiles.py canonical profile + Stockfish resolution
utils/cliconf.py         small optional-override helper
artifacts/               generated test/evidence output
```

Operational entry points must work with no required CLI arguments and default safely to v332 unless the file is explicitly family-specific. `v328` and `v327` remain selectable only for explicit frozen-baseline regression work. Cross-family orchestration selects a profile and uses UCI process boundaries; `v507` remains the supported NNU4 line.

## Colab organization

All current cloud implementations reside under `colab/`.
Both Zchezz and Zquoridor use the same directory roles:

```text
colab/
  cli/                    terminal commands and artifact monitoring
  playwright/             reusable browser commands and monitoring
    diagnostics/          targeted historical inspection and repair scripts
  remote/                 implementations that execute inside a runtime
  notebooks/              notebook entry points
  config.py               public account slots and workload settings
  private.py              external local identity configuration
  layout.json             directory roles and compatibility map
```

The root Colab shell files forward to `remote/` for compatibility with existing
notebooks. They contain no training or self-play implementation. The shared
profile resolver selects the repository default for a bare remote run.
An explicit secondary profile remains available through the same interface.

Keep generated reports, local environments, and caches under `artifacts/`.
Keep transient scratch files under ignored `scratch/` rather than the repository
root. Existing engine and training experiments retain their current paths.
Frozen engine snapshots and agent configuration copies are intentional copies.
Their matching bytes do not authorize deletion.

Run `python tools/audit_repository.py` for source layout and duplicate classification.
Run `python -m colab.privacy_check` before staging cloud changes.
The source audit preserves historical copies and does not delete files.
Both reports exclude ignored local artifacts and Git history.
