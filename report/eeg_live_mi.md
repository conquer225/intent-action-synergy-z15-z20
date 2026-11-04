# 实时 EEG 与运动想象使用说明

## 本次接入

2026-11-05 修订将板端 `SignalRuntime` 的默认来源接回现有 `DemoBridge`，读取同机 9102 服务的 `/api/status` 与 `/api/telemetry`。进入疲劳和情绪页使用实时输入，页面切换保持采集时间；接收器等待和三秒数据过期分别显示对应状态。录制素材在显式请求回放时加载。

用户确认本工程此前已完成实时接收。仓库已有 Cyton USB 接收、正式采集入口与 MI 采集分支。本次改变的是展示运行时的默认接线，原解包、滤波、模型和执行设备协议沿用已有实现。

## 实时脑电展示

1. 使用 `build/restore_workspace.py` 恢复原路径，按原板端环境准备模型、依赖与配套显示固件。
2. 由原采集服务持有 Cyton USB 接收器，固定采样率为 250 Hz，通道顺序为 F3/F4/C3/C4/T7/T8/O1/O2。
3. 原 9102 服务发布真实接收状态和波形。`DemoBridge` 在后台读取并核对来源、通道与新鲜度。
4. 进入板端脑电页，疲劳、情绪使用同一实时来源。退出后再次进入，默认来源为 live。

在已经安装对应更新的媒体目录中，可以显式切回实时：

```sh
python integrations/vision_demo/select_signal_source.py --media-root /path/to/media_root live
```

需要检查历史记录时，准备相应回放素材并选择：

```sh
python integrations/vision_demo/select_signal_source.py --media-root /path/to/media_root replay
```

这里的 `/path/to/media_root` 是实际媒体安装根目录，其下存在 `vision_demo/signal_runtime.py`。命令写入本地来源请求，正在运行的展示读取请求后切换。未准备回放素材时，实时来源仍可独立工作。

电脑端 `preview_signals.py` 保留历史录制素材预览，板端 `SignalRuntime` 使用本次实时默认入口。两者用途和数据来源在各自页面标记。

## Z20 NPU 脑电页

疲劳与情绪页读取 9020 协议接收后的运算结果。原来从本地 `lemon_features.json` 自动补入特征的分支已改为等待实时输入；声音页继续沿用其既有来源。实时 EEG 页可以独立于录音素材启动。

原工程已提供 `build_z15_adapter.py`、`ReconnectingFeatures` 与 `FeatureTap`。按适配包说明将观察钩子绑定到现有分类器实例，来源设为 `live:Z15`，目标地址设为实际 Z20 地址。Z20 接口对应疲劳 20 维、情绪 180 维；情绪观察点使用产生该 180 维特征的现有 SEED 分支。Z15 本地的 105 维协方差情绪分支有独立模型与显示路径。

连接与特征就绪后，页面显示收到的窗口、来源、PL 分类与整数参考。过期状态由原 `FeatureRuntime` 撤销，导航切页保持后台来源会话。已有 `feature_replay.py` 可用于显式的历史数据回归。

## 运动想象入口

实际路径：

```text
guardianloop_acquisition.py
  → cyton_guardianloop.py：唯一串口采集者
  → MICandidateRuntime / MIAcquisition：有界分发与断流处理
  → RMSVirtualSession / CuedMISession：提示、窗口、质量与试次
  → RMS EEGNet：左右手候选
  → MIWebBridge → /mi-cued：结果与虚拟手
```

正式采集入口读取 `/etc/default/guardianloop-mi.json`。现有配置约定为 `{"enabled":true}` 开启 MI 分支，`{"enabled":false}` 关闭；按原流程重启采集服务后生效。启用时检查 `experimental_rms_eegnet.npz` 的固定 SHA256，并设置 `--mi-source live`。权重按外部输入清单准备，模型身份与现有版本配对。

在 Z15 原脑电网页服务打开 `/mi-cued`，等待接收、500 点预热和信号质量就绪。选择“想象左手”或“想象右手”，按页面提示完成试次。提示呈现回执成为收集起点，偏移 125 点后收集 500 点窗口，8–30 Hz 处理与推理运行在 ARM。虚拟手选项为每试次一次、每次 20% 的开合动作。

现有模型属于实验模型，评估材料按其公开数据、录制回放和真实佩戴试次分别记录。本次沿用现有识别器与虚拟手，实物机构继续使用已有眼控设备链。

参考项目 [Xsingh-Luo/fpga_eeg_rehab](https://github.com/Xsingh-Luo/fpga_eeg_rehab)采用 CSP / SVM 和 PL 算法流水线。本次参考其任务组织、运动相关节律与试次展示方式，现有工程采用固定八通道 RMS EEGNet。双方源码、模型与测试结果各自对应各自实现。

## 修订文件与验证

| 文件 | 变化 |
| --- | --- |
| `integrations/vision_demo/vision_demo/signal_runtime.py` | 默认建立实时只读桥接；回放延迟加载；来源请求支持 live/replay；退出恢复 live。 |
| `integrations/vision_demo/select_signal_source.py` | 增加 live 选择，实时运行与回放素材分开准备。 |
| `integrations/z20_compute/z20_compute/visual_pipeline.py` | NPU 脑电页等待接收结果，移除自动补入录制特征；录音素材在声音路径按需读取。 |
| `integrations/z20_compute/z20_compute/visual_display.py` | 显示 Z15 实时脑电来源。 |
| `sim/test_live_eeg_entry.py` | 用真实 DemoBridge 和确定性 EEG 数据验证来源、波形、切页、过期、回放选择和命令入口。 |
| `sim/test_live_eeg_npu.py` | 验证两种脑电任务接收结果、等待状态、旧结果清除及录音素材独立性。 |
| README 与使用说明 | 介绍已有 MI、实时接收、FPGA 模块与工程工作，附实际源码入口。 |

新增八项行为测试先复现原入口强制加载、自动回放和自动补入特征，再检查修订后的实时默认流程。集中回归共通过 160 项，结果记录在 `report/verification/eeg_live_mi.json`。

本轮验证运行于普通电脑，板卡保持原状态；新默认入口的现场联调在恢复对应板端环境后执行。历史实时接收事实与本轮软件结果分别保留。
