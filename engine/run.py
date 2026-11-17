"""v1.0: 見積り→注文の記録→再開→比較動画。API注文は自動再送しない。"""
from pathlib import Path
import argparse,contextlib,datetime,hashlib,json,os,shutil,subprocess,sys
from lib import client,cost,preflight,upload
from lib.common import ROOT,LEDGER_PATH,H3Error,config,probe_summary

def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def local(base,name):
    p=(base/name).resolve()
    if not p.is_relative_to(base.resolve()) or not p.is_file():raise H3Error(f'素材がありません／フォルダ外です: {name}')
    return p

def ff(*args):
    subprocess.run(['ffmpeg','-nostdin','-v','error','-y',*map(str,args)],check=True,timeout=600)

@contextlib.contextmanager
def single_writer():
    """別の画面から同時に注文しても、台帳・日次上限を共有して守る。"""
    lock=ROOT/'run.lock';f=lock.open('a+b');f.seek(0)
    if lock.stat().st_size==0:f.write(b'0');f.flush();f.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise H3Error('別の制作が進行中です。その画面で続きを確認してください。')
        else:
            import fcntl
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except (BlockingIOError,OSError):raise H3Error('別の制作が進行中です。その画面で続きを確認してください。')
        yield
    finally:f.close()

def inspect_project(project):
    base=project.parent;spec=read(project)
    if spec.get('version')!=1:raise H3Error('未対応の制作レシピです')
    images=[local(base,p) for p in spec['people']]
    local(base,spec['reference']);seen=set();total=0;segments=[]
    for seg in spec['segments']:
        if seg['id'] in seen or not seg['id'].isalnum():raise H3Error('区間IDが不正です')
        seen.add(seg['id']);prompt=local(base,seg['prompt']).read_text(encoding='utf-8').strip()
        if len(prompt)>config()['limits']['prompt_max_chars']:raise H3Error('生成指示が長すぎます')
        if not 4<=seg['seconds']<=15 or not 0<seg['target_seconds']<=15:raise H3Error('区間の秒数を確認してください')
        pf=preflight.run(prompt=prompt,duration=seg['seconds'],resolution=spec['resolution'],ratio=spec['ratio'],first_frame=None,last_frame=None,ref_images=list(map(str,images)),ref_videos=[str(local(base,seg['reference']))],ref_audios=[])
        estimate=cost.estimate(spec['resolution'],seg['seconds'],ref_image_count=len(images),ref_video_seconds=pf.ref_video_seconds)
        segments.append((seg,prompt,pf,estimate));total+=estimate['total_usd']
    if abs(sum(s['target_seconds'] for s in spec['segments'])-spec['duration'])>.034:raise H3Error('区間合計と全編の秒数が一致しません')
    for script in spec['render_scripts']:local(base/'scripts',script)
    return spec,segments,round(total,4)

def fingerprint(project):
    spec=read(project);base=project.parent
    paths=[project,local(base,spec['reference'])]+[local(base,p) for p in spec['people']]
    for seg in spec['segments']:paths.extend([local(base,seg['prompt']),local(base,seg['reference'])])
    paths+=sorted((base/'scripts').glob('*'))
    h=hashlib.sha256()
    for p in paths:
        if p.is_file():h.update(p.relative_to(base).as_posix().encode());h.update(p.read_bytes())
    return h.hexdigest()

def quote(project):
    spec,parts,total=inspect_project(project);yen=round(cost.usd_to_jpy(total))
    ok,msg=cost.check_daily_limit(yen)
    print(f"[見積り] {spec['name']} 全{spec['duration']:.2f}秒 / {len(parts)}区間",flush=True)
    print(f'[見積り] ${total:.2f} / 約{yen:,}円（参考動画入力料金込み・設定レート換算）',flush=True)
    print(f'[予算] {msg}',flush=True)
    print('[確認] '+('上限内です。まだ課金していません。' if ok else '日次上限を超えるため新規発注できません。'),flush=True)
    return spec,parts,total

def create_run(project):
    quote(project)
    run=ROOT/'runs'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+read(project)['id'])
    run.mkdir(parents=True)
    shutil.copytree(project.parent,run/'project')
    snap=run/'project/project.json'
    save(run/'state.json',{'version':1,'fingerprint':fingerprint(snap),'segments':{},'status':'prepared'})
    (ROOT/'last-run.txt').write_text(str(run.relative_to(ROOT)),encoding='utf-8')
    return run

