"""One display owner: cached menu shells and a silent, contain-fit video ROI."""
import sys
import math
import hashlib
import json
from pathlib import Path
import threading
import time

import numpy as np
from PIL import Image,ImageDraw,ImageFont

BASE=Path(__file__).resolve().parent
BACKGROUND=(10,19,30)
CARD=(20,35,50)
OUTLINE=(49,77,97)
ACCENT=(102,217,219)
TEXT=(236,245,250)
MUTED=(161,186,202)
PROGRESS_LABELS={'idle':'注视此处进行选择','dwell':'正在确认',
    'locked':'请先看其他区，再选此处','executed':'已执行，请换区再选',
    'reading':'切页保护，请稍候','lost':'等待有效注视'}
BOXES=tuple((round(i*1280/3)+18,140,round((i+1)*1280/3)-18,630) for i in range(3))
FREQUENCY_BOXES=((8,'前进',(26,140,410,332)),(10,'后退',(870,140,1254,332)),
                 (12,'左转',(26,446,410,638)),(14,'右转',(870,446,1254,638)))
SELECTED=(24,91,68)
ICONS={
    'home':('direction','speech','play'),'drive':('direction','pause','play'),
    'speed':('plus','return','minus'),'media':('play','return','music'),
    'video':('next',None,'heart'),'video_nav':('previous','return','next'),
    'video_rate':('heart','return','minus'),'speech':('speech','return','speech'),
    'music':('previous','return','next'),'music_offer':('music','pause','return'),
    'fatigue_alert':('return','pause','pause')}


def rounded_box(draw,box,radius,fill,outline=None,width=1):
    """Rounded cards using primitives available in the board's Pillow 7.0."""
    def paint(bounds,r,color):
        left,top,right,bottom=bounds
        draw.rectangle((left+r,top,right-r,bottom),fill=color)
        draw.rectangle((left,top+r,right,bottom-r),fill=color)
        for x in (left,right-2*r):
            for y in (top,bottom-2*r):draw.ellipse((x,y,x+2*r,y+2*r),fill=color)
    paint(box,radius,outline if outline is not None else fill)
    if outline is not None:
        left,top,right,bottom=box
        paint((left+width,top+width,right-width,bottom-width),radius-width,fill)


def centered_text(canvas,renderer,words,box,size,color=TEXT):
    """Place the visible glyph bounds at the centre, including mixed CJK/Latin."""
    if not words:return None
    width=box[2]-box[0]-24
    words=str(words)
    if renderer.text_width(words,size)>width:
        words=renderer.wrapped(words,size,width,1)[0].rstrip('…')
        while words and renderer.text_width(words+'...',size)>width:words=words[:-1]
        words+='...'
    height=max(sum(font.getmetrics()) for font in (renderer.fonts[size],renderer.latin_fonts[size]))+size+8
    mask=Image.new('L',(math.ceil(renderer.text_width(words,size))+8,height))
    renderer.write_text(ImageDraw.Draw(mask),4,0,words,size,255)
    bounds=mask.getbbox()
    if bounds is None:return None
    mask=mask.crop(bounds)
    x=round((box[0]+box[2]-mask.width)/2);y=round((box[1]+box[3]-mask.height)/2)
    canvas.paste(color,(x,y),mask)
    return (x,y,x+mask.width,y+mask.height)


def image_from_bgr(pixels):
    height,width,_=pixels.shape
    return Image.frombytes('RGB',(width,height),pixels.tobytes(),'raw','BGR')


def image_to_bgr(image):
    return np.frombuffer(image.tobytes('raw','BGR'),dtype=np.uint8).reshape((image.height,image.width,3)).copy()


