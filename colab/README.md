# Zchezz — Automação e Geração de Self-Play no Google Colab

Este diretório consolida **toda a infraestrutura do Google Colab** do repositório Zchezz em um único local:
- **Scripts de orquestração local (Playwright/CDP):** Disparo, watchdog keep-alive, relatórios, gerenciamento de runtime e autenticação.
- **Scripts de execução remota:** `run_selfplay_colab.sh` e o notebook `zchezz_selfplay_colab.ipynb`.
- **Sessões e credenciais:** `cookies/` (backups de cookies de autenticação persistentes).
- **Evidências e métricas ao vivo:** `artifacts/` (screenshots de watchdog, relatórios Markdown e status JSON).

---

## 1. Estrutura Unificada do Diretório `colab/`

```text
colab/
├── config.py                 # Registro central de contas, portas CDP e bootloaders
├── browser_utils.py          # Primitivas Playwright, stealth e gerenciamento de cookies
├── human_actions.py          # Simulação de micro-interações humanas para keep-alive
├── launch_workers.py         # Bootstrapper remoto e disparador de células
├── watchdog_workers.py       # Watchdog contínuo resiliente e monitor keep-alive
├── report_workers.py         # Inspetor de métricas, auditor e gerador de relatórios
├── manage_runtime.py         # Gerenciamento de aceleradores (CPU/GPU) e sessões
├── login_worker.py           # Auxiliar para login interativo e salvamento de cookies
├── inspect_workers.py        # Inspeção rápida de status de conexão e saída
├── run_selfplay_colab.sh     # Script bash de geração com tolerância a falhas na VM
├── zchezz_selfplay_colab.ipynb # Notebook executado no Google Colab
├── cookies/                  # Espelho local de cookies de sessão (gitignored)
└── artifacts/                # Screenshots periódicos, report.md e status JSON (gitignored)
```

---

## 2. Registro de Workers Zchezz

| Worker ID | Identificador | Perfil | Conta Google | Porta CDP | Notebook Colab | Shard Prefix |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **6** | `v331` | `v331` (NNU3) | `zchezzproject@gmail.com` | `9331` | [Notebook v331](https://colab.research.google.com/drive/1j8-gG7qApv--t2DBM8tf1gmgKjuUXiLC) | `sp_v331_r2` |
| **7** | `v507` | `v507` (NNU4) | `zbrainproject@gmail.com` | `9507` | [Notebook v507](https://colab.research.google.com/drive/1WaoYFjPIl70cECrs9CGZEwEoMxVzBEp8) | `sp_v507_r2` |

> [!NOTE]
> Por padrão, todos os utilitários de orquestração atuam estritamente sobre os workers **6** (`v331`) e **7** (`v507`) do Zchezz.

---

## 3. Comandos de Orquestração

### A. Monitorar (Watchdog Contínuo)
Mantém as sessões ativas com micro-interações para evitar desconexão por inatividade, detecta quedas, reconecta automaticamente e atualiza métricas em `colab/artifacts/`:
```bash
python colab/watchdog_workers.py
```

### B. Relatório de Status e Métricas
Audita o status de execução, coleta os shards gerados, posições/s e captura prints em `colab/artifacts/`:
```bash
python colab/report_workers.py
```

### C. Disparar Células de Self-Play
Dispara a execução de novas rodadas ou reconecta workers ociosos (ignora workers que já estejam gerando ativamente):
```bash
python colab/launch_workers.py
```

### D. Gerenciar Runtimes e Quotas
```bash
# Alternar de GPU para CPU padrão (limpa bloqueios de cota)
python colab/manage_runtime.py --action switch-cpu

# Terminar sessões travadas
python colab/manage_runtime.py --action terminate-active

# Reiniciar ambiente da VM
python colab/manage_runtime.py --action reset
```

---

## 4. Protocolo de Shards e Persistência Atômica

Para garantir total tolerância a falhas e desconexões:
1. **Geração Local:** Cada shard (2.000 a 3.000 jogos) é gerado localmente em `/content/zchezz_shards/` com seed única (`ACCOUNT_ID * 1000000 + shard_idx`).
2. **Validação Rigorosa:** O shard é inspecionado com `train/dataset.py:MultiShardSelfplay` para garantir integridade estrutural (cabeçalho de 184 bytes seguido por 75 bytes por posição).
3. **Metadados Sidecar:** É gerado um arquivo JSON sidecar contendo seed, nodes, movetime, threads, commit git, tempo decorrido, taxa de posições/s e modelo da CPU.
4. **Cópia Atômica:** O arquivo é copiado para o Google Drive como `.tmp` e renomeado via `mv`.
5. **Retomada Idempotente:** Ao reiniciar a célula, o script detecta os shards já consolidados no Drive e pula automaticamente.

---

## 5. Treinamento na GPU no Google Colab

1. Altere o runtime para **GPU (T4 ou A100)** High-RAM.
2. Copie os shards consolidados do Google Drive para o disco local `/content/shards/` para leitura com alta vazão.
3. Crie link simbólico de `checkpoints/<PROFILE>` para o Google Drive para persistência atômica de `latest.pt`.
4. Dispare o treino oficial:
   ```bash
   python3 train/run.py --profile <PROFILE> --source kind=bin,path=/content/shards/*.bin,k=0.75 --epochs <N> --workers $(nproc)
   ```
