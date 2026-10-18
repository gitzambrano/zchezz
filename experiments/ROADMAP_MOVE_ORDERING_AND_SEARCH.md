# Plano Experimental: Melhorias de Move Ordering, History e Eficiência de Busca

## 1. Diagnóstico e Motivação

No benchmark contra o Stockfish 17 sob controle de tempo idêntico (100 ms por lance):
* **Zchezz (`v331_exp3`):** 84.080 nós/lance $\to$ **depth 12.7**
* **Stockfish 17:** 95.224 nós/lance $\to$ **depth 32.2**

Com praticamente o mesmo volume de nós avaliados (~90.000 nós), o Stockfish atinge **2,5x mais profundidade**.

A razão não é velocidade de execução (NPS), mas sim a **eficiência da árvore de busca**:
1. O Stockfish poda até 80% das variantes calmas em profundidades rasas porque seu **Move Ordering acerta o lance de corte em 1º ou 2º lugar mais de 92% das vezes**.
2. O Stockfish usa **Singular Extensions (SE)** para aprofundar de forma laser na variante crítica sem explodir o número de nós secundários.

---

## 2. Pilares de Melhoria do Move Ordering

Antes de aplicar podas mais agressivas nas famílias (`3xx`, `5xx`, `6xx` e Híbridos), o Move Ordering deve ser aprimorado:

### 2.1. Capture History Table
* **Estrutura:** `cap_history[attacker_piece][to_sq][captured_piece_type]`
* **Mecanismo:** Capturas que causam cortes beta (mesmo sem ganho material estático) recebem pontuação alta de histórico e passam à frente de outras capturas no ordenamento.
* **Benefício:** Evita testes lentos de SEE em lances já conhecidos como bons.

### 2.2. Countermove History (CMH) & Followup History (FMH)
* **Estrutura:** 
  * `counter_history[prev_piece][prev_to][current_piece][current_to]`
  * `followup_history[prev2_piece][prev2_to][current_piece][current_to]`
* **Mecanismo:** Premia lances que são refutações naturais ao lance anterior do adversário.
* **Benefício:** Aumenta a taxa de TT hit e beta cutoff logo nos lances 1 e 2.

### 2.3. History Gravity (Decaimento Dinâmico)
* **Problema atual:** Reset periódico ou limites arbitrários geram ruído no histórico.
* **Solução:** Fórmula de gravidade do Stockfish:
  $$H \leftarrow H + \text{bonus} - H \times \frac{|\text{bonus}|}{16384}$$
* **Benefício:** Os valores de histórico convergem dinamicamente sem overflow e priorizam o momento atual da partida.

---

## 3. Podas Agressivas Viabilizadas pelo Novo Move Ordering

Com o Move Ordering de elite implementado, as seguintes podas podem ser acionadas com segurança:

1. **Late Move Pruning (LMP) Tensa:**
   * Lances calmos além de $3 + \text{depth}^2 / 2$ são ignorados completamente a partir do ply 2.
2. **Singular Extensions (SE) com Extensão Dupla (+2 plies):**
   * Disparo a partir de $\text{depth} \ge 6$.
   * Se o re-search excluindo o TT move falha muito abaixo do limiar ($\text{score} < \beta - 40$), estender $+2$ plies.
   * Se outros lances também superam $\beta$ (multi-cut), podar o nó imediatamente.
3. **Late Move Reductions (LMR) Aprofundadas:**
   * Lances com histórico muito negativo ($H < -1024$) sofrem $-2$ ou $-3$ plies de redução.

---

## 4. Evolução da Arquitetura Híbrida (Dual NNUE)

1. **Normalização de Escala de Avaliação:**
   * Alinhar a função de mapeamento de centipawns entre a Small Net (`507_exp1`, NNU4) e a Big Net (`v601`, NNU5) para evitar descontinuidades no chaveamento ($|\text{eval}| \approx \theta$).
2. **Gating Dinâmico Decrescente:**
   * Utilizar limiar adaptativo: $\theta(d) = 180 - 10 \times d$.
   * Em profundidades rasas, a Small Net resolve tudo a 1.2M+ NPS.
   * Em profundidades altas ($d \ge 12$), a Big Net atua apenas nos desempates finos.
