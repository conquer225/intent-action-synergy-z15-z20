# Z15＋Z20 离线开发模块

当前四模式无线视觉入口：[使用说明](VISUAL_DEMO_GUIDE.md)，录制按[178秒拍摄清单](SHOOTING_PLAN.md)。Z15 收缩为原编号1/2/3三图像、疲劳/情绪两页；新增眼控入口、电脑渲染回传和Z20本地NPU页。候选包不含固件，实板无线、眼控与HDMI需另行验收；下方各旧演示仍保留。

固定图片最小演示入口：[FIXED_PHOTO.md](FIXED_PHOTO.md)。当前电脑可切换人物、狗、背景三张照片，以模板权重复用共享整数NPU算法；双击 `start_fixed_photo_demo.cmd` 启动。结果只覆盖登记图回忆，按键/HDMI板端接入另行实施，不接Z15眼控菜单。

2026-10-24 已恢复实板联调。实际板为领航者ATK-DF7010/7020P，双目接J3；新版CLG484 Z20候选不能用于该板。领航者PL临时加载、NPU整数对照、双目采集和电脑回传已实测；用户暂缺标定，米制测距与点云待验收。先读 [本次实板记录](report/board_20261024.md)。

用户要求无标定继续尝试后，新增 [假设参数点云试验](report/navigator_nominal_trial.md)：真实录制图生成53,589点预览，形状和米制尺度尚未验证；该实验与正式标定测距入口分开。

本目录实现新增 Z20 的计算程序和共享全连接 NPU。原 Z15 的采集、控制、现用模型和启动文件保持原样；158 个原始文件的 SHA256 保存在 `report/z15_baseline.json`。

当前优先完成双目：连续左右显示、只读完整帧旁路、棋盘格采集、ARM 本地测距和点云导出。当前领航者使用 [NAVIGATOR_BOARD.md](NAVIGATOR_BOARD.md) 中的专用产物和恢复步骤；[STEREO_BOARD.md](STEREO_BOARD.md) 保留此前新版目标记录。构建及测试证据放在 `report/`。四个新分类器仍需实际标注数据训练；合成数据只验证流程和数值。

## 运行与验证

本机在工程根目录运行：

```powershell
Set-Location D:\fpga\z15_multimodal
python integrations/z20_compute/verify_offline.py
python integrations/z20_compute/build_hls.py
python integrations/z20_compute/run_cosim.py
python integrations/z20_compute/build_bundle.py
```

日常运行命令从本目录执行：

```powershell
Set-Location D:\fpga\z15_multimodal\integrations\z20_compute
python -m z20_compute --help
python -m z20_compute doctor --models artifacts/models --calibration artifacts/calibration/calibration.json --board-review examples/board-review.json
```

Python 依赖为 NumPy、SciPy、OpenCV，依赖声明见 `requirements.txt`。本机验证环境版本写入检查报告；ARM 板端依赖需匹配实际 Linux 镜像。点云 ICP 单独依赖电脑上的 Open3D，基础点云导出和已知位姿合并不需要它。默认命令不会连接硬件、烧写或修改 Z15 启动目录。

## 数据和四个模型

| task | 输入 | 输出标签，顺序对应 0／1／2 |
|---|---|---|
| emotion | 原 SEED 连续预处理输出的 180 维特征 | negative／neutral／positive |
| fatigue | 原校准与滤波后的 20 维 DE 特征 | awake／mild／severe |
| face | 固定 ROI 缩小为 32×32 灰度图，归一化为 0～1 | person_1／person_2／person_3 |
| sound | 16 kHz、1 秒单声道声音，20 频带的均值和标准差，共 40 维 | clap／whistle／knock |

四个模型分别训练，共用 D→32 ReLU→3 的整数核心。训练、归一化统计和量化标定只使用训练组；验证组选模型，测试组单独评价。按录制会话划分，不随机拆开同一次录制的重叠窗口。疲劳的三档真实标签需另行标注，原 HGB 输出只保留为对比基线。

