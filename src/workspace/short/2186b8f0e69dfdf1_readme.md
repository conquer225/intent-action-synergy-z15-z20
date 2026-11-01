# 当前固定八通道公共滤波：独立 PL 候选

## 最新：显式协议转换器隔离候选（2026-09-28）

在另一个隔离副本里，用两路显式 AXI4→AXI3 转换器替代了内存互连自动转换器，模式 0；Vivado 2025.2 BD 校验和原版 VIP 下三场景总线侧仿真通过，16 拍突发前提有自动检查。用户随后授权对隔离副本重新综合、布局布线：**50 MHz 布线后 WNS +4.627 ns、WHS +0.049 ns；旧 12 项 RAMB 异步控制警告归零，但 LUTAR-1 仍有 1 项位于显式写转换器。**原版 VIP 的 DDR 读回仍失败，运行时跨进程缓冲所有权也未解决；不生成 bitstream、不上板。详见[显式转换器结果](../output/pl_protocol_explicit_20260928/RESULTS.md)。

## 最新：DDR、复位 DRC 与缓冲区所有权准入（2026-09-28）

原版 PS7 VIP 的严格 DDR 读回仍失败；独立 AW/W/B 影子内存核对通过，但只证明 HP0 接口侧，不能冒充 DDR 合格。既有 12 项 RAMB 与 3 项 LUT 异步复位警告未关闭；隔离工程直接修改自动协议转换器参数被 Vivado 拒绝。ARM 候选仅在存活进程内隔离可疑 CMA 缓冲区，进程死亡后的物理内存所有权尚无保证。**不得生成 bitstream 或接入正式服务。**完整证据见[三道门槛审计](../output/pl_next_gates_20260928/RESULTS.md)及[缓冲区所有权合同](BUFFER_OWNERSHIP_CONTRACT.md)。

## 最新：互连复位警告与在途事务边界（2026-09-27）

隔离候选的 DMA MM2S FIFO 仍有12项BRAM异步控制警告，协议转换器FIFO仍有3项LUT异步复位方法学警告；不能据此宣称风险已清除。此前ARM寄存器模型与滤波AXIS帧中复位仿真通过，见[早期审计](../output/pl_dma_inflight_audit_v2025_2_20260927_retry2/RESET_DMA_AUDIT.md)。**现在已加入 Vivado 2025.2 生成的真实 AXI DMA 与读/写 AXI4→AXI3 转换器联合仿真：在下游内存保留未完成突发的条件下，外部PL复位后重新启用会混入旧读数据或把新写数据接到旧缓冲区。仅软件复位不会修复先前已被外部PL复位切断的读事务。**只有测试模型明确冲刷内存侧未完成事务的对照才通过。这是隔离仿真中的条件性风险证据，不是PS7 HP0实际复位语义或板端实测；因此仍未批准bitstream/上板。详见[厂商IP联仿报告](../output/pl_vendor_dma_cosim_v2025_2_20260927/RESULTS.md)。

## 最新：隔离分拍候选通过50 MHz布局布线（2026-09-27）

用户授权在隔离副本内修改关键路径并重新仿真、综合、实现。乘积前置寄存器使裸核81,728字、AXIS 81,120字和顶层160字逐字回归通过；完整布线WNS **+4.473 ns**、WHS **+0.079 ns**，10,746条可布线网络全部完成。单字处理从25拍变为50拍。仍有DRC和互连异步复位警告，未生成bitstream、未上板、未批准生产部署。见[新候选的完整证据](../output/pl_pipeline_route_v2025_2_20260927/RESULTS.md)。下文原版及边缘物理优化的数字保留为历史对照。

## 最新：布局布线完成，50 MHz时序尚未通过（2026-09-27）

用户已授权对修复候选做2025.2布局布线验证；仍未授权bitstream或上板。实际结果在 `../output/pl_route_v2025_2_20260927_retry2/`：10,705条可布线网络全部完成，布线错误0，但WNS **−0.025 ns**、TNS −0.077 ns、5个建立时间违规端点；保持裕量+0.034 ns。不能将综合阶段+2.690 ns当作实际时序通过。

