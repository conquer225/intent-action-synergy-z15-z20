# 常开 HDMI 与私有脑电 CPU 分工对照（2026-10-10）

## 目的和范围

上一轮 Nice=0 提升视频发布帧率，但脑电过期回复增加，整机候选未采用。
用户继续“进行下一步”，本轮检验 CPU 放置分工，不提高显示优先级。
常开 HDMI 不关闭；正式采集、网页、模型、PL、启动配置都不改。
通过以太网 192.168.2.99 控制，板卡热点保持原样。静音、无闪烁、轮椅禁用。

确认：入场正式 53 文件和显示受保护文件／boot-pins 未改变，boot_id 为
8f136697-cbea-4b20-a74f-c899978d7f3a。采集 PID 7988、网页 PID 7994、
显示 PID 900 均 active、NRestarts=0。显示 session play-df4fc516 常开，
video 页、direction=stop、physical=false、stimulus=false、silent=true、
audio_output=false。实际 PL 仍 eye_wifi.bit，本轮不加载 Overlay。

确认：原私有 --split-worker-cpus 仅让 reader/父进程用 CPU0、MI/遥测/SSVEP
用 CPU1；异步主模型通过 --primary-worker-cpus 0,1 仍可使用两个核。
源码：pynq_guardianloop/soak_service_replay.py 的角色设置和 live 参数组装。
本轮修正该参数帮助文本，未改变默认行为。

推断：将显示和全部私有 EEG 计算放到不同核，可能减少调度争抢；也可能使
CPU0 排队增多。单核计算预算是否足够、视频是否同时改善，需要本轮数据判断。
未知：真人无线输入、信号质量频繁改变、佩戴识别准确率和实体轮椅效果。
本轮不能证明这些，也不将离线结果注入正式网页或显示。

## 两组参数

- shared 基线：显示 Nice=5、affinity=[0,1]；私有 reader/父进程 CPU0，
  异步主模型 CPU0/1，MI/遥测/SSVEP CPU1。
- separate 候选：显示 Nice=5、affinity=[1]；私有父进程及全部 EEG 子进程
  CPU0，异步主模型继承 CPU0，后台子进程显式 CPU0。
- 两组同一份 156 秒、39,000 包台架记录，不重复输入；数学、模型、记录和
  已有有界交接候选相同。使用 video 页策略，页面不需要的候选继续按需暂停。
  所有进程普通调度，私有 EEG Nice=0；没有增加实时调度或新依赖。
- 正式采集／网页 affinity 仍 [0,1]，本次不是整机独占核或内核 CPU 隔离。
  对照改变一整套任务放置，不能把差异单独归因于某一个线程。
- 保持质量、500 ms、新鲜度、epoch 和过期结果撤销门槛，不用减小结果检查
  或隐藏无效窗口来提高通过率。

## 实现与保护

复用 phone_video_upload/display_schedule_trial.py，新增受限 cpu-division
计划，不复制一套控制器。已有 Nice 对照模式仍支持原参数。
prewear_load.py 和 soak_service_replay.py 只新增显式私有 --eeg-cpu0；
数学、模型、采集正式文件不修改。本地文件仅复制到新的私有目录执行。

每次读取／变更均验证 boot、PID 起始 tick、线程身份、SCHED_OTHER、
Nice=5 和本轮允许的 affinity。用户换页／输出范围变化时结束私有试验，
不强行切回 video。正常结束的缓存线程可消失；同一 owner 新创建的线程
需要继承对应 affinity，恢复也覆盖它们。其他调度状态拒绝覆盖。

两组每组 240 秒上限，回放驱动 225 秒上限，整个 systemd 私有单元
RuntimeMaxSec=500 秒、KillMode=control-group、MemoryMax=384M。
finally 和独立 ExecStopPost 恢复显示所有普通线程 affinity=[0,1]，
Nice=5 不变；不对正式采集或 HDMI 发停止信号。恢复失败明确保存错误。

本地 19 项纯调度／观察器测试通过；板端 32 项测试通过，9.490 秒。
包括 affinity 设置／核验、线程复用保护、异常 RT／Nice／affinity 拒绝、
新缓存线程和重复恢复、失败不报成功、CPU角色选择、后台CPU0转发、
既有 fork 继承及普通优先级保护。板端完整 stderr 已保存。
首次只读显示安装器审计使用非 root 因文件访问权限失败，随后只读 root
审计得到 protected_unchanged=true、pin_mismatches=[]；未执行安装器写操作。

私有控制器：/home/xilinx/gl-display-cpu-20261010-DiO5Cd。
基线：/home/xilinx/gl-prewear-cpu-shared-20261010-uiEAGd。
候选：/home/xilinx/gl-prewear-cpu-separate-20261010-cudJwT。
本地证据：phone_video_upload/output/cpu_division_20261010/。
stage.json 保存计划、上传指纹和 15 个候选／数学／模型／记录的预期指纹。

