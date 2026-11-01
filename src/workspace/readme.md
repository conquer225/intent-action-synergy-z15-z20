# Z15 多模态交互控制平台

2026-10-25 修复合并完整包：[GuardianLoop_Submission_20261025.zip](GuardianLoop_Submission_20261025.zip)。收录此前板端 PS_KEY0、灵巧手、音频频谱、相机进入保护及视频缓存修复，51 个安装载荷与最后一次视频修复上板版本一致。使用与安装见 [合并版说明](integrations/vision_demo/RELEASE_20261025.md)，独立解压检查见 [发布核验](report/release_20261025/verification.json)。旧包保留。

2026-10-21 当前“我们意念合一”展示版已在 Z15 运行。灵巧手本轮开合已获现场确认；PS_KEY0 的 GPIO 中断修复已安装，等待真人标定复测，图像帧率与间歇黑屏继续排查。见 [当前状态](docs/status.md)和[按键修复](integrations/vision_demo/report/commissioning_20261021/ps_key0_recovery.md)。下方独立版本入口与验收记录保留。

2026-10-14 当前完整整合入口为 **我们意念合一**：[工程与启动说明](multimodal/README.md)。接入用户确认异机实物验收的 GuardianLoop 原包与 S3/C3 灵巧手、倒立摆工程，保留独立眼控、SSVEP、电极与MPU输入。软件、固件构建和新overlay离线验证见 [记录](multimodal/report/verification.md)；新增整合的同机实物验收待设备接回。以下版本入口和历史证据保留。

2026-09-30 新增 **r9 无线脸部 ROI / 瞳孔回传眼控**：[运行说明](ps_eye_net/README.md)。保留用户提供的 PYNQ/Linux 无线启动环境，USB Wi-Fi 将板端脸部 ROI 发给电脑计算双眼瞳孔，摄像头坐标回传后由 PS 完成校准、方向与停留事件。独立 overlay、ARM Linux 库、电脑工具和完整包已生成；21 项网络/控制测试、C 回归、RTL 和配套载荷/时序核验通过。r8 原文件哈希保持一致；r9 USB 无线实板链路与真人效果待测，见 [验证记录](ps_eye_net/report/verification.md)。不要将备用有线裸机 `ps_eye_net/build/BOOT.BIN` 覆盖到现有无线 Linux 卡。

2026-09-29 当前 PS 版本为 **r8-live-osd**：[使用与上板检查](ps_eye_auto/LIVE_OSD.md)。视频由独立 VDMA 连续显示，PL 叠加可暂留、平滑移动的框；保留 r7 定位、特征与校准算法。配套 BOOT 和完整包已生成，通过软件/RTL 测试、实现时序与载荷校验。用户已确认前版 r7-video1 恢复出图并认可定位表现；r8 尚未上板测量。

2026-09-29 上板视频启动排查：已生成 `r7-video1`，修复可复现的首帧预热超时并补充分步诊断；修复版 HDMI 出图仍待实板确认。对话总结、原因边界和新包复测说明见 [PS 上板黑屏排查记录](docs/ps_video_startup_session_20260929.md)。

2026-09-28 新增独立 PS 自动找脸版本：[ps_eye_auto/README.md](ps_eye_auto/README.md)。嵌入人脸/眼睛 Haar 模型，自动眼框接三点校准，带 SD/JTAG 启动文件与逐步操作说明；当前为上板验证候选，真实帧率和眼控表现待测。此前固定眼框的 `ps_eye` 原样保留。下文为 PL v2 的历史入口，不要混用其 PL UART 工具与新版 PS UART。

当前 r7 修复分析框随眼检测框共同移动而抵消眼动的问题，改用人脸框变换跟随头位。用户提供的 r6 三轮校准仍失败；已补回归并重建 PC DLL、PS ELF/BOOT，见 [r7 报告](ps_eye_auto/report/gaze_roi_motion_r7.md)。r7 真人效果待测。

电脑端三点眼动测试：[ps_eye_auto/PC_GAZE.md](ps_eye_auto/PC_GAZE.md)，双击 `ps_eye_auto/start_pc_gaze.bat`。它调用与 ARM 相同的定位和 `eye_tracker.c` 方向算法，用于在没有 Z15 时验证左、中、右特征；不代表 ARM 性能或真实摄像头链路结果。

更新：2026-09-23。AMD 自主选题初级组，正点原子 Z15（xc7z015clg485-2），Vivado 2023.1。

当前入口是 **v2 屏幕三分区眼控**：OV5640 接 P2，固定在 HDMI 屏幕上方面向使用者。初次在电脑上框选双眼、调阈值，然后跟随 HDMI 白点自动校准左、中、右。FPGA 识别两眼相对暗/亮区位置，屏幕高亮注视区域，左/右停留确认并从 PL UART 输出。固定头位使用；不是连续注视坐标或自动人脸跟踪。

