from pathlib import Path
import subprocess,shutil,json
r=Path(__file__).resolve().parent;out=r/'outputs';out.mkdir(exist_ok=True);D=1042/30
def ff(*args):subprocess.run(['ffmpeg','-v','error','-nostdin','-y',*map(str,args)],check=True)
ff('-i',r/'part-a.mp4','-i',r/'part-b.mp4','-i',r/'part-c.mp4','-filter_complex','[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]','-map','[v]','-an','-t',D,'-c:v','libx264','-crf','19','-preset','fast',r/'joined.mp4')
args=['-i',r/'joined.mp4','-i',r/'mix.wav']
for name in ['title','label1','label2','label3','complete']:args+=['-loop','1','-i',r/(name+'.png')]
# A区間に焼き込まれた見出しだけを除いて、全編共通の見出しに統一。
filters="[0:v]delogo=x=110:y=86:w=500:h=216:enable='lt(t,14.733333)'[clean];[clean][2:v]overlay=(W-w)/2:82[v0]"
for i,(start,end) in enumerate([(0,3),(5.5,8.5),(15,18.066667),(32.8,D)]):
    idx=i+3
    # Short entrance fade reproduces the brief source pop without a new motion.
    filters+=f";[{idx}:v]format=rgba,fade=t=in:st={start}:d=0.06:alpha=1[p{i}];[v{i}][p{i}]overlay=(W-w)/2:582:enable='between(t,{start},{end})'[v{i+1}]"
ff(*args,'-filter_complex',filters,'-map','[v4]','-map','1:a','-t',D,'-c:v','libx264','-crf','19','-preset','fast','-c:a','aac','-b:a','192k','-movflags','+faststart',out/'Packing-trial.mp4')
fit='fps=30,scale=360:640:force_original_aspect_ratio=decrease,pad=360:640:(ow-iw)/2:(oh-ih)/2,setsar=1'
ff('-i',r/'reference.mp4','-i',out/'Packing-trial.mp4','-filter_complex',f'[0:v]{fit}[a];[1:v]{fit}[b];[a][b]hstack=shortest=1[v]','-map','[v]','-map','1:a','-t',D,'-c:v','libx264','-crf','21','-preset','fast','-c:a','aac','-movflags','+faststart',out/'compare-trial.mp4')
ff('-i',out/'compare-trial.mp4','-i',r/'reference.mp4','-map','0:v','-map','1:a','-t',D,'-c:v','copy','-c:a','aac','-movflags','+faststart',out/'compare-reference.mp4')
ff('-ss',8.8,'-i',out/'compare-trial.mp4','-frames:v',1,out/'poster.jpg')
shutil.copy2(r/'person.png',out/'person.png')
shutil.copy2(r/'assistant.png',out/'assistant.png')
ff('-i',out/'compare-trial.mp4','-vf','fps=1,scale=360:320,tile=7x5','-frames:v',1,r/'final-board.jpg')
print('Rendered full trial and two synchronized comparison audio versions.')
