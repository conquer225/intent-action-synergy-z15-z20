# 复现步骤与外部输入

## 离线源码验证

先在仓库根目录使用 Python 3.10+ 执行：

```sh
python -X utf8 -B build/verify_package.py
python -X utf8 -B build/restore_workspace.py --output C:/work/intent_action_runtime
python -m pip install "numpy>=1.24"
python -X utf8 -B sim/run_checks.py --workspace C:/work/intent_action_runtime --output C:/work/intent_action_checks
```

两个输出目录必须尚不存在且位于仓库外。Linux 使用对应的新路径。来源清单恢复原路径及大小写，不下载缺失输入。检查结果写入外部 `summary.json` 和三个日志文件。

## 完整演示的条件

按照[外部输入清单](external_inputs.json)逐项准备需要的模型、素材和原生库，核对对应 SHA256；不需要恢复全部历史快照。来源线索见[第三方说明](third_party.md)及恢复后的原工程文档。私人配置在本地生成，不放入仓库。

恢复后的 `integrations/z20_compute/requirements.txt`、`requirements-pc.txt`、`requirements-reconstruction.txt` 分别描述相关依赖。浏览器视觉还需要匹配版本的浏览器、PyTorch、Ultralytics 和图形环境；基础数值依赖不能覆盖完整模型环境。随后才可调用 `build_visual_release.py`，其固定输入检查会拒绝缺失或不匹配的资产。

## FPGA 和板卡

使用原工程的 Vivado/Vitis HLS 2023.1，并准备 Z15 CLG485 与 Navigator CLG400 匹配的参考 IP。`build_signal_hardware.py`、部分 HLS/Tcl 入口仍包含 `D:/vivado`、`D:/fpga/z15_multimodal` 或旧厂商根目录，需在恢复副本改成实际目录。

Z20 先从 BD Tcl 重建工程及 IP runs，再执行综合、实现和导出；历史 `implement.tcl` 所引用的生成目录不能直接代替这一步。Z15 信号版本需要相应视觉/FFT HLS 导出。检查匹配版本的时序、资源、CDC、DRC 和配套摘要后，才进入实际板卡流程。

Z15 使用匹配 PYNQ/Linux 介质；Z20 原环境为 ARMv7 Linux 5.4.0-xilinx-v2020.2，内核、设备树、UIO、驱动及 `.so` 须匹配 ABI。本仓库没有完整 SD 系统镜像。现有证据覆盖公开副本恢复和指定离线测试，尚未在干净机器上验收全套 FPGA 与整机启动链。
