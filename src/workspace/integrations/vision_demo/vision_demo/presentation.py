"""HDMI/desktop rendering with explicit source and processor provenance."""
from pathlib import Path
import re
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from presentation_theme import BG,FG,DIM,ACCENT,AMBER


class Presenter:
    def __init__(self,font_path=None):
        candidates=[font_path,'C:/Windows/Fonts/msyh.ttc',
            '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
            '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
            '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']
        found=next((str(p) for p in candidates if p and Path(p).is_file()),None)
        if not found:raise RuntimeError('A local Chinese display font is required')
        self.title=ImageFont.truetype(found,32)
        self.body=ImageFont.truetype(found,22)
        latin=next((p for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                    'C:/Windows/Fonts/arial.ttf') if Path(p).is_file()),found)
        self.latin={size:ImageFont.truetype(latin,size) for size in (22,32)}

    def text(self,draw,xy,words,font,fill):
        # Droid fallback supplies Chinese only on the board. Align Latin runs
        # on the same baseline so source names and coordinates remain readable.
        x,y=xy;baseline=font.getmetrics()[0]
        # The board's Droid fallback covers CJK, but not Greek, microvolt,
        # mathematical minus or many punctuation marks. DejaVu covers these.
        cjk=r"\u2e80-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef"
        for run in re.findall('['+cjk+']+|[^'+cjk+']+',words):
            chosen=font if re.match('['+cjk+']',run) else self.latin[font.size]
            draw.text((x,y+baseline-chosen.getmetrics()[0]),run,font=chosen,fill=fill)
            x+=chosen.getlength(run) if hasattr(chosen,'getlength') else chosen.getsize(run)[0]

    def render(self,snapshot,rgb=None,pupils=None,backend='not running',fixture=False):
        canvas=Image.new('RGB',(1280,720),BG);draw=ImageDraw.Draw(canvas)
        self.text(draw,(28,14),'我们意念合一  /  图像处理',font=self.title,fill=FG)
        self.text(draw,(28,62),'%02d / 10   %s'%(snapshot['index']+1,snapshot['label']),font=self.body,fill=ACCENT)
        origin='OV5640' if snapshot['source']=='ov5640' else 'Tobii IS4'
        self.text(draw,(650,66),'%s  |  %s'%(origin,'合成测试素材' if fixture else ('实时输入' if rgb is not None else '等待输入')),font=self.body,fill=(215,186,114) if fixture else DIM)
        box=(32,108,1248,632)
        draw.rectangle(box,fill=(3,6,10))
        if rgb is not None:
            view=Image.fromarray(rgb)
            scale=min((box[2]-box[0])/view.width,(box[3]-box[1])/view.height)
            size=(max(1,int(view.width*scale)),max(1,int(view.height*scale)))
            left=(1280-size[0])//2;top=box[1]+(box[3]-box[1]-size[1])//2
            canvas.paste(view.resize(size,getattr(Image,'Resampling',Image).BILINEAR),(left,top))
            if pupils:
                for number,p in enumerate(pupils.get('pupils',[])):
                    if not p.get('valid'):continue
                    (cx,cy),(a,b),angle=p['ellipse']
                    # Ellipse orientation follows source pixels; draw sampled outline.
                    t=np.linspace(0,2*np.pi,65);theta=np.deg2rad(angle)
                    xs=cx+a/2*np.cos(t)*np.cos(theta)-b/2*np.sin(t)*np.sin(theta)
                    ys=cy+a/2*np.cos(t)*np.sin(theta)+b/2*np.sin(t)*np.cos(theta)
                    points=list(zip((left+xs*scale).tolist(),(top+ys*scale).tolist()))
                    draw.line(points,fill=(80,255,130),width=3)
                    px,py=left+cx*scale,top+cy*scale
                    draw.line((px-9,py,px+9,py),fill=(255,220,80),width=2)
                    draw.line((px,py-9,px,py+9),fill=(255,220,80),width=2)
                    self.text(draw,(left+8,top+8+number*29),'中心 %d: (%.1f, %.1f)'%(number+1,cx,cy),font=self.body,fill=(80,255,130))
        else:
            self.text(draw,(64,310),'等待 %s 新画面，请检查摄像头连接'%origin,font=self.body,fill=(189,199,211))
        self.text(draw,(28,648),'瞳孔定位' if snapshot['mode']=='pupil' else '视频图像分析',font=self.body,fill=DIM)
        self.text(draw,(28,682),'PL_KEY0 下一模式  |  原眼控标定保持  |  瞳孔中心为源图像像素坐标',font=self.body,fill=DIM)
        if snapshot['mode']=='pupil' and pupils and not pupils.get('valid'):
            self.text(draw,(700,648),'未找到可靠瞳孔候选',font=self.body,fill=(235,187,102))
        return np.asarray(canvas)
