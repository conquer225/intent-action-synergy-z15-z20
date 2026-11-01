# 2026-10-12：恢复五个全零通道并重新校准

用户报告校准时 CH1/CH3/CH4/CH6/CH7 为平线，要求恢复并重新校准。
只读核查确认这些通道的现有原始与滤波显示数据均为零，标准差为零、
唯一值数为一；不是纵轴缩放。其他三个通道仍有变化。采集 PID 9169，
校准主进度 14/15，SQI 判定平线。未将截图当作电极接触差来处理。

短暂重启既有 ARM 采集服务，启动流程重新应用八通道 power-on、
gain24、normal input、BIAS-on、SRB2-on、SRB1-off。新 PID 15801。
没有修改源码、模型、SQI 门限、启动配置或编译 PL。之后新鲜快照中
八通道原始唯一值数为 559–620，滤波唯一值数为 618–622，全部恢复
变化。恢复设置有效，但未读回 ADS1299 寄存器，尚未确认原先全零
究竟由哪个通道状态／命令异常导致。OpenBCI SDK 说明通道关闭时
会输出 0.00，这只支持配置异常的排查方向，不是本次根因证明：
https://docs.openbci.com/Cyton/CytonSDK/

确认八路恢复后，才执行用户明确要求的新 wear_new，命令
093b5e57ba5f1b05c0fac935aba76e2d 已 applied。观察 5→6→7→8→15，
最终 state=prediction、八通道均可用、没有原始平线。最后快照年龄
约 0.374 秒。5/15 到 15/15 这段检查，异常字节 1891、序号缺口 46
保持不变；这是阶段性恢复，不是永久稳定性通过。

此前用户已明确选择 ARZOPA HDMI 四角，允许加载已有 eye_wifi.bit，
不自动到期，结束恢复 guardianloop_pynq.bit。会话 play-3fce78a2 保持
运行，静音，轮椅始终禁用。没有开闪烁。新佩戴请求让界面返回静态
主页；完成校准后按既有流程进入最低档速度页，再进入静态 drive 页。
虚拟 arm 曾执行，但后续输入中断又撤销，最后观察 direction_armed=false，
HDMI preflight 尚未 ready，原因包括 input_backlog／连续窗口热身。
不能把校准完成、静态四角已呈现写成 SSVEP 注视识别验收通过。

证据在 `phone_video_upload/output/flat_channels_repair_20261012/`：before、
acquisition-reconfigured、post-channel-reconfiguration、recalibration-request、
recalibration-progress-1/2、static-direction-prepared、hdmi-ready-after-recalibration。
仅保存统计及状态，不保存本轮新波形。此前一次佩戴重校准及 HDMI
启动请求在 `ssvep_mainline_recalibration_20261012/`，保留其未完成的14/15。

下一步等待用户准备好，再按当前输入门控尝试右上 10 Hz 的短时 HDMI
测试；不绕过过期、坏包或无可信输入检查，不发送实体轮椅指令。

## 用户要求“开始10Hz”后的实际状态

用户主动要求启动右上 10 Hz 注视测试，四角频率仍是 8/10/12/14 Hz；
期望目标不发送给解码器。启动前发现旧显示会话 play-3fce78a2 因
Runtime guard heartbeat expired 退出，报告 buffers_released=true、
display_halted=true、original_restored=true；校准仍为15/15。
按此前明确的用户控制显示授权，恢复已有显示版，新的会话为
play-337f3740，未重校准、未修改程序或模型。

恢复后准备静态方向页并申请虚拟 arm，开始前门控一直因
malformed_or_sequence_or_timing_gap 未 ready，因此 hdmi_start 未发送。
一次后续检查暂时没有新鲜页面状态；只读 systemctl 确认显示服务仍
active，不能据此写成第二次崩溃。最后一次更长重试命令被工具执行
策略拒绝，未执行，也没有换工具规避。

最终只读确认显示会话在静态 drive 页面，stimulus_enabled=false，
hdmi_stimulus.active=false、session_id=null，physical_output_enabled=false。
原始八路无平线，采集 PID15801 active；校准15/15。SSVEP 输入仍因
坏包／序号／时间间隔异常未就绪。没有实际闪烁、原始录制或10Hz
识别成绩，本段不得算作完成／失败识别样本；只是启动被阻止。

证据：`phone_video_upload/output/hdmi_10hz_trial_20261012/` 的
before-recovery、display-restarted、display-restarted-ready、trial-result、
trial-retry-result、after-failed-start、final-readonly-state。HDMI 显示维持
用户控制运行，未自动停止其显示会话，实体轮椅始终禁用。
