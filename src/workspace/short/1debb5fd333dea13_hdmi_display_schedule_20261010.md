# 常开 HDMI 显示调度对照（2026-10-10）

## 范围和目的

用户在上一轮建议显示调度对照后要求“进行下一步”。本轮仅短时改变同一
显示进程的普通线程 Nice=5 → Nice=0，再恢复 Nice=5；不关闭常开 HDMI，
不改服务文件、实时调度类、CPU affinity、正式采集、模型、PL 或启动配置。
电脑通过以太网 192.168.2.99，板卡热点不变，全程静音、无闪烁、轮椅禁用。

目的是检验降低显示线程的普通调度让步程度，能否在有脑电计算负载时减少
软件新视频帧的低帧区间，同时不使脑电输入延迟、积压和校准恢复变差。
只看视频平均帧率不足以判定通过，不为帧率放宽 500 ms 或质量门槛。

## 已确认的入场状态

正式 53 文件、boot_id、显示指纹和 boot-pins 均与上轮一致。
采集 PID 7988、网页 PID 7994、显示 PID 900 均 active、NRestarts=0。
显示 session 为 play-df4fc516，用户控制常开、没有自动到期；video 页，
direction=stop、stimulus=false、physical=false、silent=true、audio_output=false。
实际 PL 仍为 eye_wifi.bit，本轮不加载任何 Overlay。

PID 900 起始 tick 为 19902340。入场线程为 900、947、948、957、997，
均 SCHED_OTHER、Nice=5、affinity=[0,1]。按线程实际设置／读取 Nice，
不把 systemd 单元静态 Nice=5 属性误认为试验中的实际线程优先级。

## 受控方法

- 同一 156 秒、39,000 包台架记录，先 Nice=5 基线，再 Nice=0 对照。
  两组使用相同已核验的后台交接候选、参数、video 页面策略、MI 空闲 lane、
  遥测与 SEED 状态审计；页面不需要的候选依原规则暂停。
- 两个全新回放目录完整复制同一私有 runtime，不覆盖上轮目录或输出。
  四个候选代码和七个模型／记录指纹逐个一致，不改数学或权重。
- 显示通过现有只读 frame_progress 的发布计数／时间统计，不使用观察轮询
  时间冒充帧时间，也不把扫描重复算为新视频帧。没有光学测量。
- 采样过程验证 boot、显示 PID 起始 tick、线程调度类、Nice、affinity、
  session、页面和禁用输出范围；用户换页／停显示时退出，不抢回界面。
- 只允许该 owner 的普通 Nice=0/5 线程。发现实时线程、其他优先级或不同
  affinity 时拒绝操作，不用恢复代码覆盖别人设置。缓存读取线程正常退出
  不当作 PID 失踪；恢复包含同一 owner 在对照中创建的新普通线程。
- 两组回放每组最多 240 秒，整个私有单元 RuntimeMaxSec=500 秒，
  KillMode=control-group。控制器 finally 和独立 ExecStopPost 都执行恢复，
  后者不依赖电脑连接；不对 HDMI 或正式采集发信号。

## 文件和检查

新增 display_schedule_trial.py 和对应调度保护测试；prewear_observe.py 提取
sample_display 供原观察器和本轮复用，不修改正在运行的显示程序。
复用 upload_server.write_json 原子记录，不增加第三方依赖。

本地 14 项均通过；板端 14 项均通过，用时 0.188 秒。覆盖普通线程设置、
恢复中新缓存线程、重复恢复、RT／异常 affinity／异常 Nice 拒绝、PID／线程
复用保护、boot 改变拒绝、用户页面／输出范围改变退出、恢复失败明确记录，
以及既有发布帧统计和 /proc 解析。
首次远程测试调用未捕获 stderr，输出日志为空，不能作为测试通过证据；
随后显式合并 stderr，保存了完整 14 项通过日志，没有把空日志当成功报告。

私有控制器：/home/xilinx/gl-display-schedule-20261010-j9XedE。
基线回放：/home/xilinx/gl-prewear-schedule5-20261010-y9cD1i。
对照回放：/home/xilinx/gl-prewear-schedule0-20261010-vNISMX。
本地证据：phone_video_upload/output/display_schedule_20261010/。

## 解释边界

两组按顺序跑，并非随机交叉试验；视频播放相位、Linux 长尾及温度等可能
随时间变化。单轮差异仅用于工程取舍，不能证明唯一卡顿原因或永久消除长尾。
实际正式脑电当前为 no_data，私有回放不注入正式网页／HDMI，因此不验证
真实质量状态频繁变化、无线链路或佩戴准确率，也不批准实体轮椅控制。

