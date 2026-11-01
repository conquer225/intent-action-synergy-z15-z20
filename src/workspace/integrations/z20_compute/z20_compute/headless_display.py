"""One RGB720p scene for HDMI and HTTP; NumPy plus a bundled CJK glyph atlas."""
import math
import ctypes as C
import os
import sys
from pathlib import Path
import numpy as np

TITLES=dict(overview='联机总览',emotion='脑电情绪',fatigue='脑电疲劳',depth='双目测距',
            cloud='局部点云',person_dog='人狗关系',sound='声音分类',audio='静音音频分析',adda='AD/DA 准备')
LABELS=dict(emotion=('负向','中性','正向'),fatigue=('清醒','轻度疲劳','重度疲劳'),sound=('拍手','口哨','敲击'))
RELATIONS=dict(holding='抱着',petting='抚摸',leashing='牵着',walking_with_dog='遛狗')
STATES=dict(waiting_input='等待输入',disconnected='连接中断',expired='结果过期',uncalibrated='未标定',
            model_unavailable='模型未就绪',prediction='有效结果',silence='静音拒识',unrecognized='未识别',
            waiting_for_fresh_frame='等待新图像',prepared='接口已准备',sample_changed='切换录音中',
            source_unavailable='输入未就绪',measurement='测距结果',feature_version_mismatch='预处理版本不匹配')
BACKGROUND=(251,247,238);INK=(51,44,34);MUTED=(116,100,77);LINE=(217,204,182);ACCENT=(133,95,34)


def _label(task,result):
    index=result.get('class_id')
    return LABELS[task][index] if result.get('valid') and type(index) is int and 0<=index<3 else '--'


def describe_view(snapshot):
    page=snapshot.get('page','overview');detail=snapshot.get('detail',0)
    result=snapshot.get('results',{}).get(page,{})
    environment=snapshot.get('environment',{})
    entry=environment.get(page,{})
    payload=entry.get('payload') if entry.get('valid') else None
    lines=[];primary='等待输入';subtitle=''
    help_text='KEY2 冻结/恢复预览'
    if page in ('emotion','fatigue','sound'):
        primary=_label(page,result)
        lines=[STATES.get(result.get('state'),'等待有效结果'),
               '输入来源：'+str(result.get('source','--')),
               '窗口：'+str(result.get('window_id','--'))]
        if page=='sound':
            subtitle='登记录音样例：'+LABELS['sound'][detail%3]
            help_text='KEY2 切换拍手/口哨/敲击样例'
        else:
            subtitle='NPU 与原模型对照' if detail else 'NPU 三分类输出'
            help_text='KEY2 原模型与 NPU 对照'
            lines.append('录制回放 / 教师一致性验证')
    elif page=='depth':
        primary='%.2f m'%payload['distance_m'] if payload else '-- m'
        subtitle='指定区域到摄像头的距离'
        lines=[STATES.get(entry.get('state'),'未标定'), '米制结果绑定当前双目采集与标定',
               '有效点数：'+str(payload.get('valid_points',0) if payload else 0)]
        help_text='KEY2 原图/测距详情'
    elif page=='cloud':
        primary='米制点云' if payload and payload.get('metric') else '历史相对案例' if payload else '点云待标定'
        lines=['有效点数：'+str(payload.get('points',0) if payload else 0),
               '单位：'+str(payload.get('units','--') if payload else '--'),
               '真实静物标定与米制验证留现场']
        help_text='KEY2 切换观察角度'
    elif page=='person_dog':
        primary=RELATIONS.get(payload.get('interaction'),'未识别') if payload else '未识别'
        subtitle='视频标注回放' if detail else '平板照片像素配准'
        geometry=payload.get('geometry') if payload else None
        lines=['人狗中心间距（估算）：'+('%.2f m'%geometry['distance_m'] if geometry else '--'),
               '人到原相机（估算）：'+('%.2f m'%geometry['person_depth_m'] if geometry else '--'),
               '狗到原相机（估算）：'+('%.2f m'%geometry['dog_depth_m'] if geometry else '--'),
               '到平板屏幕的双目距离：未标定']
        help_text='KEY2 切换照片/视频输入'
    elif page=='audio':
        primary='%.1f dBFS'%payload['dbfs'] if payload else '-- dBFS'
        subtitle='文件输入 · 全程静音'
        lines=['波形、音量与 FFT 来自同一段 PCM',
               '频谱峰值：'+('%.1f Hz'%payload['peak_frequency_hz'] if payload and payload.get('peak_frequency_hz') is not None else '--'),
               '播放关闭 · 板载采音另验收']
        help_text='KEY2 波形/频谱详情'
    elif page=='adda':
        primary='接口准备';subtitle='MC8008 模拟采集与输出'
        lines=['采样接口 → 滤波/频谱 → DAC 输出',
               '当前未启用模拟输入输出','实际接线、量程与输出另行验收']
        help_text='KEY2 采样/输出准备说明'
    else:
        primary='辅助计算与外部情况识别'
        subtitle='Z15 负责人的输入与原控制 · Z20 返回辅助结果'
    return dict(page=page,title=TITLES[page],primary=primary,subtitle=subtitle,lines=lines,
                footer='KEY1 下页 · 长按 0.8 秒回总览 · '+help_text)


