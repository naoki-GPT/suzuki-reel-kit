"""プロンプトの型と、書き方の自動チェック。

出典は2つあり、性質が違う。混ぜないこと。

【公式書式】= MiniMax公式のプロンプト作成ガイド（2026-09-04 確認）
  https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md
- 必須3項目: 本文 / overall_soundscape / non_diegetic_music
- 画像を渡す注文（I2VA/FL2VA/L2VA）は、先頭に**位置合わせの一文**を置く
    For the target video, at 0.00 seconds into the target video,
    <Picture 1> (from [Shot 1]) is fully referenced.
- ショットは [Shot 1] から。2つ目以降は時刻が要る（[Shot 2] At 00:03.500, ...）
- カメラは「種類＋振幅＋速度」の3点セット
    種類 = Zoom / Push / Pan / Truck / Tilt / Pedestal / Arc / Tracking /
           Static / Shake / POV / Roll
    振幅 = with small amplitude / with large amplitude
    速度 = at slow speed / at fast speed
- 話者は登場順に S1 / S2。同時発話は (S1,S2)。全ショットで同じ人に同じIDを固定
- セリフは `(S1) says: <d>[Japanese] しゃべる言葉</d>`
  画面外のナレーションは `says in an off-screen voiceover` と書き、
  続けて「唇は閉じたまま」を明記する（書かないと口が動く）
- セリフは一字一句そのまま。訳したり書き換えたりしない
- 音が無い場合は "none" ではなく **N/A** と書く
- 音楽は雰囲気語でなく「楽器・速度・リズム・強弱の変化」で書く

【実測の癖】= ウチの実叩きで分かったこと（公式には書かれていない）
- セリフは5秒あたり1〜2文まで。超えると早口・口とのズレ（8/11）
- 形容詞と効果は増幅される。`mildly amused` → 明確な笑顔（8/11）
- 発光の語は絵が暴れる。「どこを照らすか」に限定して書く（8/11 目が発光）
- 画面に読める文字は一字一句指定する。しないと商品名を幻覚する（8/18）
- 角度の指示は減衰する。40〜50度と書いて出るのは30度前後（8/18）
- 参照画像は表情まで運ぶ。否定形では打ち消せない（8/11）
"""
from __future__ import annotations

import re

from .common import log

DIALOGUE_RE = re.compile(r"<d>\s*(?:\[(?P<lang>[^\]]+)\]\s*)?(?P<line>.*?)</d>", re.DOTALL)
SENTENCE_END = re.compile(r"[。．！？!?…]+")

# 公式のショット見出し。2つ目以降は時刻が要る
SHOT_RE = re.compile(r"\[Shot\s+(\d+)\]([^\n]*)", re.IGNORECASE)
TIMECODE_RE = re.compile(r"\b\d{2}:\d{2}\.\d{2,3}\b")

# 公式のカメラ語彙
CAMERA_TYPES = ("zoom", "push", "pan", "truck", "tilt", "pedestal", "arc",
                "tracking", "static", "shake", "pov", "roll")
AMPLITUDE_RE = re.compile(r"with (small|large) amplitude", re.IGNORECASE)
SPEED_RE = re.compile(r"at (slow|fast) speed", re.IGNORECASE)

# 位置合わせの一文（画像を渡す注文で必要）
ALIGN_RE = re.compile(r"fully referenced", re.IGNORECASE)

# 画面に出す文字（公式書式では英語のダブルクォートで囲む）
ONSCREEN_TEXT_RE = re.compile(r'"[^"\n]{1,80}"')
# 縦の位置の指定があるか。
# 9/7実測: 「中央に」「幅の60%」と書いても、縦をフレーム高さの割合で書かないと
# 文字が上3分の1に寄り、下半分が丸ごと空いた。効くのは「縦がどこか」の明示。
VERTICAL_RE = re.compile(
    r"(frame height|vertically|vertical cent(?:re|er)|upper third|lower third|"
    r"middle third|from the top of the frame|from the bottom of the frame)",
    re.IGNORECASE)

