# Experiments

`experiments/run_experiment.py` is the only experiment runner. An experiment is
a JSON spec in `specs/`; a source change is a patch in `patches/`.

```bash
python experiments/run_experiment.py --list
python experiments/run_experiment.py --spec <id> --show-config   # resolve only
python experiments/run_experiment.py --spec <id> --dry-run       # resolve only
python experiments/run_experiment.py --spec <id>                 # build candidates and play
```

## Spec

```json
{
  "id": "lmr_hist768",
  "description": "v335 with LMR history divisor 768",
  "engine_a": {"label": "cand", "candidate": {"base_profile": "v335", "patch": "experiments/patches/lmr_hist768.diff"}},
  "engine_b": {"label": "v335", "profile": "v335"},
  "build": {"arch_flags": "-march=native"},
  "protocol": {"movetime_ms": 200, "threads": 1, "games": 100, "concurrency": 1, "color_swap": true, "seed": 0}
}
```

- Engine forms: `profile`, `path`, `target: "stockfish"` or `candidate`. Any
  engine may set `label` and `options` (UCI options).
- `id` must equal the file name. Labels must differ.
- Protocol defaults follow the benchmark contract (200 ms, Threads=1, one
  concurrent game, color-reversed pairs). `games` counts openings; each is played
  twice. `nodes` > 0 selects fixed-node search, which is not promotion evidence.
- `seed: 0` draws a fresh seed. The seed actually used is recorded.
- A suite spec `{"id": ..., "suite": [ids]}` runs each member in order.

## Candidate patches

Write patches relative to the base engine directory with `a/` and `b/`
prefixes, for example `git diff --no-index a/search.c b/search.c` from a folder
that holds the two copies. The runner copies the base profile's directory into
the run directory, applies the patch and builds with `engine/build/Makefile`.
Build both sides with the same `arch_flags` before claiming NPS or Elo changes.

## Output

Each run writes `artifacts/experiments/<id>/<UTC timestamp>/` with `spec.json`,
`summary.json`, the PGN and log, and `build/<label>/` for candidates.
`summary.json` records the commit and dirty state, host and compiler, binary
and patch hashes, the protocol with the seed used, W/D/L, and trinomial and
pentanomial Elo. `artifacts/experiments/<id>/latest.json` names the newest run.

Record conclusions in `EXPERIMENTS_HISTORY.md` with the run directory name.
