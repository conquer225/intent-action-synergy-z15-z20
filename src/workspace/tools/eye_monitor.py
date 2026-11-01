"""Z15 PL eye-control calibration console. Run: python tools/eye_monitor.py"""
import time
import tkinter as tk
from tkinter import ttk, messagebox
try:
    import serial
    from serial.tools import list_ports
except ImportError:
    raise SystemExit("请先运行：python -m pip install pyserial")
from eye_protocol import Decoder, roi_packet, WIDTH, HEIGHT


class Monitor:
    def __init__(self, root):
        self.root = root
        root.title("Z15 眼控 · OV5640 / P2")
        self.connection = None
        self.decoder = Decoder()
        self.photo = None
        self.gray = None
        self.drag_start = None
        self.snapshot_started = None
        self.last_status = 0
        self.last_seq = None
        self.port = tk.StringVar()
        self.status = tk.StringVar(value="连接 PL USB 串口，115200 / 8N1。上电后相机初始化约 5 秒。")
        self.detail = tk.StringVar(value="先取图，在画面中拖动框住单只眼睛，应用参数，再分别校准左、中、右。")
        bar = ttk.Frame(root, padding=8)
        bar.pack(fill="x")
        self.port_box = ttk.Combobox(bar, textvariable=self.port, width=18)
        self.port_box.pack(side="left")
        ttk.Button(bar, text="刷新", command=self.refresh).pack(side="left")
        ttk.Button(bar, text="连接", command=self.connect).pack(side="left")
        ttk.Button(bar, text="断开", command=self.disconnect).pack(side="left")
        ttk.Button(bar, text="取图（约 7 秒）", command=self.snapshot).pack(side="left", padx=10)
        self.canvas = tk.Canvas(root, width=640, height=480, bg="#20252d", highlightthickness=0)
        self.canvas.pack(padx=8)
        self.canvas.create_text(320,240,text="连接后点击取图",fill="white",font=("Microsoft YaHei",18),tags="placeholder")
        self.canvas.bind("<ButtonPress-1>", self.drag_begin)
        self.canvas.bind("<B1-Motion>", self.drag_move)
        self.canvas.bind("<ButtonRelease-1>", self.drag_end)
        controls = ttk.Frame(root, padding=8)
        controls.pack(fill="x")
        self.values = {}
        for label, initial in (("X",120),("Y",96),("宽",80),("高",40),("阈值",64)):
            ttk.Label(controls,text=label).pack(side="left")
            variable=tk.StringVar(value=str(initial))
            self.values[label]=variable
            ttk.Entry(controls,textvariable=variable,width=5).pack(side="left",padx=3)
        ttk.Button(controls,text="应用并清除校准",command=self.apply).pack(side="left",padx=8)
        calibration = ttk.Frame(root,padding=(8,0,8,8))
        calibration.pack(fill="x")
        for label,command in (("看左 → 校准左",b"l"),("看中 → 校准中",b"c"),("看右 → 校准右",b"r"),("清除校准",b"x")):
            ttk.Button(calibration,text=label,command=lambda cmd=command:self.calibrate(cmd)).pack(side="left",padx=2)
        ttk.Label(root,textvariable=self.status,wraplength=640).pack(anchor="w",padx=8,pady=4)
        ttk.Label(root,textvariable=self.detail,wraplength=640).pack(anchor="w",padx=8,pady=4)
        self.log=tk.Text(root,height=6,width=85,state="disabled")
        self.log.pack(fill="both",padx=8,pady=8)
        root.protocol("WM_DELETE_WINDOW",self.close)
        self.refresh()
        root.after(20,self.poll)

    def refresh(self):
        ports=[p.device for p in list_ports.comports()]
        self.port_box["values"]=ports
        if ports and not self.port.get(): self.port.set(ports[0])

    def note(self,text):
        self.log.configure(state="normal")
        self.log.insert("end",time.strftime("%H:%M:%S ")+text+"\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def connect(self):
        self.disconnect()
        try:
            self.connection=serial.Serial(self.port.get(),115200,timeout=0,write_timeout=1)
            self.decoder=Decoder()
            self.last_seq=None
            self.last_status=time.monotonic()
            self.note("已连接 "+self.port.get())
        except (serial.SerialException,ValueError) as exc:
            messagebox.showerror("串口连接失败",str(exc))

    def disconnect(self):
        if self.connection:
            self.connection.close()
        self.connection=None
        self.snapshot_started=None
        self.status.set("未连接")

    def send(self,data):
        if not self.connection:
            messagebox.showinfo("未连接","先选择并连接 PL USB 串口。")
            return False
        try:
            self.connection.write(data)
            return True
        except serial.SerialException as exc:
            self.note(str(exc));self.disconnect();return False

    def snapshot(self):
        if self.snapshot_started is not None:
            return
        if self.send(b"p"):
            self.snapshot_started=time.monotonic()
            self.status.set("正在取图；这段时间 FPGA 暂停产生眼控确认事件。")

    def calibrate(self,cmd):
        if self.snapshot_started is not None:
            messagebox.showinfo("正在取图","图像接收完成后再校准。")
            return
        if self.send(cmd):
            self.note("校准命令 "+cmd.decode()+"：保持头部不动，保持注视，等待 A0。每个方向需要连续 8 个有效帧。")

    def apply(self):
        try:
            vals=[int(v.get()) for v in self.values.values()]
            packet=roi_packet(*vals)
        except ValueError as exc:
            messagebox.showerror("参数错误",str(exc));return
        if self.send(packet):
            self.last_seq=None
            self.draw_roi()
            self.note("参数已发送，原校准失效。请按左、中、右重新校准。")

    def draw_roi(self):
        self.canvas.delete("roi")
        try: x,y,w,h,_=[int(v.get()) for v in self.values.values()]
        except ValueError:return
        self.canvas.create_rectangle(x*2,y*2,(x+w)*2,(y+h)*2,outline="#00ffff",width=2,tags="roi")

    def drag_begin(self,event):
        self.drag_start=(max(0,min(319,event.x//2)),max(0,min(239,event.y//2)))

    def drag_move(self,event):
        if self.drag_start is None:return
        x0,y0=self.drag_start
        x1=max(0,min(320,event.x//2));y1=max(0,min(240,event.y//2))
        for key,value in zip(("X","Y","宽","高"),(min(x0,x1),min(y0,y1),abs(x1-x0),abs(y1-y0))):
            self.values[key].set(str(value))
        self.draw_roi()

    def drag_end(self,event):
        self.drag_move(event);self.drag_start=None

    def handle(self,kind,value):
        if kind=="image":
            self.gray=value
            self.photo=tk.PhotoImage(data=b"P5\n320 240\n255\n"+value,format="PPM").zoom(2)
            self.canvas.delete("image");self.canvas.delete("placeholder")
            self.canvas.create_image(0,0,image=self.photo,anchor="nw",tags="image")
            self.canvas.tag_lower("image");self.draw_roi();self.snapshot_started=None
            self.note("图像已接收。框住单只眼睛的眼白和瞳孔，避开眉毛、黑色镜框。")
        elif kind=="status":
            self.last_status=time.monotonic()
            d=value
            self.status.set(f"方向 {d['direction']}　有效 {d['V']}　特征 {d['F']}　相机 {d['I']:04X} / 就绪 {d['R']}　断流 {d['S']}　故障 {d['!']}")
            self.detail.set(f"质心 X={d['X']}　暗像素={d['N']}　对比度={d['Q']}　校准掩码={d['C']:X}（完整为 7）　正在校准={d['A']}　校准冲突={d['K']}")
            if (self.last_seq is not None and d['E']!=self.last_seq
                    and d['D'] in ('L','R') and d['C']==7 and not d['K']):
                self.note(f"确认事件 #{d['E']}：{d['D']}。回中保持后可发下一次。")
            self.last_seq=d['E']
        else:self.note(value)

    def poll(self):
        if self.connection:
            try:
                data=self.connection.read(min(self.connection.in_waiting,16384))
                for kind,value in self.decoder.feed(data):self.handle(kind,value)
                now=time.monotonic()
                if self.snapshot_started is not None and now-self.snapshot_started>20:
                    self.note("取图超时：检查相机就绪和 P2 接线；复位板卡后重新连接。")
                    self.disconnect()
                elif self.snapshot_started is None and now-self.last_status>2:
                    self.status.set("串口无状态数据：检查 PL USB 串口、J24 跳线和 FPGA 是否已配置。")
            except (serial.SerialException,OSError) as exc:
                self.note(str(exc));self.disconnect()
        self.root.after(20,self.poll)

    def close(self):
        self.disconnect();self.root.destroy()


if __name__=="__main__":
    root=tk.Tk()
    Monitor(root)
    root.mainloop()
