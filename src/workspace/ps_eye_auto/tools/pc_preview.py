"""Local image/webcam UI. One worker owns camera and C inference."""
import argparse
import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog,messagebox,ttk
from pc_model import Detector,annotate,cv2,fit_input,load_image

class PreviewWorker:
    def __init__(self,detector,capture_factory=None):
        self.detector=detector
        self.capture_factory=capture_factory or (lambda index:cv2.VideoCapture(index,cv2.CAP_DSHOW))
        self.commands=queue.Queue()
        self.results=queue.Queue(maxsize=1)
        self.epoch=0
        self.closed=threading.Event()
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def request(self,kind,value=None):
        self.epoch+=1
        self.commands.put((self.epoch,kind,value))
        return self.epoch

    def publish(self,epoch,**data):
        if epoch!=self.epoch or self.closed.is_set():return
        try:self.results.get_nowait()
        except queue.Empty:pass
        self.results.put_nowait(dict(epoch=epoch,**data))

    def run(self):
        cap=None
        epoch=0
        try:
            while not self.closed.is_set():
                try:
                    command=self.commands.get(timeout=0.02 if cap is not None else 0.1)
                    while not self.commands.empty():command=self.commands.get_nowait()
                except queue.Empty:command=None
                if command:
                    epoch,kind,value=command
                    if cap is not None:cap.release();cap=None
                    if kind=='stop':self.publish(epoch,state='stopped');continue
                    try:
                        if kind=='image':
                            frame=load_image(value)
                            result=self.detector.detect(frame)
                            self.publish(epoch,state='image',frame=annotate(frame,result),result=result,source=Path(value).name)
                        elif kind=='camera':
                            cap=self.capture_factory(value)
                            if not cap.isOpened():raise RuntimeError('摄像头无法打开。检查 Windows 相机权限、设备编号和其他占用相机的软件。')
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT,720)
                    except Exception as exc:
                        if cap is not None:cap.release();cap=None
                        self.publish(epoch,state='error',message=str(exc))
                if cap is not None:
                    try:
                        ok,frame=cap.read()
                        if not ok:raise RuntimeError('摄像头没有返回图像，已停止检测。')
                        if epoch!=self.epoch:continue
                        frame=fit_input(frame)
                        result=self.detector.detect(frame)
                        self.publish(epoch,state='camera',frame=annotate(frame,result),result=result,source='电脑摄像头')
                    except Exception as exc:
                        cap.release();cap=None
                        self.publish(epoch,state='error',message=str(exc))
        finally:
            if cap is not None:cap.release()

    def close(self):
        self.closed.set()
        self.epoch+=1

