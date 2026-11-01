# Z15 PS 自动找脸、双眼定位与三区眼控

2026-09-29 新增 **r8-live-osd**：连续视频与 PS 检测分离，PL 独立叠加可暂留、平滑移动的框。保留当前 r7 识别、模型和校准逻辑。新入口、上板检查和频率字段见 [LIVE_OSD.md](LIVE_OSD.md)。用户已确认前版 r7-video1 恢复出图并认可定位表现；r8 的实际板上帧率与效果仍需验证。以下历史版本说明以本段和 LIVE_OSD 为准。

2026-09-29 视频启动修复 `r7-video1`：针对上板 `OV5640 OK` 后 `VIDEO FAIL rx=00010000 tx=00011000`，修复首帧等待与原厂采集模块多帧预热不匹配的问题。仅首次采集等待放宽到 3 秒，运行时仍为 500 毫秒；启动时验证采集、显示两路实际帧切换，并输出失败阶段。眼控算法仍为 r7。离线回归已通过，用户已确认该修复版 HDMI 恢复出图，见 [视频启动修复记录](report/video_startup_r7_video1.md)。

当前 r7：分析框改用人脸框变换跟随头位，修复眼模型框共同移动可能抵消眼动的问题；保留 r6 的滚动采样、失败诊断和 `t` 续采。电脑测试见 [PC_GAZE.md](PC_GAZE.md)，验证见 [gaze_roi_motion_r7.md](report/gaze_roi_motion_r7.md)。r6 真人校准仍失败，r7 连续效果与 ARM 速度待测试。
没有板卡时，可双击 `start_pc_preview.bat` 打开照片或使用电脑摄像头测试同一份 C 定位模型，操作见 [PC_TEST.md](PC_TEST.md)。此窗口只测试定位，不执行三点眼控校准。

2026-09-28，r4。在 r3 的逐眼累计和暂停续采基础上，扩大模型眼区，并用相邻帧双眼框的共同平移/缩放跟随小幅头动；检测条件和灰度特征门槛保持不变。详见 [r4 验证](report/eye_roi_follow_r4.md)。独立目录 `ps_eye_auto`，旧 `ps_eye` 和此前 r2/r3 发布 ZIP 保持原样。

电脑端三点校准入口为 `start_pc_gaze.bat`，使用与 ARM 相同的新版 C 特征提取，操作见 [PC_GAZE.md](PC_GAZE.md)。

本版把轻量 Haar 人脸和眼睛模型编译进 ARM ELF。启动后先自动找人脸，再在人脸上半部检测两只眼睛，生成左右眼 ROI。按 `c` 后仍使用左、中、右三点校准。校准成功后，看左或右并停留会从 PS 串口输出一次事件；回看中间后才允许下一次事件。

已经完成 PC 测试、ARM 编译和启动包构建；还没有运行本版的实物板卡测量。你提供的三张图片回放中，两张找到双眼，第三张未组成合格眼对而被拒绝。这不是准确率测量，也不能据此承诺真人操作成功率。完整证据见 [verification.md](report/verification.md)。

## 现在画面应当是什么样

HDMI 显示摄像头画面，上面叠加黄色人脸框和两个眼部框。眼部暗区统计通过时眼框为绿色，否则为红色；绿色十字是暗区重心，不是经过精确分割验证的瞳孔中心。画面顶部有左、中、右三个色块，校准阶段或有效注视方向对应的色块变黄。校准时白色目标依次出现在屏幕左、中、右位置。

自动定位只解决“到哪里分析眼睛”。眼动仍用眼内暗区的相对位置估计，眼镜反光、低照度、眨眼、头动都可能使它失效。眼对丢失或位置偏移时暂停，校准保留；恢复原位置和稳定定位后继续。校准前和运行中，人脸框的小幅平移/缩放会更新分析 ROI；超出跟随范围时暂停，避免把眼内运动当成头动。更换坐姿请按 `r` 清除后重做。它不识别身份，不支持多人同时眼控，也不支持自由头动下的连续屏幕坐标。

