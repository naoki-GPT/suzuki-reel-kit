#!/bin/bash
# v1.1: Shared Mac paths. No installs or API calls when sourced.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

kit_find_python() {
  local candidate
  for candidate in /opt/homebrew/bin/python3.11 /usr/local/bin/python3.11 /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11; do
    if [[ -x "$candidate" ]] && "$candidate" -c 'import sys,tkinter; assert sys.version_info[:2] == (3,11)' >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  if command -v python3.11 >/dev/null 2>&1 && python3.11 -c 'import tkinter' >/dev/null 2>&1; then
    command -v python3.11
    return 0
  fi
  return 1
}

kit_pause() {
  if [[ -t 0 ]]; then
    printf '\nEnterキーでこの処理を閉じます。'
    read -r _kit_answer
  fi
}

kit_environment() {
  local os_type major
  os_type="$(uname -s)"
  if [[ "$os_type" != Darwin ]]; then
    printf '[停止] この起動ファイルはMac用です。Windowsは .bat を使ってください。\n'
    return 1
  fi
  KIT_CPU="$(uname -m)"
  KIT_MACOS="$(sw_vers -productVersion)"
  major="${KIT_MACOS%%.*}"
  KIT_AUTO_INSTALL=no
  if [[ "$KIT_CPU" == arm64 && "$major" =~ ^[0-9]+$ && "$major" -ge 15 ]]; then
    KIT_AUTO_INSTALL=yes
  fi
  printf '[環境] Mac / %s / macOS %s\n' "$KIT_CPU" "$KIT_MACOS"
}
