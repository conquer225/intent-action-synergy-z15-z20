# 恢复、检查与构建

在仓库根目录执行，输出选择包外的新目录：

```sh
python -X utf8 -B build/verify_package.py
python -X utf8 -B build/restore_workspace.py --output C:/work/intent_action_runtime
```

恢复工具核对来源清单及全部源码摘要，恢复原路径和大小写。根 `.gitattributes` 保留 Windows/Linux 检出的原始字节。

## 新增 PL 构建入口

| 入口 | 输出 |
| --- | --- |
| `pl_vectors.py --check` | 从独立整数参考重建并比较固定测试向量 |
| `pl_accel.py eeg或map --output 新目录 --tool HLS路径 --cosim` | C 仿真、HLS 综合、Verilog 联合仿真和 IP 导出 |
| `pl_platform.py eeg或map --ip IP目录 --output 新目录 --tool Vivado路径` | PS 兼容平台、原 BD 或原 XPR 的增量集成和逻辑综合 |
| `pl_platform.py ... --implement` | 使用原整机与板级约束完成布线、bitstream 及 XSA 导出 |
| `pl_demo.py --output 新目录` | 实际 C++ 核生成的地图 PNG/GIF、脑电特征和整数比较结果 |

原工程通过 `--project 原工程.xpr` 复制到新目录，保留原顶层；或通过 `--bd-tcl 原BD.tcl` 配合 `--source`、`--ip-repo`、`--xdc` 重建。两者各自检查器件、原端口与地址。完整参数和部署顺序见 [PL 说明](../report/pl_accel.md)。

Windows Codex 环境中的厂商工具可通过本包启动器运行，子进程继承工作目录、环境与输出，返回实际退出码：

```sh
python -X utf8 -B build/run_unpacked.py python -X utf8 -B build/pl_accel.py eeg --output C:/work/pl_eeg --tool D:/vivado/Vitis_HLS/2023.1/bin/vitis_hls.bat --cosim
```

## 原有构建入口

恢复后在各模块目录执行：

| 目标 | 入口 | 配套输入 |
| --- | --- | --- |
| Z20 共享整数核 | `integrations/z20_compute/build_hls.py`、`run_cosim.py` | Vitis HLS 2023.1、固定测试和模型 |
| Z15 图像/信号/音频 | `integrations/vision_demo/build_hardware.py`、`build_signal_hardware.py` | CLG485 参考、厂商 IP、FFT/视觉 HLS 导出 |
| Navigator 双目与整数核 | `integrations/z20_compute/build/navigator/` | CLG400 参考、共享核及观察器 IP |
| 四模式软件 | `integrations/z20_compute/build_visual_release.py` | 固定版本模型、素材、原生库 |

原入口中的厂商根目录按本机资料位置设置。系统、模型和固定资产见[复现步骤](../report/reproduction.md)及[外部输入清单](../report/external_inputs.json)。
