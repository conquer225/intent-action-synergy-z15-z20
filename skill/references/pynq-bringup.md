# PYNQ 加载前检查与 DMA 排查

适用于已有 Vivado 自定义 overlay、PYNQ Python 控制程序及可核对板卡资料的队伍。输入是实物板卡记录、可信构建的 bit/HWH、摘要清单、IP/寄存器约定和最近失败日志。输出是静态检查 JSON、最小数据通路记录及明确的失败层。更换题目时替换这些输入；更换板卡时重新生成匹配硬件，复用检查方法和工具。

## 固定当前板卡和构建

按[板卡模板](../templates/board-profile.example.json)登记器件、封装、速度等级、板修、启动镜像、PYNQ/内核/Python 与工具版本。型号名和 JTAG IDCODE 不一定包含封装及载板修订信息，要与实物和匹配原理图核对。先确认本次是 PYNQ overlay 还是 Linux FPGA Manager/UIO 路径。

从一次已完成的构建导出 bit、对应 HWH 和实现报告，记录源版本、构建标识和摘要。将[清单模板](../templates/overlay-manifest.example.json)放到发布目录；填入 `bit.path`、`hwh.path`、两个 SHA256、`target_part` 和应用实际使用的 `required_ips`。层次 IP 名称使用 HWH 的 `FULLNAME` 去掉开头 `/`，如 `compute/dma_0`。

在可信构建结束时固定摘要，交付及搬迁时比较。不要在已经出现损坏或错配的文件上重新计算后直接覆盖原清单。

## 执行文件预检

从包目录运行：

```sh
python scripts/check_overlay.py /path/to/release/manifest.json --part ACTUAL_DEVICE_PACKAGE
```

工具检查清单版本和构建标识、文件摘要、同目录同名、Vivado bit 头的器件/封装、HWH `SYSTEMINFO` 的器件/封装及所需 IP。路径相对于清单目录，不能越出该目录。`required_ips` 至少列一项应用确实依赖的 IP。

当前解析器支持常见 Vivado 有序标签 `a/b/c/d/e` 的完整 `.bit`，以及含 `SYSTEMINFO DEVICE/PACKAGE` 和 `MODULE` 的 HWH。测试覆盖 Zynq-7000 格式；XSA、裸 BIN、PDI、XCLBIN、部分重配置或其他头格式要换用匹配工具。遇到“不支持格式”保留原文件，先辨认格式。

`passed=true`表示本次静态身份约定相符。它依赖使用者提供的真实板型和可信清单，不能推导出 DDR、引脚、电压、时钟、速度等级或驱动均正确；也不能通过摘要本身证明两个文件来自同一次构建。

## 分开检查元数据与硬件运行

PYNQ 的 `Overlay(bit_path)` 默认下载配置；只检查元数据时使用 `Overlay(bit_path, download=False)`。实际下载前先识别现有 PL/VDMA 所有者，按原程序完成停流、确认停止和资源交还。加载后重新取得与新硬件对应的驱动对象，不复用上一代 MMIO/DMA 对象。[PYNQ Overlay 说明](https://pynq.readthedocs.io/en/v3.1/pynq_libraries/overlay.html)

先核对 IP 名称、地址、寄存器版本、时钟和复位，再通过最小已知输入验证通路。保存输入、原始输出和寄存器读数。资源共享程序由一个明确的所有者负责启动与退出，分析旁路只取得自己的输入副本。

## 建立最小传输合同

为当前 IP 写明输入/输出的形状、元素字节数、符号、布局、字节序、总字节数、对齐、握手、包边界和超时。AXI DMA 流传输的 TLAST 是包结束；AXI Video/VDMA 的 TLAST 通常表示行结束，不能直接互换。

以 16 个 `uint32` 为例，内存有效字节数为 `16×4=64`。若为每拍 32 位且不含填充的包，则检查 16 次 `TVALID && TREADY` 握手，最后一次应带包结束。不同总线宽度、TKEEP、重排或图像行布局时重新计算，不能套用这组拍数。

PYNQ 连续内存用 `allocate` 或匹配平台的分配器；把设备物理地址传给 PL。非一致缓存下，PS 写入后、PL 读取前同步到设备，PL 写入完成后、PS 读取前同步回主机。不要用普通 NumPy 虚拟地址代替设备地址。[PYNQ 内存说明](https://pynq.readthedocs.io/en/v3.1/pynq_libraries/allocate.html)

准备好接收通路及有效输出缓冲，再按当前驱动合同提交发送和计算。每次实际运行保留总字节数、开始/结束条件、超时以及完成/错误寄存器。PYNQ 驱动版本的等待能力要查实际接口；不要给不存在的 `wait(timeout=...)` 参数编写依赖代码。

## 卡住时按证据定位

先区分 MM2S、计算核、S2MM 和显示哪一段无进展。读取当前驱动的状态寄存器并对照其 IP 版本文档；若有 ILA，观察时钟、复位和实际握手，检查 TREADY 回压、TLAST/TKEEP 和期望字节数。保持失败输入，不同时修改长度、复位、数据类型和缓冲策略。

如果 CPU 超时退出而硬件停止尚未确认，保留仍可能被访问的缓冲，标记所有权未解除。用既有复位流程取得停止证据后再释放或重用；Python 异常和后台线程结束都不能代替硬件停止确认。DMA 常见失败的波形排查可参考 [Mario Ruiz 的原始复现文章](https://discuss.pynq.io/t/debugging-common-dma-issues-part-3/7157)。

视频输入另外核对 HSIZE（有效行字节数）、STRIDE（相邻行跨度）、帧高及缓冲大小。环形槽索引重复不代表复制期间未覆盖；采用硬件完成/写入代数或匹配驱动的所有权机制。相机采集率、完整快照率、分析更新率和 HDMI 刷新率分别计数。

## 验证效果与失效条件

本队观察 E01/E02/E03/E06 对应错误封装、固件引用漏更新、DMA 所有权和复制覆盖问题，见[案例来源](../examples/z15-z20/README.md)。本包脚本可离线检出摘要、封装、HWH 和 IP 不一致；DMA/屏幕步骤需要现场寄存器、波形及显示记录。

未知载板、无可信构建记录、无法确认停流、HWH 缺少目标信息、驱动格式不符或输入布局不明时，在该层停止加载结论，补齐材料。完整验收至少保留静态预检、相同输入通路、异常退出和资源交还结果；尚未执行的上板项目写入[运行记录](../templates/run-record.example.json)。
