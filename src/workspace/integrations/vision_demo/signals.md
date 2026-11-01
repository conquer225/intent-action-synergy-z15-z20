# 我们意念合一：PL_KEY1 脑电与音乐演示

当前完整包为 `GuardianLoop_Submission_20261025.zip`，已合并后续板端修复。使用、安装与回退优先阅读 [修复合并版说明](RELEASE_20261025.md)；下文保留各历史修订当时的状态。

## 2026-10-20 热力图修订

本次修改疲劳、情绪两页与脑电全景；保留暖金主题，减少说明文字、扩大波形与特征图。网页四页直接显示同一套 1280×720 HDMI 渲染结果，图表没有鼠标交互。PL_KEY1 四页循环和 PL_KEY0 图像入口保持。

疲劳页显示八通道原始／滤波曲线、显示支路的时频能量和四通道五频段的 20 项微分熵。全部波形共用一个明确标出的微伏量程。时频图仅取现有 50 Hz 显示数据，64 点 Hann、4 点步进、八通道功率均值，范围 1–25 Hz，色标为相对 1 μV²/Hz 的 dB，固定 −8 至 10 dB 并饱和截色。它属于显示计算；原模型仍在 250 Hz 数据上提取五频段特征。

情绪页将原模型已经计算的 105 项特征按五频段还原成五张六通道对数协方差矩阵。严格逆转原上三角展开与非对角 √2 权重，顺序 F3/F4/T7/T8/O1/O2；保留符号、统一对称色标，不重新估算协方差或运行分类。各页保留真实记录来源、时间、状态、窗口和必要数值，失效后清除旧结论和信号。

新交付为 `GuardianLoop_Submission_20261020_r2.zip`，安装入口仍为 `presentation_release/bundle`。安装与回退步骤沿用下文；完整检查见 [热力图修订记录](report/heatmap/verification.md)。这轮没有接板部署。


2026-10-20 展示版。PL_KEY1 循环进入疲劳分析、情绪分析、脑电音乐联动、音乐音频分析；PL_KEY0 返回原十种图像模式。四页共享脑电时间轴，切页保持连续；原 PS 开始／暂停键或手机返回主页退出并停止音乐。HDMI、网页与手机界面统一为奶油白、淡黄与香槟金主题。

疲劳页显示八通道原始／滤波波形、五频段二十维特征、八秒窗口与分类。情绪页显示十二秒窗口、一百零五维协方差特征及原始分类。音乐联动页展示状态到选曲的过程；音频页使用播放器报告位置对应的样本，显示立体声波形、频谱、瀑布图与频段能量。

## 使用

打开界面即进入 LEMON 真实记录的处理展示。本轮没有实时采集选择入口，既有实时后端保留供后续工程接入。四页数据说明保留出处，主界面不显示开发后端和测试信息。

```powershell
python integrations/vision_demo/preview_signals.py --port 9130
```

打开 <http://127.0.0.1:9130>。音乐联动页点击“播放音乐”允许浏览器发声；“暂停展示”暂停脑电时间并停止音乐，“重新开始”清除旧选曲，从记录起点重放。电脑端四页、脑电全景、综合控制台、HDMI 画廊分别为 `/`、`/eeg-demo`、`/console`、`/gallery`。本地控制台的执行端保持不可用，不向硬件发送命令。板端正式服务沿用现有控制台。

板端按 KEY1 直接开始同一段记录；四页之间切换不会重置。需要重播时退出后重新进入，也可执行：

```bash
sudo /usr/local/share/pynq-venv/bin/python3 integrations/vision_demo/select_signal_source.py \
  --media-root /home/xilinx/gl-hdmi-live-20261008-ea117349 replay
```

该命令只更新本地记录重播请求，不调用实时采集、校准或执行端。播放结束后撤销结果；原模型和控制协议保持。

## 素材和音乐规则

LEMON sub-010002 为公开真实静息 EEG。下载源、截取范围、原始头文件、单位、通道索引和摘要在 `local/signal_materials/lemon/source.json`。原始 2500 Hz、0.1 μV 整数数据选取 F3、F4、C3、C4、T7、T8、O1、O2，保留原参考，抗混叠降采样至原算法使用的 250 Hz。前 120 秒按原流程校准，后 180 秒演示；波形显示另降采样为 50 Hz。模型、滤波、质量检查和分类实现保持原文件摘要。静息记录缺少本工程疲劳／情绪真值，其分类输出用于处理流程演示。

