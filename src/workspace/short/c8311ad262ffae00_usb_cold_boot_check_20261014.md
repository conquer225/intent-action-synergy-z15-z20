# Z15 USB 冷启动对照：准备状态

这轮只准备和验证日志，不代表眼控／Cyton 已恢复连接。用户仍不在设备旁，未执行拔插、整板重启或换电。

## 已准备

- 板端 `/home/xilinx/gl-usb-boot-trace/usb_boot_trace.py` 与 `guardianloop-usb-trace.service` 已安装；服务已 enabled，但没有在当前 boot 启动该正式记录 unit。
- 下次启动会启动一个独立 Type=simple 观察进程，最多记录 180 秒后退出。它不成为正式采集的 Requires 依赖，不等待 180 秒才放行采集，不重试启动硬件。记录进程本身有 systemd 200 秒运行上限。
- 记录 USB VID/PID、序列号、节点、运行电源状态、固定串口入口、采集状态中的包计数／原因、USB／PL 内核事件及采集握手日志。不打开 USB 设备端点，不读取 telemetry 的脑电数组，不改模型／门限／校准，不控制轮椅。
- 日志路径 `/var/lib/guardianloop-usb-traces/<boot-id>-<monotonic-ns>.jsonl`；每次独立新文件，不覆盖或自动删除旧日志，文件权限 0600。
- 本地 3 项 fixture 测试通过，Z15 Python 3.8 同样 3 项通过；板端 systemd unit 校验通过。既有 dbus.socket 的旧 /var/run 路径提示与本 unit 无关，未修改它。
- 私有 12 秒观察 unit 正常完成，实际约 12.83 秒、19,332 字节；只产生 started／observation／completed 三条变化记录，未干扰当前会话。不能把这次已开机后的试运行描述为真实冷启动测试。

源码和安装记录在本工程 `pynq_guardianloop/usb_boot_trace.py`、`pynq_guardianloop/guardianloop-usb-trace.service`、`pynq_guardianloop/test_usb_boot_trace.py`，证据在 `phone_video_upload/output/shoot_ready_20261014/usb-boot-trace-*.json`。板端私有验证及安装记录目录为 `/home/xilinx/gl-usb-boot-trace-stage-20261014-4SRifa`。安装前记录目标目录和 unit 均不存在；回退可 disable 新 observer unit，再核对安装记录哈希，仅移除本轮新增 observer 文件，不操作正式采集或显示文件。

## 新取得的时间顺序证据

boot `24f029c7-bee2-4576-9c4f-fa07fb4d57f1` 的完整 dmesg 显示：接收器在约 19.343、21.902 秒断开重枚举，正式 PL 于 47.191 秒加载、显示 PL 于 75.959 秒加载。最早两次 USB 断开在两次 PL 下载之前，故不能将这两次断开归因为第二个 bit 覆盖第一个 bit。这个顺序不能排除随后其他故障，也不证明断开的具体电气／固件／驱动触发原因。

最终核查同一 boot，采集 PID 18415 未因安装日志而变化；原静态显示保持 home/menu、物理输出关闭；87 项既有启动 pin 无差异。正式采集仍未收通、眼控仍待枚举；本轮没有将日志功能验收写成连接验收。

## 等用户回到设备旁后

1. 不需要佩戴。保持同一电源、软件版本、端口、HDMI 和网络接法不变；Cyton 保持 PC 档开机、电机不使能。
2. 按届时明确确认的关机／重新供电流程做 A 组：只接接收器，眼控暂不接；保留网卡和管理连接，等启动观察 3 分钟完成后取日志。
3. B 组仅增加眼控回原 USB Host，其他条件不变，使用相同关机／启动流程再取一份日志。不要同时换电源、换口或更新软件。
4. 分开判断“USB 枚举成功”和“应用握手／新数据成功”：接收器要求正确序列号、配置回执和包计数增长；眼控要求正常工作标识，再用有限的原生握手确认，不能仅看已插线或电源灯。眼控握手成功不等于已完成三点标定。
5. 根据首个失败发生的时间和层级决定后续单一改动。单次恢复不宣布根因修好，冷启动重复验收的次数与条件在 A/B 首轮结果后确定。

