# ARM 输入修复上线与未通过的实时验收（2026-10-11）

## 范围和当前结果

用户明确授权备份、更新 ARM 采集及网页，并短暂停止后恢复 HDMI。
通过以太网 192.168.2.99 操作，没有切换手机热点、改模型或 SD 启动镜像。
静音、无闪烁、无实体轮椅输出。HDMI 保持用户控制，不设置自动到期。

软件更新已提交，发布为 `guardianloop-fixed8-input-repair-20261011`。
发布清单 SHA256：
`189ef68f693d4add0757d7ed8e315b3bf5cdd98aa44e6f1ad191a6e115fd040e`。
板端运行目录：`/home/xilinx/jupyter_notebooks/guardianloop_pynq`。
完整的实时验收尚未通过：后台主监测仍间歇出现
`PRIMARY_WORKER_BACKLOG`，SSVEP 仍出现暂停和一次队列缺口。
不能将这轮交付描述为延迟问题已经全部解决或可直接控制轮椅。

## 已确认原因和改动

1. 页面曾显示的 412212 ms 是 `page_task_suspended` 旧事件的年龄，
   不是一次算法执行耗时。暂停时改为明确显示暂停、年龄为空、结果撤销。
   网页增加主动“准备脑电输入”入口，独立于启动录制与闪烁；心跳每秒更新，
   三秒失效，隐藏或离开页面释放。读取状态不会自动激活输入。
2. SQI 自适应距离原来将工频能量显著降低也视为异常。只把工频指标的
   自适应距离改为上尾检查；保留高工频、幅度、断线、削顶等其余检查，
   不重建佩戴基线、不整体降低质量门槛。
3. MI/SSVEP reader tap 改为最多十包一次 IPC；每次串口 read 后立即
   刷新不足十包的批次。保留每包时间戳、序号、ordinal、坏包标记和
   500 ms 时效检查；有界队列没有扩容，丢失仍导致结果撤销。

复用现有安装器、原子 JSON、reader sink 和页面调度，不额外加入另一套
生产运行框架。显示准入、发布清单、live wrapper 与 boot-pins 同步更新。

## 精确部署与校准保存

正式更新十个代码/网页文件及发布清单，另更新五份准入或元数据文件，
共十六个严格锁定的目标；安装计划逐文件记录前后 SHA256。

本地 `mi_acquisition.py` 原先含未上线的 `return_snapshot=False` 优化，
与板端正式 `mi_cued.py` 不兼容，因此没有直接覆盖整份本地候选。
本轮实际部署的 MI 源码是
`phone_video_upload/output/input_repair_20261011/candidate/mi_acquisition.py`，
只纳入与当前正式版兼容的小批传递改动。今后不能用本地实验文件盲目覆盖。

旧 HDMI 会话正常退出，确认 `original_restored=true`、
`buffers_released=true` 且 errors 为空后安装；退出过程恢复
`guardianloop_pynq.bit`。更新后启动 `play-40bda203.service`，重新加载
已有 `/home/xilinx/tobii_z15/overlay/eye_wifi.bit`，再返回 home。

安装复用独立 150 秒回退计时器；核对服务及同次佩戴校准后提交并停止
回退计时器，随后恢复 HDMI。没有运行板卡复位、烧写或 Vivado 构建。

同一次开机的 calibration-session、wear-session 文件更新前后 SHA256
完全相同。疲劳基线保持 15 个窗口，八通道 SQI 各 60 个参考片段。
断流仍撤销旧预测；本结论不代表重新上电、更换佩戴或模型后沿用旧校准。

## 检查及失败记录

- 本地相关软件组 47 项通过；另组 17 项中 6 项因 Windows 条件跳过，
  跳过项不计通过。虚拟 DOM 浏览器整合检查通过，不产生真实闪烁。
- 板端 Python 3.8 正常优先级检查 64 项全部通过，86.728 秒，
  systemd success / inactive / status=0。日志内故意触发的审计 I/O
  失败和回退提示属于负向测试，不是正式程序故障。
- 早期隔离检查拦截了未推广 MI API、缺依赖及 Python 3.8 测试代码
  不兼容。修正后重跑，没有将这些失败候选写入正式目录。
- 同一测试组低优先级 Nice=10 时，64 项有一项真实 reader 压力检查
  失败，出现队列缺口；该轮不算通过。正常优先级重测才得到上述通过。
- 初次现场诊断脚本误把 fatigue.signal_quality 字符串当成详细 SQI，
  自身报错退出。修正为读取 telemetry.sqi/runtime 后重测；失败轮
  不算实时验收通过，没有因此重启正式采集或清除校准。

## 不闪烁真实输入观察

修正诊断脚本后的约 29 秒会话：24 次状态采样，无诊断请求错误。

- 校准文件完全不变，始终 15/15；CH2/F4 24 次均 usable，非降权。
- SSVEP 状态：ready 9 次、warmup 7 次、suspended 8 次。
  出现一次 `ssvep_reader_queue_gap`。这些计数不是识别准确率。
