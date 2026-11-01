# HDMI 静态扫描时序检查（2026-10-08）

## 授权、目标和边界

用户明确授权短时加载显示版，做不闪烁的扫描检查，结束恢复正式版。
目标 Z15 的已核验显示 HWH 标明 `DEVICE=7z015`、`PACKAGE=clg485`、
`SPEEDGRADE=-2`，系统名 `system`，元数据 Vivado 2023.1；这不表示已有
可重建的 Vivado 原工程。没有运行综合、实现、JTAG、烧写或板卡复位。

本次固定显示同一张低亮静态文字画面，不播放视频、不闪烁、不打开眼控 USB，
不输出音频，不发送 ESP32/电机/轮椅命令，不停止脑电或网页服务。
启动前核验正式 ARM 清单、ARM-only 共存契约、两套 bit/HWH 与显示库哈希，
取得 PL/显示独占锁；独立 75 秒恢复定时器只针对本次脚本、状态文件和服务。

显示文件：`/home/xilinx/brain_eye_coexist_20261005/eye/overlay/eye_wifi.bit`
及同名 HWH；显示库 `libtobii_display.so` SHA256
`f0e12abe7901c3b98843a10135f1ce98d0507d3ef518a9836186ceab4d1e9da9`。
原始恢复目标：
`/home/xilinx/jupyter_notebooks/guardianloop_pynq/guardianloop_pynq.bit`。

## 结果

- 硬件帧计数采样 30.001730 秒，增量 1819，平均 **60.629837 Hz**。
- 各完整秒增量均为 60 或 61；未观察到一次轮询跨过多个计数增量。
- VTC 生成有效区读回 1280×720，水平总长 1650、垂直场 0 总长 750。
- 已核验 HWH 中 `clk_wiz_0.clk_out1` 和 `live_osd_0.pix_clk` 的时钟元数据
  为 75 MHz，据此与总长推算 60.606061 Hz，与帧计数结果相符；这不是独立
  的像素时钟或光学测量。避免仅凭参数名混淆第二路 375 MHz 时钟。
- VDMA 状态 `0x11000`，现有错误/停止掩码 `0x80000ff1` 检查通过。
- 软件轮询观察的相邻计数间隔中位数 16.836508 ms、p95 17.074361 ms，
  最大 27.882834 ms；最大轮询间隔 12.825225 ms。
- 报告 `errors=[]`，显示 DMA 停止、CMA 释放、正式 PL 恢复均为 true。
- 独立结束核验正式 50 文件清单与启动配置哈希保持一致，启动 ID 不变；
  采集 PID 23531、网页 PID 26555，NRestarts 均为 0，均未变化。
- 有限检查服务退出码 0，无残留工作进程；确认恢复后取消本次恢复定时器。

帧计数来源：现有库 `display_frames()` 的只读反汇编确认读取
`live_osd_0` 的 `0x43c0000c`，不是统计 ARM 新视频帧或浏览器回调。
VTC 有效区/总长地址解释依据
[AMD PG016 Default/Constant Tab](https://docs.amd.com/r/en-US/pg016_v_tc/Default/Constant-Tab)
与 [Control Signals and Timing](https://docs.amd.com/r/en-US/pg016_v_tc/Control-Signals-and-Timing)。

## 结论和限制

静态硬件扫描进展及受控恢复检查通过。当前 HDMI 输出是约 60.63 Hz，
不是电脑网页曾测得的约 240 Hz；后续刺激调度不能复用网页 240 Hz 门控。

上述间隔受 Linux 调度与轮询延迟影响，不能把最大间隔直接当成屏幕丢帧。
没有光电/高速相机实测，也没有测实际光学频率、刺激切换是否撕裂、四角
SSVEP 识别准确率、休息拒绝、眼控/视频完整同场负载或实体轮椅制动。
一次静态检查不意味着这些后续验收已经通过。

下一步是单一显示所有者下的 HDMI 扫描同步刺激和会话/窗口时序适配；
需根据约 60.63 Hz 的实际扫描率安排周期，处理非整数帧半周期，不将平均
频率接近目标冒充为精确光学频率。然后另行授权短时闪烁检查与佩戴频率/
休息验收。通过前实体轮椅输出继续禁用。

## 证据

本地证据：`phone_video_upload/output/scan_timing_20261008/` 下的
`before.json`、`launch.json`、`scan-report.json`、`after.json`、`unit-status.json`。
远端有限试验：`/home/xilinx/gl-scan-20261008-7c632ea6/`。
脚本 `phone_video_upload/scan_timing_probe.py`、控制端
`run_scan_timing.py`；5 个静态采样/故障软件测试在电脑和板端通过，
统一状态机 58 项测试通过。未修改正式模型、采集代码、开机配置或 bit 文件。
