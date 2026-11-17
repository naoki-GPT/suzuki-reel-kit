"""v1.0: 鈴木さん用のローカル操作画面。APIキーはこのPCの.envだけに保存。"""
from pathlib import Path
import datetime,json,os,queue,re,shutil,subprocess,sys,threading,tkinter as tk,webbrowser
from tkinter import ttk,filedialog,messagebox
from lib.common import ROOT

class App:
    def __init__(self,win):
        self.win=win;win.title('鈴木さん｜リール制作キット v1.2・Mac対応');win.geometry('840x740')
        self.q=queue.Queue();self.busy=False;self.proc=None
        self.project=tk.StringVar(value=str(ROOT/'projects/packing/project.json'))
        self.people=[tk.StringVar(value=str(ROOT/'projects/packing/assets'/n)) for n in ['person.png','assistant.png']]
        self.key=tk.StringVar();self.cap=tk.StringVar(value=str(json.loads((ROOT/'config.json').read_text(encoding='utf-8'))['daily_limit_jpy']))
        box=ttk.Frame(win,padding=18);box.pack(fill='both',expand=True)
        ttk.Label(box,text='鈴木さん用 リール制作',font=('TkDefaultFont',20,'bold')).pack(anchor='w')
        ttk.Label(box,text='今回の梱包レシピは、生成 → 字幕・BGM・SE → 同時再生比較まで実行します。').pack(anchor='w',pady=6)
        form=ttk.Frame(box);form.pack(fill='x');form.columnconfigure(1,weight=1)
        ttk.Label(form,text='MiniMax APIキー').grid(row=0,column=0,sticky='w',pady=5)
        ttk.Entry(form,textvariable=self.key,show='*').grid(row=0,column=1,sticky='ew')
        ttk.Button(form,text='キーを保存',command=self.save_key).grid(row=0,column=2,padx=6)
        ttk.Label(form,text='日次上限（円）').grid(row=1,column=0,sticky='w',pady=5)
        ttk.Entry(form,textvariable=self.cap,width=10).grid(row=1,column=1,sticky='w')
        ttk.Button(form,text='上限を保存',command=self.save_cap).grid(row=1,column=2,padx=6)
        ttk.Label(form,text='制作レシピ').grid(row=2,column=0,sticky='w',pady=5)
        ttk.Entry(form,textvariable=self.project).grid(row=2,column=1,sticky='ew')
        ttk.Button(form,text='選ぶ',command=self.pick_project).grid(row=2,column=2)
        for i,title in enumerate(['主役Aの画像','補助役Bの画像']):
            ttk.Label(form,text=title).grid(row=i+3,column=0,sticky='w',pady=5)
            ttk.Entry(form,textvariable=self.people[i]).grid(row=i+3,column=1,sticky='ew')
            ttk.Button(form,text='選ぶ',command=lambda j=i:self.pick_person(j)).grid(row=i+3,column=2)
        ttk.Label(box,text='キー保存済みの場合、入力欄は空のままで使えます。キーはチャットや共有ZIPへ入れないでください。',wraplength=790).pack(anchor='w',pady=8)
        row=ttk.Frame(box);row.pack(fill='x');self.buttons=[]
        for title,fn in [('1. 無料で見積り',self.estimate),('2. 制作を開始',self.start),('途中から再開',lambda:self.launch('resume')),('生成済みを再編集',lambda:self.launch('render'))]:
            b=ttk.Button(row,text=title,command=fn);b.pack(side='left',padx=3);self.buttons.append(b)
        row2=ttk.Frame(box);row2.pack(fill='x',pady=8)
        for title,fn in [('完成例を見る',lambda:webbrowser.open((ROOT/'examples/packing/index.html').as_uri())),('自分の出力を開く',self.open_output),('使い方',lambda:webbrowser.open((ROOT/'はじめに.html').as_uri()))]:ttk.Button(row2,text=title,command=fn).pack(side='left',padx=3)
        self.log=tk.Text(box,wrap='word',height=21);self.log.pack(fill='both',expand=True)
        self.log.insert('end','最初にAPIキーを保存。見積りは課金しません。\n別動画は同梱スキルでAIに制作レシピを作らせてから選びます。\n')
        win.protocol('WM_DELETE_WINDOW',self.close);win.after(100,self.pump)

    def save_key(self):
        if self.busy:return
        key=self.key.get().strip()
        if not key or any(c in key for c in '\r\n"\' '):messagebox.showerror('入力確認','空白や改行のないAPIキーを入力してください。');return
        (ROOT/'.env').write_text('MINIMAX_API_KEY='+key+'\n',encoding='utf-8');self.key.set('');messagebox.showinfo('保存','このキットの.envに保存しました。キーは画面に表示しません。')

    def save_cap(self):
        if self.busy:return
        try:
            cap=int(self.cap.get());assert 0<cap<=100000
        except (ValueError,AssertionError):messagebox.showerror('入力確認','1〜100000の整数を入力してください。');return
        if not messagebox.askyesno('日次上限','このキットの日次上限を '+str(cap)+'円に変更しますか？'):return
        p=ROOT/'config.json';data=json.loads(p.read_text(encoding='utf-8'));data['daily_limit_jpy']=cap;p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        from lib import common
        common._config_cache=None

    def pick_project(self):
        if self.busy:return
        value=filedialog.askopenfilename(title='project.jsonを選択',filetypes=[('制作レシピ','*.json')])
        if value:
            try:
                p=Path(value);data=json.loads(p.read_text(encoding='utf-8-sig'));assert len(data['people'])==2
                self.project.set(value)
                for v,name in zip(self.people,data['people']):v.set(str(p.parent/name))
            except Exception:messagebox.showerror('レシピ確認','この画面は人物2名のレシピに対応しています。project.jsonを確認してください。')

    def pick_person(self,i):
        if self.busy:return
        v=filedialog.askopenfilename(filetypes=[('人物画像','*.png *.jpg *.jpeg *.webp')])
        if v:self.people[i].set(v)

    def prepare_project(self):
        p=Path(self.project.get()).resolve();spec=json.loads(p.read_text(encoding='utf-8-sig'))
        if len(spec['people'])!=2:raise ValueError('操作画面は人物2名に対応しています')
        selected=[Path(v.get()).resolve() for v in self.people]
        if all(a==(p.parent/b).resolve() for a,b in zip(selected,spec['people'])):return p
        dst=ROOT/'projects'/('custom_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'));shutil.copytree(p.parent,dst)
        for i,src in enumerate(selected):
            if not src.is_file():raise ValueError('人物画像がありません')
            name='assets/person-'+str(i+1)+src.suffix.lower();shutil.copy2(src,dst/name);spec['people'][i]=name
        # 元の人物の髪型・服装が残らないよう、差し替え画像を明示的に優先。
        identity='For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced for Person A identity, hair and clothing. Picture 2 defines Person B identity, hair and clothing. Two distinct adults, no face merging. Person A replaces the lead worker and stands LEFT in two-person scenes; Person B replaces the assistant and stands RIGHT. First single-person shot uses A only. Video 1 controls actions and warehouse; ignore portrait backgrounds. Preserve both image identities and outfits throughout.\n\n'
        for seg in spec['segments']:
            prompt=dst/seg['prompt'];s=prompt.read_text(encoding='utf-8')
            if 'The reference has been cleaned' not in s:raise ValueError('この別レシピの人物変更は同梱スキルでAIに依頼してください')
            s=s[s.index('The reference has been cleaned'):]
            s=re.sub(r'gray-cardigan man','Person A',s,flags=re.I);s=re.sub(r'black-T-shirt assistant','Person B',s,flags=re.I)
            s=s.replace("Maintain the main man's visible forehead, same face and same gray cardigan whenever he rises above the box.",'Keep Person A identical to Picture 1 whenever visible.')
            prompt.write_text(identity+s,encoding='utf-8')
        (dst/'project.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
        self.project.set(str(dst/'project.json'))
        for v,n in zip(self.people,spec['people']):v.set(str(dst/n))
        return dst/'project.json'

    def estimate(self):
        try:p=self.prepare_project();self.launch('quote',p)
        except Exception as e:messagebox.showerror('素材を確認',str(e))

    def start(self):
        if self.busy:return
        try:
            p=self.prepare_project()
            from run import inspect_project
            from lib import cost
            spec,_,usd=inspect_project(p);jpy=round(cost.usd_to_jpy(usd));ok,msg=cost.check_daily_limit(jpy)
            if not ok:raise ValueError(msg)
            if not (ROOT/'.env').exists() and not os.environ.get('MINIMAX_API_KEY'):raise ValueError('APIキーを保存してください')
            if not messagebox.askyesno('有料生成を開始',f"{spec['name']}\n見積り ${usd:.2f}（約{jpy}円）\n{msg}\n\n新規制作を開始しますか？途中停止した制作は「途中から再開」を使ってください。"):return
            self.launch('new',p)
        except Exception as e:messagebox.showerror('開始できません',str(e))

    def launch(self,action,project=None):
        if self.busy:return
        self.busy=True
        for b in self.buttons:b.configure(state='disabled')
        args=[sys.executable,'-u',str(ROOT/'engine/run.py'),action]
        if project:args+=['--project',str(project)]
        if action=='new':args+=['--yes']
        def worker():
            try:
                self.proc=subprocess.Popen(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                for line in self.proc.stdout:self.q.put(('line',line))
                self.q.put(('done',self.proc.wait()))
            except Exception as e:self.q.put(('line',str(e)+'\n'));self.q.put(('done',1))
        threading.Thread(target=worker,daemon=True).start()

    def pump(self):
        while not self.q.empty():
            kind,value=self.q.get()
            if kind=='line':self.log.insert('end',value);self.log.see('end')
            else:
                self.busy=False;self.proc=None
                for b in self.buttons:b.configure(state='normal')
                self.log.insert('end','\n処理終了。\n' if value==0 else '\n停止しました。表示された理由を解消し、注文済みなら「途中から再開」を押してください。\n')
        self.win.after(100,self.pump)

    def open_output(self):
        try:
            run=ROOT/(ROOT/'last-run.txt').read_text(encoding='utf-8');p=run/'work/outputs/index.html'
            if not p.exists():raise ValueError('まだ比較画面が完成していません')
            webbrowser.open(p.as_uri())
        except Exception as e:messagebox.showinfo('出力',str(e))

    def close(self):
        if self.busy:messagebox.showinfo('処理中','処理が終わるまでこの画面を開いておいてください。');return
        self.win.destroy()

if __name__=='__main__':
    win=tk.Tk();App(win);win.mainloop()