本轮采用 code-humanizer Guard：单一只读观察器、标准库和既有 systemd／sysfs 接口，不新增采集器、驱动依赖或生产控制参数。

## A 组安全关闭已执行

用户到设备旁，明确确认眼控已拔下，随后单独授权安全关闭 Z15。关闭前同一 boot `24f029c7-bee2-4576-9c4f-fa07fb4d57f1`、接收器 `0403:6015/D309LDXY` 与网卡均在，无 EyeChip 节点，87 项 pin 一致、日志 enabled、物理输出关闭。

复用现有 `hdmi_live_session.py restore`，`gl-cold-a-close-20261014` 成功结束；会话 `play-9af94a3c` 报告 original_restored／buffers_released 均 true、errors 空，PYNQ 实查为正式 `guardianloop_pynq.bit`。随后停止采集／网页／HDMI 入口，四个目标 MainPID 均为 0，os.sync 已返回。未修改源程序、模型、SD 启动镜像或 PL 文件。

上述完成后才提交 5 秒延迟的 `systemctl poweroff`；关机接受回执与最终网络状态分别记录，不把网络不可达等同于串口已观测内核 halt。下次用户重新供电后仍需核对新 boot、采集回执和日志 completed，不能提前写为 A 组通过。证据为 `cold-a-shutdown-preflight.json`、`cold-a-ready-to-poweroff.json`、`cold-a-poweroff-request.json`。

## A 组首次冷启动结果：枚举通过，采集握手失败

用户按要求重新供电，报告接收器红灯灭；随后明确确认 Cyton 本体在 PC 档、蓝灯常亮。新 boot `998f4ce2-3ca0-409e-9d5d-73153d2a3198`，EyeChip 不接，FTDI 始终为 `1-1.4`／设备 4／D309LDXY，产品字符串为正常的 `FT231X USB UART`，固定串口和 ModemManager ignore 标签均生效。ModemManager 日志未再探测该接收器。

日志进程从 boot 约 14.90 秒启动、完整记录 180.34 秒、正常退出。记录期间接收器断开事件为 0，未出现前次 19／22 秒重枚举；正式／显示 PL 分别于 43.19／80.63 秒加载。原开机流程在 54 秒左右将正式采集切至 HDMI 包装入口，此服务切换来自原自启逻辑，不是本轮人为重启。USB 稳定不等于无线或应用协议通过：采集 23 次记录配置应答超时，没有八通道配置完成回执，packets_seen=0、无 telemetry。

这说明单独不接眼控也能复现采集握手失败，不能把接收器问题仅归为眼控占用 USB；也不能因本轮无断开就断言上轮 ModemManager 是唯一根因，因为接法与规则均不同。A 组期间未重启服务、未发额外诊断命令、未改软件／质量／模型／PL 文件。完整证据 `cold-a-boot-trace.jsonl` 和摘要 `cold-a-result.json` 已下载保存。

B 组仍待单独确认安全关机后，再在断电状态插回眼控，其他条件保持相同。不要在 A 组记录中途加眼控，不将热插拔和冷启动结果混为一组。

## B 组关机准备

用户再次明确授权安全关机。核对 A 组记录已完整结束并下载、boot 仍为 `998f4ce2-3ca0-409e-9d5d-73153d2a3198`、87 项 pin 一致后，执行原显示恢复流程。`gl-cold-b-close-20261014` 正常成功，`play-2240a644` 清理无 errors，正式 PL 已恢复、缓冲释放。

采集、网页、HDMI 入口和显示进程 MainPID 均为 0，os.sync 返回后才提交 5 秒延迟关机请求。启动记录服务保持 enabled，软件／模型／接收器设置和 SD 镜像未更改。证据 `cold-b-shutdown-preflight.json`、`cold-b-ready-to-poweroff.json`、`cold-b-poweroff-request.json`。请求接受与网络退出单独核对，不将其等同串口已观察内核 halt；B 组上电与结果仍待用户执行及日志确认。

## B 组首次冷启动结果及后续隔离探针