布线后资源4,258 LUT、7,341 FF、4 DSP、3 BRAM。34项DRC（含原12项BRAM异步控制）以及3项LUT驱动异步复位方法学警告尚未豁免。最差路径为滤波状态选择经乘加/舍入到z1寄存器，33级逻辑。下一步可先评估单独的布线后物理优化，必要时对算术链分拍并重新回归；不能直接部署。未生成bitstream、未改变板上服务。[完整实现结果](../output/pl_route_v2025_2_20260927_retry2/RESULTS.md)。下文为先前阶段记录。

## 当前状态：复位修复及重新综合完成（2026-09-27）

用户已授权修复隔离候选、补检查/仿真并用2025.2重新综合。**未授权布局布线、bitstream或上板。** 新结果在 `../output/pl_dma_reset_fixed_v2025_2_20260927/`，旧故障工程与证据保留。

旧复位IP `C_AUX_RESET_HIGH=0`（低有效）却把aux接0，导致持续复位；现已改接1，debug仍接0。补充真实生成参数/全链路复位连接审计，新工程通过，旧错误接法被拒绝；13项错误配置负例全部被拦截。使用新工程生成的官方复位IP封装，启动释放和3次重复复位/恢复通过，脉宽与功能模型边沿检查通过。此前裸核/AXIS测试不包含这层复位，漏检原因及旧失败证据见 [原复位审计](../output/pl_reset_audit_20260927/RESET_AUDIT.md)。

重新综合完成，0错误、0关键警告；4,570 LUT、7,476 FF、4 DSP、3 BRAM，50 MHz综合估计WNS +2.690 ns、WHS +0.036 ns。12项BRAM异步控制警告仍存在，未豁免，尚不证明完整DMA复位恢复或物理时序安全。板上生产服务未改。详见 [修复后的结果与复现步骤](../output/pl_dma_reset_fixed_v2025_2_20260927/RESULTS.md)。下文首次综合数值作为历史记录保留，当前结果以新目录为准。

## 当前工具与授权（2026-09-27）

用户已明确指定 **只用 Vivado 2025.2**，安装路径已实测为 `D:/ruanjian/2025.2/Vivado/bin`（SW Build 6299465）。不是 `D:/ruanjian/amd/2025.1`；此前遗漏了前一个目录。下面2025.1证据仅作为历史记录。`validate_candidate_bd.py` 和 `synthesize_candidate.tcl` 均禁止回退到2025.1。

用户本轮仅授权隔离候选综合及 DSP/LUT、关键路径检查；**未授权实现、bitstream生成或烧写**。综合脚本只启动 `synth_1`，不启动 `impl_1`，也不调用任何硬件管理命令。

2025.2证据目录：`../output/pl_filter_v2025_2_20260927/`（流接口/控制仿真）和 `../output/pl_dma_bd_v2025_2_20260927/`（BD、工程及综合报告）。结果必须以对应日志为准；综合后时序只是估计，不能当作布局布线后收敛或实测加速。

状态：**浮点→定点、裸核/AXI-Stream/复位状态接口仿真、ARM DMA 寄存器模型测试通过；已用 Vivado 2025.2 完成隔离候选全局综合及综合后资源/时序检查。未实现、未生成bitstream、未部署。**

## 本轮综合结论（Vivado 2025.2）

目标 `xc7z015clg485-2`、`clk_fpga_0=50 MHz`（20 ns）。工程为 `../output/pl_dma_bd_v2025_2_20260927/project/pl_filter_candidate_dma.xpr`，检查点为该目录下 `pl_filter_candidate_dma.runs/synth_1/filter_candidate_wrapper.dcp`。源RTL/系数未改，2025.2下AXIS 81,120字/1,014帧和控制封装160字回归通过；155项PS参数与原BD一致。

全局候选包含滤波核、双向64位DMA、GPIO、互连及PS封装，不是裸核资源，也**不是与现有质量/DE/HGB等PL模块合并后的全业务资源**：

- LUT：4,570 / 46,200，9.89%。
- FF：7,476 / 92,400，8.09%；推断锁存器为0。
- DSP48E1：4 / 160，2.50%。
- BRAM Tile：3 / 95，3.16%（2个RAMB36加2个RAMB18）。
- 分层 `pf_filter`（含AXIS封装）：1,664 LUT、3,435 FF、4 DSP、0 BRAM；其中裸 `primary_sos_core` 为1,650 LUT、3,426 FF、4 DSP。

