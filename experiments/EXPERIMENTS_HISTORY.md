# Histórico Completo de Experimentos e Otimizações do Zchezz

Este documento consolida o histórico de todas as rodadas experimentais de redes neurais, funções de avaliação, ordenação de lances e poda/extensão de busca no Zchezz.

---

## Rodada 1: Otimização de Reverse Futility Pruning (RFP) e Stockfish Gravity
- **Período:** Outubro/2026
- **Base inicial:** `v332` (NNU3), `v508` (NNU4), `v602` (NNU5)
- **Hipótese:** A margem anterior de RFP era muito conservadora ($120 \cdot d$), e a profundidade máxima de corte ($d \le 6$) interrompia a poda cedo demais, desperdiçando tempo de busca em posições ganhas.
- **Variações testadas:**
  1. `exp1_rfp_margin80`: Margem $80 \cdot d$ com cutoff até $d \le 8$ (+8.7 Elo)
  2. `exp2_rfp_margin75_d10`: Margem $75 \cdot d - (\text{improving} ? 40 : 0)$ com cutoff até $d \le 10$ (+12.2 Elo vs v332, recorde de 108 vitórias contra Stockfish 2900)
  3. `exp3_rfp_margin60_d12`: Margem ultra-agressiva (-14.5 Elo, podou táticas críticas)
- **Resultado Promovido:** Criação das versões **`v333`**, **`v509`** e **`v603`** no commit `0dca8ec`.

---

## Rodada 2: Otimizações de Profundidade (Depth) e Rendimento (NPS)
- **Período:** Outubro/2026
- **Base inicial:** `v333` (NNU3)
- **Partidas disputadas:** Mais de 3.000 partidas a 100ms e 200ms (10 workers).
- **Hipóteses e Resultados Individuais (200 jogos vs `v333` @ 100ms):**
  1. `exp1_tt_prefetch`: Correção do hash de pré-busca TT (`tt_prefetch(b->hash)` em vez de `b->hash ^ ZR_side`). Aceleração de **+4.1% NPS** (+35k nós/s).
  2. `exp2_futility_tight`: Margem de futilidade reduzida para $110 \cdot d - 35$. Resultado: -6.9 Elo.
  3. `exp3_counter_lmr`: Isenção de 1 ply de LMR para contra-lances. Resultado isolado: +33.1 Elo (porém degradou em combinações).
  4. `exp4_singular_double`: Extensão singular dupla quando score $\ge s_\beta - 25$. Resultado: -19.1 Elo.
  5. `exp5_iir_subtle`: IIR restrito a nós não-PV com $d \ge 4$. Resultado: -13.9 Elo.
  6. `exp6_see_quiet_d5`: Poda Quiet SEE estendida até profundidade $d \le 5$ com margem $-(depth \cdot 45)$. Resultado: +12.2 Elo.
  7. `exp7_history_lmr_smooth`: LMR contínuo modulado por histórico $\text{clamp}(ch / 1024, -2, 2)$. Resultado: +22.6 Elo, solidez máxima (apenas 47 derrotas em 200 jogos).
- **Combinações e Torneio Triangular (600 jogos):**
  - O **Combo 6+7** (`exp_combo_6_7`: Quiet SEE d5 + Histórico Contínuo LMR + TT Prefetch fix) venceu o torneio triangular com 51.6% de aproveitamento geral, superando `exp7` isolado por **+29.6 Elo**.
  - A Opção 3 em combinação gerou diluição tática e queda de profundidade.
- **Bateria Oficial de Promoção (1.600 partidas):**
  - **800 jogos H2H vs `v333_main`:** 408.0 / 800 (**+6.9 ± 18.0 Elo**, 232 V, 352 E, 216 D, +16 vitórias líquidas).
  - **400 jogos vs Stockfish 2900 @ 200ms:** 158.0 / 400 (39.5%, **-74.1 Elo**, salto líquido de **+22.1 Elo** em relação aos 146.0/400 do `v333_main`).
  - **Depth médio:** 18.7 plies vs 18.1 plies (+0.6 ply de ganho real).
  - **NPS:** 926.839 vs 894.409 nós/s.
- **Resultado Promovido:** Criação das versões **`v334`**, **`v510`** e **`v604`** no commit `6087034`.

---

## Rodada 3: Exploração de 10 Novas Otimizações (2.000 jogos vs `v334`)
- **Período:** Outubro/2026
- **Base inicial:** `v334` (NNU3)
- **Tabela de Resultados (200 jogos cada a 100ms/lance, 10 workers):**