- 有数值的输入年龄样本最大/p95 均为 452.2 ms；包含 warmup，
  是离散状态采样，不是逐包耗时或显示端到端时延。
- reader 队列等待的本次进程累计峰值为 390.160 ms，流复位计数
  观察前后均为 0，过期包丢弃为 0；不能据此认定所有计算路径达标。
- 主监测返回正常预测的状态采样 9 次，
  `PRIMARY_WORKER_BACKLOG` 15 次。该原因来自后台处理进度年龄
  超过 500 ms，而非 reader 队列本身或校准丢失。
- 释放输入准备后，SSVEP 回到 suspended / ready=false /
  age_seconds=null。全程会话 idle、accepted=false，未启动录制或闪烁。

只读十秒调度观察中，home 页面 lease 年龄最大约 1.001 秒；
该后续观察不能证明前一轮所有暂停均因 lease 过期。
当前实现中，显式浏览器输入仍依赖有效 HDMI 页面 lease，
因此显示线程的更新长尾是待查路径，尚未确认是本次暂停的唯一原因。
没有通过扩大时效上限、队列或隐藏错误来绕过这一问题。

## 恢复与下一步

板端校验备份目录：
`/home/xilinx/gl-calibration-install-20261011-p9jFFq`。
本地证据与恢复包：`phone_video_upload/output/input_repair_20261011/`。
恢复包 `input-repair-recovery.tar.gz` SHA256：
`fd601fd638fca2ea760c1fde4bf4d40c175edd38774d83b8e8b7040cab064f6e`。
含旧发布、变更目标、候选、计划和本次佩戴基线备份；不含原始 EEG、
手机视频或已上传媒体，仍应按私有状态管理。

不得在新 HDMI 正运行时盲目执行 rollback：先正常停止显示并确认 DMA
回收和正式 PL 恢复，再让安装器按前后指纹校验回退，最后按旧准入恢复
显示。以后目标若再次改变，安装器会拒绝覆盖。

下一步应针对主窗口处理进度与 SSVEP 调度做短时定位，而不是重新校准、
改模型或让用户反复试闪烁。分开记录主 worker 的实际处理耗时、待处理
数量、结果年龄，以及浏览器输入心跳和 HDMI 页面 lease 的新鲜度。
明确剩余瓶颈并通过复测后再进入四频＋休息测试。当前轮椅继续禁用。

## 后续调度定位：候选验证记录（随后已部署，见末节）

本节记录上述部署后的续查，不能与已经上线的十六目标更新混为一谈。
续查没有重启正式采集、网页或显示，没有加载 PL、启动闪烁或清除校准。

### 已确认

- 约 29 秒、不闪烁输入观察得到 24 次状态采样和 247 次页面心跳观察。
  SSVEP 为 ready 10 次、warmup 7 次、suspended 2 次、no_data 5 次。
  在相对 5.11 秒，HDMI 页面心跳年龄达到 2.081 秒，浏览器输入心跳仍
  有效；随后 5.43 秒出现 page_task_suspended。证明至少一次暂停来自
  HDMI 页面 lease 超过两秒，不能据此归因全部暂停或队列缺口。
- `page_policy.py` 在读文件前采样时钟，写端可能在读过程中推进，令
  合法的新时间戳被当成未来值。确定性回归能复现该竞态。候选改为在
  读取各自时间戳后取单调时钟；页面两秒、浏览器三秒时限及全部校验
  保持不变。新增阻塞读取导致过期的测试，确认没有延长有效期。
- `media_player.py` 发布页面心跳时用了循环开始的时间。循环中的脑电
  状态处理、标签绘制和准入检查可能已经耗时。候选仅将该处时间戳
  改为发布前重新读取单调时钟；这不能保证真实循环永不超过两秒。
- 最新正式日志存在 MALFORMED_STREAM、STREAM_TIMING_GAP、STREAM_IDLE。
  这些是连续输入窗口重建，不是佩戴基线重置。末次快照累计流复位
  30 次、坏字节 16813、序号缺口 473，随后已恢复 prediction；仍不能
  判定实时稳定验收通过。最近 240 条内核日志未见 USB 断开或复位，
  这个有限范围的阴性结果不能排除无线、供电、串口或更早的 USB 问题。
- 采集、网页与显示的 PID 分别仍为 12118、12125、12724，NRestarts=0。
  同次开机校准持续 15/15，calibration-session SHA256 始终为
  `639c5b58c7e34d6b040f759f7794fa4a6ec93acfb943c0284391245be1333c49`。
  正式清单 SHA256 仍为
  `189ef68f693d4add0757d7ed8e315b3bf5cdd98aa44e6f1ad191a6e115fd040e`，
  57 个文件无不匹配。HDMI API 确认 menu/home、静音、无闪烁、方向 stop、
  physical_output_enabled=false；基础 player_status.json 的 starting 记录
  不是当前实时状态，不能以它判定显示退出。

### 计算定位的边界

