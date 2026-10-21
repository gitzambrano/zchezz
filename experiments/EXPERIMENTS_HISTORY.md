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