# 実測: 増幅されて事故った語
GLOW_WORDS = ("glow", "glowing", "luminous", "radiant", "shining", "shines",
              "pulses", "pulsing", "emit", "emitting")
EMOTION_WORDS = ("amused", "cheerful", "delighted", "excited", "smiling",
                 "grinning", "joyful", "playful", "angry", "furious")

TEMPLATE = """\
{画像を渡す注文なら、この一文を必ず先頭に置く（公式書式）:}
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

[Shot 1] {場面・被写体・光。形は比率、向きは時計方位、画角は占有率で書く}

Action: {動作。表情を変えたくないなら明示的に抑える}

Camera: The camera {pushes in/pans left/tilts down/holds static} with {small|large} amplitude at {slow|fast} speed toward {対象}.

Effects: {エフェクト。光り物は「どこを照らすか」に限定して書く}

Character (S1): {年齢・性別・声質・話し方。ここは口に出す言葉ではなく“どんな声か”}
{2カット目以降は: Match the voice in the reference audio exactly.}

Dialogue:
(S1) says: <d>[Japanese] {実際にしゃべる言葉だけ}</d>

overall_soundscape: {環境音を1〜4文。無音にしたいときだけ N/A}
non_diegetic_music: {楽器・速度・リズム・強弱。音楽を入れないなら N/A}
"""


def dialogue_lines(prompt: str) -> list[tuple[str, str]]:
    """(言語, セリフ) のリストを返す。"""
    return [(m.group("lang") or "", (m.group("line") or "").strip())
            for m in DIALOGUE_RE.finditer(prompt)]


