# 采集候选短读缓冲修复（2026-10-12）

## 已部署的修复

`ReaderPacketSink` 的批大小为 10，底层队列槽数为 `capacity // 10`。
原串口读包循环每次短读后都调用候选 `flush()`；若每次只读到一包，标称
128 包容量实际只剩 12 个单包消息槽。候选消费稍有停顿就可丢包，ordinal 缺口
导致 `ssvep_reader_queue_gap`、窗口重新预热。此路径和真实串口 framing 错误不同。

只修改 `pynq_guardianloop/cyton_guardianloop.py`：候选正常积累到 10 包再提交；
空闲 40 ms 时提交尾批，读包进程退出时也提交尾批。主采集短读仍立即提交。
没有扩大队列、重写接收时间、插值脑电、改标签或放宽 500 ms 新鲜度检查。
连续 250 Hz 输入时，十包积累额外等待最多约 36 ms；中断后的尾批由空闲路径释放。

实现复用现有 `offer`/`flush`，按 code-humanizer 约束没有新增队列类、后台线程或配置开关。
回归测试在 `pynq_guardianloop/test_reader_batch.py`。

## 软件验证

新增 Linux 管道测试把 80 包输入切成每次最多 2 包，停止消费候选队列，仍要求其保存
容量以内全部 ordinal 和原始 packet；另测不足十包的 idle/EOF 尾批交付。
板端原版聚焦 2 项测试有 1 项失败：候选队列收到的包不足 80，读取超时。
这在不接触真实串口的条件下复现了错误，不是以截图推断。

修复后 Windows 本地 54 项运行成功，其中 40 项因 Linux/fork 平台限制跳过；
采集模块编译检查通过。板端 62 项相关测试全部通过，66.911 秒。
包括短读、尾批、真正队列满、ordinal 缺口、原包/时间/标志保持、SSVEP 数值参考、
暂停恢复、过期输入撤销及校准存档边界。

首次较大板端测试目录缺少 `test_calibration_main`，同时发现预期的短读测试失败；
失败日志保留。补齐私有测试依赖后使用聚焦测试复现，再运行修复测试，未修改正式依赖。

## 用户授权的安装和恢复

复用 `deploy_input_repair.py` 的已有窄文件集和
`install_calibration_repair.py` 备份、独立回滚 timer、commit 流程。
私有安装目录 `/home/xilinx/gl-calibration-install-20261011-4U10KD`，
备份含旧正式发布和同次开机校准；安装已 committed，回滚 timer 已取消。

新 release 为 `guardianloop-reader-tap-repair-20261012`。
九个安装目标中，网页、mobile.js、async_primary.py 字节未变；正式数学与模型不变。
除了采集源码，变化仅为 release、启动状态、显示准入和对应校验值。
上一轮 HDMI 时间比较修复保持，没有覆盖回旧版。

旧显示 `play-87d62ec9` 正常退出，报告 original_restored、buffers_released、
display_halted 为 true，errors=[]。先恢复正式 PL，再安装并重启采集和控制网页。
同次开机 15/15 校准成功恢复，校准文件 SHA256 前后一致：
`14f30964edeb5ae8a1fc66bab104ff077116e79fc96f3a18bdbd3810865dfcb3`。

随后加载原有 `eye_wifi.bit`，会话 `play-ac55ca7a`，静音、无闪烁、实体输出禁用，
主页→最低速度→静态方向的执行回执均 applied。一次过早选择在页面阅读门控内被拒绝；
等待实际 reading=false 后成功，不是命令过期或再次校准。

## 更新后的实际输入仍未通过

修复后静态方向页的 24 次只读观察：0 次 ready，全部因
`malformed_or_sequence_or_timing_gap` 预热；未观察到 `ssvep_reader_queue_gap`。
这只证明该短观察未再次出现队列缺口，不是无限期保证。
异常字节 22,383→23,284，序号缺口 668→693；主监测均 MALFORMED_STREAM。
当时 reader_queue_delay_max_ms=226.437、stale_packets_discarded=0，校准一直 15。
主要剩余阻塞不能再一概称为“计算队列满”；需要区分实际传输/分帧错误。

