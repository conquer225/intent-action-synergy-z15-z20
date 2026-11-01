# r8：连续视频与 PL 框暂留

本版针对 r7 板上约 1.6 FPS 的处理节奏，把 HDMI 视频更新从 PS 检测循环中拆开。Haar 模型、人脸/眼框定位、眼内特征、三点校准和方向确认逻辑保持原样。本版没有 NPU，也没有用跟踪代替检测。

## 显示行为

- 摄像头原始图像经独立连续 VDMA 缓存进入 HDMI，PS 算法不再复制整帧来更新显示。
- 人脸框、两个分析框、两个暗部中心分别保存最近一次有效几何位置。检测暂失时保留位置、显示灰色；不会每次失败立即消失。
- 成功检测的新位置按显示帧逐步靠近，每帧移动剩余距离的四分之一，至少移动一个像素，不越过目标。第一次出现或完全过期后的重新捕获直接定位。不是固定延迟数秒再开始移动。
- 默认几何有效期为采样后 1500 ms，随后灰色显示 500 ms，到期隐藏。PS 已花掉的检测时间计入有效期；失败消息不延长旧几何寿命。
- 顶部方向状态与暂留框分开。过期或无效方向不会因为框仍存在而变成有效观察；校准目标继续按原有状态显示。
- `a`、`r`、切固定模式和视频故障会清除旧框。原有按键含义保持。

这些是显示处理，不会改写 EyeTracker 的 ROI、参考值或事件状态。低速方向判定仍受原来 250 ms 运行间隔门限约束；画面流畅不代表方向判定已经加速。

## 上板

使用本发布包的 `build/BOOT.BIN`，只复制该文件到已准备好的 FAT32 SD 卡根目录。先保存当前可用 BOOT.BIN，断电后换卡并按原先已验证的 SD 启动接法上电。新固件包含成对的 PL 和 PS，不能把旧 bit 与新 ELF 混用。

串口 115200、8N1、无流控。预期启动标识：

```text
PS_EYE_AUTO_START r8-live-osd BGR888 1280x720 unchanged r7 gaze + Haar
OV5640 OK
VIDEO_BOOT r8-live-osd ... live=triple-genlock snapshot=independent
VIDEO_READY stage=live-and-snapshot ...
```

识别仍使用 `seq`、`detect_ms`、`period_ms`。另外输出：

| 字段 | 含义 |
| --- | --- |
| `cam_frames` | 预热后摄像头输入 VSYNC 计数，不能单独证明所有帧均成功写入 DDR |
| `hdmi_frames` | PL OSD 输入端的显示 VSYNC 计数，不等于独立的新摄像头帧数 |
| `up_ms` | PS 当前毫秒时钟，配合计数差计算观测频率 |

相邻两条日志的计数差乘 1000，再除以 `up_ms` 差，即对应频率；计数和时间按 32 位无符号回绕处理。显示刷新、相机输入和检测更新要分别统计。

`OSD HARDWARE MISMATCH` 表示 BSP/应用与 PL 不匹配；`OSD PUBLISH FAILED` 表示更新未能在限定时间交接，应用停止新事件。`VIDEO_*` 保留采集、显示状态以及实际失败阶段。

回退文件随包放在 `rollback/r7-video1/BOOT.BIN`。需要回到上一版时断电更换 SD 卡根目录的同名文件，不能混用两版 bit 和 ELF。离线检查结果与 CDC/板级时序边界见 [r8 验证记录](report/live_osd_r8.md)。

## 架构与缓存归属

同一原始 camera native RGB 驱动两个独立 Video-In-to-AXIS 接收器。分析接收器的 TREADY 不回传到视频接收器，两路仍共享 DDR 带宽。

- VDMA0：3 个共享 live buffer，动态写主/读从 genlock，连续采集/显示。
- VDMA1：2 个独立 capture buffer，PS 只切换该通道的停泊地址。确认写入切换后，复制上一完整帧到独立快照，算法全程使用不可变快照。
- PL OSD：位于 Video-Out 与 DVI 之间，图像与同步信号一起延迟一个像素时钟。检测数据没有 OSD 像素。
- PS 通过 AXI-Lite 提交几何/状态。独立 holding bank 在 request/ack 期间保持，视频域在垂直消隐统一采用，避免半帧只更新部分坐标。

DDR 地址延续原预留区：capture `0x02000000`、live `0x03000000`、snapshot `0x04000000`；每帧 2,764,800 字节。

## 重新构建和验证

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\run_live_osd_sim.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\run_host_tests.ps1
python .\tests\run_gaze_parity.py
python .\tools\build_pc_gaze.py
python -m unittest discover -s tests -p 'test_*.py' -v
powershell -NoProfile -ExecutionPolicy Bypass -File .\build\build_hardware.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\build\build_all.ps1
python .\tools\verify_release.py
python .\build\package_release.py
```

Vivado/Vitis 默认安装路径与原版本相同。`video_io.c` 和其测试保留为 r7 协议回归；r8 Makefile 实际编译 `video_live.c`。PC DLL 仍是算法验证工具，并不模拟整条 FPGA 视频链路。

板上验收需确认：遮挡或移出画面时视频继续更新，旧框变灰并最终隐藏；重新进入画面能重新定位；缓慢移动时框逐步跟随；串口计数持续增加且无 VDMA 故障。实际帧率、相机清晰度与识别效果需要实测，不能以 RTL 仿真或实现时序代替。
