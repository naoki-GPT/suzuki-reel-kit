from pathlib import Path
import json,zipfile
r=Path(__file__).resolve().parent;out=r/'outputs';out.mkdir(exist_ok=True)
s=(r/'index.template.html').read_text(encoding='utf-8')
s=s.replace('ストームエメラルダ｜全編再現比較','梱包レベル1〜3｜全編再現比較').replace('ストームエメラルダ：元のカット順で全編再現','Noob vs Pro vs Hacker：梱包を全編再現')
s=s.replace('中盤のスタッフは指定した男性画像を参照して生成。元にない商品パネルは追加していません。','主役は前回の男性画像を参照して生成。小・中・大の箱を梱包する約35秒です。試作には参考店の店名・ロゴを入れていません。')
s=s.replace('Storm-trial.mp4','Packing-trial.mp4').replace('Dbc5TBDJ2gl','DfR36MmTIsK')
start=s.index('<div><button data-time="0">');end=s.index('</div>',start)+6
s=s[:start]+'''<div><button data-time="0">Level 1：小箱</button><button data-time="5.5">Level 2：2人で梱包</button><button data-time="14.73">Level 3：大箱</button><button data-time="30">箱を閉じる</button><button data-time="32.83">Complete!</button></div><p class="muted">共通の見出し：How to ship Japanese TCG<br>日本のトレーディングカードを発送する方法</p>'''+s[end:]
s=s.replace('（発話の間）','（説明テロップなし）').replace('映像の動きを確認する場面','梱包の動きを見る場面')
s=s.replace('販売・発送・店舗名は参考店の投稿当時の表現です。自社の実在庫や所在地を示す公開版ではありません。人物と動作、商品細部の一致は出力を見て確認するための試作です。','参考側の店名・ロゴ・原音は比較用に保持。試作側では除去しています。人物・倉庫・梱包は生成による再現で、自社の実在庫や発送実績を示す記録ではありません。')
s=s.replace('<details><summary>全編の英語と日本語訳</summary>','<p class="muted">参考側の固定表示「SAMURAI SWORD」「FROM JAPAN TO THE WORLD」は、参考店名と「日本から世界へ」の意味です。試作では表示しません。歌詞の翻訳ではなく、画面の英語テロップの訳を掲載しています。</p><details><summary>全編の英語と日本語訳</summary>')
cues=json.dumps(json.loads((r/'cues.json').read_text(encoding='utf-8')),ensure_ascii=False)
s=s.replace('__REFERENCE__',cues).replace('__TRIAL__',cues).replace('__FINDINGS__',(r/'findings.html').read_text(encoding='utf-8'))
s=s.replace('指定人物で全編を再現・v1','主役・補助役の2名を画像指定・v2')
s=s.replace('主役は前回の男性画像を参照して生成。小・中・大の箱を梱包する約35秒です。試作には参考店の店名・ロゴを入れていません。','主役と補助役、それぞれ別の人物画像を全3区間に指定した約35秒の試作です。小・中・大の箱を梱包する流れを再現。右側の試作を見ながら、顔・服装・手の動きを比較できます。')
s=s.replace('<details class="box"><summary>人物の参照画像を見る</summary><img src="person.png" alt="指定した架空男性" style="display:block;width:220px;max-width:100%;margin:15px auto"></details>','<details class="box"><summary>指定した2名の人物画像を見る</summary><div style="display:flex;gap:16px;flex-wrap:wrap;justify-content:center"><figure style="margin:10px"><img src="person.png" alt="主役A：グレーのカーディガン" style="width:180px;max-width:100%"><figcaption>主役A：グレーのカーディガン</figcaption></figure><figure style="margin:10px"><img src="assistant.png" alt="補助役B：短髪・黒Tシャツ" style="width:180px;max-width:100%"><figcaption>補助役B：短髪・黒Tシャツ</figcaption></figure></div></details>')
(out/'index.html').write_text(s,encoding='utf-8')
(out/'はじめに.txt').write_text('鈴木さん専用／梱包レベル1〜3 全編再現比較 v1\n再制作版\n\nZIPをすべて展開し、index.htmlをChromeまたはEdgeで開きます。\n左＝参考、右＝前回の男性を使った試作。音声ボタンで再生位置を保って切り替えます。\nLevel 1／Level 2／Level 3／箱を閉じる／Complete!のボタンで各場面へ飛べます。\n英語の画面テロップと日本語訳を表示します。\nPacking-trial.mp4は試作単体です。\n\n参考：https://www.instagram.com/p/DfR36MmTIsK/\n試作には参考店の店名・ロゴ・読み上げなし。追加の商品パネルなし。\n原曲と生成原音を試作に流用せず、別制作のインストBGMと梱包SEを使用。説明ナレーションなし。\n生成映像の手指・箱・顔・切替の完全一致を保証するものではありません。所見はindex.htmlに記載。\n',encoding='utf-8-sig')
guide=out/'はじめに.txt'
guide.write_text(guide.read_text(encoding='utf-8-sig').replace('全編再現比較 v1','全編再現比較 v2・2名指定版').replace('前回の男性を使った試作','主役・補助役それぞれの画像を使った試作'),encoding='utf-8-sig')
with zipfile.ZipFile(out/'Packing-two-people-comparison.zip','w',zipfile.ZIP_DEFLATED) as z:
    for name in ['index.html','はじめに.txt','person.png','assistant.png','poster.jpg','Packing-trial.mp4','compare-trial.mp4','compare-reference.mp4']:
        z.write(out/name,'Packing-two-people-comparison/'+name)
print('Portable comparison page and ZIP ready.')
