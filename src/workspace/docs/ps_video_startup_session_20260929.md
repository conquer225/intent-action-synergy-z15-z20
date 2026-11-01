# PS 上板黑屏排查与修复对话记录

日期：2026-09-29。维护项目：`D:/fpga/z15_multimodal`。本记录覆盖本次上板黑屏、串口与 JTAG 排查、原厂例程对照，以及 `r7-video1` 软件修复。此前电脑端瞳孔定位和校准问题是背景，本次没有修改眼控算法，也没有新增真人准确率结论。

截至记录时，软件修复、离线回归和固件构建已完成；修复版实板是否恢复摄像头画面仍待确认。

## 用户反馈与排查过程

用户反馈板卡上电后 HDMI 黑屏，断电重上电也无明显变化，并表示接线和 SD 卡内容已检查。用户指出，以前 PL 版本的视频链路已经能够出图，应参考原厂视频例程排查当前 PS 版本。

| 阶段 | 本次对话中的现象或操作 | 能够确认的结论 |
| --- | --- | --- |
| SD 上电 | HDMI 黑屏，早期没有取得明确启动日志 | 当时不能确认应用是否已进入 main；接线和卡内容检查不能替代启动证据 |
| 串口连接 | 协助打开 PS_UART 串口，后来截图端口为 COM14，参数 115200、8N1 | 电脑串口打开只代表连接建立；仍须看到板端输出 |
| JTAG 命令 | 用户混淆脚本参数与工具目录，随后命令执行到结束 | 参数名应为 `-VitisRoot`，参数值是 Vitis 安装根目录，不是 Vitis_HLS 的 bin 目录 |
| ECHO 提示 | 命令输出两次“ECHO 处于关闭状态”，随后打印启动提示 | 后续板端日志已确认应用执行，这两行没有阻止本次启动 |
| 板端日志 | 连续几次出现 r7 启动标识、OV5640 OK、VIDEO FAIL | PS 应用和串口已运行，视频初始化检查未通过，尚未进入眼控循环 |
| 修复验证 | 对照原厂代码，复现首帧延迟导致的超时，修改并重建 | 已修复可复现的软件缺陷；实板黑屏的完整原因仍需新日志确认 |

原始串口日志保存在本机 `ps_eye_auto/report/board_20260929_182450.txt`，包含：

```text
PS_EYE_AUTO_START r7 BGR888 1280x720 face-anchored gaze + Haar
OV5640 OK
VIDEO FAIL rx=00010000 tx=00011000
```

`OV5640 OK` 表示摄像头初始化函数返回成功，不表示 VDMA 已收到完整图像。当前 [main.c](../ps_eye_auto/src/app/main.c) 在 `video_init()` 失败后直接返回，因此此时继续发送 `c` 不会进入校准。

主机脚本打印的 `PS_EYE_AUTO running. Read PS UART0 at 115200 8N1.` 表示脚本已执行到启动命令之后，不是视频自检结果。此次已证实的是 JTAG 路径进入了 PS 应用；SD 冷启动是否正常没有在本次对话中完成验收。

## 关于 PS、PL 和以前成功出图的澄清

项目历史记录和用户反馈确认，旧 PL 版本曾显示摄像头画面。这个结果可以作为硬件接法和视频链路的排查依据，但不能直接当作当前 PS 版本已经验收。

当前所谓“PS 端初始化”，是 PS 程序配置并检查视频硬件；PL 仍参与采集和显示，当前程序还使用 VDMA、DDR 帧缓存及 PS 图像处理。启动时序、缓存控制和所用固件需要配套核对。用户要求参考官方例程解决问题后，本次修改范围限定在视频启动软件、相关测试和交付文件。

## 原厂例程对照及原因判断

核对的正点原子例程为：

```text
E:/cankao/2_Embedded_Vitis/XC7Z015/XC7Z015/26_ov5640_hdmi
```

当前 `ov5640_init.c`、`emio_sccb_cfg.c`、`display_ctrl_hdmi.c` 与该例程对应文件逐字节相同；调用参数同为有效图像 1280×720、总时序参数 2570×980。当前硬件 source BD 的 nets 和 interface_nets 与该例程一致，不将这一项等同于整个工程或所有硬件参数完全相同。