源码、电脑工具、模块与整链路仿真、综合、布局布线和 bitstream 已完成。2026-09-25 用户照片已确认 HDMI 出图、串口状态和人脸快照；实拍暴露明暗阈值分割及背景误检问题，真人三区域识别尚未验收，见 [实拍问题分析](docs/eye_failure_analysis_20260925.md)。真实准确率、适用距离和显示器兼容范围仍未测量。

## 使用入口

| 内容 | 路径 |
| --- | --- |
| 队友从解压到运行的完整清单 | [teammate_runbook.md](docs/teammate_runbook.md) |
| 换电脑后眼框无法应用 / 参数诊断版 r2 | [roi_update_troubleshooting.md](docs/roi_update_troubleshooting.md) |
| 查看瞳孔/眼白灰度并保存原图 | [gray_inspection.md](docs/gray_inspection.md) |
| 接线、点击、双眼设置、校准和测试 | [新版详细使用说明](docs/screen_gaze.md) |
| 可下载固件 | [z15_screen_top.bit](report/screen/z15_screen_top.bit) |
| Vivado 工程 | `local/screen_vivado/z15_screen.xpr`，ZIP 内含相对路径工程 |
| 电脑工具 | [screen_monitor.py](tools/screen_monitor.py) |
| 验证结果与限制 | [verification.md](report/screen/verification.md) |
| 2024 易灵思作品及论文 | [eye_research.md](docs/eye_research.md) |
| 第三方源码来源 | [THIRD_PARTY.md](THIRD_PARTY.md) |

![HDMI 运行画面，RTL 仿真示例](report/screen/hdmi_run.png)

```powershell
python -m pip install -r tools/requirements.txt
python tools/screen_monitor.py
```

也可以双击 `tools/start_screen_monitor.bat` 打开电脑设置窗口。这个窗口不是 Vivado，也不在 HDMI 显示器里；当前标题为 `Z15 屏幕三分区眼控 · 参数诊断版 2026.09.25-r2`，用于选择 J23 的 PL UART、取图、框选双眼和启动校准。最新电脑工具单独打包为 `D:/fpga/Z15_Screen_PC_20260925_r2.zip`，含灰度检查、旧眼框冲突恢复和诊断日志；无需为这次更新重新构建固件。

重新构建及校验：

```powershell
& 'D:/vivado/Vivado/2023.1/bin/vivado.bat' -mode batch -source build/screen/build.tcl
& ./build/screen/test.ps1
& ./build/screen/test_pipeline.ps1
python -m unittest discover -s sim/screen -p 'test_*.py' -v
python tools/screen_manifest.py
python tools/package_screen.py
```

源码包位于维护根目录上一级 `D:/fpga/Z15_Screen_Gaze_v2.zip`。包括源码、约束、PC 工具、测试、报告、固件、操作说明和 Trellis 记录；不包括原厂整盘、论文 PDF 或大型实现 checkpoint。

## 长期工程与历史版本

正式维护根目录 `D:/fpga/z15_multimodal`，Trellis 开发者 sds，Claude + Codex。`src/screen` 是新版 RTL，`sim/screen` 是测试，`build/screen` 是构建脚本，`report/screen` 是证据。复用 `src/eye` 中 UART、SCCB、帧缓存及跨时钟握手模块；`board/constraints` 是唯一引脚和时序约束。

v1 单眼实验版保留在 `src/eye`、`report/eye` 和 `D:/fpga/Z15_Eye_Control_v1.zip`；其使用记录见 [eye_control.md](docs/eye_control.md)。当前屏幕三分区任务使用 v2，请配套使用新固件和电脑工具。

脑电、肌电、灵巧手、倒立摆、音乐联动及 PS 模式管理仍是后续规划。当前独立 PL 眼控不依赖 PS、DDR、PYNQ，没有 HWH。

| 文档 | 内容 |
| --- | --- |
| [完整项目思路](docs/project_overview.md) | 原多模态方案及范围 |
| [比赛要求](docs/competition.md) | 组别、评分、工具与材料 |
| [现状](docs/status.md) | 已实现、已验证和待实测 |
| [架构](docs/architecture.md) | 当前实装与后续边界 |
| [参考资料](docs/references.md) | 厂商资料、源码和研究索引 |
| [路线](docs/roadmap.md) | 长期模块验收顺序 |
| [决策](docs/decisions.md) | 硬件、协议与未决事项 |
| [维护方式](docs/maintenance.md) | Trellis、Git、日志 |

外部原工程 `D:/vivado/project_1.xpr` 与原始资料保持原样。最初的 `Z15_Multimodal_Embedded_Skeleton_v1.zip` 有 501 个空文件，只是早期骨架，不能运行。
