# 当前状态核验

2026-10-25 完整修复包已合并：`GuardianLoop_Submission_20261025.zip`，142,366,819 字节，SHA-256 `c56138c4ec3160e39f49a864311eeb7fe1db4852bd1c755e8b448d9ba1a081b0`。独立解压后 85 项模块、原六组回归、BLE Python/C++ 与射频检查通过；旧版及当前 DeviceLink 基线均通过实际 bundle 的 57 项临时事务、56 项启动摘要及严格回退，未知版本仍拒绝。修正了新 EEG 基础更新与展示安装基线的精确摘要配套。51 个运行载荷与最后一次视频修复上板版本一致；2,657 项原归档逐字节保留，私有 WLAN 密码字面值扫描无命中。未操作板卡；Tobii 帧率和 OV5640 偶发启动底层原因仍待实机。见 [使用与安装](../integrations/vision_demo/RELEASE_20261025.md)和[检查结果](../report/release_20261025/verification.json)。

2026-10-21 多媒体视频黑屏修复：实际异常为预载视频 `local_index` 未初始化，发生于脑电页已累计显示帧后首次进入同一视频。生成运行文件在取得缓存块时初始化索引；84项模块、原六组及板端实际代码测试通过，51文件／148摘要匹配。实板从脑电页切入sd02连续播放约12秒，帧704→813后正常回主页；用户确认画面正常、没有黑屏。手机控制台“启动／恢复 HDMI 主页”可用于此类进程退出后的恢复。见 [修复记录](../integrations/vision_demo/report/commissioning_20261021/video_cursor_recovery.md)。

2026-10-21 高频频谱密度与黑屏：按用户圈图，将高频密集折线改为64段对数频率峰值柱，实际PL FFT活动帧截图已核对。黑屏原因为OV5640采集启动失败使全局HDMI会话退出；已恢复主页，并新增安全清理完成后的相机进入失败返回主界面逻辑。83项模块、原六组回归及17项ARM相关测试通过，51发布文件／148摘要匹配。用户随后确认相机正常显示；底层偶发启动触发条件仍待连续切换诊断。见 [本次记录](../integrations/vision_demo/report/commissioning_20261021/spectrum_density_recovery.md)。

2026-10-21 音乐音频页布局已更新到 Z15：按用户最终指明的左侧频谱拥挤问题，主频谱扩大到整行 1166 像素，瀑布共用频率轴，双声道与三段能量横排。78 项模块测试通过，另三页同输入 PNG 字节一致；50 文件／147 项摘要及模型核验通过，主页已恢复。见 [音频布局记录](../integrations/vision_demo/report/commissioning_20261021/audio_layout.md)。

2026-10-21 PS_KEY0 修复已部署：板端确认摄像头裸机 GPIO 初始化屏蔽了 Linux 按键中断。摄像头适配层已隔离中断寄存器写入，并恢复当前 MIO11/12 中断；78 项模块测试、原按键与 DMA 检查通过，50 个发布文件／147 项启动摘要匹配。用户随后确认按键入口恢复；图像帧率与间歇黑屏仍待处理。见 [按键修复记录](../integrations/vision_demo/report/commissioning_20261021/ps_key0_recovery.md)。以下记录保留各历史版本当时状态。

2026-10-20 脑电热力图修订：按用户要求保留 HDMI／PL_KEY1 切页，网页四页是同一套被动画面。疲劳与情绪页放大八通道波形，增加时频能量、20 维特征与五频段六通道对数协方差热力图；脑电全景同步减少文字。71 项模块、原六组回归、27 组浏览器与 WAV 检查通过；独立包 55 文件安装／54 项启动摘要、严格回退通过，原包 2,657 项归档逐字节保持。新交付 GuardianLoop_Submission_20261020_r2.zip，未部署到板端。见 [修订检查](../integrations/vision_demo/report/heatmap/verification.md)。

2026-10-20 展示版交付：全部当前 HDMI、眼控菜单、手机控制台、媒体、脑电全景与四页统一暖金主题，脑电默认载入真实 LEMON 记录，开发提示进入技术说明。68 项模块、原六组回归、27 组浏览器布局、实际 WAV 解码和跨页暂停恢复检查通过；独立包 54 文件事务／53 项启动摘要、严格回退通过，2,657 项原工程归档内容保持。交付 GuardianLoop_Submission_20261020.zip；板端未部署，听音、流畅度与共存实测待接板。见 [交付检查](../integrations/vision_demo/report/presentation_verification_20261020.md)。

