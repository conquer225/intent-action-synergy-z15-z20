"""Optional Tkinter console. Importing this module does not open a window."""
from __future__ import annotations

import argparse
import json
import queue
import threading
import time
from typing import Any, Callable

from pc_client import ClientError, ControlClient, SOURCES


class ControllerWindow:
    def __init__(self, root: Any, tk: Any, ttk: Any, *, host: str, port: int,
                 source: str, simulator: Any = None):
        self.root, self.tk, self.ttk = root, tk, ttk
        self.simulator = simulator
        self.client: ControlClient | None = None
        self.busy = False
        self.closing = False
        self.results: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.operation_lock = threading.Lock()
        self.command_buttons: list[Any] = []
        self.root.title("MultiControlS3 本机演练" if simulator else "MultiControlS3 PC 控制")
        self.root.geometry("910x750")
        self.root.minsize(800, 680)
        self.root.protocol("WM_DELETE_WINDOW", self._shutdown)
        page = ttk.Frame(root, padding=14)
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(6, weight=1)
        banner = "本机模拟：传感器、标定状态和动作均为合成数据，无硬件输出。" if simulator else \
                 "连接后先选择设备模式，再单独启用。断线后需要手动重连和启用。"
        ttk.Label(page, text=banner, wraplength=850).grid(row=0, column=0, sticky="w", pady=(0, 10))
        connect_row = ttk.Frame(page)
        connect_row.grid(row=1, column=0, sticky="ew")
        self.host = tk.StringVar(value=host)
        self.port = tk.StringVar(value=str(port))
        self.source = tk.StringVar(value=source)
        for column, text in ((0, "ESP32 地址"), (2, "端口"), (4, "来源")):
            ttk.Label(connect_row, text=text).grid(row=0, column=column, padx=(0, 4))
        self.host_entry = ttk.Entry(connect_row, textvariable=self.host, width=19)
        self.host_entry.grid(row=0, column=1, padx=(0, 10))
        self.port_entry = ttk.Entry(connect_row, textvariable=self.port, width=7)
        self.port_entry.grid(row=0, column=3, padx=(0, 10))
        self.source_box = ttk.Combobox(connect_row, textvariable=self.source,
                                       values=sorted(SOURCES), state="readonly", width=7)
        self.source_box.grid(row=0, column=5, padx=(0, 10))
        if simulator:
            self.host_entry.configure(state="disabled")
            self.port_entry.configure(state="disabled")
        self.connect_button = ttk.Button(connect_row, text="连接", command=self._connect)
        self.connect_button.grid(row=0, column=6, padx=4)
        self.disconnect_button = ttk.Button(connect_row, text="断开", command=self._disconnect)
        self.disconnect_button.grid(row=0, column=7, padx=4)
        self.connection = tk.StringVar(value="未连接")
        ttk.Label(page, textvariable=self.connection).grid(row=2, column=0, sticky="w", pady=8)
        devices = ttk.Frame(page)
        devices.grid(row=3, column=0, sticky="ew")
        devices.columnconfigure(0, weight=1)
        devices.columnconfigure(1, weight=1)
        self.device_status: dict[str, Any] = {}
        self.modes: dict[str, Any] = {}
        for column, (device, title, modes) in enumerate((
                ("hand", "灵巧手", ("network", "emg", "glove")),
                ("pendulum", "倒立摆", ("network", "emg")))):
            frame = ttk.LabelFrame(devices, text=title, padding=10)
            frame.grid(row=0, column=column, sticky="nsew", padx=(0, 8) if column == 0 else (8, 0))
            self.modes[device] = tk.StringVar(value="network")
            ttk.Combobox(frame, textvariable=self.modes[device], values=modes,
                         state="readonly", width=13).grid(row=0, column=0, sticky="w")
            self._button(frame, "应用模式", lambda d=device: self._command(d, "mode", mode=self.modes[d].get()), 0, 1)
            self._button(frame, "启用", lambda d=device: self._command(d, "enable"), 1, 0)
            self._button(frame, "停用", lambda d=device: self._command(d, "disable"), 1, 1)
            actions = (("张开", "open"), ("闭合", "close")) if device == "hand" else \
                      (("启动平衡", "start"), ("停止", "stop"), ("向左", "left"), ("向右", "right"))
            for index, (label, action) in enumerate(actions):
                self._button(frame, label, lambda d=device, a=action: self._command(d, a), 2 + index // 2, index % 2)
            self.device_status[device] = tk.StringVar(value="等待状态")
            ttk.Label(frame, textvariable=self.device_status[device], wraplength=380).grid(
                row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
            frame.columnconfigure(0, weight=1)
            frame.columnconfigure(1, weight=1)
        telemetry = ttk.LabelFrame(page, text="灵巧手反馈 / 六路姿态", padding=10)
        telemetry.grid(row=4, column=0, sticky="ew", pady=12)
        self.pressure_labels: list[Any] = []
        for index in range(5):
            text = tk.StringVar(value=f"压力 {index + 1}: 未上报  PWM: 未上报")
            self.pressure_labels.append(text)
            ttk.Label(telemetry, textvariable=text).grid(row=0, column=index, sticky="w", padx=4)
        self.angles = tk.StringVar(value="目标角度：未上报")
        self.pots = tk.StringVar(value="电位器 ADC：未上报")
        self.hand_flags = tk.StringVar(value="标定 / RF / 执行器：等待状态")
        for row, variable in ((1, self.angles), (2, self.pots), (3, self.hand_flags)):
            ttk.Label(telemetry, textvariable=variable, wraplength=840).grid(
                row=row, column=0, columnspan=6, sticky="w", pady=3)
        pose_row = ttk.Frame(telemetry)
        pose_row.grid(row=4, column=0, columnspan=6, sticky="w", pady=(8, 0))
        ttk.Label(pose_row, text="目标角度 0–180：").pack(side="left")
        self.pose_entries: list[Any] = []
        for index in range(6):
            value = tk.StringVar(value="")
            self.pose_entries.append(value)
            ttk.Entry(pose_row, textvariable=value, width=5).pack(side="left", padx=3)
        pose_button = ttk.Button(pose_row, text="发送六路姿态", command=self._pose)
        pose_button.pack(side="left", padx=8)
        self.command_buttons.append(pose_button)
        controls = ttk.Frame(page)
        controls.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        self._button(controls, "读取状态", lambda: self._command("all", "status"), 0, 0)
        stop = tk.Button(controls, text="全部急停", bg="#b3261e", fg="white",
                         activebackground="#8c1d18", font=("Microsoft YaHei UI", 11, "bold"),
                         command=self._estop)
        stop.grid(row=0, column=1, padx=12, ipadx=16, ipady=3)
        ttk.Label(controls, text="实物首次使用：先通过 USB 保存张开/闭合姿态并完成标定。",
                  wraplength=520).grid(row=0, column=2, sticky="w")
        self.log = tk.Text(page, height=9, wrap="word", state="disabled")
        self.log.grid(row=6, column=0, sticky="nsew")
        self._refresh_controls()
        self.root.after(80, self._poll)

    def _button(self, parent: Any, text: str, command: Callable[[], None], row: int, column: int) -> None:
        button = self.ttk.Button(parent, text=text, command=command)
        button.grid(row=row, column=column, sticky="ew", padx=3, pady=3)
        self.command_buttons.append(button)

    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S ") + text + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 200:
            self.log.delete("1.0", "20.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _refresh_controls(self) -> None:
        connected = self.client is not None and self.client.connected
        active = connected and not self.busy and not self.closing
        for button in self.command_buttons:
            button.configure(state="normal" if active else "disabled")
        self.connect_button.configure(state="normal" if not connected and not self.busy and not self.closing else "disabled")
        self.disconnect_button.configure(state="normal" if connected and not self.busy and not self.closing else "disabled")
        self.source_box.configure(state="disabled" if connected or self.busy else "readonly")
        if not self.simulator:
            self.host_entry.configure(state="disabled" if connected or self.busy else "normal")
            self.port_entry.configure(state="disabled" if connected or self.busy else "normal")

    def _submit(self, work: Callable[[], Any]) -> None:
        if self.busy or self.closing:
            return
        self.busy = True
        self._refresh_controls()

        def run() -> None:
            try:
                with self.operation_lock:
                    self.results.put(("result", work()))
            except Exception as exc:
                self.results.put(("error", str(exc)))
        threading.Thread(target=run, name="gui-request", daemon=True).start()

    def _connect(self) -> None:
        try:
            new_client = ControlClient(self.host.get().strip(), int(self.port.get()), self.source.get())
        except ValueError as exc:
            self._log(str(exc))
            return

        def work() -> dict[str, Any]:
            if self.client:
                self.client.close()
            self.client = new_client
            new_client.connect()
            return new_client.send("all", "status")
        self._submit(work)

    def _disconnect(self) -> None:
        client = self.client
        if client:
            self._submit(lambda: client.close())

    def _command(self, device: str, action: str, **fields: Any) -> None:
        client = self.client
        if client and client.connected:
            self._submit(lambda: client.send(device, action, **fields))

    def _pose(self) -> None:
        try:
            values = [int(value.get()) for value in self.pose_entries]
            if any(not 0 <= value <= 180 for value in values):
                raise ValueError("角度超出 0–180")
        except ValueError:
            self._log("请填写六个 0–180 的整数角度。")
            return
        self._command("hand", "pose", angles=values)

    def _estop(self) -> None:
        client = self.client
        if not client or not client.connected:
            self._log("连接已关闭；急停未送达。实物请使用硬件停止开关。")
            return

        def work() -> None:
            try:
                reply = client.send("all", "estop")
                self.results.put(("estop", reply))
            except Exception as exc:
                self.results.put(("estop_error", str(exc)))
        # Do not queue emergency stop behind an ordinary GUI task.
        threading.Thread(target=work, name="gui-estop", daemon=True).start()

    def _show_status(self, status: dict[str, Any]) -> None:
        for device in ("hand", "pendulum"):
            state = status.get(device, {})
            if not isinstance(state, dict):
                continue
            line = f"模式 {state.get('mode', '?')} / 来源 {state.get('source', '?')} / 启用 {state.get('enabled', '?')}"
            if device == "pendulum":
                line += f"\n状态 {state.get('state', '?')} / 桥接 {state.get('bridge_link', '?')} / STM新鲜 {state.get('stm_fresh', '?')}"
                if state.get("blocked"):
                    line += f"\n接收端阻断 {state['blocked']}"
            self.device_status[device].set(line)
        hand, sensors = status.get("hand", {}), status.get("sensors", {})
        if not isinstance(hand, dict) or not isinstance(sensors, dict):
            return
        pressures, pwm = hand.get("pressures", []), hand.get("vibration_pwm", [])
        valid = hand.get("pressure_valid", False)
        for index, variable in enumerate(self.pressure_labels):
            pressure = pressures[index] if isinstance(pressures, list) and index < len(pressures) else "?"
            vibration = pwm[index] if isinstance(pwm, list) and index < len(pwm) else "?"
            variable.set(f"压力 {index + 1}: {pressure if valid else '无效'}  PWM: {vibration}")
        self.angles.set(f"目标角度：{hand.get('angles', '未上报')}")
        self.pots.set(f"电位器 ADC：{sensors.get('pots', '未上报')}")
        self.hand_flags.set(f"电位器标定 {hand.get('pot_calibrated', '?')} / 姿态就绪 {hand.get('poses_ready', '?')} / "
                            f"压力标定 {hand.get('pressure_calibrated', '?')} / RF链路 {hand.get('radio_link', '?')} / "
                            f"执行器就绪 {hand.get('actuator_ready', '?')}")

    def _poll(self) -> None:
        while True:
            try:
                kind, value = self.results.get_nowait()
            except queue.Empty:
                break
            if kind == "closed":
                self.root.destroy()
                return
            if kind in ("result", "error"):
                self.busy = False
            if value is not None:
                if isinstance(value, dict):
                    self._log(json.dumps({key: item for key, item in value.items() if key != "status"}, ensure_ascii=False))
                else:
                    self._log(str(value))
        client = self.client
        if client:
            while True:
                try:
                    event = client.events.get_nowait()
                except queue.Empty:
                    break
                if event["event"] == "disconnected":
                    self._log(f"连接关闭：{event.get('error', '?')}。重连不会恢复动作。")
            self._show_status(client.latest_status)
        connected = client is not None and client.connected
        self.connection.set("已连接，100 ms 心跳" if connected else "未连接；反馈为上次收到的状态")
        if self.closing:
            self.connection.set("正在急停并关闭连接")
        self._refresh_controls()
        self.root.after(80, self._poll)

    def _shutdown(self) -> None:
        if self.closing:
            return
        self.closing = True
        self._refresh_controls()

        def close() -> None:
            try:
                # A pending connect must finish before shutdown closes its client.
                with self.operation_lock:
                    if self.client:
                        self.client.close()
                    if self.simulator:
                        self.simulator.close()
            finally:
                self.results.put(("closed", None))
        threading.Thread(target=close, name="gui-shutdown", daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MultiControlS3 PC panel (Tkinter standard library)")
    parser.add_argument("--host", default="")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--source", choices=sorted(SOURCES), default="pc")
    parser.add_argument("--simulate", action="store_true")
    args = parser.parse_args(argv)
    if args.simulate and args.host:
        parser.error("--simulate cannot be combined with --host")
    simulator = None
    app = None
    try:
        # Import only when opening the GUI; command-line and tests need no display.
        import tkinter as tk
        from tkinter import ttk
        if args.simulate:
            from mock_server import MockControlServer
            simulator = MockControlServer().start()
            args.host, args.port = "127.0.0.1", simulator.port
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            raise RuntimeError(str(exc)) from exc
        app = ControllerWindow(root, tk, ttk, host=args.host, port=args.port,
                               source=args.source, simulator=simulator)
        root.mainloop()
        return 0
    except (ImportError, OSError, RuntimeError) as exc:
        print(f"GUI unavailable: {exc}; use pc_client.py instead.")
        return 1
    finally:
        if app:
            with app.operation_lock:
                if app.client:
                    app.client.close()
        if simulator:
            simulator.close()


if __name__ == "__main__":
    raise SystemExit(main())