## 验收边界

帧数使用已发布软件帧计数和发布时间，不是屏幕光学扫描实测，也不算重复帧。
需要检查视频低于16 fps区间、脑电输入年龄、主worker接受／过期回复、
队列积压、校准完成后的保留、EOF撤销以及严格共同窗口软件参考一致性。
未匹配窗口保留清单，不跨片段强制对齐。

即使单轮视频门槛通过，若脑电过期／积压恶化，仍不正式采用。异步候选的
校准存档／恢复和真实服务重启边界仍是接入前必要工作，不被本轮替代。
multitask_16fps_qualified 不根据单轮发布帧率自动改成 true。

## 完整结果：这套单核 EEG 分工不采用

两组均读完39,000/39,000包，输入不重复、报告错误／监测错误／残留子进程
为空。控制器每组墙钟时间201.868/204.504秒，包含启动和收尾，不是记录时长。
正常读完并不等于所有包都足够新鲜：候选组正确丢弃了10个过期包。

- shared：187个视频发布区间，平均19.488 fps、最低12.276 fps、4个区间
  低于16 fps。输入年龄p95 52.794 ms、最大300.400 ms。
- separate：188个区间，平均19.587 fps、最低12.794 fps，同样4个区间
  低于16 fps。输入年龄p95 97.132 ms、最大638.335 ms，超过500 ms门槛。
- 两组buffering观察、重复发布均为0；最大发布年龄0.557/0.581秒。
  平均帧率略升不能说明已解决低帧长尾，本轮视频条件两组均未通过。
- 主worker过期回复2→10，接受回复30→18，积压撤销3→6；提交批数
  3,884→3,869，queue_full和handoff_busy均为0。队列未满不等于结果不延迟。
- 校准完成后两组current=15、retained=true都保持；候选新增STREAM_IDLE，
  stream_resets为1→2、epochs为2→3，stale_packets_discarded为0→10。
  两组收尾时情绪／疲劳、SEED、SSVEP都撤销旧结果，没有为了帧数放宽检查。
- 严格共同(window, packets_seen)参考零差异：shared共同31个，参考34、
  候选34；含11个共同情绪prediction和9个共同NORMAL窗口。separate仅共同
  13个，参考34、候选27，共同窗口为12个CALIBRATING和1个INVALID，
  **不含共同正常预测**。候选运行中自身有4次情绪prediction，但因窗口未
  对齐，不能用这13个零差异宣称其正常预测已完成参考验证。未匹配键全部保存。
- 主进程CPU56.652/56.815秒、子进程CPU78.317/78.643秒；单包计算p95
  4.386/8.860 ms、p99 14.074/19.863 ms、最大289.868/344.822 ms。

实测monitor.jsonl确认separate中主模型、reader、producer、SEED、MI、
SSVEP、遥测子进程均为[0]；整个候选期间显示各线程为[1]、Nice=5。
shared的异步主模型实际[0,1]，MI/SSVEP在spawn初始化时可短暂继承[0]，
进入包装后的工作目标才变为[1]，没有把初始化观察错误地报告为始终[1]。

判定：overall_candidate_accepted=false，display_only_gate_passed=false，
input_age_gate_passed=false；不正式采用把全部脑电计算挤在CPU0的方案。
这是一轮顺序对照，不能证明单核放置是所有延迟的唯一原因；足以拒绝本轮
带来过期包且未满足视频门槛的候选，不再用该失败配置做佩戴测试。

## 最终恢复与下一步

finally和独立ExecStopPost均核验恢复，日志中两次
DISPLAY_ORIGINAL_SCHEDULER_VERIFIED；私有单元success/inactive/MainPID=0。
所有当前显示线程恢复SCHED_OTHER、Nice=5、affinity=[0,1]。
正式采集／网页实际仍Nice=0、affinity=[0,1]，三个正式服务PID和NRestarts
均与入场一致，未重启。53文件、boot_id、显示受保护文件及boot-pins不变；
两组15个候选／数学／模型／记录指纹未改变。实际PL仍eye_wifi.bit。
同一session继续播放video，静音、无闪烁、实体禁用、用户控制常开。
正式multitask_16fps_qualified仍false。

decision.json、acceptance-summary.json、各组acceptance-details.json保留结果；
unit-final.txt、restored.json、after-display.json、final-services.txt、
formal-audit.json、after-display-audit.json、after-session.json和
model-math-source-proof.json保留保护／恢复证据。板端源码保留在新私有目录，
没有复制到正式服务路径。

下一步保留双核共享，先完成已有后台交接候选的校准存档／恢复及真实服务
重启边界离线验收，再决定正式接入。不要继续通过强制单核或提高显示优先级
换取过期脑电结果，也不把本轮台架结果写成真人准确率或完整多任务验收。