综合后时序估计：WNS **+2.690 ns**、TNS 0、建立时间失败端点0；WHS **+0.036 ns**、THS 0；WPWS +8.870 ns。一个已约束时钟；无缺失时钟、无未约束内部端点、无组合环。**这些不是布局布线后的时序，不证明板上速度或整机加速收益。**尤其保持时间裕量需实现后重新检查。

最差路径：

```text
filter_candidate_i/pf_filter/inst/axis_core/core/FSM_sequential_state_reg[2]/C
  -> 系数/操作数选择 -> DSP级联乘法 -> 宽位加减/舍入 -> 溢出判断
filter_candidate_i/pf_filter/inst/axis_core/core/overflow_reg/D
```

数据路径16.906 ns，其中逻辑11.265 ns、估计布线5.641 ns；33级逻辑包括21个CARRY4、2个DSP48E1及LUT。`y_value`若干端点也具有同样最差裕量。根据报告和源码对应关系，主要风险在滤波算术链，不在AXI控制地址。若实现后不收敛，应优先研究乘法输出/累加/舍入的流水线切分；本轮没有擅自改算法或放宽50 MHz目标，也没有添加隐藏false path。

综合阶段0错误、0关键警告，但不是零警告。综合后DRC有30项：

- 14项DSP流水线警告：DPIP-1=6、DPOP-1=4、DPOP-2=4。当前未使用DSP的完整输入/乘积/输出寄存流水线，工具建议改善性能/功耗。
- 12项BRAM异步控制警告：REQP-1839=8、REQP-1840=4，涉及DMA FIFO及互连控制路径。复位断言下的存储器行为不由普通STA充分覆盖；需要继续核对复位/恢复行为，不能直接豁免。
- 4项WRITE_FIRST advisory：REQP-165=2、REQP-181=2，需要确认FIFO协议保证读写地址冲突行为符合预期。

其他生成阶段警告包括标准互连AXI ID位宽适配、GPIO单引脚绑定、目录内不相关板卡定义缺少器件，以及未使用IP端口/寄存器裁剪。完整日志保留；未修改告警等级。上述DRC结果是综合网表检查，不代替实现后的完整DRC。

完整证据位于 `../output/pl_dma_bd_v2025_2_20260927/synthesis_reports/`：`synthesis_audit.json`、`utilization.rpt`、`utilization_hierarchical.rpt`、`clocks.rpt`、`check_timing.rpt`、`timing_summary.rpt`、`critical_paths.rpt`、`drc.rpt`、`timing_metrics.txt`。审计保留源码、仿真、日志、报告和DCP哈希，并检查候选目录没有bitstream或实现运行日志。

下一阶段先核对BRAM复位告警，再在取得**实现（布局布线）授权**后检查实际时序/资源和实现DRC；仍可不生成bitstream、不接触板卡。真实DMA往返及ARM/PL耗时比较需要后续受控上板授权。板上正式服务与模型未改，本轮不需要佩戴。

这是隔离的工程候选，不被 Cyton 正式服务导入。固定顺序仍是 `F3,F4,C3,C4,T7,T8,O1,O2`。只覆盖公共预处理 `CausalEEGFilter`：250 Hz、50 Hz Q=5 陷波、四阶 1–45 Hz Butterworth 带通，共五个 SOS。不包含 SSVEP 独立 6–45 Hz 滤波、SQI、DE、协方差、分类器或实时服务状态机。

## 定点合同

- 输入和 SOS 状态：有符号 40 位，16 个小数位，单位 µV；范围约 ±8,388,608 µV，分辨率 1/65536 µV。不是旧 `int16/0.01 µV` 的 ±327.67 µV 窄格式。
- 系数：有符号 34 位、31 个小数位，SOS 分母首项固定为 1。每级 ROM 顺序 `b0,b1,b2,a1,a2`，五级共 25 项。系数的 +2 必须可表示，故不能直接使用 signed32 Q31。
- 乘积 74 位，累加 76 位。每次输出或状态窄化均先四舍五入，恰好半值时远离零；超范围饱和、不回绕，同时置位 sticky `overflow`。不能把饱和后的样本当作可用 EEG。
- ARM 在会话/重置后的首个样本记录每通道 origin；送入本核的是 `raw_uv - origin` 的量化值，复现现有滤波类。原始数据、ADC 饱和、包序号和工频告警仍保留在 ARM，不能用滤波后波形替代原始质量证据。
- DF-II-transposed 每级：`y = round(b0*x+z1)`，`z1' = round(b1*x-a1*y+z2)`，`z2' = round(b2*x-a2*y)`；乘法项和状态项先对齐到统一的 47 个小数位，然后舍入回 16 位小数。