## 完整结果：视频改善，整机候选不采用

两组各消费 39,000 / 39,000 包，没有重复输入，原记录的 SEQUENCE_GAP 保留。
Nice=5 基线含启动／收尾墙钟时间 193.064 秒；Nice=0 对照 190.776 秒。
回放错误为空，剩余子进程为空；控制单元最终 success / inactive / MainPID=0。

- Nice=5：194 个发布区间，平均 19.492 fps、最低 11.138 fps、6 个区间低于
  16 fps。输入年龄 p95 46.881 ms、最大 430.890 ms；主 worker 过期回复 4，
  接受回复 28，PRIMARY_WORKER_BACKLOG 撤销 4。
- Nice=0：190 个发布区间，平均 19.945 fps、最低 17.592 fps、低于 16 的区间
  为 0。输入年龄 p95 86.496 ms、最大 310.208 ms；主 worker 过期回复 8，
  接受回复 24，PRIMARY_WORKER_BACKLOG 撤销 5。
- 两组 buffering 观察均为 0；最大发布年龄分别 0.573 / 0.600 秒。
  两组均接收 3,884 批，handoff_busy=0、queue_full=0。
- 相同可对齐窗口与第 13 轮软件参考零差异：基线共同 30 个，参考／候选各
  34 个索引键；对照共同 25 个，参考 34、候选 31 个索引键。所有未匹配键
  都保留在各组 verification-summary.json，未跨区段强行比较。
- 两组完成校准后 calibration_current=15、calibration_retained=true 保持，
  EOF 时情绪／疲劳、SEED、SSVEP 最终均无效，旧结果撤销。
- 主进程 CPU 分别 56.668 / 57.561 秒，子进程 CPU 79.340 / 78.706 秒；
  单包计算 p95 4.197 / 6.385 ms、p99 13.797 / 18.809 ms、最大
  323.230 / 140.798 ms。不能只因最大延迟降低说整个脑电计算延迟改善。

判定：Nice=0 **仅本次台架视频发布区间**达到 16 fps 条件，但输入年龄 p95
增加、过期回复翻倍、可接受主结果减少，PRIMARY_WORKER_BACKLOG 也增加。
父进程输入年龄小于 500 ms，并不意味着后台完成后的回复也足够新鲜；后者
仍按原时间／epoch 门槛撤销。不能通过降低撤销门槛来把这些回复计为成功。
因此 overall_candidate_accepted=false，不正式采用“直接提高显示优先级”。
正式网页的 multitask_16fps_qualified 仍为 false。

下一步优先做显示与私有脑电计算的 CPU 放置分工对照，把相互争抢控制在
明确的核／任务边界；不能假定单纯 Nice=0 已把视频和脑电同时解决，也不能
仅凭此单轮断言 Nice 是全部卡顿的唯一原因。异步候选的佩戴校准存档／
恢复与真实服务重启边界验证仍为正式接入前的必要工作，本轮未改这些功能。

## 恢复与最终保护审计

finally 与独立 ExecStopPost 均完成恢复。最终实际显示线程均为 Nice=5、
SCHED_OTHER、affinity=[0,1]；没有留下试验中的 Nice=0。PID 900／session
play-df4fc516 仍播放 video、用户控制常开、静音、无闪烁、实体禁用。

正式 53 文件无改变、boot_id 不变，采集 PID 7988、网页 PID 7994、显示
PID 900 保持 active、NRestarts=0；显示静态服务配置仍 Nice=5。显示安装器
protected_unchanged=true、pin_mismatches=[]；实际 PL 仍 eye_wifi.bit，
没有停止显示、重新加载 PL 或修改 SD 启动文件。

两组各 15 个候选／数学／模型／输入指纹在回放后核验一致；控制器／测试
源码只在本地和新私有目录，不在正式服务路径上。常开 HDMI 和正式采集
都未被重启，回放预测没有注入网页或显示。

comparison.json 和各组 acceptance-details.json 保存完整回放及显示结果；
decision.json 明确区分视频条件通过与整机候选拒绝。restored.json、
after-display-threads.json、final-services.txt、formal-audit.json、
after-display-audit.json、after-session.json 和 model-math-source-proof.json
保存恢复、保护和指纹证据。测试和候选没有宣称真人识别准确率或光学时序。

后续 CPU 分工对照已完成，见 [HDMI_CPU_DIVISION_20261010.md](HDMI_CPU_DIVISION_20261010.md)。
显示 CPU1＋全部私有 EEG CPU0 同样未满足视频门槛，并出现超过500 ms的输入，
不采用；显示已恢复双核共享，正式服务／模型／PL未改。
