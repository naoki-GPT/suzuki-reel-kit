"""v1.0: two synchronized views in one portable HTML file, with switchable sound."""
import argparse
import base64
import html
import json
import math
from pathlib import Path
import subprocess
import tempfile


def media_info(path):
    result = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)
    ])
    streams = json.loads(result)["streams"]
    lengths = []
    for kind in ("video", "audio"):
        stream = next((s for s in streams if s["codec_type"] == kind), None)
        if stream is None:
            raise ValueError(f"{path.name} に {kind} トラックがありません")
        duration = stream.get("duration")
        if duration not in (None, "N/A"):
            lengths.append(float(duration))
    return min(lengths) if lengths else None


def encode(*arguments):
    subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                    "-y", *map(str, arguments)], check=True)


def data_url(path):
    return "data:video/mp4;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def build(reference, trial, destination, start, duration, title):
    if destination.suffix.lower() != ".html" or not all(map(math.isfinite, [start, duration])) or start < 0 or duration <= 0:
        raise ValueError("有効な開始秒・尺・出力HTMLを指定してください")
    for path, offset in [(reference, start), (trial, 0)]:
        length = media_info(path)
        if length is not None and offset + duration > length + .05:
            raise ValueError(f"{path.name} の尺を超えています（{length:.2f}秒）")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
        folder = Path(temp)
        pair = folder / "pair.mp4"
        ref_sound = folder / "ref.mp4"
        # Both soundtrack versions share identical encoded picture frames.
        fit = "fps=30,scale=360:640:force_original_aspect_ratio=decrease,pad=360:640:(ow-iw)/2:(oh-ih)/2,setsar=1"
        encode("-ss", start, "-i", reference, "-i", trial, "-filter_complex",
               f"[0:v:0]{fit}[left];[1:v:0]{fit}[right];[left][right]hstack=shortest=1[pair]",
               "-map", "[pair]", "-map", "1:a:0", "-t", duration, "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", pair)
        encode("-i", pair, "-ss", start, "-i", reference, "-map", "0:v:0", "-map", "1:a:0",
               "-t", duration, "-c:v", "copy", "-c:a", "aac", ref_sound)
        template = Path(__file__).with_name("review.html").read_text(encoding="utf-8")
        page = template.replace("__SOURCES__", json.dumps([data_url(pair), data_url(ref_sound)]))
        ready = folder / "complete.html"
        ready.write_text(page.replace("__TITLE__", html.escape(title)), encoding="utf-8")
        ready.replace(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "trial", "destination"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--title", default="参考リールと試作の比較")
    build(**vars(parser.parse_args()))