`examples/face-manifest.json` 是格式示例，需补齐每个划分中的三个人及实际路径。音频记录的 kind 为 `wav`；脑电记录为 `eeg`；已有特征为 `features`。每条记录必须写明 label、group 和 split（train／validation／test）。音频 WAV 支持单声道 PCM16 或归一化 float32，按完整的一秒片段取样，不足一秒的尾部舍弃。脑电 NPZ 包含 samples_uv（N×8）、sample_rate_hz=250、channels，顺序为 F3、F4、C3、C4、T7、T8、O1、O2。每个 EEG 文件从原校准流程重新开始，因此应保留足够的校准和连续有效录制时间。

```powershell
python -m z20_compute prepare --manifest data/manifest.json --output artifacts/dataset.npz
python -m z20_compute train --task face --dataset artifacts/dataset.npz --output artifacts/models/face --epochs 100
```

模型目录保存 model.json、weights.npz 和 metrics.json，包含来源、预处理版本、类别顺序、权重摘要、混淆矩阵、拒绝数与定点／浮点一致率。合成模型会标为 synthetic，默认服务拒绝加载。相同最高分的输出无效；空白、过暗、过曝 ROI 与静音会被输入检查拒绝。固定框内的背景纹理仍可能被三类模型误分，后续必须用真实空框和未录入人员样本检查拒识，不能将三类闭集准确率当成拒识能力。

## 双目测距与点云

相机保持固定安装。电脑用同步左右图做棋盘格标定，棋盘格参数是内角点数量，方格边长以米填写。至少十组有效角点；实际采集应覆盖不同位置、深度和倾斜角度。标定文件绑定分辨率和 capture-mode，换镜头、变焦、改变左右关系或采集模式后重新核对。

```powershell
python -m z20_compute calibrate --manifest data/pairs.json --columns 8 --rows 6 --square-m 0.025 --capture-mode mc5640d-gray-320x240 --output artifacts/calibration
python -m z20_compute depth --calibration artifacts/calibration/calibration.json --capture-mode mc5640d-gray-320x240 --left data/left.png --right data/right.png --output artifacts/view001
python -m z20_compute fuse --manifest data/clouds.json --output artifacts/merged
```

`depth` 使用板端与电脑共用的 StereoBM 程序，默认 64 档视差、15 像素窗口、中心 32×32 测距框，输出米制距离、有效状态、depth.npz 和 cloud.ply。ROI 可用 `--roi x y width height` 改动。至少十个有效深度点才输出中位距离，默认保留 0.1～10 米；这是软件筛选范围，实际可测范围需用板上图像和已知距离确认。

`fuse` 读取深度文件与每帧 camera_to_world 位姿，执行米制坐标变换和体素合并。可加 `--icp` 用 Open3D 微调有重叠的相邻视角，低重合率或误差过大即终止。位姿示例中的平移量只是格式示意。首期适合静止物体、缓慢移动相机和少量视角，输出为可见表面的点云；实时房间建图暂缓。

## 声音与模拟输出

```powershell
python -m z20_compute audio --wav data/sound.wav --filtered --output artifacts/audio
python -m z20_compute audio --wav data/sound.wav --model artifacts/models/sound --output artifacts/audio
```

输出文件包含 40 维特征、FFT 频率／幅度、音频 DAC 码、频谱 DAC 码和频谱同步数组。FFT 为 1024 点，频谱使用固定 −100～0 dBFS 映射到 0～255，避免每帧自动缩放改变含义。DAC 音频按无符号八位中点 128 编码，滤波模式保留跨块 FIR 延迟状态。频谱模式需循环发送完整冻结数组，切回音频在完整块边界提交。

`hardware/rtl/z20_dac_stream.sv` 消费 9 位流：低八位为 DAC 码，第八位为扫描起点。采样使能到来时取值，欠载输出中点、清除扫描标记并累计欠载次数。它与 ADC 采样、时钟输出和实际管脚约束的连接见硬件说明。当前离线生成的数据文件尚未经过真实 DAC 输出。

## 异步调度与双板通信

`RuntimeCoordinator` 分别维护 EEG、前台分析和按需音频。前台切换只使旧的人脸／双目结果失效。`AnalysisWorker` 只有一个正在执行任务和一个待处理最新任务，分析繁忙时替换旧等待任务。`SnapshotReader` 仅复制最近完整帧，复制前后比较写入代数、写入索引与完成序号；检测到变化就丢弃该次复制。

