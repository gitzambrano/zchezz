#!/usr/bin/env bash
# run_selfplay_colab.sh — Geração atômica de self-play em shards para Colab Pro
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ============================ CONFIGURAÇÃO ============================
PROFILE="${PROFILE:-v507}"                        # v507 (NNU4 nativo) ou v331 (NNU3 UCI)
ACCOUNT_ID="${ACCOUNT_ID:-1}"                      # 1 ou 2 (determina seed e identificador do shard)
TARGET_POSITIONS="${TARGET_POSITIONS:-5000000}"    # Meta de posições por conta
GAMES_PER_SHARD="${GAMES_PER_SHARD:-3000}"        # Jogos por shard
NODES="${NODES:-0}"                                # Nós por lance (obrigatório > 0 para v507 na geração real)
MOVETIME="${MOVETIME:-50}"                        # ms por lance (usado como TC para o runner UCI v331)
THREADS="${THREADS:-0}"                            # 0 = autodetecta núcleos da CPU (nproc)
MULTIPV="${MULTIPV:-4}"                            # Candidatos MultiPV na fase de temperatura
TEMP_PLIES="${TEMP_PLIES:-24}"                     # Lances com temperatura T0
RANDOM_PLIES="${RANDOM_PLIES:-8}"                  # Lances aleatórios de abertura
OPENINGS="${OPENINGS:-}"                           # Caminho opcional para livro de aberturas
LOCAL_DIR="${LOCAL_DIR:-/content/zchezz_shards}"
DRIVE_DIR="${DRIVE_DIR:-/content/drive/MyDrive/zchezz_data/selfplay_${PROFILE}}"
DRY_RUN="${DRY_RUN:-0}"                            # 1 = modo inspeção (--show-config)
# ======================================================================

if [[ "${THREADS}" -le 0 ]]; then
    ACTUAL_THREADS=$(nproc 2>/dev/null || echo 2)
else
    ACTUAL_THREADS="${THREADS}"
fi

GIT_COMMIT=$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo "unknown")
CPU_MODEL=$(lscpu 2>/dev/null | grep "Model name:" | sed -E 's/Model name:\s+//' || echo "Unknown CPU")

echo "=========================================================="
echo " Zchezz Self-Play Shard Runner (Colab Pro)"
echo "=========================================================="
echo " Perfil:           ${PROFILE}"
echo " Conta ID:         ${ACCOUNT_ID}"
echo " Meta Posições:    ${TARGET_POSITIONS}"
echo " Jogos por Shard:  ${GAMES_PER_SHARD}"
echo " Nós por Lance:    ${NODES}"
echo " Movetime (v331):  ${MOVETIME} ms"
echo " Threads:          ${ACTUAL_THREADS} (config: ${THREADS})"
echo " Temp Plies:       ${TEMP_PLIES} (MultiPV ${MULTIPV}, T_final 0)"
echo " Random Plies:     ${RANDOM_PLIES}"
echo " Diretório Local:  ${LOCAL_DIR}"
echo " Destino Drive:    ${DRIVE_DIR}"
echo " Commit Git:       ${GIT_COMMIT}"
echo " CPU:              ${CPU_MODEL}"
echo " Modo Dry-Run:     ${DRY_RUN}"
echo "=========================================================="

if [[ "${DRY_RUN}" == "1" ]]; then
    echo "[DRY-RUN] Configuração exibida com sucesso. Nenhuma ação executada."
    exit 0
fi

# Validação de pré-requisitos
if [[ "${PROFILE}" == "v507" && "${NODES}" -le 0 ]]; then
    echo "ERRO: Para o perfil v507, NODES deve ser maior que 0." >&2
    echo "Execute a calibração primeiro (Fase 1) para determinar a quantidade ideal de nós por lance." >&2
    exit 1
fi

WEIGHTS_PATH="${REPO_ROOT}/engine/c/zchezz_${PROFILE}/nnue_weights.bin"
if [[ ! -f "${WEIGHTS_PATH}" ]]; then
    echo "ERRO: Arquivo de pesos não encontrado: ${WEIGHTS_PATH}" >&2
    exit 1
fi

if [[ ! -d "${DRIVE_DIR}" ]]; then
    echo "Criando diretório no Google Drive: ${DRIVE_DIR}"
    mkdir -p "${DRIVE_DIR}"
fi

mkdir -p "${LOCAL_DIR}"

BUILD_DIR="${REPO_ROOT}/engine/build"
SELFPLAY_BIN="${BUILD_DIR}/selfplay"

