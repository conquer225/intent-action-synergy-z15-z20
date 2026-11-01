# HDMI 回报背压修复（2026-10-13）

用户要求尽快处理回报拥堵，并评估 PL 方案；正式四频测试前必须实测，不把软件回归当作识别结果。固定八通道、模型、门限、SD 启动配置不改，实体轮椅禁用、静音；15 秒退出继续关闭。

## 改动与验证边界

只修改 `phone_video_upload/hdmi_stimulus.py`：原队列仍最多两批、扫描仍每四条形成一批；发送线程可把已排队的相邻两批合并成最多八条，保持全部 ACK 的时间戳和顺序。短时队列满时扫描线程暂存未发送记录（最多八条），不阻塞原生扫描；超过这个界限仍停止。原有 `.35` 秒生产者时效、`.3` 秒响应时效、连续扫描计数／间隔校验、强制停止均不放宽。不是清理历史脑电，也不是无限扩大队列。

最初只合并、没有短暂背压处理的版本在持续 131ms 请求模拟下仍偶发满队列，未上线；其测试失败保留。加入有界待发送记录后，本地相关 24 项通过，131ms 慢回报用例重复八次全部通过。板端 23 项针对性测试通过：线程停止、顺序保留、有界满队列停止、扫描证据及安装回滚。完整合成解码检查因缺依赖／测试素材失败，补齐后耗时较长被主动停止，不计为通过；模型、解码代码未修改。

## 部署

复用已有 `install_video_path.py` 的备份、校验、恢复原 PL、保护正式服务及哈希的事务。本次私有调用将精确文件集合设为 `('hdmi_stimulus.py',)`，额外更新其 `boot-pins.json`；不替换采集／控制接口，不重启 ARM 服务。私有目录 `/home/xilinx/gl-video-path-20261009-rJOfB4`，校验备份在其 `active-backup/`。

源码候选 SHA256 `08fc4f6ec35120ccb61191171242ef913d2db70717331e8a5dfcbae077673fab`；原板端文件 SHA256 `b45981d0672e0975dd5f5a20ba60f62c0287a7ddf36a6fbfdade3527610b81fb`。保护的 61 个文件、正式运行服务身份在安装时均未变化。当前同次校准 SHA256 `14f30964edeb5ae8a1fc66bab104ff077116e79fc96f3a18bdbd3810865dfcb3`。

实际固定亮度测试通过现有媒体 Controller 启动，不把诊断开关写入正式 media_state；扫描接口仍核验全部真实 ACK。复测如果未完成 20 秒或出现回报错误，就在释放显示缓冲／恢复原 PL 后回滚文件，再启动正常静态主页。试验与恢复由独立板端 unit 执行，避免控制电脑中断把显示留在诊断模式。

## PL 可行性

把刺激相位、缓冲切换和锁存事件记录放进 PL，可减少 Linux 调度影响，仍需 ARM 负责脑电识别和页面控制。但目前显示版 `eye_wifi.bit` 缺对应可重建 Vivado 工程；已有其他加速／示例工程不能当作显示版源码。统一显示／加速 PL 仍在主线，不在本轮猜引脚或 AXI 地址、不做综合／烧录新 bit。当前短诊断显示过正常约 60.6Hz 扫描，却因 ARM 回报路径停止，先解决已确认的软件拥堵。

证据：`phone_video_upload/output/hdmi_backpressure_repair_20261013/`。本文件初稿时软件已安装、固定亮度复测尚在进行，**尚未宣布现场修复通过**。

## 实测追加：合并／有界背压仍未解决

首轮诊断显示初始化超过私有脚本 20 秒等待期限，尚未进入扫描；自动回滚并恢复正常主页。启动日志无显示错误，原生 preflight 合格，因此私有诊断等待延长至 60 秒（不改正式启动配置或 EEG 门限）后补测。

