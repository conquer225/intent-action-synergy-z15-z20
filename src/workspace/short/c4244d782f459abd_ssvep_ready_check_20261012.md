# 2026-10-12：SSVEP 启动前只读检查

用户要求进入下一步。检查对象为以太网 192.168.2.99 的 Z15，未启动
闪烁、录制、HDMI、声音或轮椅，未重启服务或修改算法／校准。

## 已确认

- 同一次开机，boot 为 0e44bc51-655b-4974-b982-d6689fa20948。
- 主校准及八通道 SQI 参考均为 15/15，校准 SHA 仍为
  01f43dbad367d8074c91b4e4180b647f12bf026fa7ebc4c2c9ce991b3d70025f。
- 采集和网页服务 active；第一份质量快照 C4 0.7563、usable=true。
- 起始累计异常字节 6173、序号缺口 177、流恢复 17，较上一轮又增加。
- 随后的六次快照跨约 24.73 秒，流恢复计数 20→25，异常字节
  6461→6696，序号缺口 186→191。不是只看到历史累计数在页面增长。
- SSVEP 输入经历 ready、warmup、ready、no_data、ready、ready，原因
  涉及 malformed_or_sequence_or_timing_gap 与 input_expired。各次校准
  仍为 15/15；因此当前问题是连续输入失效，并非重新佩戴校准。
- 短观察最后原始输入快照年龄约 0.90 秒，发布时输入年龄约 33 ms。
  后者不能替代快照当前年龄；没有据此宣称没有延迟。
- 33 字节包标记异常及序号缺口由同一串口 reader 产生，早于主模型。
  没有用改质量阈值、增加队列或绕过中断检查掩盖这些异常。
- USB FTDI 为 0403:6015，sysfs power/control=on、runtime_status=active，
  latency_timer=16 ms。读取的最近内核日志未发现新 USB 掉线／重枚举。
- 网卡 RTL8188EUS 与 FTDI 同属板载 USB hub，wlan0 为 GuardianLoop-Z15
  AP、地址 192.168.50.1；以太网 eth0 为 192.168.2.99。没有改变网络。

## 推断与未知

SSVEP 实时输入不能持续覆盖窗口，继续闪烁可能只得到反复热身或
失效结果。目前没有证据把包字节异常归因于 CH4、情绪模型或校准。
无线干扰、Cyton 电池／供电、无线距离与遮挡、UART 链路仍需区分。
未读取实际 Cyton 射频频道，未更改射频配对或固件。

OpenBCI 官方 GUI Troubleshooting 的 Packet Loss 部分说明嘈杂环境、
低电量等可能导致丢包，并建议缩短 Cyton 与接收器距离或检查射频
频道。这支持排查方向，不证明 Z15 Wi-Fi 就是本次原因：
https://docs.openbci.com/Troubleshooting/GUI_Troubleshooting/

下一项建议是在以太网控制下临时停板卡 Wi-Fi AP 约 30 秒做对照，
随后恢复；这会短时影响连接该热点的设备，需要用户确认后才执行。
当前没有停 AP、停采集、重启校准或加载显示版 bit。

## 证据

`phone_video_upload/output/ssvep_ready_check_20261012/`：before、
short-input-watch、usb-and-radio-readonly。只有状态／计数／质量摘要，
未保存新 EEG 波形。流恢复与校准进度是不同的状态，不混称“重新校准”。

## 用户授权后的 30 秒关闭热点对照

用户明确允许关闭热点 30 秒后恢复。先安排独立 45 秒恢复 timer，
比较单元另有 ExecStopPost 恢复 AP/DHCP；采集和网页服务没有停止。
运行目录 `/home/xilinx/gl-wifi-receive-20261012-HSXit5`，比较单元
`gl-wifi-receive-20261012-HSXit5.service`，脚本仅记录状态摘要。
系统确认 wlan0 已 down，再开始关闭阶段；没有改频道、配对、驱动、
模型、开机配置或 PL。

- 开启前 10.030 秒：计数新增 2520 包，异常字节／序号缺口／流恢复
  均为 0。
- 关闭 30.020 秒：新增 7430 包、102 异常字节、3 次序号缺口、
  3 次流恢复。
- 恢复后 10.099 秒：新增 2780 包，异常字节／序号缺口／流恢复
  均为 0。

包数来自已发布快照端点，存在发布滞后及积压赶包；不能把短时计数
增量解释为实际 ADC 采样率改变。开启阶段各十秒，关闭阶段三十秒，
时长不同，不能仅比较绝对次数来宣称关闭热点让错误率增加。
本轮仅确认关闭热点未消除异常；单轮短对照不能彻底排除其影响，
但不支持“关闭 Z15 热点即可解决”的假设。

比较正常完成（Result=success、ExecMainStatus=0），unit 与恢复 timer
均 inactive；GuardianLoop-Z15 AP/DHCP 均已 active，wlan0 恢复
192.168.50.1/24，eth0 仍为 192.168.2.99/24。采集 PID 9169 和网页
PID 19876 不变，校准 SHA 不变、15/15 保留，正式 57 文件无差异。
更晚的恢复确认快照又显示 MALFORMED_STREAM 和 SSVEP 旁路热身；
不把恢复后的十秒零异常当作长期通过。

补充证据：`phone_video_upload/output/wifi_off_receive_compare_20261012/`
的 preflight、plan、launch、comparison-result、after-restoration。
下一项应核对 Cyton 电池／供电与无线距离、遮挡等，仍不清空校准。
