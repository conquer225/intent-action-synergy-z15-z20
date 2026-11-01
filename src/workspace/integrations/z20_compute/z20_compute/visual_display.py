"""Local NPU/menu rendering and latest-only decoded remote frame cache."""
import numpy as np
import time
from .headless_display import BACKGROUND,INK,MUTED,ACCENT,LINE
from .visual_demo import MODES
from .visual_wire import decode_jpeg
from .headless_display import LABELS

TITLES=dict(fluid='眼控流体',spectrum='三维声谱',npu='NPU 分类计算',spatial='空间感知')


class DemoDisplay:
    def __init__(self,font,decoder=decode_jpeg):
        self.font,self.decoder=font,decoder
        self.last_key,self.last_frame=None,None

    def render(self,state,latest):
        trace=state['data'].get('npu',{})
        pulse=bool(trace.get('event') and 0<=time.monotonic()-trace.get('event_monotonic',-float('inf'))<.35)
        remote=not state['menu'] and state['mode']!='npu'
        key=(state['session'],state['epoch'],state['menu'],state['stopped'],
             latest[:2] if remote and latest else None,trace.get('window_id'),
             trace.get('valid'),trace.get('event'),pulse,state['renderer_online'])
        if key==self.last_key:return self.last_frame,key
        if remote and latest:
            try:frame=self.decoder(latest[2])
            except ValueError:pass
            else:
                self.last_key,self.last_frame=key,frame
                return frame,key
        frame=np.empty((720,1280,3),np.uint8);frame[:]=BACKGROUND
        text=lambda s,x,y,size=28,color=INK:self.font.text(frame,str(s),x,y,size=size,color=color)
        if not state['menu'] and state['mode']!='npu' and latest:
            text('画面解码失败，等待下一帧',40,250,40)
        else:
            text('我们意念合一 / '+TITLES[state['mode']],35,22,40)
            if state['menu']:
                text('选择 Z20 展示模式',40,130,40)
                for i,mode in enumerate(MODES):
                    y=235+i*82
                    if mode==state['mode']:frame[y-8:y+55,30:1245]=LINE
                    text(TITLES[mode],60,y,40,color=ACCENT if mode==state['mode'] else INK)
                text('左：上一个    中：进入    右：下一个',45,630)
            elif state['mode']=='npu' and not state['renderer_online']:
                text('无线渲染连接中断',40,250,40)
            elif state['mode']=='npu':
                task=trace.get('task',('fatigue','emotion','sound')[state['sample_index']])
                for i,name in enumerate(('疲劳分类','情绪分类','声音分类')):
                    x=40+i*415;text(name,x,105,28,ACCENT if task==('fatigue','emotion','sound')[i] else MUTED)
                    if task==('fatigue','emotion','sound')[i]:frame[148:151,x:x+350]=ACCENT
                text('输入',40,177,28);text('Z20 分类计算',455,177,28);text('本次结果',875,177,28)
                source=trace.get('source','')
                origin='电脑麦克风 · 一秒录音' if source=='live:pc_microphone' else '导入音频文件' if source=='recorded:pc_wav' else '脑电特征记录回放' if 'LEMON' in source else '登记录音回放' if source.startswith('recorded:') else '等待数据输入'
                text(origin,40,227,20,MUTED)
                text('窗口 '+str(trace.get('window_id','等待采集'))[-30:],40,478,20,MUTED)
                features=trace.get('quantized_features',[])
                text('%d 项实际输入特征'%len(features),40,265,28)
                for i,value in enumerate(features[:180]):
                    x,y=40+(i%15)*23,320+(i//15)*12
                    level=(int(value)+128)/255.
                    frame[y:y+9,x:x+19]=np.asarray((80+150*level,65+115*level,60+55*level),np.uint8)
                event=trace.get('event');complete=event=='completed'
                for i,label in enumerate(('特征转为 INT8','全连接 / ReLU / 三输出','读取结果与软件核对')):
                    y=240+i*86
                    frame[y:y+2,455:800]=LINE
                    text(label,460,y+16,20,ACCENT if complete else MUTED)
                text('已完成' if complete else '计算中' if event=='submitted' else '等待输入',460,505,28,ACCENT)
                scores=trace.get('scores') or []
                labels=LABELS[task];valid=trace.get('valid') and trace.get('class_id') in (0,1,2)
                text(labels[trace['class_id']] if valid else '无有效分类' if complete else '等待输入',875,230,40,ACCENT)
                if scores:
                    low=min(scores);span=max(max(scores)-low,1e-6)
                    for i,(label,value) in enumerate(zip(labels,scores)):
                        y=320+i*65;text(label,875,y,20);text('%.3f'%value,1135,y,20)
                        frame[y+35:y+43,875:1235]=LINE
                        frame[y+35:y+43,875:875+int((float(value)-low)/span*360)]=ACCENT
                text('三类原始得分 · 不是概率',875,535,20,MUTED)
                frame[576:578,40:1240]=LINE
                timing=trace.get('timing') or {}
                if timing.get('npu_predict_seconds') is not None:
                    text('软件 %.3f ms    NPU %.3f ms    速度比 %.2f 倍'%(timing['software_seconds']*1000,timing['npu_predict_seconds']*1000,timing['speedup']),40,595,28)
                else:text('耗时对照：等待实板计算',40,595,28)
                match=trace.get('integer_reference_equal')
                text(('Z20 PL 硬件计算' if trace.get('backend')=='PL_z20_mlp' else '软件计算')+' · 整数核对：'+('一致' if match is True else '不一致' if match is False else '待核对'),40,640,20,MUTED)
                text('左 / 右：切换分类任务    中：返回    声音输入在电脑操作页',40,680,20,MUTED)
                text('疲劳候选模型' if task=='fatigue' else '冻结声音样本结果' if trace.get('frozen') else '',1000,640,20,MUTED)
            else:
                text('等待电脑渲染画面' if state['renderer_online'] else '无线渲染连接中断',40,250,40)
        self.last_key,self.last_frame=key,frame
        return frame,key
