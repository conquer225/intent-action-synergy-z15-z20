# HP0 DDR 与崩溃后缓冲区所有权：2026-09-28 准入状态

本文件是隔离候选的工程门槛，不是已部署说明。板端正式 ARM 路径及 Overlay 本轮未改。

## 已验证

- Vivado/XSim 2025.2 原版 PS7 VIP：直接驱动 HP0 的最小探针 5×16 个 64-bit 字，AW/W/B 全部成功；后门和前门读回各有末尾 16 字不符。原样本地重编官方源码仍复现；见 [`../output/pl_hp0_ddr_diagnosis_v2025_2_20260928/RESULTS.md`](../output/pl_hp0_ddr_diagnosis_v2025_2_20260928/RESULTS.md)。
- 本轮再次独立运行原版探针，见 [`../output/pl_hp0_stock_recheck_20260928/probe.log`](../output/pl_hp0_stock_recheck_20260928/probe.log)：`AW=5 W=80 B=5`，`backdoor_mismatches=16 frontdoor_mismatches=16`，首错字 64，严格断言失败。这是预期失败的证据，脚本返回 0 仅表示“已识别并记录失败”，不是 DDR 验收通过。
- AMD [DS940](https://docs.amd.com/api/khub/documents/qWhIQ_YlwuQYtWV9XHaUsQ/content) 规定 DDR `write_mem`/`read_mem` 起始地址须 32-bit 对齐、长度单位为字节且最大 128；现有探针的地址以 8 字节递增、每次长度 8，满足这些文档约束。
- 原版内部请求和数据在同一仿真时间槽的更新顺序可解释末尾漏写；只在隔离副本把请求断言延后一个 delta 时，最小探针 0/80 不符、完整链路严格数值通过。但这不是 AMD 发布的修复，也不能证明实物 DDR。
- Z15 只读检查：Linux `5.4.0-xilinx-v2020.2`；`CONFIG_DMA_CMA=y`；内核构建目录存在；`/dev/xlnk` 存在；没有发现 `/dev/udmabuf*`、`/dev/dma_heap/*` 或设备树 `reserved-memory` 节点。当前 PYNQ 源码 `pynq/pl_server/embedded_device.py:468` 实际用 XRT 分配，故不能把 `/dev/xlnk` 的存在误认为这个路径的缓冲区持有者。检查未加载模块或修改板卡。
- Z15 的 `pynq/buffer.py:107` 中 `PynqBuffer.close()` 是兼容性空操作；`freebuffer()` 才转交/释放底层指针，`pynq/pl_server/xrt_device.py:138` 中相应 XRT 路径调用 `xclFreeBO`。原候选正常关闭/错误分配路径错误地调用 `.close()`，现已改为 `.freebuffer()`，模型测试会主动拒绝误用 `.close()`。
- `PrimaryFilterDMA` 曾使用调用进程的 `pynq.allocate` 两块 640 字节 XRT/ZOCL 缓冲区。其 Python `_quarantined` 只保护仍存活的进程。现已默认在任何 MMIO/分配前拒绝物理模式；仅寄存器模型测试传 `test_only=True`。14 项常规和 3 项在途模型测试通过。**这关闭危险软件入口，不代表跨进程所有权已实现。**
- `output/` 下历史仿真证据目录中可能有旧版 `primary_filter_dma.py` 快照，保留原样以维护证据；任何上板集成都不得从这些快照导入。正式服务当前未导入本候选。

## 不可混淆的两个问题

1. 原版 PS7 VIP 读回失败尚无厂商确认的修复。不得删除末尾 16 字断言、额外写一笔“冲刷”、把诊断修改混进生产仿真，或将 AW/W/B 影子内存通过说成 DDR 通过。最小复现和正式提问草稿位于 [`../output/pl_next_gates_20260928/AMD_VIP_REPRO.md`](../output/pl_next_gates_20260928/AMD_VIP_REPRO.md)。官方修复或独立实物 DDR 读回，至少需要其中之一。
2. 软件锁、磁盘故障标记、`atexit`、DMA `Halted/Idle` 都不能持有已在途的物理页。需要一个不随工作进程退出而释放缓冲区的内核所有者，或经设备树预留且不归普通内存分配器的固定区。两者都需要独立审查及受控板测。

可研究的免新驱动路线：当前 XRT/ZOCL 理论上支持 [BO 导出 DMA-BUF FD](https://xilinx.github.io/XRT/2020.2/html/xrt.main.html)，由独立持有进程或 systemd FD store 持有引用。板上 systemd 为 245；它支持 `FileDescriptorStoreMax=`，但较新的 `FileDescriptorStorePreserve=` 不可假设存在。尚未验证本板 XRT 导出是否成功、FD 被保留后物理地址是否稳定、异常终止/重启限额/手动停服务如何处理。即使该路可行，也必须先通过同样的杀进程与在途写故障实验；目前不能替代内核持有合同。

## 候选内核持有者的必要合同（离线候选已编写，板上未验收）

2026-09-28 用户授权后，已在 [`kernel_owner/`](kernel_owner/) 编写第一方隔离模块，匹配 `5.4.0-xilinx-v2020.2` 的 ARMv7 交叉编译通过，离线共享状态机测试通过；见 [`../output/kernel_owner_offline_20260928/RESULTS.md`](../output/kernel_owner_offline_20260928/RESULTS.md)。以下条目只有源代码/离线检查，不代表板上通过：

- 模块/保留内存设施独占持有成对 TX/RX 缓冲区，地址在整个内核所有者生命期不变；工作进程只获得受限映射或复制接口，不决定释放物理页。
- 只有一个工作会话可提交，提交前原子锁存 `IN_FLIGHT`；SIGKILL 后页依旧持有、故障锁存为 `UNKNOWN`，后继会话只读状态、不得提交或回收。
- `COMPLETE` 必须检查双通道 IOC/Idle、无错误、长度及帧边界；`UNKNOWN` 不能依据 DMA reset done 或 PL reset 变为 `IDLE`。需要可观察的 HP0 AR/R/AW/W/B 排空证明，或独立板级验证过的整 PS/HP 恢复规程。
- 拒绝在 `IN_FLIGHT/UNKNOWN` 状态卸载或释放；重启后恢复条件、单会话互斥、缓存一致性、最小权限及故障注入测试都需明确验收。内核模块是否采用 `dma_alloc_coherent`、`dma_mmap_coherent`，应在匹配当前 5.4 内核源码/设备 DMA mask 后决定；参考 [Linux DMA API](https://docs.kernel.org/core-api/dma-api.html)。

## 尚需的授权和实证

隔离第一方内核候选的编写与离线测试已获授权并完成。离线编译和测试不等于可加载。安装/加载模块、停服务、重启、烧写或在实体 DDR 进行故障注入分别需要明确授权和恢复计划。在此之前保持正式 ARM 路径，PL DMA 候选不准上板。没有物理页跨进程保持与 HP0 排空证据，就不能宣称两项问题已解决。
