# ARM 后台主窗口：校准存档与进程恢复（2026-10-10）

## 范围

承接 HDMI_CPU_DIVISION_20261010.md。只更新本地候选及新的私有目录
`/home/xilinx/gl-primary-recovery-20261010-NeqEAx/runtime`，不部署正式采集，
不重启正式服务，不关闭常开 HDMI，不切换热点、PL、模型或开机配置。
通过以太网 192.168.2.99 工作；静音、无闪烁、实体轮椅禁用，不需要佩戴。

## 已确认的缺口

异步主窗口在 fork 子进程内累积 SQI 和疲劳校准；父进程保留的是 fork 前的
对象副本。原 accept_primary 存档路径只认识父对象，而且私有异步模式不能
启用 wait-for-data，因此此前的异步回放没有覆盖真实后台校准保存路径。
显式新佩戴原来只更新父对象、发普通流重置，不能保证子进程清除旧基线。
这是接入正式服务前的缺口，不等同于已经证明正式同步程序因此反复校准。

证据代码：pynq_guardianloop/async_primary.py、cyton_guardianloop.py、
calibration_session.py、wear_session.py。数学与模型文件本轮未改。

## 候选修改

- AsyncPrimaryWorker 接受 CalibrationSession，在实际计算进程内保存真实
  校准；父 accept_primary 只在同步模式保存，避免写入父进程旧副本。
- checkpoint 提交和显式新佩戴删除共用 generation 锁。新佩戴携带独立
  wear_id 到子进程；旧 epoch 的在途窗口不能在删除后重建旧存档。
- 普通断流／epoch 撤销不清空已接受基线。存档写失败单独计数、记录错误，
  不假报“已保存”，也不以写失败为理由丢弃现有基线。
- 私有 --isolated-primary-checkpoint 只允许 /dev/null、ARM、无 ESP32，
  状态与遥测必须位于同一个 /dev/shm/gl-primary-recovery-* 目录；仍禁止
  live USB、wait-for-data 和 PL。没有加入可直接上线的异步实时开关。
- 沿用现有 boot、wear_id、通道顺序、量纲、模型 SHA 和滤波契约检查。
  仅恢复校准，不恢复旧预测、EMA、滤波历史或计算窗口；文件权限为 600。

32 批容量、输入数组所有权、500 ms 门槛、质量判断及过期撤销均保持原规则。
generation 锁中的存档提交增加了少量工作；本轮不是此改动的吞吐性能验收。

## 自动检查

板端 Python 3.8 / Linux fork 运行 37 项，151.433 秒结束：36 通过，1 项
未提供锁定旧提取源码的全主循环对照跳过，退出状态 success / MainPID=0。
覆盖真实后台 partial→SIGKILL→恢复→complete、同步／异步校准后数值一致性、
新佩戴与在途旧窗口竞态、写失败计数、队列容量、epoch、时效和存档校验。
新加 6 项全部通过。跳过项不计为通过。

Windows 本地 18 项检查中 1 项通过、17 项 Linux 用例跳过；另做源码编译检查。
不能把 Windows 跳过项作为板端结果。

首次板端测试遗漏 GL_TEST_FATIGUE_MODEL，37 项出现 19 errors / 1 failure /
1 skip；原因是测试寻找原树的模型路径。保留 board-tests.log，补正确私有
模型路径后使用新单元重跑，上述成功记录为 board-tests-fixed.log。

首次私有服务演练的硬件 open 保护误拦 Python 自己的 /dev/shm/pym-* 共享
内存，未访问 USB。修正为只替换主模块的 os 引用，不修改全局 os.open。
失败记录 partial.log 保留；不把失败尝试混入成功统计。

## 实际私有进程演练

使用 primary_recovery_probe.py，在独立 tmpfs
`/dev/shm/gl-primary-recovery-20261010-JZXmdi` 中运行不同 systemd 单元。
每项有 120 秒上限、384 MiB 上限、KillMode=control-group、用户 xilinx。
只有故障注入阶段主动结束自己的进程；不操作正式服务或显示进程。