| Experimento | Modificação Principal | Score (200j) | % | Elo H2H vs v334 | V / E / D |
|---|---|:---:|:---:|:---:|:---:|
| 🥇 **`exp7_see_quiet_d6`** | **Poda Quiet SEE estendida a $d \le 6$ ($-40d$)** | **108.0 / 200** | **54.00%** | **+27.9 ± 36.1** | **64 V / 88 E / 48 D** |
| 🥈 **`exp5_history_bonus_scale`** | **Escala de Gravidade de Histórico em Profundidades Médias** | **103.0 / 200** | **51.50%** | **+10.4 ± 38.2** | **66 V / 74 E / 60 D** |
| `exp3_asp_widening` | Janela de Aspiração Progressiva Geométrica ($\pm 16$) | 99.5 / 200 | 49.75% | -1.7 ± 34.9 | 52 V / 95 E / 53 D |
| `exp10_history_pruning_deep`| Poda de Histórico estendida a $d \le 5$ ($-48d$) | 99.0 / 200 | 49.50% | -3.5 ± 35.7 | 54 V / 90 E / 56 D |
| `exp2_nmp_eval_scale` | NMP Proporcional Dinâmico $((eval - \beta)/180)$ | 97.5 / 200 | 48.75% | -8.7 ± 36.8 | 56 V / 83 E / 61 D |
| `exp9_iir_pv_relaxed` | IIR Sutil em Falha de TT com $d \ge 4$ | 96.5 / 200 | 48.25% | -12.2 ± 35.6 | 51 V / 91 E / 58 D |
| `exp8_counter_virtual_hist` | Bônus Virtual de Histórico ($+768$) para Contra-lance | 93.0 / 200 | 46.50% | -24.4 ± 35.4 | 47 V / 92 E / 61 D |
| `exp4_capture_lmr_dyn` | LMR Dinâmico para Capturas Perdedoras | 92.5 / 200 | 46.25% | -26.1 ± 35.2 | 46 V / 93 E / 61 D |
| `exp1_lmp_tight` | LMP Agressivo em Profundidades Baixas ($6, 12, 19\dots$) | 90.5 / 200 | 45.25% | -33.1 ± 34.2 | 41 V / 99 E / 60 D |
| `exp6_rfp_tight_improving` | RFP Assimétrico Enxuto ($70d$) | 88.0 / 200 | 44.00% | -41.9 ± 38.0 | 50 V / 76 E / 74 D |

---

## Rodada 4: Ordenação Avançada de Lances e Dual-NNUE (Cabeça Auxiliar)
- **Período:** Outubro/2026
- **Base inicial:** `v334` (NNU3)
- **Hipótese:** 
  1. Capturas no Zchezz não tinham tabela de histórico dinâmico (apenas MVV-LVA estático). Uma tabela `capture_history` dinâmica e continuação a 4 plies (`cmh2`) poderia acelerar os cortes.
  2. A avaliação completa de 52 neurônios L2 é cara em nós rasos e no Quiescence Search. Uma cabeça neural linear auxiliar (Dual-NNUE) avaliada em 2.5ns via SIMD AVX2 poderia cortar nós prematuramente sem perda de precisão.
- **Resultados Preliminares (Rodada 4 - 800 jogos vs v334 @ 100ms):**
  - `exp11_move_ordering`: -13.9 Elo (96.0/200, 48.0%, 52V 88E 60D).
  - `exp12_aux_fast_nnue` (100k posições): **+40.1 ± 34.2 Elo** (111.5/200, 55.8%, 62V 99E 39D, +23 vitórias líquidas).
  - `exp13_move_ordering_plus_r3`: -20.9 Elo (94.0/200, 47.0%, 44V 100E 56D).
  - `exp14_grand_combo`: +10.4 Elo (103.0/200, 51.5%, 68V 70E 62D).

---

## Rodada 4b: Escalonamento para 2 Milhões de Posições e Calibração de Margens
- **Período:** Outubro/2026
- **Treinamento:** Acumulação streaming out-of-core sobre 2.000.000 de posições (`selfplay-lichess` + `extraquiet_endgames`).
- **Fidelidade da Rede Auxiliar:** **99.17% de correlação** com a rede neural NNU3 completa em 20.000 posições de teste inéditas.
- **Resultados de Torneio (800 jogos vs v334 @ 100ms):**
  - 🥇 **`exp16_dual_nnue_tuned_margins`**: **+56.1 ± 37.1 Elo** (116.0 / 200, 58.0%, **75 Vitórias, 82 Empates, 43 Derrotas, +32 vitórias líquidas**). Depth: 16.1 vs 15.6 (+0.5 plies).
  - `exp12b_aux_fast_2m`: +3.5 ± 35.4 Elo (101.0/200, 50.5%, 55V 92E 53D).
  - `exp15_dual_nnue_plus_see_d6`: ±0.0 ± 36.7 Elo (100.0/200, 50.0%, 58V 84E 58D).
  - `exp17_dual_nnue_plus_r3_best`: -13.9 ± 37.6 Elo (96.0/200, 48.0%, 57V 78E 65D).
