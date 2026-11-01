# 隔离原生扫描与受控调度（2026-10-08）

## 范围

用户要求隔离显示扫描路径、优化受控调度，再做固定亮度复测。
只使用 Z15 现有显示 `eye_wifi.bit/.hwh` 和显示库，结束恢复正式
`guardianloop_pynq.bit`。没有综合、实现、生成新 bit、改 SD 启动配置、
重启采集、开启闪烁、声音、眼控或实体轮椅。

HWH 标注为 system 设计、7z015 / CLG485 / -2；匹配 Vivado/BD/RTL/XDC
源码仍缺。这轮不是两套硬件设计融合。

## 实现

- `phone_video_upload/native_scan.c`：将原有三缓冲、提前两帧、角区复制、
  变化行带缓存同步、锁存及逐扫描检查放进一个独立 pthread。热循环不调用
  Python、不联网、不写逐帧日志、不分配内存。没有增加 AXI 地址或修改显示库。
- `native_scan.py`：按实际板端 PYNQ/XRT ABI 传入函数地址、设备句柄、CMA
  缓冲和角区补丁。相位表来自原软件 `pattern()`，回执仍由原 `ScanEvidence`
  离线复核，不以模拟相位冒充屏幕光学测量或在线方向控制。
- 只对该扫描线程设置 CPU1 亲和性和 SCHED_RR 优先级 1，主线程保持
  SCHED_OTHER。扫描最多 30 秒；记录并检查每轮 8 ms 线程 CPU 用量预算，
  超过预算、漏扫描、缓存同步失败、锁存不符或迟到即停止。该预算是循环末
  检查，不等于可抢占的硬实时保证；未更改系统全局 RT 预算或采集调度。
- 保留原 16.5 ms 扫描配置、24.75 ms 最大回执间隔以及原频率/计数检查，
  没有为了通过而放宽门槛。工作线程退出并 join 前不能释放缓冲；若无法退出，
  保留 CMA 和映射，交给独立恢复程序处理。
- `run_scan_timing.py --native-scan` 只允许全新隔离的固定亮度目录，不能与
  睡眠诊断 preload 混用。加载前核验 bit/HWH、显示库、软件与原正式发布哈希；
  保留独立 150 秒恢复定时器。