class GlyphAtlas:
    def __init__(self,path):
        with np.load(path,allow_pickle=False) as data:
            self.chars=str(data['chars'].item())
            self.sizes=data['sizes'].tolist();self.masks=data['masks'].copy();self.widths=data['widths'].copy()
        self.index={ch:i for i,ch in enumerate(self.chars)}
        library=Path(path).parent/'libz20_ui.so';self.native=None
        if library.is_file() and sys.platform=='linux' and os.uname().machine.startswith('arm'):
            self.native=C.CDLL(str(library.resolve()))
            self.native.z_ui_text.argtypes=[C.POINTER(C.c_ubyte),C.c_int,C.c_int,C.POINTER(C.c_ubyte),
                C.POINTER(C.c_int16),C.c_int,C.c_int,C.POINTER(C.c_uint32)]+[C.c_int]*7
            self.native.z_ui_text.restype=C.c_int

    def text(self,frame,text,x,y,*,size=28,color=INK,max_width=1190):
        slot=self.sizes.index(size);start=x
        if self.native is not None:
            indices=np.array([self.index.get(ch,self.index['?']) for ch in str(text)],dtype=np.uint32)
            result=self.native.z_ui_text(frame.ctypes.data_as(C.POINTER(C.c_ubyte)),1280,720,
                self.masks[slot].ctypes.data_as(C.POINTER(C.c_ubyte)),
                self.widths[slot].ctypes.data_as(C.POINTER(C.c_int16)),len(self.chars),self.masks.shape[-1],
                indices.ctypes.data_as(C.POINTER(C.c_uint32)),len(indices),x,y,max_width,*color)
            if result<0:raise ValueError('native text compositor rejected frame')
            return
        for ch in str(text):
            index=self.index.get(ch,self.index['?']);width=int(self.widths[slot,index])
            if x+width>start+max_width:break
            mask=self.masks[slot,index];h=min(mask.shape[0],frame.shape[0]-y);w=min(mask.shape[1],frame.shape[1]-x)
            mask=mask[:max(0,h),:max(0,w)]
            if x>=0 and y>=0 and h>0 and w>0:
                alpha=mask[:,:,None].astype(np.uint16)
                region=frame[y:y+h,x:x+w]
                region[:]=((region.astype(np.uint16)*(255-alpha)+np.asarray(color,np.uint16)*alpha+127)//255).astype(np.uint8)
            x+=width


def fit_image(frame,image,box=(40,148,700,470)):
    x,y,w,h=box
    image=np.asarray(image)
    if image.ndim!=3 or image.shape[2]!=3 or image.dtype!=np.uint8:return None
    scale=min(w/image.shape[1],h/image.shape[0]);iw=max(1,int(image.shape[1]*scale));ih=max(1,int(image.shape[0]*scale))
    left=x+(w-iw)//2;top=y+(h-ih)//2
    sy=np.minimum((np.arange(ih)/scale).astype(int),image.shape[0]-1)
    sx=np.minimum((np.arange(iw)/scale).astype(int),image.shape[1]-1)
    frame[top:top+ih,left:left+iw]=image[sy[:,None],sx]
    return left,top,scale


class HeadlessDisplay:
    def __init__(self,atlas):self.font=GlyphAtlas(atlas)

    def render(self,snapshot,*,image=None,analysis=None,cloud_points=None):
        view=describe_view(snapshot);frame=np.full((720,1280,3),BACKGROUND,np.uint8)
        text=lambda value,x,y,**kw:self.font.text(frame,value,x,y,**kw)
        text('Z20 · '+view['title'],40,22,size=40)
        text('已录制板测结果' if snapshot.get('fixture_scope') else '静音 · 原控制链保持',920,36,size=20,max_width=320)
        frame[92:94,40:1240]=LINE;frame[654:656,40:1240]=LINE
        text(view['footer'],40,674,size=20)
        page=view['page']
        if page=='overview':
            if image is not None:fit_image(frame,image,(40,155,590,420))
            text('人的状态',690,130,size=28)
            for index,task in enumerate(('emotion','fatigue')):
                result=snapshot.get('results',{}).get(task,{})
                text(TITLES[task]+'  '+_label(task,result),690,185+index*70,size=40,max_width=540)
            text('环境结果',690,345,size=28)
            env=snapshot.get('environment',{});person=env.get('person_dog',{})
            text(RELATIONS.get((person.get('payload') or {}).get('interaction'),'未识别') if person.get('valid') else '未识别',690,390,size=40)
            text('控制状态',690,485,size=28)
            text('辅助结果不触发执行设备',690,530,size=20)
            text('Z15 数据端：'+('已连接' if snapshot.get('connected') else '等待连接'),40,600,size=20)
        elif page in ('emotion','fatigue','sound'):
            text(view['subtitle'],40,123,size=28)
            text(view['primary'],40,185,size=40)
            result=snapshot.get('results',{}).get(page,{})
            if page in ('emotion','fatigue') and snapshot.get('detail'):
                reference=result.get('original_reference') if result.get('valid') else None
                label=LABELS[page][reference['class_id']] if reference else '等待原模型结果'
                text('原模型：'+label,670,185,size=40,max_width=560)
                ps=dict(valid=result.get('valid'),class_id=result.get('ps_class_id'))
                text('PS 整数参考：'+_label(page,ps),670,250,size=28)
            if result.get('valid') and result.get('scores') is not None:
                scores=np.asarray(result['scores'],float);lo=min(float(scores.min()),0.);hi=max(float(scores.max()),0.)
                span=max(hi-lo,1e-12)
                for i,(label,value) in enumerate(zip(LABELS[page],scores)):
                    y=285+i*64;text(label,40,y,size=28);text('%.4f'%value,1030,y,size=28,max_width=200)
                    frame[y+9:y+31,260:980]=LINE
                    frame[y+9:y+31,260:260+int(720*(value-lo)/span)]=ACCENT
            for i,line in enumerate(view['lines']):text(line,40,510+i*30,size=20)
        elif page=='audio':
            text(view['subtitle']+'  '+view['primary'],40,115,size=28)
            if analysis:
                wave=np.asarray(analysis.get('waveform_minmax',[]),float)
                if wave.shape==(160,2):
                    frame[270:271,45:1230]=LINE
                    for i,(low,high) in enumerate(wave):
                        x=45+int(i*1180/160);a=max(175,int(270-high*95));b=min(365,int(270-low*95)+1)
                        frame[a:b,x:x+3]=ACCENT
                amplitude=np.asarray(analysis.get('amplitudes',[]),float)
                if amplitude.shape==(513,):
                    for i,values in enumerate(np.array_split(amplitude,64)):
                        height=int(np.clip((20*np.log10(max(float(values.max()),1e-8))+100)/100,0,1)*190)
                        x=45+i*18;frame[595-height:595,x:x+12]=ACCENT
                text('波形（FS）',45,158,size=20);text('FFT 1024 · 0–8000 Hz · 频带峰值',45,377,size=20)
            else:text('等待录音文件分析',40,245,size=40)
            text(view['lines'][-1],40,615,size=20)
        else:
            text(view['subtitle'],40,115,size=28)
            if page=='adda':
                for index,label in enumerate(('ADC 采集','滤波/频谱','DAC 输出')):
                    x=45+index*235
                    frame[255:257,x:x+205]=LINE;frame[375:377,x:x+205]=LINE
                    frame[255:377,x:x+2]=LINE;frame[255:377,x+203:x+205]=LINE
                    text(label,x+18,295,size=28,max_width=170)
            if image is not None and page!='adda':
                transform=fit_image(frame,image,(40,173,700,440))
                env=snapshot.get('environment',{}).get('person_dog',{})
                if page=='person_dog' and env.get('valid') and transform:
                    for box in (env.get('payload') or {}).get('display_boxes',[]):
                        ox,oy,scale=transform;x0,y0,x1,y1=[int(v*scale) for v in box]
                        x0,x1=np.clip([ox+x0,ox+x1],0,1279);y0,y1=np.clip([oy+y0,oy+y1],0,653)
                        frame[y0:y0+3,x0:x1]=ACCENT;frame[y1-3:y1,x0:x1]=ACCENT
                        frame[y0:y1,x0:x0+3]=ACCENT;frame[y0:y1,x1-3:x1]=ACCENT
            text(view['primary'],780,190,size=40,max_width=460)
            for i,line in enumerate(view['lines']):text(line,780,305+i*58,size=20,max_width=460)
            if page=='cloud' and cloud_points is not None:
                points=np.asarray(cloud_points,float).reshape(-1,3);points=points[np.isfinite(points).all(1)][::max(1,len(points)//2200)]
                if len(points):
                    axes=((0,1),(2,1),(0,2))[snapshot.get('detail',0)%3];xy=points[:,axes]
                    xy=(xy-np.median(xy,0))/max(float(np.ptp(xy,axis=0).max()),1e-9)
                    pixels=(xy*np.array([520,-380])+np.array([390,390])).astype(int)
                    pixels=pixels[(pixels[:,0]>=40)&(pixels[:,0]<740)&(pixels[:,1]>=170)&(pixels[:,1]<610)]
                    frame[pixels[:,1],pixels[:,0]]=ACCENT
        return frame
