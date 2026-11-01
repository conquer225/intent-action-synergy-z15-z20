# Z15 PS 眼动验证工程

这个目录是 Z15 的独立 PS 眼动验证工程。硬件链路沿用已核对的原厂 `26_ov5640_hdmi`：OV5640 进入 PL 采集 IP，经 AXI VDMA 写入 PS DDR，再由 VDMA 读出送 HDMI。PS 程序每 100 ms 读取采集缓存中的一帧，做双眼 ROI 灰度检测和方向状态机，同时复制到独立显示缓存，在 HDMI 画面叠加状态条、双眼 ROI 框和瞳孔中心，并从 UART0 输出诊断信息。

当前默认输入是 1280×720、3 字节每像素，采集缓存地址为 `PS DDR base + 0x01000000`，显示缓存位于采集三帧之后再偏移 1 MiB 的区域。默认 ROI 是左眼 `(300,240,260,160)`、右眼 `(720,240,260,160)`，这些坐标是第一轮上板调参起点，不是对照片中眼睛位置的测量结果。

## 目录

| 路径 | 内容 |
| --- | --- |
| `vivado/ps_eye.xpr` | 独立 Vivado 工程副本 |
| `vivado/system_wrapper_reference.bit` | 原厂已生成、与 XSA 配套的回退 bitstream |
| `vivado/system_wrapper_reference.xsa` | 原厂硬件导出 |
| `src/app` | PS 应用和眼动算法源码 |
| `build` | Vivado、ARM 编译、Bootgen 脚本和产物 |
| `tests` | 主机端合成帧测试 |
| `report` | Vivado 日志和构建证据 |

## 构建

在 PowerShell 中执行：

```powershell
& 'D:/fpga/z15_multimodal/ps_eye/build/validate_vivado.ps1'
& 'D:/fpga/z15_multimodal/ps_eye/tests/run_host_tests.ps1'
& 'D:/fpga/z15_multimodal/ps_eye/build/build_app.ps1'
& 'D:/fpga/z15_multimodal/ps_eye/build/package_release.ps1'
```

`build_app.ps1` 使用 Vitis 2023.1 的 ARM GCC 和从 XSA 生成的 standalone BSP；`package_release.ps1` 把 FSBL、bitstream 和应用 ELF 合成 `build/BOOT.BIN`。如果 `build/ps_eye_rebuilt.bit` 存在，打包脚本会优先使用它；否则使用已核对的原厂回退 bitstream。

## 上板

连接 P2 OV5640、HDMI OUT、JTAG 和 PL USB UART。UART0 使用 MIO14/15，115200 8N1。JTAG 启动时保持 BOOT_CFG 的两个开关为 ON；SD 启动时使用 `build/BOOT.BIN`，并按板卡实际启动拨码切到 SD。

上电后应看到：

```text
PS_EYE_START z15 xc7z015 1280x720 RGB888
OV5640 OK
VDMA OK ...
HDMI STARTED
```

串口输入 `c` 开始三点校准，按顺序注视左、中、右；输入 `r` 清除校准，输入 `p` 打印一次状态。`EYE_EVENT` 是 PS 算法的候选确认事件，不能在没有实物日志时当作准确率结果。

HDMI 状态条使用三段颜色表示左、中、右候选方向；绿色/红色 ROI 框表示左右眼有效性，十字表示当前暗区中心，底部细线表示校准掩码和当前校准阶段。状态条是 PS 软件叠加层，摄像头原始帧和显示帧使用不同 DDR 区域。

也可以在连接 JTAG、确认没有其他 Vivado Hardware Manager 会话占用目标时执行 `build/program_jtag.ps1`。这个脚本只负责下载 bitstream；PS 应用仍需通过 `BOOT.BIN` 启动或在 Vitis/XSCT 中加载 ELF。

## 证据边界

Vivado BD、ARM ELF、Bootgen 和主机端合成帧测试可以在本机复现。真实相机清晰度、DDR 连续读写、HDMI 兼容性、端到端延迟和真人识别准确率需要在用户的 Z15 上记录 UART 和屏幕现象后再填写。