摄像头输入为 1280×720 BGR888。识别人脸时内部缩至 320×180 灰度图；识别眼睛时从原始帧重新取人脸上半部。HDMI 保留相机原始颜色。r8 连续显示摄像头图像，不再等待每次 PS 检测完成；几何框按独立策略更新。显示、摄像头输入和检测更新频率分别统计，实际表现以上板日志为准。

## 第一次上板：用 SD 卡

1. 解压完整工程。打开本目录的 `build` 文件夹，找到 **BOOT.BIN**。此文件已经包含 FSBL、PL bitstream 和 PS ELF；不需要另放模型、Linux 镜像或照片。
2. 准备已有 FAT32 分区的 SD 卡，先备份卡内已有 `BOOT.BIN`。只把本版 `build/BOOT.BIN` 复制到卡根目录。不要复制整个 build 文件夹作为启动文件。
3. 板卡断电。OV5640 保持连接 **P2**，显示器连接 **HDMI OUT**，保留你此前已经验证出图的摄像头和电压跳线接法。插入 SD 卡。
4. 把板上 **BOOT_CFG 两位都拨到 OFF**，这是此 Z15 的 SD 启动模式。JTAG 模式则是两位都 ON。拨码在重新上电后生效。
5. 电脑 USB 连接板上丝印 **PS_UART** 的串口。这里使用 PS UART0，MIO14/15，**115200、8 数据位、无校验、1 停止位、无流控**。旧 PL 工程的 J23/PL_UART 和 `screen_monitor.py` 不是本版的控制入口。
6. Windows 右键“开始”→“设备管理器”→展开“端口（COM 和 LPT）”。拔插 PS_UART USB，记录新增端口号，例如 COM6。关闭占用这个端口的其他串口软件。
7. 在工程文件夹空白处右键→“在终端中打开”，运行下面命令。将 COM6 换成实际端口。窗口出现 Connected 后给板卡上电。

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\serial_console.ps1 -Port COM6
   ```

8. 串口预期依次出现以下内容。HDMI 应显示相机画面；随后每秒左右输出一行 `PS_AUTO` 状态。启动代码里没有模拟这些成功信息，只有对应初始化返回成功才会打印。

   ```text
   PS_EYE_AUTO_START r8-live-osd BGR888 1280x720 unchanged r7 gaze + Haar
   OV5640 OK
   VIDEO_BOOT r8-live-osd startup_ms=3000 runtime_ms=500 live=triple-genlock snapshot=independent
   VIDEO_INIT live-display-configured; waiting-for-camera-frames
   VIDEO_READY stage=live-and-snapshot ...
   VDMA OK / HDMI STARTED
   AUTO default. Commands: c=calibrate, t=retry failed point, r=clear, p=status, a=auto reacquire, m=fixed ROI
   ```

串口脚本运行时直接按英文字母，不用回车；按 `q` 退出。板上完整输出自动保存到 `report/board_日期_时间.txt`。也可以用已有串口助手，选择上面的参数，按文本/ASCII 发送 `c`、`p` 等字符，关闭十六进制发送。

## 校准和实际操作

1. 摄像头固定在显示器上方，对准脸。先正视屏幕中间，保持头部位置。等黄色脸框和两只眼框落到正确位置。串口应有 `pair=1 stable=2` 或 `stable=3`，并且至少一眼有效（`eye_valid=1/1`、`1/0` 或 `0/1`）。
2. 在串口终端按 `c`。出现 `CAL LEFT`，看 HDMI 左边的白色目标，头保持不动。不要按固定秒数自行切换。
3. 等白点移到中间且出现 `CAL CENTER`，转动眼睛看中间；随后按 `CAL RIGHT` 看右边。白点横向在 8%、50%、92%，高度为屏幕顶部下方 18%。每阶段先累计约 2 秒有效等待，再分别为每眼收集 16 个样本；单眼暗部暂失时另一眼可继续采样，不设 15 秒整轮超时。三点参考无法分开或顺序不单调仍会报 `CAL FAILED`。
4. 出现 `CAL OK`、`cal=7 stage=0`，才表示三点数据有效。看左或右时，对应顶部色块应变黄；连续保持至少 750 ms 后输出 `EYE_EVENT ... direction=LEFT` 或 `RIGHT`。离散采样会使实际等待时间更长。
5. 一直看同一侧不会反复输出。回看中间并稳定至少 350 ms，再看一侧，才产生下一次事件。这里输出串口事件，没有接入电机或灵巧手。
6. 眼对丢失、单眼暗部无效或位置偏移时，保持看当前白点并恢复原坐姿，无需重新按 `c`。UART 的 `cal_samples` 显示逐眼计数，`pause` 显示暂停原因。校准前和运行中，人脸框的小幅平移/缩放会投影到当前 ROI；超过约 0.75–1.33 倍尺度、脸部几何不一致或超出画面时暂停，避免把眼内运动当成头动。更换坐姿请按 `r` 清除后重做。

| 按键 | 程序反应 | 适用情况 |
| --- | --- | --- |
| `p` | 立即打印状态 | 保存故障证据 |
| `c` | 开始左→中→右校准 | 双眼定位稳定且至少一眼暗部有效后 |
| `t` | 从失败点重新采样，保留此前参考 | 校准失败且原坐姿定位恢复后；`cal_error/eye/retry/gap/noise` 显示原因 |
| `a` | 清校准，重新自动找脸和双眼 | 重新定位 |
| `r` | 清校准，保留当前模式 | 重做三点数据 |
| `m` | 切到预设固定眼框并清校准 | 仅调试对照，不等于旧版固件 |
| `q` | 关闭电脑串口脚本 | 不会让板卡停机 |

左右眼名称按摄像头画面横坐标从小到大定义，不是使用者的解剖左右。三点方向由你看屏幕目标的顺序建立，因此允许摄像头画面镜像。

## 看日志判断停在哪里

| 现象 | 含义与下一步 |
| --- | --- |
| 没有任何串口输出 | 核对 PS_UART 的 COM、115200、BOOT_CFG、卡根目录 BOOT.BIN 和供电；用下方 JTAG 路径区分 SD 启动问题 |
| `OV5640 FAIL` | 摄像头初始化没有通过；断电检查 P2、排线方向、电压及模组 |
| `VIDEO_WAIT stage=rx-prime-1` | 正在等待摄像头首帧；最多等待 3 秒，不代表已失败 |
| `VIDEO_TIMEOUT stage=rx-prime-1` / `rx-prime-0` | 采集端未完成要求的帧切换；保留整段启动日志 |
| `VIDEO_TIMEOUT stage=live-prime` | 连续视频读写地址或显示 VSYNC 未推进；保留整段启动日志 |
| `VIDEO_INIT_FAIL` / `VIDEO_FAULT` / `VIDEO FAIL` | 初始化 API、VDMA 故障或帧切换失败；保存 `stage/rc/elapsed_ms/rx/tx/live_rx/cam_frames/hdmi_frames`，不要只截最后一行 |
| `pair=0` | 模型未找到合格眼对，当前暂停采样；已有校准保留，先调整正脸角度、距离、清晰度和面部照明 |
| `pair=1 eye_valid=0/0` 或 `1/0` | 已有模型眼框，但暗区特征不合格；检查框内反光、睫毛/眉毛、欠曝 |
| `CAL BLOCKED` | 当前双眼不稳定或特征无效，程序没有接受校准 |
| `CAL FAILED` | 三个方向差别过小或参考顺序不单调；保持头位重新校准 |
| `period_ms` 超过 250，或 `detect_ms` 超过 1000 | 触发保留的运行间隔门限或检测超时；动作不会正常累计。连续视频不会改变这些算法门限 |
| `VIDEO LOST/ERROR` / `DISPLAY FAILED` | 程序停止输出新动作，需重新启动；画面可能保留最后一帧 |
| `valid=0 dir=INVALID` | 当前不能确定注视方向，不能据此执行动作 |

`pause` 是位掩码：1=画面左眼无效，2=右眼无效，4=等待双眼定位，8=慢帧，16=位置偏移；1 和 2 可组合为 3。

`faces` 是模型候选数，不是身份数量；`pair` 是合格双眼对；`cal` 是三点完成位掩码，只有 7 才全部完成。`quality` 是对比度等启发式分数，不是识别概率。`seq` 是 PS 实际取帧计数，无法据此称摄像头无丢帧。程序每次记录真实检测时间 `detect_ms` 和两次取帧间隔 `period_ms`，PC 回放时间不能代替这两个板上数值。

## JTAG 启动：不使用 SD 卡

1. 断电，BOOT_CFG 两位都 ON。接好板上 JTAG 下载器 USB、PS_UART USB、P2 摄像头和 HDMI OUT，然后上电。
2. 在 Vivado 2023.1 点击“Open Hardware Manager”→“Open Target”→“Auto Connect”，确认能看到 Zynq 器件。
3. 保持 Hardware Manager 打开。在解压后的本目录打开终端，运行：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\build\run_jtag.ps1
   ```

   如果 Vitis 安装路径不同，增加 `-VitisRoot '你的路径/Vitis/2023.1'`。