私有合成输入、只读加载既有基线的 8000 样本诊断产生 13 个主窗口。
诊断以 Nice=10 运行，正式进程仍为 Nice=0，因此不是正式实时延迟验收。
第二轮总墙钟 6.740 秒、线程 CPU 3.244 秒。每次窗口快照平均 CPU
26.98 ms、原始质量描述 27.17 ms、滤波后质量评估 49.29 ms；独立八次
情绪特征/核计算平均 CPU 分别 34.76/5.64 ms。最长主窗口墙钟
421.72 ms 时，对应 CPU 120.91 ms、非自愿调度切换 57 次。

合成信号没有通过保存的情绪质量门控，故常规 emotion_predict 计时
主要是拒绝路径；额外特征与核计时没有发布成情绪预测，也不验证准确率。
这些结果支持继续减少窗口整理/质量评估的成本，并检查 CPU 竞争；不能
证明某个后台进程是所有积压的唯一根因。实时后台进度超过 500 ms 后
状态可能一直保持 backlog，直到下一次新鲜结果被接受，因此状态采样的
backlog 次数不能直接换算成连续堵塞时长。

### 测试、证据与交接

- 本地调度、HDMI 绘制和命令检查共 38 项：37 项通过、1 项平台跳过。
- 板端 Python 3.8 私有目录的页面调度测试 8 项全部通过，0.286 秒。
  正常未来值、过期、错误模式、实体输出标志和损坏 JSON 仍拒绝启用。
- 两处生产代码候选只改现有调度/JSON 调用，没有新建运行框架或扩大
  队列和时效。新增计算脚本为有限、私有诊断，不接触 USB、PL、正式
  输出或保存佩戴基线。此次沿用 code-humanizer 约束，未做无关清理。
- 证据位于 `phone_video_upload/output/input_repair_20261011/`：
  `lease-correlation.json`、`window-kernels.json`、
  `timing-policy-linux-tests.json`、`scheduling-diagnosis-stream-evidence.json`、
  `scheduling-diagnosis-final-health.json` 与两份 `scheduling-diff-*.json`。

在本节记录时，两处修复尚未写入正式目录。若接着上线，须新建安装 stage 和独立备份，
不能复用已提交的 p9jFFq 安装计划。更新正式 page_policy 清单、所有相关
准入指纹与 HDMI media_player 指纹后，经过明确授权再短暂重启采集和
显示（包含已有 eye_wifi.bit 的重新加载），核对同次佩戴基线并复测。
串口坏包与真正的长时调度等待仍待单独定位，不应让用户用重复校准或
反复闪烁试验来掩盖这些问题。

## 页面时钟修复：已部署，实时稳定性验收未通过

用户批准备份、短暂重启 ARM 采集与网页、恢复 HDMI 并重新加载已有
`eye_wifi.bit`。本轮使用独立安装目录
`/home/xilinx/gl-calibration-install-20261011-QkQBuD`，未复用上次 p9jFFq
的安装计划。正式版本现在为 `guardianloop-page-timing-repair-20261011`，
清单 SHA256：
`af02baeb86e49d4f91df14d72537a4f93857a8914665c8792765bc8bc5ddefba`。

### 更新范围和恢复

- 仅更新两份生产代码：正式 `page_policy.py` 的读取后取时钟，以及
  HDMI `media_player.py` 的发布前取时钟。其余五个目标为正式清单、
  显示准入指纹、启动状态、实时入口状态和 boot-pins；共七个目标。
- 安装器复用既有输入修复的校准保留和校验回退机制，增加精确七目标
  准入测试。未部署其他本地候选优化，未增加框架、依赖或驱动。
- 本地 46 项检查：45 项通过、1 项平台跳过。板端 Python 3.8 的
  16 项私有检查全部通过（2.732 秒）；生产安装前逐项核对旧文件和
  payload 指纹。模型、500 ms 时效门槛、页面两秒和浏览器三秒 TTL
  均未改变。
- 旧 HDMI `play-40bda203` 正常退出，报告确认原 PL 恢复、DMA 缓冲
  回收且 errors 为空，然后安装；采集和两个网页服务恢复后提交。
  新 HDMI 会话 `play-15e10318` 已恢复为静音 home 菜单、方向 stop、
  无闪烁、实体输出禁用，继续保持用户控制关闭、无自动到期。
  最后核对正式 57 个文件与 boot-pins 的 79 个目标全部匹配，采集、
  主网页、媒体网页及显示均 active，NRestarts=0。
- 初次显示状态查询早于初始化完成，返回 inactive，诊断脚本因此退出。
  随后只读日志和状态确认同一显示进程已正常 playing，再切回 home；
  没有因此重启第二次采集、清除校准或执行回退。
- 同一 boot `0e44bc51-655b-4974-b982-d6689fa20948`，校准持续 15/15，
  八通道 SQI 参考各 60 个。校准文件 SHA256 仍为
  `639c5b58c7e34d6b040f759f7794fa4a6ec93acfb943c0284391245be1333c49`，
  wear 文件仍为
  `980c25f97e458583211c3b46a9fc97c422d95f28d2a8c9cf96fe5503ff99a412`。
  此保留只适用于已核对的同次开机、同次佩戴，不扩大到重新戴帽或换线。

