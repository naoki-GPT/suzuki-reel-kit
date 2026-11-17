#!/bin/bash
# v1.4: Mac setup; this never submits a video order or reads an API key.
set -Eeuo pipefail
KIT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
cd "$KIT_DIR"
source "$KIT_DIR/mac_common.sh"
trap 'printf "\n[停止] セットアップが完了していません。上に出た理由を確認し、同じファイルをもう一度開いてください。API課金はありません。\n"; kit_pause' ERR

kit_environment
# Finder/TerminalがRosettaで起動されていたら、Appleシリコンのネイティブ側で再実行。
if [[ "$(sysctl -in sysctl.proc_translated 2>/dev/null || true)" == 1 ]]; then
  printf '[切替] Appleシリコンのネイティブ環境で再開します。\n'
  exec /usr/bin/arch -arm64 /bin/bash "$0" "$@"
fi
KIT_PYTHON="$(kit_find_python || true)"
KIT_READY=yes
[[ -n "$KIT_PYTHON" ]] || KIT_READY=no
command -v ffmpeg >/dev/null 2>&1 || KIT_READY=no
command -v ffprobe >/dev/null 2>&1 || KIT_READY=no

if [[ "${1:-}" == --check-only ]]; then
  if [[ "$KIT_READY" == yes ]]; then
    printf '[OK] Python 3.11・Tk・FFmpeg・FFprobeがあります。インストールやAPI通信はしていません。\n'
    exit 0
  fi
  printf '[未準備] Python 3.11・Tk・FFmpegが必要です。通常の01_setup.commandを開いてください。\n'
  exit 1
fi

if [[ "$KIT_READY" != yes ]]; then
  if [[ "$KIT_AUTO_INSTALL" != yes ]]; then
    printf '[停止] 自動導入の対象はAppleシリコン・macOS 15以降です。\n'
    printf 'このMacでは個別の環境準備が必要です。上のチップ・OS表示を制作担当へ伝えてください。既存のPython 3.11・Tk・FFmpegがそろっていれば実行を試せます。\n'
    kit_pause
    exit 1
  fi
  if ! command -v brew >/dev/null 2>&1; then
    printf '必要なソフトの導入にHomebrewを使います。公式インストーラーが変更内容を表示し、Macのログインパスワードを求める場合があります。\n'
    printf 'Homebrew公式インストーラーを取得して開始しますか？ [y/N]: '
    read -r KIT_APPROVAL
    case "$KIT_APPROVAL" in y|Y|yes|YES) ;; *) printf 'キャンセルしました。API課金はありません。\n'; exit 0 ;; esac
    mkdir -p "$KIT_DIR/.setup"
    curl --fail --location --proto '=https' --tlsv1.2 'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh' -o "$KIT_DIR/.setup/homebrew-install.sh"
    /bin/bash "$KIT_DIR/.setup/homebrew-install.sh"
  fi
  if [[ -x /opt/homebrew/bin/brew ]]; then
    KIT_BREW=/opt/homebrew/bin/brew
  else
    KIT_BREW="$(command -v brew)"
  fi
  printf '[準備] Python 3.11・画面表示用Tk・FFmpegを導入します。時間がかかる場合があります。\n'
  "$KIT_BREW" install python@3.11 python-tk@3.11 ffmpeg
  KIT_PYTHON="$("$KIT_BREW" --prefix python@3.11)/bin/python3.11"
fi

"$KIT_PYTHON" -c 'import sys,tkinter; assert sys.version_info[:2] == (3,11)'
if [[ ! -x "$KIT_DIR/.venv-mac/bin/python" ]]; then
  "$KIT_PYTHON" -m venv "$KIT_DIR/.venv-mac"
fi
"$KIT_DIR/.venv-mac/bin/python" -m pip install -r "$KIT_DIR/requirements.txt"
"$KIT_DIR/.venv-mac/bin/python" "$KIT_DIR/engine/run.py" doctor
# v1.4: 別の参考動画用。動画の取得と文字起こしの道具を確認し、文字起こし用データを先に取得する。課金なし。
"$KIT_DIR/.venv-mac/bin/python" "$KIT_DIR/engine/media.py" check
if ! "$KIT_DIR/.venv-mac/bin/python" "$KIT_DIR/engine/media.py" prepare; then
  printf '[注意] 文字起こし用データをまだ取得できていません。梱包動画の制作には影響しません。通信の良い場所で、このファイルをもう一度開いてください。
'
fi
printf '\n[完了] 次に02_start.commandを開き、MiniMax APIキーを保存してください。\n'
kit_pause