if [[ "${PROFILE}" == "v507" ]]; then
    if [[ ! -x "${SELFPLAY_BIN}" ]]; then
        echo "Compilando binário nativo selfplay (Linux AVX2)..."
        make -C "${BUILD_DIR}" TOOLS_ENGINE=v507 STATIC_FLAG="" selfplay
    fi
elif [[ "${PROFILE}" == "v331" ]]; then
    V331_BIN="${REPO_ROOT}/engine/c/zchezz_v331/zchezz"
    if [[ ! -x "${V331_BIN}" ]]; then
        echo "Compilando binário nativo v331 (Linux AVX2)..."
        make -C "${BUILD_DIR}" ENGINE=v331 STATIC_FLAG="" native
    fi
else
    echo "ERRO: Perfil não suportado: ${PROFILE}. Escolha v507 ou v331." >&2
    exit 1
fi

# Função auxiliar para somar amostras dos shards já persistidos no Drive
count_persisted_samples() {
    python3 - <<EOF
import os, sys
sys.path.insert(0, '${REPO_ROOT}/train')
try:
    import dataset
    drive_dir = '${DRIVE_DIR}'
    pattern = f"{drive_dir}/sp_${PROFILE}_a${ACCOUNT_ID}_s*.bin"
    import glob
    shards = sorted(glob.glob(pattern))
    if not shards:
        print(0)
        sys.exit(0)
    d = dataset.MultiShardSelfplay.from_glob(pattern)
    print(len(d))
except Exception as e:
    print(0)
EOF
}

CURRENT_SAMPLES=$(count_persisted_samples)
echo "Posições já existentes no Drive para Conta ${ACCOUNT_ID} (${PROFILE}): ${CURRENT_SAMPLES}"