### 不闪烁复测：剩余故障仍存在

24 次输入状态采样、无诊断请求错误，前后校准文件完全相同。
SSVEP 为 ready 6 次、warmup 12 次、no_data 5 次、suspended 1 次。
有效 ready 样本的输入年龄最大 214.0 ms；全部带数值的年龄样本最大
1232.5 ms 出现在 no_data，已撤销输出，不能称为可信预测计算耗时。
这些离散状态计数不是识别准确率，也不能代表逐包或端到端延迟。

主监测状态为 MALFORMED_STREAM 18 次、STREAM_TIMING_GAP 6 次，
期间没有正常主任务预测。运行时累计流复位由 5 增至 10，reader 队列
等待的进程累计峰值为 501.513 ms，过期包丢弃累计 1 个。SSVEP 也出现
reader_queue_gap、input_backlog 和 input_expired。这说明流连续性及
交付长尾尚未解决；不能因时钟回归通过而宣称整机稳定验收通过。

主监测 SQI 在该轮中不可用，CH2 的 24 次详细质量读数均为 null；
不能把“usable=true 次数为零”说成 CH2 被降权或电极不良。
随后实时快照仍显示 15/15 保留，并出现 PRIMARY_WORKER_BACKLOG，
累计坏字节 1474、序号缺口 36。有限的最近 180 条内核日志未见 USB
断开或复位；仍不足以排除无线、供电、驱动或更早的 USB 问题。

页面观察中有一次年龄 2.0047 秒；同一观察的浏览器输入 enabled=false，
即已经释放输入。24 次输入状态采样内仅最初一次 suspended，随后均
来自暖机或流连续性/过期检查；这不能证明 HDMI 永远不再超过两秒。
释放输入后 suspended、ready=false、age_seconds=null，旧结果正常撤销。
全程未录制原始 EEG、启动闪烁或使轮椅运动。

### 只读负载定位与证据

八秒进程 CPU 观察中，采集父进程约 30.9%、主网页约 22.6%、HDMI 约
14.9%；这些百分比按一个 CPU 核计算，不能单凭它们认定双核已饱和。
所有被观察进程均允许运行于 CPU 0/1，没有观察到固定单核亲和性。
板端 `/proc/<pid>/schedstat` 不存在，故没有获得实际运行队列等待时间。
前一轮十二秒脚本因该接口缺失得到空进程列表，不作为负载结论；随后
八秒脚本改用现有 /proc/stat 字段，明确记录缺失项，正常得到 11 个进程。
未改生产调度优先级或 CPU 亲和性。

本轮沿用 code-humanizer 限制改动范围，复用安装器和恢复包流程。
证据位于 `phone_video_upload/output/page_timing_repair_20261011/`，包括
`linux-tests.json`、`deployment-plan.json`、`before-deploy-audit.json`、
`display-recovery-before-install.json`、`installed-live-check.json`、
`display-restarted-confirmed.json`、`live-input-observation.json`、
`live-input-summary.json`、`post-retst-input-diagnosis.json`、
`process-scheduling-8s.json` 和 `final-health.json`。

新恢复包 `page-timing-recovery.tar.gz` 大小 2,292,916 字节，SHA256：
`6e0865ed351c5a1ebefcecf67c8acc6775df60060ed6556696dce28e8cbcd25b`。
含旧正式发布、七个旧目标、候选 payload、校验计划、安装器和本次佩戴
基线私有备份；不含原始 EEG、手机视频或访问密钥。不要在新 HDMI 正
运行时盲目回退：先正常停止并确认 DMA 回收和原 PL 恢复，再执行严格
校验的回退，最后依旧准入恢复显示。

下一项应分离定位串口坏包、reader 交付等待和主 worker 进度长尾。
末次健康快照主监测为 PROCESSING_BACKLOG，累计收包 89588、坏字节
5676、序号缺口 157；校准和 wear 指纹仍完全相同。该快照再次证明
剩余问题没有解决，不应以服务 active 或恢复校准等同于预测可用。
目前仍不应进入真实四频闪烁或实体轮椅联动，也不应要求用户反复校准。

## 网页状态减负候选与输入链路再定位（未部署）

本轮只改本地 `guardianloop_web.py`，在新私有目录
`/home/xilinx/gl-input-chain-20261011-lCdUz8/runtime` 做检查，没有修改正式
发布、服务配置、校准、模型或 PL。沿用 code-humanizer 的最小变更约束，
复用现有状态读取、过期撤销、TelemetryResponseCache 和测试入口，没有
新增实时采集程序、依赖或预测缓存。

### 已确认的代码问题与候选

- 原 `system_status()` 每次遍历 ttyUSB/sysfs，并分别启动两次服务查询。
  候选将查询合并为一次 `systemctl show`，按 Id 映射，拒绝缺项、重复
  单元、非预期单元、查询失败和超时，不缓存旧的 active 状态。
