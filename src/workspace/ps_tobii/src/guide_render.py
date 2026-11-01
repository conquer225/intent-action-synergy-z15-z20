"""Chinese HDMI instructions, rendered with the board's installed CJK font."""
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from guide import POINTS, HORIZONTAL_POINTS, FIVE_POINTS, DIRECTION_POINTS
from validation import TARGETS

BG = (19, 23, 27)
TEXT = (241, 243, 242)
MUTED = (183, 193, 196)
ACCENT = (213, 230, 172)
ERROR = (255, 191, 161)

class Renderer:
    def __init__(self, font=None, buttons=False, live=False, relaxed=False, validation=False, selection_test=False,calibration_points=3,relative=False,local_media=False):
        self.buttons = buttons
        self.live = live
        self.relaxed = relaxed
        self.validation = validation
        self.selection_test = selection_test
        self.relative = relative
        self.local_media = local_media
        if local_media:
            Image.preinit()  # Register JPEG before the playback clock starts.
        self.points = DIRECTION_POINTS if relative else {3:HORIZONTAL_POINTS,5:FIVE_POINTS,9:POINTS}[calibration_points] if selection_test else POINTS
        self.selection_base = None
        self.selection_key = None
        self.media_key = self.media_base = None
        self.video_shell_key = self.video_shell = None
        self.tracking_key = self.tracking_strips = None
        candidates = [font, "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
                      "C:/Windows/Fonts/msyh.ttc"]
        self.path = next((str(p) for p in candidates if p and Path(p).exists()), None)
        if self.path is None:
            raise RuntimeError("Chinese display font not found")
        self.fonts = {s: ImageFont.truetype(self.path, s) for s in (24, 28, 32, 44, 54, 72)}
        latin = next((p for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                                 "C:/Windows/Fonts/arial.ttf") if Path(p).exists()),None)
        if latin is None:
            raise RuntimeError("Numeric display font not found")
        # DroidSansFallbackFull is CJK-only on the actual board: ASCII digits
        # render as tofu. Align explicit Latin/CJK runs on the same baseline.
        self.latin_fonts = {s: ImageFont.truetype(latin,s) for s in self.fonts}

    def render(self, view):
        if view.phase in ("menu","video"):
            return self.media_render(view)
        key=(view.hover,view.selected,view.paused,view.confirmations,view.detail)
        if view.phase=="selection" and key==self.selection_key and self.selection_base is not None:
            frame=self.selection_base.copy()
            self.tracking_overlay(frame,view)
            self.selection_progress(frame,view)
            return frame
        canvas = Image.new("RGB", (1280,720), BG)
        d = ImageDraw.Draw(canvas)
        def text(x, y, words, size=32, color=TEXT):
            self.write_text(d,x,y,words,size,color)
        phase = view.phase
        if view.preview:
            text(920, 40, "画面演练 · 不采样", 24, ACCENT)
        if phase == "selection":
            names=("左区", "中区", "右区")
            text(60,40,"三点方向标定 | 选区验证" if self.relative else "选区与停留验证",44)
            text(60,108,view.detail,28,MUTED)
            for i,name in enumerate(names):
                left=round(i*1280/3)+22
                right=round((i+1)*1280/3)-22
                active=i==view.hover and not view.paused
                d.rectangle((left,198,right,550),
                                    fill=(39,51,44) if active else (28,34,39),
                                    outline=ACCENT if active else (65,76,81),width=5 if active else 2)
                text(left+70,290,name,54,ACCENT if active else TEXT)
                if i==view.selected:text(left+95,397,"已选中",32,ACCENT)
                d.rectangle((left+24,489,right-24,505),fill=(65,76,81))
            text(60,146,"已确认 %d 次  |  %s"%(view.confirmations,"已暂停" if view.paused else "真实眼动采样"),24,ACCENT)
            text(60,657,"PS_KEY0 重新标定  |  PS_KEY1 暂停 / 继续  |  换区后可再次确认" if self.relative else "PS_KEY1 暂停 / 继续  |  换区后可再次确认",24,MUTED)
        elif phase == "ready" and self.validation:
            text(72,110,"左、中、右注视验证",54)
            text(72,220,"沿用上一轮校准，检查真实方向与连续采样。",32,MUTED)
            text(72,330,"按开始后先倒计时 5 秒，再跟随 9 个白点。",28)
            text(72,400,"每点约 10 秒，总计约 1 分半；正常眨眼即可。",28)
            text(72,490,"点未移动就继续看，直到屏幕提示验证结束。",28)
            text(72,660,"PS_KEY0 开始验证  ·  PS_KEY1 停止",28,ACCENT)
        elif phase == "ready":
            text(72, 110, "准备好后再开始", 54)
            text(72, 202, "现在不用盯着屏幕，先坐稳并摆好模组。", 32, MUTED)
            text(72, 328, "开始前", 28, MUTED)
            text(72, 367, "5 秒倒计时", 44, ACCENT)
            text(460, 328, "每个白点", 28, MUTED)
            text(460, 367, "约 8 秒" if self.relative else "约 5 秒" if self.relaxed else "约 4 秒", 44, ACCENT)
            text(860, 328, "采不到时", 28, MUTED)
            text(860, 367, "不足则停止" if self.relative else "最多 35 秒" if self.relaxed else "10 秒停止", 44, ACCENT)
            text(72, 503, "白点移动时跟着看；正常眨眼，保持头部自然稳定。", 28)
            text(72, 555, "中、左、右三点方向标定；通常约 30 秒。" if self.relative else "本轮 %d 点校准；点未移动时继续看，最多 35 秒。"%len(self.points) if self.selection_test else "宽松试测：失败自动重采，最多 3 次；点未移动就继续看。" if self.relaxed else "屏幕提示结束后，就可以移开视线。", 28)
            text(72, 611, "按开始先检查实时距离，位置合适后再按 PS_KEY0 标定。" if self.relative else "校准成功后自动进入左、中、右选区，停留满格确认。" if self.selection_test else "真实校准试测 · 屏幕几何写入未支持，坐标精度待验证" if self.live else "当前为画面演练；正式校准采样尚未接入", 24, MUTED)
            text(72, 660, ("PS_KEY0 开始方向标定  |  PS_KEY1 暂停" if self.relative else "PS_KEY0 开始校准  ·  PS_KEY1 暂停" if self.live else "PS_KEY0 开始演练  ·  PS_KEY1 暂停") if self.buttons else "等待开始指令", 28, ACCENT)
        elif phase == "restarting":
            text(72,110,"准备重新标定",54)
            text(72,230,"正在结束上一轮，请先坐稳。",32,MUTED)
            text(72,330,"结束后进入距离检查，调整好后按 PS_KEY0 开始。",28)
            text(72,650,"PS_KEY1 取消",28,ACCENT)
        elif phase == "positioning":
            text(72,110,"先检查距离和眼部状态",54)
            text(72,220,"模组固定在屏幕下沿中央，正对双眼。",32,MUTED)
            text(72,310,"保持头部稳定，调整位置时观察下方实时读数。",28)
            text(72,380,"上一轮可用距离约 40～43 cm，可以先回到那个位置。",28,MUTED)
            text(72,460,"位置合适后按 PS_KEY0，再跟随中、左、右三个白点。",28)
            text(72,669,"PS_KEY0 开始三点标定  |  PS_KEY1 停止",24,ACCENT)
        elif phase == "connecting":
            text(72,110,"正在连接眼动模组",54)
            text(72,218,"连接完成后先检查实时距离，请先坐稳。" if self.relative else "连接完成后开始 5 秒倒计时，请先坐稳。",32,MUTED)
            text(72,650,"按 PS_KEY1 可停止",28,MUTED)
        elif phase in ("vsettle","vcollect"):
            text(72,42,"请看白点  ·  第 %d / 9 点"%(view.point+1),32)
            text(72,94,"%s，剩 %d 秒"%("正在移视稳定" if phase=='vsettle' else "正在验证方向",view.remaining),24,MUTED)
            x,y=TARGETS[view.point];x,y=round(x*1280),round(y*720)
            d.ellipse((x-17,y-17,x+17,y+17),fill=TEXT)
            d.ellipse((x-3,y-3,x+3,y+3),fill=BG)
            text(72,520,view.detail,28,ACCENT)
            text(72,669,"只跟随白点；按 PS_KEY1 可停止",24,MUTED)
        elif phase == "vprocessing":
            text(72,110,"正在核对验证结果",54)
            text(72,240,"采样已结束，可以移开视线。",32,MUTED)
            text(72,340,"核对九段统计和模型读回，不重新校准。",28)
        elif phase in ("validated","usable","validation_failed"):
            text(72,110,"本轮方向验证通过" if phase=='validated' else "方向基线可用" if phase=='usable' else "验证结束，需继续调整",54,ERROR if phase=='validation_failed' else ACCENT)
            text(72,240,"可以移开视线",44)
            text(72,350,view.detail,28,MUTED)
            if phase=='usable':text(72,430,"个人模型已保留；无效样本不参与控制，精确定位仍待调整。",28,MUTED)
            text(72,650,"PS_KEY0 重做验证  ·  PS_KEY1 停止",28,MUTED)
        elif phase == "prepare":
            text(72, 65, "即将开始，请坐稳", 44)
            text(72, 150, "倒计时结束后，看屏幕上的白点。", 28, MUTED)
            text(595, 280, str(view.remaining), 72, ACCENT)
            text(430, 470, "正常眨眼，不需要憋着不眨", 28)
        elif phase in ("settle", "collect", "waiting"):
            label = {"settle": "请看白点", "collect": "保持注视", "waiting": "请继续看白点"}[phase]
            text(72, 42, "%s  |  第 %d / %d 点" % (label,view.point+1,len(self.points)), 32)
            if phase == "waiting":
                text(72, 94, (view.detail+"；" if view.detail else "")+"最多再等 %d 秒" % view.remaining, 24, MUTED)
            else:
                text(72, 94, "还剩 %d 秒，完成后自动换点" % view.remaining, 24, MUTED)
            x,y = self.points[view.point]
            x,y = round(x*1280),round(y*720)
            d.ellipse((x-17,y-17,x+17,y+17), fill=TEXT)
            d.ellipse((x-3,y-3,x+3,y+3), fill=BG)
            d.rectangle((72,647,1208,653), fill=(55,65,69))
            d.rectangle((72,647,72+round(1136*view.progress),653), fill=ACCENT)
            text(72, 669, "只看白点；按 PS_KEY1 可暂停" if self.buttons else "只看白点；无需操作电脑", 24, MUTED)
        elif phase == "compute":
            text(72, 110, "正在计算三个方向" if self.relative else "正在处理校准结果", 54)
            text(72, 218, "请继续看中央白点，核对真实注视数据。" if self.live else "白点采样已结束，可以移开视线。", 32, MUTED)
            if self.live:
                d.ellipse((623,343,657,377),fill=TEXT)
            text(72, 650, "成功后自动进入离线菜单" if self.local_media else "成功后自动进入选区验证，最多 45 秒" if self.selection_test else "收到结果后自动结束，最多 45 秒", 28, MUTED)
        elif phase == "diagnostic":
            text(72,65,"眼部定位对照检查",44)
            text(72,145,"保持坐姿，看中央白点；还剩 %d 秒。"%view.remaining if self.selection_test else "保持坐姿，看中央白点；约 15 秒后自动结束。",28,MUTED)
            text(72,210,view.detail,28,ACCENT)
            d.ellipse((623,343,657,377),fill=TEXT)
            text(72,669,"只看白点；按 PS_KEY1 可暂停",24,MUTED)
        else:
            title = {"complete": "演练结束" if view.preview else "校准完成",
                     "failed": "本次已停止", "cancelled": "已暂停", "checked":"定位检查结束"}.get(phase,"本次已停止")
            text(72, 110, title, 54, ERROR if phase == "failed" else ACCENT)
            text(72, 218, "可以移开视线", 44)
            text(72, 332, view.detail, 28, MUTED)
            text(72, 650, ("按 PS_KEY0 可重做验证" if self.validation else "按 PS_KEY0 可重新校准" if self.live else "按 PS_KEY0 可重新演练") if self.buttons else "等待下一次开始指令", 28, MUTED)
        # RGB drawing -> the audited overlay's BGR888 DMA layout.
        frame=np.asarray(canvas)[:,:,::-1].copy()
        if phase=="selection":
            self.selection_key,self.selection_base=key,frame.copy()
            self.selection_progress(frame,view)
        self.tracking_overlay(frame,view)
        return frame

    def tracking_overlay(self, frame, view):
        """Cache only telemetry strips; changing distance cannot stale the base."""
        if not view.tracking:
            return
        if self.tracking_key != view.tracking:
            strips=[]
            for i,words in enumerate(view.tracking):
                canvas=Image.new("RGB",(1280,34),BG)
                self.write_text(ImageDraw.Draw(canvas),60,0,words,24,ACCENT if i==0 else MUTED)
                strips.append(np.asarray(canvas)[:,:,::-1].copy())
            self.tracking_key,self.tracking_strips=view.tracking,strips
        positions=(88,) if view.phase=="video" else (140,633) if view.phase=="menu" else (576,612)
        for y,strip in zip(positions,self.tracking_strips):
            frame[y:y+34]=strip

    def write_text(self, draw, x, y, words, size=32, color=TEXT):
        baseline = self.fonts[size].getmetrics()[0]
        for run in re.findall(r"[\x00-\x7f]+|[^\x00-\x7f]+", words):
            font = self.latin_fonts[size] if run.isascii() else self.fonts[size]
            draw.text((x,y+baseline-font.getmetrics()[0]),run,font=font,fill=color)
            x += font.getlength(run) if hasattr(font,"getlength") else font.getsize(run)[0]

    def text_width(self, words, size):
        total = 0
        for run in re.findall(r"[\x00-\x7f]+|[^\x00-\x7f]+", words):
            font = self.latin_fonts[size] if run.isascii() else self.fonts[size]
            total += font.getlength(run) if hasattr(font,"getlength") else font.getsize(run)[0]
        return total

    def wrapped(self, words, size, width, lines=2):
        result, line = [], ""
        for char in words.replace("\n"," "):
            if line and self.text_width(line+char,size) > width:
                result.append(line)
                line = ""
                if len(result) == lines:
                    result[-1] = result[-1][:-1] + "…"
                    return result
            line += char
        if line:result.append(line)
        return result

    def media_render(self, view):
        if view.phase == "video":
            # Chinese font drawing is expensive on Cortex-A9. Cache the static
            # shell independently of JPEG serials; only copy/blit each frame.
            key = (view.title,view.subtitle,view.footer,view.page_id)
            if key != self.video_shell_key:
                canvas = Image.new("RGB",(1280,720),BG)
                draw = ImageDraw.Draw(canvas)
                title = (view.title or "正在观看") + (" · " + view.subtitle if view.subtitle else "")
                self.write_text(draw,60,34,self.wrapped(title,44,1160,1)[0],44)
                self.write_text(draw,60,670,view.footer,24,MUTED)
                self.write_text(draw,440,340,"正在读取视频",32,MUTED)
                self.video_shell_key = key
                self.video_shell = np.asarray(canvas)[:,:,::-1].copy()
            frame = self.video_shell.copy()
            self.tracking_overlay(frame,view)
            if view.video_image is not None:
                picture = view.video_image.resize((960,540),getattr(Image,"Resampling",Image).NEAREST)
                pixels = np.frombuffer(picture.tobytes("raw","BGR"),dtype=np.uint8).reshape((540,960,3))
                top=124 if view.tracking else 106
                frame[top:top+540,160:1120] = pixels
            return frame
        key=(view.phase,view.title,view.labels,view.subtitle,view.detail,view.footer,
             view.page_id,view.reading,view.hover,view.selected,view.paused,
             view.video_frame,view.confirmations,bool(view.tracking))
        if key == self.media_key and self.media_base is not None:
            frame = self.media_base.copy()
        else:
            canvas = Image.new("RGB",(1280,720),BG)
            draw = ImageDraw.Draw(canvas)
            self.write_text(draw,60,34,view.title,44)
            for i,line in enumerate(self.wrapped(view.subtitle,28,1160,1 if view.tracking else 2)):
                self.write_text(draw,60,100+i*34,line,28,MUTED)
            if view.phase == "menu":
                for i,label in enumerate(view.labels):
                    left=round(i*1280/3)+22
                    right=round((i+1)*1280/3)-22
                    active=i==view.hover and not view.paused and bool(label)
                    draw.rectangle((left,198,right,550),
                        fill=(39,51,44) if active else (28,34,39),
                        outline=ACCENT if active else (65,76,81),width=5 if active else 2)
                    size=44 if self.text_width(label,44)<=right-left-44 else 32
                    lines=self.wrapped(label,size,right-left-44,3)
                    top=312-len(lines)*(size+10)//2
                    for row,line in enumerate(lines):
                        x=left+(right-left-self.text_width(line,size))/2
                        self.write_text(draw,x,top+row*(size+10),line,size,ACCENT if active else TEXT)
                    if label:draw.rectangle((left+24,489,right-24,505),fill=(65,76,81))
                for i,line in enumerate(self.wrapped(view.detail,28,1160,1 if view.tracking else 2)):
                    self.write_text(draw,60,578+i*34,line,28,
                                    ERROR if "失败" in view.detail or "缺失" in view.detail or "未找到" in view.detail else MUTED)
            self.write_text(draw,60,670,view.footer,24,ACCENT if view.paused else MUTED)
            frame=np.asarray(canvas)[:,:,::-1].copy()
            self.media_key,self.media_base=key,frame.copy()
        self.tracking_overlay(frame,view)
        if view.phase=="menu":self.selection_progress(frame,view)
        return frame

    @staticmethod
    def selection_progress(frame,view):
        if view.hover>=0 and not view.paused and view.progress>0:
            left=round(view.hover*1280/3)+22
            right=round((view.hover+1)*1280/3)-22
            end=left+24+round((right-left-48)*view.progress)
            frame[489:506,left+24:end+1]=ACCENT[::-1]