def draw_icon(draw,cx,cy,kind):
    draw.ellipse((cx-42,cy-42,cx+42,cy+42),fill=(22,52,66),outline=(48,100,118),width=2)
    line=lambda points:draw.line([(cx+x,cy+y) for x,y in points],fill=ACCENT,width=4)
    if kind in ('previous','next','return'):
        sign=-1 if kind in ('previous','return') else 1
        line([(-20*sign,0),(20*sign,0)]);line([(6*sign,-14),(20*sign,0),(6*sign,14)])
        if kind=='return':line([(20,-17),(20,0)])
    elif kind in ('plus','minus'):
        line([(-20,0),(20,0)])
        if kind=='plus':line([(0,-20),(0,20)])
    elif kind=='direction':
        line([(0,22),(0,-23)]);line([(-15,-7),(0,-23),(15,-7)])
        line([(-20,16),(0,-4),(20,16)])
    elif kind=='play':
        rounded_box(draw,(cx-24,cy-20,cx+24,cy+20),7,(22,52,66),ACCENT,3)
        draw.polygon([(cx-5,cy-11),(cx+12,cy),(cx-5,cy+11)],fill=ACCENT)
    elif kind=='pause':
        rounded_box(draw,(cx-16,cy-21,cx-6,cy+21),3,ACCENT)
        rounded_box(draw,(cx+6,cy-21,cx+16,cy+21),3,ACCENT)
    elif kind=='speech':
        rounded_box(draw,(cx-24,cy-19,cx+24,cy+15),8,(22,52,66),ACCENT,3)
        line([(-13,15),(-13,25),(-3,15)])
        for x in (-12,0,12):draw.ellipse((cx+x-2,cy-3,cx+x+2,cy+1),fill=ACCENT)
    elif kind=='music':
        line([(-6,17),(-6,-19),(17,-24),(17,12)])
        draw.ellipse((cx-20,cy+10,cx-4,cy+22),fill=ACCENT)
        draw.ellipse((cx+3,cy+5,cx+19,cy+17),fill=ACCENT)
    elif kind=='heart':
        draw.ellipse((cx-23,cy-20,cx+2,cy+5),fill=ACCENT)
        draw.ellipse((cx-2,cy-20,cx+23,cy+5),fill=ACCENT)
        draw.polygon([(cx-23,cy-5),(cx+23,cy-5),(cx,cy+24)],fill=ACCENT)


def status_bar(canvas,renderer,labels):
    draw=ImageDraw.Draw(canvas);draw.rectangle((0,80,1279,133),fill=BACKGROUND)
    for card,label in zip(BOXES,labels):
        box=(card[0],86,card[2],128)
        rounded_box(draw,box,12,(15,30,43),(38,63,81))
        centered_text(canvas,renderer,label,box,24,MUTED)


def present_frame(lib,target,clock=time.monotonic,sleep=time.sleep,not_before=None,require=None):
    """Require a real latch and scan progress; don't wait for an extra scan."""
    waiting=clock()
    if not_before is not None:
        delay=not_before-clock()
        if delay>0:sleep(delay)
    if require:require()
    counter=lib.display_frames();started=clock()
    if not lib.display_park(target) or lib.display_index()!=target:
        raise ValueError('Video frame did not latch')
    while lib.display_frames()==counter:
        if clock()-started>.1:raise ValueError('Display scan stalled')
        sleep(.001)
    if lib.display_status()&0x80000ff1:raise ValueError('Display DMA error/halt')
    return dict(playback_wait_ms=(started-waiting)*1000,latch_scan_ms=(clock()-started)*1000)


class RuntimeWatch:
    """Move the unchanged runtime checks off the frame path; expired checks abort."""
    def __init__(self,check,clock=time.monotonic):
        self.check=check;self.clock=clock;self.verified=clock();self.error=None
        self.check_ms=[]
        self.diagnostic=dict(checks=0,started=None,pending=False,last_check_ms=0.,
            maximum_check_ms=0.,wake_delay_ms=0.,maximum_wake_delay_ms=0.,native_tid=None)
        self.stopped=threading.Event()
        self.thread=threading.Thread(target=self._run,name='display-runtime-guard',daemon=True)
        self.thread.start()

    def _run(self):
        due=self.clock()+1
        while not self.stopped.wait(1):
            started=self.clock()
            delay=max(0.,started-due)*1000
            self.diagnostic=dict(self.diagnostic,started=started,pending=True,
                wake_delay_ms=delay,maximum_wake_delay_ms=max(delay,self.diagnostic['maximum_wake_delay_ms']),
                native_tid=threading.get_native_id())
            try:self.check()
            except Exception as error:
                self.diagnostic=dict(self.diagnostic,pending=False,
                    last_check_ms=(self.clock()-started)*1000)
                self.error=error;return
            self.verified=self.clock()
            duration=(self.verified-started)*1000
            self.check_ms.append(duration)
            self.diagnostic=dict(self.diagnostic,checks=self.diagnostic['checks']+1,
                pending=False,last_check_ms=duration,
                maximum_check_ms=max(duration,self.diagnostic['maximum_check_ms']))
            due=self.verified+1

    def snapshot(self):
        row=self.diagnostic.copy();now=self.clock()
        row.update(verification_age_ms=(now-self.verified)*1000,
            pending_elapsed_ms=(now-row['started'])*1000 if row['pending'] else 0.,
            thread_alive=self.thread.is_alive(),error=str(self.error) if self.error else None)
        return row

    def require(self):
        if self.error:raise RuntimeError('Runtime admission revoked: '+str(self.error))
        if self.clock()-self.verified>4:raise RuntimeError('Runtime guard heartbeat expired')

    def ready(self):
        if self.error:raise RuntimeError('Runtime admission revoked: '+str(self.error))
        return 0<=self.clock()-self.verified<=4

    def close(self):
        self.stopped.set();self.thread.join(timeout=3.5)
        if self.thread.is_alive():raise RuntimeError('Runtime check did not stop')