def retrieve(task_id,dest,est,spec,seg):
    task=client.poll(task_id)
    if task.get('status')!='succeeded':raise H3Error(f"注文 {task_id} は {task.get('status')} です。自動で再発注しません。")
    task=client.settle_price(task_id,task);client.download(task_id,task,dest)
    info=probe_summary(dest)
    if not info['width'] or abs(info['duration']-seg['seconds'])>1.5:raise H3Error('生成動画の尺・形式を確認できません')
    actual=cost.actual_from_task(task)
    cost.append_ledger({'task_id':task_id,'status':'succeeded','billed':True,'actual_jpy':actual['jpy'],'actual_usd':actual['usd'],'est_jpy':est['total_jpy']})
    return {'task_id':task_id,'status':'completed','actual_usd':actual['usd'],'actual_jpy':actual['jpy'],'probe':info}

def generate(run):
    project=run/'project/project.json';state_path=run/'state.json';state=read(state_path)
    if state['fingerprint']!=fingerprint(project):raise H3Error('開始後に素材や指示が変更されています。元の状態で再開するか、新規制作してください。')
    spec,parts,_=inspect_project(project);work=run/'work';work.mkdir(exist_ok=True)
    # 注文番号保存直後にPCが止まって台帳への追記が欠けた場合も予約額を復元。
    known=set()
    if LEDGER_PATH.exists():
        for line in LEDGER_PATH.read_text(encoding='utf-8').splitlines():
            try:known.add(str(json.loads(line).get('task_id')))
            except ValueError:continue
    for record in state['segments'].values():
        tid=record.get('task_id')
        if tid and tid not in known:
            cost.append_ledger({'task_id':tid,'status':record['status'],'billed':True,'est_jpy':record.get('estimated_jpy',record.get('actual_jpy',0)),'actual_jpy':record.get('actual_jpy'),'date':record.get('ordered_date',datetime.date.today().isoformat())})
    pending=sum(est['total_jpy'] for seg,_,_,est in parts if not state['segments'].get(seg['id'],{}).get('task_id'))
    ok,msg=cost.check_daily_limit(pending)
    if pending and (not ok or pending>spec.get('max_run_jpy',1200)):raise H3Error(msg+' / 制作ごとの上限も確認してください')
    for seg,prompt,pf,est in parts:
        sid=seg['id'];record=state['segments'].get(sid,{})
        dest=work/f'raw-{sid}.mp4'
        if record.get('status')=='completed' and dest.exists():continue
        if record.get('status')=='submitting' and not record.get('task_id'):
            raise H3Error('前回の発注の成否が不明です。MiniMaxで注文番号を確認してください。自動再送しません。')
        task_id=record.get('task_id')
        if not task_id:
            ok,msg=cost.check_daily_limit(est['total_jpy'])
            if not ok:raise H3Error(msg)
            print(f'[制作] 区間 {sid} の素材をアップロード',flush=True)
            upload.upload_all(pf)
            payload=client.build_payload(prompt=prompt,duration=seg['seconds'],resolution=spec['resolution'],ratio=spec['ratio'],assets=pf.assets)
            # POST前に不明状態を保存。通信断／PC停止でも勝手に払い直さない。
            state['segments'][sid]={'status':'submitting'};save(state_path,state)
            try:task_id=client.create_task(payload)
            except H3Error as e:
                if any(f'HTTP {n}' in str(e) for n in [400,401,402,403,422]):
                    state['segments'][sid]={'status':'rejected','reason':'注文受付前のエラー。残高・素材・キーを確認してください。'};save(state_path,state)
                raise
            state['segments'][sid]={'status':'ordered','task_id':task_id,'estimated_jpy':est['total_jpy'],'ordered_date':datetime.date.today().isoformat()};save(state_path,state)
            cost.append_ledger({'task_id':task_id,'status':'created','billed':True,'est_jpy':est['total_jpy'],'title':run.name})
            print(f'[受付済み] 区間 {sid} / 注文番号 {task_id}',flush=True)
        else:print(f'[再開] 区間 {sid} / 注文番号 {task_id}（再発注なし）',flush=True)
        result=retrieve(task_id,dest,est,spec,seg)
        result['ordered_date']=state['segments'][sid].get('ordered_date',datetime.date.today().isoformat())
        state['segments'][sid]=result;save(state_path,state)
    state['status']='generated';save(state_path,state)
    render(run)

