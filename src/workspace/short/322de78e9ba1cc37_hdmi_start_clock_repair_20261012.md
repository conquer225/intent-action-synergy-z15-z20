# HDMI 启动时间比较修复（2026-10-12）

## 结论

用户授权的两处时间比较修复已部署，9119 控制网页和统一 HDMI 已重启并恢复静态方向页。
ARM 采集及 9102 网页未重启，15/15 校准文件完全未变；模型、SD 启动配置未改。
本轮没有发送 `hdmi_start`，没有闪烁、声音或实体轮椅输出，也没有新的识别准确率结果。

局部静态检查通过，但最后核对又观察到真实 `ssvep_reader_queue_gap`，窗口退回
10/660 样本，启用已撤销。主监测同时报告 `PRIMARY_WORKER_BACKLOG`。
因此本次修复移除了已复现的时间误判，不代表真实输入连续性和整体积压问题全部解决。

## 已确认的两处原因和修复

1. 显示循环在渲染、发布状态之前取时间，稍后才读新到命令。新命令可能比旧循环时间更晚，
   `0 <= now - queued_monotonic <= 3` 的下界判断会把它误判为过期。
   在实际验证、执行命令前重新读取单调时钟；脑电更新后也刷新循环时间。
2. 脑电轮询线程可能在显示循环取时间之后发布快照。旧的调用时间可能把新快照误判为
   “未来数据”，从而触发 input_lost 并撤销启用；也可能让真正过期数据多活一轮。
   `BrainInputs.snapshot` 复制线程快照后使用 `max(now, self.clock())` 比较新鲜度。

保留原有 3 秒命令有效期及脑电新鲜度、质量检查，不交换标签、不重置校准、不放宽门限。
遵循 code-humanizer 的小范围修改原则，复用现有部署、备份和恢复入口。

生产源码仅改 `phone_video_upload/media_player.py` 和
`guardianloop_system/live_inputs.py`；新增回归覆盖在 `guardianloop_system/test_live_inputs.py`。
对应板端安装位置：

- `/home/xilinx/gl-hdmi-live-20261008-ea117349/media_player.py`
- `/home/xilinx/gl-hdmi-live-20261008-ea117349/system_runtime/guardianloop_system/live_inputs.py`

显示运行时 `boot-pins.json` 同步更新这两个文件的校验值。
`coexist_guard.py` 虽属于既有安装器的必需文件集，字节和 SHA 均未改变。

## 验证

本地修复前，新增 4 项回归有 3 项按预期失败；真正未来时间的拒绝测试原先即通过。
修复后本地相关 101 项测试通过，板端隔离测试 80 项通过，播放器编译检查通过。
早期私有测试目录缺失依赖造成的失败保留在证据目录，补齐测试目录后通过；未为此修改正式依赖。

不闪烁集成检查：主页 → 速度 → 方向 → 启用，三次执行回执延迟分别为
11.334、6.865、34.579 ms，均 applied。随后 8 次短时观察中启用保持，O1/O2
ready、660/660，输入年龄 0.0502–0.155 秒；全程 stimulus_enabled=false、
physical_output_enabled=false。此短时检查不是长期稳定性或识别效果验收。

最终独立核对：

- `play-87d62ec9.service` active，PID 4415；静态 drive 页、静音、无闪烁。
- 9119 服务 active，PID 4022。
- `guardianloop-cyton.service` active，PID 15801，与更新前一致。
- `guardianloop-web.service` active，PID 19876，与更新前一致。
- 校准 15/15；校准文件 SHA256 更新前后均为
  `14f30964edeb5ae8a1fc66bab104ff077116e79fc96f3a18bdbd3810865dfcb3`。
- 正式 manifest SHA256 未变：
  `04c24472f64e9edd36c0a73cb5117f43cd69193798ea78007208a60d92d9e45d`。
- 安装文件全部匹配计划的新 SHA。
- 最后一帧实时状态：`ssvep_reader_queue_gap`、warmup 10/660、年龄 0.3471 秒，
  direction_armed=false；主监测 `PRIMARY_WORKER_BACKLOG`，stale=false。

最后一项是实际输入/队列问题，不能算作“时间修复已同时解决”，也不能称已具备真实 10 Hz
试验条件。下一次真实刺激前应先核对连续输入；不再重复校准或重复可见闪烁单测。

## 部署与恢复

私有部署及可恢复备份目录：`/home/xilinx/gl-display-restart-20261012-VoQm2j`，
备份在其中 `backup/`，安装记录 `guard-installation.json`。
复用 `phone_video_upload/display_restart_install.py` 的校验安装/rollback 流程；
需要回滚时先停止显示、确认恢复正式 PL，再使用同目录安装器回滚，避免覆盖后续改动。

旧显示 `play-aef64f65` 已正常退出；其报告确认 original_restored、buffers_released、
display_halted 均为 true。随后才部署修复、重启控制服务并加载已有 `eye_wifi.bit`。
当前显示按用户“保持至我说停止”的授权继续运行；退出仍走既有恢复
`guardianloop_pynq.bit` 的流程。

证据目录：`phone_video_upload/output/hdmi_start_block_20261012/`。主要记录：
`timeline-before.json`、`board-tests.json`、`guard-plan.json`、`installation.json`、
`old-display-cleanup.json`、`nonflashing-start-check.json`、`after-install-verification.json`。
