# Zchezz — Geração de Self-Play (~10M Posições) no Google Colab Pro + Treino na GPU

Este diretório contém a automação completa para gerar cerca de 10 milhões de posições avaliadas em shards atômicos no **Google Colab Pro** distribuídas entre duas contas independentes, com persistência direta no Google Drive e suporte a treinamento na GPU.

---

## 1. Divisão por Conta e Perfis

Cada conta Colab executa um pipeline autônomo de ponta a ponta:

| Parâmetro | Conta 1 | Conta 2 |
|---|---|---|
| **Perfil** | `v507` (NNU4) | `v331` (NNU3) |
| **Gerador** | `selfplay` nativo (C, threads in-process) | `tests/run_selfplay.py --profile v331` (UCI, processos persistentes) |
| **Compilação** | `make -C engine/build TOOLS_ENGINE=v507 selfplay` | `make -C engine/build ENGINE=v331 native` |
| **Shards no Drive** | `zchezz_data/selfplay_v507/` | `zchezz_data/selfplay_v331/` |
| **Checkpoints no Drive** | `zchezz_data/checkpoints/v507/` | `zchezz_data/checkpoints/v331/` |
| **Seed Base** | `1000000` | `2000000` |
| **Variável no Notebook** | `PROFILE = "v507"`, `ACCOUNT_ID = 1` | `PROFILE = "v331"`, `ACCOUNT_ID = 2` |

> [!NOTE]
> **Plano B para o v331:** Como o backend UCI do v331 opera via processos separados e protocolo de texto, sua vazão em posições/segundo é naturalmente menor que o gerador in-process do v507. A etapa de calibração medirá essa diferença. Caso o v331 fique excessivamente lento, é possível treinar a rede `v331` na GPU utilizando diretamente os shards gerados pelo `v507` (os dados de tabuleiro são arquiteturalmente neutros, e o cabeçalho registra a proveniência).

---

## 2. Configuração de Runtime no Colab Pro

1. Abra [`zchezz_selfplay_colab.ipynb`](file:///colab/zchezz_selfplay_colab.ipynb) em cada conta do Google Colab.
2. Defina `PROFILE` e `ACCOUNT_ID` na célula de configuração no topo.
3. No menu **Ambiente de execução (Runtime) -> Alterar tipo de ambiente de execução (Change runtime type)**:
   - **Fase 1 e 2 (Calibração e Geração):**
     - Acelerador: **Nenhum** (CPU).
     - Perfil de hardware: **High-RAM / High-CPU** (8 a 12 vCPUs).
   - **Fase 3 (Treinamento PyTorch):**
     - Acelerador: **GPU (T4 ou A100)**.
     - Perfil de hardware: **High-RAM**.
4. Habilite a opção **Execução em segundo plano (Background execution)** se disponível na assinatura.

---

## 3. Protocolo de Shards e Persistência Atômica

Para garantir total tolerância a falhas e desconexões:
1. **Geração Local:** Cada shard (2.000 a 3.000 jogos) é gerado localmente em `/content/zchezz_shards/` com seed única (`ACCOUNT_ID * 1000000 + shard_idx`).
2. **Validação Rigorosa:** O shard é inspecionado com `train/dataset.py:MultiShardSelfplay` para garantir que o tamanho do registro bate exatamente com os 75 bytes por amostra após o cabeçalho de 184 bytes.
3. **Metadados Sidecar:** É gerado um arquivo JSON ao lado (`.json`) contendo seed, nodes, movetime, threads, commit git, tempo decorrido, taxa de posições/s e modelo da CPU.
4. **Cópia Atômica:** O arquivo é copiado para o Google Drive como `.tmp` e renomeado via `mv`.
5. **Retomada Idempotente:** Se a sessão cair, ao reiniciar a célula, o script detecta os shards já consolidados no Drive e pula automaticamente.

---

## 4. Fases de Execução

### Fase 1: Calibração
- Execute a célula de calibração no notebook (200 jogos para v507, 50 para v331).
- Anote: posições/s, amostras por partida (lances forçados de abertura são excluídos da contagem) e ETA.
- Defina `CALIBRATED_NODES` para o v507 com base no seu orçamento de horas.

### Fase 2: Geração em Larga Escala
- Inicie a geração na célula 5. O progresso é reportado a cada shard com posições acumuladas e ETA restante.

### Fase 3: Treinamento na GPU
- Altere o runtime para GPU High-RAM.
- Os shards são copiados para `/content/shards/` (leitura local rápida).
- O diretório `checkpoints/<PROFILE>` é linkado simbolicamente ao Google Drive para que o `latest.pt` seja salvo com segurança.
- O treinamento oficial é disparado via:
  ```bash
  python3 train/run.py --profile <PROFILE> --source kind=bin,path=/content/shards/*.bin,k=0.75 --epochs <N> --workers $(nproc)
  ```

---

## 5. Avaliação Final (Local)
Ao término do treino, copie a rede treinada para a máquina local e rode o benchmark canônico do repositório:
`movetime=200 ms`, `Threads=1`, aberturas pareadas com cores invertidas, sem tablebases, contra a rede atual do mesmo perfil. Tempos do Colab não servem como evidência de promoção.