- 接收器检查改为直接 stat 现有正式采集契约要求的 D309LDXY udev
  字符设备。语义明确收窄为本系统固定的 Cyton 接收器，不再把其他
  FTDI 适配器认作它。此路径已由运行服务及板端 sysfs 核验；更换
  接收器时须同时更新固定采集契约，不能仅靠“USB 芯片相同”放行。
- `/api/status` 原先先判脑电新鲜，再做可能阻塞的服务查询。新增
  HTTP 回归在查询期间分别模拟输入过期和状态过期；旧代码两种
  情况均错误返回有效结果，两个 subtest 都失败。候选将服务查询
  前移，让既有时效门控在查询结束后执行，保持原阈值和撤销规则。
  这修复响应中的旧结果暴露，不证明无线坏包或采集长尾已经解决。

候选 `guardianloop_web.py` SHA256：
`4b67d166c3cb6569bcc9cd3378e8310e92fee2e8b10f835ac83d8654461c8e79`。

### 私有验证和测量边界

Windows：主组 21 项，20 项通过、1 项 Linux 字符设备 fixture 跳过；
缓冲组 7 项，4 项通过、3 项 Linux fork 测试跳过。板端 Python 3.8
主组 21 项全部通过（14.717 秒），缓冲组 7 项全部通过（35.539 秒）。
涵盖真实 `/dev/null` 的字符设备链接、链接移除、普通文件与悬空链接，
以及过期输入、过期主状态、原有缓冲和波形缓存行为。测试只使用私有
fixture，不打开 Cyton 串口或加载 PL。

在同一 Nice10 诊断进程中交错调用原版和候选，各 8 对。最新一轮：
接收器检查墙钟中位耗时 15.829 -> 0.249 ms；系统状态查询中位
321.422 -> 258.746 ms，最大 581.381 -> 344.291 ms，包含子进程的
CPU 中位耗时 66.103 -> 54.112 ms。每对返回值均相同。前一轮系统
查询为 231.520 -> 164.168 ms，显示板端调度背景会影响墙钟值。
这些是元数据函数测量，不是脑电端到端延迟、准确率或整机减负比例；
少量样本也不能保证以后没有长尾。

8 秒主线程 futex 跟踪只记录锁操作与耗时，没有采集 EEG 内容。
11,690 个带时长的记录中最大 18.286 ms，未捕获 >=50 ms 的等待；
不能据此排除其他时段或其他线程的阻塞，也不能把它当无扰动验收。
首次解析不支持 strace resumed 行而失败，随后只重解析保留日志，
没有重复跟踪；已核对 TracerPid=0。纯函数、回归与跟踪均不重启正式
服务，但会叠加 CPU/调度开销。

### 仍存在的故障与下一项

最初四分钟日志坏字节稳定为 6776、序号缺口 187，仍出现积压；后续
快照增至 15243、433，并记录 MALFORMED_STREAM、STREAM_TIMING_GAP
和 STREAM_IDLE。因此输入链路异常与处理积压是两类待分离的问题，
不能把短时无坏包推广成无线链路已正常。

缓冲测试结束后的累计队列峰值达到 2052.726 ms，过期包丢弃 1962，
主状态为 PROCESSING_BACKLOG。这期间有私有诊断负载叠加，不能当作
无诊断的生产基线，更不能声称本轮优化已消除积压。全部私有单元
结束后再进行轻量只读观察，结果另存，不追加计算压力测试。

诊断全部结束后的 11 次轻量采样跨 21.495 秒：主状态有效 8 次，
末次有效、无拒绝 reason，当前 reader 队列等待 17.141 ms。坏字节
15243、缺口 433、流复位 47 和过期包 1962 均未增加，校准/wear
指纹保持不变。系统恢复了有效输出，但这是短时离散观察，不是
长时间稳定性通过，也不能证明诊断负载就是之前全部故障的原因。

正式版本仍为 `guardianloop-page-timing-repair-20261011`，57 个正式
文件和 79 个 boot-pins 均完全匹配。采集、主网页、媒体网页及原
HDMI 进程 PID 均未变，NRestarts=0；HTTP 确认 HDMI 仍为 home 菜单。
同一 boot 的 15/15 及八通道各 60 份 SQI 参考未变，校准/wear 指纹
仍为前节记录值。候选没有写入正式清单，不能直接覆盖上线。

下一项应请求短暂独占串口：停止正式采集后，复用
`diagnose_stream_transport.py` 做约 40 秒纯接收计数对照，不存脑电
样本，不启用模型、SSVEP 闪烁或 PL；随后恢复原采集并核对同次
佩戴校准及所有入口。不允许同时打开第二个串口读取者。网页候选
留待有完整恢复校验的部署，避免把网页减负称为输入故障的根治。

证据目录：`phone_video_upload/output/input_chain_diagnosis_20261011/`。
主要记录为 `private-stage.json`、`linux-final-tests.json`、
`linux-cache-tests.json`、`paired-final-web-cost.json`、
`main-futex-summary.json`、`current-health.json`、`recent-events.json`、
`final-health.json` 及 `post-diagnostic-observation.json`。初次
`initial-audit.json` 包含现有 telemetry 的波形快照，不是新启动的
同步原始 EEG 录制；后续只保存选定元数据。该初次快照属私有数据，
不要随公开工程包转交。

