"""Live three-point calibration window using the unchanged firmware C code."""
import json
import queue
import threading
import time
import tkinter as tk
from collections import deque
from datetime import datetime
from pathlib import Path
from tkinter import filedialog,messagebox,ttk
from pc_model import cv2,fit_input
from pc_gaze import GazeEngine,annotate_gaze,eye_diagnostic,calibration_diagnostic
from pc_preview import PreviewWorker,Preview

WORDS={0:'无效',1:'左',2:'中',3:'右'}

class GazeWorker(PreviewWorker):
    def __init__(self,engine,capture_factory=None):
        self.history=deque(maxlen=2000)
        self.history_id=0
        self.control_lock=threading.Lock()
        self.last_trace=0
        self.previous=None
        super().__init__(engine,capture_factory)

    def request(self,kind,value=None):
        with self.control_lock:
            return super().request(kind,value)

    def publish(self,epoch,**data):
        with self.control_lock:
            super().publish(epoch,history=list(self.history),**data)

    def record(self,kind,text,**data):
        self.history_id+=1
        self.history.append(dict(id=self.history_id,time=datetime.now().isoformat(timespec='milliseconds'),
                                 kind=kind,text=text,**data))

    def trace(self,result):
        s=result['gaze']
        signature=(s['cal_mask'],s['stage'],s['failed'],s['reason'])
        if signature!=self.previous:
            if s['stage']:text='校准：看'+WORDS[s['stage']]
            elif s['cal_mask']==7:text='校准完成'
            elif s['reason']==2:text='超出位置跟随范围，已暂停；校准保留'
            elif s['failed']:text=calibration_diagnostic(s)
            elif not s['pair']:text='未找到可靠双眼，等待恢复；校准进度保留'
            else:text='等待开始校准'
            self.record('state',text,gaze=s)
            self.previous=signature
        if s['commit']:
            self.record('event',f"触发 {s['direction_name']} · 第 {s['event_seq']} 次",
                        direction=s['direction_name'],event_seq=s['event_seq'])
        now=time.monotonic()
        if now-self.last_trace>=1 or s['commit'] or s['stage']:
            self.record('sample','诊断采样',gaze=s,host_ms=result['host_ms'],period_ms=result['period_ms'],
                        width=result['width'],height=result['height'],
                        localization={k:result.get(k) for k in ('face','left','right','valid')})
            self.last_trace=now

    def run(self):
        cap=None;epoch=0
        try:
            while not self.closed.is_set():
                try:command=self.commands.get(timeout=.01 if cap is not None else .1)
                except queue.Empty:command=None
                if command:
                    epoch,kind,value=command
                    if epoch!=self.epoch:continue
                    try:
                        if kind in ('camera','stop'):
                            if cap is not None:cap.release();cap=None
                            self.detector.reset();self.detector.last_sample=None
                            self.history.clear();self.previous=None;self.last_trace=0
                            if kind=='stop':
                                self.publish(epoch,state='stopped');continue
                            self.record('source',f'摄像头 {value}；电脑处理时间，不代表 ARM 速度')
                            cap=self.capture_factory(value)
                            if not cap.isOpened():raise RuntimeError('摄像头无法打开。检查设备编号、Windows 相机权限和其他占用相机的软件。')
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT,720)
                            cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
                        elif kind in ('calibrate','retry'):
                            if cap is None or not self.detector.calibrate(retry=kind=='retry'):
                                self.record('notice','无法开始：需要新鲜、稳定的双眼定位，且至少一眼暗部有效')
                                self.publish(epoch,state='notice',message=self.history[-1]['text'])
                            else:self.record('notice','重采失败点；保持原坐姿，跟随白点' if kind=='retry' else '开始三点校准；保持头部位置，跟随白点')
                        elif kind=='reset':
                            self.detector.reset();self.previous=None
                            self.record('notice',value or '已清除校准，请重新开始')
                            self.publish(epoch,state='notice',message=self.history[-1]['text'])
                    except Exception as exc:
                        if cap is not None:cap.release();cap=None
                        self.detector.reset()
                        self.record('error',str(exc));self.publish(epoch,state='error',message=str(exc))
                if cap is None:continue
                try:
                    ok,frame=cap.read()
                    sampled=time.monotonic()
                    if epoch!=self.epoch:continue
                    if not ok:raise RuntimeError('摄像头没有返回图像，已停止。检查连接后重新启动。')
                    frame=fit_input(frame)
                    result=self.detector.process(frame,sampled)
                    if epoch!=self.epoch:continue
                    self.trace(result)
                    self.publish(epoch,state='camera',frame=annotate_gaze(frame,result),raw=frame,result=result)
                except Exception as exc:
                    cap.release();cap=None;self.detector.reset()
                    self.record('error',str(exc));self.publish(epoch,state='error',message=str(exc))
        finally:
            if cap is not None:cap.release()
            self.detector.close()