受控线程调度的含义参见 [sched_setscheduler 手册](https://man7.org/linux/man-pages/man2/sched_setscheduler.2.html)。
实际 ABI 以板上安装的 `pynq._3rdparty.xrt` 源码为准，不能用新版本文档代替。

## 首次实际加载：适配失败

目录：`/home/xilinx/gl-latch-20261008-381409ee/`。
本地证据：`phone_video_upload/output/dynamic_latch_20261008-native-rr/`。

软件准备 20 项通过（93.135 秒）；随后加载显示设计、初始化固定亮度三缓冲。
VTC 核验 1280×720、总计数 1650×750。开始扫描适配时发生：

`incompatible types, LP_c_void_p instance instead of c_void_p instance`

因此原生工作线程**没有启动**，没有采集到原生扫描回执，也没有测试 RT 调度。
本轮不能报告速度改善、30 秒通过、频率通过或光学时序通过。

根因已由板端安装源码确认：`xclOpen.restype` 为
`ctypes.POINTER(xclDeviceHandle)`，其中 `xclDeviceHandle=ctypes.c_void_p`；
返回的是 `LP_c_void_p`。原适配器直接赋值给配置的 `c_void_p` 字段而失败。
修正使用 `ctypes.cast(handle, ctypes.c_void_p)` 保留原不透明指针值，绝不
解引用设备句柄。

并新增真实接口预检：在 PL 加载之前使用真实 CMA 缓冲核验配置结构、设备句柄
和原生缓存同步调用；该预检不调用任何显示/MMIO 函数、不启动工作线程。
软件测试的真实 XRT 检查须与实际运行一致，以 root 和 `XILINX_XRT=/usr`
执行；普通无硬件单元测试继续作为独立非特权检查。

修复版目录为 `/home/xilinx/gl-latch-20261008-f1efd161/`，本地证据为
`phone_video_upload/output/dynamic_latch_20261008-native-abi-verified/`。
无硬件软件回归 20 项全部通过（99.314 秒）；随后独立真实 CMA/XRT 预检
1 项通过（7.857 秒），没有加载 PL、调用显示/MMIO 函数或启动原生线程。
软件预检结束时，修复版 `launch.json` 的 `launched=false`。

前一次修复预检目录 `dynamic_latch_20261008-native-abi-preflight` 保留了测试
环境错误：20 项纯软件检查通过，真实接口检查因未使用 root/XRT 环境而报
`No Devices Found`。该次未加载 PL；改为与实际运行一致的环境后才得到上述
真实接口通过记录，不能把前次检查失败删去或计入通过数。

电脑最新回归 28 项通过（2.504 秒），11 项需要原生 Linux 库／板端 XRT 的
检查在电脑明确跳过；这些检查的通过证据取自上述板端测试，不将跳过计为通过。

## 恢复与输入

实际失败加载后 `display_halted / buffers_released / original_restored` 全为 true；
正式发布 50 项哈希、保护文件、启动 ID、服务 PID 与 NRestarts 均与本轮
加载前相同。正式 PL 已恢复，独立恢复定时器已核对取消。

本轮开始前采集 PID 已为 30461、NRestarts=1；网页 PID=26555、NRestarts=0。
不能沿用上一轮的采集 PID=23531 / NRestarts=0 来冒充一直无重启。

手机热点 QqqQ 保持连接。加载前读取状态为 132104 包、校准 6/15、序号间隙
38；稍后读到 204209 包、间隙 69、`MALFORMED_STREAM`、校准 0/15。
这不是 30 秒扫描区间的同起止比较，不能据此定位原因；原生线程未启动，
所以不能归因为新线程 RT 优先级。输入包持续增长也不代表质量或稳定性通过。

完成软件修复后，最新状态为 309725 包、校准 15/15、质量 good、prediction，
热点仍连接；历史序号间隙已累积 146。此时能预测不抹去此前的无效/校准撤销，
不能据此宣布采集长时稳定性通过。

## 后续边界

句柄修复后的软件/真实接口检查与硬件复测必须分别记录。
首次失败后没有直接追加加载；经用户再次回复“允许”，才执行下面的一次补测。

主线仍是固定显示 PL + ARM 完整闭环。之后另行确认可见闪烁，才做佩戴的四频／
休息识别、人工停止及方向闭环；实际轮椅继续禁用。显示设计源码取得／必要加速器
整合、HDMI 原始脑电与提示同步录制、MI 右手／休息重训仍是未完成项。

## 经再次确认后的固定亮度补测：通过

仍使用修复版 `/home/xilinx/gl-latch-20261008-f1efd161/`，没有再编译或改测试
门槛。启动前只读核验 110 个硬件/软件文件哈希、远端配置、正式发布、服务、
启动 ID 与上次预检一致，手机热点 QqqQ 已连接。

实际扫描于 2026-10-08 11:58 UTC 左右启动，持续 **30.011270427 秒**。
目标是 30 秒；多出的约 11 ms 来自完成最后一轮扫描，不是额外一次测试。

- 连续接受 **1819 次**逐扫描回执，计数 34→1853；没有跳扫、重复、错误
  锁存或 DMA 错误，原生错误码 0，消费者复核无错误。
- 原 `ScanEvidence` 原门槛复核为 ready，计数速率 **60.61260047 Hz**，
  对应名义值 60.60606061 Hz。最大回执间隔 **16.788843 ms**，低于
  原 24.75 ms 上限；没有放宽门槛。
- 角区复制中位 1.681706 ms、p95 2.270268 ms、最大 3.057824 ms；
  缓存同步中位 0.037409 ms、p95 0.044021 ms、最大 0.126854 ms。
- 锁存调用中位 14.721735 ms、p95 15.395798 ms、最大 16.418977 ms。
  它包含等待实际扫描边界，不应被当成全程占用 CPU 的计算时长。
- 实际工作线程为 SCHED_RR（策略值 2）、优先级 1、CPU1；调度 errno=0。
  主线程前后均 SCHED_OTHER（策略值 0）。工作线程总 CPU 9643.86282 ms，
  最大单轮线程 CPU 7.017099 ms，未触发 8 ms 循环末预算检查。
- 四种逻辑相位的回执统计约 7.9973 / 9.9966 / 11.9959 / 13.9952 Hz。
  **全部可见补丁亮度相同，以上不是实际屏幕闪烁频率，也不是光学测量。**

这是合并“原生路径＋单线程调度”的一个 30 秒样本，没有拆分各改动的因果贡献，
也不能据此保证任意负载下长期无迟到。原生线程目前仍属于隔离测试版，尚未接入
正式在线 HDMI 刺激/方向会话。

### 恢复、输入和证据

三缓冲像素哈希一致，`pixels_constant / display_halted / buffers_released /
original_restored` 均为 true。正式发布 50 项哈希、保护文件、服务 PID / NRestarts
与启动 ID 均未变。试验进程已退出，MainPID=0、ExecMainStatus=0、Result=success；
独立恢复定时器核对后取消，LoadState=not-found、ActiveState=inactive。

输入观察起止不是精确 30 秒窗口：加载前读数 server_time=1791460597、357973 包、
间隙 171、校准 4/15；补测后读数 1791460734、392473 包、间隙仍 171、校准
15/15、quality=good、prediction；后续读数 1791460836、417973 包，间隙仍171、
校准仍15/15，但因 REQUIRED_CHANNEL_QUALITY 显示 invalid / degraded。
期间服务和热点保持运行，未增加报告的 dropped_packets；质量波动仍存在，不能
把此轮扫描通过同时计为脑电质量/识别或长时稳定性通过。

证据目录 `phone_video_upload/output/dynamic_latch_20261008-native-abi-verified/`：

- `retest-admission.json`：此次加载前只读核验。
- `scan-report.json`：完整 1819 次锁存、计时、实际调度和原生预检。
- `after.json`、`unit-status.json`：正式 PL、文件、服务、退出码与恢复定时器。
- `independent-recheck.json`：电脑使用原 `ScanEvidence` 对全部回执另行复核通过。

下一项先将这条通过的原生扫描路径接入隔离 HDMI 刺激候选，再另行取得可见
闪烁确认，检查真实输入质量并做四频／休息与人工停止验收。不得直接开启轮椅。
