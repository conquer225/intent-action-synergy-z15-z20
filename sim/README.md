# 仿真与软件验证

在仓库根目录安装数值依赖后执行：

```sh
python -m pip install numpy scipy pillow opencv-python
python -X utf8 -B -m unittest discover -s sim -p "test_*.py" -v
python -X utf8 -B -m unittest discover -s skill/tests -v
```

## 新增 PL 测试

31 项 `test_pl_*.py` 覆盖定点舍入与方差、模型导出、数值饱和和静默输入、真实 HLS C++、MMIO/缓存/超时所有权、串流撤销及重连、几何包、socket 会话、已知位姿融合、两套显示流水和原显示恢复。

`test_pl_hls.py` 使用 `g++` 编译仓库内的真实核，通过注入的 MMIO 接口测试驱动调用及输出；参考结果来自独立 Python 整数模型。`build/pl_vectors.py --check` 校验 FPGA 测试台向量；Vitis HLS 联合仿真入口见[构建目录](../build/README.md)。

实际 HLS 综合、Verilog 联合仿真、两板原整机综合与数值比较见[PL 记录](../report/pl/README.md)。

## 原入口与交付工具

- `test_live_eeg_entry.py`、`test_live_eeg_npu.py`：8 项实时展示行为，覆盖来源切换、连续性、过期清除和 Z20 等待。
- `test_restore_workspace.py`、`test_verify_package.py`：源码恢复、大小写、摘要、路径及 Git 检出完整性。
- `run_checks.py`：在恢复工程上执行既有选定软件、Skill 和交付测试。

原 RTL/HLS 与软件测试位于恢复后的 `sim/`、`integrations/vision_demo/tests`、`integrations/z20_compute/tests` 及对应硬件目录。模型和屏幕字库依赖按[外部输入清单](../report/external_inputs.json)准备；指定软件测试使用各自的夹具。历史记录按版本保存在 [verification](../report/verification/README.md)。