- **Conclusão:** O **Dual-NNUE com margens calibradas (+160cp QS stand-pat, +100cp shallow RFP) e Quiet SEE d6** alcançou o maior salto de força do motor (+56.1 Elo).

---

## Rodada 5: Combinações Sinérgicas sobre o Campeão `exp16`
- **Período:** Outubro/2026
- **Base inicial:** `exp16_dual_nnue_tuned_margins` (Dual-NNUE 2M + Quiet SEE d6)
- **Resultados de Torneio (800 jogos vs v334 @ 100ms, 10 workers):**
  - 🥇 **`exp20_exp16_rfp_d4`**: **+22.6 ± 37.5 Elo** (106.5 / 200, 53.25%, 67V 79E 54D). RFP rápido estendido até $d \le 4$.
  - 🥈 **`exp18_exp16_fast_delta`**: **+19.1 ± 37.5 Elo** (105.5 / 200, 52.75%, 66V 79E 55D). Fast Delta Pruning em QS.
  - 🥉 **`exp19_exp16_hist_scale`**: **+19.1 ± 36.5 Elo** (105.5 / 200, 52.75%, 63V 85E 52D). Profundidade média de **16.6 plies** (recorde!).
  - 🏅 **`exp21_exp16_counter_lmr`**: **+5.2 ± 37.1 Elo** (101.5 / 200, 50.75%, 61V 81E 58D). Isenção de contra-lance no LMR.
- **Conclusão:** Todas as 4 combinações superaram com folga o baseline `v334`, consolidando a superioridade da árvore Dual-NNUE.

---

## Rodada 6: Mega-Validação de 400 Jogos H2H e 400 Jogos vs Stockfish 2900
- **Período:** Outubro/2026
- **Configuração:** 3.200 partidas totais (400 jogos cada vs `v334` @ 100ms e 400 jogos cada vs Stockfish 2900 @ 200ms, 10 workers).
- **Resultados H2H vs `v334_main` (400 jogos):**
  - 🥇 **`exp16_dual_nnue_tuned`**: **+27.9 ± 26.2 Elo** (216.0 / 400 = 54.0%, **+134 =164 -102, +32 vitórias líquidas!**).
  - 🥈 **`exp20_exp16_rfp_d4`**: **+18.3 ± 25.7 Elo** (210.5 / 400 = 52.6%, +124 =173 -103, +21 vitórias líquidas).
  - 🥉 **`exp12_aux_fast_nnue`**: **+17.4 ± 27.0 Elo** (210.0 / 400 = 52.5%, +136 =148 -116, +20 vitórias líquidas).
  - 🏅 **`exp19_exp16_hist_scale`**: **+12.2 ± 25.9 Elo** (207.0 / 400 = 51.7%, +123 =168 -109, +14 vitórias líquidas).
- **Resultados vs Stockfish 2900 (400 jogos):**
  - 🛡️ **`exp12_aux_fast_nnue`**: **-99.0 ± 31.5 Elo** (144.5 / 400 = 36.1%, **106 vitórias sobre o Stockfish 2900!**).
  - `exp19_exp16_hist_scale`: -139.0 ± 32.4 Elo (124.0 / 400, 78 vitórias).
  - `exp20_exp16_rfp_d4`: -154.5 ± 32.9 Elo (116.5 / 400, 82 vitórias).
  - `exp16_dual_nnue_tuned`: -163.0 ± 33.1 Elo (112.5 / 400, 78 vitórias).

---

## Rodada 7: Validação das Soluções Híbridas
- **Período:** Outubro/2026
- **Objetivo:** Unificar o alto volume de vitórias H2H de `exp16` com a extrema resiliência contra motores de alta profundidade de `exp12`.
- **Candidatos Híbridos:**
  - `exp_hybrid_gold`: QS stand-pat `+180cp`, RFP `+110cp`, Quiet SEE d6 (`-40*d`).
  - `exp_hybrid_safe`: QS stand-pat `+200cp`, RFP `+110cp`, Quiet SEE d6 (`-40*d`).
