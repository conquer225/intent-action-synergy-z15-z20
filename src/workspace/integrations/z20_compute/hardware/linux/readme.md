# Linux 接入文件

双目专用入口使用 `z20-stereo.dts`，运行步骤见 `../../STEREO_BOARD.md`。它在旧候选 PS 设备树上保留低 1 GiB DDR，划出 0x01000000 起、8294400 字节的 no-map 视频环；UIO map0 是 0x43C20000 观测寄存器，map1 是这一保留区域。两张映射只读，不依赖 u-dma-buf。相机由 Linux 启动前的独立程序初始化，随后保留 VDMA 与 HDMI 工作，再交给 U-Boot 和 Linux；这里移除了未启用的 I2C_GPIO 候选节点。

双目模块只导入 NumPy／OpenCV，不导入 SciPy 或四模型计算服务。原厂 Python 3.7／NumPy 1.17／OpenCV 3.4.3 已在 ARM QEMU 中完成 8 项取帧、采集和快照测试，以及 1.25 米独立视差算例；设备树也注册了两个 UIO 映射。完整分类服务仍受下面的驱动与依赖缺口约束。根文件系统打包进 RAM，单 FAT 分区镜像避免在 Windows 上手工建立 ext4，SD 分区保存标定和点云。

`z20-video-npu-candidate.dts` 从官方第4套 Linux 实验的设备树恢复 PS 部分，移除旧 PL 的 DRM、帧缓冲和音频节点，并添加当前 NPU 地址、DMA 分配节点及相机 EMIO I²C 候选节点。`bin/` 内的 DTB 已由 DTC 1.6.1 编译；它仍须与最终 XSA、时钟和视频初始化程序核对，不能直接当作配套启动包。

`bin/z20_integer_selftest` 为静态 ARMv7 hard-float ELF，来自现有 `hardware/hls/mlp.cpp` 和 `test_mlp.cpp`，使用 GCC 12.2.0 编译。它执行软件整数参考，不访问 NPU 或相机。电脑 QEMU 启动用户提供的官方 Linux 5.4 内核，运行此程序后输出六事务 PASS。测试将它作为 `/init`，返回0后内核因 PID 1 退出而 panic；QEMU 在60秒上限停止。日志见 `report/arm-qemu-console.txt`，该记录不代表实板或 PL 测试。

官方内核已启用 UIO、UIO_PDRV_GENIRQ 和 CMA；CONFIG_I2C_GPIO 未启用，u-dma-buf 也未提供。`u-dma-buf/` 保存固定提交源码、许可和摘要，须用与目标内核匹配的构建目录及 Module.symvers 编译。当前官方资料包没有完整内核构建环境。Qt 根文件系统中的 Python 3.7／NumPy 1.17 也未满足计算服务依赖。

## 用户态 NPU 接口

`z20_compute/linux.py` 提供 `UioRegisters` 和 `UdmaAllocator`。前者核对 sysfs 的基址、大小及偏移；后者核对低1 GiB DDR 地址，分配64字节对齐且不重叠的缓冲，并通过上游驱动的原子 sysfs 请求执行缓存同步。Linux 下设备文件采用独占 flock，缓冲不会作为可修改 NumPy 视图逸出。

下列命令供匹配镜像和硬件就绪后使用。先从 sysfs 核对设备名；示例中的 uio0 不保证是实际编号。

```sh
python -m z20_compute serve --models artifacts/models --backend pl \
  --uio /dev/uio0 --udmabuf /dev/udmabuf0 --npu-base 0x40000000
```

不指定 `--backend pl` 时使用软件整数参考。PL 启动前检查 idle；超时或启动后寄存器失联会保留 DMA 缓冲并停止继续推理。恢复前须确认 PL 已复位，不应卸载驱动、重新分配该内存或仅重启服务冒充硬件复位。

视频使用独立 VDMA 通路。这里的 NPU 分配器不负责视频初始化、帧同步或旁路快照。双目专用 `StereoUIO` 与硬件观测模块负责完整帧和覆盖检查，不能用当前循环索引替代写入代数。