2026-10-20 PL_KEY1 四页候选完成离线交付检查：疲劳、情绪、脑电音乐联动、音乐音频分析已接入同一 HDMI 所有者。新增 FFT1024 与连续图像合并布局布线通过，WNS +0.136 ns、WHS +0.034 ns；真实 LEMON 八通道校准前段和三分钟回放已调用原模型处理。默认实时、人工回放；尚未部署或验收实际听音与播放同步。63 项模块测试、FFT 七组 RTL 事务／3,591 个复数频点、原六组回归及 12 组浏览器布局检查通过；独立解压 623 文件，40 文件临时安装／39 项启动摘要及严格回退通过。交付 GuardianLoop_Signals_20261020.zip，未部署。见 [四页入口](../integrations/vision_demo/SIGNALS.md) 和 [检查记录](../integrations/vision_demo/report/signal_verification_20261020.md)。

2026-10-19 流式候选自检：修复模式回执超时、独立 HDMI 停滞检测及首次缓存初始化失败释放，收紧 CPU 暂停验收，恢复工作区仿真错误检查。图像模块 38 项测试和原六组回归通过；修订包为 GuardianLoop_Vision_Stream_20261019_r2.zip，保持未部署状态。见 [自检报告](../integrations/vision_demo/report/self_audit_20261019.md)。

2026-10-19 图像流式候选离线检查通过：首版 OV5640 模式用户确认可显示和切换，但帧率与观感未通过验收。新版改用连续 VDMA 三缓冲、1280×720 PL 像素滤镜，33 项软件、五组 RTL（含 1,843,200 像素）、原六组回归及独立解压安装/回退检查通过；WNS +0.165 ns、WHS +0.009 ns，Critical CDC 清除。候选包 GuardianLoop_Vision_Stream_20261019.zip 已生成，首版部署保留。用户当前不便接板，流式版尚未部署，无实机帧率结论。见 [修订记录](../integrations/vision_demo/report/streaming_revision.md)。

2026-10-19 眼控调试保持：用户实测启用后遇到显示/眼控租约过期，随后明确要求关闭续约以便单人调试。已安装 debug_hold=true，页面标注“调试保持”；视线移开和显示续约超时不自动停用，暂停、切页、停止及网络断开仍撤销控制。真实中立测试 1201ms 无显示续约仍保持启用，手动停止成功，新菜单已运行且未启用机构。更新后需重新标定并复测真人动作。见 [调试保持记录](../report/commissioning_20261019/eye_debug_hold.md)。

2026-10-19 Z15 部署：眼控设备菜单与脑电演示统一更新已安装，23 个事务文件、58 个发布文件和 107 项启动摘要匹配，正式启动自检重新通过。原显示会话正常清理后重开，主页已有“设备与方向”，设备配置指向 S3 192.168.50.45:9000，等待注视启用；脑电页面和只读接口 HTTP 200。备份及回退路径见 [部署记录](../report/commissioning_20261019/eye_eeg_deployment.md)。真人眼控联动与脑电佩戴识别待验收。

2026-10-19 灵巧手实测：Z15 经原 Wi-Fi/S3 TCP9000 和 RF 手端完成张开、闭合、再张开，命令回执及动作期间 RF/执行端反馈正常；用户现场确认闭合、重新张开无卡顿。测试结束恢复原 AUTO 模式并停用，倒立摆全程保持停用；未重烧或修改校准。见 [开合实测记录](../report/commissioning_20261019/hand_motion_acceptance.md)。

2026-10-19 后续机械测试：用户已现场确认左右短动作方向正确并停住；每次为单条命令后停用。约 0.8 秒启动停止检查观察到启摆动作；随后用户授权最多 5 秒检查，控制器从约 1.24 秒起持续回报平衡状态至约 5.03 秒，主动停止后回到 state=0、enabled=false。用户随后确认成功立起、保持了一段时间并停止，本轮短时实机检查通过；未改固件或参数。长时间稳定性、物理蓝牙断连、冷启动及真人眼控联动待验收。见 [机械测试记录](../report/commissioning_20261019/pendulum_motion_acceptance.md)。

