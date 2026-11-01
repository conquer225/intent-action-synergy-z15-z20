# 固定八通道 MI 整体 RMS 重训对照

本轮只解决一个已复现的问题：冻结源尺度的 EEGNet 在较低幅值输入下会趋向单一类别。它不是新采集、逐指任务或正式部署。帽位仍为 `F3,F4,C3,C4,T7,T8,O1,O2`，不换标签，不改物理单位质量门限，不驱动实体灵巧手。

## 已完成的结果

90 个候选全部训练冻结后统一评分，复核通过。原开发 30 人的平均跨人 BA 为 63.8280%→64.6587%，配对差值 95% 区间为 +0.0167～+1.6155 个百分点；不是新的独立确认。1/8、1/32 共同幅值压缩下，新模型均保持 64.6587%，旧模型分别为 53.7672%、50.5714%。预声明的“继续隔离 ARM 运行验证”门槛通过，正式晋升仍为 false，板卡未操作。详细边界、数值复核及下一步见 [结果说明](D:/ican/codex_project/eeg_apps_z15/output/mi_rms_comparison_20261003/RESULTS.md)。

后续隔离ARM验收已通过：PC/ARM类别、滤波及恢复状态一致；156秒实际节拍回放feed p99=105.9467ms，无持续积压。只写独立测试目录，正式服务、程序、模型和PL未改；这并不是识别准确率又提高。见 [ARM验收报告](D:/ican/codex_project/eeg_apps_z15/output/mi_rms_arm_acceptance_20261003/RESULTS.md)。

隔离虚拟控制接入也已通过：PC/ARM各49项测试，观察与虚拟模式全量回放输出一致，13个完整预测各执行一次虚拟命令；实际网页启停、休息和撤销通过。新页面只接已有台架记录，未接实时Cyton，不控制实体手；正式9102、模型、服务和PL未改。入口及恢复命令见 [虚拟控制接入报告](D:/ican/codex_project/eeg_apps_z15/output/mi_rms_virtual_20261003_retry2/RESULTS.md)。

## 仅有的处理变化

在完整的 `N×8×500`、已 CAR 和滤波的窗口上：

```text
r[n] = sqrt(mean over all 8 channels and 500 samples of x[n,c,t]^2)
u[n,c,t] = x[n,c,t] / r[n]
z[n,c,t] = float32((u[n,c,t] - source_mean[c]) / source_scale[c])
```

每个窗口只有一个正除数，不逐通道把方差调成相同。因而 RMS 步骤保留通道间功率比例和符号。后续通道标准化参数仅由每折 26 名源拟合人计算，训练/推理使用同一函数。原始脑电与 SQI 不经过这项无量纲变换。平坦、非有限或整体 RMS≤1e-12 的窗口直接拒绝，不能将纯零信号“归一化出脑电”。

## 比较边界

- 复用原 30 人全部逐人留出、26 人拟合／3 人源验证划分及 42、43、44 三个种子；原 12 人确认集和另外 10 人不读取。
- 原 `C2_EEGNet_SMALL` 为直接算法基线。架构、学习率、优化器、批大小、最大 200 epoch、20 epoch 早停、源验证选点、通道和滤波不变。
- 保留原 6,080 个完整窗口及作者坏试次标记；仍只评分原始顺序≥60 的 4,280 个目标窗口，不改变分母。
- 90 个候选 checkpoint 全冻结后再评分。低幅值条件固定为 `1,1/8,1/32`，仅为数值域压力测试，不代表真实物理干扰或真实佩戴准确率。
- 每人先平均三个种子的 BA，再平均 30 人；配对区间按人重采样。不能选最高种子或先平均 logits 冒充这一指标。
- 后续数值兼容检查固定用 `s01_seed42`，在评分前确定；七个实时窗口只检查数值和倍率一致性，不按提示算准确率或选择权重。

本轮预声明的继续条件：候选正常幅值平均 BA≥60%，相比原基线平均下降不超过 1 个百分点，配对差值 95% 下界大于 −3 个百分点，低幅值输出与其正常幅值一致率≥99.9%。这是**继续隔离运行验证**的门槛，不是正式上线授权，也不是证明个人效果。只有配对区间下界>0，才可称原开发组支持正常幅值的探索性提升；它仍不是新独立确认。

## 可复现命令

```powershell
& 'D:\ican\codex_project\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 'D:\ican\codex_project\eeg_apps_z15\mi_rms_comparison.py' prepare
& 'D:\ican\codex_project\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 'D:\ican\codex_project\eeg_apps_z15\mi_rms_comparison.py' train
& 'D:\ican\codex_project\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 'D:\ican\codex_project\eeg_apps_z15\mi_rms_comparison.py' evaluate
& 'D:\ican\codex_project\eeg_apps_z15\.venv-mi\Scripts\python.exe' -X utf8 'D:\ican\codex_project\eeg_apps_z15\audit_mi_rms_comparison.py'
```

完成的 prepare、evaluate、audit 不覆盖已有产物。中断的 train 只能在代码/协议/原数据/基线摘要均未变、没有进入目标评分时续跑；部分写入的模型保留并停止，不自动删掉重做。

## 文件

- 协议：`D:\ican\codex_project\eeg_apps_z15\mi_rms_comparison_protocol.json`
- 共享纯 NumPy 变换：`D:\ican\codex_project\pynq_guardianloop\mi_window_rms.py`
- 隔离推理代码：`D:\ican\codex_project\eeg_apps_z15\output\mi_rms_runtime_20261003\mi_eegnet_portable.py`
- 训练、指标、原始预测和摘要：`D:\ican\codex_project\eeg_apps_z15\output\mi_rms_comparison_20261003`
- 原基线：`D:\ican\codex_project\eeg_apps_z15\output\mi_model_comparison_20261001`

隔离 RMS 模型状态为 `offline_shared_rms_only`；原正式 `offline_plumbing_only` 加载器会拒绝，防止用旧预处理误载。候选在任何情况下都保持生产资格、晋升、物理控制=false。本轮不停止板端服务，不写板卡模型、PL、设备树或开机配置。

源 MAT 物理单位仍未独立核定；这项除数对正的共同倍率不敏感，但不能消除参考、噪声、任务差异，也不能证明归一化后保留了足够的个人 MI 判别信息。
