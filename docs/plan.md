# Plano: Zchezz acima de 3100 Elo

Objetivo: um release do Zchezz com rating **medido** acima de 3100, com intervalo de confiança
de 95% cujo limite inferior fique acima de 3050.

Este documento define as fases, os gates e as regras de decisão. Resultados de experimentos
entram em `docs/experiments/`; este arquivo só muda quando a estratégia muda.

## 1. Ponto de partida (fatos do repositório)

| Item | Estado | Fonte |
|---|---|---|
| Linha principal | v3.31, NNU3 (799 → 256 → 64 → 1, sem king buckets) | `docs/nnue.md` |
| Força declarada | "~2900 Elo". Não há no repo a medição que sustente o número (pool, controle de tempo, IC) | `Readme.md` |
| Linha v5 (NNU4) | Mais fraca que a v3: v5.01 −73,7 Elo vs v3.24; v5.21 −137 vs v3.28 (200k nós) | `docs/v501-release.md`, ledger v5 |
| Avaliação estática vs Stockfish | v3.28 MAE 141 cp; v5.06 MAE 162 cp | ledger v5 (v5.22) |
| Micro-ajustes locais da rede v5 | Esgotados (v5.24–v5.31 todos rejeitados) | ledger v5 |
| Busca v3 | Madura: PVS, aspiration, LMR, NMP, RFP, futility, LMP, SEE, singular extension, IIR, correction history de peões, Lazy SMP | `docs/search.md`, `zchezz_v331/search.c` |
| Treino da rede v5 grande | 2,4M posições | ledger v5 |
| Arena nativa, SPRT e `ga_tune` | Só no host NNU4 (v507). A linha v3 só compara via UCI | `engine/build/Makefile`, `docs/regression-testing.md` |

Conclusões para o plano:

1. **A linha v3 é o caminho para 3100.** A linha v5 continua como pesquisa, mas nenhuma fase
   deste plano depende dela.
2. **O gargalo mais provável é o dado de treino, não a arquitetura.** Redes maiores e
   professores mais fortes não ganharam Elo com poucos milhões de posições e com o objetivo
   de treino atual. Engines na faixa de 3100+ treinam com centenas de milhões a bilhões de
   posições rotuladas.
3. **Sem uma medição ancorada, "3100" não é verificável.** A Fase 0 vem antes de tudo.

## 2. Definição da métrica

- **Rating (para o objetivo de 3100):** gauntlet contra âncoras com rating conhecido, na
  escala CCRL, no controle de tempo em que as âncoras foram calibradas. Referência: o
  `UCI_Elo` do Stockfish é calibrado em 60 s + 0,6 s contra âncoras CCRL 40/4 (confirmar na
  documentação da versão fixada do Stockfish). O desvio do protocolo padrão de 200 ms fica
  registrado em cada resultado.
- **Promoção entre versões (sem mudança):** protocolo padrão de `docs/regression-testing.md`
  (200 ms por lance, `Threads=1`, 1 jogo por vez, aberturas pareadas, sem tablebases), com
  SPRT.
- Tempo de CI hospedado e matches com nós fixos não contam como evidência de força.

## 3. Fases

### Fase 0 — Medição (pré-requisito, bloqueia as outras)

1. Fixar a versão do Stockfish (binário e SHA) usada como âncora e professor.
2. Gauntlet do v3.31 contra o Stockfish com `UCI_LimitStrength=true` e `UCI_Elo` em
   {2700, 2900, 3100, 3190} (3190 é o teto do `UCI_Elo`), no TC de calibração, com aberturas
   pareadas. Opcional: 1 ou 2 engines com rating CCRL publicado, como âncoras extras.
3. Ajustar o rating do v3.31 com IC de 95%. Meta: meia-largura do IC ≤ 25 Elo.
4. Ter SPRT para a linha v3 via UCI (o SPRT atual é do `arena.exe`, só NNU4). Adicionar SPRT
   ao runner de torneio UCI ou portar o cálculo de `tests/run_arena.py`. Bounds padrão:
   `elo0=0, elo1=5` (mudanças pequenas) e `elo0=0, elo1=10` (mudanças de rede).

**Gate:** rating do v3.31 publicado em `docs/experiments/` com IC, pool, TC, número de jogos
e SHAs. Esse número substitui o "~2900" do README. A distância real até 3100 define o
orçamento das fases seguintes.

### Fase 1 — Dados em escala para a rede v3 (maior ganho esperado)

Mesma arquitetura NNU3; só muda o dado. Assim o experimento isola uma única causa.

1. **Posições:** self-play no Colab com `colab/run_selfplay_colab.sh`. O gerador nativo
   (v507) produz posições cerca de 24x mais rápido que o runner UCI do v331 (smoke local:
   ~1470 vs ~62 pos/s em 4 threads). Ele vira a fonte principal de **posições**; o v331 via
   UCI entra como fonte secundária, para cobrir as posições que a própria v3 visita.
2. **Rótulos:** rotular de novo todas as posições com o Stockfish fixado
   (`train/teacher.py`, que já aceita `.bin`), com nós fixos por posição (rotular é trabalho
   de esforço fixo; isso é permitido). O `eval_cp` do gerador serve só para minerar
   discordância.
