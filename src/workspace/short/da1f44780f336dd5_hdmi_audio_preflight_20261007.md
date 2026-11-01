# HDMI 实际发声测试前检查（2026-10-07）

用户请求测试 ARZOPA HDMI 屏幕能否发声。本轮只读取 Z15 的音频设备、内核配置和现有显示 HWH，没有播放测试音、加载驱动、改变 PL、重启服务或操作轮椅。

## 已确认

- Z15 `192.168.2.99`，Linux `5.4.0-xilinx-v2020.2`，boot ID `e0fd1f19-9ccd-494d-b262-7a5924046336`。
- `/proc/asound/cards` 为 `--- no soundcards ---`，`/proc/asound/pcm` 为空。
- `/dev/snd` 只有 `timer`，没有 PCM 播放设备。
- 已有 `/home/xilinx/tobii_z15/bin/aplay -l` 报告 `no soundcards found`。
- 没有已加载的 snd/audio/hdmi 模块，也没有枚举到 USB 音频设备。设备树按 sound/audio/i2s 名称检索未找到节点；此检索不是对所有 compatible 值的完整审核。
- 内核启用了 ALSA/PCM/ASoC 及部分 ADI I2S/SPDIF 支持，但 `CONFIG_SND_USB_AUDIO` 未启用。编译选项存在不等于可用声卡已经注册。
- 本机配套 `brain_eye_coexist/candidate/eye/overlay/eye_wifi.hwh` 列出 `openedv.com:user:DVI_Transmitter:1.0`、VDMA/VTC/视频接口等，模块清单中没有独立音频模块。HWH 不能代替未取得的显示 RTL 来证明所有内部逻辑。
- 正式采集服务 PID 24926、网页 PID 677 均 active，NRestarts=0。本轮未启停它们。

## 结论与边界

当前没有 Linux 可用的音频播放通道，所以不能通过现有 Z15 程序发送实际测试音。没有进行失败播放后把“无声”解释为屏幕坏了，也不把此前只解码到 RAM 的 `audio_probe` 当作声音播放验收。

ARZOPA 具体型号、内置扬声器能力、静音/音量和 HDMI 音频接收情况仍未知。先将同一屏幕的 HDMI 接到已具备正常 HDMI 音频输出的电脑，选择对应显示器音频输出、关闭静音、以低音量播放短声音，可以独立验证屏幕侧；这不能证明 Z15 音频通路通过。

若屏幕侧通过，后续再评估 Z15 的音频发送硬件、显示 PL 和 Linux 设备/驱动方案。不能仅凭有 HDMI 图像就认为已具备音频，也不能未经授权改 bitstream、设备树或安装驱动。
