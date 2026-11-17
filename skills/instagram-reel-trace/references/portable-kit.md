# 実行キット v1.5（Mac対応）

鈴木さん専用。Mac（Appleシリコン想定・起動時に判定）／Python 3.11。Windows起動ファイルも同梱。キットのREADME.mdとはじめに.htmlが利用者向けの入口。

## 対応範囲

同梱の梱包レシピは、APIキーと利用残高、初回セットアップ後に操作画面から再制作できる。人物2名の参照画像を変更でき、注文番号を保存して再開し、字幕・BGM・SE・比較画面まで書き出す。画面の「再編集」はローカル処理のみ。

v1.4から、参考動画の取得と文字起こしは同梱の道具で行う。どちらもMiniMaxへ通信せず、課金はない。キットの専用環境（Macは.venv-mac/bin/python、Windowsは.venv/Scripts/python.exe）で実行する。

- `python engine/media.py fetch <URL> --out projects/<題材>/assets`：reference.mp4と投稿情報を保存。Instagramは同じ投稿でも一時的に取得を断ることがあるため、v1.5から20秒おきに4回まで自動でやり直す（`--tries`・`--wait`で変更可）。通信の許可が要る環境では、許可を得てから実行する。それでも取得できないときだけ動画ファイルを求める。
- `python engine/media.py transcribe <動画か音声> --out projects/<題材>/work/reference.asr.json`：単語ごとの時刻つきで保存。自動の聞き取りなので、商品名・数字は映像と投稿文で確かめる。生成した音声と台本の照合にも使う。
- `python engine/media.py check`：道具の有無だけ確認。`prepare`：文字起こし用データ（約500MB）をキット内の.modelsへ取得。初回セットアップが自動で行う。

台本の改訂、ナレーション生成、自社ロゴ配置、仕上げの編集は汎用自動処理ではない。AIが元動画の全編を確認して別レシピを準備する。カードや商品の画像が映る場面は、元映像を流用せず公式画像を合成する（SKILL.mdの「カード・商品画像が映る場面」）。元の画像と動きを調べずに梱包の区間・台本を使い回さない。AI環境や音声サービスの費用・設定はMiniMax動画生成と区別する。

## 別レシピの形

`projects/<題材>/project.json`、`assets/`、`scripts/`を作る。既存のpackingは保持。パスはproject.jsonからの相対パスで、そのレシピ内だけを参照する。

project.jsonの項目：

- version: 1、id: 短い英数字、name: 日本語題名。
- source_url、reference: 比較する元MP4、people: 人物参照画像の配列（画面は2名対応）。
- duration: 最終全編秒数、resolution: 768Pまたは2K、ratio: 9:16。
- max_run_jpy: この制作回の上限。費用が超えるときは無断で引き上げない。
- segments: id、seconds（生成尺4〜15整数）、target_seconds（仕上がり尺）、prompt（txt）、reference（各区間MP4）。target_secondsの合計をdurationへ合わせる。
- render_scripts: scripts内のPythonファイル名を実行順で列挙。
- output_video: 最終MP4名、comparison: index.html。

実例は同梱projects/packing/project.json。入力素材は全区間で同じ人物順にする。2名なら人物A/Bの役割と位置を各プロンプトに指定。顔・髪・服装は指定人物を優先し、元動画は動き・構図の参考にする。

実行時、キットがprojectをrunsの制作回へコピーし、素材・指示の指紋を保存する。再開中にスナップショットを編集しない。新しい指示は新規制作回にする。生成結果はwork/raw-<id>.mp4、整尺した映像はwork/part-<id>.mp4へ入る。scriptsの内容はworkへコピーされ、作業ディレクトリもworkになる。

編集スクリプトはwork/outputsに試作MP4、compare-trial.mp4、compare-reference.mp4、index.htmlと日本語訳を作る。参照原音がない動画なら、参考音声モードを無音にするなど明示的に対応する。汎用エンジンはこの3動画に音声トラックと全編尺を要求する。

映像生成の音声を使う／別の音声を載せる場合は、そのレシピの編集処理を実装する。梱包の既定処理は生成原音を捨て、別制作のBGM・SEを載せる。語りのある動画へそのまま使わない。梱包のfinish.pyにある前半見出し除去座標は梱包専用。別動画へ転用しない。

## 実行と停止時

`python engine/run.py quote --project projects/<題材>/project.json` は無料チェック。
`python engine/run.py new --project projects/<題材>/project.json --yes` は有料生成。
`python engine/run.py resume --run runs/<制作回>` は既存注文の続き。
`python engine/run.py render --run runs/<制作回>` は生成済み映像のローカル再編集。

通信断でtask_idが未確定のsubmitting状態は自動で再送しない。MiniMaxダッシュボードで受付の有無と注文番号を確認し、既存注文ならstate.jsonにtask_id・status=orderedを追記して再開する。確認できなければ停止理由を伝える。キット利用後の.env、runs、ledger、stateを配布しない。

元の参考映像・素材・音は指定範囲だけ送る。キットの別PC実行や鈴木さんのアカウント権限を、元の制作成功だけで確認済みにしない。

## Macへの配布

初回01_setup.command、通常02_start.command。Homebrewの自動導入はAppleシリコン・macOS 15以降を対象とし、Intelや古いOSに同じ導入を強制しない。Python 3.11・Tk・FFmpegが既存なら導入を省ける。Mac実機での動作は未確認なので、Windowsの検証結果と区別して伝える。

フォントはprojects/packing/scripts/Arimo.ttfとArimo-OFL.txtを同梱する。WindowsのArialなど端末依存のフォントパスを新しいレシピへ持ち込まない。ZIPの.command/.shはLF・UTF-8（BOMなし）・Unix実行権限755を保持する。展開先にAPIキー・.venv-mac・.setup・注文履歴を同梱しない。配布後は最初のクリーンなZIPを共有元にする。

## Codexでの入口（v1.2）

配布物に.models（文字起こし用データ）・.venv・.envを含めない。yt-dlpはInstagram側の変更で取得できなくなることがあるため、版を固定せず新しい版を導入する。

## 2026-11-14の通し試験で分かったこと

配布キットv1.3とCodexだけでストームエメラルダ（約24秒・語りあり）を完成できた。費用は約955円、約100分。当時は取得・文字起こしの道具が試験PCに元から入っていたものだったため、v1.4で同梱した。比較ページの自動検査（Playwright）は同梱していない。必要ならAIが準備し、未実施なら未確認と伝える。

## 2026-11-15の通し試験で分かったこと

配布キットv1.4とCodex（Windowsのデスクトップ版）で、同じストームエメラルダを作り直した。約400円・依頼から約30分。カード2種は公式サイトの画像を元と同じ位置に合成し、出典URLをassets/sources.jsonに記録していた。参考店の店名・ロゴ・倉庫や発送の説明は残っていない。取得と文字起こしは同梱の道具が使われた。

参考動画の取得は1回目だけ失敗した（Instagramが空の返事を返した。数分後の再実行で成功）。このためv1.5で自動のやり直しを入れた。出典記録に取得日がなかったため、取得日も書く決まりを明記した。完成動画は720×1280（参考は1080×1920）。Codexは今回も生成と仕上げのプログラムを自作し、操作画面と標準の実行手順は使っていない。費用はキットの台帳に記録された。

配布ルートのAGENTS.mdが専用スキルへ誘導する。はじめに.htmlはAPIキー取得・Codex初回設定・画像とURLで制作、の3ステップ。詳しい旧ガイドは詳しい使い方.html。キー設定は画面で.envへ保存し、設定確認では値を表示しない。無料見積りと実API認証の確認を区別する。