4. 脚本会系统复位、下载本版 bit、执行 PS 初始化、下载 ELF 并启动 ARM。PS_UART 的显示和校准步骤与 SD 启动相同。只在 Vivado 点“Program Device”下载 bit 不会自动运行 PS 算法。

## 源码、重新构建与灰度选择

| 路径 | 内容 |
| --- | --- |
| `src/app/main.c` | 找脸、稳定性、丢失暂停、串口与帧处理循环 |
| `src/app/haar.c`、`auto_face.c` | Haar 推理与真正的眼睛检测、自动 ROI |
| `src/app/eye_tracker.c` | 原暗区方法的三点校准、拒识、停留和中间重置 |
| `src/app/video_live.c`、`live_osd.c` | 连续视频、独立检测快照与 PL OSD 数据提交 |
| `src/app/video_io.c` | 保留的 r7 视频实现，不参与 r8 固件编译 |
| `model/` | 三个 OpenCV 4.10.0 XML 模型、许可和 C 常量生成器 |
| `hardware/source/` | 原厂相机/HDMI BD、IP 和 P2 约束副本 |
| `hardware/ps_eye_auto.bit`、`.xsa` | 本版支持 SD0 的硬件输出 |
| `hardware/fsbl.elf`、`ps7_init.tcl` | 本版 FSBL 与 JTAG PS 初始化 |
| `build/ps_eye_auto.elf`、`BOOT.BIN` | PS 应用与 SD 启动包 |
| `bsp/` | Vivado/Vitis 2023.1 生成的 standalone 头文件、库 |
| `tests/`、`report/` | PC 测试、离线核对及实现报告 |

