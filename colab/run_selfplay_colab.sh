#!/usr/bin/env bash
# run_selfplay_colab.sh — Geração atômica de self-play em shards para Colab Pro
#
# Roda sem argumentos (perfil v507). Toda a configuração vem de variáveis de
# ambiente. DRY_RUN=1 só imprime a configuração: não compila, não gera, não
# grava nada.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ============================ CONFIGURAÇÃO ============================
PROFILE="${PROFILE:-v507}"                        # v507 (NNU4 nativo) ou v331 (NNU3 UCI)
ACCOUNT_ID="${ACCOUNT_ID:-1}"                      # 1 ou 2 (faixa de seeds e nome do shard)
TARGET_POSITIONS="${TARGET_POSITIONS:-5000000}"    # Meta de posições desta conta
GAMES_PER_SHARD="${GAMES_PER_SHARD:-3000}"        # Jogos por shard (par: v331 joga cada abertura nas duas cores)
NODES="${NODES:-0}"                                # Nós por lance, v507 (obrigatório > 0)
MOVETIME="${MOVETIME:-50}"                        # ms por lance, v331 (o runner UCI não expõe nós fixos)
THREADS="${THREADS:-0}"                            # 0 = nproc
MULTIPV="${MULTIPV:-4}"                            # v507: candidatos MultiPV na fase com temperatura
TEMP_PLIES="${TEMP_PLIES:-24}"                     # v507: lances com temperatura T0
RANDOM_PLIES="${RANDOM_PLIES:-8}"                  # Lances aleatórios de abertura
OPENINGS="${OPENINGS:-}"                           # v507: livro opcional (.pgn/.epd ou diretório)
LOCAL_DIR="${LOCAL_DIR:-/content/zchezz_shards}"
DRIVE_DIR="${DRIVE_DIR:-/content/drive/MyDrive/zchezz_data/selfplay_${PROFILE}}"
DRY_RUN="${DRY_RUN:-0}"                            # 1 = só inspeção
MAKE_CMD="${MAKE_CMD:-make}"                       # mingw32-make para teste local no Windows
# ======================================================================

case "${PROFILE}" in
    v507|v331) ;;
    *) echo "ERRO: Perfil não suportado: ${PROFILE}. Escolha v507 ou v331." >&2; exit 1 ;;
esac

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
if [[ "${PROFILE}" == "v507" ]]; then
echo " Nós por Lance:    ${NODES}"
echo " MultiPV / Temp:   ${MULTIPV} / ${TEMP_PLIES} plies, T_final 0"
else
echo " Movetime:         ${MOVETIME} ms"
fi
echo " Threads:          ${ACTUAL_THREADS} (config: ${THREADS})"
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
    echo "Execute a calibração primeiro (Fase 1) para determinar a quantidade de nós por lance." >&2
    exit 1
fi
if [[ "${PROFILE}" == "v331" && $((GAMES_PER_SHARD % 2)) -ne 0 ]]; then
    echo "ERRO: GAMES_PER_SHARD deve ser par para v331 (cada abertura é jogada nas duas cores)." >&2
    exit 1
fi

WEIGHTS_PATH="${REPO_ROOT}/engine/c/zchezz_${PROFILE}/nnue_weights.bin"
if [[ ! -f "${WEIGHTS_PATH}" ]]; then
    echo "ERRO: Arquivo de pesos não encontrado: ${WEIGHTS_PATH}" >&2
    exit 1
fi

