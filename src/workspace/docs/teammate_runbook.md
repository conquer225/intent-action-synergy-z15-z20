# 队友运行清单：Z15 屏幕左、中、右眼控

这份清单对应当前 v2 固件：`report/screen/z15_screen_top.bit`。目标是让使用者看 HDMI 屏幕的左、中、右三个区域，Z15 通过 OV5640 采集双眼，FPGA 输出当前方向和左右确认事件。

当前版本使用固定坐姿、手动框选双眼和三点校准。它还没有做自动人脸定位，也没有完成真实摄像头准确率测试。第一次运行要把结果当作上板联调结果记录。

## 先记住：电脑上有两个窗口

| 位置 | 用途 | 能否在这里框眼睛 |
| --- | --- | --- |
| Vivado | 把 `.bit` 固件下载到 Z15 | 不能 |
| 电脑上的 `Z15 屏幕三分区眼控 · 双眼设置` | 选 COM、取图、框双眼、调阈值、开始校准 | 可以，只有这里可以 |
| HDMI 显示器 | 显示摄像头预览、校准白点和 LEFT/CENTER/RIGHT | 不能用鼠标框眼睛 |

设置窗口由下面的命令打开。队友应在项目根目录打开 PowerShell，逐行输入：

```powershell
cd D:\fpga\z15_multimodal
python tools\screen_monitor.py
```

如果项目是从 ZIP 解压出来的，先把 `D:\fpga\z15_multimodal` 换成实际解压目录。命令运行后会出现标题为 **Z15 屏幕三分区眼控 · 双眼设置** 的电脑窗口。窗口顶部有 **刷新、连接、断开、取图（约 7 秒）**，右侧有 **框选眼 1、框选眼 2、应用双眼参数、开始 HDMI 三点校准**。

## A. 准备软件

1. 在英文短路径解压 `Z15_Screen_Gaze_v2.zip`，例如 `D:\fpga\z15_multimodal`。路径中不要放在桌面深层中文目录中。
2. 安装 Vivado 2023.1，并确认包含 Artix-7/Zynq-7000 器件支持。
3. 安装带 `tkinter` 的 64 位 Python。打开 PowerShell 检查：

   ```powershell
   python --version
   python -c "import tkinter; print('tkinter OK')"
   ```

4. 安装电脑工具依赖：

   ```powershell
   cd D:\fpga\z15_multimodal
   python -m pip install -r tools\requirements.txt
   ```

   这一步安装的是 `pyserial`。如果电脑没有 `python` 命令，使用 Python 安装器提供的 `py` 命令，并把清单中的 `python` 替换为 `py`。

## B. 断电接线

先关闭 Z15 电源，再接线。需要：Z15、正点原子 OV5640、HDMI 线和显示器、JTAG 下载器、两根电脑 USB 数据线、原配 12V 电源。

```text
OV5640（镜头朝人） ── P2 / CAMERA
JTAG 下载器 ──灰色排线── J18       下载器 USB ── 电脑 USB
PL UART 数据线 ───────── J23       另一端 ───── 电脑 USB
HDMI OUT ─────────────── 显示器 HDMI 输入
12V 电源 ─────────────── J1
```

逐项核对：

1. OV5640 插到 **P2**，连接器 1 脚对 1 脚，镜头固定在 HDMI 屏幕上方，朝向使用者。镜头不要朝 HDMI 屏幕。
2. HDMI 线接 Z15 的 **HDMI OUT**，另一端接独立显示器。显示器菜单切到这一个 HDMI 输入。
3. JTAG 下载器的灰色排线接 Z15 **J18**。它只负责下载 FPGA 固件。
4. 另一根 USB 数据线从 Z15 **J23 / PL UART** 接电脑。它负责让 `screen_monitor.py` 读状态、取图和发送参数。JTAG 下载器不能代替 J23 串口。
5. **J24** 两个跳线帽按项目接法分别短接 **1–3、2–4**，把 PL UART 接到 USB 串口通路。跳线帽不是插在 J23 上；它们插在板上的 J24 针脚上。
6. 底板 1V1 三针版本的 Bank 跳线 J3、J4 各接 **2–3**。如果实物是六针座，不直接套用这个针号，先按该板修订原理图核对。
7. `BOOT_CFG` 开关 1、2 都拨到 **ON**，使用 JTAG 启动。
8. 最后接原配 12V 电源到 **J1**，打开板卡电源。

## C. 下载固件

1. 打开 Vivado 2023.1，选择 **File → Open Project**。
2. 打开：

   ```text
   D:\fpga\z15_multimodal\local\screen_vivado\z15_screen.xpr
   ```

   旧的 `D:\vivado\project_1.xpr` 是空工程，不用于本次运行。
3. 左侧选择 **PROGRAM AND DEBUG → Open Hardware Manager**。
4. 点 **Open target → Auto Connect**。
5. 在 Hardware 树中选择名称包含 `xc7z015` 的器件，右键点 **Program Device**。
6. `Bitstream file` 选择：

   ```text
   D:\fpga\z15_multimodal\report\screen\z15_screen_top.bit
   ```

   `Debug probes file` 留空，点 **Program**。
7. 等待下载完成，再等 5–10 秒让 OV5640 初始化。HDMI 应出现摄像头灰度预览和 `SETUP ON COMPUTER`。

如果 Hardware Manager 找不到器件，先检查 JTAG USB、灰色排线和 J18；不要把 JTAG 设备的端口当成 PL UART COM 口。

## D. 找到 PL UART 的 COM 口

