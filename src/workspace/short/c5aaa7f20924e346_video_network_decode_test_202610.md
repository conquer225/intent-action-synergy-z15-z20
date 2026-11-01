# 手机热点视频链路：无线与 ARM 解码台架测试

日期：2026-10-06。对象：当前 Z15（Zynq-7015、Linux
`5.4.0-xilinx-v2020.2`），现有 8188eu USB 无线网卡，手机热点 `QqqQ`。
手机端和板端地址分别为 `192.168.43.1`、`192.168.43.6`。
控制通道使用有线 SSH `192.168.2.99`，测速数据使用 WLAN。
没有安装依赖、读取手机照片、录屏、改 PL、操作 DMA 或修改正式服务。

## 本轮结论

现有网卡先保留。手机直连吞吐短测约 20–21 Mbps，对计划中的
4–8 Mbps 压缩视频有带宽余量，但不是长期稳定性或端到端投屏验收。
720p/30 可作为下一阶段目标；1080p/30 在本轮完整 BGR 内存路径上不达标。

现有 OpenCV 路径不是板端所有解码方案的性能上限：直接使用板上已有
FFmpeg 库，720p 解码加 BGR 转换从约 27 fps 改善到约 34–39 fps。
这是隔离探针的结果，尚未接入正式程序。没有在模型正常预测的完整负载下
测同时运行，也没有 HDMI 输出、音频或手机屏幕发送端。

## 手机补测结果

临时页面 `http://192.168.43.6:9118/` 每项约 10 秒，使用 256 KiB 请求块。
服务端记录的对端为 `192.168.43.1`，确认来自手机热点主机。

- 手机 → Z15：26,738,688 字节 / 10.0632 秒，21.2566 Mbps，102 次请求，
  请求失败 0，单块完成时间 p95 122.4 ms。
- Z15 → 手机：25,427,968 字节 / 10.0673 秒，20.2064 Mbps，97 次请求，
  请求失败 0，单块完成时间 p95 133.0 ms。

这些是 HTTP/TCP 测试字节吞吐，不是视频帧率。单块时间不是画面延迟；
TCP 会重传，请求失败为零不能证明无线包级零丢包。只有一组手机短测，
也可能受同期板端台架 CPU 活动影响，不能作为网卡极限或长期保障值。

第一版临时页面因 Python 字符串中的换行转义生成无效 JavaScript，没有
有效手机结果。修复为原始字符串、显式 DOM 引用和 AbortController 后，
离线脚本语法检查通过，用户补测并回传上述结果。未把第一次点击算成成功。

电脑另做了两跳对照：PC Wi-Fi → 手机热点 → Z15，上传三次约
10.36 / 15.84 / 18.36 Mbps，下载约 9.74 / 9.81 / 10.04 Mbps。
4 / 8 / 12 Mbps 的各 6 秒节流上传分别达到约 4.03 / 8.02 / 12.01 Mbps。
均无 HTTP 请求失败，但两跳结果不能替代手机直连。

## 合成视频与解码结果

没有使用真实手机画面。样本为自行生成的移动渐变/方格，H.264
Constrained Baseline，ultrafast、zerolatency、无 B 帧，YUV420P，无音频。
图像简单、片段短，不能代表所有投屏编码器或复杂视频。

- 720p：180 帧，名义 30 fps、6 秒；2,926,150 字节，按名义时长约
  3.9015 Mbps。旧样本容器报告 30.1676 fps，系最后一包时长未补齐；
  此处测的是不限速解码吞吐，不按该时钟播放。修正后的生成器会补包时长。
- 1080p：60 帧、30 fps、2 秒；2,000,523 字节，约 8.0021 Mbps。
  初次生成 180 帧超过 30 秒限时，未作为有效视频使用；缩短后完整生成。
  失败产物保留在板端，已加 `.incomplete` 后缀防止误当作有效样本。

每种有效解码对照重复两次，全部解完预期帧数：

- OpenCV/FFmpeg → BGR：720p 为 27.32 / 27.19 fps；1080p 为
  11.02 / 12.00 fps。
- 原生 FFmpeg，单线程，仅 YUV 解码：720p 为 39.01 / 39.19 fps；
  1080p 为 17.55 / 17.85 fps。
- 原生 FFmpeg，双线程，仅 YUV 解码：720p 为 67.11 / 58.88 fps；
  1080p 为 29.75 / 24.23 fps。
- 原生 FFmpeg，双线程，加 BGR 转换：720p 为 38.79 / 33.93 fps；
  1080p 为 17.11 / 16.88 fps。

