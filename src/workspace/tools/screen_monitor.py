"""Dual-eye setup wizard for Z15 screen-region gaze firmware v2."""
import time
from datetime import datetime, timezone
import tkinter as tk
from tkinter import ttk, messagebox
import serial
from serial.tools import list_ports
from screen_protocol import Decoder, eye_packet
from screen_inspector import SnapshotInspector

APP_VERSION = "2026.09.25-r2"
ACK_TIMEOUT = 3


def boxes_overlap(a, b):
    return (a[0] < b[0]+b[2] and b[0] < a[0]+a[2]
            and a[1] < b[1]+b[3] and b[1] < a[1]+a[3])


def packet_description(packet):
    return (f"眼 {packet[1]+1} X={int.from_bytes(packet[2:4], 'big')} "
            f"Y={int.from_bytes(packet[4:6], 'big')} 宽={packet[6]} 高={packet[7]} "
            f"暗={packet[8]} 亮={packet[9]}")

REASONS = {0: "双眼方向一致", 1: "等待摄像头初始化", 2: "双眼特征不足：检查眼框、对焦和阈值",
           3: "位置改变：请回到校准时的坐姿", 4: "方向边界或双眼不一致", 5: "跟随 HDMI 白点，头部保持不动",
           6: "校准失败：三个方向特征过近或等待超时", 7: "取图期间暂停输出", 8: "先设置双眼，再开始屏幕校准", 9: "相机帧中断"}


