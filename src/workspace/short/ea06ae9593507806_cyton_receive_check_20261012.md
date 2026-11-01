# 2026-10-12：完整 40 秒纯收包与主动重新校准

用户确认 Cyton 已开机并允许纯收包。随后要求同时重启校准，并确认
已经佩戴固定八通道、坐稳。正式采集独占串口，测试期间临时停止，
纯收包结束恢复后再执行用户要求的校准重启，未启动闪烁或实体轮椅。

## 范围

沿用 diagnose_stream_transport.py、stream_transport_session.py，无新源码
修改、驱动安装或 PL 加载。诊断与正式采集使用同一十包批传递 reader，
不运行模型，不保存原始 EEG；仅保存 framing/sequence/收包间隔计数。
使用新的隔离目录和当前发布／PID／boot 指纹，未重用上一轮计划。
正式发布是 guardianloop-stream-status-repair-20261012。

隔离目录：`/home/xilinx/gl-stream-transport-20261012-PTvQEN`。
单元：`gl-stream-transport-20261012-PTvQEN-receive-60a3.service`。
固定串口：`/dev/serial/by-id/usb-FTDI_FT231X_USB_UART_D309LDXY-if00-port0`。

诊断两个板端软件测试通过。子命令采用已有 75 秒时限，包含模块导入，
留出完整 40 秒接收。Transient unit 的 ExecStopPost 启动正式采集，
并有独立 150 秒备用恢复 timer。RuntimeMaxSec=130，KillMode=control-group。
采集 RuntimeDirectoryPreserve=yes；停止前检查串口 owner 均属于原采集
cgroup，不把 fork 继承的四个文件描述符误认成四个独立采集器。

## 完整接收结果

正常结束，exit=0、completed=true、error_type=null：

- 接收 40.02913 秒，9,970 包，约 249.0686 包／秒。
- malformed_bytes=0，sequence_gaps=0，first_fault_after_s=null。
- 最大接收间隔约 172.892 ms，超过 250 ms 的间隔为 0。
- reader 交付年龄最大约 8.027 ms。

这轮的 framing 接收检查通过，不是脑电识别准确率、长期无线稳定性
或多任务完整负载通过。前一轮 33.38 秒不完整测试的异常记录保留。
正式采集测试前有累计 1,051 异常字节，不能把累计计数直接解释成当前
仍持续坏包；本次重启后的新计数也暂保持异常字节／序号缺口为 0。

正式采集自动恢复 PID 9169；网页 PID 19876、媒体网页 PID 19881 不变。
确认正式采集 active 后才取消备用恢复 timer（最终 inactive）。

## 按用户要求重新校准及平线核查

使用已有明确确认的 wear_new 接口，不直接写校准数值／交换标签。
命令 85cef0343e4fb1413d3a6eb42d743496 从 queued 变成 applied。
旧 15/15 基线因本次用户要求而清除，属于主动重校准，不是异常丢失。
恢复后观察从 1/15 进展至 7/15、8/15、14/15，最后两次状态均为
15/15、state=prediction，确认重新校准完成。过程中未再次归零。

用户报告 CH1/CH3/CH4/CH6/CH7“平线”时，测试期间正式采集停止，页面
没有新鲜波形。恢复后逐通道读取统计，没有保存波形样本：这五通道
都有变化，625 行快照各有 621 左右不同的滤波数值，首个快照滤波标准差
约 16–85 µV。后三次快照所有通道 flat_ratio 约 0（O2 一次 0.002004），
没有 flatline 理由，因此没有证据支持这些通道实际全部平线。
不能据此断言用户看到的图形问题一定由暂停或纵轴缩放导致；若刷新后
仍显示平线，应继续核对界面。未人为放大信号或放宽平线检查。

当前 CH4/C4 出现幅度／削顶原因，质量曾降权，之后一窗恢复 usable。
CH5/T7 和 CH2/F4 偶有幅度提示。接收计数无异常不等于电极质量全部
合格；通道质量仍沿用真实门控，不以重新校准掩盖接触问题。

14/15 时曾出现各通道幅度／削顶异常，CH4 整窗还带 flatline 理由；
随后这段异常自然离开分析窗，15/15 的两个新鲜快照均无 clipping／
flatline 理由，flat_ratio 约 0–0.002。最新各通道滤波标准差约 9–16 µV，
峰峰值约 48–105 µV；CH4 仍带 adaptive_outlier 降权理由。没有通过
修改阈值撤销这些检查。clipped_rows 累计 7,045 在末两次快照没有增加，
不能把该累计数当作最新窗口仍削顶。

