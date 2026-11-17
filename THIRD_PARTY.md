# 同梱フォント

Arimo（可変フォント、字幕では太さ700を使用）。SIL Open Font License 1.1。
配布元：https://github.com/google/fonts/tree/main/ofl/arimo
フォント：projects/packing/scripts/Arimo.ttf
著作権表記・ライセンス全文：projects/packing/scripts/Arimo-OFL.txt

MicrosoftのArialフォントは同梱していません。PythonライブラリやFFmpeg本体は配布ZIPには同梱せず、セットアップ時に各配布元から導入します。

# セットアップ時に導入するもの（v1.4追加分）

- yt-dlp（動画の取得）：Unlicense。https://github.com/yt-dlp/yt-dlp
- faster-whisper（文字起こし）：MIT License。https://github.com/SYSTRAN/faster-whisper
- 文字起こし用データ（Whisper small の変換版）：MIT License。初回の準備でHugging Faceから取得し、このフォルダの.modelsへ保存します。

参考動画の取得は、利用する各サービスの利用規約の範囲で行ってください。
