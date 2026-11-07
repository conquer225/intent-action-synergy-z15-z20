# Z15 脑电识别与 Z20 地图绘制

意动协同将两条计算密集的数据路径放入 PL：Z15 连续提取脑电节律特征并完成左右手分类，Z20 把已有建模结果变成带遮挡关系和轨迹的显示帧。原有 EEGNet 试次、眼控执行、相机与 HDMI 管理继续沿用各自入口。

## 源码入口

| 内容 | 位置 |
| --- | --- |
| 定点合同与 Python 参考 | [fixed.py](../src/workspace/integrations/pl_accel/fixed.py)、[eeg.py](../src/workspace/integrations/pl_accel/eeg.py)、[mapping.py](../src/workspace/integrations/pl_accel/mapping.py) |
| HLS 硬件核 | [z15_fbcsp](../src/workspace/integrations/pl_accel/hls/eeg.cpp)、[z20_map](../src/workspace/integrations/pl_accel/hls/map.cpp) |
| 训练与参数导出 | [train.py](../src/workspace/integrations/pl_accel/train.py) |
| 缓冲、MMIO 与缓存同步 | [backend.py](../src/workspace/integrations/pl_accel/backend.py) |
| 单一 Cyton 读者接入 | [live.py](../src/workspace/integrations/pl_accel/live.py)、[pl_mi.py](../src/workspace/integrations/eeg_demo/brain_runtime/pl_mi.py) |
| 点云观察变换 | [view.py](../src/workspace/integrations/pl_accel/view.py) |
| 原建模清单与位姿轨迹 | [map_source.py](../src/workspace/integrations/z20_compute/z20_compute/map_source.py) |
| 硬件集成与 Linux 节点 | [integrate.tcl](../src/workspace/integrations/pl_accel/hardware/integrate.tcl)、[map.dtsi](../src/workspace/integrations/pl_accel/hardware/map.dtsi) |
| HLS / 平台构建 | [pl_accel.py](../build/pl_accel.py)、[pl_platform.py](../build/pl_platform.py) |

## Z15：滤波器组 → CSP → 窗口特征 → SVM

```text
现有 Cyton USB 串口读者：8 通道 × 250 Hz
  ├─ 原疲劳、情绪、EEGNet 试次与交互
  └─ 有界数据分送队列
      → PS：计数转 µV、Q8 量化、装载新样本
      → PL：3 频带 × 2 SOS × 8 通道
           → 每带 2 个 CSP 空间分量
           → 6 路滑窗和 / 平方和 / 方差
           → 每带归一化 log2 特征
           → 线性 SVM → 左 / 右
      → PS：状态 JSON、事件日志、MI 多任务页
```

### 输入与数值

通道顺序固定为 `F3/F4/C3/C4/T7/T8/O1/O2`。三个频带为 8–16、16–24、24–32 Hz，每带两级二阶节；每个输入采样点更新 48 个 SOS 节及 6 个 CSP 输出。默认窗口为 500 点（2 秒），每增加 125 点（0.5 秒）输出一个窗口结果；窗口支持 4–1024 点，步长支持 1–窗口长度。

| 量 | 表示 | 处理 |
| --- | --- | --- |
| EEG 输入 | µV × 2⁸，int32 容器，signed24 值域 | PS 按采集增益换算，按采样顺序装载 |
| SOS 系数 | Q28，3×2×5 | `b0,b1,b2,a1,a2`，归一化 `a0=1` |
| SOS / CSP 输出 | signed24，Q8 | 对称舍入，半值远离零，逐级饱和计数 |
| CSP 系数 | Q14，3×2×8 | 每带两个空间投影 |
| 方差 | 64 位累加，整数总体方差 | 保留分数均值的贡献，避免先构造 `N×平方和` |
| 特征 | Q12，6 项 | `log2(max(1,var_i))-log2(max(1,var_0)+max(1,var_1))` |
| log2 | 8 位尾数查表，Q12 | 整数指数加 256 项尾数表 |
| SVM | 权重 Q12，偏置及分数 Q24 | signed64 分数，`score>=0` 对应右手 |

归一化在每个频带的两个 CSP 分量之间进行。训练导出使用 `intent-fbcsp-v1 / per_band_pair_log2_v1` 合同，模型携带参数 SHA256、采样率、通道、频带与量化信息。导出器检查 SOS 极点稳定性、形状和值域。