末次三快照年龄约 0.44–0.85 秒，输入在快照发布时年龄约 9.76–36.72 ms，
reader 队列等待约 6.94–34.31 ms；主窗口计算记录约 160.29–329.83 ms。
快照年龄、reader 交付和窗口计算含义不同，不相互代替成延迟结论。

## 恢复验证与证据

boot 未变，正式 57 文件和 79 boot-pins 无指纹差异，PL 一直是
guardianloop_pynq.bit，本轮没有重新烧录。用户要求新基线后 wear／
calibration 文件发生预期改变，不能再把原 15/15 指纹当作本次验收要求。

证据：`phone_video_upload/output/stream_transport_isolation_20261012/`。
包含 before、stage、linux-tests、launch、receiving-state、pure-receive-result、
recovery-timer-cancelled、recalibration-request、post-recalibration-channel-check、
after-restoration-and-requested-calibration。只有计数和幅度／质量摘要，
不含新原始 EEG 文件；wear ID 和个人质量统计仍为私有工程证据。
补充 final-calibration-progress 和 quality-after-calibration-progress 记录
14/15 的暂时拒绝与 15/15 的恢复，不隐去中间异常。

此次重新校准已经完成，不再次自动重启。若波形显示小，先用滤波后
视图和合理纵轴核对；如需要调整接线／电极，先关闭 Cyton。四频＋休息
尚未在此次新佩戴上测试，HDMI 目前不运行，启动显示需要单独按实际
请求加载已有显示 bit，实体轮椅仍禁用。

## 后续 CH4 只读诊断

用户询问 CH4 持续很差的原因。三次新鲜快照显示 C4 交替出现 amplitude、
clipping／transport，未见最新段 flatline；串口仍零坏字节和零序号缺口。
这里的 clipping／transport 来自软件工程幅值边界，不等同 ADS1299 ADC
饱和或无线坏包，实际 adc_near_rail_ratio 八通道均为零。

另一快照中原始 C4 的 50 Hz 在所定义频段内占比约 0.999463；其他多个
通道也超过 0.98，因此不能仅据此归因 C4 局部电极或宣称参考／BIAS
已接错。电极／线缆接触和公共参考接触需要现场核对。

还确认自适应基线可造成持续降权：C4 本次 p99 校准中心约 115.834 µV，
当前段约 30.354 µV，负向偏差归一化后绝对值约 7.64989，略超过本次
阈值 7.64956。源码对 p99 幅度下降也做双侧偏离处罚，只有工频下降
被特别豁免。因此较大幅度已经恢复时仍可能带 adaptive_outlier；这与
真实的大幅波动是两层原因。该段只是整窗的一段，不能忽略窗内其他
异常，也不能只凭幅度变小就断言脑电质量全面改善。

本轮只解释原因、保存摘要，没有修改门限、交换通道、重新校准或操作
硬件。证据位于 `phone_video_upload/output/ch4_quality_diagnosis_20261012/`，
recent-quality 和 interference-and-baseline。硬件排查建议核对 OpenBCI
官方 minimizingNoise / EEGSetup 文档中的稳固电极、参考、BIAS 与远离
电源线建议；调整接线／电极前按既定流程关闭 Cyton。

## 按用户再次要求重新校准与同步尖峰核查

用户确认已经佩戴好并明确要求重新校正。使用已有 wear_new 接口，
命令 4579fac83ccf13fe6f260c3e25e0de59 已 applied；未直接写基线数值。
本次观察到校准从 4/15 进展至 15/15，C4 自身参考也完成 15/15。
新 C4 p99 校准中心约 34.201 µV，区别于此前受较大幅值影响的基线。
之后三个新鲜快照 C4 质量为 0.9672、0.9631、0.9507，均 usable、
reasons=[]。本次没有修改 CH4 算法、放宽质量门限、模型或正式 PL。
已有七项 SQI 测试通过；重新校准完成不代表波形没有伪迹。

用户截图中的重复尖峰也出现在读取的现有显示数据中。三个 625 行、
125 Hz、约 5 秒快照，CH1/CH2/CH5/CH7 的滤波后峰时刻基本同步，
差异约 0–16 ms，各通道峰间隔中位数均约 0.68 秒。CH4 未达到本次
临时工程峰检测条件；这不是临床尖波检测，也不是心率测量。
快照相互有重叠，不把它们当作三个独立记录或长期稳定性试验。

