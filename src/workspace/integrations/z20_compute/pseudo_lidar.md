# 双目伪激光雷达点云

2026-10-26 已增加电脑端 YOLO26-depth 分支，用同一张真实录制图做了 n/m 两个模型与旧 SGBM 的对比。当前优先用这个分支查看连续可见表面，详见 [原因分析与实跑记录](report/reconstruction_review_20261026.md)和[对比图](artifacts/reconstruction-review-20261026/comparison.png)。传统双目模式继续用于几何诊断。

## YOLO26 深度与表面预览

本机已经准备好独立的 CPython 3.11 环境、YOLO26n/m 官方权重。双击本目录的 `run_reconstruction_preview.cmd`，或在本目录执行：

```powershell
build/reconstruction-venv/Scripts/python.exe -m z20_compute.pseudo_lidar --backend yolo26 --model build/reconstruction/models/yolo26m-depth.pt --npy build/navigator/scene-bgr.npy --output artifacts/yolo26-preview
```

输出在 `artifacts/yolo26-preview/frame-0000000000/`：`surface.ply` 是带三角面的彩色可见表面，`cloud.ply` 是彩色点云，`depth-preview.png` 是深度图，两个 NPY 分别保存原始预测与中位深度归一化结果。`latest.json` 保存实际输入帧序号和文件目录。PLY 可用 CloudCompare、MeshLab 或 Open3D 打开。

自己的单张图片用下面的入口，不需要板卡：

```powershell
build/reconstruction-venv/Scripts/python.exe -m z20_compute.mono_depth --image D:/your-picture.png --model build/reconstruction/models/yolo26m-depth.pt --output artifacts/my-depth
```

输入图片应保持原比例。默认焦距是为现有 640 像素宽测试图显式假设的 600 像素；换镜头或图片时，深度纹理仍可预览，三维形状的相机几何需用 `--focal-px` 设置并核对。当前导出坐标以每张深度图中位数为 1，不给它标米；模型原始预测另存，可在取得实测数据后做尺度校正。

后续板端恢复已有 JPEG 回传程序时，可运行：

```powershell
build/reconstruction-venv/Scripts/python.exe -m z20_compute.pseudo_lidar --backend yolo26 --model build/reconstruction/models/yolo26m-depth.pt --ssh-host 192.168.1.20 --output artifacts/yolo26-live --max-clouds 3
```

这一步只使用左侧主视图估计深度，右侧相机仍可供传统双目几何检查。模型放在电脑运行，板端相机持续采集，电脑推理期间只保留最新待处理帧。本轮已用保存帧重放板端 JPEG 协议验证，真实板端连续更新率待恢复设备后测量。

迁移到其他电脑时，用 Python 3.11 创建单独环境，按 `requirements-reconstruction.txt` 安装；权重从 [Ultralytics 官方发布页](https://github.com/ultralytics/assets/releases/tag/v8.4.0)取得 `yolo26m-depth.pt`。这份可选环境使用 CPU PyTorch，避免改动原工程依赖。新建环境中没有传统双目所需的 SciPy；传统分支仍用原来的开发环境。

这条电脑端通路使用领航者 J3 双目相机的左右画面，先从图像特征估计相对旋转，再做视差和三维反投影。相机间距在算法中设为 1，因此输出坐标的单位是 `baseline_lengths`。它适合演示物体前后层次和一个视角的可见表面；米制测距仍使用实拍标定及已知距离核对。

## 当前可直接复现的结果

在 `integrations/z20_compute` 目录执行：

```powershell
python -m z20_compute.pseudo_lidar --npy build/navigator/scene-bgr.npy --output artifacts/pseudo-lidar-20261025
```

输入是此前从真实领航者双目采集保存的 `720×1280` BGR 帧。程序输出 `cloud-0000000000.ply`、`disparity-0000000000.png` 和 `latest.json`。PLY 可在 CloudCompare 或 Open3D 中打开。视差图的黑色区域表示没有通过左右一致性等检查的像素。

`--focal-px` 默认 600，表示每路图缩放到宽 640 像素时的**假设**焦距；这个值不是镜头标定结果。改动它会改变点云的形状和深度。程序不会给这种结果标米或厘米。

## 接实板后连续接收

当前原系统没有双目观察器 UIO。先按 [领航者恢复记录](NAVIGATOR_BOARD.md)恢复已验证的专用 Linux、双目/NPU PL、相机初始化和采集；只使用已验证的 CLG400 双目固件。音频测试镜像与本通路无关，不要加载。板端需有 `/tmp/navigator-check/jpeg_stdout.py`，这是已归档的 15 秒 JPEG 诊断程序。

确认电脑能通过 SSH 访问板子后，在电脑运行：

```powershell
python -m z20_compute.pseudo_lidar --ssh-host 192.168.1.20 --output artifacts/pseudo-lidar-live --max-clouds 3
```

这条命令通过 SSH 读取板端的二进制帧序号／JPEG 流。电脑端只有一个最新帧槽：点云计算期间新帧替换旧帧，采集和传输不等待点云计算。每个成功的帧保存独立的 PLY 和视差 PNG；`latest.json` 记录序号、点数、单位及有效状态。纹理不足、匹配不足或视差无效时写入 `valid=false`，不把上一帧的点云当作当前结果。

JPEG 诊断流每路为 320×240，是从每路 640×720 采集环分别按横向 2、纵向 3 抽样得到。当前程序按宽度比例把假设焦距缩放到 300 像素。它只检验这个采集模式；换分辨率、裁剪或镜头后应重新检查图像配对和几何假设。

## 本轮证据与限制

2026-10-25，原始保存帧经新入口得到 53,279 点；同一真实帧按板端 `>II` 帧序号/JPEG 格式压缩，再交给流式入口，得到 19,028 点。两次均为电脑离线运行，后者验证的是传输格式与处理链路，并非本轮新鲜上板画面。程序测试覆盖流边界、最新帧替换、无效状态清空、真实录制图几何和端到端 JPEG 输入。

本次低分辨率流式结果保存在 `artifacts/pseudo-lidar-stream-20261025/`，包括 `cloud-0000000123.ply`、`disparity-0000000123.png` 和从该 PLY 绘制的 `cloud-preview.png`。预览呈现稀疏、断裂的可见表面；点数本身不代表几何精度。后续应换前后层次更丰富、有纹理且两镜头共同可见的场景检查。

本轮电脑未枚举开发板 USB 串口，PS 以太网适配器也显示断开，因此没有进行实时实板采集。此前实测双目采集约 28.6 帧/秒、JPEG 回传约 14 帧/秒；新伪点云更新率尚未实板测量。一个位置的点云只包含当前可见表面；多视角融合需要相机位姿估计和不同视角的重叠图像。
