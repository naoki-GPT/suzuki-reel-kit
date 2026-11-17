"""MiniMax H3 API クライアント。

リトライしてよい操作と、絶対にしてはいけない操作を明確に分ける:
- 注文作成（POST /v2/video_generation）… **絶対に自動リトライしない**
  通信エラーでも1回目が通っている可能性があり、再送すると2本作られて二重課金になる
- 状態問い合わせ（GET）… リトライしてよい（副作用なし）
- ダウンロード … リトライしてよい。URLが失効していたら作り直さず再問い合わせする
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import requests

from .common import API_BASE, MODEL, H3Error, auth_headers, config, log

TERMINAL = {"succeeded", "failed", "cancelled"}

# MiniMax 独自のエラー番号。HTTPステータスだけでは原因が分からないので中身も見る
ERROR_CODES = {
    1000: ("不明なエラー", True),
    1001: ("リクエストがタイムアウトしました", True),
    1002: ("投げすぎです（レート制限）", True),
    1004: ("認証に失敗しました。APIキーを確認してください", False),
    1008: ("残高が不足しています。platform.minimax.io でチャージしてください", False),
    1024: ("MiniMax側の内部エラー", True),
    1026: ("入力内容がNG判定されました。プロンプトを見直してください", False),
    1027: ("出力内容がNG判定されました。プロンプトを見直してください", False),
    1033: ("MiniMax側のシステムエラー", True),
    1039: ("トークン上限に達しました。プロンプトを短くしてください", False),
    1041: ("同時実行が多すぎます。1本ずつ流してください", True),
    1042: ("不可視文字が多すぎます。プロンプトを整形してください", False),
    2013: ("リクエストの書き方が不正です", False),
    2049: ("APIキーが無効です", False),
    2056: ("使用量の上限に達しました。枠がリセットされるまで待ってください", False),
}

HTTP_MEANING = {
    400: "リクエストが不正です（課金なし）",
    401: "認証に失敗しました。APIキーを確認してください",
    402: "残高が不足しています",
    422: "内容がNG判定されました（センシティブ判定）",
    429: "投げすぎです（レート制限）",
}


def _explain(resp: requests.Response) -> str:
    """HTTPステータスと MiniMax エラー番号の両方から日本語の説明を作る。"""
    parts = [f"HTTP {resp.status_code}"]
    if resp.status_code in HTTP_MEANING:
        parts.append(HTTP_MEANING[resp.status_code])
    try:
        data = resp.json()
    except ValueError:
        data = {}
    base = (data.get("base_resp") or {}) if isinstance(data, dict) else {}
    code = base.get("status_code")
    if code not in (None, 0):
        meaning, retryable = ERROR_CODES.get(int(code), ("未知のエラー番号", False))
        parts.append(f"code={code} {meaning}"
                     f"{'（時間を置けば再試行可）' if retryable else '（再試行しても直りません）'}")
        if base.get("status_msg"):
            parts.append(str(base["status_msg"]))

    # v2 系は {"error": {"type": ..., "message": "... (1000)"}} 形式でも返ってくる
    err = (data.get("error") or {}) if isinstance(data, dict) else {}
    if err:
        msg = str(err.get("message") or "").strip()
        etype = str(err.get("type") or "").strip()
        m = re.search(r"\((\d{4})\)\s*$", msg)
        if m:
            n = int(m.group(1))
            meaning, retryable = ERROR_CODES.get(n, ("未知のエラー番号", False))
            parts.append(f"code={n} {meaning}")
        parts.append(" ".join(x for x in (etype, msg) if x))

    body = resp.text[:300].strip()
    if body and not base and not err:
        parts.append(body)
    return " / ".join(parts)


# --------------------------------------------------------------------------- #
# 注文作成（リトライ禁止）
# --------------------------------------------------------------------------- #
def build_payload(*, prompt: str, duration: int, resolution: str, ratio: str,
                  assets: list, allow_unuploaded: bool = False) -> dict:
    """注文の中身を組み立てる。

    allow_unuploaded は --dry-run 用。実際に送る時は False のままにして、
    ローカルパスがそのまま URL として送られる事故（＝壊れたURLでも満額請求）を止める。
    """
    if not allow_unuploaded:
        missing = [a for a in assets if not a.is_url and not a.file_id]
        if missing:
            names = ", ".join(str(a.path or a.src) for a in missing)
            raise H3Error(
                "内部エラー: 未アップロードのローカル素材を送ろうとしました（送信中止）\n"
                f"  {names}\n"
                "  ※ローカルパスをURLとして送ると、エラーにならず別物が生成され満額請求されます"
            )

    content: list[dict] = [{"type": "text", "text": prompt}]
    for a in assets:
        if a.kind == "image":
            content.append({"type": "image_url",
                            "image_url": {"url": a.api_url()},
                            "role": a.role})
        elif a.kind == "video":
            content.append({"type": "video_url",
                            "video_url": {"url": a.api_url()},
                            "role": a.role})
        elif a.kind == "audio":
            content.append({"type": "audio_url",
                            "audio_url": {"url": a.api_url()},
                            "role": a.role})
    return {
        "model": MODEL,
        "content": content,
        # duration は必ず明示する。省略すると API 側は5秒・Web画面は8秒で値段が変わる
        "duration": duration,
        "resolution": resolution,
        "ratio": ratio,
    }


def create_task(payload: dict) -> str:
    """注文を出して task_id を返す。**この関数は自動リトライしない。**"""
    url = f"{API_BASE}/v2/video_generation"
    headers = {**auth_headers(), "Content-Type": "application/json"}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=120)
    except requests.RequestException as e:  # noqa: BLE001
        raise H3Error(
            "注文の送信中に通信エラーが起きました。\n"
            "  **自動で再送はしません。**1回目が通っている可能性があり、\n"
            "  再送すると2本作られて二重課金になります。\n"
            "  platform.minimax.io のダッシュボードでタスクが作られていないか確認してから、\n"
            "  無ければもう一度実行してください。\n"
            f"  詳細: {type(e).__name__}: {e}"
        ) from e

    if r.status_code != 200:
        raise H3Error(f"注文を受け付けてもらえませんでした: {_explain(r)}")

    try:
        data = r.json()
    except ValueError as e:  # noqa: BLE001
        raise H3Error(f"応答を解析できません: {r.text[:300]}") from e

    base = data.get("base_resp") or {}
    if base.get("status_code") not in (0, None):
        raise H3Error(f"注文を受け付けてもらえませんでした: {_explain(r)}")

    task_id = data.get("task_id") or (data.get("task") or {}).get("id")
    if not task_id:
        raise H3Error(f"task_id が返りませんでした: {r.text[:300]}")
    return str(task_id)


# --------------------------------------------------------------------------- #
# 状態問い合わせ（リトライ可）
# --------------------------------------------------------------------------- #
def get_task(task_id: str, *, max_retry: int = 4) -> dict:
    url = f"{API_BASE}/v2/query/video_generation/{task_id}"
    last = ""
    for attempt in range(1, max_retry + 1):
        try:
            r = requests.get(url, headers=auth_headers(), timeout=60)
        except requests.RequestException as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
            time.sleep(min(2 ** attempt, 20))
            continue

        if r.status_code == 200:
            try:
                data = r.json()
            except ValueError:
                last = f"解析不能: {r.text[:200]}"
                time.sleep(min(2 ** attempt, 20))
                continue
            return data.get("task") or data

        if r.status_code in (401, 402, 404):
            raise H3Error(f"注文の状態を取得できません（task_id={task_id}）: {_explain(r)}")

        last = _explain(r)
        time.sleep(min(2 ** attempt, 20))

    raise H3Error(f"注文の状態を取得できません（task_id={task_id}）: {last}")


def check_key() -> None:
    """APIキーが有効かを課金ゼロで確かめる。

    存在しない task_id を問い合わせるだけ。キーが無効なら401、
    有効なら「そんなタスクは無い」（404/400）が返る。生成は一切走らない。
    """
    # 形式としては妥当だが存在しない task_id。生成は走らないので課金ゼロ
    url = f"{API_BASE}/v2/query/video_generation/000000000000001"
    try:
        r = requests.get(url, headers=auth_headers(), timeout=30)
    except requests.RequestException as e:  # noqa: BLE001
        raise H3Error(f"MiniMax に接続できません: {type(e).__name__}: {e}") from e

    try:
        data = r.json()
    except ValueError:
        data = {}
    code = ((data.get("base_resp") or {}).get("status_code")) if isinstance(data, dict) else None

    # --- 無効と断定できる ---------------------------------------------------
    if r.status_code in (401, 403) or code in (1004, 2049):
        raise H3Error(
            f"APIキーが無効です: {_explain(r)}\n"
            "  .env の MINIMAX_API_KEY を確認してください（前後の空白や改行に注意）"
        )
    # --- 有効だが残高が無い -------------------------------------------------
    if r.status_code == 402 or code == 1008:
        raise H3Error(
            "APIキーは通りましたが、残高が不足しています。\n"
            "  platform.minimax.io の Pay-as-you-go > Balance からチャージしてください"
        )
    # --- 有効と断定できる（認証を通過して「そんなタスクは無い」まで進んだ）---
    # MiniMax は存在しない task_id に対して HTTP 500 + "record not found" を返す。
    # 認証を抜けてレコード検索まで進んだ証拠なので、これはキーが有効という意味になる
    body = (r.text or "").lower()
    if "record not found" in body or "not found" in body:
        log("OK", f"APIキーは有効です（存在しないタスクを正しく「無い」と返した / 課金ゼロ）")
        return
    if r.status_code in (200, 400, 404, 422) or code in (0, 2013):
        log("OK", f"APIキーは有効です（HTTP {r.status_code} / 課金ゼロ）")
        return

    # --- それ以外は判定できない（500等をOK扱いにしない）---------------------
    raise H3Error(
        f"APIキーの有効性を判定できませんでした: {_explain(r)}\n"
        "  ※MiniMax側の一時的な不調の可能性があります。少し待って再実行してください。\n"
        "  （これは「無効」という意味ではありません。判定できなかっただけです）"
    )


def poll(task_id: str) -> dict:
    """完了するまで待つ。既定10秒間隔・上限30分。"""
    cfg = config()
    interval = cfg["poll_interval_sec"]
    timeout = cfg["timeout_sec"]
    started = time.monotonic()
    last_status = ""

    while True:
        task = get_task(task_id)
        status = (task.get("status") or "").lower()
        if status != last_status:
            log("INFO", f"状態: {status or '(不明)'}  (task_id={task_id})")
            last_status = status

        if status in TERMINAL:
            return task

        elapsed = time.monotonic() - started
        if elapsed > timeout:
            raise H3Error(
                f"待ち時間が上限（{timeout // 60}分）を超えました。注文自体は生きています。\n"
                f"  操作画面の「途中から再開」で再接続してください。注文番号: {task_id}"
            )
        if int(elapsed) % 60 < interval and elapsed > interval:
            log("INFO", f"待機中... {int(elapsed)}秒経過（完成まで7分前後かかります）")
        time.sleep(interval)


def settle_price(task_id: str, task: dict) -> dict:
    """完了直後は price が空で返ることが多いので、少し待って取り直す。"""
    if task.get("price") is not None:
        return task
    wait = config()["price_settle_wait_sec"]
    time.sleep(wait)
    try:
        return get_task(task_id)
    except H3Error:
        return task


# --------------------------------------------------------------------------- #
# ダウンロード（失効したら作り直さず再問い合わせ）
# --------------------------------------------------------------------------- #
def download(task_id: str, task: dict, dest: Path, *, max_retry: int = 3) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = ((task.get("content") or {}).get("url"))
    if not url:
        raise H3Error(f"完成した動画のURLが見つかりません（task_id={task_id}）")

    for attempt in range(1, max_retry + 1):
        try:
            with requests.get(url, timeout=600, stream=True) as r:
                if r.status_code >= 400:
                    raise requests.RequestException(f"HTTP {r.status_code}")
                tmp = dest.with_suffix(dest.suffix + ".part")
                with tmp.open("wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        if chunk:
                            f.write(chunk)
                tmp.replace(dest)
            return dest
        except requests.RequestException as e:  # noqa: BLE001
            if attempt >= max_retry:
                raise H3Error(
                    f"動画のダウンロードに失敗しました（task_id={task_id}）\n"
                    f"  **作り直さないでください。**続きから再開できます:\n"
                    f"  操作画面の「途中から再開」を使ってください。注文番号: {task_id}\n"
                    f"  詳細: {e}"
                ) from e
            # URLは時間で失効する。作り直さず、新しいURLをもらい直す
            log("WARN", f"ダウンロード失敗（{attempt}/{max_retry}）。URLを取り直します: {e}")
            time.sleep(3)
            task = get_task(task_id)
            new_url = ((task.get("content") or {}).get("url"))
            if new_url:
                url = new_url

    raise H3Error(f"動画のダウンロードに失敗しました（task_id={task_id}）")
