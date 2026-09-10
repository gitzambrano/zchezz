# Repository Layout

```text
.github/workflows/       one minimal read-only CI workflow
engine/ACTIVE_ENGINE     default profile marker (`v325`)
engine/c/zchezz_v3xx/    supported/current and retained v3-family sources
engine/c/zchezz_v500/    supported secondary v5 source
engine/c/tools/          native in-process tools
engine/build/            shared build entrypoint
train/                   architecture-neutral data plus family-specific trainers/exporters
utils/engine_profiles.py canonical profile and Stockfish resolution
utils/cliconf.py         small optional CLI override helper
tests/                   local correctness and benchmark harnesses
artifacts/               generated evidence
```

Operational scripts must work without command-line arguments. Optional flags only override in-file defaults. Cross-family orchestration selects a profile rather than importing a network binary layout directly.
