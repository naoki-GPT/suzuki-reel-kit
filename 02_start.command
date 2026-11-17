#!/bin/bash
# v1.1: Launch the local UI using the kit's Mac environment.
set -Eeuo pipefail
KIT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
cd "$KIT_DIR"
source "$KIT_DIR/mac_common.sh"
trap 'printf "\n[停止] 起動できませんでした。上の理由を確認してください。\n"; kit_pause' ERR
kit_environment
if [[ "$(sysctl -in sysctl.proc_translated 2>/dev/null || true)" == 1 ]]; then
  exec /usr/bin/arch -arm64 /bin/bash "$0" "$@"
fi
if [[ ! -x "$KIT_DIR/.venv-mac/bin/python" ]]; then
  printf '[未準備] 先に01_setup.commandを開いて初回セットアップをしてください。\n'
  kit_pause
  exit 1
fi
"$KIT_DIR/.venv-mac/bin/python" "$KIT_DIR/engine/run.py" doctor
exec "$KIT_DIR/.venv-mac/bin/python" "$KIT_DIR/engine/app.py"
