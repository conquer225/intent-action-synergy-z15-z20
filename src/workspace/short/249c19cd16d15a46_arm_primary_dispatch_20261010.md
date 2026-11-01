# ARM 主窗口后台交接候选（2026-10-10）

## 范围

承接 `HDMI_BGR_INSTALL_20261010.md`。只更改本地及新的板端私有目录
`/home/xilinx/gl-prewear-dispatch-20261010-yR15QX`，不关闭常开 HDMI，
不重启正式采集或网页，不更换 PL、模型、SD 启动配置或正式调度策略。
以太网 192.168.2.99，板卡自己的热点不变。全程静音、无闪烁、轮椅禁用，
不需要佩戴。新的候选没有部署到正式采集。

## 确认的输入错位

上一轮显示更新后的隔离回放有一次 PRIMARY_WORKER_HANDOFF_BUSY。
原队列容量有空位，但父进程 try-acquire feeder 互斥锁失败，拒绝数据批次；
主循环按真实丢批撤销结果、更新 epoch、重新预热滤波及窗口。
已经接受的校准基线不被清空，但计算窗口边界改变，导致与第 13 轮参考
严格 window + packets_seen 对齐时只有 2 个非预测窗口可比较。
不能把它解释为模型准确率降低，也不能说已完整核验预测一致性。

另外一次 PRIMARY_WORKER_BACKLOG 只撤销过期预测，不丢连续输入，不清空
校准／滤波历史；它与交接拒绝导致的连续性重建是不同路径。

## 私有候选

保留标准 CPython multiprocessing Queue 的消费、序列化、管道、feeder、
跨进程容量 semaphore。父进程和新 dispatcher 线程间用 CPython deque
交接已有独占数组，只在父进程做容量非等待预留和 append。
dispatcher 最多每 2 ms 检查一次输入，在后台等 feeder 锁，再交给标准
feeder 序列化；不再因该短暂锁竞争拒绝已接收的批次。

容量仍为 32 批，预留涵盖 deque、后台交接中、标准 buffer 及管道内所有
未消费数据，原消费者 get 时释放一次。没有扩大容量或复制成无界缓存。
真正满时仍报 PRIMARY_WORKER_QUEUE_FULL，继续原连续性失效／旧结果撤销。
旧 epoch、输入时间、数组所有权、500 ms 门槛、数学及校准保留不改。
dispatcher 出错或关闭超时会抛错误，不作为成功提交继续运行。

这是已核验 CPython fork 下的单生产者／单 dispatcher 私有实现，不能未经
验证推广到其他解释器或启动方式。handoff_busy 统计字段保留兼容旧日志，
本候选不产生该拒绝；它不代表真正队列满或计算积压已被解决。

原 `async_primary.py`、对应测试及微基准留在本地输出目录 reference/ 和
板端 reference/。本地只改上述队列实现、相关测试和控制竞争基准；主循环、
数学核心、模型权重未改。详细提交 tracer 恢复为第一次 offer 必须成功，
不再使用前三次新 offer 重试的合成测试办法。

## 已完成检查

- Windows 本地原相关 22 项：10 通过、12 项 Linux/fork 用例跳过。
  没有把平台跳过项当作板端通过。
- 初次板端把整套主循环检查也放入 120 秒、Nice=10 的有限任务，运行到
  时限被系统停止；记录 Result=timeout / failed，不算通过，也不清除日志。
- 改用明确相关的 33 项、Nice=0、180 秒限时检查，实际 49.720 秒结束：
  32 通过、1 项未配置旧提取源的全主循环对照跳过。包括 36,000 样本校准后
  同步／异步逐项数值一致性、32 批锁竞争 FIFO／容量恢复、旧 epoch、
  数组所有权、队列满撤销、过期结果、主计算滞后不重建输入、MI tap 和
  遥测边界检查。
- 两对受控 feeder 锁竞争约 250 ms：标准 put_nowait 等待 250.934 /
  250.301 ms；新候选立即接收 0.052 / 0.055 ms。两种方法最终均完整收到
  同一 payload、容量恢复；没有把后台真实等待冒称已消失。

## 视频只读观察

现有常开 `play-df4fc516` 不结束，不获取仅退出时才产生的最终阶段报告。
新增可选的只读 `/proc/<pid>/task/<pid>/stat` 和 status 主线程 CPU tick／
主动与非主动切换计数，与原帧进展记录并存。不对显示进程挂调试器或改调度。
该内核没有 `/proc/900/sched`，不能据此声称获得了 runqueue 等待时间。

解析器 2 项本地、2 项板端均通过。最初 Windows 测试缺少 os.sysconf，
仅在测试 mock 中显式创建它后通过；生产实现没有加入猜测时钟或 fallback。
读取不存在的 PID 会报错，不用 0 CPU 冒充测量值。

使用同一 156 秒记录和上轮参数，完整无探针回放及 205 秒只读显示观察
在独立有限单元运行，记录不重复、输出不覆盖历史。仍包含 MI 空闲 lane、
遥测和 SEED 状态审计；页面策略仍是 video，按原规则暂停页面不需要的候选。
这不是所有候选同时满载或新的真人输入测试。

## 证据位置

`phone_video_upload/output/primary_dispatch_20261010/` 保存初次 timeout、
最终板端检查日志、受控竞争结果、原实现备份、前后审计及录制回放结果。

## 完整回放结果

