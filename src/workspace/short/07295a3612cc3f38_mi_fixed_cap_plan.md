# 固定八通道运动想象候选：预先冻结的离线关口

目标是补上整机功能缺口，而不是把公开数据分数当作佩戴者准确率。**固定采集顺序始终为 `F3,F4,C3,C4,T7,T8,O1,O2`，不重新佩戴或调整帽位。**

假设：在完全未见过的受试者上，使用固定八位置的轻量 3 秒左／右手运动想象模型，平均受试者 balanced accuracy 至少 0.60，且受试者 bootstrap 95% 区间下限高于 0.50。若不满足，则不把这个模型接入正式 Cyton 服务，也不输出脑控指令。

数据来自 [PhysioNet EEG Motor Movement/Imagery v1.0.0](https://physionet.org/content/eegmmidb/1.0.0/)，许可为 Open Data Commons Attribution 1.0。只下载第 `4,8,12` 轮；T1 是左手想象，T2 是右手想象。第 `6,10,14` 轮的 T1/T2 含义是双手／双脚想象，绝不混作左右手。下载器默认从 PhysioNet 官方列出的开放 S3 镜像取文件，并按其官方 SHA-256 清单校验每个 EDF。EDF 头部审计发现 S088、S092、S100 的文件为 128 Hz，其余为 160 Hz；均按各自实际采样率重采样到 250 Hz，保留全部受试者。参考方式与 Cyton 不同，因此即使离线关口通过，也仍需单独做跨设备数值核对和一次有提示的实时验收。

冻结划分和选择：受试者 1–70 训练、71–89 验证、90–109 一次性测试；整人分割。比较 `C3/C4` 与固定八路两个同流程的标准化逻辑回归模型；只看验证组的逐人平均 balanced accuracy 决定模型，然后在训练+验证受试者上重训。测试主指标是逐人 balanced accuracy 的均值，次指标为逐人 macro-F1；保存逐试次预测和逐人结果。预处理为完整记录按 EDF 实际采样率重采样到 250 Hz，再运行与 Cyton 同一份 `CausalEEGFilter`，按提示后 0.5–3.5 秒的完整 3 秒窗口抽取两段频带 Welch 对数功率。归一化只在相应训练集拟合。

即使通过，也只可称为“有提示的左右手想象候选”。无提示、输入不连续或通道质量不合格时拒绝；不自动发控制指令。拟接板端之前必须核对 NumPy 推理与训练器逐试次一致，以及主循环、网页状态、开机恢复不会显示过期结果。

复现（数据由脚本下载到 `D:\ican\datasets\EEGMMIDB`，约三百份 EDF；虚拟环境只用于离线 EDF 读取）：

```powershell
cd D:\ican\codex_project\eeg_apps_z15
python mi_physionet_download.py --workers 8
.\.venv-mi\Scripts\python.exe mi_physionet_evaluate.py
```

`mi_physionet_protocol.json` 是机器可读版本；候选 ARM 数值实现位于 `D:\ican\codex_project\pynq_guardianloop\mi_candidate.py`。当前**尚未加入正式服务或 PL**，这一步的预处理／分类面向 ARM。
