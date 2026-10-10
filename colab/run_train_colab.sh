#!/usr/bin/env bash
# run_train_colab.sh — Pipeline oficial de Fine-Tuning NNUE no Google Colab
#
# Roda sem argumentos (perfil v331 por padrão, conforme AGENTS.md).
# Toda configuração pode ser sobrescrita via variáveis de ambiente ou flags.
# DRY_RUN=1 ou --show-config apenas exibe a configuração sem alterar estado.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ============================ CONFIGURAÇÃO ============================
PROFILE="${PROFILE:-v331}"                        # v331 (NNU3) | v507 (NNU4) | v600 (NNU5)
EPOCHS="${EPOCHS:-100}"                            # Épocas de fine-tuning (padrão 100)
LR="${LR:-1e-5}"                                   # Learning rate inicial de fine-tuning (10^-5)
ETA_MIN="${ETA_MIN:-1e-7}"                         # Learning rate final via CosineAnnealing (10^-7)
K="${K:-0.1}"                                      # Peso WDL (0.1 = target denso TD(λ) com lookahead)
BATCH_SIZE="${BATCH_SIZE:-0}"                      # 0 = auto por arquitetura (16384 v331, 65536 v507/v600)
DEVICE="${DEVICE:-auto}"                           # auto | cuda | cpu
SHARDS_DIR="${SHARDS_DIR:-/content/shards}"        # Cache local de alta vazão NVMe
DRIVE_DIR="${DRIVE_DIR:-/content/drive/MyDrive/zchezz_data}"
# Suporte a flags CLI opcionais
while [[ $# -gt 0 ]]; do
    case "$1" in
        --show-config|-s) DRY_RUN=1; shift ;;
        --profile|-p) PROFILE="$2"; shift 2 ;;
        --epochs|-e) EPOCHS="$2"; shift 2 ;;
        --lr) LR="$2"; shift 2 ;;
        --eta-min) ETA_MIN="$2"; shift 2 ;;
        --k) K="$2"; shift 2 ;;
        --batch-size|-b) BATCH_SIZE="$2"; shift 2 ;;
        --device|-d) DEVICE="$2"; shift 2 ;;
        *) echo "AVISO: Argumento desconhecido ignorado: $1" >&2; shift ;;
    esac
done

CHECKPOINTS_DRIVE_DIR="${CHECKPOINTS_DRIVE_DIR:-/content/drive/MyDrive/zchezz_checkpoints/${PROFILE}}"

case "${PROFILE}" in
    v331|v507|v600) ;;
    *) echo "ERRO: Perfil não suportado: ${PROFILE}. Escolha v331, v507 ou v600." >&2; exit 1 ;;
esac

if [[ "${BATCH_SIZE}" -le 0 ]]; then
    if [[ "${PROFILE}" == "v331" ]]; then
        ACTUAL_BATCH_SIZE=16384
    else
        ACTUAL_BATCH_SIZE=65536
    fi
else
    ACTUAL_BATCH_SIZE="${BATCH_SIZE}"
fi

GIT_COMMIT=$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo "unknown")
CPU_MODEL=$(lscpu 2>/dev/null | grep "Model name:" | sed -E 's/Model name:\s+//' || echo "Unknown CPU")
GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo "Sem GPU dedicada (CPU mode)")

echo "=========================================================="
echo " Zchezz NNUE Training & Fine-Tuning Runner (Colab)"
echo "=========================================================="
echo " Perfil:           ${PROFILE}"
echo " Épocas:           ${EPOCHS}"
echo " Learning Rate:    ${LR} -> ${ETA_MIN} (Cosine Annealing)"
echo " Target Blend (K): ${K} (WDL weight; search lookahead ativo)"
echo " Batch Size:       ${ACTUAL_BATCH_SIZE}"
echo " Dispositivo:      ${DEVICE}"
echo " Shards Locais:    ${SHARDS_DIR}"
echo " Drive Dados:      ${DRIVE_DIR}"
echo " Drive Checkpoints:${CHECKPOINTS_DRIVE_DIR}"
echo " Git Commit:       ${GIT_COMMIT}"
echo " CPU:              ${CPU_MODEL}"
echo " Acelerador GPU:   ${GPU_INFO}"
echo " Modo Dry-Run:     ${DRY_RUN}"
echo "=========================================================="

if [[ "${DRY_RUN}" == "1" ]]; then
    echo "[DRY-RUN] Configuração exibida com sucesso. Nenhuma ação executada."
    exit 0
fi

# 1. Preparação de diretórios locais
mkdir -p "${SHARDS_DIR}"

# 2. Coleta e consolidação de todos os shards (.bin) disponíveis
echo "[1/4] Agrupando shards de self-play em ${SHARDS_DIR}..."
SHARDS_COUNT=0