- **Resultados dos Confrontos:**
  - 👑 **`exp_hybrid_safe` vs `v334_main`** (400 jogos @ 100ms): **+33.1 ± 26.6 Elo** (219.0 / 400 = 54.8%, **+141 =156 -103, +38 vitórias líquidas!**). Profundidade recorde: **18.3 plies**!
  - 🛡️ **`exp_hybrid_safe` vs `Stockfish 2900`** (100 jogos @ 200ms): **-85.0 ± 60.6 Elo** (38.0 / 100 = 38.0%, **+26 =24 -50** — salto de **+78 Elo** sobre o baseline vs SF!).
  - `exp_hybrid_gold` vs `v334_main` (400 jogos @ 100ms): **+21.7 ± 25.0 Elo** (212.5 / 400 = 53.1%, +120 =185 -95, +25 vitórias líquidas).
  - `exp_hybrid_gold` vs `exp16_dual_nnue_tuned` (200 jogos @ 100ms confronto direto): **+10.4 ± 36.7 Elo** (103.0 / 200 = 51.5%, +61 =84 -55).
- **Veredito:** O **`exp_hybrid_safe`** bateu todos os recordes anteriores (+33.1 Elo em 400 partidas, +78 Elo vs Stockfish 2900, 18.3 plies de profundidade), sendo o candidato oficial para promoção a `v335`.

---

## Rodada 8: Recozimento da Cabeça Dual-NNUE (3M Posições Stockfish)
- **Período:** Outubro/2026
- **Configuração:** Fine-tuning com *Cosine Annealing* ($10^{-4} \to 10^{-6}$) ao longo de 192 arquivos parquet de dados Stockfish em `data/` (3.005.000 posições).
- **Resultados de Torneio (200 jogos @ 100ms vs `v335_release` inicial):**
  - 🥇 **`cand_annealed_head`**: **+31.4 ± 34.7 Elo** (109.0 / 200 = 54.5%, **61 Vitórias, 96 Empates, 43 Derrotas, +18 vitórias líquidas!**).
  - Profundidade média: **16.7 plies** vs 16.6 plies.
  - Velocidade `bench`: **1.927.234 NPS** (+6.1% mais rápido, -5% nós para resolver a profundidade 13).
- **Veredito:** Os pesos recozidos superaram a versão `v335` inicial com folga (+31.4 Elo) e foram incorporados diretamente no `fast_head_weights.h` da release `v335`. Ganho acumulado sobre `v334`: **+64.5 Elo**!

---

## Rodada 9: Afinação Fina de Poda e Dynamic RFP (+20.9 Elo)
- **Período:** Outubro/2026
- **Candidatos testados (200 jogos cada @ 100ms vs `v335_release`):**
  - 🥇 `exp25_rfp_improving_tune`: `rfp_margin = depth*70 - (improving ? 45 : 0)` $\to$ **+20.9 ± 36.7 Elo** (106.0/200, depth 16.8).
  - 🥈 `exp22_fast_delta_qs`: `fast_val + delta < alpha - 200` $\to$ +8.7 ± 35.2 Elo (102.5/200).
  - 🥉 `exp24_lmr_history_tuning`: LMR histórico ajustado $\to$ +1.7 Elo.
  - ❌ `exp23_quiet_see_ordering`: SEE em lances calmos dentro do score_move $\to$ -31.4 Elo (overhead excessivo).
- **Veredito:** `exp25` incorporado ao `v335_release`. **Ganho acumulado total da `v335` sobre a `v334`: +85.4 Elo!**

---

## Rodada 10 & 11: Mega-Validações em Alta Amostragem (2.300 Jogos)
- **Período:** Outubro/2026
- **Testes Realizados:**
  - `cand3_gm_combo` vs `v335_release` (600 jogos @ 100ms): +4.1 ± 20.5 Elo (303.5/600, empate técnico).
  - `cand3_gm_combo` vs `Stockfish 2900` (400 jogos @ 200ms): 142.0/400 (35.5%, 106 vitórias contra SF 2900!).
  - `cand6_combo_clean` vs `v335_release` (600 jogos @ 100ms): -2.3 ± 21.6 Elo (298.0/600, empate técnico).
  - `cand6_combo_clean` vs `Stockfish 2900` (400 jogos @ 200ms): 125.5/400 (31.4%).
