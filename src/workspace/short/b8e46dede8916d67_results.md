# Z15 正式 PL 模块与滤波核共存：Vivado 2025.2 隔离候选

2026-09-29；目标器件 `xc7z015clg485-2`，工程 `D:\ican\codex_project\gli26c\project\gl_filter_coexist_sc_20260929.xpr`。本轮只在本机创建隔离产物；没有打开 Hardware Manager，没有给 Z15 下载、修改启动镜像或切换正式 Overlay。

## 结论

- 新工程从正式 BD 导入，保留原 PS7、DMA、DE、质量、HGB 和寄存器模块及其旧连线/地址。新增 `pf_filter`、双向 `pf_dma`、`pf_control`；滤波 DMA 的两个 AXI4 主口直接接到原 HP0 SmartConnect 的新增入口，由 SmartConnect 处理到 PS7 HP0 的协议适配。生成后的 BD 再审计通过，见 `D:\ican\codex_project\gli26c\contract_audit_final.json`；正式源 BD SHA-256 仍为 `7881cb8ee55ca124bd4689b98e0cda8d64b8aaa6c2d2abfcd41a77f1cf0065cb`。
- 固定 PS FCLK0 为 50 MHz（20 ns）。`pf_dma` 地址 `0x40410000`，`pf_control` 地址 `0x41200000`；旧 DMA 仍是 `0x40400000`。配套 HWH 再次确认三者地址不冲突。复位仍由 `rst_ps7_0_50M/peripheral_aresetn` 供给新滤波、DMA、GPIO。未增加新 PL 外部引脚。
- Vivado 2025.2 综合成功。原显式 AXI4→AXI3 协议转换候选的 12 项 `REQP-1839/1840` RAMB 异步控制告警，在此 SmartConnect 候选的综合/最终布线 DRC 中均不存在。
- 最终采用独立 Explore 实现 `D:\ican\codex_project\gli26c\route6`：24,378 个可布线网络全部布通，0 个布线错误；setup WNS **+0.139 ns**、TNS 0、0 个失败端点；hold WHS **+0.033 ns**、0 个失败端点。`check_timing` 的 no_clock、unconstrained_internal_endpoints 均为 0；methodology 检查 0 项。
- 布线后使用约 10,029 个逻辑 LUT、15,843 个寄存器、19 个 BRAM tile、8 个 DSP48E1。资源报告为 `D:\ican\codex_project\gli26c\route6\utilization.rpt`。
- `write_bitstream` 自身前置 DRC 为 0 个错误，并成功生成 **隔离候选** `D:\ican\codex_project\gli26c\bit1\guardianloop_bd_wrapper.bit`（3,510,803 字节；SHA-256 `f05626df1bf429442fd43d601c3435868ffc64473b4746f62290f5b98b100031`）。配套 `D:\ican\codex_project\gli26c\bit1\guardianloop_bd_wrapper.hwh`（482,272 字节；SHA-256 `55d9e51f8c39da4605a97e5b2af67f91277a2892294f68fd89282e8c230c2653`），与生成目录中的 HWH 哈希一致。**未上板。**

## 告警与边界

- 最终 DRC 没有 Error/Critical Warning；仍有 `DPIP-1` 6、`DPOP-1` 8、`DPOP-2` 8 项 DSP 流水线优化建议，`RTSTAT-10` 1 项（40 条无可布线负载的 SmartConnect 内部复位流水线网），以及 `REQP-165/181` 的 BRAM `WRITE_FIRST` 咨询项。详见 `D:\ican\codex_project\gli26c\route6\drc.rpt`。这些没有被隐藏或降级。需继续验证 DMA/FIFO 重叠与异常复位行为，不能仅凭静态时序宣称运行安全。
- WNS 虽为正但仅 0.139 ns；这是当前实现、约束和 Vivado 版本下的静态时序结果，不保证另一实现种子、供电/温度或板端压力条件仍有裕量。首轮默认实现 WNS −0.054 ns；路由后 `-routing_opt` 到 −0.038 ns；`-clock_opt` 虽到 +0.002 ns，却引入 `PLBUFGOPT-1`，故**没有**用该检查点生成 bitstream。最终 bit 来自没有 `PLBUFGOPT-1` 的 Explore 实现。
- 现有软件仍默认 ARM 滤波，候选 PL 后端需显式选择；原正式服务和 Overlay 未替换。现场双 DMA 并发、DDR 内容一致性、完整服务延迟、断连恢复及内核缓冲区进程崩溃归属，均**不由本轮综合/布线/bit 生成证明**。在这些试验完成前，不得把 bit/HWH 当正式发布件；候选驱动也未在本轮加载。

## 可复核证据与后续

构建/检查脚本在 `D:\ican\codex_project\eeg_apps_z15\pl_filter_pipeline_candidate\`：`stage_integrated_smartconnect.tcl`、`audit_integrated_coexistence.py --direct-smartconnect`、`prepare_integrated_smartconnect_wrapper.tcl`、`synthesize_integrated_smartconnect.tcl`、`route_integrated_explore.tcl`、`generate_integrated_smartconnect_bitstream.tcl`。原始日志和全部检查点分别保存在 `D:\ican\codex_project\gli26c\` 的 `stage_sc.log`、`synth2.log`、`route6.log`、`bit2.log` 及 `synth1/`、`route6/`、`bit1/`。原正式工程及另一显式转换隔离候选未覆盖。

下一道门槛是**另行控制的上板验收**：现场再次核对正式 Overlay/可回退文件与 bit/HWH 哈希，停止冲突服务，仅临时加载此候选；先静态读版本/地址，再用既有 Cyton 记录测新滤波 DMA 与原 DMA/质量/DE/HGB 共存、双向并发、超时/复位和服务端到端耗时。任何 DMA 所有权不明或硬故障都按此前安全策略立即停止候选，并通过整板重启恢复正式 Overlay。此次没有执行这些硬件步骤。
