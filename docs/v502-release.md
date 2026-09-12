# Zchezz v5.02

v5.02 promotes the epoch-3 48x20 NNU4 candidate trained by direct Stockfish 19 NNUE distillation over the existing v5 self-play position bank.

## Training

- Stockfish teacher: SF19 commit `edb0d9db6731067ec50ce619ff372b463bc4dd5d`.
- Source: 1,411,054 stored positions from 10 existing v5 self-play artifacts.
- Direct usable labels: 1,255,843.
- Student architecture: HalfKP-4Bucket `2560 -> 48 -> 20 -> 1` (NNU4).
- Warm start: exact v5.01 48x20 network.
- Selected checkpoint: epoch 3.
- Candidate SHA-256: `5e6cca42f11823505edefb3ee068e0e9bb3a8576f8fb5b0b7a688736ed377150`.

## Strength gate

Against v5.01 at 200 ms/move, one UCI thread, one concurrent game, 64 MB TT, no tablebases, and 256 deterministic independent EPD openings:

- 128 games: **63 wins / 28 draws / 37 losses**.
- Score: **60.16%**.
- Estimated gain: **+71.6 Elo**.
- 95% CI half-width: **54.2 Elo**; lower bound remains positive.

The screen selected epoch 3 over epoch 1. Epoch 3 was 9/6/9 in its 24-game screen; epoch 1 was 9/3/12.

## Performance

Depth-10 benchmark on the promotion research runner:

- v5.01: 2,874,632 nodes/s.
- v5.02 candidate: 2,829,656 nodes/s.
- Throughput delta: about -1.6%.

This release promotes v5.02 as the new **v5-family baseline**. It does not change the repository's v3.25 default/reference policy.