数据使用 CC BY 4.0；出处为 Babayan 等，2019，Scientific Data 6:180308，DOI [10.1038/sdata.2018.308](https://doi.org/10.1038/sdata.2018.308)。本包保存来源与改动说明。

三首本地器乐由 `prepare_signal_music.py` 生成，附 CC0-1.0 许可、生成方式、文件摘要，无外部录音。舒缓、平稳、明快分别对应负向、中性、正向；严重疲劳优先舒缓。进入第三页后才启用选曲，两次不同实际推理窗口确认同一组才能播放；换组至少相隔二十秒，淡出／淡入约一秒。有效信号中断超过三秒时淡出停止，恢复后重新确认。每首约四十八秒，播完等待后续换组，界面如实报告结束，不虚构持续输出。播放器状态来自实际会话回报。

## PS、PL 和播放分工

PS 复用原脑电摘要、模型和 PCM 会话，负责页面、选曲、Hann 加窗及频谱统计。新增 PCM 子程序保留原 FIFO 和 HDMI 音频通路，加入文件格式检查与采样级淡入淡出。原音频进程退出后四页播放器才能启动。

PL 新增 1024 点定点 FFT，基地址 `0x43c50000`，样本、实部、虚部窗口分别为 `+0x1000/+0x2000/+0x3000`，输出 FFT/N 的 513 个单边复数频点。分析支路独立线程，超时后停止复用该核；分析失败不会阻塞发声。原视频像素流水线保持连续流结构。播放位置为 FIFO 软件回报估算，实际 HDMI 声音延迟与同步需实测。

音频分析功能参考 [PYNQ-Z2 Audio Analyzer](https://github.com/VincentttWang/FPGA_SocChina_2025) 的波形、频谱、瀑布图与频段能量展示。FFT、适配和界面为本工程独立实现，没有复制其 GPL-3.0 源码或 bitstream。

## 离线检查与重建

依赖 Python、NumPy、SciPy、Pillow、OpenCV；Windows C 算例使用现有 MinGW。板端沿用 PYNQ Python 3.8、原字体与依赖，不需联网下载资源。完整 FPGA 重建还需要已有 Vivado/Vitis HLS 2023.1、原相机与 DVI IP、ARM 交叉编译器。

```powershell
$env:PYTHONPATH='integrations/vision_demo'
python -m unittest discover -s integrations/vision_demo/tests -v
python integrations/vision_demo/render_signals.py --output integrations/vision_demo/report/signal-preview
python integrations/vision_demo/run_audio_cosim.py --build local/audio_hls_20261020
python integrations/vision_demo/build_signal_hardware.py --output local/signal_hardware_NEW
python integrations/vision_demo/build_bundle.py --hardware local/signal_hardware_NEW --output local/signal_bundle_NEW
```

FFT 先按 `build_audio_hls.py --help` 构建，再运行上述协同仿真；束包校验已通过的 RTL 数值证据、源代码摘要和成对硬件摘要。Windows HLS 自动仿真脚本清空 PATH，复验工具检测该故障后执行同一套生成的 xelab/xsim 命令，再执行生成的 C 回检。自动启动失败与最终 RTL 通过分别留档。

## 安装、回退与板端验收

新包包含流式图像、四页演示和全部当前页面的主题资源。保留 S3、STM32 固件和蓝牙接线。正式脑电模型不属于安装写入项。

先停止显示，核实会话报告 `display_halted`、`buffers_released`、`original_restored` 均为 true；再停止原显示守护、媒体和采集服务。若板上仍是已记录的首版图像扩展，先用它的原备份严格回退：

```bash
sudo /usr/local/share/pynq-venv/bin/python3 integrations/vision_demo/install_vision.py \
  --media-root /home/xilinx/gl-hdmi-live-20261008-ea117349 \
  --brain-root /home/xilinx/jupyter_notebooks/guardianloop_pynq \
  --eye-root /home/xilinx/brain_eye_coexist_20261005/eye \
  --rollback /home/xilinx/gl-hdmi-live-20261008-ea117349/.eeg-demo-backups/install-5b1b2yt3
```

路径和备份必须与板端实际状态一致。然后在新包根目录预检：

```bash
sudo /usr/local/share/pynq-venv/bin/python3 integrations/vision_demo/install_vision.py \
  --media-root /home/xilinx/gl-hdmi-live-20261008-ea117349 \
  --brain-root /home/xilinx/jupyter_notebooks/guardianloop_pynq \
  --eye-root /home/xilinx/brain_eye_coexist_20261005/eye --bundle ./bundle
```

预检通过后给同一命令加 `--apply`，保存新 `INSTALLED_BACKUP`；恢复原服务，从静态主页按 PL_KEY1 验收。安装器核对当前启动摘要、共存引用、原文件、模型保护和 FFT 寄存器地址。回退新包时同样先停止显示并核实资源归还，再用三个根目录及 `--rollback <新 INSTALLED_BACKUP>`，恢复服务。

板端依次验收四页循环、KEY0 切回图像、暂停／主页退出、记录播放、暂停和结束撤销、选曲间隔、听音、音乐与频谱位置、CPU 负载及连续显示。原眼控、脑电、音频、灵巧手、倒立摆各做一次功能复测。离线检查记录见 `report/signal_verification_20261020.md`。