2026-10-19 蓝牙整链路实测：修复 Arduino-ESP32 3.3.11 将 MTU EALREADY 当作连接失败并遗留占用句柄的问题，兼容处理仅作用于私有构建副本。S3 app0 写入校验通过；Z15 Wi-Fi → S3 TCP9000 → DX-BT24 → STM32 的状态、中立确认、停止/禁用/重新启用、主动断开及来源超时检查通过。30 秒连续查询收到 354 个回执、298 帧遥测，全部状态采样保持 BLE 已连接、STM32 新鲜、停止且禁用。没有发送启动、左右或手端动作；结束恢复倒立摆原 emg 模式并禁用。C3 保留停用，STM32/Nano/PL/Z15 运行文件未重刷，机械动作、蓝牙物理断连与冷启动待验收。见 [实测报告](../integrations/pendulum_ble/report/verification.md)，新包 GuardianLoop_BLE_Pendulum_20261019.zip。

2026-10-18 蓝牙替代链路：用户要求 C3 保留停用，采用 Z15 原 Wi-Fi → S3 TCP9000 → DX-BT24 BLE → STM32。隔离 S3 蓝牙版已通过会话行为检查和构建，镜像 1,242,496 字节；COM27 app0 烧录及写入校验成功。重启后 S3 接入 Z15 热点取得 192.168.50.45，12 秒观察 pend_enabled=0、poses=1、emg_gaps=0，未见重启错误。手端及原协议文件保持摘要一致，无 STM32/Nano/PL 或 Z15 运行文件更新。用户随后要求断电，完整蓝牙中继、实际动作与冷启动明天验收。此前独立 DX-BT24 双向 60/60 帧和 STM32 被动 125 帧已通过，不能替代新中继验收。见 [蓝牙交付入口](../integrations/pendulum_ble/README.md)。

2026-10-18 设备通信实测：Z15 COM18、S3 COM27 可用，RTL8188EUS 识别正常。用户明确最终使用 Z15 USB 无线网卡，网线仅调试。C3 后续无指示灯、无 USB 枚举且热点不可见；暂时由 Z15 建立设备热点，真实 S3 接入后 38/38 条只读协议请求收到回执、30 帧遥测，路由确认为 wlan0。原热点和采集服务已恢复，无机构动作或固件修改。C3 最终拓扑、手端持续就绪及机械验收待继续，见 [现场记录](../report/commissioning_20261018/README.md)。

2026-10-18 脑电演示页：新增 `/eeg-demo`，展示真实八通道遥测、滤波、现有特征、疲劳与情绪，支持本机限时记录和人工历史回放。发布摘要与回退成套处理。165 项计数测试、原手机断言组与三种尺寸浏览器检查通过，Windows 跳过一项 termios 测试；设备验收待连接。见 [演示更新](../integrations/eeg_demo/README.md)。

2026-10-18 眼控设备接入：以用户新提供的 GuardianLoop_team_20261017_03 包重新实现灵巧手开合、倒立摆平衡启停与左右短动作，入口为 [本次更新](../integrations/eye_c3/README.md)。旧 multimodal 整合版未用于本次实现。沿用 C3 局域网与 S3 TCP 9000，Z15 网口需桥接进入该网络；新增软件与原功能回归、可回退安装和源码摘要分别记录。实际部署、真人眼控与机械验收待设备。

2026-10-05 Tobii 实时距离：按用户要求增加位置检查页，连接后先显示距离与眼部状态，再按 PS_KEY0 开始三点。三点、选区、菜单与视频保留约半秒刷新的距离，一位小数、缺失或过期显示未知；40～43 cm仅为旧可用轮参考。75项本机、33项ARM通过，实板位置页读数变化及HDMI持续输出已确认。用户多轮失败的有效样本不足或三点抖动已记录，调整位置后反馈本轮恢复可用；未量化准确率，未放宽原算法门槛。见 [实时距离记录](../ps_tobii/report/distance_display_1005.md)。