# Busca em subpastas conhecidas do Google Drive
for sub in "selfplay_v507" "selfplay_v507_r2" "selfplay_v331" "selfplay_v331_r2" "v507_shards" "v331_shards"; do
    SRC_PATH="${DRIVE_DIR}/${sub}"
    if [[ -d "${SRC_PATH}" ]]; then
        echo "  Localizando shards em ${SRC_PATH}..."
        for f in "${SRC_PATH}"/*.bin; do
            if [[ -f "${f}" ]]; then
                fname="$(basename "${f}")"
                if [[ ! -e "${SHARDS_DIR}/${fname}" ]]; then
                    ln -sf "${f}" "${SHARDS_DIR}/${fname}" || cp -f "${f}" "${SHARDS_DIR}/${fname}"
                fi
                ((SHARDS_COUNT++)) || true
            fi
        done
    fi
done

# Busca em shards locais (/content/zchezz_shards) caso existam
if [[ -d "/content/zchezz_shards" ]]; then
    for f in /content/zchezz_shards/*.bin; do
        if [[ -f "${f}" ]]; then
            fname="$(basename "${f}")"
            if [[ ! -e "${SHARDS_DIR}/${fname}" ]]; then
                ln -sf "${f}" "${SHARDS_DIR}/${fname}" || cp -f "${f}" "${SHARDS_DIR}/${fname}"
            fi
            ((SHARDS_COUNT++)) || true
        fi
    done
fi

echo "  Total de shards consolidados: ${SHARDS_COUNT}"

if [[ "${SHARDS_COUNT}" -eq 0 ]]; then
    echo "ERRO: Nenhum shard .bin encontrado para treinamento em ${DRIVE_DIR} ou /content/zchezz_shards." >&2
    exit 1
fi

# 3. Persistência atômica de checkpoints no Google Drive
echo "[2/4] Configurando espelhamento de checkpoints no Google Drive..."
if [[ -d "/content/drive/MyDrive" ]]; then
    mkdir -p "${CHECKPOINTS_DRIVE_DIR}"
    CKPT_LOCAL="${REPO_ROOT}/checkpoints/${PROFILE}"
    mkdir -p "$(dirname "${CKPT_LOCAL}")"
    if [[ -d "${CKPT_LOCAL}" && ! -L "${CKPT_LOCAL}" ]]; then
        # Copia checkpoints existentes para o drive se ainda não existirem
        cp -rn "${CKPT_LOCAL}"/* "${CHECKPOINTS_DRIVE_DIR}"/ 2>/dev/null || true
        rm -rf "${CKPT_LOCAL}"
    fi
    if [[ ! -L "${CKPT_LOCAL}" ]]; then
        ln -sf "${CHECKPOINTS_DRIVE_DIR}" "${CKPT_LOCAL}"
        echo "  Link simbólico criado: ${CKPT_LOCAL} -> ${CHECKPOINTS_DRIVE_DIR}"
    fi
fi

# 4. Disparo do treinamento oficial
echo "[3/4] Iniciando treinamento via train/run.py..."
python3 "${REPO_ROOT}/train/run.py" \
    --profile "${PROFILE}" \
    --source "kind=bin,path=${SHARDS_DIR}/*.bin,k=${K}" \
    --epochs "${EPOCHS}" \
    --lr "${LR}" \
    --transfer-lr "${LR}" \
    --eta-min "${ETA_MIN}" \
    --batch-size "${ACTUAL_BATCH_SIZE}" \
    --device "${DEVICE}"

# 5. Exportação e empacotamento dos pesos finais
echo "[4/4] Exportando pesos binários pós-treinamento..."
case "${PROFILE}" in
    v331)
        python3 "${REPO_ROOT}/train/export_nnu3.py" \
            --ckpt "${REPO_ROOT}/checkpoints/v331/latest.pt" \
            --out "${REPO_ROOT}/engine/c/zchezz_v331/nnue_weights.bin"
        ;;
    v507)
        python3 "${REPO_ROOT}/train/export_nnu4.py" \
            --checkpoint "${REPO_ROOT}/checkpoints/v507/latest.pt" \
            --output "${REPO_ROOT}/engine/c/zchezz_v507/nnue_weights.bin"
        ;;
    v600)
        python3 "${REPO_ROOT}/train/export_nnu5.py" \
            --checkpoint "${REPO_ROOT}/checkpoints/v600/latest.pt" \
            --output "${REPO_ROOT}/engine/c/zchezz_v600/nnue_weights.bin"
        ;;
esac

# Se o Google Drive estiver montado, copia os pesos finais para o Drive
if [[ -d "${CHECKPOINTS_DRIVE_DIR}" ]]; then
    cp -f "${REPO_ROOT}/engine/c/zchezz_${PROFILE}/nnue_weights.bin" "${CHECKPOINTS_DRIVE_DIR}/nnue_weights.bin"
    echo "  Pesos finais salvos no Drive: ${CHECKPOINTS_DRIVE_DIR}/nnue_weights.bin"
fi

echo "=========================================================="
echo " Treinamento do perfil ${PROFILE} concluído com sucesso!"
echo "=========================================================="
