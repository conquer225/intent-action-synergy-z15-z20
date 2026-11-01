# 参考资料导航

原件保留原位置，完整路径、大小、SHA-256 与页数见 [来源清单](source_inventory.csv)。本次完成清单与全文检索，重点核对 AMD 自主选题条款、FPGA 板卡/工具页、Vitis 相机 HDMI 架构、PYNQ 镜像说明；不声称逐页审查了所有教程与电路。

## 文件分工

| 文件 | 页数 | 在本项目的用途 | 阅读优先级 |
| --- | --- | --- | --- |
| AMD.pdf | 28 | 自主选题规则、评分和交付 | 先读 |
| Z15 开发板用户快速体验 V1.1 | 86 | 上电、现有演示与基础外设入口 | G0 |
| Z15 FPGA 开发指南 V1.1 | 1334 | IO、板级硬件、Vivado、RTL、HDMI | G0-G2 |
| Z15 嵌入式 Vitis 开发指南 V1.2 | 876 | PS/PL、DDR、DMA/VDMA、OV5640 视频基线 | G1 与集成 |
| Z15 嵌入式 Linux 开发指南 V1.1 | 1419 | Linux 启动、驱动和自启动背景 | PS 集成按需 |
| Z15 Vitis HLS 开发指南 V1.1 | 327 | 算子综合、仿真、IP 封装 | 有软件基线后按需 |
| Z15 PYNQ 开发指南 V1.1 | 110 | 镜像、overlay、GPIO/MMIO/DMA | 最小 PS/PL 配套验证 |
| PCIe 开发指南 Windows V1.1 | 321 | PCIe 专项背景 | 当前功能范围不需要 |
| PCIe 测试文档 V1.1 | 30 | PCIe 板级测试 | 当前功能范围不需要 |
| ZYNQ7015 底板原理图 1V1 | 15 | 连接器、电平、复用和供电 | 接线前逐项核对 |
| ZYNQ7015 核心板原理图 1V1 | 14 | 器件、时钟、DDR、Bank 和供电 | 接线/约束前逐项核对 |
| Z15 IO 引脚分配表.xlsx | 不适用 | 与原理图和原厂 P2 例程核对 | 已发现 D4/PWDN 冲突，按原理图修正 |
| see.code-workspace | 不适用 | 原参考目录的编辑器工作区设置 | 已登记，不执行 |
| UUID 命名的 28 页 PDF | 28 | AMD.pdf 的重复副本 | SHA-256 相同，无需重复维护 |

## 先找这些章节

下表页码以 PDF 物理页为准。AMD 正文页比物理页少 3，厂商资料本轮核对页与印刷页一致。目录定位条目不等于完整例程已审查。

| 目标 | 文档与页码 | 当前核验 |
| --- | --- | --- |
| 初级组、PYNQ 推荐 | AMD p22，正文 p19 | 已读条款 |
| 工具版本、上板、开源 | AMD p23，正文 p20 | 已读条款 |
| 工程/Skill/报告、命名 | AMD p24，正文 p21 | 已读条款 |
| 评分权重与赛程 | AMD p25，正文 p22 | 已读条款 |
| 决赛海报与最终细则 | AMD p28，正文 p25 | 已读条款 |
| IO 分配、器件 | FPGA p91、p132 | 已核对文字 |
| PL UART 与 J24 复用 | FPGA p119 | 已核对文字，待对照实物 |
| P2 摄像头接口 | FPGA p120 | 已核对文字，待看实际模块 |
| HDMI 电路区别 | FPGA p123 | 已核对文字 |
| PS DDR、PL 时钟 | FPGA p135、p138 | 已核对文字，未测量 |
| Vivado/Vitis/HLS 2023.1 | FPGA p145、p150 | 已核对文字 |
| LED 与基本开发过程 | FPGA 第 7 章 p184 起 | 目录定位 |
| HDMI 彩条 | FPGA 第 29 章 p667 起 | 目录定位，优先寻找原厂源码 |
| PL 读写 PS DDR | Vitis 第 20 章 p364 起 | 目录定位 |
| AXI DMA 环路 | Vitis 第 21 章 p399 起 | 目录定位 |
| OV5640 到 HDMI | Vitis 第 27 章 p564 起 | 已读 p564-565，采用 PS DDR/VDMA 路径 |
| OV5640 灰度 | Vitis 第 30 章 p601 起 | 已读章节入口，示例显示为 LCD，需适配 HDMI |
| OV5640 二值化 | Vitis 第 31 章 p618 起 | 已读章节入口，不能当作眼动识别完成 |
| Linux 开机自启动 | Linux p540 的相关条目 | 目录定位 |
| PYNQ 镜像 | PYNQ p16、p19 | 已读：出厂镜像不支持 PYNQ，需专用 SD 镜像 |
| PS-PL 交互 | PYNQ p53 起 | 已读接口背景 |
| 最小 overlay | PYNQ GPIO p55、AXI GPIO p68、MMIO p77 起 | 目录定位 |

## 几个需要保留的事实

Z15 的 HDMI OUT 与 HDMI IN 电路不同；不能移植任意 PYNQ 板的 base overlay 当作本板驱动。PS DDR 依赖 PS 配置和初始化，视频基线应先复现厂商 Vitis 例程，再决定如何接 PYNQ。

PYNQ 指南 p16 指向资料盘 `4_SourceCode/6_PYNQ_Design/IMG` 下的 `Z15-2.7.0.zip`，还出现历史 `vivad0_2020.2_A` 路径。p19 描述 Ubuntu 20.04 和 Linux 5.4.0。这些是手册描述，不代表当前板上实际版本或与 2023.1 已兼容。

后来已找到原厂工程 `E:/cankao/XC7Z015/XC7Z015/` 和 Vitis 目录 `E:/cankao/2_Embedded_Vitis/XC7Z015/XC7Z015/`，用于相机配置、引脚和接口核对。当前独立眼控不使用 PS DDR；PYNQ 镜像仍未核验。

2024 易灵思瞳孔追踪作品、PuRe、ElSe 和开源代码的具体来源及适用限制见 [眼控研究记录](eye_research.md)；实际复用文件和许可证见 [THIRD_PARTY.md](../THIRD_PARTY.md)。

## 旧方案

`Z15_Multimodal_Embedded_Skeleton_v1.zip` 记录多模态功能、分工建议、接口草案、模块用途和验收方向。它不是安装包，非 README 文件全部为空。主文档已吸收其方案，原 ZIP 保留作为来源快照，后续功能由新工程真实源码与测试记录决定。
