"""Inspect frozen UART grayscale bytes; never reads rendered overlay colors."""
import json
import tempfile
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from tkinter import ttk, messagebox

WIDTH, HEIGHT = 320, 240
LABELS = ("眼1 暗部", "眼1 眼白", "眼2 暗部", "眼2 眼白", "其他")


def pixel_stats(gray, x, y):
    """Coordinates address snapshot pixels, not the 2x displayed image."""
    if len(gray) != WIDTH * HEIGHT or not (0 <= x < WIDTH and 0 <= y < HEIGHT):
        raise ValueError("快照尺寸或取样位置不正确")
    nearby = [gray[yy * WIDTH + xx]
              for yy in range(max(0, y-1), min(HEIGHT, y+2))
              for xx in range(max(0, x-1), min(WIDTH, x+2))]
    return {"snapshot_x": x, "snapshot_y": y, "vga_x": x*2, "vga_y": y*2,
            "gray": gray[y*WIDTH+x], "nearby_min": min(nearby),
            "nearby_max": max(nearby), "nearby_median": median(nearby),
            "nearby_count": len(nearby)}


class SnapshotInspector:
    def __init__(self, parent, gray, metadata):
        if len(gray) != WIDTH * HEIGHT:
            raise ValueError("需要完整的 320×240 快照")
        self.gray = bytes(gray)
        self.metadata = metadata
        self.samples = []
        self.window = tk.Toplevel(parent)
        self.window.title("Z15 原始灰度检查 · 静态快照")
        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="移动鼠标查看灰度；选择记录类型后，在原图上单击取样。0 最黑，255 最亮。",
                  wraplength=940).pack(anchor="w")
        ttk.Label(outer, text="这是打开检查窗口时的静态快照；重新取图后，请重新打开检查窗口。",
                  wraplength=940).pack(anchor="w", pady=(2, 8))
        row = ttk.Frame(outer)
        row.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(row, width=640, height=480, highlightthickness=0)
        self.canvas.pack(side="left", anchor="n")
        self.raw_photo = tk.PhotoImage(master=self.window,
                                      data=b"P5\n320 240\n255\n"+self.gray, format="PPM")
        self.display_photo = self.raw_photo.zoom(2)
        self.canvas.create_image(0, 0, image=self.display_photo, anchor="nw")
        side = ttk.Frame(row, padding=(12, 0, 0, 0))
        side.pack(side="left", fill="both", expand=True)
        self.label = tk.StringVar(master=self.window, value=LABELS[0])
        ttk.Label(side, text="记录类型（由你判断位置）").pack(anchor="w")
        ttk.Combobox(side, textvariable=self.label, values=LABELS,
                     state="readonly", width=24).pack(anchor="w", pady=4)
        self.zoom_canvas = tk.Canvas(side, width=200, height=200, bg="#202020", highlightthickness=0)
        self.zoom_canvas.pack(anchor="w", pady=6)
        self.readout = tk.StringVar(master=self.window, value="把鼠标移到左侧眼睛上")
        ttk.Label(side, textvariable=self.readout, wraplength=260).pack(anchor="w")
        ttk.Label(side, text="局部放大 8 倍，不增加细节。\n取样避开镜框、眼睑和反光点。\n每类取 3–5 个点，不要只看一个点。",
                  wraplength=260).pack(anchor="w", pady=8)
        ttk.Button(side, text="清空取样", command=self.clear_samples).pack(fill="x", pady=3)
        ttk.Button(side, text="保存原图和取样", command=self.save).pack(fill="x", pady=3)
        self.records = tk.Text(outer, width=100, height=5, state="disabled", wrap="word")
        self.records.pack(fill="both", expand=True, pady=(8, 4))
        self.status = tk.StringVar(master=self.window, value="原图为 320×240 降采样灰度；没有红蓝覆盖。取样不改变 FPGA 参数。")
        ttk.Label(outer, textvariable=self.status, wraplength=930).pack(anchor="w")
        self.canvas.bind("<Motion>", self.inspect)
        self.canvas.bind("<Button-1>", self.record)

    def inspect(self, event):
        if not (0 <= event.x < 640 and 0 <= event.y < 480):
            return None
        x, y = event.x//2, event.y//2
        stats = pixel_stats(self.gray, x, y)
        self.readout.set(f"原图位置 ({x}, {y})\n灰度 {stats['gray']}\n"
                         f"附近 3×3：{stats['nearby_min']}–{stats['nearby_max']}\n"
                         f"中位数 {stats['nearby_median']:g}")
        x0, y0 = max(0, min(WIDTH-25, x-12)), max(0, min(HEIGHT-25, y-12))
        crop = b"".join(self.gray[yy*WIDTH+x0:yy*WIDTH+x0+25] for yy in range(y0, y0+25))
        self.zoom_photo = tk.PhotoImage(master=self.window, data=b"P5\n25 25\n255\n"+crop, format="PPM").zoom(8)
        self.zoom_canvas.delete("all")
        self.zoom_canvas.create_image(0, 0, image=self.zoom_photo, anchor="nw")
        xx, yy = (x-x0)*8, (y-y0)*8
        self.zoom_canvas.create_rectangle(xx, yy, xx+8, yy+8, outline="#00d080", width=1)
        return stats

    def record(self, event):
        stats = self.inspect(event)
        if stats is None:
            return
        sample = {"label": self.label.get(), **stats}
        self.samples.append(sample)
        self.records.configure(state="normal")
        self.records.insert("end", f"{len(self.samples)}. {sample['label']}  "
                            f"({sample['snapshot_x']}, {sample['snapshot_y']})  灰度 {sample['gray']}  "
                            f"附近 {sample['nearby_min']}–{sample['nearby_max']}  "
                            f"中位数 {sample['nearby_median']:g}\n")
        self.records.see("end")
        self.records.configure(state="disabled")

    def clear_samples(self):
        self.samples.clear()
        self.records.configure(state="normal")
        self.records.delete("1.0", "end")
        self.records.configure(state="disabled")

    def export(self, directory):
        """Save the unscaled image with no markers, colors or contrast adjustment."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.raw_photo.write(str(directory / "raw.png"), format="png")
        report = {"format_version": 1, "width": WIDTH, "height": HEIGHT,
                  "sampling": "VGA even x/y pixels; original UART gray bytes",
                  "exported_utc": datetime.now(timezone.utc).isoformat(),
                  "context": self.metadata, "samples": self.samples,
                  "labels": "Manually selected, not an anatomical detection result"}
        (directory / "samples.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def save(self):
        try:
            base = Path(__file__).resolve().parents[1] / "local" / "eye_captures"
            base.mkdir(parents=True, exist_ok=True)
            directory = Path(tempfile.mkdtemp(prefix=datetime.now().strftime("%Y%m%d_%H%M%S_"), dir=base))
            self.export(directory)
        except (OSError, tk.TclError) as exc:
            messagebox.showerror("保存失败", str(exc), parent=self.window)
            return
        self.status.set("已保存："+str(directory))
        messagebox.showinfo("保存成功", f"原图：raw.png\n取样记录：samples.json\n\n{directory}", parent=self.window)