用户在断电状态插回眼控后重新供电，报告接收器红灯灭。新 boot `e388785e-8f99-4259-8722-dd777623c225`。完整 180.36 秒观察正常结束，EyeChip 始终未枚举；接收器于 7.312 秒断开一次、7.645 秒重枚举为设备 5，随后未再断开。两次 PL 加载在 43.27／84.71 秒；21 次配置回执超时、无八通道完成回执、packets_seen=0，无 telemetry。初次包含多个子命令的审计查询超时，重新以限时、保留部分结果的只读查询取得现场；未将这次查询超时解释成硬件复位或服务失败。

A/B 各仅一轮，不能量化故障概率，也不能从断开次数差异判定眼控导致 USB 断开。两组都表明：不论是否接眼控，接收器均未恢复采集；B 中物理插回并不等于 EyeChip 已进入正常 USB 工作状态。完整记录和摘要已保存为 `cold-b-boot-trace.jsonl`、`cold-b-result.json`。

在 B 日志 completed 之后，私有 `cyton_connection_check.py` 增加 `--start-only`，复用既有串口、read_for 和 parse_frames；不替换正式代码、不放宽任何生产门控。三项真实 Linux PTY 行为测试全部通过（1.171 秒）：开始／停止与计包、零回复保留为零、读取失败仍停止并恢复服务。随后用有限时诊断 unit 暂停正式采集，仅发 s／b／s，实际 3 秒收到 0 字节／0 包；未发送 V、v、d、无线频道修改或额外配置，未保存脑电样本。finally 与 ExecStopPost 恢复采集，unit 正常退出。不能把本次无流仅归因于 V 查询门控，也不能据零字节确定 UART、无线或 Cyton 的唯一根因。

接着准备独立的眼控换口检查：先暂停采集、释放接收器串口，再请用户暂时拔下接收器，将眼控移到接收器刚才的同一 USB Host 口；网卡、电源、网线和 HDMI 不变。这是热插拔端口隔离，单独记录，不混入 A/B 冷启动结果。未复位整板／Hub、未切换 PL。证据 `start-only-probe-tests.json`、`start-only-probe-result-b.json`、`eye-port-crossover-ready.json`。code-humanizer Guard 限制诊断复用原解析器，只在私有探针增加选项，并保证清理失败也尝试恢复正式服务。

## 眼控换到接收器口：正常枚举且 hello 握手成功

用户确认已换口，仍为 boot `e388785e-8f99-4259-8722-dd777623c225`，未重新供电、未切换 PL／驱动。EyeChip 现在位于 `1-1.4`（原接收器口）、设备 8，VID/PID=`2104:0124`，同一序列号 `CN033F74DTOB186P0822A00`。接收器此时已拔下，采集仍明确停止；原静态 HDMI home/menu 保持、物理输出 false。

设备初始为 power/control=auto、runtime_status=suspended。复用此前有限 hello-only 探针 `/home/xilinx/gl-shoot-ready-20261014-dNayYB/eye_init_probe`，先核对同次 boot／节点／PID／序列号／设备号，再执行一次原生握手：退出码 0，OPEN_CONTROL=0、HELLO_SEND=0（79 字节）、IN_TRANSFER=0（43 字节）、回复 op=03e8／seq=1／status=0，HELLO_ANSWERED=yes。设备自动恢复 active。未手工改 PM、未发 USB reset、DFU 请求、固件上传、校准或 PL 加载。

因此目前可确认该模组在 Z15 当前系统、当前 PL 和新端口上能枚举并完成真实 vendor/hello 通信，不是仅仅“节点出现”；不能把它写成三点标定、稳定注视数据或精度验收已通过。此次 auto/suspended 能正常唤醒，也不能继续把所有失败单独归因自动休眠。换口／实际重新插接后恢复，不足以唯一判定原物理口损坏，还需要反向接入接收器的端口对照。

下一步保持眼控在 `1-1.4`，请用户将接收器插入眼控原 USB Host 口。核对新节点后再启动采集；不要将当前主动暂停状态下的红灯灭当成新故障。证据 `eye-port-crossover-result.json`、`eye-port-crossover-hello.json`。

## 接收器反向换口及同时通信检查