2026-10-05 Tobii 重标定修复：用户确认只需能重新标定。已补菜单、视频及暂停状态的 PS_KEY0 入口，停媒体并等旧采样进程退出后再开始，PS_KEY1 可取消，标定算法不变。67项本机、21项ARM检查通过，修复已部署，当前准备页及HDMI持续输出已确认。复位没有丢文件，SD上288项完整素材哈希正确；启动仍为手动。两轮真人标定、准确性和实际听音待测。见 [修复记录](../ps_tobii/report/recalibration_1005.md)。

2026-10-05 Tobii 离线媒体首版：复用已获用户确认的三点方向标定和停留选区，增加句子发声、音乐控制及无声视频。60项本机、14项ARM新增测试通过，六句/三首歌/两段视频素材已生成。实板10.2秒视频用时10.251秒，呈现97帧、跳过5帧，HDMI无报错；原内核缺少USB音频，已编译并成功加载匹配模块。没有声卡，实际听音未验收；完整192MB素材需复制更新包，真人新菜单与冷启动仍待测。见 [使用说明](../ps_tobii/LOCAL_MEDIA.md) 和 [检查记录](../ps_tobii/report/local_media_verification.md)。

2026-09-30 PS r9 无线版：已实现 OV5640 全脸 ROI → USB Wi-Fi → 电脑双眼瞳孔 → 摄像头坐标回传 → PS 校准/停留事件/HDMI。主链路运行在用户提供的 PYNQ/Linux 环境，动态加载配套 bit/hwh；帧缓存使用五块 PYNQ CMA 分配，退出先停 DMA。21 项 Python 网络/眼控/内存/Tk 检查、8 组 C 回归、1363201 像素 RTL 仿真、ARM Linux hard-float 库及裸机备用固件编译通过，WNS +0.746 ns、WHS +0.048 ns。51 项原 r8 文件哈希未变。USB 网卡型号/驱动、现有 rootfs、上板吞吐和真人校准效果尚未实测；参考启动文件不包含 rootfs。交付入口 [ps_eye_net/README.md](../ps_eye_net/README.md)，检查记录 [verification.md](../ps_eye_net/report/verification.md)。

2026-09-29 PS r8-live-osd：视频与检测分离，新增独立分析 VDMA 和 PL OSD 暂留/平滑，10 个识别及模型源文件哈希保持不变。912 帧/81 字段一致性、34 项 Python、C host、RTL 像素对齐与过期检查通过；WNS +0.450 ns、WHS +0.036 ns，BOOT/XSA/ELF/FSBL 载荷配套校验通过。源码、回退 BOOT 与完整发布包已整理。没有自动下载或复位板卡，实际帧率与效果待测。用户已确认前版 r7-video1 出图且定位表现不错；以下更早的待测状态保留为历史记录。见 [r8 验证记录](../ps_eye_auto/report/live_osd_r8.md)。

2026-09-29 PS 视频启动排查：用户板端 r7 日志已确认 PS 应用启动、`OV5640 OK`，随后 `VIDEO FAIL rx=00010000 tx=00011000`，尚未进入眼控。对照原厂例程后，已复现并修复首帧预热与 500 ms 启动超时不匹配的问题；`r7-video1` 首次采集等待 3 秒，运行时仍为 500 ms，并增加采集/显示切帧确认与分步诊断。Host 回归、ARM/BOOT 构建和载荷校验通过，修复版实板出图与 SD 冷启动仍待确认。对话结论、交付文件及复测步骤见 [本次排查记录](ps_video_startup_session_20260929.md)。

2026-09-29 PS r7：用户 r6 三轮实测左眼参考分别为 149/153/143、152/152/149、150/148/144，均失败。新增回归确认：人脸不动、眼模型框随虹膜移动时，旧跟随逻辑会把三点抵消为 128/128/128。现在从人脸框变换投影分析 ROI，保留眼对姿态检查；34 项 Python、C host、912 帧/81 字段一致性、ARM/BOOT 构建通过。实际三轮失败的原因尚不能完全归于该缺陷，r7 真人效果待测。见 `ps_eye_auto/report/gaze_roi_motion_r7.md`。

