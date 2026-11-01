# Z15 八通道疲劳识别：模型、电极与部署审计

更新时间：2026-09-16

## 结论

现在不需要等待真实佩戴才能继续。完整 SEED-VIG 数据可用于电极方案比较、跨被试训练、模型压缩和部署验证；真实佩戴主要用于最后的信号质量、个体校准和端到端验收。

当前不应把 `route_b_8ch_model.pth` 直接替换板上模型。该权重只使用 `Ablation/10subject.mat`，随后按窗口随机划分训练、验证和测试；同一受试者的相邻窗口可能分散到各集合，存在明显的受试者与时间相关泄漏风险。

在本次部署一致、严格跨被试测试中，当前 HGB 轻量模型仍优于按同样输入重训的复杂 ViFormerNet：

| 模型 | Pearson | RMSE | Accuracy | Macro-F1 |
| --- | ---: | ---: | ---: | ---: |
| 当前 8ch DE + HGB | 0.6582 | 0.2039 | 0.5905 | **0.6023** |
| 8ch DE + ViFormerNet | 0.6088 | 0.2316 | 0.5681 | 0.5764 |

因此近期主线应保留 HGB 作为可交付基线，同时把 ViFormerNet 当作研究分支继续做跨被试调参、蒸馏和量化。复杂不等于在真实新用户上更准。

## 已完成的检查

### 1. 严格评测协议

- 数据：完整 23 段 SEED-VIG、21 个受试者组。
- 外层测试：按受试者留一（participant-grouped LOSO），测试受试者从不参与训练。
- ViFormerNet 调参：每折另留一个开发受试者，用于早停和分类阈值选择。
- 每段记录前 15 个 8 秒窗口（120 秒）只做无标签个体校准，并从评分中排除。
- 输入与板端一致：8 通道 × 5 频带 DE，随后进行因果 EMA。

这与原 `route_b_train_8ch.py` 的单受试者随机窗口划分不是同一难度，因此不能直接拿两者的高分比较。

### 2. 五组八通道方案

| 排名 | 方案 | 通道 | Pearson | Accuracy | Macro-F1 |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | 当前组合 | FT7, FT8, CP1, CP2, P1, PZ, PO3, O1 | 0.6582 | 0.5905 | **0.6023** |
| 2 | 纯后部对称 | CP1, CP2, P1, P2, PO3, PO4, O1, O2 | 0.6282 | **0.5942** | 0.5943 |
| 3 | 顶枕对称 | FT7, FT8, CP1, CP2, P1, P2, O1, O2 | 0.6545 | 0.5737 | 0.5867 |
| 4 | 文献关键通道 | TP7, TP8, CP1, CP2, POZ, O1, OZ, O2 | 0.6552 | 0.5657 | 0.5735 |
| 5 | 颞枕组合 | FT7, FT8, TP7, TP8, PO3, PO4, O1, O2 | **0.6797** | 0.5508 | 0.5592 |

当前组合在本次五组候选中 Macro-F1 最好，可先用于原型，不必现在改线。但它左右不完全对称，所以还不能把这次探索当成最终电极定论；最终方案还需结合帽子结构、干电极接触稳定性和真实佩戴伪迹做验证。

文献证据与结果并不冲突：SEED-VIG 原始研究指出单一 EEG 模态下后部区域总体优于颞区，并观察到困倦时顶叶 theta/alpha 增强、颞区 gamma 降低；近年的通道选择研究也反复选中 O1/OZ/O2/POZ 与 TP7/TP8。不同目标指标和模型会导致不同最佳子集，所以不能只按论文中的“常见通道”直接接线。

## ViFormerNet 部署审计

- 输入：`1 × 8 × 5` DE 特征，不是 8 路原始波形。
- 参数：432,988。
- FP32 参数体积：1,731,952 字节（约 1.65 MiB）。
- 原 checkpoint：1,828,433 字节。
- TorchScript：1,777,032 字节，输出与 PyTorch eager 最大绝对误差为 0。
- 当前电脑 CPU 单窗口推理：中位数 3.84 ms，P95 4.68 ms。

其计算频率仅每 8 秒一次，理论计算量并不构成实时瓶颈。Z15 的主要障碍是 ARMv7/PYNQ 2.7 缺少适合的 PyTorch 运行时，而不是模型太慢。

### 推荐部署路径

1. **当前交付版**：PL 继续做 8ch 五频带 DE，ARM 运行 HGB；这是目前严格测试下更好的方案。
2. **研究版**：继续改进严格 LOSO ViFormerNet，不使用原来的单人随机窗口成绩作依据。
3. **达到明确增益后**：把教师网络蒸馏成小型 MLP/TCN，或导出 INT8 静态 C/C++ 推理；优先在 ARM 上跑。
4. **不建议现在做**：直接在 PL 中完整实现 MultiheadAttention、LayerNorm、Softmax 与 Conformer。虽然器件尚有资源，但开发和验证成本远高于每 8 秒一次推理所需，性价比低。

当前已实现的 DE 加速 IP 约使用 1,453 LUT、726 FF、1 个 RAMB36 和 4 个 DSP；HGB IP 报告约使用 390 LUT、255 FF、12.5 个 BRAM Tile。现有系统仍有资源，但“有资源”不代表应优先把 Transformer 硬化。

## 论文与实现判断

- SEED-VIG 原始论文明确给出 23 名受试者、后部/颞部电极布局、PERCLOS 标签和脑区频带变化，并强调跨人差异会显著降低泛化性能。
- 2026 年 ViFormerNet 论文公开元数据声称 LOSO 平均 PCC 0.8532、Accuracy 82%。本地代码结构与论文摘要描述的双分支、共享 Conformer、多任务与 ODT 一致。
- 本次结果不是对论文的精确复现：我们只使用 8 通道和板端五频带 DE，而论文结果可能基于 17 通道、更细的 2 Hz 特征、不同训练细节或不同统计方式。因此本次结果回答的是“当前 Z15 八通道输入下是否值得替换部署模型”，答案目前是否定的。

主要参考：

- [SEED-VIG 原始论文：A Multimodal Approach to Estimating Vigilance Using EEG and Forehead EOG](https://arxiv.org/abs/1611.08492)
- [ViFormerNet: A Dual-Branch Multi-Task Framework for EEG-Based Vigilance Estimation](https://doi.org/10.1109/ICSP69961.2026.11540912)
- [VIGNet 官方代码与论文信息](https://github.com/wko1014/VIGNet)
- [EEG fatigue critical-channel selection study](https://pmc.ncbi.nlm.nih.gov/articles/PMC11739579/)

## 下一阶段，不佩戴也能完成

1. 对 ViFormerNet 做少量、受试者级超参数搜索，而不是窗口级随机调参。
2. 训练一个 INT8 友好的学生模型，与 HGB 在同一 LOSO 协议下比较。
3. 给网页加入 SEED-VIG 离线回放模式，先验证 8 通道波形、频谱、丢包/质量、疲劳曲线与报警链路。
4. 固化真实实验记录模板：电极位置、参考/偏置电极、阻抗或接触质量、佩戴时间、Cyton 包统计。
5. 最后才进行真实佩戴：先做 2 分钟校准和短时清醒数据，不应一开始就用个人数据重新训练整网。

## 产物

- `audit_viformer.py` / `audit.json`：模型体积、TorchScript 一致性与速度审计。
- `evaluate_channel_sets.py` / `channel_set_loso.json`：五组八通道方案的严格 LOSO 比较。
- `train_strict_loso_viformer.py` / `viformer_strict_loso.json`：部署一致 ViFormerNet 严格跨被试结果。

