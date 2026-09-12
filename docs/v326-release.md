# Zchezz v3.26

Zchezz v3.26 promotes the validated search-selectivity work from the v3.25 line. It keeps the same NNU3 evaluator, NNUE weights, board representation, compact TT32 layout, UCI surface, and general search architecture. The release changes only search selectivity.

## Search changes

Relative to v3.25:

- Remove the blanket `depth++` applied to every in-check alpha-beta node. Check evasions are still searched normally, and quiescence handles in-check horizon nodes.
- Retune shallow quiet history pruning from the effectively unreachable `-4000 * depth` threshold to `-64 * depth`.
- Retune quiet LMR history feedback from `-4000/-8000/+4000` to `-512/-1024/+512`, so measured history information actually affects reductions.

No singular-extension repair, null-move retune, qsearch experiment, or stale-TT policy change is included in this release.

## Strength evidence

The release candidate was tested against the original v3.25 under the repository promotion protocol:

- 800 games
- 200 ms/move
- engine `Threads=1`
- one concurrent game
- Hash 64 MB
- tablebases disabled
- OwnBook disabled
- MultiPV 1
- Ponder disabled
- paired UHO openings with colors reversed
- maximum 400 plies

Candidate result, from the v3.26 perspective:

```text
W-D-L   249-346-205
Score   52.750%
Elo     +19.13 ± 18.14  (approx. 95% CI)
```

The nominal 95% interval is therefore slightly above zero. Correctness checks passed before the match.

## Search efficiency

On the fixed-depth 20-position structural suite, the no-check + history-pruning base reduced depth-12 work from 7,214,751 nodes in v3.25 to 5,456,654 nodes. The final LMR512 layer adds roughly 5.3% nodes relative to that reduced base, leaving v3.26 at roughly 20% fewer depth-12 nodes than the original v3.25 on this suite.

Fixed-depth node counts are search-efficiency evidence only; they are not strength evidence. The 200 ms head-to-head result above is the release strength gate.

## Compatibility

- `v326` becomes the repository default and released NNU3 profile.
- `v325` remains available unchanged as a frozen NNU3 regression/comparison baseline.
- `v500` remains the supported secondary NNU4 experimental profile.
- v3.26 reuses the v3.25 NNU3 weights unchanged.
