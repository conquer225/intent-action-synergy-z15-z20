# 正式开机部署验收：2026-10-01

结论：正式发布版本已经安装并启用开机加载，经真实重启和已有记录的 80 秒回放通过本次部署验收。未改写 SD/QSPI 启动镜像，未启用实验 PL 滤波或矩阵核。

## 本次完成

- 新增 `guardianloop-startup.service`，核对 25 个代码、模型、bit/HWH 文件以及固定通道顺序，再加载正式 PL 并核对硬件标识和 HGB ABI。
- 采集服务依赖启动自检成功；网页即使自检失败也能显示失败原因。失败状态目录保留。
- 主页增加“启动自检与计算分工”，以当前 boot ID 排除旧记录。SSVEP 提示页保留原有风险确认、停止及禁止外设控制逻辑。
- 原网页、原运行文件、原服务配置和启动介质哈希均留存；提供受精确哈希保护的文件级回退。

## 重启证据

发布版本：`guardianloop-fixed-cap-20261001`。

部署前 boot ID：`aac73d24-6e45-459e-bfec-f49c6ce060c3`。

真实重启后 boot ID：`4b83eb27-4354-42f1-b4e0-42b8aa32e568`。

重启后无需手动重新加载 PL，自检即为 `ready/complete`，25 个发布文件与安装清单一致。
读取的 DE/HGB/model ID 分别为 `44453031`、`48473031`、`50537911`，HGB ABI 为 `(3480,120,24,30)`。
启动自检退出成功，实测启动阶段约 36.2 秒；新增 startup、原采集和网页服务均启用开机启动。
当前启动日志没有发现 ordering cycle；`RuntimeDirectoryPreserve=yes` 已生效。
`BOOT.BIN`、`image.ub`、`boot.scr` 的哈希与部署前一致。

证据：`reboot_postflight.json`、`after_replay.json`、`deployment.json`。
PL 标识仅在启动时检查；之后有人通过 JTAG 改写 PL，需要重新核验，不能沿用本记录作证明。
板卡日历仍可能显示旧日期，应使用 boot ID 和单调时钟判断本次启动及先后关系。

## 80 秒历史记录回放

使用实际安装的正式运行文件，保留现有连续滤波、SQI、情绪、疲劳、SEED/SSVEP 候选和遥测流程。
真实采集服务暂时停止，回放输出在独立目录，USB 串口未打开；完成后恢复采集服务并重新校验安装版本和网页。

- 20,000/20,000 个输入包全部消费，生产者实际耗时 80.001 秒；包含启动/结束处理的测试总耗时 83.996 秒。
- 输入等待时间 p95 为 175.621 ms，最大 607.259 ms，分别低于事先采用的 500 ms 和 3,000 ms 门限。
- 单包处理耗时 p95 为 4.434 ms、p99 为 20.277 ms、最大 534.872 ms。不能据 p95 声称所有包都能在 4 ms 内完成。
- 主进程与子进程合计 CPU 时间 66.627 秒；主进程峰值 RSS 62,108 KiB。这个 RSS 不含全部子进程内存。
- 主流程结果与上一正式版本的参考结果逐字段完全一致；无运行错误、监视器错误或残留子进程。
- 来源明确为 `offline_replay_not_live`，未写入正式实时输出目录。

输入 SHA-256：`e263590f40edbf4581b106cc202b092b7855e68f1f3febf40bd8bc7b2bf1f255`。
参考结果：`D:\ican\codex_project\eeg_apps_z15\output\ssvep_quality_gate_20260930\post_deploy_1_primary_results.json`。
原始报告：`replay_report.json`；最终判定：`replay_audit.json`；分阶段耗时：`replay_stages.json`。

范围限制：回放用真实主循环和管道读入，遥测缓存每秒请求一次；不包含实际无线传输、网络浏览器绘制或真实闪烁注视。
本记录的主流程结果为 2 个校准状态、10 个无效状态，尚不足以完成可信校准；这证明拒绝/校准路径一致，不能当成有效情绪或疲劳分类准确率，也不是全部可预测任务的最坏负载证明。
初次回放因漏上传测试专用 `replay_stage_trace.py` 未进入数据处理；第二次碰到上次遗留的测试 tmpfs 目录，亦在处理前退出。补齐依赖并为每次尝试分配独立目录后，上述最终回放通过。未为此改动正式算法或放宽质量门限。

## ARM / PL 实际分工

固定 CH1–CH8 始终为 `F3,F4,C3,C4,T7,T8,O1,O2`。

ARM：8 通道连续滤波/SQI；GAMEEMO 情绪使用 F3/F4/T7/T8/O1/O2；疲劳使用 T7/T8/O1/O2；SEED 候选使用固定八通道；SSVEP 候选使用 O1/O2。

PL：已自动加载正式历史 DE/HGB 核，当前固定帽位算法不调用这些历史核。不得描述成“当前情绪/疲劳模型已由 PL 加速”。实验共存滤波核和矩阵核未上线。

## 软件回归及复核

从 `D:\ican\codex_project\pynq_guardianloop` 运行：

```powershell
python -m unittest test_guardianloop_startup test_ssvep_cued test_seed_shadow_web
```

结果：15 项全部通过，包含校验失败阻止 PL 加载、模型失败阻止 PL 加载、硬件失败不发布 ready、旧 boot ID 状态不显示为已通过，以及既有 SSVEP/SEED 网页回归。

板端只读复核：

```powershell
python D:\ican\codex_project\eeg_apps_z15\deploy_startup.py verify
```

需要回退本次新增配置时执行（会停止并恢复相关服务；其他人改过文件时会拒绝覆盖）：

```powershell
python D:\ican\codex_project\eeg_apps_z15\deploy_startup.py rollback
```

应用恢复包见 `package/README.md`。本次没有新增佩戴记录，没有宣称准确率提高，尚未完成真实 SSVEP 注视及光学频率验收。Cyton 关闭时网页只能显示无新鲜 EEG，启动自检正常不等于实时预测正常。