156 秒记录消费 39,000 / 39,000 包，记录不重复，包含原有一次 SEQUENCE_GAP。
含初始化、收尾的墙钟时间为 191.374 秒，回放错误列表为空、剩余子进程为空。
测试、回放、观察三个有限单元最终均 success / inactive / MainPID=0；首次
120 秒检查仍为 timeout / failed / MainPID=0，不混入成功统计。

- 新 dispatcher 接受 3,884 批，handoff_busy=0、queue_full=0；本轮没有因为
  feeder 锁竞争拒收批次。仍有一次 PRIMARY_WORKER_BACKLOG，过期结果照常
  撤销；不能宣称整个计算积压问题已解决。
- 主计算流状态重建一次，原因是原记录的 SEQUENCE_GAP。worker epochs=2
  还包括最终 EOF 撤销，不是发生了两次重新校准。
- 主结果 35 条：INVALID 8、CALIBRATING 18、NORMAL 9，情绪预测 13 条。
  完成校准后，calibration_current=15 和 calibration_retained=true 一直保持。
  EOF 时情绪／疲劳、SEED、SSVEP 的最终状态均无效，旧结果已撤销。
- 与第 13 轮同步软件参考按 window + packets_seen 严格对齐，共同窗口 33 个，
  状态、校准、疲劳分数／平滑值及情绪完整结果零差异。两边均有 34 个索引键；
  参考单独剩 (25,35173)，候选单独剩 (24,35273)，未把它们强行配对。
  这验证所比较窗口的计算一致性，不证明佩戴识别准确率。
- 输入年龄 p95 54.596 ms、最大 471.447 ms，仍小于现有 500 ms 门槛。
  相比上轮 p95 32.247 ms、最大 389.723 ms，本轮延迟变差且更靠近门槛。
  主进程 CPU 56.414 秒、子进程 CPU 78.525 秒，总计 134.939 秒，也高于上轮
  127.150 秒。不能把消除交接拒收描述为整机算力或延迟全面改善。
- 单包计算 p95 5.004 ms、p99 13.956 ms、最大 421.884 ms。

`profile23/acceptance-details.json` 保存 worker 统计、最终撤销状态和指纹证据；
`profile23/verification-summary.json` 保存严格对齐、未配对窗口与显示统计。
这里只运行 video 页策略、MI 空闲 lane、遥测和 SEED 状态审计，页面不需要的
候选按原规则暂停；不是四种候选同时满负荷，也未把回放预测注入正式网页。

## 视频仍未达到稳定 16 帧

205 秒只读观察产生 178 个可计算发布区间，软件发布进度平均 19.481 fps，
最低 14.238 fps，有 4 个区间低于 16 fps；buffering 观察为 0，最大发布年龄
0.828 秒。会话始终同一播放器、video 页、无闪烁、实体输出禁用。

上轮平均 19.534 fps、最低 11.827 fps、低帧区间 2 个。本轮最低值虽提高，
平均略降、低帧区间增多，不能单凭一次运行宣称视频性能改善。
published_intervals_16fps_met=false，网页 multitask_16fps_qualified 仍为 false。
这些是软件新视频帧的发布统计，不是逐扫描或屏幕发光实测。

新增只读主线程 CPU／切换观察：正常区间的 CPU 中位数约 15.94%，4 个低帧
区间约 11.79%～15.51%，非主动切换数没有一致升高。CPU 差分以观察时刻为边界，
帧率以发布时刻为边界，二者并非完全同窗；未测到 runqueue 延迟，不能据此
把全部卡顿归因于 Linux 抢占或主线程的 Nice=5。
`display-process-correlation.json` 明确保留上述限制。

## 最终保护审计与下一步边界

正式 53 文件无改变，boot_id 仍为 8f136697-cbea-4b20-a74f-c899978d7f3a。
采集 PID 7988、网页 PID 7994、显示 PID 900 保持 active、NRestarts=0；
采集／网页 Nice=0，显示 Nice=5，实际 CPU affinity 均为 [0,1]。
安装器 protected_unchanged=true、pin_mismatches=[]，四个显示文件指纹不变。
实际 PL 仍为已有 eye_wifi.bit，本轮没有重新加载它，也没有停止常开 HDMI。
会话 user_controlled=true、seconds=null、silent=true、audio_output=false、
direction=stop、stimulus=false、physical=false。

四个新候选源码指纹、七个模型／记录指纹及 primary_window、covariance、
fatigue、SQI 数学核心均在回放前后核对一致。`formal-audit.json`、
`after-display-audit.json`、`after-session.json`、`final-services.txt`、
`source-after.json`、`math-proof.json` 和 `profile23/model-input-proof.json` 为证据。

下一步可做范围明确、可回退的显示调度对照，区分调度竞争与其他等待；
不能未经确认改正在运行的显示策略或承诺它必然提升帧率。异步主窗口候选
仍需补齐真实服务的佩戴校准存档／恢复和重启边界验证，才考虑正式更新。
本轮没有部署该候选，没有降低质量、输入时效或过期撤销门槛，也没有完成
真实无线连续输入、实体轮椅或 SSVEP 识别验收。

后续已完成 Nice=5/0 显示调度对照，见 HDMI_DISPLAY_SCHEDULE_20261010.md。
Nice=0 改善本次视频发布低帧，但主 worker 过期回复增加，因此未正式采用，
已恢复 Nice=5，仍需任务／CPU 分工及真实校准存档恢复验证。

后续 CPU 分工对照见 HDMI_CPU_DIVISION_20261010.md，未采用全部脑电固定
CPU0 的方案。后台校准存档及不同私有服务进程的恢复边界已补测，见
ARM_PRIMARY_RECOVERY_20261010.md；仍未部署异步主窗口到正式采集。
