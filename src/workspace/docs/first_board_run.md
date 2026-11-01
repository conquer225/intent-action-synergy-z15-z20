# 首次接线与点击流程

本页保留 v1 单眼实验版记录。当前“摄像头在屏幕上方、识别左中右区域”请使用 [v2 完整操作说明](screen_gaze.md) 和 z15_screen_top.bit。

适用于目前已有的 Z15 眼控工程和 Vivado 2023.1。现有截图是旧的空工程 project_1；本次使用已经生成的眼控 bitstream。

## 1. 断电接线

关闭板卡电源，调整跳线与插拔模块时拔掉电源、USB 线。

| 项目 | 连接或设置 |
| --- | --- |
| 相机 | 正点原子 OV5640 → P2/CAMERA，18 针全部对齐，1 脚对 1 脚 |
| Bank34 / Bank35 | 均设 1.8V。所提供 1V1 原理图中的三针 J4/J3 各短接 2–3；其他版本按丝印与对应原理图核实 |
| 启动模式 | BOOT_CFG 1=ON、2=ON |
| 串口跳线 | J24 用两个跳线帽，分别短接 1–3、2–4 |
| 下载 | 电脑 USB → Xilinx 兼容下载器 → 10 针 JTAG/J18 |
| 结果传输 | 电脑 USB → 数据线 → PL UART/J23 的 Type-C 口 |
| 供电 | 原配 12V 适配器 → DC/J1，完成接线后打开板卡开关 |
| 可选屏幕 | HDMI OUT → 显示器 HDMI 输入 |

USB 串口线不承担整板供电。PL UART 与 PS UART 是两个接口，当前只用 PL UART。JTAG 下载器和串口各自连接电脑。

## 2. 打开已有工程

1. Vivado 左上角点 File → Open Project。
2. 文件名栏输入 `D:/fpga/z15_multimodal/local/eye_vivado/z15_eye.xpr`，点 Open。
3. 若提示关闭旧工程，按提示关闭；如旧工程有自己的未保存修改，先保存。
4. 确认窗口标题为 z15_eye，Sources 中顶层为 z15_eye_top。

已有 bitstream，不需要重新点 Run Synthesis 或 Generate Bitstream。

## 3. 下载到 FPGA

1. 左侧最下方 PROGRAM AND DEBUG 中点 Open Hardware Manager。
2. 页面上方点 Open target → Auto Connect。
3. 左侧 Hardware 树应出现 xc7z015_1 或名称包含 xc7z015 的设备。
4. 右键该设备 → Program Device。
5. Bitstream file 右侧点浏览，选择 `D:/fpga/z15_multimodal/report/eye/z15_eye_top.bit`。
6. Debug probes file 留空；保留默认的启动完成检查，点 Program。
7. 等进度结束，确认无下载错误、设备显示 Programmed；再等约 5–10 秒。

如果 Auto Connect 没找到器件，先检查板卡供电、下载器 USB/驱动、JTAG 排线和启动开关。此处只进行 JTAG 易失性下载，断电后重新下载。

## 4. 打开电脑工具

1. Windows 开始按钮右键 → 设备管理器 → 端口（COM 和 LPT）。记下 PL 串口的 COM 号；通常显示 USB-SERIAL CH340。
2. 多个 COM 口分不清时，观察拔插 PL UART 那条 USB 数据线后出现/消失的端口。
3. Windows 开始按钮右键 → 终端，进入 PowerShell，逐行执行：

```powershell
cd D:\fpga\z15_multimodal
python tools\eye_monitor.py
```

本机已验证 Python/tkinter/pyserial。换电脑遇到缺少 pyserial 时先执行 `python -m pip install -r tools/requirements.txt`。运行位置是 PowerShell，不是 Vivado 底部的 Tcl Console。

4. 工具窗口点刷新，选择 COM 号，再点连接。
5. 期望相机为 5640、就绪为 1、故障为 0。尚未校准时方向 I/有效 0 是正常状态。
6. 同一 COM 口只能由一个程序打开；关闭占用它的串口助手。

## 5. 取图与校准

1. 点“取图（约 7 秒）”，等待灰度图出现。它是一张快照，不是连续视频。
2. 固定摄像头与头部，调整位置/焦点，让一只眼睛在图中足够清楚，再取图确认。
3. 鼠标拖框圈住单只眼睛的眼白和瞳孔，避开眉毛、黑镜框与大片阴影。
4. 阈值先用 64，点“应用并清除校准”。结合图像调框/阈值，要求“特征”能稳定为 1。改参数后需重新校准。
5. 头部保持不动，看左侧时点“看左 → 校准左”，等“正在校准=0”。每次需要连续 8 个有效且稳定的帧。
6. 看中间，点“看中 → 校准中”，等 0；看右侧，点“看右 → 校准右”，等 0。
7. 三方向完成后应显示校准掩码 7、校准冲突 0。

如果正在校准一直不回 0，检查特征是否有效以及眼睛/头部是否晃动。校准冲突 1 通常表示三个参考位置太接近或中间不在两端之间。

## 6. 查看眼控结果

看左保持 15 个有效帧，日志出现一次 L 确认；一直看左不会连续重复。回中保持 6 个有效帧，再看右保持，日志出现一次 R 确认。中间用于释放，不产生新的动作事件。

头部、镜头位置或光照改变后可能需要重新设置区域和校准。当前还没有真实板卡准确率记录；首次上板先验证相机就绪与清晰图像，再判断方向结果。

用户 LED 的旧说明已经更正：当前 bitstream 中就绪/有效时相应用户灯熄灭。判断相机状态以串口为准；核心板 DONE 灯另表示配置完成。