class GazePreview:
    # Reuse the old viewer's image rendering; calibration overlay remains Tk geometry.
    render_image=Preview.render

    def __init__(self,root,worker=None):
        self.root=root
        root.title('Z15 眼动测试 r7 · 人脸锚定与眼动保留')
        root.geometry('1120x840');root.minsize(900,680)
        self.current=None;self.photo=None;self.history=[];self.last_sample=0
        self.running=False;self.pending=False;self.closed=False;self.session=0
        self.geometry_key=None;self.gaze=None;self.poll_id=None
        self.worker=worker or GazeWorker(GazeEngine())
        self.style=ttk.Style(root)
        self.style.configure('Direction.TLabel',font=('Microsoft YaHei UI',22),anchor='center',padding=10)
        self.style.configure('Selected.Direction.TLabel',background='#145b48',foreground='white')
        panel=ttk.Frame(root,padding=16);panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='三点眼动测试',font=('Microsoft YaHei UI',18)).pack(anchor='w')
        ttk.Label(panel,text='眼框会跟随小幅位置变化。校准时尽量坐稳，用眼睛跟随白点。').pack(anchor='w',pady=(4,12))
        row=ttk.Frame(panel);row.pack(fill='x')
        ttk.Label(row,text='摄像头').pack(side='left')
        self.camera=tk.StringVar(value='0')
        ttk.Spinbox(row,from_=0,to=9,textvariable=self.camera,width=3).pack(side='left',padx=(6,12))
        ttk.Button(row,text='启动摄像头',command=self.start_camera).pack(side='left')
        ttk.Button(row,text='停止',command=self.stop).pack(side='left',padx=6)
        self.calibrate_button=ttk.Button(row,text='开始三点校准',command=self.calibrate,state='disabled')
        self.calibrate_button.pack(side='left',padx=(14,6))
        ttk.Button(row,text='清除校准',command=self.reset).pack(side='left')
        ttk.Button(row,text='全屏 / F11',command=self.fullscreen).pack(side='right')
        self.status=tk.StringVar(value='请启动摄像头，等待找到双眼。')
        tk.Label(panel,textvariable=self.status,font=('Microsoft YaHei UI',12),height=2,
                 anchor='w',justify='left',wraplength=1000).pack(fill='x',pady=(14,4))
        self.details=tk.StringVar(value='未采集图像；当前没有方向结果。')
        ttk.Label(panel,textvariable=self.details).pack(anchor='w',pady=(0,10))
        self.eye_details=tk.StringVar(value='等待图像；将分别显示两眼特征和拒绝原因。')
        # Reserve both lines: changing diagnosis text must not move the target
        # canvas and trigger the window-resize calibration reset.
        tk.Label(panel,textvariable=self.eye_details,height=2,anchor='w',justify='left').pack(fill='x',pady=(0,8))
        cells=ttk.Frame(panel);cells.pack(fill='x',pady=(0,8))
        self.cells={}
        for i,text in ((1,'左  LEFT'),(2,'中  CENTER'),(3,'右  RIGHT')):
            cells.columnconfigure(i,weight=1)
            label=ttk.Label(cells,text=text,style='Direction.TLabel')
            label.grid(row=0,column=i,sticky='ew',padx=2);self.cells[i]=label
        self.canvas=tk.Canvas(panel,background='#172027',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',self.resized)
        self.progress=ttk.Progressbar(panel,maximum=100)
        self.progress.pack(fill='x',pady=(8,4))
        self.progress_text=tk.StringVar(value='校准成功后，看左或右停留 750 ms；回中 350 ms 后可再次触发。')
        ttk.Label(panel,textvariable=self.progress_text).pack(anchor='w')
        footer=ttk.Frame(panel);footer.pack(fill='x',pady=(10,0))
        self.event_text=tk.StringVar(value='本次尚无触发事件')
        ttk.Label(footer,textvariable=self.event_text,font=('Microsoft YaHei UI',11)).pack(side='left')
        self.export_button=ttk.Button(footer,text='导出诊断记录',command=self.export,state='disabled')
        self.export_button.pack(side='right')
        self.snapshot_button=ttk.Button(footer,text='保存原图与诊断',command=self.save_diagnostic,state='disabled')
        self.snapshot_button.pack(side='right',padx=8)
        ttk.Label(panel,text='漏检时保留校准进度。绿框：暗部有效；红框：本帧无效。先选好窗口大小，再校准；Esc 退出全屏。').pack(anchor='w',pady=(8,0))
        root.bind('<F11>',lambda e:self.fullscreen())
        root.bind('<Escape>',lambda e:self.leave_fullscreen())
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.poll_id=root.after(40,self.poll)
        self.render()

    def clear(self,text):
        self.current=None;self.photo=None;self.gaze=None
        self.status.set(text);self.details.set('当前方向：无效')
        self.eye_details.set('等待新鲜图像。');self.snapshot_button.configure(state='disabled')
        self.calibrate_button.configure(state='disabled');self.progress['value']=0
        self.progress_text.set('等待有效图像与校准。')
        for label in self.cells.values():label.configure(style='Direction.TLabel')
        self.canvas.delete('all');self.render()

    def start_camera(self):
        try:
            index=int(self.camera.get())
            if not 0<=index<=9:raise ValueError()
        except ValueError:
            messagebox.showerror('摄像头编号','请输入 0–9 的整数。');return
        self.clear('正在打开摄像头…')
        self.history=[];self.event_text.set('本次尚无触发事件');self.export_button.configure(state='disabled')
        self.running=True;self.pending=True;self.session+=1
        self.worker.request('camera',index)

    def stop(self):
        self.running=False;self.pending=False
        self.clear('已停止。重新启动摄像头后需要校准。')
        self.worker.request('stop')

    def calibrate(self):
        if not self.running or not self.gaze or not self.gaze['can_calibrate']:return
        if time.monotonic()-self.last_sample>1:return
        retry=bool(self.gaze['failed'])
        self.clear('正在重采失败点，请保持原坐姿…' if retry else '正在开始校准，请保持头部位置…');self.pending=True
        self.worker.request('retry' if retry else 'calibrate')

    def reset(self,reason=None):
        self.clear(reason or '已清除校准，等待双眼稳定后重新开始。')
        if self.running:
            self.pending=True;self.worker.request('reset',reason)

    def fullscreen(self):
        self.root.attributes('-fullscreen',not bool(self.root.attributes('-fullscreen')))

    def leave_fullscreen(self):
        if self.root.attributes('-fullscreen'):self.root.attributes('-fullscreen',False)

    def resized(self,event):
        key=(event.width,event.height)
        if self.geometry_key is not None and key!=self.geometry_key and self.running:
            self.reset('窗口尺寸已改变，请重新做三点校准。')
        self.geometry_key=key;self.render()

    def apply_result(self,item):
        r=item['result'];s=r['gaze']
        self.current=item;self.gaze=s;self.last_sample=r['sampled'];self.pending=False
        stage=s['stage'];direction=s['direction'] if s['valid'] else 0
        if stage:
            message=f'正在校准：看{WORDS[stage]}侧白点。' if stage!=2 else '正在校准：看中间白点。'
            if s['paused']&16:message+=' 超出跟随范围或双眼位置不一致，进度保留；靠近原坐姿继续。'
            elif s['paused']&8:message+=' 图像处理过慢，暂停采样；进度已保留。'
            elif s['paused']&4:message+=' 双眼定位暂失，恢复后自动继续，进度已保留。'
            elif s['paused']==3:message+=' 两眼本帧无效，暂停采样；进度已保留。'
            elif s['paused']&3:message+=' 单眼暂失：有效眼继续采样，另一眼恢复后补齐。'
        elif s['reason']==2:message='超出跟随范围或双眼位置不一致，校准保留；靠近原坐姿或清除后重做。'
        elif s['reason']==3:message='采样间隔或检测超过 1 秒，本次方向无效。'
        elif s['failed']:message=calibration_diagnostic(s)
        elif s['cal_mask']==7 and (not s['pair'] or not s['left_valid'] or not s['right_valid']):
            message='校准已保留，当前方向暂停；双眼恢复后自动继续。'
        elif not s['pair']:message='未找到可靠双眼。请正对摄像头，调整光线与距离。'
        elif s['stable']<2:message='已找到眼框，等待连续定位稳定。'
        elif s['cal_mask']!=7:message='可以开始三点校准；两眼会分别积累有效样本。' if s['can_calibrate'] else '眼部特征未通过，可查看下方原因或保存原图诊断。'
        elif direction:message=f'当前方向：{WORDS[direction]}  {s["direction_name"]}'
        elif s['cal_mask']==7:message='校准已保留：'+s['tracking_name']+'；当前不累计动作。'
        else:message='当前方向：无效。双眼判断不一致，或特征远离校准值。'
        self.status.set(message)
        def nx(eye):return str(s[eye+'_nx']) if s[eye+'_valid'] else '无效'
        fused=f"  ·  归一化 {s['gaze_raw']} → {s['gaze_filtered']}" if s['cal_mask']==7 and s['filter_count'] else ''
        self.details.set(f"眼内位置 {nx('left')} / {nx('right')}（0–256）{fused}  ·  {r['width']}×{r['height']}  ·  PC 检测 {r['host_ms']:.0f} ms / 间隔 {r['period_ms']} ms")
        def refs(eye):
            if not (s['failed'] or s['cal_mask']):return ''
            prefix='cal_l_' if eye=='left' else 'cal_r_'
            values='/'.join(str(s[prefix+p]) for p in ('left','center','right'))
            mad='/'.join(str(s[prefix+'mad_'+p]) for p in ('left','center','right'))
            return f' · 参考 {values} · 抖动 {mad}'
        self.eye_details.set('画面左眼：'+eye_diagnostic(s,'left')+refs('left')+'\n画面右眼：'+eye_diagnostic(s,'right')+refs('right'))
        self.snapshot_button.configure(state='normal' if 'raw' in item else 'disabled')
        self.calibrate_button.configure(state='normal' if s['can_calibrate'] and not stage else 'disabled',
                                        text='重采失败点' if s['failed'] else '重新校准' if s['cal_mask']==7 else '开始三点校准')
        for i,label in self.cells.items():
            label.configure(style='Selected.Direction.TLabel' if i==(stage or direction) else 'Direction.TLabel')
        if stage:
            required=s['cal_samples_required']
            if s['settle_ms']<s['cal_settle_required']:
                self.progress['value']=s['settle_ms']/s['cal_settle_required']*100
                self.progress_text.set(f'看{WORDS[stage]}：等待眼睛稳定；漏检只暂停，恢复后继续。')
            else:
                self.progress['value']=(s['cal_left_count']+s['cal_right_count'])/(2*required)*100
                waiting=any(s['cal_'+e+'_count']==required and not s['cal_'+e+'_ready'] for e in ('left','right'))
                hint='抖动偏大，正在更新最近样本；继续看白点。' if waiting else '白点移动后再换方向。'
                self.progress_text.set(f"看{WORDS[stage]}：左眼 {s['cal_left_count']}/{required}，右眼 {s['cal_right_count']}/{required}；核心跨度 {s['cal_left_core_span']}/{s['cal_right_core_span']}；{hint}")
        elif direction:
            goal=350 if direction==2 else 750
            self.progress['value']=min(100,s['dwell_ms']/goal*100)
            self.progress_text.set('已触发，请回看中间后再操作。' if not s['armed'] and direction!=2 else
                                   f"{'回中准备' if direction==2 else '侧向确认'}：{s['dwell_ms']} / {goal} ms")
        else:self.progress['value']=0;self.progress_text.set('无有效方向，停止累计停留时间。')
        self.render()

    def poll(self):
        if self.closed:return
        try:item=self.worker.results.get_nowait()
        except queue.Empty:item=None
        if item and item['epoch']==self.worker.epoch:
            # History includes commits even when their video frame was replaced.
            if item.get('history'):
                self.history=item['history'];self.export_button.configure(state='normal')
                events=[e for e in self.history if e['kind']=='event']
                if events:self.event_text.set('最近事件：'+events[-1]['text']+'（历史记录）')
            if item['state']=='camera':
                if time.monotonic()-item['result']['sampled']<=1:self.apply_result(item)
                else:self.clear('图像处理超过 1 秒，方向已清除。')
            elif item['state']=='error':
                self.running=False;self.pending=False;self.clear('采集失败：'+item['message'])
            elif item['state']=='notice':self.clear(item['message'])
            elif item['state']=='stopped':self.clear('已停止。重新启动摄像头后需要校准。')
        if self.current is not None and time.monotonic()-self.last_sample>1:
            self.clear('超过 1 秒没有新鲜图像，方向已清除；等待摄像头恢复。')
        self.poll_id=self.root.after(40,self.poll)

    def render(self):
        if self.current is not None:self.render_image()
        else:
            self.canvas.delete('all')
            self.canvas.create_text(max(1,self.canvas.winfo_width())//2,max(1,self.canvas.winfo_height())//2,
                                    text='摄像头画面',fill='#c7d5da',font=('Microsoft YaHei UI',16))
        if self.gaze and self.gaze['stage']:
            stage=self.gaze['stage'];w=self.canvas.winfo_width();h=self.canvas.winfo_height()
            side=self.gaze['target_side_percent']/100
            x=w*({1:side,2:.5,3:1-side}[stage]);y=h*self.gaze['target_y_percent']/100
            self.canvas.create_oval(x-14,y-14,x+14,y+14,fill='white',outline='#172027',width=3,tags='target')
            self.canvas.create_text(x,y+34,text='看'+WORDS[stage],fill='white',font=('Microsoft YaHei UI',14),tags='target')

    def export(self):
        history=list(self.history)
        if not history:return
        path=filedialog.asksaveasfilename(title='保存诊断记录（不含照片）',defaultextension='.json',filetypes=[('JSON','*.json')])
        if not path:return
        try:
            payload=dict(format='z15-pc-gaze-v1',version='r7',source='PC camera',arm_timing=False,
                         exported=datetime.now().isoformat(),history_limit=2000,records=history)
            Path(path).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception as exc:messagebox.showerror('导出失败',str(exc))

    def save_diagnostic(self):
        item=self.current
        if item is None or 'raw' not in item:return
        # Hold the exact chosen immutable frame while the file dialog runs.
        path=filedialog.asksaveasfilename(title='保存相机原图及同名诊断 JSON',defaultextension='.png',filetypes=[('PNG','*.png')])
        if not path:return
        try:
            ok,png=cv2.imencode('.png',item['raw'])
            if not ok:raise RuntimeError('PNG 编码失败')
            target=Path(path);target.write_bytes(png.tobytes())
            target.with_suffix('.json').write_text(json.dumps(dict(version='r7',source='PC camera',
                result=item['result'],note='Original BGR image, no overlays. PC timing is not ARM timing.'),
                ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception as exc:messagebox.showerror('保存失败',str(exc))

    def close(self):
        self.closed=True
        if self.poll_id:self.root.after_cancel(self.poll_id)
        self.worker.close();self.root.destroy()

def main():
    root=tk.Tk()
    try:GazePreview(root)
    except Exception as exc:
        messagebox.showerror('无法启动眼动测试',str(exc));root.destroy();raise
    root.mainloop()
if __name__=='__main__':main()
