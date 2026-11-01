# 恢复、检查与构建

`restore_workspace.py` 根据来源清单校验全部公开载荷，再在包外新目录恢复原路径和大小写。`verify_package.py` 检查公开文件的完整集合、摘要、来源清单及最长 120 字符的成员路径预算。

Git 版检查器忽略根 `.git/` 元数据，并将根 `.gitignore` 和 `.gitattributes` 纳入文件摘要；其他新增文件仍会使校验失败。相应用例先复现旧检查器拒绝 Git 元数据，再验证修订后的行为。生产程序源码没有为此改写。

恢复后的实际构建入口：

| 目标 | 原工程入口 | 需要另备的输入 |
| --- | --- | --- |
| Z20 整数核 | `integrations/z20_compute/build_hls.py`、`run_cosim.py` | Vitis HLS 2023.1，匹配的测试与模型输入 |
| Z15 图像/信号/音频 | `integrations/vision_demo/build_hardware.py`、`build_signal_hardware.py` | Z15 CLG485 参考、厂商 IP、音频/视觉 HLS 导出 |
| Navigator 相机与整数核 | `integrations/z20_compute/build/navigator/` 中 Tcl | CLG400 参考 IP、共享核和观察器，重新生成的 Vivado 工程 |
| 四模式软件 | `integrations/z20_compute/build_visual_release.py` | 固定版本的模型、素材、原生库及原输入清单 |

部分原入口仍固定本机根路径和生成目录，需在恢复副本按实际环境调整，不能把旧生成目录视为构建输入已齐。顺序及限制见[复现说明](../report/reproduction.md)。

根 `.gitattributes` 禁止自动换行转换，保留 Windows/Linux 检出时的原始字节与摘要。