补测会话 `f05fca1d3f69a9d2a827b052c8dcbaf2` 仍很快因 `HDMI report queue full` 停止；4 次回报最长 280.30ms，最旧 ACK 排队年龄最大 95.69ms；原生线程累计 31 次扫描，最大周期 CPU 6.33ms，controlled_stop。这个结果说明合并／短暂有界待发送不足以保证持续回报，不能通过加大队列掩盖。原软件已回滚，静态显示 `play-5189e946` 恢复 home，ARM PID 15708、校准 SHA256 未变。补测结果 `completed=false`，即使恢复 unit success 也不解释为修复通过。

隔离 HTTP 对照：静态正式接口 12 次 GET 中位 10.75ms、最大 26.21ms；独立同代码接口中位约 23.26ms、最大 41.75ms；启用 TCP_NODELAY 的独立接口中位 21.24ms、最大 45.65ms。独立静态 GET 不能替代扫描期间 POST，但未显示关掉 Nagle 是本轮问题的解法；这项配置未上线。

下一候选在同一回报代码中仅将普通扫描控制／回报线程从 Nice=0 调到 -5，视频渲染仍为 Nice=5，不把 Python 改为实时线程。板端 23 项针对性测试通过；直接运行候选线程助手，检查实际 nice=-5、policy=0（普通调度）。新候选 SHA256 `f5090131da68d22732b558c824e7b9ef26d3aed7095d4a932b743e5d61a7cb3c`，私有备份目录 `/home/xilinx/gl-video-path-20261009-eu9T3h/active-backup`。当前正在固定亮度验证，失败仍回滚，不能提前宣布通过。

## 用户中断时的最终复核

优先级候选首轮在 hdmi_start 时被控制接口 409 拒绝，没有扫描，已回滚。私有诊断此前仅等后端 input ready；补充等待媒体预检和后端同时 ready、保留详细拒绝原因后再次固定亮度测试。该补测确实启动，但仍因 `HDMI report queue full` 失败：8 次回报最长 237.38ms，最大队列 ACK 年龄 242.95ms；原生累计 69 次扫描，controlled_stop，最大周期 CPU 6.38ms。优先级对照没有解决持续回报拥堵，不能上线为已验证修复。

用户主动中断后只做恢复复核，不继续修改或刺激：板端诊断 unit 已 inactive，候选文件及 pin 已回滚到原 SHA256；正常静态显示 `play-68f03251` 在 home，非固定亮度模式，刺激／录制准备均关闭，实体输出禁用，15 秒退出关闭；ARM PID 15708 仍 active，校准仍为原 15/15 的 SHA256。两次失败候选均未留在运行版，本地代码保留作未通过候选。复核证据位于 `priority/attempt2/interruption-audit.json` 与 `interruption-display.json`。

本轮利用既有安装／回滚完成有界改动，没有增加生产通信框架或新依赖；回报拥堵仍未解决。下一次继续时应优先拆解扫描同场期间 HTTP 处理、锁等待和 CPU/GIL 调度，而不是继续扩大队列、降 EEG 门限或把未建成的 PL 方案当作现成可部署修复。

## 后续隔离验证：连接复用与 SD 写盘长尾

本次只在本地和 Z15 私有目录验证 `ssvep_cue_runtime.py`，未部署正式文件，未重启正式采集／显示，未加载 PL，未启动闪烁或实体输出。候选 SHA256 为 `dd83e7bd3dbfc6522f124c958722ac819c7272a3cc586faaebecc53c803c3797`；运行版仍为 `f3c16dfb3335e650d6c72a16b979b654c76dffc6a8e0bdeb29326c14816f4e56`。

候选让有限 HDMI 生产者的 presented／heartbeat 请求复用一个 HTTP/1.1 连接；其他请求继续走原路径。停止、错误响应、来源身份不符时关闭连接，不自动重发扫描证据。服务关闭后也拒绝已有连接的新请求；未读取请求体就拒绝的分支关闭连接，避免遗留请求体被当作下一条请求。没有修改解码、模型、窗口、质量或时效门限，也没有把前两轮未通过的 `hdmi_stimulus.py` 候选混入部署。

本地相关 46 项通过，其中新增 4 项检查连接复用、停止关闭、错误不重发及关闭／身份拒绝。Z15 首轮旧测试桩没有实际替换已绑定路由，导致一项断言失败，修正测试桩后重测，不将该轮计为通过。