模型本来按灰度特征训练，运行也必须使用同样的输入含义。灰度相对 RGB888 减少工作图的存储量，适合当前 Cortex-A9 上的 Haar 算法；这不表示“灰度一定比彩色准”。换用依赖 RGB 的神经网络时，应按它的训练预处理输入。当前不为检测另引入 OpenCV、Python、Linux 或 SD 模型加载到 ARM 上。

已有预编译文件，首次验证无需重新构建。重新编译软件需要 Vitis/Vivado 2023.1 与 GNU Make；默认 Make 在 `C:/mingw64/mingw64/bin/mingw32-make.exe`，可以传参修改：

```powershell
python .\model\generate_haar_model.py
powershell -ExecutionPolicy Bypass -File .\build\build_all.ps1
```

重建完整硬件和 BSP：

```powershell
powershell -ExecutionPolicy Bypass -File .\build\build_hardware.ps1
powershell -ExecutionPolicy Bypass -File .\build\build_all.ps1
```

前一条会在本目录生成 `hardware/vivado_live_osd/ps_eye_auto.xpr`，可在 Vivado“Open Project”打开。重跑会保留先前 Vitis workspace 为带时间后缀的备份。发布包不包含庞大的实现临时目录。

PC 测试使用 MinGW GCC；模型参考测试另需 `tests/requirements.txt` 中的 Python 库，只安装在电脑上：

```powershell
powershell -ExecutionPolicy Bypass -File .\tests\run_host_tests.ps1
python -m pip install -r .\tests\requirements.txt
python .\tests\test_haar_reference.py
```

带真人图片的回放通过 `tests/replay.py` 的私有 manifest 输入。发布包不含你的照片；具体数据结构见该脚本开头。原版兼容性、时序与上板待测项目见 [验证报告](report/verification.md)，工作清单见 [WORKLIST.md](WORKLIST.md)。
