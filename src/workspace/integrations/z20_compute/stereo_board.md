# Z20 双目板测

2026-10-23 实物核对：当前接入的是领航者 ATK-DF7010/7020P，XC7Z020、CLG400；双目接照片左侧竖排 J3。下文 J22、CLG484 硬件与 `z20-stereo-sd.img` 属于此前按新版 Z20 资料制作的候选，不能烧到当前实板。领航者进度见 [NAVIGATOR_BOARD.md](NAVIGATOR_BOARD.md)。

2026-10-24 领航者已执行临时加载、真实采集、电脑预览和像素视差诊断，具体结果见 [实板记录](report/board_20261024.md)。恢复联调使用上述领航者入口；下面的SD烧写步骤仅供原新版目标追溯。

先用双目摄像头占用 J22，接 HDMI 显示器和 USB 串口。MC8008 暂时拔下；两个模块各自可以直插配套接口，但不能同时占用同一个 J22。断电时插拔，按套件排针方向连接。

本次提供 SD 镜像候选、匹配 bit／XSA、启动程序和 Python 源码。电脑离线与 ARM 仿真验证记录在 `report/`。真实相机曝光、画面帧率、测距误差和电气时序要在板上确认。

## 启动

使用 `artifacts/z20-stereo-sd.img`，将镜像写入一张备用 SD 卡。烧写会覆盖所选卡的原内容，先备份并核对盘符。镜像约 512 MiB，建议使用容量至少 1 GB 的卡；不要把整个 `.img` 当普通文件复制到卡里。

镜像只有一个 FAT 分区。它包含 BOOT.BIN、zImage、system.dtb、boot.scr、rootfs.gz；Linux 根文件系统加载到内存，沿用原厂 Qt 包中的 Python 3.7、NumPy 和 OpenCV。关机后根目录中的修改不会保留，标定图片、参数和点云要存到 SD 分区。

按 Z20 手册设为 SD 启动，串口设为 115200、8N1。上电后应依次出现：

```text
Z20_DUAL_VIDEO_BRINGUP
CAM0 init=0 size=640x720
CAM1 init=0 size=640x720
VIDEO_START_CONFIGURED
VIDEO_HANDOFF_UBOOT entry=04000000
Z20 stereo: retain running PL video, boot matched Linux
Z20_STEREO_RAM_ROOT_READY
... login:
```

相机初始化返回 0 表示该步骤成功。`VIDEO_START_FAILED` 会停在失败阶段，保留串口日志；不要通过跳过检查把失败改成成功。首次 Linux 启动包含原厂服务和 SSH 主机密钥生成，需等待登录提示。账号未在本轮修改。此次提供的密码与所选 Qt 原厂根文件系统内 root、petalinux 的配置均不匹配，普通密码登录尚未完成；这不代表未来实板上已有系统使用相同密码。当前程序检查通过隔离 QEMU 的维护启动完成，交付镜像没有增加免密入口或修改账号。

先只看 HDMI 的左右画面，让手在镜头前移动。此时不启动任何分析。登录后确认设备：

```sh
for p in /sys/class/uio/uio*; do echo "$p: $(cat "$p/name")"; done
mkdir -p /mnt/sd
mount /dev/mmcblk0p1 /mnt/sd
```

列表中应有 `z20-video-observer`。如果 SD 已自动挂载，使用实际挂载目录。下面假定它是 `/mnt/sd`。

## 标定采集

先使用静止棋盘格，左右镜头都要完整看到棋盘。每次采集间隔 2 秒，改变棋盘的位置、距离和倾斜角，至少保留 20 对清晰图像。

```sh
z20-stereo record --pixel-order BGR --output /mnt/sd/pairs --count 20 --interval 2 --seconds 180
sync
```

采集和测距使用相同的 1280×720 左右合成图，再拆成两幅 320×240 灰度图。BGR 是本候选的初始参数，板测时用红蓝色块确认 DDR 字节顺序；如果需要改为 RGB，采集和测距两处一起改，重新标定，不能混用旧参数。图像必须来自当前两路完整帧，复制期间被覆盖会丢弃。

