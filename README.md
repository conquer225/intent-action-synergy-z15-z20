# 意动协同：Z15 与 Z20 多模态感知交互控制台

仓库：[conquer225/intent-action-synergy-z15-z20](https://github.com/conquer225/intent-action-synergy-z15-z20)

这是 Z15＋Z20 联动工程的程序源码公开版，快照日期为 2026-11-01，面向 AMD 自主选题赛道初级组。Z15 使用 XC7Z015 CLG485，负责交互、脑电/眼动接入和原控制链；Z20 使用 Navigator XC7Z020 CLG400，负责相机、共享整数核和辅助显示。电脑承担浏览器视觉渲染、相对深度等计算。开发工具基线为 Vivado/Vitis HLS 2023.1。

本仓库保留 4744 个原始源码、测试及配置文件，包含 RTL、HLS、PS Python、外设程序、安装和构建入口，以及可单独复用的 PYNQ Skill。文件内容与已验证的参赛快照一致，存储路径经英文规范化。运行前按清单恢复原路径和大小写。

公开版不携带抓取的第三方网页、模型权重、音视频、板卡镜像、原生二进制库、厂商 SDK、设备快照和历史原始运行记录。部分历史部署脚本含固定登录凭据，也未公开。缺少的输入按路径、大小和 SHA256 列入[外部输入清单](report/external_inputs.json)。本仓库可以完成下述离线验证，完整视觉演示及 FPGA 构建仍需准备对应输入，见[复现说明](report/reproduction.md)。

## 目录

| 目录 | 内容 |
| --- | --- |
| [src](src/README.md) | 原始程序源码、测试和配置的规范化副本 |
| [sim](sim/README.md) | 离线回归入口与交付工具测试 |
| [build](build/README.md) | 源码恢复、完整性检查及构建说明 |
| [board](board/README.md) | 实际板型、职责与接板条件 |
| [data](data/README.md) | 可手算的黄金参考正负例 |
| [skill](skill/README.md) | 通用 PYNQ 固件核对、数值比对和会话恢复工作流 |
| [report](report/README.md) | 公开范围、来源、状态和复现记录 |

## 在普通电脑验证

使用 Python 3.10 或更新版本，先进入仓库根目录：

```sh
python -X utf8 -B build/verify_package.py
python -X utf8 -B -m unittest discover -s sim -p "test_*.py" -v
python -X utf8 -B -m unittest discover -s skill/tests -v
```

这些命令只读取本地文件。完整性检查会核对全部公开文件和原始源码摘要，忽略 Git 自身的 `.git/` 元数据；其他未登记文件仍会报错。请将日志和缓存写到仓库外。

恢复原目录后，可运行指定工程回归。以下是 Windows 路径示例，输出目录须尚不存在；Linux 可使用对应的新目录：

```sh
python -X utf8 -B build/restore_workspace.py --output C:/work/intent_action_runtime
python -m pip install "numpy>=1.24"
python -X utf8 -B sim/run_checks.py --workspace C:/work/intent_action_runtime --output C:/work/intent_action_checks
```

检查集为 12 项指定原工程回归、14 项 Skill 工具测试和 7 项交付工具测试，共 33 项。它们验证整数算例、板型拒绝、缓冲所有权、会话过期、文件恢复与 Git 克隆后的完整性检查。原工程的其他测试及板卡测试不包含在这组计数中。

## 查找程序

[来源清单](report/source_manifest.json) 的 `runtime_path` 是原工程路径，`package_path` 是本仓库存储位置。部分过长路径缩短到 `src/workspace/short/`；恢复命令会还原原名，不应直接在规范化树上启动原程序。

主要原始入口如下：

- `integrations/vision_demo`：Z15 图像流、信号/音频显示及 FPGA 构建。
- `integrations/eeg_demo`、`integrations/eye_c3`：脑电、眼动、菜单与执行控制状态。
- `integrations/z20_compute`：共享整数核、相机、双板协议、四模式及电脑辅助程序。
- `integrations/pendulum_ble`、`multimodal/firmware`：既有外设通信和嵌入式源码。

## 当前状态
源码、数据和依赖按各自声明保留版权；本次公开未给全部源码重新指定统一许可证。来源和许可范围见[第三方说明](report/third_party.md)。