用户确认接收器插好；仍为同一 boot `e388785e-8f99-4259-8722-dd777623c225`。接收器现在位于 `1-1.2`（原眼控口），`0403:6015/D309LDXY`、设备 15，固定串口入口仍正确指向 `/dev/ttyUSB0`；眼控保持 `1-1.4`、设备 8、正常 `2104:0124`。接收器插入期间，内核记录约 874～879 秒间多次断开／重枚举，此时采集尚未启动；审计时最后一次连接已经保持约 46 秒。这些插入阶段事件不能记作采集或眼控探针触发的断开，也不能据此确定是手动插接过程还是端口电气问题。

核对同次 boot 与两个精确序列号后，仅启动原 `guardianloop-cyton.service`，成功运行 PID 6667／NRestarts=0；没有换 PL、改源程序、重置 USB、重启 Z15 或启动标定。服务确认固定串口存在，但多次配置应答超时，没有八通道配置完成回执。四个间隔 8 秒的状态样本均为 `CHANNEL_CONFIGURATION_UNCONFIRMED`、packets_seen=0，不能算脑电已接通；status 文件在等待阶段未逐次刷新，其年龄不是最新脑电延迟。此次冷启动的日志本来就没有恢复旧标定，不将当前 0/15 解释为测试过程中又丢失了一次有效标定。

采集服务运行期间，再执行同一有限原生 eye hello 探针：OPEN_CONTROL=0、发送 79 字节成功、接收 43 字节成功、回复 status=0、HELLO_ANSWERED=yes。说明同时插入接收器并运行其原采集入口时，眼控仍能完成真实握手；不等于持续注视数据／三点标定通过，也不能声称两个设备的完整功能已经联用。该轮启动后的内核记录没有新增 USB 断开，接收器仍为设备 15、眼控仍为设备 8。

本轮保留静态 HDMI 和原采集重试，不对脑电质量或 Ch4 做处理，不发声、不闪烁、不使能轮椅。下一步可在不动 Z15 和 USB 的条件下，只对 Cyton 本体做一次关机后 PC 档重新上电，观察正在运行的原采集重试能否收到应答；需由用户执行，尚未执行或验收。证据 `receiver-reverse-port-before-start.json`、`receiver-reverse-port-service-start.json`、`receiver-reverse-port-coexist-check.json`、`receiver-reverse-port-packets-check.json`。

## Cyton 本体重新开机后：真实收包与眼控握手共存

用户确认仅 Cyton 本体关机后 PC 档重新开机。Z15 保持同一 boot，接收器仍为 `1-1.2`／设备 15，眼控仍为 `1-1.4`／设备 8，未重启 Z15、未切换 PL、未改软件／门限／模型或重新标定。

首轮核查发现原采集遇到 `Cyton firmware did not confirm the v3 command contract` 的 ValueError，触发 systemd 一次自动重启。原代码将未匹配版本的回复作为普通 ValueError，而等待逻辑只接住 TimeoutError 和 CytonConfigurationError；这是明确的重连行为缺口，但本轮没有放宽版本契约或声称已经修复。出错时的实际回复未被记录，不能断言是开机横幅混入、无线失败文本或固件版本不兼容。

复用现有有限 `cyton_connection_check.py` 查询 s、无线状态、频道、V，结束自动恢复原服务；未发 v／d、频道改写或 USB reset，不保存脑电样本。该轮 unit 已完整退出、Result=success／ExecMainStatus=0；两个无线查询各为零字节，但 V 收到 `v3.1.1$$$`。曾在 unit 仍 active 时读到上一轮 start-only report，已另外保留为中间记录，不能将旧 report 当成本轮查询结果。最终结果以 `after-body-restart-query-complete.json` 为准。

最终生产服务恢复后，日志确认八通道配置 8/8、CYTON_STREAM_STARTED。前一个服务正常停止时已累计 19,685 包，说明不能把恢复全部归因于后续查询探针；本体重新上电、原服务自动重启及有限查询都发生在观察过程中，尚未作唯一因果拆分。