把 `pairs` 文件夹复制到电脑。在本工程 `integrations/z20_compute` 目录运行下例；9、6 是棋盘内部角点数，0.024 是打印后实测的单格边长（米），按实际棋盘修改：

```powershell
python -m z20_compute calibrate --manifest D:/stereo/pairs/pairs.json --columns 9 --rows 6 --square-m 0.024 --capture-mode z20-sbs-640x720-BGR-gray-320x240 --output D:/stereo/calibration
```

查看 `calibration/calibration-report.json` 中被拒绝图片和误差，保留独立拍摄的已知距离作为验收数据。把 `calibration/calibration.json` 放回卡的根目录。

## Z20 测距与点云

```sh
z20-stereo depth --pixel-order BGR --calibration /mnt/sd/calibration.json --output /mnt/sd/depth --seconds 600 --cloud --interval 2
```

测距在 Z20 ARM 本地运行 StereoBM。默认测量分析图中心 32×32 区域；结果打印到串口，并原子更新 `depth/depth.json`。`cloud.ply` 保存最近有效点云，单位为米。无有效视差、数据过期或程序退出时，JSON 中的距离清空；旧点云文件作为已保存快照保留，不能当实时状态读取。

`processing_ms` 是单次处理时间，另行记录实际结果更新率。HDMI 由 PL 和 VDMA 连续输出，分析读取只读映射，停止或让分析变慢都不应停止画面。左右完成序号配对只确认帧缓冲归属，不代表两个传感器同时曝光；首轮先测静止目标。

每次点云保存还会生成 `depth.npz` 和 `snapshot.json`，记录序号、时间、单位及两个数据文件的摘要。停止分析后再复制这一组文件，作为一个已保存视角。分别使用 `--output /mnt/sd/view001`、`view002` 保存少量静止视角，避免把相机移动期间的连续帧当成同一个视角。

电脑已建立 `build/pc-venv` 的 Python 3.11 环境，装有 Open3D；重建环境使用 `requirements-pc.txt`。参考 `examples/clouds.json`，在点云目录写 `clouds.json`，各项 `depth_npz` 指向视角目录中的 `depth.npz`。填写米制相机位姿；使用 ICP 时填写合理的初始估计，保留充分重叠，先做小幅、缓慢移动的受控场景。

```powershell
.\build\pc-venv\Scripts\python.exe -m z20_compute fuse --manifest D:/stereo/clouds.json --output D:/stereo/merged --icp
```

输出 `merged.ply` 与配准报告。Open3D 的已知位姿恢复和无重叠拒绝测试已在电脑执行，真实场景拼接另行验收。它是局部 ICP 拼接，尚未提供移动环境的全局位姿估计或 SLAM。

在电脑上打开合并点云：

```powershell
.\build\pc-venv\Scripts\python.exe -c "import open3d as o; cloud=o.io.read_point_cloud(r'D:/stereo/merged/merged.ply'); o.visualization.draw_geometries([cloud])"
```

## 一次板测需要记录的结果

保存上电串口日志；确认左、右画面顺序与颜色；分别记录相机帧率、HDMI 刷新率和测距更新率。在分析暂停、延迟一秒、进程退出时观察 HDMI，核对它始终连续。

在至少三个已知距离放置有纹理的平面目标，记录标尺距离、输出距离、有效率和处理耗时。移开目标、遮住镜头或对准白墙，检查距离被清空。观察模块故障时会拒绝继续取帧，原视频仍运行；收集日志后重新上电再测。

当前硬件使用与官方实验一致的两路 PCLK 普通布线例外，外部输入／输出延迟尚未完成实测约束。内部时序报告和 QEMU 启动通过分别说明内部实现与软件流程，实板结果填写到 `examples/stereo-board-results.json`。

## 本轮系统内检查

report/stereo_maintenance_qemu.json 记录隔离仿真检查：从相同内核、设备树和 rootfs.gz 以维护 shell 启动，运行已安装的 z20-stereo 命令，核对 OpenCV／NumPy、UIO、SD 挂载和缺少 PL 时的拒绝行为。结果通过，SD 镜像摘要不变。它跳过普通认证与系统服务启动，不代表已成功用密码登录；常规启动至登录提示的证据另见 stereo_sd_qemu.json。