## HDL 端口、复位与周期

`primary_sos_core.sv` 是单时钟、顺序处理的裸核。输入为 `in_valid/in_ready`、3 位 `in_channel`、40 位 `in_data`；输出为 `out_valid/out_ready`、通道号和40位结果，另有 sticky `overflow`。上游必须遵守 ready/valid，忙时输入不会被接收。

- 五级、每级五个算术步骤；接受输入后 25 个计算周期得到输出。无反压时相邻输入接受间隔为 27 周期。一个样本时刻的八通道依次发送；每个通道保留独立状态。
- 同步高有效 `rst` 清空全部通道状态、输出 valid、溢出标志，并丢弃在途事务。发生断连、时间/包不连续等重置事件时，未来适配器必须同步重置 origin、核状态以及下游热身/结果；本裸核不自行推断这些事件。
- 输出未被接受时，数据/通道/valid 稳定。本核没有 CDC。AXI/DMA 时钟跨域只能由经验证的桥实现，不能直接将异步信号接入。
- 裸核/AXIS测试台的10 ns周期只是仿真节拍，**不是确认能在板上达到100 MHz**。当前已取得50 MHz候选综合资源及估计时序，见上文；布局后时序、实测Fmax和功耗未验证。
- 已实现 `primary_sos_axis.sv` 流接口及 `primary_filter_top.sv` 故障/复位封装，候选 DMA 接线见下文；**尚无上板验证和实现后时序证据**，不得直接替换正式 Overlay。现有旧模型 PL 的通道/模型 ABI 不适用。

### AXI-Stream 帧合同

64位 `TDATA`，低40位是有符号定点值，高24位必须是符号扩展，`TKEEP=0xff`。每帧固定80字，样本优先、通道从0到7；第80字且仅第80字携带 `TLAST`。输出保持同一顺序和TLAST；反压期间结果保持不变。每帧10个八通道样本，不在批次之间清滤波状态。

输入符号扩展/TKEEP/TLAST错误或内部数值溢出均置sticky `fault` 并停止接受/输出，必须显式复位才能恢复。错误发生前该帧可能已有部分输出；ARM 候选适配器现已实现整帧拒绝、有界轮询及显式复位合同，**不对 S2MM 调用无限期 wait**。软件寄存器模型和 RTL 状态接口分别验证，不等于真实 AXI DMA 硬件恢复已通过。

## 证据与失效保留

预设数值门槛：最大绝对误差 ≤0.05 µV、RMS ≤0.01 µV；正常/记录/ADC 满量程测试不能内部饱和；分块处理必须逐位一致。

首版 signed32/29 位小数系数在 ADC 满量程交替输入下最大误差 **0.0590 µV**，不通过。原始失败记录保存在 `../output/pl_primary_filter_20260927/numerical.json`。提高系数精度两位后同测试最大误差 **0.0140 µV**；未放宽门槛。当前精度的各量化 SOS 极点模均 <1。

最终记录在 `../output/pl_primary_filter_q31_20260927/`：

- `numerical.json`：8 组输入，合计 89,232 个八通道样本时刻，包括 39,000 点非佩戴台架记录、20,232 点既有 Cyton 记录，以及工频、pop、脉冲、零输入、满量程压力。台架最大误差约 0.00545 µV；既有 Cyton 记录约 0.00546 µV。正常测试无内部饱和；专门的越界压力产生120次状态/输出窄化饱和。
- `vectors.txt` / `rtl_audit.json`：81,728 个通道采样字与软件定点输出逐位一致，含反压、处理中复位、跨案例重置和饱和告警。RTL使用记录前缀和完整pop过渡，不等于对所有89,232个八通道样本都做了RTL仿真。
- `axis_overflow_audit.json`：81,120字、1,014个完整DMA候选帧逐字一致；四类格式错误（早到/缺失TLAST、部分TKEEP、错误符号扩展）、中途复位、输出反压和数值溢出后的停止输出均通过。此前未含数值溢出的初版接口审计 `axis_audit.json` 也保留；以扩展审计为准。
- `downstream.json`：两份记录的29个非重叠8秒窗口中，SQI可用/校准状态及坏通道名单无变化；73+35个协方差特征窗口的诊断分类无变化。最大协方差特征差约0.00315，DE特征差约0.00218。这里没有完整包序号/断连状态机，部分窗口不合格，诊断分类不能视为有效实时预测；没有疲劳模型最终PERCLOS等价证明。
- `arm_micro.json`：板上生产公共滤波系数与PC导出的浮点系数逐项相同。只读微测保持生产服务运行，三轮公共滤波 CPU 约4.00–4.05秒/39,000样本；每10×8样本的中位墙钟约0.984–1.023 ms；定点打包中位约0.185–0.193 ms。不是单服务端到端加速对照。