1. 打开 Windows **设备管理器 → 端口（COM 和 LPT）**。
2. 拔下、插回 **J23 的 USB 数据线**，观察哪一个 COM 口出现或消失，把它记下来。
3. 工具中只选择这个随 J23 变化的端口。不要选择蓝牙链接上的标准串行端口，也不要选择 JTAG 下载器的 USB 项。
4. 如果插拔 J23 没有任何新设备：
   - 确认 J24 是 1–3、2–4；
   - 确认用的是能传数据的 USB 线，不是只能充电的线；
   - 换电脑的独立 USB 口，暂时不要接拓展坞；
   - 在设备管理器检查未知 USB 设备，并安装板卡 USB-UART 所需驱动；
   - 关掉占用该 COM 口的串口助手后再试。

## E. 打开电脑设置窗口

在项目根目录的 PowerShell 输入：

```powershell
cd D:\fpga\z15_multimodal
python tools\screen_monitor.py
```

也可以双击 `tools\start_screen_monitor.bat`。窗口打开后按这个顺序：

1. 点 **刷新**。
2. 选择刚才由 J23 找到的 COM 口。
3. 点 **连接**。
4. 等待状态出现相机 `5640`、就绪 `1`、故障 `0`。未校准时显示“设置、识别无效”是正常的。

窗口显示“未连接”时，问题在 J23 串口或 COM 选择，不在 HDMI 画面。先解决串口，再继续下面的步骤。

## F. 取图并框选两只眼睛

1. 保持使用者正对屏幕坐好，头部先不要移动，点 **取图（约 7 秒）**。这个按钮在电脑设置窗口顶部，不在 HDMI 屏幕上。
2. 等待电脑窗口出现灰度快照。它是用于设置的静态图，不是 HDMI 实时画面。
3. 检查快照中能同时看清两只眼睛、虹膜和眼白。若拍到的是插排、桌面或线缆，先转动摄像头让镜头朝人，再重新取图。
4. 选 **框选眼 1（按画面从左到右）**，在电脑快照上按住鼠标左键拖框住画面左侧眼睛。
5. 选 **框选眼 2（按画面从左到右）**，拖框住画面右侧眼睛。
6. 两个框不能重叠。框内要包含虹膜和一部分眼白，避开眉毛、黑镜框和大片皮肤阴影。
7. 勾选 **阈值预览：红色暗区 / 蓝色亮区**。红色应主要落在虹膜暗区，蓝色应覆盖眼白。必要时调整暗阈值、亮阈值或重新取图。
8. 点 **应用双眼参数**，等待窗口明确显示 **FPGA 已确认两个眼框**。只看到按钮被点击，不代表板卡已经接受参数。
9. 只有眼 1、眼 2 都有效时，**开始 HDMI 三点校准** 才会变为可用。

## G. 校准左、中、右

1. 点 **开始 HDMI 三点校准**。
2. 把视线转回 HDMI 屏幕。屏幕会依次显示左、中、右目标白点。
3. 每个目标先稳定看约 2 秒，再继续盯住白点，直到该阶段自动完成。不要转头追白点。
4. 三个阶段自动切换，不需要在 HDMI 画面上点击。校准完成后进入运行状态。

## H. 验证运行效果

1. 看屏幕左侧目标：HDMI 的 LEFT 框应变绿。
2. 看中间目标：CENTER 框应变绿。回中约 0.35 秒用于释放上一次左右确认。
3. 看右侧目标：RIGHT 框应变绿。
4. 左或右持续约 0.75 秒，电脑窗口日志应出现一次确认事件。持续盯着同一侧不会重复触发。
5. 先回中，再看另一侧，才能测试下一次确认。
6. 闭眼、遮住一只眼、移动头部或处于左右边界时，应显示无效或拒识，不应产生新的确认事件。

## I. 收工和重新运行

- 重新下载、复位或断电后，需要重新打开工具、应用双眼参数并重新做三点校准。
- JTAG 下载是易失配置，本阶段不烧写 Flash，也不需要 SD 卡、PYNQ 或 HWH 文件。
- 结束时先在工具中点 **断开**，再关闭电源和拔线。
- 真实测试数据写入 `report/screen/board_test_template.csv`，不要把仿真截图或仿真结果当作真人准确率。

## 常见现象

| 现象 | 先检查 |
| --- | --- |
| 电脑没有设置窗口 | 在项目根目录运行 `python tools\screen_monitor.py`，不要在 Vivado Tcl Console 中运行 |
| HDMI 无信号 | HDMI OUT、显示器输入、JTAG 下载是否成功 |
| HDMI 有画面但拍不到眼睛 | 摄像头方向、焦点、人与屏幕距离；镜头必须朝人 |
| 设置窗口只有蓝牙 COM | J23 USB 数据线、J24 跳线和 USB-UART 驱动；不要选蓝牙 COM |
| 点击取图后超时 | 复位板卡，检查 P2、J23 和摄像头初始化状态 |
| 应用参数后不确认 | 两个眼框是否重叠、尺寸是否合规、阈值是否合理；必要时复位后重新应用 |
| 校准失败 | 重新取图和应用参数，固定头部，左中右分别看白点 |

## 文件入口

| 用途 | 路径 |
| --- | --- |
| 本清单 | `docs/teammate_runbook.md` |
| Vivado 工程 | `local/screen_vivado/z15_screen.xpr` |
| 下载固件 | `report/screen/z15_screen_top.bit` |
| 电脑设置工具 | `tools/screen_monitor.py` |
| 双击启动工具 | `tools/start_screen_monitor.bat` |
| 详细协议和限制 | `.trellis/spec/hardware/screen-contract.md`、`docs/screen_gaze.md` |