## 本次佩戴问题收尾：先修复验证，随后已部署，见末节

用户关闭 Cyton 后要求修复此次佩戴遇到的问题。本节操作通过以太网
192.168.2.99 完成，不要求重新佩戴或开机。当前只修改本地源码，并把
候选及校验安装计划放入板端私有目录；没有写入正式目录、重启正式
服务、清除校准、切换网络或加载 PL。此前已上线的缓冲、异步主任务、
异步 SEED 和页面时钟修复不能重复说成这轮才完成。

### 纯收包的实际结果：不完整，不能算稳定性通过

此前获准停止正式采集进行纯收包，使用单一串口读取者、十包批传递，
不运行模型或保存脑电样本。独立 150 秒恢复计时器及 transient unit 的
`ExecStopPost=/bin/systemctl start guardianloop-cyton.service` 保护恢复。

原计划收包 40 秒，但 50 秒命令保护时限包含约 16.6 秒 ARM 模块启动，
实际收包仅 33.378 秒，退出码 124，`completed=false`，单元 failed。
保存的部分计数为：7909 帧、1310 坏字节、37 次序号缺口；首次异常在
9.804 秒，最大收包间隔 320.04 ms，超过 250 ms 的间隔一次。236.95
帧/秒是该部分时段的计数率，不是完整验收或无线吞吐结论。

模型关闭时依然观察到格式与序号异常，说明它们不全由主模型计算积压
造成；目前不能进一步区分无线干扰、发送端、USB、串口或驱动来源。
最大 reader 交付年龄 13.79 ms 也不能代表长时间稳定。

失败后恢复钩子成功，正式采集恢复为 PID 27104；网页、媒体网页及
HDMI PID 23651/23653/24089 没变。随后核对正式 57 文件、79 boot-pins、
PL 和校准指纹均不变，才取消备用恢复计时器。证据保留在
`phone_video_upload/output/stream_transport_isolation_20261011/`，尤其
`pure-receive-result.json`、`after-restoration.json`。

私有诊断 runner 的本地超时已改为 75 秒，为模块启动留出时间；未上传
或再次实测，不属于正式采集更新。第一轮 fixture 未模拟 tcflush，及
最初错误使用 `/usr/bin/systemctl` 的尝试均已记录；后一项在停止服务
之前失败，没有出现无恢复保护的串口独占。

### 本轮四份生产候选的精确作用

1. `guardianloop_web.py`：接收器固定身份检查与合并服务查询减负；
   在阻塞查询完成后再执行原有新鲜度检查。桌面状态及 telemetry 轮询
   防重入、1.8 秒超时；请求失败隐藏旧分类和质量。未把其他所有接口
   都改成此轮询方式，也不缓存旧 active 服务状态。
2. `mobile.js`：显示 CH2 等通道的具体降权原因；明确“校准 15/15
   保留，等待连续窗口，不是重新校准”。断流或过期继续撤销旧结果，
   不将无数据当作休息或正常情绪。
3. `async_primary.py`：后台每次产生主窗口时，记录 processor.append
   的实际墙钟耗时，作为 reply 元数据。包括此期间调度等待，不是纯
   CPU 时间；不含校准文件写入、回复 IPC，也不是数据年龄。
4. `cyton_guardianloop.py`：将该耗时送入已有 telemetry 字段，结束
   异步运行下“窗口计算耗时一直为空”的观测缺口。计算公式、数值
   结果、模型、队列容量及过期和质量门槛保持不变。

沿用 code-humanizer 的局部约束，复用现有安装器和状态字段，不做
无关重构、添加依赖、另建实时采集框架或修改驱动。

### USB 检查与 CH2 结论边界

固定 FTDI 接收器 D309LDXY 实际 USB 设备的 power/control 为 on、
runtime_status 为 active，latency_timer 为 16；有限的最近 500 条内核
记录未发现此接收器断开/复位。因此没有证据支持把它直接归因于接收器
自动休眠，未据此改驱动或电源设置。父节点部分属性读取返回 EIO 是
不支持的 sysfs 属性，不是捕获到串口传输 I/O 故障。
证据：`phone_video_upload/output/prewear_issues_repair_20261011/usb-readonly.json`。

CH2/F4 此前存在 usable 的观察，也有质量窗口不存在的时段，不能
将空值说成持续降权。Cyton 已关闭，本轮无法重新判定当前电极接触或
位置，只修复原因展示，不强制将 CH2 改成可用。

### 回归、安装计划及未完成事项

- Windows 最近一组 28 项：24 通过、4 项平台条件跳过。
- Node 虚拟 DOM 检查通过，覆盖手机/桌面的降权原因、校准保留文字、
  旧质量撤销、同接口不重叠、请求超时后可恢复；没有实际闪烁。