### 训练与导出

将左右手试次整理成 NPZ：`trials_uv[N,T,8]` 为微伏数据，`labels[N]` 为 `0=左手、1=右手`，每类至少两个试次。试次中保留滤波预热段；训练器在每个试次复位后使用最后一个完整窗口。在线消费者则在连续输入上维护滤波及滑窗状态。

```sh
# 在恢复后的工程根目录执行
python -m integrations.pl_accel.train --input recordings/mi_trials.npz --output models/mi_fbcsp.json --window 500 --hop 125 --features 4
```

训练器用量化 SOS 传递函数估计正则化 CSP，选择每带两个特征向量，再用实际整数特征训练 L2 squared-hinge 线性 SVM。Fisher 特征选择在训练集内完成，标准化折入最终权重和偏置；未选维度的权重为零。JSON 元数据记录训练条数、所选特征、训练集分类统计和输入数据摘要。

### 实时接入

把恢复后的 `integrations/pl_accel` 与现有 `integrations/eeg_demo` 一起部署。将新核加入 Z15 当前整机设计，使用生成的配套 bit/HWH 后，在原采集服务参数后追加：

```sh
--pl-mi-model /home/xilinx/models/mi_fbcsp.json \
--pl-mi-hwh /home/xilinx/overlays/guardianloop_fbcsp.hwh \
--pl-mi-status /run/guardianloop/pl-mi.json \
--pl-mi-audit /home/xilinx/recordings/pl-mi.jsonl
```

`--pl-mi-ip` 默认 `z15_fbcsp_0`。HWH 入口读取已有平台的地址描述；省略该参数时读取 `PYNQ PL.ip_dict`。启动过程使用 MMIO 和 `allocate` 连接当前硬件。原串口读者继续唯一持有 USB 数据流，新消费者的 250 点有界队列按每批 10 点分送，独立线程以至多 50 点、且至多一个 hop 的批次调用硬件。

状态含 `label/class_id`、6 项特征、Q24 分数、样本和窗口计数、模型 SHA256、缓冲调用耗时及 `control_enabled=false`。现有 MI 多任务页的 `/api/multitask` 同步展示 `tasks.pl_mi`。原 EEGNet 仍负责既有提示试次与虚拟手动作；PL 分支提供独立识别结果及比较记录。

采样序号跳变、队列缺口、过期输入、重连及佩戴会话变化会撤销旧结果并重建窗口。发生数值饱和时撤销本窗并重新预热。初始化或工作线程故障写入独立状态，原采集消费者继续运行。

## Z20：已有几何 → PL 地图帧

```text
已有单目建模 / 标定双目 / 已知位姿融合清单
  → 点坐标 + RGB + 坐标单位 + 可选轨迹
  → 当前会话 / epoch / 序号绑定
  → PS 观察相机矩阵
  → PL Q16 变换与透视投影
       → 近远裁剪、深度测试、点覆盖
       → 线段裁剪、轨迹光栅化
  → 独立 DDR 帧 → 原 HDMI 显示所有者 / PNG 预览
```

接口支持 1–1280×1–720 帧、最多 65,536 个彩色点、1,024 个轨迹点及 0–2 像素覆盖半径。空间数据使用 Q16；每个顶点占 16 字节，包含 XYZ 与 `0xRRGGBB`。硬件清理帧及深度缓冲，逐点投影并保留最近深度，再用 Cohen–Sutherland 与 Bresenham 绘制轨迹。共享迭代除法器控制资源规模。

观察矩阵由 PS 根据点云中心、范围和三个观察方向设置，投影、遮挡和线段像素由 PL 生成。传输与结果保留源坐标单位、帧身份和米制标记。原单目可见表面使用相对深度单位；已知位姿融合使用世界坐标。

### 来源与切换

四模式空间页提供“原有建模显示”和“PL 地图绘制”两个选择。默认进入原有模式。切换时递增 epoch、清理旧显示结果，复用已有点云；几何包与 JPEG 分别接收和检查。切回后沿用原来的图像与 Three.js 展示流程。

板端在原 `headless_server` 参数后追加 `--pl-map` 即开放选择；标准启动器对应：