既有Cyton记录来源为2026-09-23文件；通道映射是用户声明，历史参考接法无法仅由TXT证明。仅作数值输入，不声称改善真实识别准确率。SSVEP是另一条滤波支路，不由本核替换。

## 速度收益判据与下一个接口步骤

单服务负载验收中ARM缓存候选已达到P95约212–220 ms。本滤波核不是已证实的最大瓶颈，约4秒CPU/156秒输入的组件成本意味着潜在整体节省仅是几个百分点，不能宣称整机数倍加速。

若用64位DMA字承载40位定点样本，每批10×8样本输入640 B、输出640 B，在250 Hz时各方向16 kB/s。带宽不大，**调用/缓存一致性/同步等待延迟才可能抵消收益**。完整 `打包 + DMA发送/接收 + 核计算 + 解包` 必须低于同批ARM滤波约1 ms；应保留明确余量，建议目标≤0.7 ms，且全链路P95不能恶化。这是待验证工程门槛，不是已测的PL速度。

### 已查明的上板接口缺口

2026-09-27只读解析板上 `/home/xilinx/jupyter_notebooks/guardianloop_pynq/guardianloop_pynq.hwh`，`axi_dma_0` 配置为 `C_INCLUDE_MM2S=1`、`C_INCLUDE_S2MM=0`、`C_INCLUDE_SG=0`，MM2S流宽128位、长度字段16位。**现有工程配置只有送入PL的DMA，没有滤波结果返回ARM的S2MM**，不能直接把本64位进出核接上旧Overlay。这描述安装文件，不证明当时芯片内加载了哪一个配置。

现有主要工程 `D:\ican\ican_fpga_project\GuardianLoop_Z15_2025_1\GuardianLoop_Z15_2025_1.xpr` 声明 part=`xc7z015clg485-2`、BoardPart为空；其 `guardianloop_bd.bd` 的 PS 参数给出 FCLK0=50 MHz、GP0/HP0 开启。候选复用该文件的全部 PS 参数，不从早期加一例程猜测 DDR/MIO。该 BD 标记工具版本2025.2，本机验证工具2025.1；原工程未改动，实体板修订号和电气约束仍需在真正上板前确认。

已补充双向 DMA 接线脚本和独立 ARM 后端；在正式服务中仍默认使用 ARM 浮点路径。候选不含旧 Overlay 的质量/DE/HGB 核，**即使生成候选 bitstream，也只能先做隔离往返实验，不能加载后照常启动依赖旧核的正式服务**。完整多任务部署需要共存集成或明确关闭依赖旧核的支路并完成恢复验证。

## ARM DMA 与控制接口（2026-09-27 新增）

`primary_filter_dma.py` 不加载 Overlay，不探测硬件地址，不被正式服务导入。**2026-09-28 起默认禁止物理 DMA：构造时在首次 MMIO/分配前拒绝。** 仅寄存器模型测试显式传入 `test_only=True`。原先由调用者传入 `pynq.allocate` 的设计无法在进程崩溃后保留 CMA 页；此前的说明仅保留作为测试接口历史，不能用来上板。恢复物理路径必须先有经验证的内核持有缓冲区租约与 PS/HP 恢复方案。只支持64位双向、无SG、32位地址；旧128位单向DMA被拒绝。