实际连续收包期间再次执行同一 eye hello，发送 79 字节、接收 43 字节、status=0、HELLO_ANSWERED=yes；其前后两个采集状态快照分别累计 16,000／20,000 包，dropped_packets=0、sequence_gaps=0、malformed_bytes=0。两个包计数来自按窗口刷新的状态快照，不用这两个快照的壁钟差计算瞬时采样率。当前采集 PID 9247／NRestarts=0，静态显示 `play-13b3fbf8` home/menu 持续更新，USB 设备号均未变化。

本轮验收范围是“实时收包和眼控原生握手同时成功”，不是“持续眼控注视／三点标定／完整页面控制已验收”，更不是脑电质量或 SSVEP 识别通过。依用户要求，未处理 Ch4 或其他质量问题，未取消质量门控；保留正在工作的采集与静态 HDMI。后续先确认用户在 HDMI 前可以做眼控定位／三点标定，再启动原眼控流程，不以 hello 代替注视输入验收。

本轮预读 code-humanizer 并复用既有查询／握手工具；没有新增生产采集实现或为恢复中的会话追加代码补丁。证据 `cyton-body-restart-coexist-check.json`、`after-body-restart-query-start.json`、`after-body-restart-query-result.json`（中间状态）、`after-body-restart-query-complete.json`、`after-body-restart-post-query-status.json`、`live-packets-and-eye-hello-together.json`。

## 实际定位启动及后续连接中断（标定未完成）

用户确认方便在 HDMI 前标定。只读预检为同次 boot、原静态会话 `play-13b3fbf8` home/menu、物理输出 false、无眼控进程；采集累计 66,000 包。通过既有 9119 `/api/player` 的 `eye_start` 启动原 EyeInputs／is4-calibration 相对眼控定位，取得 applied 指令回执，未加载 PL 或重启采集。

原生程序进入 positioning，实际收到约 42.3～46.3 cm 的距离和双眼／瞳孔检测比例；最早样本双眼 94%／97%、瞳孔 74%／74%，随后右瞳孔降至 0%，故尚未确认位置或发送第二次 eye_start 开始三点。用户已收到先正对中央稳定坐姿的提示，没有把三点标定或中／左／右快速验收写作完成。

下一次查询发现眼控为 failed／native_exit_-4、尚无 calibrated 或 selection；最后 native packet monotonic 1601.34。Worker 既能包装原生 error 事件，也能包装子进程返回码，尚未取得 worker.log，不能仅凭 -4 判断为 libusb NO_DEVICE 或 SIGILL。该次采集状态为 packets_seen=86,787、dropped_packets=0、malformed_bytes=50；不能继续沿用此前“坏字节为零”描述新时段。

随后读取 worker.log 的 SSH 建连报 protocol banner EOF；独立 22／9102／9119 三端口探测均超时、两次 ping 均超时。Windows `Get-NetAdapter` 显示管理以太网（InterfaceIndex 6）为 Disconnected，电脑仍配置 192.168.2.89/24，邻居 192.168.2.99 的已知 MAC 00-0A-35-00-8B-87 为 Stale；WLAN 仍 Up，但不在 Z15 的 AP 子网。用户仅确认 HDMI 仍有界面，未确认该界面是否继续刷新，不据此断定整板正常或重启。未擅自重启、改网络配置、重置 USB 或切换 PL。

当前阻碍是管理网线物理链路断开，需先检查／插紧电脑与 Z15 的网线两端，再恢复只读查询，取眼控 worker.log 和内核事件。不能把本轮中断归因于脑电质量／眼位、两个 bit 覆盖或确定的供电问题。保存 `eye-three-point-before-start.json`、`eye-positioning-start.json`、`eye-positioning-readiness.json`；SSH 失败前没有取得 `eye-positioning-interruption-audit.json`，不要引用不存在的日志文件。

## 网线插紧后恢复管理连接及定位（后续现场）

用户回复网线已插紧，22／9102／9119 端口均恢复响应。Z15 仍为同一 boot，uptime 约 5889 秒，并未在管理中断时整板重启。内核确认第一次眼控 USB 断开重枚举在 boot 1601.286 秒，早于以太网首次 link down（1655.195 秒）；不能把第一次眼控 USB 中断归为管理网线断开导致。此前仅有 -4 的包装错误，现在补充了对应时刻的真实 USB 断开事件，但尚未确定触发断开的唯一原因。网线恢复前后，另见接收器在约 5443／5446 秒断开重枚举；两类事件时间接近仍不够证明共同电气原因。

