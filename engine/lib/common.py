"""minimax-h3 共通ユーティリティ。

workspace 規約:
- コンソール出力は絵文字禁止。[OK] / [INFO] 等のテキストラベル
- .env は load_dotenv(path, override=True)（空の環境変数を上書きするため）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

ROOT = Path(__file__).resolve().parents[2]      # portable kit root
WORKSPACE = ROOT                      # Portable kit; never read a parent project's .env
CONFIG_PATH = ROOT / "config.json"
LEDGER_PATH = ROOT / "ledger" / "costs.jsonl"
STATE_DIR = ROOT / "state"
OUTPUT_DIR = ROOT / "output"

API_BASE = "https://api.minimax.io"
MODEL = "MiniMax-H3"


def log(tag: str, msg: str) -> None:
    """コンソール出力（絵文字禁止・テキストラベル）。"""
    print(f"[{tag}] {msg}", flush=True)


class H3Error(Exception):
    """このツールが投げる業務エラー。main で握って非0終了する。"""


# --------------------------------------------------------------------------- #
# 設定 / 認証
# --------------------------------------------------------------------------- #
_config_cache: dict | None = None


def config() -> dict:
    global _config_cache
    if _config_cache is None:
        _config_cache = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return _config_cache


def api_key() -> str:
    """.env から API キーを読む。空文字も「未設定」として扱う。"""
    try:
        from dotenv import load_dotenv
    except ImportError as e:  # noqa: BLE001
        raise H3Error("python-dotenv が入っていません: pip install python-dotenv") from e

    load_dotenv(WORKSPACE / ".env", override=True)
    key = (os.environ.get("MINIMAX_API_KEY") or "").strip()
    if not key:
        raise H3Error(
            "MINIMAX_API_KEY が未設定です。\n"
            "  1. https://platform.minimax.io でアカウントを作る\n"
            "  2. Developer Dashboard で API キーを発行する\n"
            f"  3. {WORKSPACE / '.env'} に MINIMAX_API_KEY=... を書く"
        )
    return key


def auth_headers() -> dict:
    return {"Authorization": f"Bearer {api_key()}"}


# --------------------------------------------------------------------------- #
# JSON
# --------------------------------------------------------------------------- #
def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# ffprobe（素材の検査と、成果物の検証に使う）
# --------------------------------------------------------------------------- #
def ffprobe(path: Path) -> dict:
    """ffprobe の JSON をそのまま返す。失敗したら H3Error。"""
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        # encoding を明示する。既定だと日本語Windowsは cp932 で復号を試み、
        # 素材のメタデータに cp932 で表せないバイトがあると UnicodeDecodeError で
        # stdout が None になる（実素材のPNGで実際に踏んだ・2026-08-11）
        r = subprocess.run(cmd, capture_output=True, timeout=60,
                           encoding="utf-8", errors="replace")
    except FileNotFoundError as e:  # noqa: BLE001
        raise H3Error("ffprobe が見つかりません（ffmpeg を PATH に通してください）") from e
    except subprocess.TimeoutExpired as e:  # noqa: BLE001
        raise H3Error(f"ffprobe がタイムアウトしました: {path.name}") from e

    if r.returncode != 0:
        raise H3Error(f"ファイルを解析できません（壊れている可能性）: {path.name}\n"
                      f"{(r.stderr or '').strip()}")
    if not r.stdout:
        raise H3Error(f"ffprobe が何も返しませんでした: {path.name}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:  # noqa: BLE001
        raise H3Error(f"ffprobe の出力を解析できません: {path.name}") from e


def probe_summary(path: Path) -> dict:
    """width / height / duration / has_audio / vcodec をまとめて返す。"""
    info = ffprobe(path)
    streams = info.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = None
    for src in (info.get("format", {}), v or {}):
        raw = src.get("duration")
        if raw:
            try:
                duration = float(raw)
                break
            except (TypeError, ValueError):
                pass

    return {
        "width": int(v["width"]) if v and v.get("width") else None,
        "height": int(v["height"]) if v and v.get("height") else None,
        "duration": duration,
        "has_audio": a is not None,
        "vcodec": (v or {}).get("codec_name"),
        "acodec": (a or {}).get("codec_name"),
        "size_bytes": path.stat().st_size,
    }