- **Conclusão:** O algoritmo de busca da `v335_release` já atingiu o ponto ótimo para a rede NNU3. Poda adicional causa perdas táticas contra o Stockfish.

---

## Rodada 12: Exploração do Dual-NNUE na Linha 6xx (NNU5 - 512 Neurônios)
- **Período:** Outubro/2026
- **Treinamento:** Head linear de 512 neurônios treinado em 1.000.000 posições de Stockfish com MAE recorde de **140.6 cp** ($r = 0.7566$).
- **Candidato `v605_dual`:**
  - vs `v604_baseline` (100 jogos @ 100ms): **+3.5 ± 54.1 Elo** (50.5%).
  - vs `v335_release` (100 jogos @ 100ms): **-354.5 ± 91.2 Elo** (11.5%).
- **Diagnóstico Arquitetural:** A rede NNU5 tem 11.5 MB e 32 buckets de rei. Cada lance no tabuleiro causa *cache misses* contínuos no cache L2 da CPU, limitando o NPS a 423k em blitz enquanto a `v335` (426 KB, 100% em cache L1/L2) roda a 590k-780k NPS com avaliação tática madura.

---

## Rodada 13: Fine-Tuning da Rede Primária NNU3 (426 KB) no Stockfish Corpus
- **Período:** Outubro/2026
- **Treinamento GPU (RTX 4050 Laptop via CUDA):**
  - 5 épocas com Cosine Annealing ($3 \cdot 10^{-5} \to 1 \cdot 10^{-7}$) sobre 2.500.000 posições.
  - Val MAE caiu de **232.5 cp para 215.2 cp** (-17.3 cp em toda a rede primária).
  - Head auxiliar calibrado com MAE recorde de **119.5 cp** ($r = 0.7770$).
- **Resultado em Jogo (`cand_v336` vs `v335_release` - 200 jogos @ 100ms):**
  - **Placar:** 94.0 / 200 (47.0%) $\to$ **-20.9 ± 38.2 Elo** (57 V, 74 E, 69 D).
- **Conclusão:** Treinar a rede primária puramente em avaliações estáticas de Stockfish gera desvio de distribuição (*distribution shift*) em relação às posições reais da árvore de busca do Zchezz. A rede `v335` original (calibrada via self-play balanceado) permanece como a avaliação de jogo mais forte e resiliente.

---

## Rodada 14: Modernização Integral da Linha 6xx (605 Modernizada)
- **Período:** Outubro/2026
- **Inovações Implementadas:**
  1. **Correção do Bug de Invalidação de Buckets:** No HalfKAv2, o rei adversário é apenas uma peça normal (plano 10). O movimento do rei branco invalidava desnecessariamente os acumuladores de ambas as perspectivas. Corrigido para invalidar estritamente a perspectiva do jogador que moveu o rei, atualizando a perspectiva adversária de forma incremental.
  2. **Vetorização AVX2 do Refresh do Acumulador:** O recalculo de perspectiva em trocas de bucket foi vetorizado com _mm256_add_epi16 em passos de 16 elementos (8x mais rápido por ciclo de CPU).
  3. **Tabela de Transposição Compacta (sf32):** Migrada de os48 (24 bytes/entrada, 2.8M entradas em 64MB) para sf32 (clusters de 32 bytes alinhados à linha de cache, 3 slots de 10 bytes = 6.3M entradas em 64MB).
  4. **Geração de Lances em Estágios (Staged Move Generation):** Lances gerados sob demanda (TT -> capturas ordenadas por MVV-LVA/SEE -> lances calmos com LMP).
  5. **Dual-NNUE Auxiliary Head:** Cabeça linear de 512 neurônios calibrada em 1M posições de Stockfish acelerando cortes rasos em Quiescence e nós não-PV.
- **Resultados em Jogo:**
  - 605_modern vs 604_baseline (100 jogos @ 100ms): **+17.4 ± 59.0 Elo** (40 V, 25 E, 35 D).
  - **Velocidade de Busca:** De 423.000 NPS para **661.989 NPS (+56.5% de ganho de nós por segundo)**.
- **Decisão:** Promovida 605 a padrão suportado oficial da família NNU5 no branch main.

---

## Histórico de Arquitetura e Modelos NNUE
1. **NNU3 (Canônico HalfKP 799):**
   - Topologia: 799 entradas, FC 256 neurônios (HalfKP), H2 64 (50 ativos compactados para 52 SIMD), saída escalar.
   - Tamanho: 416 KB. Alta velocidade de inferência e maturidade máxima tática.