板端 SD 临时目录回归仍出现真实超时：Nice=10 的 91 项有一项超时，Nice=0 的 91 项有两项超时，均保留失败记录。保持 Nice=0、原 `.8` 秒请求超时不变，只将**隔离测试临时文件**放到 `/dev/shm` 后，91 项全部通过，耗时 69.853 秒。这只验证软件行为，不证明生产 SD 日志路径或真实扫描已通过。

四轮交错的 loopback 合成回报对照（旧、新、新、旧，每轮 80 次 heartbeat、每批 4 条）没有访问 PL，也没有接入真实脑电：旧版每轮 presented＋heartbeat 新建 81 个连接，中位 15.93／18.82ms、p95 35.84／45.97ms；候选各复用 1 个连接，中位 9.65／9.68ms、p95 18.27／16.69ms，最长 29.06／23.82ms。四轮均接收 320 条**合成**扫描记录并停止。这一组关闭日志，仅用于传输成本，不能冒充实际硬件扫描或识别验收。

进一步用既有 3 项测试分别对照 SD／tmpfs，并只计时原 `_log`，未改日志实现。旧版在 SD 上一次 `trial_start` 日志调用耗时 **854.73ms**，超过 `.8` 秒请求期限，同一测试确实超时；候选该次 SD 对照及新旧 tmpfs 对照通过。`/tmp` 实际位于 `/dev/mmcblk0p2` 的 ext4，`/dev/shm` 为 tmpfs；`CuedSSVEPSession._log(durable=True)` 原代码包含同步 `fsync`。因此确认至少一类启动超时与同步 SD 日志阻塞有关，不能把所有失败都归于 HTTP 新建连接或 CPU 调度，也不能把这项 cued 日志测量当作 HDMI 回报拥堵的唯一根因。需另测启用 SD 日志的连续 HDMI 合成回报，再决定是否进入真实固定亮度验证。

正式状态复核：ARM PID 13555 active、NRestarts=0，校准仍 15/15、SHA256 `14f30964edeb5ae8a1fc66bab104ff077116e79fc96f3a18bdbd3810865dfcb3`；静态 home、刺激关闭、实体输出禁用。新记录在 `phone_video_upload/output/ssvep_contention_repair_20261013/`，私有运行目录 `/home/xilinx/gl-calibration-install-20261011-snX4Cb`。候选未上线，真实扫描持续性仍待验证。

Guard 复核：生产改动沿用现有 Bridge 与标准库 HTTPConnection，无新依赖或通用通信框架；两个额外诊断脚本仅位于 output 私有试验目录，不进入运行包。

补测开启原 HDMI SD 日志后，同样交错四轮全部正常停止，无回报失败。旧版中位 22.29／17.82ms、p95 46.94／51.36ms、最长 56.78／59.23ms；候选中位 9.66／9.75ms、p95 25.41／21.33ms、最长 27.00／31.18ms，连接数仍为每轮 81 对 1。仍是私有 loopback 合成回报，不包含原生扫描抢占和真实脑电解码负荷，不能据此宣布实际 HDMI 持续性通过。

已生成仅含 7 个精确目标的可恢复私有安装计划，尚未执行 install：正式／显示候选目录中的 `ssvep_cue_runtime.py` 两份，以及 manifest、共存 guard、启动状态、wrapper state 和 boot pins。计划不含 Cyton 配置代码或之前失败的显示队列候选。后续安装、ARM／网页／HDMI 重启与已有 bit 恢复／重载，须再次获得明确授权。

最终检查仍为原 PID 13555、15/15、静态 home、实体输出禁用，正式 runtime 哈希未改变；输入快照年龄约 106.7ms，遥测文件年龄约 0.12 秒。另有累计 sequence_gaps=2195、malformed_bytes=80176、primary_stream_resets=127，最近中断原因为 MALFORMED_STREAM。这些是上游链路的累计证据，不是本轮 HTTP 回报结果；不能声称收包错误已解决，下一轮真实测试仍需核查增量和 O1/O2 的有效性。最终状态在 `completion-audit.json`，SD 回报对照在 `sd-transport-result.json`。

