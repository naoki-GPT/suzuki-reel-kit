"""金額の見積り・記録・上限チェック。

H3 の課金でハマる点（調査で判明・2026-08-11）:
- 参考動画は「入力秒数」も出力レートで課金される＝実質二重課金
- 参照画像は5枚まで無料、6枚目から $0.04/枚
- duration を省略すると API 側は5秒（Web画面は8秒）＝同じつもりで6割違う
  → このツールでは duration を必須引数にして省略できないようにしている
- 完了直後は price が空で返ることが多い → 数秒待って再取得する（client 側で対応）
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from .common import LEDGER_PATH, config, log


def usd_to_jpy(usd: float) -> float:
    return usd * config()["usd_jpy"]


def yen(usd: float) -> str:
    return f"約{usd_to_jpy(usd):,.0f}円"


# --------------------------------------------------------------------------- #
# 見積り
# --------------------------------------------------------------------------- #
def estimate(resolution: str, duration: int, *,
             ref_image_count: int = 0,
             ref_video_seconds: float = 0.0,
             n: int = 1) -> dict:
    """1回の実行（n本ぶん）の見積りを出す。

    ref_video_seconds は preflight が ffprobe で実測した合計秒数を渡す。
    """
    cfg = config()
    rate = cfg["price_per_sec_usd"][resolution]

    output_usd = rate * duration
    # 参考動画は入力秒数ぶんも出力レートで課金される
    input_video_usd = rate * ref_video_seconds
    extra_images = max(0, ref_image_count - cfg["free_ref_images"])
    image_usd = extra_images * cfg["extra_ref_image_usd"]

    per_clip = output_usd + input_video_usd + image_usd
    total = per_clip * n

    return {
        "per_clip_usd": round(per_clip, 4),
        "total_usd": round(total, 4),
        "total_jpy": round(usd_to_jpy(total)),
        "n": n,
        "breakdown": {
            "output_usd": round(output_usd, 4),
            "input_video_usd": round(input_video_usd, 4),
            "extra_image_usd": round(image_usd, 4),
            "extra_image_count": extra_images,
            "ref_video_seconds": ref_video_seconds,
            "rate_per_sec_usd": rate,
        },
    }


def print_estimate(est: dict, resolution: str, duration: int) -> None:
    b = est["breakdown"]
    n = est["n"]
    log("COST", f"{resolution} / {duration}s / {n}本 = "
                f"${est['total_usd']:.2f} ({yen(est['total_usd'])})")
    if b["input_video_usd"] > 0:
        log("WARN", f"参考動画 {b['ref_video_seconds']:.1f}秒ぶんが別途課金されます "
                    f"(+${b['input_video_usd'] * n:.2f} / {yen(b['input_video_usd'] * n)})")
    if b["extra_image_count"] > 0:
        log("WARN", f"参照画像の6枚目以降 {b['extra_image_count']}枚が課金されます "
                    f"(+${b['extra_image_usd'] * n:.2f})")


# --------------------------------------------------------------------------- #
# 実費（完了後の usage / price から算出）
# --------------------------------------------------------------------------- #
def actual_from_task(task: dict) -> dict:
    """完了タスクから実費を出す。

    price が返っていればそれを正とする。無ければ usage から自前計算する
    （完了直後は price が空で返ることがあるため）。
    """
    cfg = config()
    resolution = task.get("resolution") or "2K"
    rate = cfg["price_per_sec_usd"].get(resolution, cfg["price_per_sec_usd"]["2K"])
    usage = task.get("usage") or {}

    price = task.get("price")
    if price is None:
        price = (task.get("usage") or {}).get("price")

    if price is not None:
        try:
            usd = float(price)
            return {"usd": round(usd, 4), "jpy": round(usd_to_jpy(usd)),
                    "source": "api_price", "usage": usage}
        except (TypeError, ValueError):
            pass

    out_s = float(usage.get("output_seconds") or 0)
    in_s = float(usage.get("input_seconds") or 0)
    imgs = int(usage.get("input_image_count") or 0)
    if out_s == 0 and in_s == 0:
        # usage も空なら duration にフォールバック
        out_s = float(task.get("duration") or 0)

    usd = rate * (out_s + in_s) + max(0, imgs - cfg["free_ref_images"]) * cfg["extra_ref_image_usd"]
    return {"usd": round(usd, 4), "jpy": round(usd_to_jpy(usd)),
            "source": "computed_from_usage", "usage": usage}


# --------------------------------------------------------------------------- #
# 台帳と日次上限
# --------------------------------------------------------------------------- #
def _today() -> str:
    return _dt.date.today().isoformat()


def append_ledger(record: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    record.setdefault("date", _today())
    record.setdefault("ts", _dt.datetime.now().isoformat(timespec="seconds"))
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def spent_today_jpy() -> float:
    """今日ぶんの支出（円）。実費が確定していない行は見積りで数える。

    注文を出した時点で課金は発生しているので、完了を待たずに計上する
    （途中で落ちた注文をタダ扱いにしない）。

    台帳は追記のみで、1つの task_id につき「created」→「succeeded/failed」と
    複数行になる。**同じ task_id は最後の行だけを採用**して二重計上を防ぐ。
    """
    if not LEDGER_PATH.exists():
        return 0.0
    today = _today()
    latest: dict[str, dict] = {}
    anonymous = 0.0

    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("date") != today or r.get("billed") is False:
            continue
        tid = r.get("task_id")
        if tid:
            latest[str(tid)] = r          # 後勝ち
        else:
            jpy = r.get("actual_jpy")
            anonymous += float(jpy if jpy is not None else (r.get("est_jpy") or 0))

    total = anonymous
    for r in latest.values():
        jpy = r.get("actual_jpy")
        total += float(jpy if jpy is not None else (r.get("est_jpy") or 0))
    return total


def check_daily_limit(est_total_jpy: float) -> tuple[bool, str]:
    """(通してよいか, 表示メッセージ) を返す。"""
    cfg = config()
    limit = cfg["daily_limit_jpy"]
    spent = spent_today_jpy()
    after = spent + est_total_jpy
    msg = f"本日累計: 約{spent:,.0f}円 → 実行後 約{after:,.0f}円 / 上限 {limit:,}円"
    return (after <= limit), msg
