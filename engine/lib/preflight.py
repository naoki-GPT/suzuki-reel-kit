"""注文を出す前の全チェック。このツールの心臓部。

なぜここが重要か（調査で判明した事故・2026-08-11）:
- 存在しない画像URLを渡しても「completed」で返り、別物の動画が生成され満額請求された報告がある
  → 壊れた素材を絶対にAPIまで到達させない
- first_frame/last_frame と reference_* の併用は仕様上不可だが、両方送ると
  エラーにならず片方が黙って捨てられて満額請求される
  → 自前で排他チェックする
- 一方、書き方が違って弾かれた場合（HTTP 400）は課金されない
  → 手元のチェックを厚くするほど事故はタダで防げる。ここに寄せる

見つかった問題は1件ずつ止めず、まとめて全部表示してから止める。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import requests

from .common import H3Error, config, log, probe_summary

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
VIDEO_EXT = {".mp4", ".mov"}
AUDIO_EXT = {".wav", ".mp3"}

IMAGE_ROLES = {"first_frame", "last_frame", "reference_image"}
FRAME_ROLES = {"first_frame", "last_frame"}
REFERENCE_ROLES = {"reference_image", "reference_video", "reference_audio"}

VIDEO_CODECS_OK = {"h264", "hevc", "h265"}


@dataclass
class Asset:
    kind: str            # image / video / audio
    role: str            # first_frame / last_frame / reference_image / ...
    src: str             # 元の指定（ローカルパス or URL）
    is_url: bool
    path: Path | None = None
    probe: dict | None = None
    file_id: str | None = None   # アップロード後に埋まる

    def api_url(self) -> str:
        """API に渡す値。ローカルは mm_file:// に化けている前提。

        未アップロードのローカル素材はプレースホルダを返す。これがそのまま
        API に届くと「壊れたURLでも満額請求」の事故になるため、
        client.build_payload 側でも二重に止める。
        """
        if self.file_id:
            return f"mm_file://{self.file_id}"
        if not self.is_url:
            name = self.path.name if self.path else self.src
            return f"mm_file://<未アップロード:{name}>"
        return self.src


@dataclass
class PreflightResult:
    assets: list[Asset] = field(default_factory=list)
    ref_video_seconds: float = 0.0
    ref_image_count: int = 0

    @property
    def local_assets(self) -> list[Asset]:
        return [a for a in self.assets if not a.is_url]


# --------------------------------------------------------------------------- #
def _check_url_reachable(url: str, errors: list[str]) -> None:
    """URLが本当に生きているかを確かめる（事故1の直接対策）。

    HEAD を蹴るサーバがあるので、失敗したら1バイトだけ GET して確かめる。
    """
    try:
        r = requests.head(url, timeout=15, allow_redirects=True)
        if r.status_code >= 400:
            r = requests.get(url, timeout=15, stream=True,
                             headers={"Range": "bytes=0-0"}, allow_redirects=True)
        if r.status_code >= 400:
            errors.append(
                f"URL に到達できません（HTTP {r.status_code}）: {url}\n"
                f"    ※壊れたURLでも課金される事例があるため、ここで止めます"
            )
            return
        r.close()
    except requests.RequestException as e:  # noqa: BLE001
        errors.append(f"URL に到達できません（{type(e).__name__}）: {url}")


def _check_local_asset(a: Asset, errors: list[str]) -> None:
    cfg = config()["limits"]
    p = a.path
    assert p is not None

    if not p.exists():
        errors.append(f"ファイルがありません: {p}")
        return
    if not p.is_file():
        errors.append(f"ファイルではありません: {p}")
        return

    ext = p.suffix.lower()
    allowed = {"image": IMAGE_EXT, "video": VIDEO_EXT, "audio": AUDIO_EXT}[a.kind]
    if ext not in allowed:
        errors.append(f"{a.kind} で使えない拡張子です（{ext}）: {p.name} / 対応={sorted(allowed)}")
        return

    size_mb = p.stat().st_size / (1024 * 1024)
    max_mb = {"image": cfg["image_max_mb"], "video": cfg["video_max_mb"],
              "audio": cfg["audio_max_mb"]}[a.kind]
    if size_mb > max_mb:
        errors.append(f"{a.kind} が大きすぎます（{size_mb:.1f}MB > {max_mb}MB）: {p.name}")
        return
    if p.stat().st_size == 0:
        errors.append(f"ファイルが空です: {p.name}")
        return

    try:
        info = probe_summary(p)
    except H3Error as e:  # noqa: BLE001
        if a.kind == "image" and ext in {".heic", ".heif"}:
            log("WARN", f"{p.name} は寸法を確認できませんでした（HEIC/HEIF）。チェックを飛ばします")
            return
        errors.append(str(e))
        return
    a.probe = info

    if a.kind == "image":
        w, h = info["width"], info["height"]
        if not w or not h:
            errors.append(f"画像の寸法を取得できません: {p.name}")
            return
        lo, hi = cfg["image_side_min_px"], cfg["image_side_max_px"]
        if not (lo <= w <= hi and lo <= h <= hi):
            errors.append(f"画像の辺が範囲外です（{w}x{h} / 許容 {lo}〜{hi}px）: {p.name}")
        ratio = w / h
        if not (cfg["image_ratio_min"] <= ratio <= cfg["image_ratio_max"]):
            errors.append(
                f"画像の縦横比が範囲外です（{ratio:.2f} / 許容 "
                f"{cfg['image_ratio_min']}〜{cfg['image_ratio_max']}）: {p.name}"
            )

    elif a.kind == "video":
        d = info["duration"]
        if d is None:
            errors.append(f"動画の長さを取得できません: {p.name}")
        elif not (cfg["clip_sec_min"] <= d <= cfg["clip_sec_max"]):
            errors.append(
                f"参考動画の長さが範囲外です（{d:.1f}秒 / 許容 "
                f"{cfg['clip_sec_min']}〜{cfg['clip_sec_max']}秒）: {p.name}"
            )
        vc = (info["vcodec"] or "").lower()
        if vc and vc not in VIDEO_CODECS_OK:
            errors.append(f"参考動画のコーデックが非対応です（{vc} / 対応=H.264/H.265）: {p.name}")

    elif a.kind == "audio":
        d = info["duration"]
        if d is None:
            errors.append(f"音声の長さを取得できません: {p.name}")
        elif not (cfg["clip_sec_min"] <= d <= cfg["clip_sec_max"]):
            errors.append(
                f"参考音声の長さが範囲外です（{d:.1f}秒 / 許容 "
                f"{cfg['clip_sec_min']}〜{cfg['clip_sec_max']}秒）: {p.name}"
            )


# --------------------------------------------------------------------------- #
def run(*, prompt: str, duration: int, resolution: str, ratio: str,
        first_frame: str | None = None, last_frame: str | None = None,
        ref_images: list[str] | None = None,
        ref_videos: list[str] | None = None,
        ref_audios: list[str] | None = None) -> PreflightResult:
    """全チェックを通す。1件でも問題があれば H3Error（＝課金ゼロで終了）。"""
    cfg = config()
    lim = cfg["limits"]
    errors: list[str] = []

    # --- 基本パラメータ ---------------------------------------------------- #
    if not prompt or not prompt.strip():
        errors.append("プロンプトが空です")
    elif len(prompt) > lim["prompt_max_chars"]:
        errors.append(f"プロンプトが長すぎます（{len(prompt)}字 > {lim['prompt_max_chars']}字）")

    if not isinstance(duration, int):
        errors.append(f"長さは整数で指定してください: {duration}")
    elif not (lim["duration_min"] <= duration <= lim["duration_max"]):
        errors.append(f"長さが範囲外です（{duration}秒 / 許容 "
                      f"{lim['duration_min']}〜{lim['duration_max']}秒）")

    if resolution not in cfg["price_per_sec_usd"]:
        errors.append(f"画質の指定が不正です（{resolution} / 許容 "
                      f"{sorted(cfg['price_per_sec_usd'])}）")

    if ratio not in cfg["ratios"]:
        errors.append(f"縦横比の指定が不正です（{ratio} / 許容 {cfg['ratios']}）")

    # --- 素材を組み立てる -------------------------------------------------- #
    result = PreflightResult()

    def add(kind: str, role: str, src: str) -> None:
        is_url = src.lower().startswith(("http://", "https://", "mm_file://"))
        result.assets.append(Asset(
            kind=kind, role=role, src=src, is_url=is_url,
            path=None if is_url else Path(src).expanduser(),
        ))

    if first_frame:
        add("image", "first_frame", first_frame)
    if last_frame:
        add("image", "last_frame", last_frame)
    for s in (ref_images or []):
        add("image", "reference_image", s)
    for s in (ref_videos or []):
        add("video", "reference_video", s)
    for s in (ref_audios or []):
        add("audio", "reference_audio", s)

    # --- 排他チェック（事故3） --------------------------------------------- #
    roles = {a.role for a in result.assets}
    if (roles & FRAME_ROLES) and (roles & REFERENCE_ROLES):
        errors.append(
            "「始点/終点の画像」と「参考素材」は同時に使えません。\n"
            f"    指定されたもの: 始点終点={sorted(roles & FRAME_ROLES)} / "
            f"参考={sorted(roles & REFERENCE_ROLES)}\n"
            "    ※APIはこれをエラーにせず、片方を黙って捨てて満額請求します。ここで止めます"
        )

    # --- 枚数・本数 -------------------------------------------------------- #
    n_img = sum(1 for a in result.assets if a.kind == "image")
    n_vid = sum(1 for a in result.assets if a.kind == "video")
    n_aud = sum(1 for a in result.assets if a.kind == "audio")
    if n_img > lim["max_ref_images"]:
        errors.append(f"画像が多すぎます（{n_img}枚 > {lim['max_ref_images']}枚）")
    if n_vid > lim["max_ref_videos"]:
        errors.append(f"参考動画が多すぎます（{n_vid}本 > {lim['max_ref_videos']}本）")
    if n_aud > lim["max_ref_audios"]:
        errors.append(f"参考音声が多すぎます（{n_aud}本 > {lim['max_ref_audios']}本）")
    # 公式の合計上限（2026-09-04 確認）: 画像・動画・音声を合わせて12個まで
    n_total = n_img + n_vid + n_aud
    if n_total > lim["max_ref_files_total"]:
        errors.append(f"素材が多すぎます（合計 {n_total}個 > "
                      f"{lim['max_ref_files_total']}個 / 画像{n_img}・動画{n_vid}・音声{n_aud}）")

    # --- 個別チェック ------------------------------------------------------ #
    for a in result.assets:
        if a.is_url:
            if a.src.lower().startswith("mm_file://"):
                continue  # 既にアップロード済みの参照。到達性は確認できない
            _check_url_reachable(a.src, errors)
        else:
            _check_local_asset(a, errors)

    # --- 合計尺（参考動画・音声はそれぞれ合計15秒以内） --------------------- #
    vid_total = sum((a.probe or {}).get("duration") or 0
                    for a in result.assets if a.kind == "video")
    aud_total = sum((a.probe or {}).get("duration") or 0
                    for a in result.assets if a.kind == "audio")
    if vid_total > lim["clip_total_sec_max"]:
        errors.append(f"参考動画の合計が長すぎます（{vid_total:.1f}秒 > "
                      f"{lim['clip_total_sec_max']}秒）")
    if aud_total > lim["clip_total_sec_max"]:
        errors.append(f"参考音声の合計が長すぎます（{aud_total:.1f}秒 > "
                      f"{lim['clip_total_sec_max']}秒）")

    if errors:
        body = "\n".join(f"  - {e}" for e in errors)
        raise H3Error(
            f"注文前チェックで {len(errors)}件 の問題が見つかりました（課金ゼロで停止）\n{body}"
        )

    result.ref_video_seconds = vid_total
    result.ref_image_count = n_img
    return result