2026-09-29 PS r6：用户提供的 `d.json` 确认 r5 校准失败，原始图像 C 回放得到同样的眼内位置 160/87；旧程序已抹去参考数据，无法追溯具体失败门槛。r6 改为稳健滚动采样，保留失败原因与统计并支持失败点续采。9 项新增校准检查、原有 22 项 Python 检查、C host、912 帧/81 字段主循环一致性、ARM/BOOT 构建和载荷验证通过。真人连续校准与板上结果待测，见 `ps_eye_auto/report/calibration_recovery_r6.md`。

2026-09-29 PS r5：用户反馈 r4 在电脑端仍不稳定。共享 C 新增灰度中值处理、保留小数精度的归一化、逐眼中位数/MAD 校准、个人尺度双眼融合、有限时间中值窗和方向切换确认。7 项稳定性序列、9 项 PC gaze、6 项 preview、C host 与 840 帧主循环一致性通过，ARM ELF/BOOT 已重建。运行帧间隔大于 250 ms 会暂停动作。没有新增真人连续或板上准确率结果；见 `ps_eye_auto/report/gaze_stability_r5.md`。

2026-09-28 PS 自动定位版入口更新：`ps_eye_auto/README.md`。新版本独立实现灰度 Haar 人脸检测、真正的双眼模型定位、自动 ROI 和三点校准；模型核对、实拍回放、状态边界、VDMA 软件协议测试及 ARM 构建已完成，详细结果见 `ps_eye_auto/report/verification.md`。实物运行仍待验证，不能用 PC 回放速度代表 Cortex-A9 速度。

对早先 PS 说明的更正：旧 `ps_eye` 所复制的 FSBL 不含 SD 初始化代码，先前 BOOT.BIN“可 SD 直接启动”的表述证据不足；本版开启 SD0 MIO40..45/CD MIO10，重新生成包含 InitSD 的 FSBL、BSP 和硬件。PS UART0 使用 PS_UART/MIO14..15，不能套用 PL J23 的端口说明。旧版四个发布文件哈希保持原样，见新版验证报告。

更新日期：2026-09-25。构建证据来自 09-23；用户已提供 HDMI 摄像头输出及电脑串口取图照片，真人眼控识别仍未验收。

09-25 实物反馈：电脑收到相机 5640 / 就绪 1 / 故障 0，快照显示人脸。用户报告背景有时被判为有效；当前照片为两眼无效，眼框大面积暗区且眼 1 高度 101 超出允许值。源码确认目前“眼有效”仅为明暗区域统计通过，不代表确认人眼。原因、参考作品和后续方向见 [实拍分析](eye_failure_analysis_20260925.md)。

| 项目 | 当前证据 |
| --- | --- |
| 比赛 | 用户确认 AMD 自主选题初级组 |
| 主板 / 相机 | 正点原子 Z15 / 正点原子 OV5640 接 P2 |
| 场景 | 摄像头固定屏幕上方，人看 HDMI 左、中、右区域；双眼参与 |
| 工具与器件 | Vivado 2023.1，xc7z015clg485-2，批处理构建通过 |
| 实物 JTAG / 输出 | 历史扫描读到 arm_dap_0 与 xc7z015_1；[连接核验](../report/screen/jtag_connection_check.md)。后续用户照片已有 SCREEN GAZE HDMI 画面及串口取图，运行固件文件哈希未现场读取 |
| 新版工程 | `local/screen_vivado/z15_screen.xpr`，由 `build/screen/create_project.tcl` 重建 |
| v2 RTL | VGA 采集、双眼相对特征、自动三点校准、拒识、停留/释放、UART、快照、HDMI 三分区 |
| 电脑工具 | `tools/screen_monitor.py`：双眼框选、阈值预览、硬件 ACK 后开始校准；7 项 Python/Tk 测试通过 |
| bitstream | `report/screen/z15_screen_top.bit`，WNS +1.268 ns、WHS +0.052 ns |
| 仿真 | 六个 v2 测试通过，含真实 XPM FIFO 的 VGA 到确认事件整链路 |
| 能力边界 | 固定坐姿、手动初始双眼 ROI 与阈值、三区域；无自动人脸检测、连续屏幕坐标或自由头动支持 |
| 未实测 | 板修、接线、电气时序、相机清晰度、真实眼控准确率、端到端延迟及 HDMI 兼容性 |
| 历史 v1 | 单眼 320×240 实验版原样保留，非当前主入口 |
| 后续模块 | EEG、sEMG、执行器、PS/PYNQ、多模态集成仍为规划 |
| Trellis | 0.6.7，sds，Claude + Codex，inline 维护 |

