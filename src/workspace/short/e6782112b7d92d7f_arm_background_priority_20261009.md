# 隔离后台优先级对照（2026-10-09）

## 结论与去留

第 15 组 156 秒记录回放正常结束，但整体实时验收仍失败。
不将 background-nice=10 上线，不冻结 ARM 候选，也没有改正式采集或显示的调度参数。
只降低后台工作进程优先级不足以解决主处理长尾；不能据此要求用户重新佩戴、
放宽 500 ms 新鲜度门限，或把已经撤销的结果恢复为有效。

同一新版显示、同一 20 fps 视频、同一记录与第 14 组相比：

- 视频发布进度平均 19.221 → 19.439 fps，最低区间 9.841 → 13.516 fps；
  低于 16 fps 的区间 10 → 8，本组未采到 buffering，仍不满足严格目标。
- 输入年龄 p95 204.837 → 184.110 ms，但最大 625.519 → 952.671 ms。
  两组均有 1 次 PROCESSING_BACKLOG 撤销。
- 本组最长单包处理墙钟 700.181 ms；监测中的最长滤波调用墙钟 658.875 ms。
  这些是墙钟停顿，尚不能区分计算耗时、调度等待、内存或其他内核等待。

这是两次单次对照，不是统计显著性结论或长期性能保证。视频统计依据发布帧计数
自己的时间戳，不是光学或逐扫描锁存测量；没有宣称屏幕稳定达到每秒 16 个新帧。

## 变更边界

私有阶段 `/home/xilinx/gl-prewear-compute-20261009-LcGhCQ`，新输出为
`load-hardened-scheduled15`。原 39,000×8 记录不重复、ARM 滤波、真实管道读包，
未打开 USB、未注入到正式监测入口，也没有加载或恢复 PL。

唯一性能变量是私有 MI／遥测／SSVEP 工作进程的普通 nice 从 0 改为 10。
角色分核沿用第 14 组：主处理、读包、输入生产器在 CPU 0，三类后台消费者在 CPU 1。
主处理 nice 保持 0；异步 SEED 的进程未改优先级。
视频页仍暂停 SEED／SSVEP 候选计算；MI 收包、滤波、预热，无主动 MI 试次。
本轮不是全部任务主动识别、真实无线采集、真实佩戴或识别准确率验收。

回放工具新增显式 `--background-nice`，仅允许 0 或 10，默认 0 不调用 setpriority。
非零值要求不带耗时探针的 ARM 角色分核回放；私有驱动还要求 idle-mi 模式。
工作进程入口用 setpriority 设置绝对值，避免重复累加；不是实时调度。
通过保存原 telemetry fork 目标防止包装函数递归，异常不被吞掉。
监测新增 `/proc` 的实际 nice 值；启动导入阶段的 MI／SSVEP 仍先为 CPU 0、nice 0，
进入工作函数才切到 CPU 1、nice 10，不将启动阶段说成已降优先级。

修改前保留四个私有诊断文件的校验备份于 `before-priority15`。
第 14 组 153 个运行文件开始时完全相同；上传后仅回放 harness 与测试文件有变化。
本组开始／结束核验完整运行目录 166 个文件，无变化，模型和算法文件未改。
本地源码变更仅涉及隔离回放、启动／观察编号和其调度测试；不是正式算法更新。

## 输入、模型与校准

39,000/39,000 包被主循环取出，生产器持续 156.001 秒，最大调度迟到 15.831 ms，
超过 100 ms 的批次为 0；这不代表全部包进入特征计算，积压保护丢弃了 219 个过期包。
主回放墙钟 187.822 秒包含初始化和收尾，主 CPU 71.212 秒、子 CPU 累计 85.124 秒。
监测错误 0、未捕获运行异常、结束剩余子进程 0。

积压发生于 window=3、packets_seen=7733，基线当时仅 3/15，尚未完成。
该撤销保留已有积累，之后校准达到 15/15，所有后续输出直至结束均保留完成状态。
所以本组证明后续完成和收尾保持；不能单独声称本组又验证了“完成后遭积压”的路径，
后者在第 14 组已有证据。

本组 13 个情绪 prediction、10 个疲劳 NORMAL；这是负载／接受路径覆盖数量，不是准确率。
与第 13 组按 `(window, packets_seen)` 对齐仅有 4 组首发输出，字段逐项相同，
但这些不是完整正常预测对照。积压与过期丢弃导致后续窗口移位，参考独有 30 组、
本组独有 27 组均保留清单，不能宣称全程模型逐窗一致。

结束直接读私有状态：主状态 invalid、SERVICE_STOPPED_OR_STREAM_TIMEOUT，情绪 valid=false，
SEED／SSVEP 均 no_data；校准 15/15、retained=true。旧预测没有继续保持为有效。

## 测试、保护与证据

Z15 Linux 调度回归 11 项通过，包含真实 fork：子进程 nice=10、父进程 nice／亲和性
不变、继承包装不会递归、默认不改优先级、非法值在任何调度修改前拒绝、MI／SSVEP
参数原样传递。Windows 同一组明确跳过，不把跳过计为通过。
本地发布帧统计及证据汇总回归 9 项通过，五个修改文件 py_compile 通过。

正式 53 文件校验相同，boot_id 未变；显示文件、启动校验清单均无不匹配。
正式采集 PID 7988、网页 PID 7994、显示 PID 19790，全程 active、NRestarts=0。
前后采集／网页 nice=0、显示 nice=5，三者 CPU 亲和性均为 [0,1]，未改。
三项有限诊断服务均 inactive、MainPID=0、Result=success、ExecMainStatus=0。
常开 `play-93498f59` 仍在同一视频页播放相同视频，user_controlled=true，
静音、无闪烁、实体输出 false；未发停止／播放重启／PL 切换命令。

证据在 `phone_video_upload/output/compute_relief_20261009/profile15/`：
`baseline-backup.json`、`before-runtime.json`、`before-display.json`、`linux-priority-tests.log`、
`report.json`、`producer.json`、`primary_results.json`、`monitor.jsonl`、`offline-replay.log`、
`verification-summary.json`、`scheduler-proof.json`、`final-private-status.json`、`protected-after.json`。
父目录保留 `display-observations-actual15.json`、`display-frame-progress15.json`。
下一步应低开销区分主循环长尾中的 CPU 计算与等待，再修对应阻塞点；
本轮未自动开始新对照，也未让用户以佩戴测试代替软件问题定位。

后续已完成[主循环长停顿定位](ARM_PRIMARY_STALL_LOCALIZATION_20261009.md)：
最长 736 ms 的同步窗口路径中约 260 ms 是线程计算，约 476 ms 为非 CPU 时间，
质量评估是这次最大已测子阶段。下一实现步转向隔离窗口评估／预测，而不是继续只调优先级。