## 授权现场验证：连接复用仍失败，已完整回滚

用户随后允许备份安装候选、短暂重启 ARM／网页／HDMI、恢复正式 PL 后重载已有显示 PL，做 20 秒不闪烁诊断。安装前发现旧安装器的 input 模式要求整套输入文件，与本次仅 7 个精确目标不符；为已有安装器增加 `report_connection_update` 的精确集合，不放宽原目标校验。新增测试验证缺文件、外来文件、混用模式及绕过校准保留均拒绝。本地安装器 14 项通过（Windows 一项 Linux 权限测试跳过），板端安装器测试命令退出 0；该安装器仅上传至私有 stage，不替换正式采集代码。独立回滚计时器与 ExecStopPost 恢复沿用现有事务。

本次 unit `gl-report-connection-live-8d5b7c`，诊断显示 `play-f56a45fa`，真实后端会话 `7bde624120618413464246d1a9c0d6c4`。启动和 presented 成功，实际锁存回报形成 60 条扫描证据，扫描率约 60.603Hz、已回报区间最大 ACK 间隔 16.739ms；原生线程最终累计 74 次扫描、最大单周期 CPU 6.217ms、controlled_stop。尚未达到 2 秒完整显示证据，因此瞬时各频率统计不解释为合格频率。

连接复用仍出现 `HDMI report queue full`，随后后端 `hdmi_report_expired`：16 次回报最长 **208.933ms**，最大队列 ACK 年龄 **131.458ms**；O1/O2 input ready 从 true 变为 false。`completed=false`、`continuous_input_ok=false`，没有完成 20 秒，没有测试识别准确率或启动可见闪烁。不能将此次结果称为修复成功；新建 TCP 连接不是全部瓶颈，尚需分离同场线程调度、锁等待、解码和同步日志处理。

失败后软件自动回滚，回滚记录 `phase=rolled_back`。首个普通显示恢复等待超过 60 秒；unit 的 ExecStopPost 再次走恢复流程，最终恢复正常显示 `play-7e4cb421`。unit 的 Result=exit-code 正确保留失败，不因恢复成功改称测试通过。最终校验：正式 runtime 回到 `f3c16dfb3335e650d6c72a16b979b654c76dffc6a8e0bdeb29326c14816f4e56`，显示脚本仍原 `b45981d0672e0975dd5f5a20ba60f62c0287a7ddf36a6fbfdade3527610b81fb`，Cyton 源码仍 `5d8861ee8264259189cad3826dad806fca9ff155d1df3b3917a96b00827bdc50`，boot pins 全匹配，独立回滚 timer inactive。

继续任务后的最终复核：ARM PID 1814、网页 PID 1820、媒体网页 PID 2782、静态显示 PID 2780 均 active。PL 为已有 `eye_wifi.bit`，home、固定亮度诊断关闭、刺激关闭、音频和实体输出均禁用；校准 15/15 且原 SHA256 未变。9102 /api/status 可访问、stale=false；9105 为 idle，输入 `page_task_suspended` 是主页按需调度状态，不是新一轮校准或计算耗时。当前没有重新开始 10Hz 刺激。

本次所有现场记录在同一 evidence 目录：`authorized-before.json`、`live-fixed-brightness-result.json`、`installation.json`、`live-completion.json`、`live-final-audit.json`。下一轮不得复用已失败 stage 的安装状态；原备份保留，候选未留在生产文件中。

恢复后的进一步读数：遥测文件年龄 0.170 秒、输入快照年龄 16.33ms、读包队列年龄 13.71ms，说明该次读取已有新包；校准仍 15/15。与此同时，当前 ARM 启动周期累计 sequence_gaps=510、malformed_bytes=17948、primary_stream_resets=37，最近原因为 STREAM_TIMING_GAP，上游错误仍存在。前一对 4 秒间隔的 status 计数相同不足以单独证明整段没有收包，不能混淆状态发布周期和真实采样新鲜度。复核在 `post-rollback-runtime.json`；恢复完成不等于采集链路或 SSVEP 已验收。