- 使用标准双通道 AXI GPIO：通道1 DATA相对偏移 `0x00`，bit0软件复位（硬件默认1）；通道2 DATA相对偏移 `0x08`，bit0为reset、bit1为sticky fault，其余为固定签名 `0x50460000`。基址由候选 HWH 解析，不沿用旧 `0x40400000`。方向寄存器相对偏移 `0x04/0x0c`。签名只说明接口 ABI，不证明模型/系数版本；上板需同时核对bit/HWH/系数哈希。
- `reset()`：无不确定在途事务时，DMA公共复位→确认双方halt→核复位→清origin→启动双方DMA。若上一批已提交而未通过完整双向完成检查，直接拒绝PL-only重启；外部PL复位后的PS/HP旧突发不能靠此调用证明清除。故障对象保留在隔离表，不能手工清空。
- `process(raw_uv)`：固定10×8有限浮点数、首样本去偏置、40/16量化→flush→清旧完成中断→先S2MM后MM2S→检查双方完成且idle、DMA错误、核状态、返回字节数与符号扩展→invalidate→解包。任一已提交批次的异常拒绝整批、禁止本PS会话内重启，须在确认PS/HP总线事务清空的受控恢复后重新热身。不能在此处静默切回一个状态不一致的ARM滤波器。
- `close()`：无不确定在途事务且确认DMA复位并双方halt后调用 PYNQ `freebuffer()`；板上 PYNQ 的 `PynqBuffer.close()` 是空操作，已纠正旧候选误用。若总线所有权未知则抛错并保持缓冲区引用；进程被强制结束时Python隔离表也会消失，因此仍不能把它当作硬件级安全保障。**当前物理构造入口整体禁用。**
- AXI DMA 寄存器来自本地 `D:/ican/codex_project/vitis_qspi_verify_20260910/guardianloop_qspi_verify_platform/zynq_fsbl/zynq_fsbl_bsp/include/xaxidma_hw.h`，GPIO偏移来自 `D:/ruanjian/amd/2025.1/data/embeddedsw/XilinxProcessorIPLib/drivers/gpio_v4_12/src/xgpio_l.h`，不是猜测的设备基址。

`dma_adapter_final_audit.json`：13项软件测试通过（2项定点测试、11项DMA测试方法，含多场景子测试），并解析最终接线脚本的Tcl过程定义。覆盖连续状态逐位一致、接收先行、DMA错误/核故障/半帧/符号错误/超时/未idle、旧中断、错误HWH、复位超时保留内存和分配失败清理。它使用软件寄存器模型，不模拟真实缓存、AXI总线仲裁或DMA IP内部逻辑。此前 `dma_adapter_audit.json` 对应较早接线脚本，保留但不代表最终脚本哈希。

`control_audit.json`：顶层RTL 160字/两帧与既有golden逐位一致；故障状态可见且保持、软件复位恢复、在途复位无旧结果、外部复位通过。20 ns仿真时钟不代表50 MHz时序收敛。

`attach_candidate.tcl`：仅定义接线过程，单独source不改项目。只允许名称以 `pl_filter_candidate` 开头的隔离工程、已核对part/50 MHz/有效低复位及空闲AXI端点；连接64位双向DMA、GPIO及滤波核，自动分配AXI地址。原工程GP0/HP0已占用，不能直接调用覆盖；它要求独立候选shell。

`validate_candidate_bd.py`：从原BD提取完整PS参数，在新目录重建候选shell，连接同步复位及GP0/HP0时钟，调用上述过程做BD验证。不会启动综合/实现、生成bit、连接板卡或修改原BD。BD是否实际通过以该次输出的 `bd_audit.json` 为准，不能用Tcl语法解析成功代替。

最终实跑输出为 `D:/ican/codex_project/eeg_apps_z15/output/pl_dma_bd_20260927_final/`：

