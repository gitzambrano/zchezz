# Zchezz v5.01

Zchezz v5.01 promotes the best validated compact NNU4 network from the direct Stockfish 19 NNUE-distillation experiment. The supported NNU4 profile remains named `v500` for repository and tooling compatibility; its UCI engine version is 5.01.

## Network

- Architecture: HalfKP-4Bucket `2560 -> 48 -> 20 -> 1`.
- Warm start: exact48x20 v5.00 baseline.
- Teacher: Stockfish 19 NNUE direct inference (`network.evaluate()`), without search.
- Training corpus: 100,000 quiet positions.
- Selected checkpoint: `lr3e5_e3` (`lr=3e-5`, epoch 3, lambda 0).
- Installed NNU4 SHA-256: `b0d6ce0c5e4903b8fc3fd14cfa3b2b33a239f1ac249d420f171cefc537933a84`.

## Strength evidence

All final gates used `movetime=200 ms`, UCI `Threads=1`, arena concurrency 1, `nodes=0`, and tablebases disabled.

- Versus the previous exact48x20 v5.00 baseline: `704/333/595` over 1,632 games, `+23.2 +/- 15.1 Elo` (95% CI; positive lower bound).
- Versus pinned v3.24: `163/79/270` over 512 games, `-73.7 +/- 28.2 Elo`.

v5.01 is therefore the new v5-family training and evaluation baseline. v3.25 remains the repository default engine profile; promotion of the v5 family does not replace the v3-family reference.
