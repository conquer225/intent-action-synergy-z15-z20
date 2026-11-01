# 有线裸机备用方案

用户当前选择 USB 无线网卡，主入口是 README 的 Linux 服务。本文件仅说明另外保留的 GEM0 裸机程序，两种启动方式不能混用。

`build/BOOT.BIN` 包含新生成的 FSBL、r9 视频/OSD bitstream 和裸机 `ps_eye_net.elf`。它不运行 Linux，不支持本项目的 USB 无线网卡。需要单独试验有线时，先保留现有 Linux SD 卡，在另一张卡上使用这个 BOOT；不要覆盖现有无线卡。

有线接口配置依据正点原子 `40_ov5640_ps_eth_udp_pc`：GEM0，MIO16..27，MDIO52..53，lwIP 2.1.3 RAW。默认板卡 `192.168.1.10/24`，网关 `192.168.1.1`，UDP5001。电脑设为同网段未占用地址，再打开同一个 PC 工具，目标地址设为板卡地址。这里使用 BGR 原像素分片，不是无线服务默认的 JPEG。

串口沿用 Z15 PS UART：`c` 开始校准、`t` 重试、`r` 清除、`p` 状态、`n` 自动使用电脑回传、`l` PS 本地检测。摄像头/HDMI 启动和独立 VDMA 同 r8 派生链路。该备用固件已编译并校验载荷，GEM0 实板数据传输尚未测试。

构建：`powershell -File build/build_all.ps1`。文件和本版 `.bit/.xsa/BSP/FSBL` 配套，源码从 `ps_eye_net` 自己的目录读取；不依赖修改 r8 工程。