在原厂 [采集模块](../ps_eye_auto/hardware/source/ip_repo/ov5640_cap_data/SRC/ov5640_capture_data.v) 中，`WAIT_FRAME=10`，计满十次 VSYNC 后，还需要下一次 VSYNC 才开放输出。旧 PS 程序对第一次采集帧切换也使用 500 ms 的超时，与正常运行阶段共用门限；原厂主程序没有这个首帧超时退出条件。

已确认的问题是：如果相机和 PL 预热超过这段等待，PS 会在图像准备好之前退出。软件模型把摄像头可供帧时间设为 600 ms 时，旧程序确实返回失败，测试退出码为 1。

原因判断保留边界：600 ms 是回归测试条件，不是这块板子测得的启动耗时。旧 `VIDEO FAIL` 汇总了多个失败位置，缺少具体阶段和首帧时间，因此不能断言该缺陷就是用户这次黑屏的唯一原因，也不能据此认定摄像头或 HDMI 硬件损坏。

## 已完成的修复与验证

修复版本标识为 `r7-video1`，眼控算法仍为 r7。

- 仅首次采集切帧等待改为最多 3000 ms；后续切帧和运行中断帧检查仍为 500 ms。
- 保留采集 1→0 的真实帧切换确认，新增显示读取端 1→0 确认；不把初始帧号 0 当成成功证据。
- 增加初始化 API 失败阶段及返回码，或切帧目标、等待耗时、RX/TX 状态、PARK_PTR、两路控制寄存器。
- 保留独立采集和显示缓存，未改动眼控算法、原厂相机配置或配套 PL bit/XSA/FSBL。

离线视频回归覆盖 600/1200/2900 ms 首帧延迟、无输入、首帧后停顿、13 个 API 失败位置、帧缓存数量、运行时 RX/TX 停顿、VDMA 故障、缓存所有权及计时回绕。Host 测试、ARM 编译和 Bootgen 已通过；发布校验确认 BOOT 内 ELF/bit 与配套文件一致，旧 `ps_eye` 四个发布文件哈希未变。

本次只读查询本机 hw_server，未列出板卡目标，没有执行板卡复位、下载或 Flash 写入。离线测试不代表修复版已经实际出图。技术细节与核验数据见 [修复报告](../ps_eye_auto/report/video_startup_r7_video1.md) 和 [机器核验记录](../ps_eye_auto/report/video_startup_verification.json)。

## 交付与复测约定

新包位于 `D:/fpga/Z15_PS_Auto_Eye_r7_video1.zip`，共 212 个文件，大小 3420990 bytes；旧 `Z15_PS_Auto_Eye_r7.zip` 保留。新包 SHA-256：

```text
3d380d8e6fda712bd9e743e0086f25e360a439d3307500cc31cb8142413094f1
```

JTAG 复测使用新包中的 `ps_eye_auto/build/run_jtag.ps1`。在本维护电脑上的完整命令是：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\fpga\z15_multimodal\ps_eye_auto\build\run_jtag.ps1" -VitisRoot "D:\vivado\Vitis\2023.1"
```

换电脑时，脚本路径改为新包实际解压路径，Vitis 路径改为该电脑的安装根目录；`-VitisRoot` 参数名不改。本机已核对 `D:/vivado/Vitis/2023.1/bin/xsct.bat` 存在，不能把 Vitis_HLS 路径替代为同一工具。SD 复测则用新的 `ps_eye_auto/build/BOOT.BIN` 替换卡根目录同名文件后重新上电。具体接线、模式及串口操作见 [PS 版本使用说明](../ps_eye_auto/README.md)。

复测需先确认运行的是新固件：

```text
VIDEO_BOOT r7-video1 startup_ms=3000 runtime_ms=500
```

首帧等待中允许出现 `VIDEO_WAIT`。初始化通过需要看到 `VIDEO_READY`、`VDMA OK / HDMI STARTED`，完整视频验收还需要显示器实际出现摄像头画面。若失败，保留从启动标识开始的整段日志，尤其是 `VIDEO_TIMEOUT`、`VIDEO_INIT_FAIL` 或 `VIDEO_FAULT`，依据具体阶段继续排查。

后续待办是确认修复版 JTAG 出图、再单独确认 SD 冷启动，视频正常后才继续校准和左右中识别测试。截至本记录，不能写成“实板黑屏已解决”或“眼控准确率已通过”。