```sh
python run_visual_demo.py board --pl-map
```

电脑端继续使用原模型和相机来源。加载已有 `fuse` 命令使用的 `depth_npz + camera_to_world` 清单时：

```sh
python run_visual_demo.py pc --map-manifest captures/views.json
```

清单沿用原结构：

```json
{"views":[{"depth_npz":"view_0/depth.npz","camera_to_world":[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]}]}
```

每份 NPZ 含原有 `xyz`、`valid_mask`。加载器复用既有刚体变换及体素融合，将各位姿的平移分量串成轨迹。融合结果以确定步长采样到显示上限。九页双目入口也能使用 `--pl-map --map-mode pl`，直接把原相机产生的点云送往同一核；`HeadlessPipeline.set_map_mode()` 负责切回。

### 内存与 Linux

新增 AXI 控制地址为 `0x83c40000`，位于 PS GP1 地址窗口；独立 DDR 端口使用 HP2，FCLK2 为 100 MHz。将 [map.dtsi](../src/workspace/integrations/pl_accel/hardware/map.dtsi) 合入 Navigator 当前设备树：

| 资源 | 配置 |
| --- | --- |
| 控制 UIO | `navigator-map`，0x83c40000，64 KiB |
| DMA UIO | `navigator-map-dma`，0x06000000，16 MiB |
| DDR 预留 | `/reserved-memory/map@6000000`，启动时 `no-map` |
| 720p 最大缓冲总量 | 8,437,952 字节，另按 64 字节对齐 |

该地址区独立于既有视频、NPU 和 HDMI 帧区。驱动检查 UIO 物理地址与预留节点一致、32 位地址范围、缓冲对齐和互不重叠。命令超时后保留缓冲所有权，硬件复位确认后释放。

## HLS 与平台构建

工具为 Vivado / Vitis HLS 2023.1。构建输出放入新的短英文路径。在仓库根目录执行：

```sh
python -X utf8 -B build/pl_accel.py eeg --output C:/work/pl_eeg --tool D:/vivado/Vitis_HLS/2023.1/bin/vitis_hls.bat --cosim
python -X utf8 -B build/pl_accel.py map --output C:/work/pl_map --tool D:/vivado/Vitis_HLS/2023.1/bin/vitis_hls.bat --cosim
python -X utf8 -B build/pl_platform.py eeg --ip C:/work/pl_eeg/kernel/solution/impl/ip --output C:/work/pl_z15 --tool D:/vivado/Vivado/2023.1/bin/vivado.bat
python -X utf8 -B build/pl_platform.py map --ip C:/work/pl_map/kernel/solution/impl/ip --output C:/work/pl_z20 --tool D:/vivado/Vivado/2023.1/bin/vivado.bat
```

前两条执行 C 仿真、综合、Verilog 联合仿真和 IP 导出，并记录源码 SHA256。后两条构建 PS 兼容性平台，验证新增接口、原控制地址保留和整合后的逻辑综合。

原 Z15 XPR 的构建方式为：

```sh
python -X utf8 -B build/pl_platform.py eeg --ip C:/work/pl_eeg/kernel/solution/impl/ip --project C:/work/z15_original/hdmi_audio.xpr --output C:/work/pl_z15_original --tool D:/vivado/Vivado/2023.1/bin/vivado.bat
```

工具以只读方式打开原 XPR，复制源文件与设置到新工程，再加入新核并保留原顶层。Windows Codex 运行时可在构建命令前加入 `python -X utf8 -B build/run_unpacked.py`，入口见[构建说明](../build/README.md)。

接入已有整机 BD 时，为 `pl_platform.py` 传入 `--bd-tcl`、对应 `--ip-repo`、RTL `--source` 和精确板型的 `--xdc`；`--implement` 执行布线、bitstream 和带 bit 的 XSA 导出。也可在已有 BD 中使用：

```tcl
source integrations/pl_accel/hardware/integrate.tcl
pl_accel::attach eeg C:/work/pl_eeg/kernel/solution/impl/ip
# Z20 对应：pl_accel::attach map C:/work/pl_map/kernel/solution/impl/ip
```