完整使用步骤见 [screen_gaze.md](screen_gaze.md)，验证边界见 [verification.md](../report/screen/verification.md)。

09-25 灰度诊断工具：新增“检查灰度 / 保存原图”，支持对冻结快照读像素、局部放大、人工标记暗部/眼白、导出原始 PNG 和 JSON。9 项 Python/Tk 测试通过（合成数据和模拟串口），没有新增板上准确率证据。无需更换 bitstream；操作见 [gray_inspection.md](gray_inspection.md)。单独电脑工具包为 `D:/fpga/Z15_Gray_Inspection_PC.zip`，旧完整 v2 ZIP 未随此修改重打包。

原始 `D:/vivado/project_1.xpr` 是空工程，未修改。用户最早写的 `D:/vivado/project/_1.xpr` 未找到。原始 ZIP 有 629 个文件，其中 128 份 README 有内容、501 个文件为空。

09-28 PS 眼动验证工程已建立在 `ps_eye/`：基于原厂 PS7/DDR3/HP0/AXI VDMA/OV5640/HDMI 配置创建独立 Vivado 副本，独立副本重新完成综合、实现、时序和 bitstream。PS standalone 应用已编译，包含 DDR 帧统计、VDMA 状态、固定双眼 ROI、三点校准、停留事件，以及把采集帧复制到独立显示缓存后叠加 HDMI 状态条、ROI 框和中心标记；`ps_eye/build/BOOT.BIN`、`ps_eye/build/ps_eye.bit`、`ps_eye/build/ps_eye.xsa`、`ps_eye/build/ps_eye_app.elf` 可用于首次上板。PS 真实上电、帧率、HDMI 兼容性和真人准确率仍待记录，不能用本机构建证据代替。

09-25 参数诊断版 r2：用户在另一台电脑上收到状态，但应用眼框未获确认。已修复 PC 更新流程在新框与板上旧框冲突时停滞的问题：超时后尝试有限次角落临时挪框，再逐项等待最终参数回执。新增发送/回执/超时日志和复制按钮。16 项 Python/Tk 测试通过，包括模拟固件的旧框拒收；用户现场失败的实际原因和修复结果仍待实物日志确认。新包 `D:/fpga/Z15_Screen_PC_20260925_r2.zip` 替代先前灰度检查 PC 包，包含其功能；完整 v2 ZIP 未重打包。见 [操作清单](roi_update_troubleshooting.md) 和 [验证记录](../report/screen/roi_update_verification.md)。

原厂源码在 `E:/cankao/XC7Z015/XC7Z015/`；P2 相机例程也在 `E:/cankao/2_Embedded_Vitis/XC7Z015/XC7Z015/26_ov5640_hdmi`。XLSX 的 D4/PWDN 与原理图冲突，XDC 按原理图及 P2 原例程取 D4=U1、PWDN=K7。

2024 易灵思作品已找到高度吻合的作者文章；其平台和红外相机与本项目不同。PuRe、ElSe 是补查论文，不能声称就是用户此前读过的论文；当前实现也不是两篇算法的完整复现，见 [eye_research.md](eye_research.md)。

09-28 PS 自动定位软件 r4：在 r3 的逐眼累计和暂停续采基础上扩大模型眼区，PC/ARM 共享 `localization_follow()`，按双眼模型框的共同平移和尺度变化投影校准 ROI；空间跟随越界、脸部几何异常或尺度超范围时暂停并保留进度。840 帧主循环一致性、C host、9 项 PC gaze 和 6 项 preview 检查通过；ARM ELF/BOOT 已重建。真人成功率、实际板速待测；详见 `ps_eye_auto/report/eye_roi_follow_r4.md`。


2026-10-14 当前整合入口为 [我们意念合一](../multimodal/README.md)：眼控/肌电/脑电主模式、PL板载键、原媒体与评分、MI只展示及双执行端接入。新增源码、固件与overlay的离线证据见 [验证记录](../multimodal/report/verification.md)。完整GuardianLoop原包的异机实物验收事实保留，新增整合同机验收待设备接回。
