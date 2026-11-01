# 复位后恢复统一 HDMI（2026-10-11）

## 授权与实际操作

用户明确允许恢复统一 HDMI，加载已校验的 eye_wifi.bit；静音、不闪烁、
实体轮椅禁用，不修改模型或 SD 启动镜像。继续使用以太网访问
192.168.2.99，wlan0 保持 FPGA 热点 192.168.50.1，没有连接手机热点。

只读核查 boot_id 为 `0e44bc51-655b-4974-b982-d6689fa20948`。
正式 ARM 发布清单 SHA256 为
`38237fbb34b6a5d3399cb37df20270580e55fecf0dc8ef7d851678c5380ac105`，
56 个文件及统一入口 boot-pins 均匹配。复位后原统一入口、网页和看护
未运行，状态文件仍属于上一次开机；没有采用旧显示进程或旧校准。

启动现有 guardianloop-hdmi-entry.service：按既有受校验 hdmi_boot.py
恢复本次开机的软件入口，保留旧会话诊断，重新启动采集，开启统一网页
和恢复看护。该入口本身没有自动加载 PL、闪烁或启动实体控制。
随后通过现有接口新建静音 sd02 视频显示会话 `play-fb6f1af0.service`。

显示 PL：`/home/xilinx/tobii_z15/overlay/eye_wifi.bit`。
bit SHA256：`8b52892466a1b4d025c5c693a951727ae6215e57ca3e5fa0dedaa2a1d510d50f`。
hwh SHA256：`5dcfe537c6793f5b18b47550f73078ab8d73500888e585037a707c8be1ebacef`。
既有失败恢复目标为正式 guardianloop_pynq.bit；本轮初始化成功，未触发回退。
显示为用户控制会话，没有自动到期；本轮没有更改正式源码、模型、启动镜像。

## 已确认与尚未验证

恢复后入口和媒体状态均属于当前 boot。6 次只读采样覆盖约 15.87 秒，
显示帧号由 793 增至 947，持续 playing。采集 PID 2497、显示 PID 2662、
统一网页 PID 2501、恢复看护 PID 2499 与原监测网页 PID 690 均未变，
NRestarts 均为 0。全程 silent=true、direction=stop、direction_armed=false、
stimulus_enabled=false、physical_output_enabled=false。最终再次核查
正式文件和 boot-pins，无不匹配。

启动自检 state=ready，verified_files=56。Cyton USB 接收器存在，但
packets_seen=0、calibration_current=0、STALE_EEG，且没有本次开机的
校准文件；界面正确显示 no_data，不输出可信情绪、疲劳或方向结果。
用户尚需佩戴并开启 Cyton，再验证收包、首次校准和真实 SSVEP。
这不是对真实脑电稳定性、屏幕目视效果或最低 16 fps 的通过结论。

证据：`phone_video_upload/output/hdmi_resume_20261011/audit-145049.json`。

## 用户佩戴开机后的只读预检

用户随后确认已佩戴并开机。此时完整收包已开始：最终所见 packets_seen
为 34574、sequence_gaps=0；采集 PID 2497 和显示 PID 2662 均未重启。
但多次遥测的 625 行原始、滤波后样本中，CH1/F3、CH3/C3、CH4/C4、
CH6/T8、CH7/O1 始终全零，其余三个通道有变化。质量不满足固定八通道
和 SSVEP 所需 O1/O2 条件，首次校准仍为 0/15，不能启动真实闪烁验收。

另有 PROCESSING_BACKLOG：累计队列延迟峰值 524.32 ms，10 个过期包
被丢弃，运行诊断中 primary_stream_resets=2；此数字不是服务重启次数，
也不能解释为已经完成的校准被清零。最终状态还有 PRIMARY_WORKER_BACKLOG。
当前通常队列延迟已回落至约 5–28 ms，不能仅据平均 CPU 推断积压已解决。

源码配置仅在采集启动时发送，等待晚开机 Cyton 的重试仅发送单字节 b。
初始配置发生在 Cyton 尚无完整包的阶段，晚开机后未重新下发八通道配置。
配置未生效是应优先核验的解释，尚不能仅凭零值断定具体硬件或接线原因。
本轮没有重启服务、改标签/门槛或向串口发送额外配置；下一步需得到
短暂暂停并重配采集的授权，不要求用户先摘帽或盲目调整电极。

预检证据：`phone_video_upload/output/hdmi_resume_20261011/worn-precheck-150113.json`。

## 授权后的八通道重配

用户允许暂停采集约 30–60 秒，重新下发并核验配置后恢复；不改模型、
质量门槛或 PL。独立诊断目录为
`/home/xilinx/gl-cyton-channels-20261011-yEjyLu`，只使用标准 EEG 配置和
寄存器查询，没有发送 v 复位、测试信号或射频改频命令。诊断由 systemd
管理，60 秒运行上限，并先设独立恢复采集的 75 秒保护 timer。

回读确认原 CH1/3/4/6/7SET=E0（关断位为 1），CH2/5/8SET=68。
因此五个零值通道实际处于关闭状态，不只是软件 SQI 判断接触不良。
依次发送 x1060110X 至 x8060110X，八个独立成功回执全部收到；回读
八通道 CHnSET 均为 68、BIAS_SENSP/N 均为 FF、MISC1=00。
字段和查询命令按 [OpenBCI Cyton SDK](https://docs.openbci.com/Cyton/CytonSDK/)
核查；原配置为何形成 E0 的具体传输/解析过程尚未被直接捕获，不能把
“服务先起、设备后开”这一解释写成唯一已证实根因。

finally 恢复采集成功，停止独立恢复 timer；当前采集 PID 17866。
正式服务重新完成初始化后，八通道原始/滤波遥测中已无全零通道。
HDMI 会话和 PID 保持 play-fb6f1af0 / 2662，静音、无闪烁、实体输出禁用。
正式发布 56 文件及 boot-pins 再次无不匹配。没有修改正式源码或基线门槛。
恢复时同一次开机的部分 SQI 进度保留，但此前疲劳基线没有完成，不能
称为恢复了一份已经完成的校准。

八通道完整输入后仍观测到 PROCESSING_BACKLOG，最大读队列延迟约
1196.8 ms、过滤耗时峰值约 860.7 ms，62 秒诊断时累计流重建 9 次、
丢弃过期包 555 个。校准进度由 2 增至 3，保留而非清零。
通过现有 home 指令切至静态菜单（回执 applied），不停止 HDMI 或采集。
随后约 15.14 秒四次观察中，首次校准推进 10→11→12/15，零值通道仍无，
流重建维持 9 次未新增，后三次读队列延迟约 7–8 ms。此短观察支持
先用静态菜单完成校准，不足以宣称视频与完整脑电并发负载已合格。
F4 在这些窗口被标为 adaptive_outlier；O1/O2 可用。质量门控继续保留。

证据：channel-recheck-report.json、after-recheck-150623.json、
static-menu-precheck.json，均在上述本地证据目录中，不含原始脑电样本。

最终只读快照 final-recheck-status.json：疲劳首次校准已达 15/15，
calibration_retained=true，八通道仍无全零，采集持续 active/NRestarts=0，
独立恢复 timer inactive，流重建累计数仍为 9。但此时结果门控为
PRIMARY_WORKER_BACKLOG / valid=false，不能把校准完成等同于识别或
SSVEP 验收通过。静态主菜单没有完全消除后台长尾；视频只是减负试探，
尚不能归因为唯一瓶颈。本次授权的重配和恢复已完成，未启动闪烁，
后续应解决后台计算时效或独立核验 SSVEP 入口，不能要求用户盲目重校准。