if [[ "${DRIVE_DIR}" == /content/drive/* && ! -d /content/drive/MyDrive ]]; then
    echo "ERRO: Google Drive não montado em /content/drive. Rode a célula de montagem do Drive." >&2
    exit 1
fi
mkdir -p "${DRIVE_DIR}" "${LOCAL_DIR}"

# O Makefile nomeia os binários com .exe também no Linux.
BUILD_DIR="${REPO_ROOT}/engine/build"
SELFPLAY_BIN="${BUILD_DIR}/selfplay.exe"
V331_BIN="${REPO_ROOT}/engine/c/zchezz_v331/zchezz.exe"

if [[ "${PROFILE}" == "v507" ]]; then
    echo "Compilando selfplay nativo (TOOLS_ENGINE=v507)..."
    "${MAKE_CMD}" -C "${BUILD_DIR}" TOOLS_ENGINE=v507 STATIC_FLAG="" selfplay
    [[ -x "${SELFPLAY_BIN}" ]] || { echo "ERRO: build não produziu ${SELFPLAY_BIN}" >&2; exit 1; }
else
    echo "Compilando motor v331 (ENGINE=v331 native)..."
    "${MAKE_CMD}" -C "${BUILD_DIR}" ENGINE=v331 STATIC_FLAG="" native
    [[ -x "${V331_BIN}" ]] || { echo "ERRO: build não produziu ${V331_BIN}" >&2; exit 1; }
fi

# Soma as amostras dos shards desta conta já persistidos no Drive.
# Um shard ilegível é erro: o script para em vez de contar como 0.
count_persisted_samples() {
    python3 - "${REPO_ROOT}/train" "${DRIVE_DIR}/sp_${PROFILE}_a${ACCOUNT_ID}_s*.bin" <<'PYEOF'
import glob, sys
sys.path.insert(0, sys.argv[1])
import dataset
pattern = sys.argv[2]
print(len(dataset.MultiShardSelfplay.from_glob(pattern)) if glob.glob(pattern) else 0)
PYEOF
}

if ! CURRENT_SAMPLES=$(count_persisted_samples); then
    echo "ERRO: não foi possível ler os shards existentes em ${DRIVE_DIR}. Remova ou corrija o shard inválido." >&2
    exit 1
fi
echo "Posições já existentes no Drive para Conta ${ACCOUNT_ID} (${PROFILE}): ${CURRENT_SAMPLES}"

SHARD_IDX=0
while [[ "${CURRENT_SAMPLES}" -lt "${TARGET_POSITIONS}" ]]; do
    SHARD_NAME=$(printf "sp_%s_a%d_s%05d" "${PROFILE}" "${ACCOUNT_ID}" "${SHARD_IDX}")
    DRIVE_BIN="${DRIVE_DIR}/${SHARD_NAME}.bin"
    DRIVE_JSON="${DRIVE_DIR}/${SHARD_NAME}.json"

    # Shard concluído no Drive (.bin e .json finais): pula. Já foi contado acima.
    if [[ -f "${DRIVE_BIN}" && -f "${DRIVE_JSON}" ]]; then
        echo "[PULAR] Shard ${SHARD_NAME} já existe no Drive."
        SHARD_IDX=$((SHARD_IDX + 1))
        continue
    fi
    # .bin sem .json = cópia interrompida. Remove e gera de novo com a mesma seed.
    if [[ -f "${DRIVE_BIN}" ]]; then
        echo "[REFAZER] ${SHARD_NAME}.bin sem sidecar JSON no Drive; gerando de novo."
        CURRENT_SAMPLES=$(( CURRENT_SAMPLES - $(python3 - "${REPO_ROOT}/train" "${DRIVE_BIN}" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
import dataset
print(len(dataset.MultiShardSelfplay([sys.argv[2]])))
PYEOF
) ))
        rm -f "${DRIVE_BIN}"
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
        # v331 via runner UCI. --games é o número de aberturas; cada uma vira
        # 2 jogos (cores invertidas), por isso GAMES_PER_SHARD / 2.
        RUNNER_DIR="${LOCAL_DIR}/runner_${SHARD_NAME}"
        rm -rf "${RUNNER_DIR}"
        mkdir -p "${RUNNER_DIR}"

        python3 "${REPO_ROOT}/tests/run_selfplay.py" \
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
            --seed "${SEED}" \
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

    # Validação: registros íntegros e cabeçalho de proveniência presente.
    VALIDATION_OUTPUT=$(python3 - "${REPO_ROOT}/train" "${LOCAL_BIN}" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
try:
    import dataset
    d = dataset.MultiShardSelfplay([sys.argv[2]])
    if not d.provenance_summary()[0][1].known:
        raise ValueError("shard sem cabeçalho de proveniência")
    print(f"OK:{len(d)}")
except Exception as e:
    print(f"FAIL:{e}")
PYEOF
)

    if [[ "${VALIDATION_OUTPUT}" != OK:* ]]; then
        echo "ERRO: Falha na validação do shard ${LOCAL_BIN}: ${VALIDATION_OUTPUT}" >&2
        rm -f "${LOCAL_BIN}"
        exit 1
    fi

    SHARD_SAMPLES="${VALIDATION_OUTPUT#OK:}"
    POS_PER_SEC=$((SHARD_SAMPLES / DURATION))

    echo "Shard ${SHARD_NAME} validado: ${SHARD_SAMPLES} posições em ${DURATION}s (${POS_PER_SEC} pos/s)."

    # Sidecar JSON de metadados (json.dumps faz o escape das strings).
    SHARD_NAME="${SHARD_NAME}" PROFILE="${PROFILE}" ACCOUNT_ID="${ACCOUNT_ID}" SEED="${SEED}" \
    GAMES_PER_SHARD="${GAMES_PER_SHARD}" NODES="${NODES}" MOVETIME="${MOVETIME}" \
    THREADS="${ACTUAL_THREADS}" MULTIPV="${MULTIPV}" TEMP_PLIES="${TEMP_PLIES}" \
    RANDOM_PLIES="${RANDOM_PLIES}" OPENINGS="${OPENINGS}" GIT_COMMIT="${GIT_COMMIT}" \
    SHARD_SAMPLES="${SHARD_SAMPLES}" DURATION="${DURATION}" CPU_MODEL="${CPU_MODEL}" \
    LOCAL_BIN="${LOCAL_BIN}" REPO_ROOT="${REPO_ROOT}" \
    python3 - > "${LOCAL_JSON}" <<'PYEOF'
import json, os, sys
e = os.environ
sys.path.insert(0, os.path.join(e["REPO_ROOT"], "train"))
import dataset
_, prov = dataset.read_bin_header(e["LOCAL_BIN"])
native = e["PROFILE"] == "v507"
print(json.dumps({
    "shard_name": e["SHARD_NAME"],
    "profile": e["PROFILE"],
    "generator": "engine/build/selfplay.exe" if native else "tests/run_selfplay.py",
    "account_id": int(e["ACCOUNT_ID"]),
    "seed": int(e["SEED"]),
    "games": int(e["GAMES_PER_SHARD"]),
    "time_control": {"nodes": int(e["NODES"])} if native else {"movetime_ms": int(e["MOVETIME"])},
    "threads": int(e["THREADS"]),
    "multipv": int(e["MULTIPV"]) if native else None,
    "temp_plies": int(e["TEMP_PLIES"]) if native else None,
    "temp_final": 0.0 if native else None,
    "opening_mode": "all" if (native and e["OPENINGS"]) else "random",
    "random_plies": int(e["RANDOM_PLIES"]),
    "openings": e["OPENINGS"],
    "provenance": {
        "engine_version": prov.engine_version,
        "weight_fingerprint": prov.weight_fingerprint,
        "weight_path": prov.weight_path,
    },
    "git_commit": e["GIT_COMMIT"],
    "sample_count": int(e["SHARD_SAMPLES"]),
    "duration_seconds": int(e["DURATION"]),
    "positions_per_second": round(int(e["SHARD_SAMPLES"]) / max(1, int(e["DURATION"])), 1),
    "cpu_model": e["CPU_MODEL"],
}, indent=2))
PYEOF

    # Cópia atômica para o Google Drive: .tmp -> mv. O .json vai por último:
    # a presença dele marca o shard como concluído.
    cp "${LOCAL_BIN}" "${DRIVE_DIR}/${SHARD_NAME}.bin.tmp"
    mv "${DRIVE_DIR}/${SHARD_NAME}.bin.tmp" "${DRIVE_BIN}"
    cp "${LOCAL_JSON}" "${DRIVE_DIR}/${SHARD_NAME}.json.tmp"
    mv "${DRIVE_DIR}/${SHARD_NAME}.json.tmp" "${DRIVE_JSON}"

    rm -f "${LOCAL_BIN}" "${LOCAL_JSON}"

    CURRENT_SAMPLES=$((CURRENT_SAMPLES + SHARD_SAMPLES))
    REMAINING=$((TARGET_POSITIONS - CURRENT_SAMPLES))
    if [[ "${REMAINING}" -lt 0 ]]; then REMAINING=0; fi

    if [[ "${POS_PER_SEC}" -gt 0 ]]; then
        ETA_MIN=$((REMAINING / POS_PER_SEC / 60))
    else
        ETA_MIN="?"
    fi

    echo "Progresso: ${CURRENT_SAMPLES}/${TARGET_POSITIONS} posições acumuladas. ETA restante: ~${ETA_MIN} minutos."
    SHARD_IDX=$((SHARD_IDX + 1))
done

echo "=========================================================="
echo "Meta atingida para a Conta ${ACCOUNT_ID} (${PROFILE})."
echo "Total acumulado no Drive: ${CURRENT_SAMPLES} posições."
echo "=========================================================="
