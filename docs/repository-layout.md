# Repository Layout

```text
.github/workflows/       one minimal read-only CI workflow
engine/ACTIVE_ENGINE     default profile marker (`v326`)
engine/build/            shared build + WebAssembly/bundle infrastructure
engine/c/zchezz_v326/    default released engine; NNU3
engine/c/zchezz_v325/    frozen NNU3 regression/comparison baseline
engine/c/zchezz_v500/    secondary supported engine; NNU4
engine/c/zchezz_v3xx/    retained historical v3 snapshots
engine/c/tools/          native v500-host self-play/arena/GA tooling
engine/c/tests/          C invariant harness
train/                   architecture-neutral data + family-specific NNUE code
tests/                   correctness/UCI/game/benchmark harnesses
tools/                   repository checks and historical migration utilities
utils/engine_profiles.py canonical profile + Stockfish resolution
utils/cliconf.py         small optional-override helper
artifacts/               generated test/evidence output
```

Operational entry points must work with no required CLI arguments and default safely to v326 unless the file is explicitly family-specific. `v325` remains selectable only for explicit frozen-baseline work. Cross-family orchestration selects a profile and uses UCI process boundaries; `v500` remains the supported NNU4 line.