3. **Escala em degraus:** 10M → 50M → 200M posições. Cada degrau só começa se o anterior
   passar no gate.
4. **Treino:** `python train/run.py --profile v331 --source kind=bin,...` com o dado do
   professor (`k` baixo; ver `docs/training.md`) misturado ao resultado das partidas.
   Resultado de partida e rótulo do professor ficam em fontes separadas, com origem
   registrada.
5. **Antes de gastar jogos:** provar que a rede exportada difere de verdade da rede instalada
   (regra 2 do ledger v5) e rodar a validação de artefato NNUE.

**Gate por degrau:** SPRT `[0, 10]` no protocolo de 200 ms contra o v3.31 instalado passa.
Se dois degraus seguidos não passarem, parar a escala e revisar o objetivo de treino antes de
gerar mais dados.

### Fase 2 — Busca da linha v3

Independente da Fase 1; pode rodar em paralelo, mas cada mudança é testada sozinha.

1. **Tuning de parâmetros (SPSA via UCI):** expor as constantes de poda e redução como opções
   UCI (margens de RFP/futility, tabelas de LMR/LMP, NMP, aspiration, bônus de history). O
   `ga_tune` nativo só roda no host NNU4, então ou se porta o tuner para UCI ou ele fica
   limitado à linha v5.
2. **Recursos candidatos,** um por experimento, só depois de conferir no `search.c` que ainda
   não existem: correction history não-peão e de continuação; ProbCut; LMR ajustado por
   history; extensões de check/ameaça ajustadas.
3. Refazer o tuning depois de cada rede nova da Fase 1, porque as margens dependem da escala
   da avaliação.

**Gate:** SPRT `[0, 5]` a 200 ms, por mudança.

### Fase 3 — Rede maior na linha v3 (só depois da Fase 1)

Só começa quando a Fase 1 provar que mais dados rendem Elo com a arquitetura atual.

1. Aumentar a capacidade em um eixo por vez: primeiro L1 (256 → 512), depois king buckets na
   entrada.
2. QAT com runtime exato é obrigatório (infraestrutura validada na v5.24).
3. Medir o custo em NPS antes do treino longo. O ganho de avaliação tem que pagar a perda de
   velocidade no protocolo de 200 ms.

**Gate:** SPRT `[0, 10]` contra a melhor rede da Fase 1, na mesma busca.

### Fase 4 — Release e medição final

1. Integrar as mudanças aprovadas num perfil novo (via `utils/engine_profiles.py`).
2. Repetir o gauntlet da Fase 0 com o mesmo pool, as mesmas âncoras e o mesmo TC.
3. Promover só com pedido explícito do usuário; `engine/ACTIVE_ENGINE` só muda nesse caso.

**Gate final:** rating > 3100 e limite inferior do IC de 95% > 3050.

## 4. Orçamento de Elo

Os valores abaixo são metas de planejamento, não previsões medidas. A Fase 0 substitui a
linha "ponto de partida" por um número real e reajusta o resto.

| Fonte | Meta | Observação |
|---|---|---|
| Ponto de partida | ~2900 (não medido) | Fase 0 |
| Fase 1: dados em escala | +80 a +150 | Maior incerteza e maior potencial |
| Fase 2: tuning + recursos de busca | +40 a +80 | Soma de muitos ganhos pequenos, cada um com SPRT |
| Fase 3: rede maior | +30 a +80 | Condicional à Fase 1 |
| **Total necessário** | **+200** | Se a Fase 0 medir abaixo de 2900, o alvo sobe |

## 5. Regras

Valem as regras do ledger v5 (`docs/experiments/v507-status-2026-09-15.md`), mais:

1. Uma causa por experimento: nunca mudar arquitetura, professor, busca e objetivo ao mesmo
   tempo.
2. Screens de 48 a 96 jogos são só triagem. Promoção exige SPRT ou um gate grande com IC.
3. Todo dado de treino registra origem (cabeçalho do `.bin` e sidecar JSON): gerador, pesos,
   seed, controle de tempo, commit.
4. Professor e resultado de partida ficam em fontes separadas no treino.
5. Todo resultado de match registra SHAs de engine e rede, pool de aberturas, W/D/L, Elo e
   IC.

## 6. Riscos

- **O "~2900" pode estar alto.** Nesse caso, 3100 fica mais distante. A Fase 0 detecta isso
  cedo.
- **Mais dados podem não render Elo** com o objetivo de treino atual (o mesmo padrão da v5).
  A regra de parada da Fase 1 limita o gasto.
- **Custo de computação:** rotular 200M posições com o Stockfish é caro. Medir a vazão do
  professor nos primeiros 10M antes de comprometer o orçamento.
- **Rating em TC curto vs longo:** ganhos a 200 ms nem sempre se mantêm em 60 s + 0,6 s. A
  Fase 4 mede no TC de calibração.

## 7. Decisões pendentes

1. Pool de âncoras da Fase 0: só Stockfish `UCI_Elo` ou também engines com rating CCRL?
2. Orçamento de computação (horas de Colab/unidades) para rotular com o Stockfish na Fase 1.
3. A conta Colab do v507 continua treinando a rede v507, ou passa a só gerar posições para a
   v3?