新读取到的后续原生会话记录表明：在管理连接不可用期间，另有两次眼控三点采样均接受；当前失败会话保留一次中／左／右快速检查 3/3 通过记录，并曾有 3568 个 valid_samples，后于 boot 1919.722 秒 USB 再次断开。对应 worker.log 为 `usb_bulk_error code=-1`。所以“首次定位后尚未开始三点”的描述只适用于首次失联前观察，不能用于否认随后本地完成的标定。此次没有重放 gaze.csv、没有把历史有效样本作为当前输入。三选区检查不作为准确率估计。

恢复连接时眼控为 `1-1.4`／设备 21／正常 0124，接收器为 `1-1.2`／设备 23；采集 PID 11393 仍运行、累计 100,000 包。原显示会话仍在，当前眼控 failed，物理输出 false。仅通过既有 API 再发一次 eye_start 重新定位，没有重启采集／Z15、没有改 PM／PL／程序或自动开始三点。指令 applied 后连续 4 次定位状态均 connected=true、无 error、last_packet 持续更新，但左右眼检测及瞳孔可用均为 0%，距离未知。同期脑电增加至 116,000 包、malformed_bytes=0、dropped_packets=0。

这一步验收到“重新打开定位并收到连续原生检测状态”，未验收当前双眼可见或标定成功。接下来需要用户正对 HDMI 坐稳，使双眼检测／瞳孔读数出现后再主动确认位置；不因当前 0% 状态重复复位设备或擅自进入采样。证据 `ethernet-reconnected-eye-audit.json`、`eye-positioning-after-ethernet-restored.json`。

## 用户确认位置后发现控制超时和串口等待（未启动标定）

用户回复位置就绪后，预检发现定位已 failed／native_exit_-7，未进入三点。只按原 API 重建一次眼控会话，未复位 USB、切换 PL、重启采集或整板；约三秒内初始化再次超时，故没有发送确认位置／开始三点的第二条指令。此时设备仍为正常 2104:0124，但设备号已从 21 变为 24：内核记录 boot 6126.973 秒断开、6127.305 秒重枚举。不能把设备号变化等同于用户一定拔插，触发原因仍未确认。

已取得中间一次原生日志：初始化和订阅先成功，随后 `relative_timeout_keepalive` 的订阅发送返回 `LIBUSB_ERROR_TIMEOUT (-7)`；后续两次新会话 worker.log 为空。复用 hello-only 探针独立验证，结果为 OPEN_CONTROL=-7、退出码 3，尚未到 hello 的收发阶段。因此当前阻碍不是单纯坐姿／无瞳孔检测，也不能靠忽略 0% 开始标定。

同时发现不能继续将采集服务 active 等同于正在收包：PID 11393 未变，包数停留 177,884，状态 STREAM_IDLE、年龄先为约 240 秒、下一轮约 284 秒。`/proc/11393/wchan` 明确为 `tty_wait_until_sent`，日志最后进入 CYTON_NO_PACKETS_RECONNECT；原 `write_command` 包含无应用层截止时间的 `termios.tcdrain(fd)`。这是串口发送等待导致重连流程无法前进的具体证据，不是脑电质量或旧窗口计算积压的证据。尚未实现／上线有界发送修复，不得写成已解决；硬件/驱动发送停滞本身的唯一原因也尚未确认。

当前停止继续标定或无界软件重试。需要先恢复眼控实际控制通信；可请用户只对眼控 USB 做一次拔下等待后插回，保持接收器／网线／供电不动，重新检查 USB 事件和控制应答，再决定是否开始三点。接收器发送等待另外跟踪，不能用改模型或放宽质量阈值处理。本轮未擅自单设备 reset、复位 Hub 或重启板卡。证据 `eye-position-confirm-preflight.json`、`eye-position-ready-reconnect.json`、`eye-position-ready-timeout-diagnosis.json`、`eye-ready-service-stall-check.json`。

