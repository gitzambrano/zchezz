# Experimento Dual NNUE: Híbrido Big Net + Small Net (v6xx + v5xx)

## 1. Contexto e Motivação

Nos testes empíricos do Zchezz com **nós fixos (50.000 nós por lance)**, foi comprovado que:
- **`v601` (NNU5 256 HalfKAv2) é superior**:
  - `+27.9 Elo` sobre a `v507_main` (52V 4E 44D, profundidade 12.7 vs 11.4)
  - `+41.9 Elo` sobre a `v331_main` (54V 4E 42D, profundidade 12.6 vs 11.7)
- Contudo, em controles de **tempo fixo** (ex: 100ms), a `v507_main` explorava mais que o dobro de variantes por atingir **~1.150.000 NPS**, contra **~470.000 NPS** da `v601`.

A arquitetura **Dual NNUE** (popularizada pelas versões modernas do Stockfish) resolve exatamente essa tensão entre *throughput* e *profundidade de avaliação*.

---

## 2. Como Funciona o Dual NNUE

A busca de xadrez divide-se em duas regiões de custo muito distintas:
1. **Quiescence Search (QSearch) e Podas Rasas (~85% a 90% dos nós avaliados):**
   - O objetivo é apenas resolver trocas táticas e verificar estabilidade de material.
   - Não requer uma rede de 256 neurônios com 22.528 features.
   - Uma rede ultra-leve e rápida é ideal.
2. **Search Principal e Nós Críticos (~10% a 15% dos nós):**
   - Posições estratégicas, equilibradas ou nós de alta profundidade no PV (*Principal Variation*).
   - Pequenas nuances posicionais decidem o lance. Aqui, o poder de representação da Big Net é decisivo.

### Regra de Decisão (Gating Function)

$$\text{Eval}(s) = 
\begin{cases} 
\text{Eval}_{\text{small}}(s) & \text{se } s \in \text{QSearch} \\
\text{Eval}_{\text{small}}(s) & \text{se } |\text{Eval}_{\text{small}}(s)| \ge \theta \quad (\text{posição desequilibrada}) \\
\text{Eval}_{\text{big}}(s) & \text{se } |\text{Eval}_{\text{small}}(s)| < \theta \quad (\text{posição equilibrada / crítica})
\end{cases}$$

Onde:
- **Small Net ($\text{Eval}_{\text{small}}$):** Modelo `NNU4` (`v507`, 48 neurônios, 2.560 features) $\to$ **1.150.000 NPS**.
- **Big Net ($\text{Eval}_{\text{big}}$):** Modelo `NNU5` (`v601`, 256 neurônios, 22.528 features) $\to$ **+28 a +42 Elo de qualidade**.
- **Limiar ($\theta$):** Tipicamente entre **80 cp e 140 cp**. Se a Small Net já avalia a posição como claramente ganha ou perdida ($|\text{eval}| \ge \theta$), não há necessidade de chamar a Big Net.

---

## 3. Estimativa de Throughput Global

Em uma busca média com 85% dos nós em QSearch/podas e 15% dos nós no search principal (onde 50% são filtrados pelo threshold $\theta$):
- **Chamadas Small Net:** 100% dos nós (custo marginal: ~0.87 $\mu$s/nó).
- **Chamadas Big Net:** apenas ~7.5% dos nós (custo: ~2.1 $\mu$s/nó).
- **Tempo médio por nó:** $0.87 + 0.075 \times 2.1 \approx 1.03\ \mu\text{s/nó}$.
- **Throughput estimado:** **~970.000 NPS** (um ganho de **+106% de velocidade** sobre a `v601` isolada), mantendo a precisão da Big Net em todos os lances decisivos!

---

## 4. Estrutura do Experimento

1. [`dual_eval_benchmark.py`](file:///c:/Projetos/Zchezz/experiments/hybrid_dual_nnue/dual_eval_benchmark.py):
   - Avalia um conjunto de posições padrão (EPD/FEN) com ambas as redes.
   - Mede a correlação de sinal, taxa de ativação da Big Net em função do threshold $\theta$, e latência combinada.
2. Planejamento da integração nativa C (Dual Accumulator com atualização sob demanda).
