# 工程说明与记录

本仓库收录双 Zynq 多模态交互系统的源码、测试、训练导出和构建工具。规范化存储路径与原运行路径见[来源清单](source_manifest.json)，模型和素材配套项见[外部输入清单](external_inputs.json)。

- [PL 脑电与地图](pl_accel.md)：滤波器组/CSP/SVM、几何接口、后端切换、寄存器与构建命令。
- [PL 构建与数值记录](pl/README.md)：两核联合仿真、原整机资源、时序估计与数值算例。
- [实时 EEG 与 MI](eeg_live_mi.md)：原 Cyton 实时入口、EEGNet 提示试次和虚拟手。
- [当前工程](current_status.md)：双板职责、计算与控制数据流。
- [复现步骤](reproduction.md)：源码恢复、依赖和板卡配套。
- [来源与许可](third_party.md)：本工程与第三方材料的归属。
- [历史验证记录](verification/README.md)：此前发布与回归的记录。

根 README 的地图 GIF 来自本工程地图核的 C++ 输出。源码、数值算例和报告随同一 Git 版本发布。
