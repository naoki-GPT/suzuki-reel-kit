"""v1: Reconstruct the source's non-brand title and four timed labels."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageFilter
import json
r=Path(__file__).resolve().parent
font=str(r/'Arimo.ttf')

def bold_font(px):
    # 同梱の可変フォントを太字に固定。Mac/Windowsの既存フォントに依存しない。
    f=ImageFont.truetype(font,px)
    f.set_variation_by_axes([700])
    return f
def panel(name,size,lines,red=True):
    w,h=size;im=Image.new('RGBA',(w+36,h+36));shadow=Image.new('RGBA',im.size)
    d=ImageDraw.Draw(shadow);d.rounded_rectangle((18,22,w+18,h+22),radius=18,fill=(0,0,0,140))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9)))
    d=ImageDraw.Draw(im);d.rounded_rectangle((18,18,w+18,h+18),radius=16,fill=(255,0,0,255) if red else (255,255,255,255))
    for text,y,px in lines:
        f=bold_font(px);stroke=5 if red else 1
        while d.textbbox((0,0),text,font=f,stroke_width=stroke)[2]>w-22:
            px-=1;f=bold_font(px)
        d.text((w/2+18,y+18),text,font=f,anchor='mm',fill='white' if red else 'black',stroke_width=stroke,stroke_fill='black')
    im.save(r/(name+'.png'))
panel('title',(470,180),[('How to ship',47,68),('Japanese TCG',126,64)],False)
panel('label1',(360,166),[('Level. 1',45,70),('One order',124,67)])
panel('label2',(620,182),[('Level. 2',49,70),("Okey, that’s a lot...",132,67)])
panel('label3',(640,182),[('Level 3.',49,70),('Got enough stock!?',132,67)])
panel('complete',(350,104),[('Complete!',50,72)])
cues=[[0,3,'Level. 1 — One order','レベル1：1件の注文'],[5.5,8.5,"Level. 2 — Okey, that’s a lot...",'レベル2：おっと、かなり多い…'],[15,18.066667,'Level 3. — Got enough stock!?','レベル3：在庫は十分ある！？'],[32.8,1042/30,'Complete!','梱包完了！']]
(r/'cues.json').write_text(json.dumps(cues,ensure_ascii=False,indent=2),encoding='utf-8')
print('Generated five source-style overlays; no store identity.')
