# Z15 眼控工程使用说明

本页保留 v1 单眼实验版记录。当前“摄像头在屏幕上方、识别左中右区域”请使用 [v2 完整操作说明](screen_gaze.md) 和 z15_screen_top.bit。

本版接线目标是正点原子 Z15 + 正点原子 OV5640（P2），电脑通过 PL USB 串口查看左/中/右、有效状态和确认事件。处理在 FPGA 的 PL 内完成；电脑只负责取图、设置参数、校准和显示结果。器件 `xc7z015clg485-2`，Vivado 2023.1。

本版采用固定头位的单眼区域识别。第一次使用需要框选眼部、调整阈值并校准三个方向；更换位置或光照后通常需要重新调参。尚无这块实物板卡的采集视频和眼控准确率记录。仿真与实现结果见 `report/eye/verification.md`。

## 接线与下载

1. 断电，将正点原子 OV5640 接到 **P2 摄像头接口**，按板卡/模块的定位与 1 脚标记对齐，不错位、不反插。不是 FMC 摄像头接口。原厂此模块自带参考时钟，工程不从 PL 额外输出 XCLK。
2. 断电检查 Bank 电压：当前 XDC 要求 Bank34、Bank35 为 **1.8V**。提供的底板 1V1 原理图物理第 3 页中，J4（Bank34）、J3（Bank35）均为三针排针，应各用一个跳线帽短接 **2–3**。FPGA 手册 p106 混有六针版本图，不能把两版针号混用；若实物不是三针，按实物版本与 1.8V 丝印核实后再上电。
3. 接原配 12V 电源适配器到 DC 电源座 J1；下载器 USB 端接电脑，10 针排线接 JTAG/J18，按定位和 1 脚标记连接。另用可传数据的 Type-C 线把 **PL UART/J23** 接电脑。按底板原理图，J24 的 **1–3、2–4** 接通 USB UART 通路（另一组位置用于 ATK 接口）。以 PCB 丝印/跳线编号核实，不能按照片的左右方向猜。
4. 上电前把 BOOT_CFG 的 **1、2 都拨到 ON**，选择 JTAG 启动。工程只下载 PL bitstream，不需要启动 PYNQ、Linux 或初始化 DDR。完成上述接线后再打开电源开关。
5. 打开 Vivado → Hardware Manager → Open Target → Auto Connect，选择 `xc7z015`，Program Device 指向 `report/eye/z15_eye_top.bit`。不要把文件烧进未知型号 Flash。此处是易失性 JTAG 下载，断电需重新下载。
6. 等待约 5 秒初始化，再额外等待 10 帧自动曝光稳定。串口状态应出现 `I5640 R1 !0`。**LED 说明勘误**：底板用户灯为高电平点亮，而本版 RTL 输出取反，因此 `led[0]` 对应灯在相机 ready 时熄灭，`led[1]` 对应灯在方向 valid 时熄灭；板上可能标为 PL_LED1/PL_LED2。此前“亮表示完成/有效”的描述错误。请以串口字段判断，不要与核心板 DONE 灯混淆。

从空工程界面开始的逐步操作见 [首次接线与点击流程](first_board_run.md)。

HDMI 可选，接板卡 **HDMI OUT**。输出 640×480/60 Hz 的灰度放大图、青色 ROI、有效时的红色质心线和顶部方向指示条。预览使用单缓冲，允许画面撕裂；识别只使用完整帧统计，电脑快照独立冻结。

## 电脑校准工具

在工程根目录执行：

```powershell
python -m pip install -r tools/requirements.txt
python tools/eye_monitor.py
```

需要带 tkinter 的 Python，Python.org 的 Windows 安装版通常已包含。依赖只有 pyserial 3.5。串口固定 **115200、8 数据位、无校验、1 停止位、无流控**，不要让其他串口助手同时占用同一个 COM 口。

先连接正确 COM 口并点击“取图”。320×240 灰度图约 7 秒传完；取图期间暂停眼控确认，传完恢复。将摄像头放到能清楚看到单只眼睛的距离，保持头部不动，在图上拖框，覆盖瞳孔和周围眼白，尽量排除眉毛、镜框和大片阴影。框宽最少 16、高最少 8，不超过图像边界。

阈值默认 64，低于阈值的像素视为暗区。点击“应用并清除校准”。查看 `F`：持续为 1 才表示暗区通过基础检查。`F0` 时结合快照调阈值和框；阈值太高会把睫毛、阴影一起纳入，太低会漏掉瞳孔。仅仅看到一个暗区并不等于已经识别人眼。

保持看向左侧，点击“校准左”，等待 `A0`；看中间校准中，看右侧校准右。每个方向要求连续 8 个有效帧，样本质心跨度不超过 6 像素。`C7` 表示三组齐全；`K1` 表示三组顺序/距离不合格，需重新校准。左右可以随镜像反向，但中间位置必须位于两端之间，相邻参考点至少相差 6 像素。

正常工作时，左/右方向连续保持 **15 个有效帧**产生一次确认。一直看同一边不会重复发；回中保持 **6 帧**后才重新使能。中间作为释放位置，不单独发动作。帧率没有实测，15 帧不应直接写成精确毫秒数。丢帧、遮挡、边界模糊会清空本次停留计数；无帧 250 ms 后输出 INVALID。改 ROI/阈值或清除校准会清零事件序号。