输入为生成信号，主循环打开的设备仅 /dev/null，使用实际后台进程和当前
SQI、疲劳、协方差模型计算。功能演练对输入做 backpressure，并保留真实
monotonic 时钟和原时效判断；不是 250 Hz 连续无线或全部任务负载验收。
SEED、SSVEP、MI 和真实录制器未参与这些进程演练。

首次 partial 与自动检查并行，出现 STREAM_TIMING_GAP / 计算滞后，6000
生成样本只接受 1 个基线窗口。断流后保持 1，不解释为三窗口完整通过，也
没有修改生产时序门槛来掩盖此结果。

阶段结果（各阶段使用不同的实际服务进程）：

- partial：主 PID 17897、worker 18079，0→1；仅 /dev/null。
- crash：主 PID 19307、worker 19455，从存档 1 恢复、接受并提交第 2 个基线
  后对自己的主进程发 SIGKILL。Result=signal / status=9 是预期注入故障，
  不冒称正常退出；退出后私有控制组为空、worker 未遗留。
- complete：主 PID 19850、worker 19978，在新进程内从 2 恢复并补到 15。
  此阶段直接给实际后台 worker 批量输入，是功能补齐，不是主循环吞吐测量。
- restored：主 PID 20288、worker 20404，主循环启动即加载 15；启动结果无效。
  1000 样本处注入 550 ms 无输入，STREAM_IDLE 撤销情绪／疲劳但保留 15。
  之后还有两次真实时钟检测到的 STREAM_TIMING_GAP，同样保留 15。
  新鲜窗口给出 MILD 1 次、NORMAL 2 次；EOF 再撤销。完整存档与本阶段前
  的文件逐字节相同。情绪仍在 collecting_12s，未得到新的情绪预测，不能
  把本阶段描述为情绪正常预测恢复通过。
- newwear：主 PID 21161、worker 21253，加载 15 后主动请求新佩戴。
  EXPLICIT_NEW_WEARING 结果为 0、无效、calibration_retained=false，
  旧 wear_id 改变；新文件仅含新佩戴接受的 1 个基线，与新身份一致。
- rejected：主 PID 21671、worker 21777；只将私有测试存档的 SQI scale
  改为负数。主循环报 CALIBRATION_CHECKPOINT_REJECTED，从 0 开始，
  200 样本结束仍为 0，无有效结果。损坏文件保留用于审计，未假报其被恢复。

五个干净结束的阶段均 success / inactive / MainPID=0；所有私有进程和控制组
均无遗留。真正后台保存的所有功能阶段 checkpoint_write_failures=0。
存档及 wear-state 权限为 600、属主 xilinx。assert 汇总见 acceptance-summary.json。

## 证据与下一步边界

`phone_video_upload/output/primary_recovery_20261010/` 保存阶段日志、
存档快照、服务状态、源码指纹、模型数学核对及正式／显示前后保护审计。

最终正式 53 文件未改变，boot_id 仍为 8f136697-cbea-4b20-a74f-c899978d7f3a。
采集 PID 7988、网页 7994、显示 900 保持 active / NRestarts=0，启动 tick
与上轮保护审计相同；实际 CPU affinity 均为 [0,1]，采集／网页 Nice=0、
显示 Nice=5。PL 仍为 /home/xilinx/tobii_z15/overlay/eye_wifi.bit。
显示安装审计 protected_unchanged=true、pin_mismatches=[]，四个显示文件
指纹不变。只读会话仍为 play-df4fc516 / playing / video / user_controlled；
静音、audio_output=false、stimulus=false、physical=false、direction=stop。

候选四个源码传输指纹一致；此前核对的七个模型／记录、四个数学核心及
三个未改诊断源（共 14 文件）指纹一致。网页 multitask_16fps_qualified
仍为 false，未利用本次功能演练改写为通过。

这是正式接入前的隔离功能检查，不证明当前用户识别准确率，不证明视频
稳定达到 16 fps，也不证明任意硬件故障都可以永久复用校准。重启板卡、
换模型／通道／量纲或显式确认新佩戴仍必须遵守校准身份与安全门控。

正式部署需要独立明确的备份、接入开关、短暂采集重启、启动／恢复核验与
回退路径；本轮没有实施。随后仍需真实无线连续输入的短检查。