- 第一私有 stage 56 项因缺少 package 相对链接有一项加载错误；该轮
  不算通过。复用正式 staging helper 补齐链接后重测。
- 最新板端 Python 3.8、Nice=0 的 80 项检查：79 通过、1 跳过，
  156.673 秒，单元 inactive/success/status=0。跳过项需要封存的重构
  前源码 `GL_TEST_PRIMARY_REFERENCE`，不是缺少脑电录制。实际 fork
  worker 与同步 processor 的 36000 样本逐结果数值一致性测试通过。
  注入校准写入失败及模拟回退的日志不是正式服务操作。

候选目录：`/home/xilinx/gl-calibration-install-20261011-iy7HY5`。
私有检查单元：`gl-calibration-install-20261011-iy7HY5-tests-9905.service`。
证据和 payload：`phone_video_upload/output/prewear_issues_install_20261011/`。
可校验计划锁定九个目标：上述四份源码、正式 release_manifest、显示
准入指纹、启动状态、live state、boot-pins。没有 SQI、模型、bit/hwh、
驱动或启动服务配置目标。候选发布清单 SHA256：
`395befb103745e56247866f69cb12d56f0bc98771ec41de6ee8f29b0204bdbc0`。
候选发布名：`guardianloop-prewear-issues-repair-20261011`，**尚未安装**。

正式版本仍是 `guardianloop-page-timing-repair-20261011`，不能把 stage
成功说成正式板端已修复。安装器的旧发布及校准备份尚未创建：只有执行
获准的 install 时才建立备份并启用独立回退。当前显示运行期间不能
直接覆盖清单，否则内存中的显示准入指纹会与新清单冲突。

末次只读核对 `final-predeploy-health.json`：57 个正式文件及 79 个
boot-pins 无不匹配；九个旧目标和候选 payload 均符合计划；没有
installation.json。正式四个服务 PID 未变、NRestarts=0，当前 PL 仍为
eye_wifi.bit，校准保持 15、八通道参考各 60，calibration/wear 指纹
完全不变。Cyton 关闭后的状态是 invalid/STREAM_IDLE、valid=false、
calibration_retained=true；这是正常撤销旧结果，不是基线被清除。

已向用户请求短暂停止 HDMI、安装 ARM/网页候选并恢复 HDMI 的授权。
正常恢复会涉及已有 guardianloop_pynq.bit 和 eye_wifi.bit 的加载；
在授权答复到达之前不操作。安装前须再次核对 boot、正式/候选指纹，
退出显示确认 DMA 回收和原 PL 恢复，然后严格安装、核对、提交与恢复。
模型及启动镜像不变；失败沿用校验回退。

同次开机的校准 SHA256 为
`639c5b58c7e34d6b040f759f7794fa4a6ec93acfb943c0284391245be1333c49`，
wear SHA256 为
`980c25f97e458583211c3b46a9fc97c422d95f28d2a8c9cf96fe5503ff99a412`。
保护这些文件不等于在换戴、换线或重新上电后盲用旧基线。

上线后下次佩戴先做短时不闪烁检查：收包及主窗口更新及时、坏包/缺口
没有持续增长、CH2 原因可解释、15/15 在异常恢复时不丢失，再进入四频
和休息。剩余物理链路稳定性及真实负载长尾尚未通过，不能保证以后绝不
断流，也不能开放实体轮椅来验收。统一显示 PL 与所需加速模块的融合
仍在主线，缺显示版 Vivado 源码，不在本轮修改范围。

后续更新：2026-10-12 已上线停流年龄显示、等待原因及只读佩戴前提示，
见 [PREWEAR_STATUS_REPAIR_20261012.md](PREWEAR_STATUS_REPAIR_20261012.md)。
最新发布为 guardianloop-stream-status-repair-20261012；下面的 10 月 11 日
部署记录保留为历史，不代表当前 HDMI 仍在运行。

## 获准更新后：已正式安装并恢复 HDMI

用户随后回复“允许”，授权正常停止 HDMI、安装正式 ARM/网页并恢复
已有显示 PL。通过以太网操作，没有切换 Wi-Fi、复位板卡、烧写 SD、
修改模型、启动闪烁、声音或实体轮椅。Cyton 始终按用户要求关闭。

### 更新检查拦截的权限问题与回退

旧会话 `play-15e10318` 正常结束，确认 controlled_stop、display_halted、
original_restored、buffers_released 均 true，errors 为空。退出时只按
既有流程恢复正式 guardianloop_pynq.bit。

第一次在 iy7HY5 安装后，网页 HTTP 检查没有通过：启动自检状态显示
not_checked。只读核实文件实际内容为 ready、boot 正确、版本正确，但
该文件为 root:root/0600，而 guardianloop-web.service 以 xilinx 运行，
无法读取。不是脑电校准被清除。最初检查脚本直接索引 release_id 自身
抛 KeyError，此后检查实际响应和文件权限才确认原因；该检查不算通过。

