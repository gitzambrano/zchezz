#!/usr/bin/env bash
# Compatibility entry point. The implementation is in colab/remote.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/remote/run_selfplay_colab.sh" "$@"