双线程原生完整 BGR 路径以最快速度运行时，CPU 约 166–189%，
其中 200% 相当于占满两个核心；峰值 RSS 720p 约 30 MiB、1080p 约 42 MiB。
不能将不限速运行 CPU 直接当作 30 fps 节流时的占用，更不能保证和 EEG
多任务共跑仍有余量。样本帧数、尺寸和首像素累加值有检查，但没有逐像素
比较整个视频或做视觉/音画同步验收。

推断：OpenCV 入口和图像转换都有明显开销，直接库调用值得保留为候选。
但不同路径的缓冲/线程行为也不同，不能将全部差值单独归因于颜色转换。
1080p 仅 YUV 的最快一次接近 30 fps，也不构成 1080p/30 出画通过。

前期 PC MSMF 生成的两段高码率压力样本实际约 27.54 / 62.07 Mbps，
720p 解码约 17.6 fps、1080p 约 7.7–8.3 fps。它们不是目标 4/8 Mbps
样本，不据此推断普通视频的帧率。MSMF 的默认码率设置见
[OpenCV 上游源码](https://raw.githubusercontent.com/opencv/opencv/4.x/modules/videoio/src/cap_msmf.cpp)。
原生探针使用已安装 FFmpeg 的发送/接收 API，参考
[FFmpeg 4.2 API](https://ffmpeg.org/doxygen/4.2/group__lavc__encdec.html)。

## HDMI 与正式系统边界

本轮 root 权限读取的 PYNQ 加载登记仍为
`/home/xilinx/jupyter_notebooks/guardianloop_pynq/guardianloop_pynq.bit`。
登记 IP 是 GuardianLoop registers、EEG quality、DE、HGB、AXI DMA、PS7，
没有 HDMI/VDMA/VTC 显示模块。已有眼控显示脚本会暂停采集、换完整
`eye_wifi.bit`，不是在当前正式 PL 中加一个独立播放器，故本轮没有启动它。
详见 `ARM_PL_BRAIN_EYE_RUNTIME_20261005.md`；本轮没有主动读写显示寄存器。

结束核对：

- 正式发布 `guardianloop-fixed8-mobile-web-20261003` 的 48 文件逐项 SHA256
  与清单一致，8 项服务/网络/启动/清单保护文件与开始前哈希一致。
- 网页 PID 677、采集 PID 2077 前后未变；网页 NRestarts 0、采集
  NRestarts 178 前后未增加。采集原有重启历史未在本轮修复。
- `/mobile` 本地 HTTP 200；启动 ID
  `e0fd1f19-9ccd-494d-b262-7a5924046336` 未变。
- 临时测速服务 `gl-video-7498b9dd4f.service` 已停止，PID 0、inactive。
  正式网页、采集服务未被停止或重启；PC Wi-Fi 已恢复 `JLU.WIFI`。
- 手机热点运行时连接保留；没有改永久热点、SD 启动镜像或安装新驱动。

## 后续门槛

先以 720p/30、约 4 Mbps 选择手机发送端和板端接收协议，确认这台
HarmonyOS 手机能实际发送所需格式；普通测速网页不能代替投屏接收器。
然后确认 HDMI 显示 PL 与正式脑控的共存/回退方案，取得明确授权才做
临时显示切换。最后测真实无线视频 → 解码 → HDMI 的画面延迟、掉帧与
脑电正常预测负载。当前没有必要仅据宣传速率购买新网卡。

## 留存与复现

Windows 目录：`D:\ican\codex_project\eeg_apps_z15\output\gl-video-7498b9dd4f\`。
板端探针目录：`/home/xilinx/gl-video-7498b9dd4f/`。目录保留，服务已停止。

- `result.json`：PC 两跳吞吐、高码率压力样本和开始/结束保护信息。
- `phone_results.json`：用户补测的服务端日志记录。
- `baseline720_phone.json`：低码率 720p OpenCV 两次结果。
- `baseline_native.json`：样本大小、SHA256、1080p OpenCV 与原生解码对照。
- `final_audit.json`：48 文件核对、服务状态和临时探针停止结果。
- 两个有效低码率 MP4 已从板端取回，上述 JSON 记录了 SHA256。

探针源码在 `eeg_apps_z15/`：`video_network_probe.py`、
`video_decode_probe.py`、`video_decode_native_probe.c`、
`make_h264_bitrate_probe.c`；另有 PC 样本生成器和 `run_video_probe.py`。
无需新安装包，板端现有 gcc/FFmpeg 头文件与库已完成编译。