SHARD_IDX=0
while [[ "${CURRENT_SAMPLES}" -lt "${TARGET_POSITIONS}" ]]; do
    SHARD_NAME=$(printf "sp_%s_a%d_s%05d" "${PROFILE}" "${ACCOUNT_ID}" "${SHARD_IDX}")
    DRIVE_BIN="${DRIVE_DIR}/${SHARD_NAME}.bin"
    DRIVE_JSON="${DRIVE_DIR}/${SHARD_NAME}.json"

    # Se o shard já existe concluído no Drive (sem .tmp), pula
    if [[ -f "${DRIVE_BIN}" && -f "${DRIVE_JSON}" ]]; then
        echo "[PULAR] Shard ${SHARD_NAME} já existe no Drive."
        SHARD_IDX=$((SHARD_IDX + 1))
        continue
    fi

    LOCAL_BIN="${LOCAL_DIR}/${SHARD_NAME}.bin"
    LOCAL_JSON="${LOCAL_DIR}/${SHARD_NAME}.json"
    rm -f "${LOCAL_BIN}" "${LOCAL_JSON}"

    SEED=$((ACCOUNT_ID * 1000000 + SHARD_IDX))
    echo "----------------------------------------------------------"
    echo "Iniciando Shard: ${SHARD_NAME} (Seed: ${SEED})"
    echo "----------------------------------------------------------"

    START_TIME=$(date +%s)

    if [[ "${PROFILE}" == "v507" ]]; then
        CMD=(
            "${SELFPLAY_BIN}"
            --out "${LOCAL_BIN}"
            --nnue "${WEIGHTS_PATH}"
            --games "${GAMES_PER_SHARD}"
            --threads "${ACTUAL_THREADS}"
            --movetime 0
            --nodes "${NODES}"
            --multipv "${MULTIPV}"
            --temperature 1.0
            --temp-plies "${TEMP_PLIES}"
            --temp-final 0
            --no-same-opening-twice
            --opening-mode random
            --random-plies "${RANDOM_PLIES}"
            --seed "${SEED}"
        )
        if [[ -n "${OPENINGS}" && -e "${OPENINGS}" ]]; then
            CMD+=(--openings "${OPENINGS}" --opening-mode all)
        fi
        "${CMD[@]}"
    else
        # Profile v331 via tests/run_selfplay.py
        RUNNER_DIR="${LOCAL_DIR}/runner_${SHARD_NAME}"
        rm -rf "${RUNNER_DIR}"
        mkdir -p "${RUNNER_DIR}"
        
        PYTHONPATH="${REPO_ROOT}/train:${REPO_ROOT}/utils" python3 "${REPO_ROOT}/tests/run_selfplay.py" \
            --profile v331 \
            --bin \
            --no-epd \
            --no-pgn \
            --no-opening-in-bin \
            --no-same-opening-twice \
            --opening-mode random \
            --random-plies "${RANDOM_PLIES}" \
            --games "$((GAMES_PER_SHARD / 2))" \
            --concurrency "${ACTUAL_THREADS}" \
            --movetime "${MOVETIME}" \
            --results-dir "${RUNNER_DIR}"

        PRODUCED_BIN=$(find "${RUNNER_DIR}" -name "selfplay_*.bin" | head -n 1)
        if [[ -z "${PRODUCED_BIN}" || ! -f "${PRODUCED_BIN}" ]]; then
            echo "ERRO: O runner UCI v331 não gerou arquivo .bin em ${RUNNER_DIR}" >&2
            rm -rf "${RUNNER_DIR}"
            exit 1
        fi
        mv "${PRODUCED_BIN}" "${LOCAL_BIN}"
        rm -rf "${RUNNER_DIR}"
    fi

    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    if [[ "${DURATION}" -le 0 ]]; then DURATION=1; fi

    # Validação do shard via MultiShardSelfplay
    VALIDATION_OUTPUT=$(python3 - <<EOF
import os, sys
sys.path.insert(0, '${REPO_ROOT}/train')
try:
    import dataset
    d = dataset.MultiShardSelfplay(['${LOCAL_BIN}'])
    print(f"OK:{len(d)}")
except Exception as e:
    print(f"FAIL:{e}")
EOF
)

    if [[ "${VALIDATION_OUTPUT}" != OK:* ]]; then
        echo "ERRO: Falha na validação do shard ${LOCAL_BIN}: ${VALIDATION_OUTPUT}" >&2
        rm -f "${LOCAL_BIN}"
        exit 1
    fi

    SHARD_SAMPLES="${VALIDATION_OUTPUT#OK:}"
    POS_PER_SEC=$((SHARD_SAMPLES / DURATION))

    echo "Shard ${SHARD_NAME} validado com sucesso: ${SHARD_SAMPLES} posições em ${DURATION}s (${POS_PER_SEC} pos/s)."

    # Geração do arquivo sidecar JSON de metadados
    cat <<EOF > "${LOCAL_JSON}"
{
  "shard_name": "${SHARD_NAME}",
  "profile": "${PROFILE}",
  "account_id": ${ACCOUNT_ID},
  "seed": ${SEED},
  "games_per_shard": ${GAMES_PER_SHARD},
  "nodes": ${NODES},
  "movetime_ms": ${MOVETIME},
  "threads": ${ACTUAL_THREADS},
  "multipv": ${MULTIPV},
  "temp_plies": ${TEMP_PLIES},
  "temp_final": 0.0,
  "random_plies": ${RANDOM_PLIES},
  "openings": "${OPENINGS}",
  "git_commit": "${GIT_COMMIT}",
  "sample_count": ${SHARD_SAMPLES},
  "duration_seconds": ${DURATION},
  "positions_per_second": ${POS_PER_SEC},
  "nproc": ${ACTUAL_THREADS},
  "cpu_model": "${CPU_MODEL}"
}
EOF

    # Cópia atômica para o Google Drive: .tmp -> mv
    TMP_BIN="${DRIVE_DIR}/${SHARD_NAME}.bin.tmp"
    TMP_JSON="${DRIVE_DIR}/${SHARD_NAME}.json.tmp"

    cp "${LOCAL_BIN}" "${TMP_BIN}"
    cp "${LOCAL_JSON}" "${TMP_JSON}"
    mv "${TMP_BIN}" "${DRIVE_BIN}"
    mv "${TMP_JSON}" "${DRIVE_JSON}"

    rm -f "${LOCAL_BIN}" "${LOCAL_JSON}"

    CURRENT_SAMPLES=$((CURRENT_SAMPLES + SHARD_SAMPLES))
    REMAINING=$((TARGET_POSITIONS - CURRENT_SAMPLES))
    if [[ "${REMAINING}" -lt 0 ]]; then REMAINING=0; fi

    if [[ "${POS_PER_SEC}" -gt 0 ]]; then
        ETA_SECONDS=$((REMAINING / POS_PER_SEC))
        ETA_MIN=$((ETA_SECONDS / 60))
    else
        ETA_MIN="?"
    fi

    echo "Progresso: ${CURRENT_SAMPLES}/${TARGET_POSITIONS} posições acumuladas. ETA restante: ~${ETA_MIN} minutos."
    SHARD_IDX=$((SHARD_IDX + 1))
done

echo "=========================================================="
echo "Meta atingida com sucesso para a Conta ${ACCOUNT_ID} (${PROFILE})!"
echo "Total acumulado no Drive: ${CURRENT_SAMPLES} posições."
echo "=========================================================="
