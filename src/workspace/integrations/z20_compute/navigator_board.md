# 领航者实板联调

2026-10-25 现场状态：重新插接后 USB 串口枚举为 COM13；用户按 PS RESET 后原系统已启动，FPGA Manager 为 `operating`。现场没有 HDMI 屏幕和线，DRM 的 HDMI 端口为 `disconnected`。原系统当前没有专用 UIO，下面 COM15、临时 Linux 和双目/NPU 步骤是上次实测的恢复记录，不代表当前已加载。音频旧测试镜像曾造成持续响声，禁止重试；见 [音频加载记录](report/navigator_audio_j4_20261025.md)。

同日后续伪点云开发时再次检查，电脑只枚举蓝牙虚拟 COM3～COM12，没有 CH340；有线以太网适配器为断开，`192.168.1.20` 不响应。新点云入口只用先前真实录制帧及其 JPEG 协议重放完成离线验证；本轮没有新的实板画面。见 [伪激光雷达点云使用说明](PSEUDO_LIDAR.md)。

2026-10-24 已恢复并完成首轮实板验证：临时Linux与PL加载成功，NPU共100次整数对照通过，两路相机持续采集，电脑预览回传约14次/秒，真实图像像素视差与ARM StereoBM诊断已运行。用户暂时没有标定参数，米制测距和点云未验收。详见 [本次实板记录](report/board_20261024.md)，此前[暂停记录](report/pause_20261024.md)保留为历史。

同日继续完成了 [无标定文件的实际重建尝试](report/navigator_nominal_trial.md)，输出53,589点的假设参数点云和可视预览；当前尺度为相机间距单位，未验证实际形状和厘米距离。

实物为正点原子领航者 ATK-DF7010/7020P。串口 COM15、115200 8N1；Linux 设备树报告 Alientek Navigator Zynq Development Board，PS IDCODE 为 0x23727093，确认 XC7Z020。CLG400 封装依据实物型号与同板参考工程；速度等级 -2 来自参考工程，尚未读取芯片完整丝印。

双目模块接照片左侧竖排的 40 针 J3。断电插接，模块与底板的 5V、3.3V、GND 同名对应，40 针完整对齐。参考工程的两路数据和控制管脚与 J3 丝印对应；例如相机0 D0=P19、PCLK=W18，相机1 D0=V17、PCLK=V16。J4 位于底边，与这组管脚不同。P2 的 18 针 OLED/CAMERA 接口用于另一种单目模块。

此前 `artifacts/z20-stereo-sd.img`、`artifacts/z20-stereo-board.zip` 及 `build/stereo_implementation/` 针对新版 Z20 CLG484，禁止烧到这块领航者。它们保留为历史离线候选。新增目标在 `build/navigator/` 单独构建，采用已核对的领航者实验38和网络实验40的 PS 配置、相机／HDMI 引脚，复用共享 NPU 与被动帧观察器。

## 现场状态

系统为 Linux 5.4.0-xilinx-v2020.2、ARMv7、约1GB内存。现有系统来自 mmcblk1p1；SD 为 mmcblk0p1，挂载到 /media/sd-mmcblk0p1。联调保留现有启动介质，不覆盖 eMMC、QSPI 或整张 SD。

临时有线地址设为PS口eth0的192.168.1.20/24，电脑为192.168.1.102。SSH可达；本轮经Linux加载FPGA，没有使用USB JTAG下载器。NumPy1.17导入成功，cv2导入仍段错误；原厂C接口的JPEG与StereoBM已执行。NPU和真实图像已验证，测距误差与点云质量待标定后测量。

电脑可以显示回传的双目图像并参与标定和点云融合，HDMI 显示器不是联调前置条件。正式方案仍由板端计算距离。米制距离需要与当前镜头、焦距和分析分辨率匹配的实拍标定；程序算例只验证数值。

## 断电后的恢复

专用归档为 `artifacts/navigator-bringup-20261024.zip`，内容及摘要见 `report/navigator_archive.json`。它包含CLG400固件、设备树、当前内核、工具源码、诊断程序与实测记录，不是整盘镜像。SD上的 `navigator-bringup/diagnostics-20261024.tar.gz` 保存了本次板端测试目录；恢复后仍需临时启动和加载PL。

电脑从本目录运行归档中的 `build/navigator_boot_resume.py`，通过COM15重启并打断U-Boot，从SD的 `navigator-bringup/zImage` 与 `system.dtb` 启动，沿用eMMC根文件系统。该脚本对应当前串口、SD编号、板型和原厂UART自动登录环境；修改这些条件时先核对，不运行 `saveenv`。

进入专用Linux后，应看到上述四个UIO设备，视频与NPU的预留内存也应存在。恢复测试目录：

```sh
tar -xzf /media/sd-mmcblk0p1/navigator-bringup/diagnostics-20261024.tar.gz -C /tmp
cd /tmp/navigator-check
export PYTHONPATH=.
```

下列PL加载步骤只用于这块领航者与上述专用设备树。先停止其他分析进程，核对SD内 `system.bin` 的SHA256为 `b29cebf8e8c0a7fc223d0b71990cb9b0a0689c469778adaf9d0d9ffe87194234`。PS FCLK1需设为约142.857MHz，与观察器和该硬件一致：

```sh
/sbin/devmem 0xf8000008 32 0xdf0d
/sbin/devmem 0xf8000180 32 0x00100700
cp /media/sd-mmcblk0p1/navigator-bringup/system.bin /lib/firmware/navigator-stereo-npu.bin
echo 0 > /sys/class/fpga_manager/fpga0/flags
echo navigator-stereo-npu.bin > /sys/class/fpga_manager/fpga0/firmware
cat /sys/class/fpga_manager/fpga0/state
/sbin/devmem 0xf8000240 32 0
/sbin/devmem 0xf8000900 32 0xf
```

状态应为 `operating`。先核对GPIO控制器的base为906，再执行 `./camera_probe 906 init`；它仅访问PS GPIO54～57对应的两路SCCB。两路ID须为0x5640、INIT须为0。只在刚加载PL且采集尚未运行时执行 `python3 start_capture.py`。启动落在半帧时可能留下错误位，先记录，再以W1C清除0xff0，随后检查错误是否复现；当前实测稳定状态为两路0x15000。

```sh
/sbin/devmem 0x43000034 32
/sbin/devmem 0x43010034 32
/sbin/devmem 0x43000034 32 0xff0
/sbin/devmem 0x43010034 32 0xff0
python3 capture_check.py
python3 -m z20_compute.npu_check --repeat 10 --output /tmp/navigator-check/npu-repeat.json
```

`jpeg_stdout.py` 在15秒内向标准输出发送大端序的“帧序号、JPEG字节数、JPEG数据”，必须由电脑二进制接收端消费，不能直接打印到串口。复用2ms取帧重试；采集、快照与电脑收到的帧率分别统计。正式标定/测距使用完整输入模式，不能直接把抽样预览的像素和另一模式的标定混用。