独立 150 秒计时器自动恢复旧版，installation.phase=rolled_back、回退
单元 success。后续尝试修正所有者的指纹检查发现文件已回退，拒绝
操作，没有实际 chown。因此没有在未核验网页权限的状态提交第一轮。
iy7HY5 的原安装记录和备份保留，不重复使用其安装目录。

修正既有部署 helper：公共启动自检报告用 0644，root 仍为唯一可写者，
网页用户可以读取；没有扩大 calibration/wear、原始脑电、访问密钥或
其他私有状态文件的权限。安装器对本轮 STARTUP 目标同时检查计划模式
和安装后真实模式，防止只验内容 SHA 却忽略权限再次上线。只改这个
公开报告的权限契约，没有全项目权限重写或新建部署框架。

新增两个回归检查。第一次将权限验证扩大到所有平台/目标，Windows
已有 fixture 出现一项失败、一项错误；随后收窄为本轮 STARTUP 目标。
最终 Windows 安装器 11 项：10 通过、1 个 Linux 权限位检查跳过。
板端 Python 3.8 的安装器、服务查询及移动网页 18 项全部通过，1.307 秒。
四份生产源码 SHA 与前一轮 80 项（79 通过、1 跳过）完全一致，数值
路径没有再次改写；不能把重复检查数相加当作独立测试用例数量。

### 正式提交与完整恢复

独立安装目录：`/home/xilinx/gl-calibration-install-20261011-LVfOPd`。
最终仍是精确九目标，同一个候选正式发布：
`guardianloop-prewear-issues-repair-20261011`，清单 SHA256：
`395befb103745e56247866f69cb12d56f0bc98771ec41de6ee8f29b0204bdbc0`。

第二轮将安装、后检查和提交连续执行，保持独立回退保护，避免控制端
停顿耽误提交。逐项核对目标指纹、启动报告真实权限、正式 57 文件与
79 boot-pins、同次开机、calibration/wear 指纹，以及采集和两个网页
服务 active。网页 `/`、`/mobile`、`/mobile.js`、`/api/status` 均 HTTP
200；确实提供新轮询代码和降权原因文字，启动状态 ready/新版本。
Cyton 关闭时情绪、疲劳均没有有效预测，校准为 15/15 且 retained=true。
全部符合才提交，installation.phase=committed，回退计时器 inactive。

新显示 `play-52f4b09f.service` 加载已有 eye_wifi.bit，home 命令 receipt
为 applied，HDMI 回到 menu/home。保存的 SD 视频选择仍是 sd02；没有
自动开启视频、眼控标定或刺激。确认 silent=true、audio_output=false、
direction=stop、physical_output_enabled=false、stimulus_enabled=false、
mi_exit_enabled=false。会话 user_controlled=true，无自动到期。

末次核对服务 PID：采集 13993、主网页 13997、媒体网页 13999、显示
14263，全部 active、NRestarts=0；本轮明确安装/回退的服务重启不能
据此说成“从未重启”。PL 仍是 eye_wifi.bit，57/79 指纹均匹配。
calibration-session、wear-session SHA 仍为前节记录值，疲劳参考 15、
八通道 SQI 各 60；当前 invalid/WAITING_FOR_CYTON、valid=false、
calibration_retained=true。这是设备关机后的保护状态，不是重校准。

### 恢复包、证据与下次佩戴边界

证据目录：`phone_video_upload/output/prewear_issues_install_20261011_retry/`。
包括 linux-tests、deployment-plan、installed-live-check-and-commit、
display-restarted-confirmed、final-health、rollback-timer-final 和 recovery。
首次尝试的权限诊断、自动回退状态和显示退出确认仍保存在未带 retry
的同名目录。末次 Node 虚拟 DOM 整合检查通过，未产生真实闪烁。

板端恢复包：
`/home/xilinx/gl-calibration-install-20261011-LVfOPd/prewear-issues-recovery.tar.gz`。
已校验下载至本地证据目录，2,367,987 字节，SHA256：
`e1a7b657dcce4fa6365311523159d711943a5302c1b6e36190b376275ed73ea9`。
含旧正式发布、九目标备份、候选 payload、校验计划、安装器、提交记录
及同次佩戴基线备份；不含原始 EEG、手机媒体或访问密钥。基线备份仍
属私有状态，不应放进公开工程包。首次普通 SFTP 因归档 root/0600
拒绝读取，改用已有受控 root 读取 helper 下载，未放宽恢复包权限。

回退必须先正常停止当前显示、确认 DMA 回收及原 PL 恢复，再在这个
独立目录运行校验安装器 rollback，按旧准入恢复显示。不能在当前 HDMI
运行时直接覆盖清单或重新执行 install；若文件后来已变更，回退应拒绝。

本轮完成的是软件修复上线与设备关闭条件下的恢复验收，不是佩戴准确率
或全链路延迟达标。纯收包中的坏字节和缺口来源仍未定位，下次先做
短时不闪烁真实输入检查，确认窗口及时更新、质量原因可解释、基线没有
意外清除，再进入四频＋休息。没有改变质量/时效门槛，也不能声称无线
断流从此绝不发生。同次开机校准保留不扩大到换戴、换线或新开机。
