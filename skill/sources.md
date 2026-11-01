# 开源检索与采用范围

检索日期为 2026-11-01。搜索主题包括 PYNQ overlay/HWH、DMA 超时与 TLAST、缓存同步、定点黄金参考、双板通信恢复，以及可复用的 PYNQ/FPGA Agent Skill。先查看 [skills.sh 目录](https://skills.sh/)，再运行 `npx --yes skills find pynq` 和 `npx --yes skills find fpga`，并检查候选技能的原始内容和许可证。

采用依据以官方文档、上游工程和原作者复现为主。以下提交用于固定本次查阅基线，表示所查源码的版本；文档 API 仍需与实际安装版本核对。

| 来源 | 查阅版本、许可证 | 本包采用内容与边界 |
| --- | --- | --- |
| [Xilinx/PYNQ](https://github.com/Xilinx/PYNQ/tree/d90670c69f7b71ea1a5d23aaa3e0ec713ff5fa9f) | 提交 `d90670c69f7b71ea1a5d23aaa3e0ec713ff5fa9f`；BSD-3-Clause | overlay 元数据/下载分开、连续物理内存、缓存同步和驱动合同；本包独立编写检查工具，不携带其镜像、固件或驱动源码 |
| [Xilinx/PYNQ_Workshop](https://github.com/Xilinx/PYNQ_Workshop/tree/67a8f9360b221a1c573491a7fa8eff85f857810e) | 提交 `67a8f9360b221a1c573491a7fa8eff85f857810e`；BSD-3-Clause | 参考最小 PS/PL 数据通路的教学组织；其中板卡设计和产物需按实际器件重建 |
| [Xilinx/PYNQ-HelloWorld](https://github.com/Xilinx/PYNQ-HelloWorld/tree/9728edf2ea6b7bc157acb126f773e93c3e9561c2) | 提交 `9728edf2ea6b7bc157acb126f773e93c3e9561c2`；BSD-3-Clause | 参考同任务软件/PL 对比与 overlay 打包方式；本包样例和黄金值独立构造，不复用其特定硬件 |
| [Mario Ruiz：Debugging Common DMA Issues, Part 3](https://discuss.pynq.io/t/debugging-common-dma-issues-part-3/7157) | 原作者复现文章；本次未确认页面附属代码的统一再分发许可 | 参考状态寄存器与 ILA 联合检查包长、握手和 TLAST 的方法，使用链接引用，未复制正文或代码 |
| [ra9fael/xilinx-skills 的 PYNQ Skill](https://github.com/ra9fael/xilinx-skills/blob/2713ffd8a8fb17d50ccd55714af0d8c5829e3e2f/pynq/SKILL.md) | 提交 `2713ffd8a8fb17d50ccd55714af0d8c5829e3e2f`；GPL-2.0 | 评估镜像、BSP、overlay 工作流的已有覆盖，未复制、安装或将其固定环境路径带入本包 |

## 直接支持使用方法的官方页面

- [Overlay 设计与交付](https://pynq.readthedocs.io/en/v3.1/overlay_design_methodology/overlay_design.html)：bit/HWH 配套、同名交付及设计流程。
- [Overlay 类](https://pynq.readthedocs.io/en/v3.1/pynq_libraries/overlay.html)：默认下载与 `download=False`、IP 字典和时钟设置。
- [allocate 与 Buffer](https://pynq.readthedocs.io/en/v3.1/pynq_libraries/allocate.html)：物理连续内存、设备地址、`flush/invalidate` 与同步方法。
- [DMA 库](https://pynq.readthedocs.io/en/latest/pynq_libraries/dma.html)：普通 DMA 的通道、传输和流结束要求。该页为滚动版本，具体 API 以安装的 PYNQ 驱动为准。

## 技能检索的判断

本次 CLI 搜到 `ra9fael/xilinx-skills@pynq`，结果页为 2 次安装，源仓库为 3 stars；这些是本次检索快照。其范围主要是环境、镜像和 overlay 开发，不能据此认定已经覆盖本队的双板生命周期、DMA 所有权或逐值验收。最终包把官方接口规则与本队 E01–E08 的失败/观察结合，补上有明确退出码的离线工具及正负例。

包内 Python 工具、合成样例、提示词和文字由本次任务编写。上述外部开源项目是接口与方法依据，原始项目经历来自本队日志；两种来源在[观察记录](evidence/project_observations.json)中分开。上游许可证按对应仓库文件记录，后续如复制其实现应继续核对相关文件的许可证。
