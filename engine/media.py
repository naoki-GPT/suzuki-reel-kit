"""v1.4: 別の参考動画を作る準備用。動画の取得と文字起こし。MiniMaxへの通信・課金はしない。
v1.5: 取得に失敗したら間をあけて自動でやり直す（既定4回・20秒間隔）。

  python engine/media.py check
  python engine/media.py prepare
  python engine/media.py fetch <URL> --out projects/<題材>/assets
  python engine/media.py transcribe <動画か音声> --out projects/<題材>/work/reference.asr.json
"""
from pathlib import Path
import argparse,importlib.util,json,subprocess,sys,time
import os
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING','1')
for _stream in (sys.stdout,sys.stderr):
    if hasattr(_stream,'reconfigure'):_stream.reconfigure(encoding='utf-8',errors='replace')

ROOT=Path(__file__).resolve().parents[1]
MODELS=ROOT/'.models'
MODEL='small'

class MediaError(Exception):pass

class _Quiet:
    # yt-dlpの長い英語のエラー表示を出さない。失敗の理由は停止時の案内に1行で入れる。
    def debug(self,m):pass
    def info(self,m):pass
    def warning(self,m):pass
    def error(self,m):pass

def missing():
    return [m for m in ['yt_dlp','faster_whisper'] if importlib.util.find_spec(m) is None]

def check():
    m=missing()
    if m:raise MediaError('道具が未導入です: '+', '.join(m)+'。Macは01_setup.command、Windowsは01_setup.batをもう一度実行してください。')
    print('[環境] 動画の取得（yt-dlp）と文字起こし（faster-whisper）を確認しました。',flush=True)

def load_model(name,download):
    from faster_whisper import WhisperModel
    MODELS.mkdir(exist_ok=True)
    try:
        return WhisperModel(name,device='cpu',compute_type='int8',download_root=str(MODELS),local_files_only=not download)
    except Exception as e:
        if download:raise MediaError(f'文字起こし用データを取得できませんでした。通信を確認して、もう一度実行してください。（{type(e).__name__}）')
        return load_model(name,True)

def prepare(name):
    check()
    print(f'[準備] 文字起こし用データ（{name}・約500MB）を確認します。初回は数分かかります。',flush=True)
    load_model(name,False)
    print('[OK] 文字起こしの準備ができました。保存先はこのフォルダの .models です。',flush=True)

def duration(path):
    r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(path)],capture_output=True,text=True,timeout=120)
    return float(r.stdout.strip()) if r.returncode==0 and r.stdout.strip() else None

def fetch(url,out,name,tries=4,wait=20):
    check()
    import yt_dlp
    out=out.resolve()
    if not out.is_relative_to(ROOT):raise MediaError('保存先はこのキットのフォルダ内にしてください。')
    out.mkdir(parents=True,exist_ok=True)
    target=out/f'{name}.mp4'
    if target.exists():raise MediaError(f'すでにあります: {target}。別の名前か別のフォルダを指定してください。')
    opts={'outtmpl':str(out/f'{name}.%(ext)s'),'noplaylist':True,'format':'bv*+ba/b','merge_output_format':'mp4','writeinfojson':True,'socket_timeout':30,'retries':2,'quiet':True,'no_warnings':True,'noprogress':True,'logger':_Quiet()}
    # v1.5: Instagramは同じ投稿でも一時的に空の返事を返すことがある。間をあけて自動でやり直す。
    last=''
    for n in range(1,tries+1):
        try:
            with yt_dlp.YoutubeDL(opts) as y:y.download([url])
            if target.is_file():break
            last='動画ファイルが保存されませんでした'
        except Exception as e:
            last=(str(e).splitlines() or [type(e).__name__])[0][:160]
        if n<tries:
            print(f'[やり直し] 取得できませんでした（{n}回目）。{wait}秒待って、もう一度試します。',flush=True)
            time.sleep(wait)
    if not target.is_file():
        raise MediaError(f'URLから動画を{tries}回試しても取得できませんでした。通信が制限されている場合は、通信の許可を得てからもう一度実行してください。それでも取得できなければ、投稿が非公開・ログイン必須・削除済みの可能性があります。その場合だけ動画ファイルを直接渡してもらってください。（{last}）')
    d=duration(target)
    print(json.dumps({'file':str(target),'seconds':d,'info':str(out/f'{name}.info.json')},ensure_ascii=False),flush=True)
    print('[OK] 取得しました。全編を最後まで確認してから制作レシピを作ってください。',flush=True)

def transcribe(src,out,name,language):
    check()
    src=src.resolve()
    if not src.is_file():raise MediaError(f'ファイルがありません: {src}')
    model=load_model(name,False)
    segments,info=model.transcribe(str(src),language=language,word_timestamps=True,vad_filter=False)
    data={'source':src.name,'model':name,'language':info.language,'duration':info.duration,'segments':[]}
    for s in segments:
        data['segments'].append({'start':round(s.start,3),'end':round(s.end,3),'text':s.text.strip(),'words':[{'start':round(w.start,3),'end':round(w.end,3),'word':w.word.strip()} for w in (s.words or [])]})
    out=out.resolve();out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    for s in data['segments']:print(f"{s['start']:7.2f}-{s['end']:7.2f}  {s['text']}",flush=True)
    print(f'[OK] {out}（自動の聞き取り。商品名・数字は映像と投稿文で確かめてください）',flush=True)

def main():
    p=argparse.ArgumentParser(description='動画の取得と文字起こし。課金なし。')
    sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('check')
    a=sub.add_parser('prepare');a.add_argument('--model',default=MODEL)
    a=sub.add_parser('fetch');a.add_argument('url');a.add_argument('--out',type=Path,required=True);a.add_argument('--name',default='reference');a.add_argument('--tries',type=int,default=4);a.add_argument('--wait',type=int,default=20)
    a=sub.add_parser('transcribe');a.add_argument('source',type=Path);a.add_argument('--out',type=Path,required=True);a.add_argument('--model',default=MODEL);a.add_argument('--language',default=None)
    a=p.parse_args()
    if a.action=='check':check()
    elif a.action=='prepare':prepare(a.model)
    elif a.action=='fetch':fetch(a.url,a.out,a.name,max(1,a.tries),max(0,a.wait))
    else:transcribe(a.source,a.out,a.model,a.language)

if __name__=='__main__':
    try:main()
    except (MediaError,subprocess.SubprocessError,OSError,ValueError) as e:
        print('[停止] '+str(e),flush=True);sys.exit(1)
