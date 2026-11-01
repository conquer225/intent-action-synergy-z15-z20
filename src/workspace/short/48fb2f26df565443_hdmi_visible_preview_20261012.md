# 2026-10-12：10秒可见闪烁单测与真实识别启动检查

用户授权10秒仅显示测试，随后确认“我看见了闪烁”。用户未单独确认每一角，
不将该反馈扩写为四角光学频率或识别准确率验证。

## 显示单测已完成

- 隔离目录：`/home/xilinx/gl-visible-only-20261012-FfhmoI`。
- 单元：`gl-visible-only-20261012-FfhmoI.service`，最终 inactive、PID0、
  Result=success、ExecMainStatus=0。
- 10.00228秒、606次扫描锁存，扫描速率60.60482 Hz，最大确认间隔16.7372 ms。
  四角软件切换率约7.951/9.951/11.951/13.951 Hz；不是光学实测。
- `recognition_tested=false`；没有启动脑电判定或实体轮椅。
- 报告 errors=[]，buffers_released、display_halted、original_restored 均为 true。
- 独立恢复定时器最后为 not-found/inactive，确认没有遗留恢复定时器与新显示竞争。
- 本地相关14项测试通过。板端完整图形测试曾SSH超时，不记为通过；
  后续只读检查没有残留的 test_scan_timing_probe unittest 进程。

测试复用现有扫描诊断、StimulusFrames与原生扫描库。可见模式仅新增于隔离诊断，
要求明确同意且严格10秒；正式程序、模型、启动配置及门限没有更改。

## 接回统一显示

按用户此前“保持至我说停止”的授权，通过现有播放器入口恢复显示，
新会话 `play-aef64f65`，默认最低速度。随后返回主页、进入速度页和静态方向页。
最终显示PID17234、ARM采集PID15801、网页PID19876均active。
当前加载已有 `eye_wifi.bit`；退出显示仍按既有流程恢复 `guardianloop_pynq.bit`。

同次开机 boot_id 为 `0e44bc51-655b-4974-b982-d6689fa20948`。
正式release仍为 `guardianloop-stream-status-repair-20261012`，formal_mismatches=[]。
校准仍15/15，checkpoint SHA256与单测前相同：
`14f30964edeb5ae8a1fc66bab104ff077116e79fc96f3a18bdbd3810865dfcb3`。
没有执行wear_new、重启采集或清除校准。

## 真实10Hz识别仍未启动

静态方向页中曾连续观察到O1/O2 ready、660/660样本、年龄0.0875–0.3895秒，
但仍有raw_mains警告；静态候选分数不记作刺激响应或正确识别。
切页和arm各有一次命令超过原有3秒有效期；随后切页成功、重试arm也applied。
arm之后日志又出现input_lost，direction_armed撤销；接口曾报告page_task_resumed，
末次又为malformed_or_sequence_or_timing_gap。

这证明启动仍受输入/调度波动阻止，不证明页面租约是唯一根因。该轮前后同时
出现坏包/序号缺口增长及PRIMARY_WORKER_BACKLOG/RESULT_STALE，不能归咎电极
或用户想象方式，也不能通过放宽质量门限、重置校准来伪装解决。
没有发送hdmi_start，没有新的真实识别成绩；最终stimulus_enabled=false、
physical_output_enabled=false，停在静态drive页。

下一步应针对启动握手、页面租约更新时间与输入丢失时间线做小范围定位，
修复实际阻塞后再提示用户开始右上10Hz注视；不要重复校准或重复可见单测。

后续更新：两处跨循环/线程的时间比较误判已修复并部署，静态切页/启用短检查通过，
校准仍15/15；最终仍观察到真实输入队列缺口，尚不能宣布真实识别启动条件已满足。
详见 [HDMI_START_CLOCK_REPAIR_20261012.md](HDMI_START_CLOCK_REPAIR_20261012.md)。

证据：`phone_video_upload/output/hdmi_visible_only_20261012/` 中的
scan-report、preview-verified-cleanup、post-preview-audit、resource-check、
real-input-readiness、armed-readiness与final-static-state。