集成器使用空闲的 GP1、HP2、FCLK2/RESET2，检查精确器件、控制地址冲突、原外部端口和原地址保留。Z15 地址为 `0x83c50000`。每块板各自加入一个新核。

## 内存接口与寄存器

两核使用 AXI4-Lite 控制及 AXI 内存主接口。指针寄存器由低 32 位及紧随其后的高 32 位组成，控制寄存器 0x00 使用 HLS `ap_start/ap_done/ap_idle`。

| 核 | 偏移 | 内容 |
| --- | --- | --- |
| EEG | 0x10 / 0x20 / 0x30 | samples / params / result 指针 |
| EEG | 0x40 / 0x48 | 新样本行数 / reset |
| Map | 0x10 / 0x20 / 0x30 / 0x40 / 0x50 | vertices / params / frame / depth / stats 指针 |

EEG 参数为 94 个 int32：0–7 是 magic、ABI、窗口、hop、8 通道、3 频带、2 分量、250 Hz；8–37 为 SOS，38–85 为 CSP，86–91 为 SVM，92–93 为 signed64 偏置。每次调用传入 0–64 行，且行数不超过 hop。reset 时清状态并装载模型，持续运行时检查模型身份。

EEG 结果为 16 个 int32：0 magic；1 flags（bit0 新结果、bit1 有效、bit2 饱和、bit3 合同错误）；2–3 采样/窗口计数；4 类别；5–6 signed64 分数；7 饱和累计；8–13 六项特征；14–15 保留。

Map 参数为 32 个 int32：0 magic、1 ABI、2–5 宽/高/点数/轨迹点数、6–8 近/远/半径、9–11 背景色/轨迹色/序号、12–23 观察变换 3×4、24–27 `fx,fy,cx,cy`、28–31 保留。统计为 16 个 int32：magic、错误、可见点、裁剪点、轨迹段、轨迹像素、序号及保留项。帧和深度各使用 `width×height` 个 int32。

PS 返回的耗时覆盖 MMIO 轮询、缓存处理及结果复制，字段 `timing.scope` 标识此口径。HLS 联合仿真的周期记录见下节。

## 构建与数值记录

| HLS 核，目标 100 MHz | LUT | FF | DSP | BRAM18K |
| --- | ---: | ---: | ---: | ---: |
| Z15 `xc7z015clg485-2` | 14,658 | 10,768 | 55 | 25 |
| Z20 `xc7z020clg400-2` | 14,251 | 11,314 | 42 | 14 |

以上为 HLS 综合估算。原整机合入后，Z15 综合占用 23,930 LUT、29,323 FF、66 DSP、88 个 BRAM36；Z20 占用 29,206 LUT、38,946 FF、48 DSP、20.5 个 BRAM36。对应源码摘要、综合报告和 RTL 联合仿真记录保存在 [pl](pl)。EEG 算例覆盖恒等算例、实际三频带系数、连续输入、重叠窗口及模型身份变化；Map 算例覆盖前后遮挡、无效深度、边界裁剪和跨屏轨迹，随机场景的 2,961 个像素逐个比较。

另一个 21,600 点、80 点轨迹的 720p 场景使用实际 HLS C++ 源码在电脑生成三视角帧，三个视角均与独立整数参考逐像素一致。重建数字与画面：

```sh
python -X utf8 -B build/pl_vectors.py --check
python -X utf8 -B build/pl_demo.py --output C:/work/pl_demo
python -X utf8 -B -m unittest discover -s sim -p "test_pl_*.py" -v
```

`pl_demo` 产出 PNG、三视角 GIF、脑电特征 CSV 和数值比较 JSON。测试覆盖定点数值、训练导出、真实 C++ 接口、缓存/缓冲所有权、串流复位、几何 socket、两种显示流水及切回原帧。

## 来源

参考 [fpga_eeg_rehab](https://github.com/Xsingh-Luo/fpga_eeg_rehab) 的滤波器组、CSP、方差/对数及 SVM 组织；参考 [fpga-orb-slam](https://github.com/ymmz2333/fpga-orb-slam) 与 [zynq-ultrascale-graphics](https://github.com/yilives/zynq-ultrascale-graphics) 的投影和 PS/PL 分工。新增核、训练导出、驱动及数值合同采用本工程独立实现；归属和许可范围见[第三方说明](third_party.md)。
