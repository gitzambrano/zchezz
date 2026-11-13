# Zchezz training data

## 1. Nomenclature

The vocabulary is closed — `cp`, `result`, `target`. Nothing else.

| Name | Is | Range | Stored? |
|---|---|---|---|
| `cp` | evaluation in centipawns | int, WHITE-relative | **yes — the primitive** |
| `result` | the real game outcome | 0.0 / 0.5 / 1.0, WHITE-relative (0 = Black won) | **yes, when a game was played** |
| `wdl` | `sigmoid(cp / 320)` — a function of `cp`, **not** an outcome | 0..1, WHITE-relative | **no — derived at training time** |
| `target` | `lambda * result + (1 - lambda) * wdl` | 0..1, WHITE-relative | **no — built at training time** |

`320` is the same constant as `nnue.c`'s `_nnL3B * 320.0f` and
`train_nnue.py`'s `CP_TO_WDL_T` (CLAUDE.md rule 10).

Three rules that decide everything in the table below:

1. **`wdl` is never a stored column.** It is a pure function of `cp`, so keeping
   both lets them rot apart. `cp` is the primitive; the trainer derives `wdl`.
2. **`lambda` blends two terms, so it is INERT unless the dataset has BOTH
   `cp` and `result`.** Setting it on a single-signal dataset changes nothing.
3. **`result` is `0.0` / `0.5` / `1.0`.** Not `-1..1`, not a win rate, not a PGN
   string. If no game was played the column is absent — never derive an outcome
   from `cp`.

### Folder naming

Tags are appended in this fixed order:
`<source>_<core>_<cp>_<evaluator>_<res>_<endgames>_<filter>_<data>`.

| Tag | Means |
|---|---|
| `_cp` | has a `cp` column |
| `_res` | has a `result` column |
| `_filter` | quiet-filtered |
| `_raw` | unfiltered / unprocessed |
| `_endgames` | endgame positions only |
| `_data<YYYYMMDD>` | generation date, full year |
| `_sf` / `_sf<budget>` / `_sfd<depth>` | evaluated by a Stockfish pass we ran (budget = nodes unless `d`-prefixed = depth); bare `_sf` = budget unrecorded |
| `_sfdb` | Stockfish evaluations shipped **with the lichess database**, several versions — not a pass we ran |
| `_zchezz` | evaluated by our own engine's search during self-play |
| `_virichess` | evaluated by Virichess's own engine, upstream |
| `selfplay_` prefix | our engine's self-play games |
| `synthetic_endgame_` prefix | generated positions, no game played |

There is no `_wdl` tag: no folder has a `wdl` column.

Evidence tags: **[M]** measured from the data · **[O]** stated by the project
owner · **[I]** inferred from the folder name · **[?]** unknown.

## 2. All datasets