## 用户重新供电并重插眼控后的新开机现场

用户主动重新供电并重插眼控，boot 变为 `aa3c4a18-68fe-42a8-8358-67ca34c083da`。本轮先做只读核查：22／9102／9119 均响应，启动合同 ready、原采集和控制网页自启，新的静态 HDMI 会话 `play-839c274c` home/menu、物理输出 false。接收器为 `1-1.2`／设备 10／D309LDXY，眼控为 `1-1.4`／设备 11／正常 2104:0124。接收器在 boot 约 11～19 秒间断开重枚举，发生在正式 PL 的 45.10 秒和显示 PL 的 81.03 秒加载之前。采集持续等待配置回执、packets_seen=0；没有将 active 服务写成已收通，不沿用前一 boot 的计数或标定。

确认无既有眼控会话后，复用有限 hello-only 探针，OPEN_CONTROL=0、79 字节发送／43 字节接收／status=0／HELLO_ANSWERED=yes。眼控最初 auto/suspended，仍能正常唤醒通信。随后只通过原 API eye_start 启动定位，收到真实双眼及瞳孔状态，距离约 39～47 cm；用户前一轮已明确确认位置就绪，因此提示跟随中央／左／右圆点后发送位置确认请求。原 confirm_position 新鲜双眼／瞳孔门控保持不变，未放宽比例或自动绕过门控。

三点分别采到 253／146／111 个样本且 accepted=true，原生输出 calibrated=true，并继续收到实时相对注视。快速检查中央目标 1 选为 1，通过一次；随后左／右尚未完成，state 保持 verification、control_enabled=false。最终观察 samples=5574、valid_samples=2936、stale_samples=595，没有错误或新 USB 断开记录；不能将“标定模型已生成”写成“三选区全部通过／正式眼控已启用”。头部／瞳孔状态有波动，也有陈旧样本，未据此改识别门限或宣称精度。

同期 Cyton 未收新包；后续 MainPID 从 765 变为 5703、NRestarts=1。状态曾更新为 SERVICE_STOPPED_OR_STREAM_TIMEOUT，但取最近 journal 超时，不能确定这次退出与上一 boot 的版本校验 ValueError 是同一原因。没有手工重启采集、修改源码、复位 USB／Hub、切换 PL、重新烧写或使能轮椅。已询问 Cyton 本体 PC 档／蓝灯及接收器红灯，当前尚未取得回复。保留现有眼控验证会话，请用户完成左、右各一次确认；采集连接需要单独验收。

证据 `repower-eye-replug-audit.json`、`repower-eye-hello-positioning.json`、`repower-three-point-progress.json`、`repower-eye-quick-check-progress.json`、`repower-eye-left-right-check.json`、`repower-cyton-retry-audit.json`。

## 用户补开 Cyton 后的真实联用核查

用户明确回复“刚才忘开了，现在开了，红灯亮的，眼控正常”。这条现场事实解释本 boot 初始缺少新数据的条件，不能再把那段未开机的等待当成采集连接故障验收；它不否定先前其他 boot 的真实 USB 断开或 tty_wait_until_sent 证据，也不证明历次故障都由忘开机造成。

仅做只读核查，无手工重启、额外查询命令、重新标定或源码修改。原采集自动完成 firmware v3.1.1、八通道配置 8/8，并启动真实流；PID 5703 未变。日志也记录两次 PRIMARY_STREAM_RESET／STREAM_TIMING_GAP（12,819／19,690 包），校准保留字段 true，但本轮 fatigue_windows=0、sqi_channels=0，不能把空基线写成已保留有效 15/15。时序间断仍是待跟踪的连续性问题，不是丢包计数非零，不应为尽快拍摄而隐藏或关闭该检查。

眼控已经完成中央／左／右各一次，3/3 通过，state=selection、calibrated=true、control_enabled=true，实际进入视频页。左区确认从该页呈现到确认约 123 秒，可能包含用户等待或有效输入间断；不作为识别响应速度／准确率估计。后续定位状态与 samples 持续更新，无 error；这些只读样本时没有新 valid_samples、valid=false，故不能声称每个观察时刻都有有效眼位，也不因此重启或重新标定已经通过的会话。