class Preview:
    def __init__(self,root,initial=None):
        self.root=root
        root.title('Z15 人脸与双眼模型 · 电脑测试')
        root.geometry('1050x820');root.minsize(760,620)
        self.worker=PreviewWorker(Detector())
        self.current=None
        self.photo=None
        panel=ttk.Frame(root,padding=16);panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='人脸与双眼定位',font=('Microsoft YaHei UI',17)).pack(anchor='w')
        ttk.Label(panel,text='打开照片或启动电脑摄像头，查看模型是否把眼框放在正确位置。').pack(anchor='w',pady=(4,14))
        row=ttk.Frame(panel);row.pack(fill='x')
        ttk.Button(row,text='打开照片',command=self.choose_image).pack(side='left')
        ttk.Label(row,text='   摄像头编号').pack(side='left')
        self.camera=tk.StringVar(value='0')
        ttk.Spinbox(row,from_=0,to=9,textvariable=self.camera,width=3).pack(side='left',padx=6)
        ttk.Button(row,text='启动摄像头',command=self.start_camera).pack(side='left')
        ttk.Button(row,text='停止',command=self.stop).pack(side='left',padx=6)
        self.save=ttk.Button(row,text='保存当前标框图',command=self.save_image,state='disabled')
        self.save.pack(side='right')
        self.status=tk.StringVar(value='等待输入；摄像头尚未开启')
        ttk.Label(panel,textvariable=self.status,font=('Microsoft YaHei UI',12)).pack(anchor='w',pady=(16,4))
        self.details=tk.StringVar(value='黄色：人脸　绿色：左右眼分析区')
        ttk.Label(panel,textvariable=self.details).pack(anchor='w',pady=(0,10))
        self.canvas=tk.Canvas(panel,background='#172027',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda event:self.render())
        ttk.Label(panel,text='这里只测试人脸/双眼定位。显示耗时来自电脑；眼控校准和 ARM 速度需另行验证。').pack(anchor='w',pady=(12,0))
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(50,self.poll)
        if initial:root.after(100,lambda:self.open_image(initial))

    def clear(self,text):
        self.current=None;self.photo=None
        self.save.configure(state='disabled')
        self.status.set(text)
        self.details.set('黄色：人脸　绿色：左右眼分析区')
        self.canvas.delete('all')

    def open_image(self,path):
        self.clear('正在检测照片…')
        self.worker.request('image',str(path))

    def choose_image(self):
        path=filedialog.askopenfilename(title='选择本地照片',filetypes=[('图像','*.png *.jpg *.jpeg *.bmp'),('所有文件','*.*')])
        if path:self.open_image(path)

    def start_camera(self):
        try:
            index=int(self.camera.get())
            if not 0<=index<=9:raise ValueError()
        except ValueError:
            messagebox.showerror('摄像头编号','请输入 0–9 的整数。');return
        self.clear('正在打开摄像头…')
        self.worker.request('camera',index)

    def stop(self):
        self.clear('已清除画面，正在停止采集…')
        self.worker.request('stop')

    def poll(self):
        try:item=self.worker.results.get_nowait()
        except queue.Empty:item=None
        if item and item['epoch']==self.worker.epoch:
            if item['state']=='error':self.clear('检测失败：'+item['message'])
            elif item['state']=='stopped':self.clear('已停止；可打开照片或重新启动摄像头')
            else:
                self.current=item
                r=item['result']
                verdict='找到双眼' if r['valid'] else '未找到可靠双眼对'
                self.status.set(f"{verdict}  ·  PC 检测 {r['host_ms']:.1f} ms")
                self.details.set(f"{item['source']}  ·  {r['width']}×{r['height']}  ·  人脸候选 {r['faces']}  ·  黄色：人脸　绿色：眼区")
                self.save.configure(state='normal')
                self.render()
        self.root.after(40,self.poll)

    def render(self):
        if self.current is None:return
        frame=self.current['frame'];h,w=frame.shape[:2]
        cw,ch=self.canvas.winfo_width(),self.canvas.winfo_height()
        scale=min(cw/w,ch/h)
        if scale<=0:return
        sized=cv2.resize(frame,(max(1,int(w*scale)),max(1,int(h*scale))))
        ok,png=cv2.imencode('.png',sized)
        if not ok:return
        self.photo=tk.PhotoImage(data=png.tobytes(),format='png')
        self.canvas.delete('all')
        self.canvas.create_image(cw//2,ch//2,image=self.photo,anchor='center')

    def save_image(self):
        item=self.current
        if item is None:return
        path=filedialog.asksaveasfilename(title='保存标框图片',defaultextension='.png',filetypes=[('PNG','*.png')])
        if not path:return
        try:
            ok,png=cv2.imencode('.png',item['frame'])
            if not ok:raise RuntimeError('PNG 编码失败')
            Path(path).write_bytes(png.tobytes())
        except Exception as exc:messagebox.showerror('保存失败',str(exc))

    def close(self):
        self.worker.close()
        self.root.destroy()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--image',type=Path)
    p.add_argument('--output',type=Path,help='Headless image test; saves annotation and JSON')
    args=p.parse_args()
    if args.output:
        if not args.image:p.error('--output requires --image')
        frame=load_image(args.image);result=Detector().detect(frame)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        ok,png=cv2.imencode('.png',annotate(frame,result))
        if not ok:raise RuntimeError('PNG encoding failed')
        args.output.write_bytes(png.tobytes())
        args.output.with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2));return
    root=tk.Tk()
    try:Preview(root,args.image)
    except Exception as exc:
        messagebox.showerror('无法启动模型测试',str(exc));root.destroy();raise
    root.mainloop()
if __name__=='__main__':main()