用户另外允许暂停约 1～2 分钟，进行 40 秒纯收包对照后自动恢复。
复用 `diagnose_stream_transport.py` 与 `stream_transport_session.py`，
使用同一读包器但不运行模型、不保存 EEG 样本、不动电极、静态 HDMI 保持。
独立 ExecStopPost 和 150 秒备用恢复 timer 保证恢复采集。
本轮诊断目录 `/home/xilinx/gl-stream-transport-20261012-uNznF4`。

纯接收结果：40.004 秒、9,913 包、247.800 包/秒，正常结束；异常字节 184、
序号缺口 5，首次错误约 2.822 秒。最大交付年龄 9.868 ms、最大接收间隔
215.109 ms，超过 250 ms 的间隔为零。无模型时仍出现 framing/sequence 错误，
因此不能把所有错误归于主推理队列；但也未锁定无线、电池、接头或固件中的具体原因。

ExecStopPost 自动恢复采集，PID 1164、NRestarts=0；校准文件 SHA 不变。
备用 timer 到期后执行幂等 start，最终 not-found/inactive，无未结束的诊断任务。
控制端尝试取消已卸载 timer 返回 not-loaded，保留该输出；不谎称取消动作成功。

恢复后曾观察到连续段约 46,000 包、异常字节及序号缺口均为零，情绪/疲劳
进入正常预测；仍出现计算长尾，reader 最大交付延迟 554.684 ms、丢弃过期包 22。
后续 framing 错误又恢复增长，最后一次静态方向观察 20/20 输入未 ready。
这些阶段性变化不足以宣布长期稳定，也不足以用单次前后变化认定电池或模型是唯一根因。

显示 `play-ac55ca7a` 后续因 Runtime guard heartbeat expired 退出，清理报告确认
原 PL 恢复、缓冲释放、DMA 停止均为 true。核验清理后按用户恢复静态显示的授权
重新加载显示版，`play-05637ac9`、PID 8427，最终静态 home 页，页面年龄约
0.294 秒、静音、stimulus=false、physical=false。此显示心跳长尾仍待后续减负修复；
没有放宽心跳门限或继续使用失去准入的显示进程。

最终正式清单与 boot-pins 所有文件匹配，校准仍 15/15。用户补充电池已使用约半个月，
没有条件将接收器通过延长线移远，并再次报告平线。最近三组波形统计均为 CH4
唯一值=1、标准差=0；其余七路有变化。更早的新鲜窗口明确 CH4 ADC near-rail ratio=1，
启动中心值 8,388,607，支持“ADC 饱和经中心化后平线”，不是纵轴缩放；最后波形快照
年龄约 2.899 秒，仍有断流，不能将其当作全链路实时就绪。
不以放大信号、放宽门限或伪造波形掩盖这一硬件输入异常。
下一步先关闭 Cyton 更换/充足充电原用电池，保持电极不动，再做同条件短收包核查；
未测电压，电池只是高优先级嫌疑，不是已确认根因。不主动清空校准。

此前的关 Wi-Fi 对照并未证明热点是根因：AP 开启前后短段没有新增坏包，
Wi-Fi 关闭的 30 秒反而仍有 102 异常字节、3 个缺口。因此不擅自关闭用户热点。
官方文档列出的低电量、距离和干扰只是后续排查候选，不是本机已证实原因：
https://docs.openbci.com/Troubleshooting/GUI_Troubleshooting/

证据：`phone_video_upload/output/reader_queue_repair_20261012/` 的
baseline、board-baseline-focus-result、linux-tests、before-install、deployment-plan、
display-cleanup、committed、post-install-before-display、static-navigation、
live-after-tap-repair、transport-plan 和 transport-launch。