def check(prompt: str, duration: int, *, has_image: bool = False) -> list[str]:
    """書き方の警告を返す（止めはしない・気づかせるだけ）。

    has_image: 始点/終点/参照の画像を渡す注文かどうか（位置合わせ文の要否）
    """
    warns: list[str] = []
    low = prompt.lower()
    # 映像の記述だけを見たい検査のための切り出し（音の欄は対象外）
    visual = low.split("overall_soundscape")[0]
    lines = dialogue_lines(prompt)

    # ------------------------------------------------------------------ #
    # 公式書式
    # ------------------------------------------------------------------ #
    # 画像を渡すのに位置合わせの一文が無い
    if has_image and not ALIGN_RE.search(prompt):
        warns.append(
            "画像を渡す注文ですが、公式の位置合わせ文がありません。先頭に置いてください: "
            "「For the target video, at 0.00 seconds into the target video, "
            "<Picture 1> (from [Shot 1]) is fully referenced.」"
        )

    # 2つ目以降のショットに時刻が無い
    for num, rest in SHOT_RE.findall(prompt):
        if num != "1" and not TIMECODE_RE.search(rest):
            warns.append(
                f"[Shot {num}] に時刻がありません。2つ目以降のショットは "
                "「[Shot 2] At 00:03.500, ...」の形（MM:SS.SSS）で書きます"
            )

    # カメラの3点セット
    if "camera" in low:
        # 活用形も認める（push / pushes / pushing / tracked …）
        if not any(re.search(rf"\b{t}(?:e?s|ing|ed)?\b", low) for t in CAMERA_TYPES):
            warns.append(
                "カメラの動きの種類がありません。公式の語彙で書いてください: "
                "Zoom / Push / Pan / Truck / Tilt / Pedestal / Arc / Tracking / "
                "Static / Shake / POV / Roll"
            )
        if not AMPLITUDE_RE.search(prompt):
            warns.append("カメラの振幅がありません（with small amplitude / with large amplitude）")
        if not SPEED_RE.search(prompt):
            warns.append("カメラの速度がありません（at slow speed / at fast speed）")

    # セリフの書式
    for lang, line in lines:
        if not lang:
            warns.append(f"言語指定のない <d> タグがあります: 「{line[:20]}...」"
                         " → <d>[Japanese] ...</d> のように書いてください")
        if not line:
            warns.append("中身が空の <d> タグがあります")
    if lines and "says" not in low:
        warns.append(
            "セリフの前に says がありません。公式書式は "
            "「(S1) says: <d>[Japanese] ...</d>」です"
            "（画面外の語りは says in an off-screen voiceover ＋「唇は閉じたまま」）"
        )

    # セリフらしき日本語があるのにタグが無い
    if not lines and re.search(r"[「『].+?[」』]", prompt):
        warns.append(
            "カギカッコのセリフがありますが <d>[Japanese] ...</d> タグがありません。"
            "タグで囲まないと、しゃべらせたい言葉として扱われないことがあります"
        )

    # 画面に出す文字の扱い（9/7実測で確立）
    onscreen = ONSCREEN_TEXT_RE.findall(prompt)
    if onscreen:
        if not VERTICAL_RE.search(visual):
            warns.append(
                f"画面に出す文字が{len(onscreen)}件ありますが、縦の位置の指定がありません。"
                "H3は「何を書くか」は守りますが「縦のどこに置くか」は聞き流します"
                "（9/7実測: 「中央に」「幅の60%」と書いても上3分の1に寄り、下半分が空いた）。"
                "縦はフレーム高さの割合で書く。"
                "例: its centre sits at 50 percent of the frame height"
            )
        if len(onscreen) > 1 and "only one line" not in low and "one line at a time" not in low:
            warns.append(
                f"画面に出す文字が{len(onscreen)}件あります。同時に出したくないなら"
                "「一度に1行だけ」を明記してください"
                "（9/7実測: 明記しても2行が重なった瞬間があった＝行数は減らすほど安全）"
            )

    # 音の指定
    if "overall_soundscape" not in low:
        warns.append(
            "overall_soundscape がありません。H3は指定しないと勝手な音を付けます"
            "（無音にしたいときは N/A と書く）"
        )
    if "non_diegetic_music" not in low:
        warns.append("non_diegetic_music がありません（音楽を入れないなら N/A と書く）")

    # 「なし」は none ではなく N/A（公式）
    for field in ("overall_soundscape", "non_diegetic_music"):
        m = re.search(rf"{field}\s*:\s*([^\n]*)", low)
        if m and re.match(r"\s*(none|no music|no sound|なし)\b", m.group(1)):
            warns.append(
                f"{field} を「なし」と書いていますが、公式書式では N/A です"
            )

    # 音楽を入れるなら歌の有無を明記
    music_m = re.search(r"non_diegetic_music\s*:\s*([^\n]*)", low)
    music_off = bool(music_m and re.match(r"\s*(n/a|none|no music|なし)\b", music_m.group(1)))
    if music_m and not music_off and "no vocals" not in low and not lines:
        warns.append("音楽を指定していますが 'no vocals' がありません。"
                     "歌が要らない場合は明記してください")

    # ------------------------------------------------------------------ #
    # 実測の癖
    # ------------------------------------------------------------------ #
    # 5秒あたり1〜2文の目安
    total_sentences = sum(
        max(1, len([s for s in SENTENCE_END.split(line) if s.strip()]))
        for _, line in lines if line
    )
    if total_sentences:
        allowed = max(1, round(duration / 5 * 2))
        if total_sentences > allowed:
            warns.append(
                f"セリフが {total_sentences}文 あります（{duration}秒なら目安 {allowed}文まで）。"
                "早口になったり口と音がズレやすくなります"
            )

    hit_glow = [w for w in GLOW_WORDS if re.search(rf"\b{w}\b", visual)]
    if hit_glow:
        warns.append(
            f"発光・脈動の語があります（{', '.join(hit_glow[:3])}）。"
            "H3は効果を強めに絵にします（8/11に目そのものが発光）。"
            "「何が光るか」ではなく「どこを照らすか」で書いてください"
        )

    hit_emo = [w for w in EMOTION_WORDS if re.search(rf"\b{w}\b", visual)]
    if hit_emo:
        warns.append(
            f"感情の形容詞があります（{', '.join(hit_emo[:3])}）。"
            "H3は形容を増幅します（mildly amused → 明確な笑顔）。弱めに書くか、"
            "表情を変えたくないなら参照画像側で決めてください"
        )

    return warns


def print_warnings(prompt: str, duration: int, *, has_image: bool = False) -> None:
    for w in check(prompt, duration, has_image=has_image):
        log("WARN", w)