class ScreenMonitor:
    def __init__(self, root):
        self.root = root
        root.title(f"Z15 屏幕三分区眼控 · 参数诊断版 {APP_VERSION}")
        self.connection = None
        self.decoder = Decoder()
        self.photo = None
        self.gray = None
        self.image_received_at = None
        self.redraw_job = None
        self.drag = None
        self.snapshot_time = None
        self.pending = []
        self.update_stage = ""
        self.parking_candidates = []
        self.sent_settings = []
        self.ack_deadline = 0
        self.applied = False
        self.last_status = 0
        self.last_seq = None
        self.last_mode = None
        self.telemetry = None
        self.port = tk.StringVar()
        self.slot = tk.IntVar(value=0)
        self.message = tk.StringVar(value="1. 连接 PL 串口并取图；2. 分别框住两只眼；3. 应用参数后，去看 HDMI 上的白点。")
        self.state = tk.StringVar(value="未连接")
        self.detail = tk.StringVar(value="识别在 FPGA 内运行，电脑只用于设置和查看结果。")
        self.settings = [[tk.StringVar(value=str(v)) for v in vals]
                         for vals in ((224, 200, 64, 32, 70, 140), (352, 200, 64, 32, 70, 140))]
        outer = ttk.Frame(root, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="把目光留在 HDMI 屏幕", font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        ttk.Label(outer, textvariable=self.message, wraplength=920).pack(anchor="w", pady=(4, 12))
        connect = ttk.Frame(outer)
        connect.pack(fill="x", pady=(0, 10))
        self.ports = ttk.Combobox(connect, textvariable=self.port, width=14, state="readonly")
        self.ports.pack(side="left")
        for text, action in (("刷新", self.refresh), ("连接", self.connect), ("断开", self.disconnect), ("取图（约 7 秒）", self.snapshot)):
            ttk.Button(connect, text=text, command=action).pack(side="left", padx=4)
        self.inspect_button = ttk.Button(connect, text="检查灰度 / 保存原图", command=self.inspect_snapshot, state="disabled")
        self.inspect_button.pack(side="left", padx=4)
        middle = ttk.Frame(outer)
        middle.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(middle, width=640, height=480, bg="#101b2b", highlightthickness=0)
        self.canvas.pack(side="left", anchor="n")
        self.canvas.create_text(320, 225, text="连接后取图，分别框住画面中的两只眼睛", fill="white", font=("Microsoft YaHei UI", 13), tags="empty")
        self.canvas.create_text(320, 258, text="快照放大到 640 × 480；不是连续视频", fill="#b8c8da", tags="empty")
        side = ttk.Frame(middle, padding=(16, 0, 0, 0))
        side.pack(side="left", fill="both", expand=True)
        for slot in (0, 1):
            ttk.Radiobutton(side, text=f"框选眼 {slot+1}（按画面从左到右）", variable=self.slot, value=slot).pack(anchor="w", pady=(0 if slot==0 else 12, 6))
            form = ttk.Frame(side)
            form.pack(fill="x")
            for index, name in enumerate(("X", "Y", "宽", "高", "暗阈值", "亮阈值")):
                ttk.Label(form, text=name).grid(row=index//2, column=(index%2)*2, sticky="w", padx=(0, 4), pady=3)
                ttk.Entry(form, textvariable=self.settings[slot][index], width=5).grid(row=index//2, column=(index%2)*2+1, padx=(0, 8))
        ttk.Label(side, text="眼框包含眼白和虹膜，避开眉毛。\n暗阈值区分虹膜，亮阈值选择眼白。\n每只眼的横向开口至少约 24 像素。", wraplength=270).pack(anchor="w", pady=12)
        ttk.Button(side, text="应用双眼参数", command=self.apply).pack(fill="x", pady=3)
        self.overlay = tk.BooleanVar(value=False)
        ttk.Checkbutton(side, text="阈值预览：红色暗区 / 蓝色亮区", variable=self.overlay, command=self.show_image).pack(anchor="w", pady=4)
        self.start_button = ttk.Button(side, text="开始 HDMI 三点校准", command=self.calibrate, state="disabled")
        self.start_button.pack(fill="x", pady=3)
        ttk.Button(side, text="返回预览 / 重新设置", command=self.preview).pack(fill="x", pady=3)
        ttk.Label(side, text="校准时只看 HDMI 白点：\n左 → 中 → 右，自动切换。\n不要跟随白点转头。", wraplength=260).pack(anchor="w", pady=12)
        ttk.Label(outer, textvariable=self.state, font=("Microsoft YaHei UI", 12, "bold"), wraplength=940).pack(anchor="w", pady=(12, 3))
        ttk.Label(outer, textvariable=self.detail, wraplength=940).pack(anchor="w")
        self.log = tk.Text(outer, height=5, width=105, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, pady=(8, 0))
        ttk.Button(outer, text="复制诊断日志", command=self.copy_log).pack(anchor="e")
        self.canvas.bind("<ButtonPress-1>", self.drag_begin)
        self.canvas.bind("<B1-Motion>", self.drag_move)
        self.canvas.bind("<ButtonRelease-1>", self.drag_end)
        for row in self.settings:
            for value in row:
                value.trace_add("write", self.invalidate)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self.note(f"电脑工具 {APP_VERSION}；参数诊断版。")
        root.after(20, self.poll)

    def copy_log(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log.get("1.0", "end-1c"))
        self.message.set("诊断日志已复制，可以粘贴发送。")

    def note(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S ") + text + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 300:
            self.log.delete("1.0", "100.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def invalidate(self, *_):
        self.applied = False
        self.start_button.configure(state="disabled")
        if self.redraw_job is None:
            self.redraw_job = self.root.after_idle(self.redraw)

    def redraw(self):
        self.redraw_job = None
        self.show_image()

    def can_calibrate(self):
        d = self.telemetry
        return (self.applied and not self.pending and self.snapshot_time is None and d
                and d["F"] == 3 and d["R"] and not d["S"] and d["M"] not in (1, 2, 3)
                and time.monotonic() - self.last_status < 2)

    def refresh(self):
        values = [p.device for p in list_ports.comports()]
        self.ports["values"] = values
        if values and self.port.get() not in values:
            self.port.set(values[0])

    def connect(self):
        self.disconnect()
        try:
            self.connection = serial.Serial(self.port.get(), 115200, timeout=0, write_timeout=1)
            self.decoder = Decoder()
            self.last_status = time.monotonic()
            self.last_seq = None
            self.last_mode = None
            self.note("已连接 " + self.port.get() + "；等待新版 SCR 状态。")
        except (serial.SerialException, ValueError) as exc:
            messagebox.showerror("连接失败", str(exc))

    def disconnect(self):
        if self.pending:
            self.note("连接中断：取消参数更新；板上可能只更新了部分眼框，重连后须重新应用。")
        if self.connection:
            self.connection.close()
        self.connection = None
        self.pending = []
        self.update_stage = ""
        self.parking_candidates = []
        self.snapshot_time = None
        self.telemetry = None
        self.invalidate()
        self.state.set("未连接")

    def send(self, data):
        if not self.connection:
            self.message.set("请先选择并连接 PL UART 的 COM 口。")
            return False
        try:
            self.connection.write(data)
            return True
        except (serial.SerialException, OSError) as exc:
            self.note(str(exc))
            self.disconnect()
            self.message.set("串口发送失败，连接已断开；参数未确认。请重新连接后应用。")
            return False

    def snapshot(self):
        if self.snapshot_time is not None or self.pending:
            return
        if self.telemetry and self.telemetry["M"] in (1, 2, 3):
            self.message.set("校准期间请看 HDMI 白点；要取图请先返回预览。")
            return
        if self.send(b"p"):
            self.snapshot_time = time.monotonic()
            self.message.set("正在接收快照，约 7 秒；眼控输出暂时停用。")

    def apply(self):
        if self.snapshot_time is not None or self.pending:
            self.message.set("请等待取图或参数确认完成。")
            return
        try:
            boxes = [[int(v.get()) for v in row] for row in self.settings]
            packets = [eye_packet(i, *box) for i, box in enumerate(boxes)]
            a, b = boxes
            if boxes_overlap(a, b):
                raise ValueError("两个眼框重叠，请分别圈住画面中的两只眼睛。")
        except ValueError as exc:
            self.message.set(str(exc))
            return
        self.invalidate()
        self.pending = packets
        self.sent_settings = boxes
        self.update_stage = "normal"
        self.parking_candidates = []
        if self.send_pending():
            self.last_seq = None
            self.message.set("正在等待 FPGA 确认双眼参数……")
            self.draw_boxes()

    def send_pending(self):
        packet = self.pending[0]
        if not self.send(packet):
            self.pending = []
            self.update_stage = ""
            return False
        self.ack_deadline = time.monotonic()+ACK_TIMEOUT
        label = {"normal": "设置", "parking": "临时挪框", "final": "恢复目标眼框"}[self.update_stage]
        self.note(f"发送 [{label}] {packet_description(packet)}；等待 RCFG 回执。")
        return True

    def try_parking(self):
        if not self.parking_candidates:
            self.fail_update()
            return
        # A legal old ROI cannot cover all four distant corners. Exclude both
        # final ROIs so eye 1 can move here before restoring eye 2 then eye 1.
        temporary = self.parking_candidates.pop(0)
        self.update_stage = "parking"
        self.pending = [eye_packet(0, *temporary),
                        eye_packet(1, *self.sent_settings[1]),
                        eye_packet(0, *self.sent_settings[0])]
        self.message.set("正在尝试自动挪框；HDMI 眼框可能暂移到角落，请等待最终确认。")
        self.send_pending()

    def fail_update(self):
        self.pending = []
        self.update_stage = ""
        self.parking_candidates = []
        self.invalidate()
        text = "双眼参数未全部确认；板上可能保留旧框、部分新框或临时框。请复制诊断日志。"
        self.message.set(text)
        self.note(text)

    def check_ack_timeout(self, now):
        if not self.pending or now <= self.ack_deadline:
            return
        self.note(f"超时：{packet_description(self.pending[0])} 未收到匹配 RCFG。")
        if self.update_stage == "normal":
            self.note("尝试排除新框与板上旧框冲突；超时本身不能确定故障原因。")
            self.parking_candidates = [
                [x, y, 24, 12, 70, 140] for x, y in ((0, 0), (616, 0), (0, 468), (616, 468))
                if not any(boxes_overlap((x, y, 24, 12), box) for box in self.sent_settings)]
            self.try_parking()
        elif self.update_stage == "parking":
            self.try_parking()
        else:
            self.fail_update()

    def inspect_snapshot(self):
        if self.gray is None:
            self.message.set("请先取图，再检查原始灰度。")
            return None
        metadata = {"image_received_utc": self.image_received_at,
                    "settings_at_inspection": [[v.get() for v in row] for row in self.settings],
                    "settings_acknowledged_at_inspection": self.applied,
                    "note": "Settings describe the inspection time, not the capture time."}
        return SnapshotInspector(self.root, self.gray, metadata)

    def calibrate(self):
        if not self.applied or self.pending or self.snapshot_time is not None:
            self.message.set("请先应用双眼参数并等待确认。")
            return
        if not self.can_calibrate():
            self.message.set("双眼必须都有效、相机持续出帧，才能开始校准。请检查眼框和阈值。")
            return
        if self.send(b"a"):
            self.last_seq = None
            self.start_button.configure(state="disabled")
            self.message.set("现在看 HDMI 屏幕上的白点。头保持正对屏幕，依次看左、中、右；无需再点电脑。")

    def preview(self):
        if self.pending:
            self.message.set("请等待参数更新完成，再返回预览。")
            return
        if self.send(b"v"):
            self.last_seq = None
            self.message.set("已请求返回 HDMI 摄像头预览。重新校准前可以取图、调整眼框。")

    def draw_boxes(self):
        self.canvas.delete("box")
        for slot, row in enumerate(self.settings):
            try:
                x, y, w, h = [int(v.get()) for v in row[:4]]
            except ValueError:
                continue
            color = "#24e0b0" if slot==0 else "#ffd46a"
            self.canvas.create_rectangle(x, y, x+w, y+h, outline=color, width=2, tags="box")
            self.canvas.create_text(x+3, y-4, anchor="sw", text=f"眼 {slot+1}", fill=color, tags="box")

    def show_image(self):
        if self.gray is None:
            return
        if self.overlay.get():
            pixels = bytearray()
            try:
                boxes = [[int(v.get()) for v in row] for row in self.settings]
            except ValueError:
                return
            for i, gray in enumerate(self.gray):
                x, y = (i%320)*2, (i//320)*2
                color = (gray, gray, gray)
                for bx, by, w, h, dark, bright in boxes:
                    if bx<=x<bx+w and by<=y<by+h:
                        if gray<dark:
                            color = (255, 70, 70)
                        elif gray>=bright:
                            color = (65, 170, 255)
                pixels.extend(color)
            data = b"P6\n320 240\n255\n"+pixels
        else:
            data = b"P5\n320 240\n255\n"+self.gray
        self.photo = tk.PhotoImage(data=data, format="PPM").zoom(2)
        self.canvas.delete("image")
        self.canvas.delete("empty")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw", tags="image")
        self.canvas.tag_lower("image")
        self.draw_boxes()

    def drag_begin(self, event):
        if self.gray is not None:
            self.drag = (max(0, min(639, event.x)), max(0, min(479, event.y)))

    def drag_move(self, event):
        if self.drag is None:
            return
        x0, y0 = self.drag
        x1, y1 = max(0, min(640, event.x)), max(0, min(480, event.y))
        for value, number in zip(self.settings[self.slot.get()], (min(x0,x1), min(y0,y1), abs(x1-x0), abs(y1-y0))):
            value.set(str(number))
        self.draw_boxes()

    def drag_end(self, event):
        self.drag_move(event)
        self.drag = None

    def handle(self, kind, value):
        if kind=="image":
            self.gray = value
            self.image_received_at = datetime.now(timezone.utc).isoformat()
            self.inspect_button.configure(state="normal")
            self.show_image()
            self.snapshot_time = None
            self.message.set("选择眼 1 后拖框，再选择眼 2 拖框；应用双眼参数。框内须能清楚分辨虹膜和眼白。")
        elif kind=="ack":
            if self.pending and value==self.pending[0][1:10]:
                self.note("收到匹配 RCFG："+packet_description(self.pending[0]))
                if self.update_stage == "parking":
                    self.update_stage = "final"
                    self.parking_candidates = []
                self.pending.pop(0)
                if self.pending:
                    self.send_pending()
                else:
                    self.update_stage = ""
                    if [[v.get() for v in row] for row in self.settings] != [[str(v) for v in row] for row in self.sent_settings]:
                        self.invalidate()
                        self.message.set("确认期间参数有改动，请再次应用双眼参数。")
                        self.note("板上已确认发送时的参数，但输入框有改动；当前参数尚未应用。")
                        return
                    self.applied = True
                    self.start_button.configure(state="normal" if self.can_calibrate() else "disabled")
                    self.message.set("FPGA 已确认两个眼框。双眼有效后，点击开始校准，再看 HDMI 白点。")
                    self.note("双眼参数已确认。")
            else:
                self.note("忽略非当前参数的 RCFG 回执："+value.hex(" "))
        elif kind=="status":
            d = value
            if not d["R"] or (d["M"] == 0 and self.last_mode not in (None, 0)):
                self.invalidate()
            self.telemetry = d
            self.last_status = time.monotonic()
            labels = {"I":"无效", "L":"左", "C":"中", "R":"右"}
            stage = {0:"设置", 1:"校准左", 2:"校准中", 3:"校准右", 4:"运行", 5:"校准失败"}[d["M"]]
            self.state.set(f"{stage}　识别：{labels[d['direction']]}　眼 1：{'有效' if d['F']&1 else '无效'}　眼 2：{'有效' if d['F']&2 else '无效'}")
            self.detail.set(f"{REASONS.get(d['H'],'等待状态')}　采样 {d['P']}/16　相机 {d['I']:04X} / 就绪 {d['R']} / 故障 {d['!']}　双眼特征 {d['X']}, {d['Y']}")
            if d["M"] != self.last_mode:
                self.note("阶段："+stage)
                if d["M"]==4:
                    self.message.set("校准完成。看 HDMI 左中右区域；看左/右停留约 0.75 秒确认，回中后可再次确认。")
                elif d["M"]==5:
                    self.message.set("校准失败。先返回预览检查图像与阈值，再重试；不要用转头代替眼睛移动。")
                self.last_mode = d["M"]
            self.start_button.configure(state="normal" if self.can_calibrate() else "disabled")
            if self.last_seq is not None and d["E"]!=self.last_seq and d["M"]==4 and d["D"] in ("L","R"):
                self.note(f"确认 #{d['E']}：{labels[d['D']]}。看中间释放后可再次确认。")
            self.last_seq = d["E"]
        else:
            self.message.set(value)
            self.note(value)

    def poll(self):
        if self.connection:
            try:
                data = self.connection.read(min(self.connection.in_waiting, 16384))
                for kind, value in self.decoder.feed(data):
                    self.handle(kind, value)
                now = time.monotonic()
                self.check_ack_timeout(now)
                if self.snapshot_time is not None and now-self.snapshot_time>20:
                    self.note("取图超时。复位板卡，检查摄像头后重新连接。")
                    self.disconnect()
                elif self.snapshot_time is None and now-self.last_status>2:
                    self.state.set("没有新版状态：检查 PL UART、J24 和 z15_screen_top.bit 是否下载。")
                    self.start_button.configure(state="disabled")
            except (serial.SerialException, OSError) as exc:
                self.note(str(exc))
                self.disconnect()
        self.root.after(20, self.poll)

    def close(self):
        self.disconnect()
        self.root.destroy()


if __name__=="__main__":
    root = tk.Tk()
    ScreenMonitor(root)
    root.mainloop()