第二次约 8 秒连续性观察中，telemetry 包计数 35,439 → 36,489 → 37,429，文件新鲜度约 0.09／0.12／0.41 秒；dropped_packets=0、sequence_gaps=0，状态中 malformed_bytes=0。眼控 samples 同期 16,966 → 17,242 → 17,478，仍为正式 selection，无错误。窗口 status 的包计数更新较慢，连续性以独立新鲜 telemetry 为证；不将 status 文件年龄等同实时计算延迟。本轮记录只保存计数及状态字段，没有另存原始 EEG 数组。物理输出始终 false，没有启动闪烁、声音或轮椅动作；脑电质量／Ch4 按用户要求未调整，现有质量门控未取消。

当前确认的是“真实 EEG 收包与已标定眼控原生程序同时运行，正式眼控页可操作”，不是全系统驾驶或 SSVEP／疲劳识别验收。保留当前会话，不因曾有 0 包或当前移开视线无有效眼位反复重校准。证据 `cyton-now-powered-eye-live-coexist.json`、`cyton-now-powered-coexist-continuity.json`。

## 用户进入 SSVEP 方向页但未闪烁的诊断

用户询问为什么进入 SSVEP 界面不闪烁。本轮仅只读诊断，没有发 arm／hdmi_start 或启动刺激。boot 与 HDMI 会话未变，方向页 drive／page_id=9、reading=false、无疲劳锁定，眼控 selection／快速检查 3/3 已通过。四角状态 active=false、preparing=false、error=null，扫描报告 count=0、识别 runtime idle；不能记为“闪烁已经启动但显示闪退”。

预检同时给出两项未满足条件：先点击“启用虚拟方向”，以及 EEG 输入 nonfinite_or_adc_rail。`prewear.hdmi_preflight` 明确区分进入方向页、direction_armed=true、输入 ready 与已启动 stimulus；手机页另有主动确认及“开始 HDMI 四角测试”按钮。进入 drive 不会自动开启闪烁，原程序没有因此加载另一份 PL 或重做标定。

当前状态的 Ch8／O2 adc_near_rail_ratio=1.0、滤波后 flat_ratio=1.0／p99_abs=0，O1／Ch7 未显示相同饱和。`ssvep_acquisition.consume_packets` 对原始 counts[6:8]（O1/O2）计算量程饱和标志，故本次 SSVEP 硬输入拒绝与之前允许忽略的 Ch4 断线不是同一项。不能把“忽略 Ch4／当前先不处理脑电质量”的授权扩大为接受饱和 O2 或伪造 input.ready。连接收包仍在进行（telemetry 129,377 包、新鲜度 0.165 秒），输入已到达不等于可做 SSVEP 识别。

本轮未更改界面、模型、质量门控、标定、PL 或驱动，没有启动闪烁／电机。后续需明确选择修复真实 O2 输入后走原识别流程，或另行授权仅显示的短时闪烁诊断；后者不能标成真实脑控或启用轮椅。证据 `ssvep-no-flash-live-audit.json`。

## 后续经授权更新：方向页自动显示与返回路径

用户随后明确要求方向页不因脑电不合格而不闪烁，并允许备份更新、显示恢复和一次重新标定。新的仅显示扫描与真实识别分离，中央标准眼控卡片改为返回主页，视频翻页页中央也改为返回主页。具体实现、备份、测试和剩余人眼验收见 `DIRECTION_AUTO_DISPLAY_20261014.md`。

用户离开、关闭 Cyton 并主动重新上电后，在 boot `4ed5747d-eda3-4c9d-88f8-9b423f1894c5` 完成安装和网页恢复。初次网页临时 unit 停止后消失，普通 systemctl start 失败；部署恢复脚本已修正为按原命令重建临时网页服务。此故障与采集或 USB 并无已证实因果关系。采集 PID 778 未变，87 项启动 pin 验证通过，正式脑电 57 项文件未改；结尾为静态主页、四角停止、眼控未自动标定、物理输出禁用。没有宣称历次 USB 故障已解决，也没有把仅显示闪烁当成真实 EEG 识别。