采集／VDMA／显示由板级视频工程持续运行，程序没有逐帧 present 回调。快照必须是拥有独立存储的只读数组；不能把 VDMA 显示缓冲直接交给分析。双目专用 StereoUIO 通过只读、非缓存映射读取保留帧缓冲；硬件观察器提供两路写入代数、完成序号与时间，复制前后重新核对。模拟器已测试这些接口，实际相机采集另行板测。

原 Z15 单一脑电读取器收到微伏样本后，调用 `EEGPublisher.offer_samples()` 发送旁路副本。它不打开串口，不修改原作品的控制状态。板端 `BoardSession` 接收 EEG 和模式命令，`pump()` 异步收集结果。连接超时、序号缺口或队列溢出会使 EEG 状态无效并重建连续处理；结果过期、模式切换和断开连接均清除旧标签。

可先在电脑启动 EEG 计算服务，默认仅监听回环地址：

```powershell
python -m z20_compute serve --models artifacts/models
```

该入口默认使用软件整数参考。新增 `--backend pl --uio /dev/uio0 --udmabuf /dev/udmabuf0` 可显式选择 Linux UIO／u-dma-buf 适配器，接入同一调度器；实际编号先从 sysfs 核对。地址、缓存同步和超时内存保留已通过电脑映射文件测试，驱动及镜像仍需匹配。详见 [Linux 文件说明](hardware/linux/README.md)。运行结果记录实际 backend，避免把软件计算计为 PL 加速。真实板间运行时显式指定有线网口地址；这是实验室受控网络协议，未加入身份认证与加密。

## 检查证据与后续

双目交付步骤见 [STEREO_BOARD.md](STEREO_BOARD.md)，当前结果见 [实施状态](report/implementation_status.md) 和 [双目优先实施](report/stereo_priority.md)。本轮以官方第 37 个双目 HDMI 实验为基础，在副本中升级 Vivado 2023.1、接入共享 NPU 与被动帧观察器。相机、VDMA 与 HDMI 保持独立运行，ARM 从只读旁路取帧。

双目专用启动链为 FSBL、PL、视频初始化程序、U-Boot、Linux。设备树移除旧 DRM／帧缓冲驱动，保留时钟与视频内存；根文件系统使用原厂 Python 3.7、NumPy 1.17、OpenCV 3.4.3，仅运行双目模块。它与需要现代 Python／SciPy 和 NPU DMA 驱动的完整四模型服务分别部署。双目镜像中包含 NPU 硬件与寄存器映射，尚未运行四模型 PL 推理。

report/offline_verification.json 记录新增模块、原视频回归及 158 个基线文件检查；arm_stereo_linux.json 记录 ARM 模拟器中的取帧／保存测试与已知视差测距。stereo_hardware_build.json 记录当前 bit／XSA、布线后时序与观察寄存器保留检查。stereo_linux_boot_verification.json 检查四个分区的头部校验、内存范围和匹配 PL 载荷；stereo_sd_image.json 与 stereo_sd_qemu.json 分别记录最终磁盘文件摘要和从 U-Boot 开始的启动仿真。

Vivado／XSim 在本机仍有退出阶段异常。工具退出码、成功完成标记、文件 CRC、源文件摘要和独立检查分别保留，不把导出文件解释为整个工具流程正常退出。已约束路径的内部时序与软件仿真也不代表真实相机帧率、电气时序或测距精度。

旧 artifacts/z20-hardware-candidate.zip 为不含帧观察器的早期候选，不能用于当前双目取帧。双目当前产物与摘要以对应报告和板测文档为准；artifacts/z20-offline.zip 是源码与 HLS IP 包，不含 SD 镜像。官方来源及先前检索记录见 report/source_inventory.md、official_vitis_integration.md、linux_integration.md 和 board_adaptation.md。

接板后先单独验收双目连续画面、稳定取帧、实拍标定、已知距离和局部点云。四模型真实训练、NPU 板测、ADDA 硬件、原页面接入和双板整机回归仍在总体任务中；MC8008 的同时连接方案后排，FMC 不是双目启动条件。