- `bd_audit.json`：Vivado 2025.1 验证通过，退出码0，无关键警告；核对自动传播的外部复位为低有效。仅执行BD校验，没有调用综合/实现/bitstream。
- `contract_audit.json`：保存后的候选BD与原BD的 **155项 PS 参数逐项相同**；双向64位流、TKEEP/TLAST、50 MHz同一时钟域及GPIO默认保持复位均通过结构检查。
- `project/pl_filter_candidate_dma.xpr`：独立候选工程。自动分配的DMA/GPIO基址本次为 `0x40400000/0x41200000`，不作为未来运行时硬编码依据；MM2S和S2MM均映射HP0的1 GiB DDR区。
- 非关键警告仍保留在日志：模块初次推断时缺省 FREQ_HZ（保存后的核时钟和两个流接口已核对为50 MHz）；GPIO单独引脚连接覆盖接口绑定（由本项目接线脚本复现，不使用自动导出Tcl作为唯一来源）。不能称作零警告工程。
- 前几次失败分别为长字符串PS参数导入、保护条件误匹配候选shell、BD顶层文件类型、流接口单针接线，以及尝试写只读复位参数。失败目录和日志保留；旧 `pl_dma_bd_20260927_verilog/bd_audit.json` 虽原工具退出成功，但因关键警告已明确判失败。最终记录才是后续综合的输入。

BD之后的综合已获本轮明确授权并完成；实现/bitstream/板上加载仍需对应授权。收益门槛不变：完整DMA调用成本目标≤0.7 ms，且多任务端到端P95不恶化；无收益则不替换生产ARM路径。

## 复现（使用新的输出目录）

```powershell
cd D:\ican\codex_project
D:\Users\lenovo\anaconda3\python.exe -m unittest discover -s eeg_apps_z15\pl_filter_candidate -p test_fixed_sos.py -v
D:\Users\lenovo\anaconda3\python.exe eeg_apps_z15\pl_filter_candidate\validate_fixed.py --output eeg_apps_z15\output\pl_filter_new_run
D:\Users\lenovo\anaconda3\python.exe eeg_apps_z15\pl_filter_candidate\run_simulation.py --output eeg_apps_z15\output\pl_filter_new_run --vivado-bin D:\ruanjian\2025.2\Vivado\bin
D:\Users\lenovo\anaconda3\python.exe eeg_apps_z15\pl_filter_candidate\run_simulation.py --suite axis --output eeg_apps_z15\output\pl_filter_new_run --vivado-bin D:\ruanjian\2025.2\Vivado\bin
D:\Users\lenovo\anaconda3\python.exe eeg_apps_z15\pl_filter_candidate\run_simulation.py --suite control --output eeg_apps_z15\output\pl_filter_new_run --vivado-bin D:\ruanjian\2025.2\Vivado\bin
D:\Users\lenovo\anaconda3\python.exe eeg_apps_z15\pl_filter_candidate\audit_adapter.py --output eeg_apps_z15\output\pl_filter_new_run\dma_adapter_final_audit.json
D:\Users\lenovo\anaconda3\python.exe eeg_apps_z15\pl_filter_candidate\validate_candidate_bd.py --source-bd D:\ican\ican_fpga_project\GuardianLoop_Z15_2025_1\GuardianLoop_Z15_2025_1.srcs\sources_1\bd\guardianloop_bd\guardianloop_bd.bd --evidence eeg_apps_z15\output\pl_filter_new_run --output eeg_apps_z15\output\pl_dma_bd_new_run --vivado-bin D:\ruanjian\2025.2\Vivado\bin
D:\Users\lenovo\anaconda3\python.exe eeg_apps_z15\pl_filter_candidate\audit_bd_contract.py --source-bd D:\ican\ican_fpga_project\GuardianLoop_Z15_2025_1\GuardianLoop_Z15_2025_1.srcs\sources_1\bd\guardianloop_bd\guardianloop_bd.bd --candidate-bd eeg_apps_z15\output\pl_dma_bd_new_run\project\pl_filter_candidate_dma.srcs\sources_1\bd\filter_candidate\filter_candidate.bd --reset-wrapper eeg_apps_z15\output\pl_dma_bd_new_run\project\pl_filter_candidate_dma.gen\sources_1\bd\filter_candidate\ip\filter_candidate_pf_shell_reset_0\synth\filter_candidate_pf_shell_reset_0.vhd --output eeg_apps_z15\output\pl_dma_bd_new_run\contract_audit.json
D:\Users\lenovo\anaconda3\python.exe eeg_apps_z15\pl_filter_candidate\run_reset_regression.py --build eeg_apps_z15\output\pl_dma_bd_new_run --vivado-bin D:\ruanjian\2025.2\Vivado\bin
```

失败首版可用 `validate_fixed.py --coeff-bits 32 --coeff-frac 29 --output <新目录>` 复现；它不符合当前RTL格式，不能用当前RTL冒充验证首版。