## 串口协议

正常约每 100 ms 输出一行 ASCII，数值为十六进制，最后 CR/LF：

```text
EYE L V1 F1 C7 A0 X087 N00C5 QA4 E0001 DL S0 I5640 R1 !0 K0
```

| 字段 | 含义 |
| --- | --- |
| `EYE L/C/R/I` | 当前左/中/右/无效方向 |
| V | 当前方向有效 |
| F | 最近一帧特征通过检查；断流时须同时看 S/V |
| C | 三个校准位：bit0 左、bit1 中、bit2 右；完整为 7 |
| A | 正在校准：0 无、1 左、2 中、3 右 |
| X | 全图横向质心，0–319 |
| N | ROI 暗像素个数 |
| Q | ROI 最大灰度减最小灰度，**不是算法置信概率** |
| E / D | 16 位确认事件序号 / 最近确认方向；只有序号变化才是新事件 |
| S | 无新帧 250 ms 的断流标志 |
| I / R / ! | 传感器 ID / 配置完成 / SCCB 或 ID 错误 |
| K | 校准参考点不满足顺序和距离要求 |

发送单个小写字符（可不加换行）：`l`、`c`、`r` 采集校准；`x` 清除校准；`p` 请求快照。换行和其他字符忽略。

ROI 配置包共 9 字节：`A5 x_hi x_lo y width height threshold xor 5A`，xor 是 6 个参数字节的异或，不含 A5/5A。越界或校验错误的包丢弃，残缺包在 100 ms 后超时。Python 的 `tools/eye_protocol.py` 提供编码函数。

快照输出：`5A 49 4D 47 40 01 F0 00`（ASCII `ZIMG`，宽高 little-endian）后紧跟 **76800 字节**灰度像素，逐行、每行 320 像素。此期间暂停 ASCII 状态，传完自动恢复。快照只用于调试，不是实时视频串流。普通串口助手收到图像会显示乱码，使用专用工具解析。

## 重新创建与构建

```powershell
& 'D:/vivado/Vivado/2023.1/bin/vivado.bat' -mode batch -source build/eye/create_project.tcl
& 'D:/vivado/Vivado/2023.1/bin/vivado.bat' -mode batch -source build/eye/build.tcl
```

第一条创建 `local/eye_vivado/z15_eye.xpr`，第二条执行综合、实现、bitstream 和报告，并检查 setup/hold。输出为 `report/eye/`。脚本的源码路径相对工程根目录，不依赖 E 盘资料或旧 Vivado 空工程。

构建末尾使用 Python 保存源码、约束、bitstream 和报告的 SHA-256。收到源码包后可运行 `python tools/eye_manifest.py` 验证它们配套；修改 RTL/XDC 后必须重新构建，不能继续分发旧 bitstream。

```powershell
./build/eye/test.ps1
./build/eye/test_pipeline.ps1
python -m unittest discover -s sim/eye -p 'test_*.py'
```

默认集成测试保留真实相机采集、XPM FIFO、识别和 UART；HDMI 时钟与串化器使用仅供测试的替代模型，不代表 HDMI 器件级验证。`test_pipeline.ps1 -DeviceDisplay` 可运行完整器件模型，耗时较长。传感器初始化在集成测试中旁路，SCCB 主机另行测试。

源码包中的 XPR 是从包内源码新建的干净工程，可以直接打开。完整报告与 bitstream 已在 `report/eye/`，无需重新综合才能下载。重打包命令为 `python tools/package_eye.py --output D:/fpga/Z15_Eye_Control_v1.zip`；打包会验证仿真记录、文件哈希和工程源路径。

Vivado 安装位置变化时给 PowerShell 测试脚本传 `-Vivado 新路径`。Windows 启动脚本偶尔打印两行 `ECHO is off`，本机实际 batch / XSim 可运行；以退出码、PASS 标记和报告判断，不只看 `-version`。

## 排查顺序

| 现象 | 检查 |
| --- | --- |
| 完全没串口数据 | bitstream 是否加载、是否选 PL COM、J24 是否接 USB 通路、115200 配置 |
| R0 或 !1 | P2 方向/接触、OV5640 供电、SCCB；工程会自动重试初始化 |
| I5640 R1 但一直 S1 | PCLK/VSYNC/HREF 接线，P2 是否选错；D4 应为 U1，PWDN 为 K7 |
| 能取图但 F0 | 对焦/曝光、ROI 是否只包含一只眼、阈值和睫毛/阴影干扰 |
| C7 K1 | 三方向没有拉开足够距离，或者校准顺序/头部位置改变 |
| 方向有效但没有下一次确认 | 先回中连续保持 6 帧；仅闭眼不会重新使能 |
| 取图时长时间无状态 | 正常传输约 7 秒；超过 20 秒，复位板卡并重新连接 |

引脚冲突、例程版本和论文参考见 `docs/eye_research.md`、`THIRD_PARTY.md`。本版约束中的 DVP 外部时序包络仍需在实物上验证；工具时序通过不能替代摄像头电气实测。
