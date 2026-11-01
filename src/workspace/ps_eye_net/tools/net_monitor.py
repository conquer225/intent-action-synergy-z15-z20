"""PC face ROI preview and explicit board calibration controls (no webcam)."""
import argparse
import queue
import time
from pc_receiver import Receiver
from net_protocol import decode_image
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--board", default="192.168.1.10", help="板卡无线 IPv4 地址")
    p.add_argument("--port", type=int, default=5001)
    p.add_argument("--local-port", type=int, default=5001)
    p.add_argument("--headless", action="store_true")
    args = p.parse_args()
    receiver = Receiver(args.board, args.port, local_port=args.local_port)
    if args.headless:
        receiver.start()
        try:
            while receiver.is_alive():
                try:
                    item = receiver.updates.get(timeout=0.2)
                except queue.Empty:
                    continue
                if "frame" in item:
                    print("FRAME", item["frame"].packet.sequence, item["result"])
                else:
                    print(item)
        except KeyboardInterrupt:
            pass
        finally:
            receiver.close()
        return
    import tkinter as tk
    from tkinter import ttk
    import cv2
    import numpy as np
    window = tk.Tk()
    window.title("Z15 无线眼控 · 脸部 ROI / 瞳孔回传 r9")
    window.geometry("1040x790")
    bar = ttk.Frame(window, padding=12)
    bar.pack(fill="x")
    message = tk.StringVar(value="连接中；图像来自板端 OV5640")
    summary = tk.StringVar(value="等待板端状态")
    control_notice = tk.StringVar(value="控制回执待命")
    ttk.Label(bar, textvariable=message, wraplength=950).pack(anchor="w")
    ttk.Label(bar, textvariable=summary, wraplength=950, font=("Microsoft YaHei UI", 12)).pack(anchor="w", pady=8)
    ttk.Label(bar, textvariable=control_notice, wraplength=950).pack(anchor="w", pady=(0, 8))
    controls = ttk.Frame(bar)
    controls.pack(anchor="w")
    buttons = []
    for caption, code in [("开始三点校准（看 HDMI）", "c"), ("重试失败点", "t"), ("清除校准", "r")]:
        def send(c=code):
            try:
                receiver.command(c)
                control_notice.set(f"控制 {c} 已排队，等待匹配的板端回执")
                message.set("已发送请求，等待板端回执")
            except queue.Full:
                message.set("已有控制请求，请等待")
        b = ttk.Button(controls, text=caption, command=send, state="disabled")
        b.pack(side="left", padx=(0, 10))
        buttons.append(b)
    image_label = ttk.Label(window, anchor="center")
    image_label.pack(fill="both", expand=True, padx=12, pady=8)
    details = tk.StringVar(value="无线断开、眨眼或回传超时会暂停动作；来源切换后重新校准。")
    ttk.Label(window, textvariable=details, wraplength=980, padding=12).pack(fill="x")
    last_image = last_status = 0.0
    state = {}
    displayed_control = None
    def refresh():
        nonlocal last_image, last_status, state, displayed_control
        while True:
            try:
                item = receiver.updates.get_nowait()
            except queue.Empty:
                break
            if item.get("last_control"):
                reply = item["last_control"]
                key = (reply["session"], reply["sequence"])
                if key != displayed_control:
                    displayed_control = key
                    control_notice.set(f"板端回执 #{reply['sequence']} · {reply['code']} · " +
                                       ("已接受" if reply["accepted"] else "已拒绝：时效、测量或校准状态不满足"))
            if "message" in item:
                message.set(item["message"])
            if "error" in item:
                message.set(item["error"])
            if item.get("disconnected"):
                state = {}
                last_status = 0
            if "status" in item:
                state, last_status = item["status"], item["received"]
                names = {0: "无效", 1: "左", 2: "中", 3: "右"}
                stage = {1: "看左点", 2: "看中点", 3: "看右点"}.get(state.get("stage"),
                            "已完成" if state.get("cal") == 7 else "未开始")
                if state.get("failed"):
                    stage = "失败，请重试该点"
                summary.set(f"来源 {state.get('source')} · 双眼 {state.get('eye_valid')} · "
                            f"注视 {names.get(state.get('dir'), '无效')} · 有效 {state.get('valid')} · "
                            f"校准 {stage} · 事件 {state.get('event')}")
                details.set(f"瞳孔 {state.get('pupil')} / 归一化 {state.get('nx')}；"
                            f"采样间隔 {state.get('period_ms')} ms，PC计算 {state.get('detect_ms')} ms；"
                            f"校准样本 {state.get('counts')}，参考 {state.get('refs')}；"
                            f"超时 {state.get('timeouts')}，拒收 {state.get('rejected')}；"
                            f"相机/HDMI帧 {state.get('cam_frames', '-')} / {state.get('hdmi_frames', '-')}")
            if "frame" in item:
                f, result = item["frame"], item["result"]
                x, y, w, h, iw, ih = f.fields[:6]
                image = decode_image(f)
                for eye in (result["left"], result["right"]):
                    if result["pair"]:
                        ex, ey, ew, eh = eye["analyzed"]
                        p0 = (round((ex - x) * iw / w), round((ey - y) * ih / h))
                        p1 = (round((ex + ew - x) * iw / w), round((ey + eh - y) * ih / h))
                        cv2.rectangle(image, p0, p1, (40, 210, 40) if eye["valid"] else (30, 30, 210), 1)
                    if eye["valid"]:
                        px, py = round((eye["x"] - x) * iw / w), round((eye["y"] - y) * ih / h)
                        cv2.drawMarker(image, (px, py), (0, 255, 255), cv2.MARKER_CROSS, 15, 1)
                scale = min(960 / iw, 530 / ih)
                image = cv2.resize(image, (round(iw * scale), round(ih * scale)))
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                hh, ww = rgb.shape[:2]
                photo = tk.PhotoImage(data=f"P6\n{ww} {hh}\n255\n".encode() + rgb.tobytes(), format="PPM")
                image_label.configure(image=photo)
                image_label.image = photo
                last_image = item["received"]
                message.set(f"板端帧 {f.packet.sequence} · {'全帧找脸' if f.fields[20] & 1 else '完整脸部 ROI'} · "
                            f"已回传 {item['frames']} 帧 · 缺包丢帧 {item['dropped']}")
        fresh = last_status and time.monotonic() - last_status <= 1.5
        for i, button in enumerate(buttons):
            allowed = bool(fresh)
            if i == 0:
                allowed = allowed and state.get("stable", 0) >= 2 and any(state.get("eye_valid", []))
            if i == 1:
                allowed = allowed and bool(state.get("failed"))
            button.configure(state="normal" if allowed else "disabled")
        if not fresh:
            summary.set("板端状态过期，眼控暂停")
        if last_image and time.monotonic() - last_image > 0.8:
            message.set("图像已过期；保留的预览不代表当前瞳孔位置")
        window.after(50, refresh)
    def close():
        receiver.close()
        window.destroy()
    window.protocol("WM_DELETE_WINDOW", close)
    receiver.start()
    refresh()
    window.mainloop()
if __name__ == "__main__":
    main()