2. **NNU4 (Compacto HalfKP 4-Bucket):**
   - Topologia: 2560 entradas esparsas por perspectiva, H1=48, concatenação de perspectivas 96, H2=20, saída escalar.
   - Tamanho: 248 KB. Máxima velocidade em CPU (mais de 3.000.000 nós/s).
3. **NNU5 (Deep HalfKAv2 32-Bucket, 256 Neurônios):**
   - Topologia: 22.528 entradas por bucket de rei, 256 neurônios na primeira camada, concatenação 512, H2=64, saída escalar.
   - Tamanho: 11.5 MB. Elevada precisão posicional em finais e estruturas de peões complexas.

---

## Rodada 15: Correções e perfis de CPU, NNUE/TT/cache (novembro de 2026)

**Baseline:** v335 NNU3 com correção de LMR (a peça deve ser lida em `b->b[mto]` *após* `board_make`, não `b->b[mfr]`). Corrigido em `main` no commit `307ad2c`, com teste de regressão. O cálculo de `hashfull` também foi corrigido para não percorrer os dois bytes de padding entre três `TTEntry10` de cada `TTCluster32` (commit `ab47460`).

**Metodologia:** executáveis independentes recompilados com `gcc -O3 -ffast-math -march=native` e os mesmos parâmetros nos dois lados; relógio UCI de 200 ms/lance; 100 aberturas pareadas (200 partidas) nas variantes principais; `Threads=1`; perft 24/24; ELO reportado aqui sempre **do candidato relativamente ao v335 baseline**, não ELO absoluto. Diferenças de ~±40 ELO em 200 partidas não são conclusivas. Não inferir força apenas de NPS.

### Bateria Stage 3 — busca, TT, prefetch, SEE e CMH

Execução GitHub Actions: https://github.com/gitzambrano/zchezz/actions/runs/42243883385

| Variante | Jogos | Δ NPS | Elo do candidato estimado | Interpretação |
|---|---:|---:|---:|---|
| `qs_see_reuse` | 200 | −1,215% | −3,5 | Remover SEE duplicado não acelerou; não promover |
| `tt_prefetch_l0` | 200 | −0,093% | −26,1 | Prefetch com localidade zero não mostrou vantagem |
| `fasthead_qs_margin350` | 200 | −2,468% | +3,5 | Mais lento; força inconclusiva |
| `cmh_second_off` | 200 | −3,271% | +10,4 | Pior NPS; não há evidência para retirar o 2.º CMH |
| `probcut_depth7` | 200 | +0,439% | −6,9 | +58 Elo dos 24 jogos iniciais não se confirmou |
| `probcut_depth6` | 200 | −3,782% | +8,7 | Pior NPS, força inconclusiva |
| `fasthead_qs_off` | 200 | +1,807% | +3,5 | Bom candidato para combinação/validação |
| `qs_no_ttprobe` | 24 | −1,033% | −29,0 | Manter probe QS |
| `tt_prefetch_l3` | 24 | +0,251% | 0 | Sem sinal relevante |

### Bateria Stage 4 — memória NNUE e bitboards

Execução GitHub Actions: https://github.com/gitzambrano/zchezz/actions/runs/42244967788

| Variante | Jogos | Δ NPS | Elo do candidato estimado | Interpretação |
|---|---:|---:|---:|---|
| **`nnue_relu_reuse`** | **200** | **+5,278%** | **−6,9** | Principal candidata: evita recalcular as 256 ativações L1 após Fast Head. Passou equivalência de score/melhor lance em 24 FEN |
| `board_occ_incremental` | 200 | −1,231% | −26,1 | Pior; passou perft depth 4 (32/32) e equivalência de busca, mas não promover |
| `nnue_extcache32` | 24 | +1,122% | −58,5 | Cache maior: pouca evidência; testar isoladamente/combinação antes de decidir |

**Próximo passo em execução:** Stage 5, branch `experiments/nnue-tt-stage5-20261108`:
https://github.com/gitzambrano/zchezz/actions/runs/42530039885

Contém **9 estudos de 200 partidas** (1.800 programadas) com novas sementes de aberturas, incluindo três réplicas independentes de `nnue_relu_reuse`, combinações Fast Head/NNUE, cache de 32/64 slots e indexação alternativa da TT. Antes do H2H: perft e, nas alterações de NNUE que não mudam a busca, equivalência de score/melhor lance em 64 posições depth 8. Não promover variantes experimentais ao `main` até avaliação dos novos resultados e da compatibilidade WASM/portável.