三次快照均 state=prediction、calibration_current=15，八通道 usable。
CH2 和 CH5 仍有 amplitude 提示。malformed_bytes=36、sequence_gaps=1、
primary_stream_resets=6 在这三次观察中未增加，最后中断原因仍是
EXPLICIT_NEW_WEARING。因此未发现重复尖峰伴随新的坏包或滤波重置，
但这不排除观察前的链路异常，也不证明信号全部干净。

同步、近周期尖峰提示共同伪迹；心电混入与周期性电气干扰是待核验
假设，尚无同步 ECG／脉搏证据，不能确定来源。可先在不动电极和
线缆的情况下，对比手腕脉搏节奏与波形尖峰节奏；节奏相近仅作线索，
不能替代同步测量。未新增削峰、平滑、ICA 或生产滤波修改。
心搏伪迹可能影响 EEG 的依据见 MNE 官方 artifact detection 文档：
https://mne.tools/stable/auto_tutorials/preprocessing/10_preprocessing_overview.html

证据：`phone_video_upload/output/ch4_recalibration_20261012/`，含请求、
校准进展、校准后检查和 spike-timing-check。仅保存幅度、时间和状态
摘要，没有新原始 EEG 波形文件。正式 57 文件指纹未变；本次主动
更新后的校准与 wear 文件指纹已记录，不再恢复旧的噪声基线。

## 继续核查：脉搏线索、软件对照与尚存干扰

用户随后确认手腕脉搏节奏与重复尖峰节奏接近。结合多通道同步、
约 0.68 秒间隔，心电混入的可能性升高，但没有同步 ECG 记录，
不能确定来源；亦不能把波形尖峰解释为身体异常。

既有 test_cyton_sqi 与 test_telemetry_json 共 12 项通过。另做本地
45 秒合成输入对照：250 Hz、八通道 8–15 Hz 正弦、25,000 µV DC、
各通道 120–1,400 µV 的 50 Hz 干扰。正式 CausalEEGFilter 整段计算
和连续十样本分批计算最大差为 0，舍弃初始五秒后没有超过
4 MAD 且 35 µV 的峰。此结果只排查分批滤波边界，不证明真实
输入没有异常，也没有更改生产滤波或新增削峰。

三次相隔超过五秒的只读快照中，校准均为 15/15，校准文件 SHA
仍为 01f43dbad367d8074c91b4e4180b647f12bf026fa7ebc4c2c9ce991b3d70025f，
C4 质量 0.9465、0.9407、0.8956，均可用。相对上一轮，累计坏字节
从 36 增至 522、序号缺口从 1 增至 13、流重置从 6 增至 9；
这些新快照期间计数又保持不变。最后中断原因 STREAM_TIMING_GAP。
不能沿用上一轮短观察结果宣称此后再无断流；但这些恢复并未
清除佩戴校准。一次快照为 PRIMARY_WORKER_BACKLOG，随后恢复预测。

用原始显示数据的五样本均值作局部只读诊断，在 125 Hz 下抵消
名义 50 Hz。该视图与既有因果滤波的相关性较低，未能可靠定位
原始峰与滤波峰的同一事件，不能据此声称“原始数据已确认心电”。
未保存波形，仅保存幅度、相关性和状态摘要。

运行环境核查确认 GL_SEED_EXECUTION=async、GL_COVARIANCE_STORAGE=array，
正式 57 文件指纹无差异，采集 PID 9169 未变。最新快照 C4 0.9054
可用，CH2/CH5 因幅度降权，O1 因 adaptive_outlier 降权；主疲劳
结果为 REQUIRED_CHANNEL_QUALITY，不是重新校准。SSVEP 分支为
candidate_only，输入年龄约 48 ms、hard_bad=false，但 O1/O2 均带
raw_mains、raw_amplitude 警告。该候选状态不等于注视目标识别通过。

正式程序、模型、校准门限和 PL 未改；未启动闪烁、HDMI、声音或
轮椅。后续现场检查应先区分心电线索和真实工频／共同干扰，必要
时核对参考／BIAS 的接触及线缆与电源线距离，调整前关闭 Cyton。
不以再次校准、强行削峰或降低质量门限替代信号检查。

补充证据仍在 ch4_recalibration_20261012：raw-spike-origin-check、
periodic-spike-runtime-audit、after-spike-investigation 与
filter-batch-characterization。状态是检查时快照，不是长期保证。
