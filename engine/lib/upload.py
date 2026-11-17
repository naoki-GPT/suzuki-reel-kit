"""手元の素材を MiniMax に先に預ける（files API）。

なぜ URL 直渡しでなく預ける方式を既定にするか:
壊れた画像URLを渡しても「completed」で返って別物が生成され満額請求された、という
報告がある。預け入れなら壊れた素材は**アップロード時点で 400 で弾かれる＝無料**。

預けた素材は7日で失効する。file_id は長期キャッシュしない。
アップロードは副作用が無い（課金されない・重複しても実害なし）のでリトライしてよい。
"""
from __future__ import annotations

import time

import requests

from .common import API_BASE, H3Error, auth_headers, log
from .preflight import Asset, PreflightResult

PURPOSE = "video_generation_input"
MAX_RETRY = 3


def _upload_one(asset: Asset) -> str:
    assert asset.path is not None
    url = f"{API_BASE}/v1/files/upload"
    last_err = ""

    for attempt in range(1, MAX_RETRY + 1):
        try:
            with asset.path.open("rb") as fh:
                r = requests.post(
                    url,
                    headers=auth_headers(),
                    data={"purpose": PURPOSE},
                    files={"file": (asset.path.name, fh)},
                    timeout=300,
                )
        except requests.RequestException as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
            if attempt < MAX_RETRY:
                log("WARN", f"アップロード失敗（{attempt}/{MAX_RETRY}）再試行します: {asset.path.name}")
                time.sleep(2 ** attempt)
                continue
            raise H3Error(f"素材のアップロードに失敗しました: {asset.path.name}\n  {last_err}") from e

        if r.status_code == 400:
            # 素材そのものが不正。ここで弾かれるのは無料。リトライしても無駄
            raise H3Error(
                f"素材が MiniMax 側に拒否されました（課金なし）: {asset.path.name}\n"
                f"  {r.text[:500]}"
            )
        if r.status_code in (401, 403):
            raise H3Error(f"認証に失敗しました（APIキーを確認してください）: HTTP {r.status_code}")
        if r.status_code >= 500 or r.status_code == 429:
            last_err = f"HTTP {r.status_code}: {r.text[:300]}"
            if attempt < MAX_RETRY:
                wait = 2 ** attempt * 3
                log("WARN", f"アップロード再試行（{attempt}/{MAX_RETRY}・{wait}秒待機）: {last_err}")
                time.sleep(wait)
                continue
            raise H3Error(f"素材のアップロードに失敗しました: {asset.path.name}\n  {last_err}")
        if r.status_code != 200:
            raise H3Error(f"素材のアップロードに失敗しました（HTTP {r.status_code}）: "
                          f"{asset.path.name}\n  {r.text[:500]}")

        try:
            data = r.json()
        except ValueError as e:  # noqa: BLE001
            raise H3Error(f"アップロード応答を解析できません: {r.text[:300]}") from e

        base = data.get("base_resp") or {}
        if base.get("status_code") not in (0, None):
            raise H3Error(
                f"素材のアップロードに失敗しました: {asset.path.name}\n"
                f"  code={base.get('status_code')} {base.get('status_msg')}"
            )

        file_id = ((data.get("file") or {}).get("file_id"))
        if not file_id:
            raise H3Error(f"file_id が返りませんでした: {asset.path.name}\n  {r.text[:300]}")
        return str(file_id)

    raise H3Error(f"素材のアップロードに失敗しました: {asset.path.name}\n  {last_err}")


def upload_all(pf: PreflightResult) -> None:
    """ローカル素材を全部預けて、各 Asset に file_id を埋める。"""
    locals_ = pf.local_assets
    if not locals_:
        return
    log("INFO", f"素材を {len(locals_)}件 預けます（7日で失効します）")
    for a in locals_:
        fid = _upload_one(a)
        a.file_id = fid
        log("OK", f"預け完了: {a.path.name} -> mm_file://{fid} ({a.role})")