def render(run):
    project=run/'project/project.json';base=project.parent;spec=read(project);work=run/'work';work.mkdir(exist_ok=True)
    for p in (base/'scripts').iterdir():
        if p.is_file():shutil.copy2(p,work/p.name)
    shutil.copy2(local(base,spec['reference']),work/'reference.mp4')
    for i,p in enumerate(spec['people']):shutil.copy2(local(base,p),work/('person.png' if i==0 else 'assistant.png' if i==1 else f'person-{i+1}.png'))
    for seg in spec['segments']:
        src=work/f"raw-{seg['id']}.mp4"
        if not src.exists():raise H3Error('未完成の区間があります。制作を再開してください。')
        info=probe_summary(src);target=seg['target_seconds'];scale=target/info['duration']
        ff('-i',src,'-an','-vf',f'setpts={scale}*PTS,scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1','-t',target,'-c:v','libx264','-crf','19','-preset','fast',work/f"part-{seg['id']}.mp4")
    (work/'findings.html').write_text('<b>再生成した動画の確認が必要です</b><p>今回の人物画像と指示で生成した結果です。顔・手・箱・ロゴ・字幕・音を全編確認してください。生成ごとに結果は変わり、同梱の完成例の品質を保証するものではありません。音は別制作のBGMと梱包SE、説明ナレーションなしです。</p>',encoding='utf-8')
    for script in spec['render_scripts']:
        print(f'[書き出し] {script}',flush=True)
        subprocess.run([sys.executable,str(work/script)],cwd=work,check=True,timeout=900)
    output=work/'outputs';report={}
    for name in [spec['output_video'],'compare-trial.mp4','compare-reference.mp4']:
        info=probe_summary(output/name)
        if abs(info['duration']-spec['duration'])>.08 or not info['has_audio']:raise H3Error('書き出し後の尺・音声チェックに失敗しました')
        subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(output/name),'-f','null','-'],check=True,timeout=180)
        report[name]=info
    save(run/'verification.json',{'media':report,'visual_review':'required by recipient'})
    state=read(run/'state.json');state['status']='rendered';save(run/'state.json',state)
    print('[完成] '+str(output/spec['comparison']),flush=True)

def doctor():
    for exe in ['ffmpeg','ffprobe']:
        if not shutil.which(exe):raise H3Error(exe+' がありません。Macは01_setup.command、Windowsは01_setup.batを実行してください。')
    try:import tkinter
    except ImportError:raise H3Error('操作画面のTkがありません。初回セットアップを実行してください。')
    if sys.version_info[:2]!=(3,11):print('[注意] 検証環境はPython 3.11です。',flush=True)
    import importlib.util
    if [m for m in ['yt_dlp','faster_whisper'] if importlib.util.find_spec(m) is None]:print('[注意] 別の参考動画用の道具（動画の取得・文字起こし）が未導入です。初回セットアップをもう一度実行してください。梱包動画の制作には影響しません。',flush=True)
    print('[環境] Python / FFmpeg / FFprobe を確認しました。API通信・課金はしていません。',flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['doctor','quote','new','resume','render']);p.add_argument('--project',type=Path,default=ROOT/'projects/packing/project.json');p.add_argument('--run',type=Path);p.add_argument('--yes',action='store_true');a=p.parse_args()
    doctor()
    if a.action=='doctor':return
    if a.action=='quote':quote(a.project.resolve());return
    if a.action=='new' and not a.yes:raise H3Error('新規の有料生成には --yes が必要です。画面から費用を確認して開始してください。')
    with single_writer():
        run=a.run.resolve() if a.run else None
        if a.action=='new':run=create_run(a.project.resolve())
        if run is None:
            if not (ROOT/'last-run.txt').exists():raise H3Error('再開する制作がありません')
            run=(ROOT/(ROOT/'last-run.txt').read_text(encoding='utf-8')).resolve()
        if not run.is_relative_to((ROOT/'runs').resolve()):raise H3Error('制作フォルダがキット内のrunsにありません')
        if a.action=='render':render(run)
        else:generate(run)

if __name__=='__main__':
    try:main()
    except (H3Error,subprocess.SubprocessError,OSError,ValueError,KeyError) as e:
        print('[停止] '+str(e),flush=True);sys.exit(1)