class UnifiedDisplay:
    # Deterministic navigation fixture, NOT real gaze/MI/SSVEP commands.
    script=((0,'home'),(3,'speed'),(8,'drive'),(12,'media'),(16,'video'),
            (78,'video_nav'),(82,'video_rate'),(86,'speech'),(90,'music'),(94,'home'))
    roi=(448,245,384,216)

    def __init__(self,eye_root,fitter=None,live=False,dimensions=(384,216),
                 shell_cache=None,font_paths=None,direction_idle_enabled=True):
        sys.path.insert(0,str(BASE/'system_runtime'))
        sys.path.insert(0,str(Path(eye_root)/'src'))
        from guide_render import Renderer
        from guardianloop_system.core import SystemController,TITLES,LABELS
        from guardianloop_system.page_policy import tasks_for
        self.controller=SystemController(time.monotonic(),direction_idle_enabled=direction_idle_enabled)
        self.tasks_for=tasks_for
        self.live=live;self.renderer=Renderer(font=str(font_paths[0]) if font_paths else None,relative=True,entry_check=live,
            buttons=live,live=live,selection_test=live)
        if font_paths:
            self.renderer.latin_fonts={size:ImageFont.truetype(str(font_paths[1]),size)
                                      for size in self.renderer.fonts}
        self.dimensions=dimensions
        self.calibration_view=None;self.overlay_key=None;self.overlays={};self.frequency_state=None
        if dimensions==(288,512):self.roi=(505,148,270,480)
        elif dimensions!=(384,216):raise ValueError('Unsupported unified ROI')
        self.shells={};self.label_bounds={};self.buffer_pages={};self.page_index=-1;self.transitions=[]
        self.buffer_feedback={};self.feedback_strips={}
        self.fitter=fitter
        self.x_indexes=np.arange(384)*640//384;self.y_indexes=np.arange(216)*360//216
        self.shell_contract=dict(format='guardianloop-menu-shells-v1',live=live,dimensions=list(dimensions),
            direction_idle_enabled=direction_idle_enabled,
            renderer_sha=hashlib.sha256((Path(eye_root)/'src/guide_render.py').read_bytes()).hexdigest(),
            display_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            fonts=[hashlib.sha256(Path(face.path).read_bytes()).hexdigest()
                   for face in (self.renderer.fonts[24],self.renderer.latin_fonts[24])],
            titles=TITLES,labels={page:list(labels) for page,labels in LABELS.items()})
        if shell_cache is not None:
            self.load_shell_cache(shell_cache)
            return
        font=self.renderer
        for page,title in TITLES.items():
            canvas=Image.new('RGB',(1280,720),BACKGROUND);draw=ImageDraw.Draw(canvas)
            font.write_text(draw,26,28,'GuardianLoop',24,ACCENT)
            centered_text(canvas,font,'综合控制' if page=='home' else title,(260,14,1020,76),44)
            badge=(1060,23,1262,65)
            rounded_box(draw,badge,12,(19,47,53),(45,92,103))
            centered_text(canvas,font,'静音 | 虚拟',badge,24,ACCENT)
            status_bar(canvas,font,('实时接口候选' if live else '隔离页面回放','脑电需质量合格','眼控需三点标定'))
            self.label_bounds[page]=[]
            for i,(box,label) in enumerate(zip(BOXES,LABELS[page])):
                left,top,right,bottom=box
                rounded_box(draw,(left,top+5,right,bottom+5),24,(5,12,20))
                rounded_box(draw,box,24,CARD,OUTLINE,2)
                if label:
                    draw_icon(draw,(left+right)//2,285,ICONS[page][i])
                    size=54 if font.text_width(label,54)<=right-left-48 else 44
                    self.label_bounds[page].append(centered_text(canvas,font,label,box,size))
                else:self.label_bounds[page].append(None)
            if page=='drive':
                draw.rectangle((0,140,1279,638),fill=BACKGROUND)
                self.paint_frequencies(canvas,None)
            if page=='video':
                x,y,w,h=self.roi;draw.rectangle((x,y,x+w-1,y+h-1),fill=(0,0,0))
            idle_note='15秒无选择退出' if direction_idle_enabled else '测试期不自动退出'
            footer='未启用闪烁 | 手机强制停止 / '+idle_note+' | 轮椅不动' if page=='drive' else '心情：模型估计 | 疲劳：辅助参考 | 轮椅不动' if live else '隔离页面预览 | 非真实脑电或眼控结果'
            centered_text(canvas,font,footer,(18,639,1262,673),24,MUTED)
            dock=(18,676,1262,714)
            rounded_box(draw,dock,11,(15,30,43),(38,63,81))
            centered_text(canvas,font,'默认最低档 | 方向停止 | 全程静音',dock,24,MUTED)
            self.shells[page]=np.asarray(canvas)[:,:,::-1].copy()

    def save_shell_cache(self,path):
        metadata=dict(contract=self.shell_contract,bounds=self.label_bounds,
            hashes={page:hashlib.sha256(frame.tobytes()).hexdigest() for page,frame in self.shells.items()})
        destination=Path(path);temporary=destination.with_suffix('.part')
        with temporary.open('wb') as handle:
            np.savez_compressed(handle,metadata=np.array(json.dumps(metadata)),**self.shells)
        temporary.replace(destination)

    def load_shell_cache(self,path):
        if Path(path).stat().st_size>60*1024*1024:
            raise ValueError('Oversize menu cache')
        with np.load(path,allow_pickle=False) as data:
            metadata=json.loads(str(data['metadata'].item()))
            if metadata['contract']!=self.shell_contract:
                raise ValueError('Menu cache contract changed; prepare it off the live path')
            if set(data.files)!=set(self.shell_contract['titles'])|{'metadata'}:
                raise ValueError('Incomplete menu cache')
            for page in self.shell_contract['titles']:
                frame=data[page]
                if (frame.shape!=(720,1280,3) or frame.dtype!=np.uint8 or
                    hashlib.sha256(frame.tobytes()).hexdigest()!=metadata['hashes'][page]):
                    raise ValueError('Corrupt menu cache')
                self.shells[page]=frame
            self.label_bounds=metadata['bounds']

    def advance(self,elapsed,now):
        if self.live:
            self.controller.tick(now);return
        index=max(i for i,(at,_) in enumerate(self.script) if elapsed>=at)
        if index!=self.page_index:
            self.page_index=index;self.controller._enter(self.script[index][1],now)
            self.transitions.append(dict(elapsed=elapsed,page=self.controller.page,source='scripted_navigation_not_user'))
        self.controller.tick(now)

    def feedback(self,now):
        from guardianloop_system.core import LABELS
        if not self.live:return ()
        state=self.controller;selection=state.selection
        fresh=selection.last_source is not None and 0<=now-selection.last_source<=selection.stale_seconds
        reading=state.presented_page!=state.page_id or now<state.read_until
        result=[]
        for region,label in enumerate(state.labels()):
            if not label:result.append(None)
            elif reading:result.append(('reading',0))
            elif not fresh or selection.paused:result.append(('lost',0))
            elif selection.hover!=region:result.append(('idle',0))
            elif selection.locked==region:
                receipt=state.last_selection
                executed=receipt is not None and receipt['page_id']==state.page_id and receipt['region']==region
                result.append(('executed',20) if executed else ('locked',0))
            else:result.append(('dwell',int(min(1,max(0,selection.progress))*20)))
        return tuple(result)

    def presentation_key(self,now):
        return (self.controller.page_id,self.overlay_key,self.feedback(now),
                self.controller.selected_frequency if self.controller.page=='drive' else None)

    def paint_frequencies(self,canvas,selected):
        draw=ImageDraw.Draw(canvas)
        for hz,direction,box in FREQUENCY_BOXES:
            chosen=selected==hz
            rounded_box(draw,box,20,SELECTED if chosen else CARD,ACCENT if chosen else OUTLINE,3)
            left,top,right,bottom=box
            centered_text(canvas,self.renderer,'%d Hz / %s'%(hz,direction),(left,top+20,right,bottom-56),44)
            centered_text(canvas,self.renderer,'已选中（可信候选）' if chosen else '未选中',
                          (left,bottom-58,right,bottom-12),24,ACCENT if chosen else MUTED)
        box=BOXES[1]
        rounded_box(draw,box,24,CARD,OUTLINE,2)
        draw_icon(draw,(box[0]+box[2])//2,285,'return')
        centered_text(canvas,self.renderer,'返回主页',box,54)

    def feedback_strip(self,width,mode):
        key=(width,mode)
        if key not in self.feedback_strips:
            canvas=Image.new('RGB',(width,96),CARD)
            draw=ImageDraw.Draw(canvas)
            rounded_box(draw,(0,14,width-1,28),6,OUTLINE)
            centered_text(canvas,self.renderer,PROGRESS_LABELS[mode],(0,38,width,94),24,
                ACCENT if mode in ('dwell','executed') else MUTED)
            self.feedback_strips[key]=np.asarray(canvas)[:,:,::-1].copy()
        return self.feedback_strips[key]

    def paint_feedback(self,buffer,feedback):
        for box,item in zip(BOXES,feedback):
            if item is None:continue
            x,y=box[0]+24,box[3]-120;w=box[2]-box[0]-48
            mode,steps=item
            np.copyto(buffer[y:y+96,x:x+w],self.feedback_strip(w,mode))
            if steps:
                buffer[y+17:y+26,x+3:x+3+round((w-6)*steps/20)]=ACCENT[::-1]

    def compose(self,buffer,index,frame=None,now=None):
        now=time.monotonic() if now is None else now
        page=self.controller.page
        token=(page,self.overlay_key,self.controller.page_id)
        changed=self.buffer_pages.get(index)!=token
        if changed:
            np.copyto(buffer,self.overlays.get(page,self.shells[page]));self.buffer_pages[index]=token
        feedback=self.feedback(now)
        feedback_changed=bool(feedback) and (changed or self.buffer_feedback.get(index)!=feedback)
        if feedback_changed:
            self.paint_feedback(buffer,feedback);self.buffer_feedback[index]=feedback
        if frame is not None:
            x,y,w,h=self.roi
            if page!='video' or frame.size not in (640*360*3,self.dimensions[0]*self.dimensions[1]*3):
                raise ValueError('Unexpected video page/frame')
            if frame.size==w*h*3:
                np.copyto(buffer[y:y+h,x:x+w,:],frame.reshape((h,w,3)))
            elif self.fitter:
                sw,sh=self.dimensions if frame.size==self.dimensions[0]*self.dimensions[1]*3 else (640,360)
                if self.fitter(frame.ctypes.data,sw,sh,buffer[y:y+h,x:x+w,:].ctypes.data,w,h,3840)!=1:
                    raise ValueError('Video fit failed')
            else:
                sw,sh=self.dimensions if frame.size==self.dimensions[0]*self.dimensions[1]*3 else (640,360)
                pixels=frame.reshape((sh,sw,3))
                np.copyto(buffer[y:y+h,x:x+w,:],pixels[(np.arange(h)*sh//h)[:,None],(np.arange(w)*sw//w)[None,:]])
        # Full-width row strip is contiguous: safe cache flush, unlike strided ROI.
        if changed:buffer.flush()
        elif frame is not None:
            x,y,w,h=self.roi;buffer[y:y+h,:,:].flush()
        elif feedback_changed:buffer[510:606,:,:].flush()
        return changed or feedback_changed

    def refresh_labels(self,brain,eye,video_name,audio=None):
        state=self.controller
        emotion=brain.get('emotion',{});fatigue=brain.get('fatigue',{})
        emotion_names={'boring':'中性情绪','calm':'中性情绪','horror':'负向情绪','funny':'正向情绪'}
        mood=emotion_names.get(emotion.get('class_name',emotion.get('label')),'无可信结果') if emotion.get('valid') is True else '无可信结果'
        level=fatigue.get('level','--') if fatigue.get('valid') is True else '无可信结果'
        if fatigue.get('calibration_retained') is True and fatigue.get('valid') is not True:
            mood='等待新鲜数据';level='校准已保留'
        key=(state.page,state.speed_level,state.direction,state.rating,state.video_index,mood,level,
             eye.get('state','未连接'),video_name,state.phrase,state.song_index,tuple(state.alerts.values()),
             state.selected_frequency,state.fatigue_ack_ready(state.last_now),state.force_stopped,
             math.ceil(max(0,state.direction_idle_deadline-state.last_now)) if state.direction_idle_deadline is not None else None,
             (audio['volume_percent'],audio['player']['phase']) if audio else None)
        if key==self.overlay_key:return False
        self.overlay_key=key;self.overlays={};self.frequency_state=state.selected_frequency
        for page in (state.page,):
            # On video pages only these two opaque bands change; keep the video
            # and menu body byte-for-byte from its already prepared BGR shell.
            video_labels=page=='video'
            rgb=Image.new('RGB',(1280,720)) if video_labels else image_from_bgr(self.shells[page])
            draw=ImageDraw.Draw(rgb)
            if audio:
                badge=(1060,23,1262,65)
                draw.rectangle(badge,fill=BACKGROUND)
                rounded_box(draw,badge,12,(19,47,53),(45,92,103))
                centered_text(rgb,self.renderer,'音频 | %d%%'%audio['volume_percent'],badge,24,ACCENT)
                if page=='music':
                    draw.rectangle((260,14,1020,76),fill=BACKGROUND)
                    centered_text(rgb,self.renderer,'歌曲选择',(260,14,1020,76),44)
            fatigue_text={0:'正常',1:'轻度',2:'严重','normal':'正常','mild':'轻度','severe':'严重'}.get(level,str(level))
            status_bar(rgb,self.renderer,('心情参考 '+str(mood),'疲劳 '+fatigue_text,'眼控 '+str(eye.get('state','未连接'))))
            if page=='drive':
                self.paint_frequencies(rgb,state.selected_frequency)
                remaining=math.ceil(max(0,state.direction_idle_deadline-state.last_now)) if state.direction_idle_deadline is not None else 15
                centered_text(rgb,self.renderer,'%d秒无新选择后返回'%remaining if state.direction_idle_enabled
                              else '注视中央框返回主页',(424,448,856,492),24,MUTED)
            if page=='home' and 'fatigue' in state.alerts:
                rounded_box(draw,BOXES[1],24,CARD,OUTLINE,2)
                centered_text(rgb,self.renderer,'查看疲劳警示',BOXES[1],44)
            if page=='fatigue_alert':
                box=BOXES[1];rounded_box(draw,box,24,CARD,OUTLINE,2)
                centered_text(rgb,self.renderer,'确认警示' if state.fatigue_ack_ready(state.last_now) else '等待恢复正常',box,44)
            draw.rectangle((0,674,1279,719),fill=BACKGROUND)
            dock=(18,676,1262,714)
            rounded_box(draw,dock,11,(15,30,43),(38,63,81))
            direction={'stop':'停止','left':'左','right':'右','forward':'前进','backward':'后退'}.get(state.direction,state.direction)
            line=('虚拟档位 %d/3 | 方向 %s | '%(state.speed_level,direction))+str(video_name)
            audio_note=('音量 %d%% / %s'%(audio['volume_percent'],audio['player']['phase'])) if audio else '本轮静音'
            if page=='speech' and state.phrase:line='已选择：'+state.phrase+'（'+audio_note+'）'
            elif page=='music':line='已选歌曲 %d/%d（%s）'%(state.song_index+1,state.song_count,audio_note)
            if state.alerts:line='；'.join(state.alerts.values())
            if page=='fatigue_alert':line='恢复正常后看中区确认 | 确认后方向仍停止，需重新启用'
            elif state.force_stopped:line='人工强制停止已执行 | 返回主页 | 必须重新进入并启用方向'
            centered_text(rgb,self.renderer,line,dock,24)
            if video_labels:
                overlay=self.shells[page].copy()
                for top,bottom in ((80,134),(674,720)):
                    overlay[top:bottom]=image_to_bgr(rgb.crop((0,top,1280,bottom)))
                if audio:overlay[23:66,1060:1263]=image_to_bgr(rgb.crop((1060,23,1263,66)))
                self.overlays[page]=overlay
            else:self.overlays[page]=image_to_bgr(rgb)
        return True

    def lease(self,now):
        return dict(page=self.controller.page,updated_monotonic=now,
            tasks=self.tasks_for(self.controller.page),mode='live_readonly_hdmi' if self.live else 'scripted_hdmi_replay',
            physical_output_enabled=False,live_eeg_connected=self.live,live_gaze_connected=False)