| # | dataset | format | files | positions | MB | source | played by | phase | analyzed by | eval budget | `cp` | `result` | filtered | date | lambda | stage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `extraquiet_cp_sf5k_res_filter` | parquet | 21 | 40,098,183 | 1,444 | human | humans **[O]** | all | Stockfish, ours **[I]** | 5k nodes | ✓ | ✓ 100% **[M]** | quiet | unrecorded | **active** | warmup |
| 2 | `viriformat_cp_virichess_filter_data20260312` | parquet | 308 | 30,753,600 | 1,154 | engine | Virichess self-play **[O]** | all | **Virichess** **[O]** | unrecorded | ✓ | ✗ lost in conversion **[M]** | quiet | 2026-03-12 | inert | **excluded** |
| 3 | `lichess_cp_sfdb_filter` | parquet | 1,460 | 18,558,222 | 627 | lichess | humans **[O]** | all | Stockfish, **lichess DB**, several versions **[O]** | varies | ✓ reconstructed **[M]** | — | quiet | unrecorded | inert | warmup |
| 4 | `selfplay_cp_sf50k_res_filter_data20260410` | parquet | 1,607 | 16,063,299 | 322 | selfplay | Zchezz **[O]** | all | Stockfish, ours **[I]** | 50k nodes | ✓ | ✓ 100% **[M]** | quiet | 2026-04-10 | **active** | finetune |
| 5 | `lichess_cp_sf_filter` | parquet | 305 | 15,223,769 | 482 | lichess | humans **[O]** | all | Stockfish, ours **[I]** | unrecorded | ✓ | — | quiet | unrecorded | inert | warmup |
| 6 | `viriformat_cp_virichess_filter_data20260112` | parquet | 118 | 11,706,900 | 439 | engine | Virichess self-play **[O]** | all | **Virichess** **[O]** | unrecorded | ✓ | ✗ lost in conversion **[M]** | quiet | 2026-01-12 | inert | **excluded** |
| 7 | `selfplay_cp_zchezz_res_filter_data20260401` | parquet | 915 | 9,140,226 | 183 | selfplay | Zchezz **[O]** | all | **Zchezz itself** **[I]** | search-time | ✓ | ✓ 86.9% **[M]** | quiet | 2026-04-01 | **active** | finetune |
| 8 | `selfplay_cp_zchezz_res_filter_data20260404` | parquet | 879 | 8,789,380 | 167 | selfplay | Zchezz **[O]** | all | **Zchezz itself** **[I]** | search-time | ✓ | ✓ 100% **[M]** | quiet | 2026-04-04 | **active** | finetune |
| 9 | `selfplay_cp_sf50k_res_filter_data20260404` | parquet | 749 | 7,475,000 | 142 | selfplay | Zchezz **[O]** | all | Stockfish, ours **[I]** | 50k nodes | ✓ | ✓ 100% **[M]** | quiet | 2026-04-04 | **active** | finetune |
| 10 | `selfplay_cp_sf100k_res_endgames_filter_data20260414` | parquet | 566 | 5,657,835 | 98 | selfplay | Zchezz **[O]** | endgames | Stockfish, ours **[I]** | 100k nodes | ✓ | ✓ 100% **[M]** | quiet | 2026-04-14 | **active** | finetune |
| 11 | `extraquiet_cp_sfd14_endgames_filter` | parquet | 56 | 2,800,000 | 74 | human | humans **[O]** | endgames | Stockfish, ours **[I]** | depth 14 | ✓ | — | quiet | unrecorded | inert | finetune |
| 12 | `selfplay-lichess_cp_sf500k_res_filter_endgames` | parquet | 54 | 2,700,000 | 44 | selfplay | Zchezz, from lichess endgame positions **[O]** | endgames | Stockfish, ours **[I]** | 500k nodes | ✓ | ✓ 85.3% **[M]** | quiet | unrecorded | **active** | finetune |
| 13 | `extraquiet_cp_sf60k_filter` | parquet | 30 | 1,500,000 | 52 | human | humans **[O]** | all | Stockfish, ours **[I]** | 60k nodes | ✓ | — | quiet | unrecorded | inert | finetune |
| 14 | `synthetic_endgame_cp_sf_filter_data20260414` | parquet | 61 | 1,220,000 | 26 | synthetic | **nobody — generated** **[M]** | endgames | Stockfish, ours **[O]** | unrecorded | ✓ | — none exists | quiet | 2026-04-14 | inert | finetune |
| 15 | `selfplay_cp_zchezz_res_filter_data20260410` | parquet | 85 | 850,000 | 17 | selfplay | Zchezz **[O]** | all | **Zchezz itself** **[I]** | search-time | ✓ | ✓ 100% **[M]** | quiet | 2026-04-10 | **active** | finetune |
| 16 | `synthetic_endgame_cp_sf_filter_data20260413` | parquet | 53 | 521,158 | 11 | synthetic | **nobody — generated** **[M]** | endgames | Stockfish, ours **[O]** | unrecorded | ✓ | — none exists | quiet | 2026-04-13 | inert | finetune |
| 17 | `extraquiet_cp_sfd12_endgames_filter` | parquet | 6 | 262,101 | 6 | human | humans **[O]** | endgames | Stockfish, ours **[I]** | depth 12 | ✓ | — | quiet | unrecorded | inert | finetune |
| 18 | `lichess_cp_sf400k_filter` | parquet | 3 | 150,000 | 5 | lichess | humans **[O]** | all | Stockfish, ours **[I]** | 400k nodes | ✓ | — | quiet | unrecorded | inert | finetune |
| 19 | `miscelaneous_cp_sf1M_res_filter` | parquet | 1 | 34,103 | 1 | mixed **[?]** | mixed **[?]** | all | Stockfish, ours **[I]** | 1M nodes | ✓ | ✓ 11.6% **[M]** | quiet | unrecorded | **active** | finetune |
| 20 | `selfplay_raw_res_data20260410` | EPD | 4 | 27,931,999 **[M]** | 2,814 | selfplay | Zchezz **[O]** | all | **none yet** | — | — | ✓ | **raw** | 2026-04-10 | — | unprocessed |
| 21 | `selfplay_raw_res_data20260401` | EPD | 12 | 14,959,362 **[M]** | 1,503 | selfplay | Zchezz **[O]** | all | **none yet** | — | — | ✓ | **raw** | 2026-04-01 | — | unprocessed |
| 22 | `selfplay_raw_res_data20260404` | EPD | 6 | 14,263,492 **[M]** | 1,423 | selfplay | Zchezz **[O]** | all | **none yet** | — | — | ✓ | **raw** | 2026-04-04 | — | unprocessed |
| 23 | `selfplay_raw_res_endgames_data20260414` | EPD | 2 | 9,845,881 **[M]** | 921 | selfplay | Zchezz **[O]** | endgames | **none yet** | — | — | ✓ | **raw** | 2026-04-14 | — | unprocessed |

### Totals

| Group | folders | positions | MB |
|---|---|---|---|
| parquet, trainable | 17 | 131,043,276 | 3,079 |
| parquet, excluded (Viriformat) | 2 | 42,460,500 | 1,593 |
| **parquet, all** | **19** | **173,503,776** | **4,672** |
| EPD, raw and unprocessed | 4 | 66,999,734 | 6,661 |

### Reading the columns

- **source** — `human` (assorted human games), `lichess` (human games from the
  lichess database), `selfplay` (our engine against itself), `synthetic`
  (positions generated with no game played), `engine` (another engine's games).
- **analyzed by** — where `cp` came from. `Zchezz itself` means the network is
  being taught its own current opinion, so at lambda=0 those rows add nothing
  new; their `result` is the only independent signal in them.
- **eval budget** — `search-time` means the value is whatever the engine's
  normal game search returned, not a separate fixed-budget analysis pass.
- **`result` %** — the fraction of rows with a known outcome. Below 100% means
  the source left some blank; blanks are kept as unknown, never guessed as draws.
- **date** — from the folder's `_data<YYYYMMDD>` tag. `unrecorded` means the
  folder carries no date; file mtimes are not a substitute, since normalization
  rewrote every parquet.
- **lambda** — `active` where both `cp` and `result` exist. **89,183,091 rows
  (51.4% of all parquet; 68.1% of the trainable corpus).**
- **stage** — which mix in `train_nnue.py`'s `STAGE` switch: `warmup` (random
  weights, LR 1e-3, crude+huge human data, 73.9M rows), `finetune` (LR 1e-5,
  ~200 epochs, the recent strong sets, 57.2M rows), `excluded` (Viriformat, data
  judged low quality), `unprocessed` (raw EPD, needs
  `train/labeling/process_positions.py`).
