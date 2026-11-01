# 2026-10-12：获准的静态 HDMI 守卫诊断

用户明确允许临时加载已有 eye_wifi.bit、做不闪烁诊断、结束恢复
guardianloop_pynq.bit，并要求避免不必要的防御性修改。没有联网、驱动
安装、重新烧录 SD、合成 FPGA 工程或改变模型。

## 范围与实现

复用已有 scan_timing_probe、run_scan_timing 和 RuntimeWatch。
仅在隔离诊断目录给 RuntimeWatch 补上检查启动／完成、检查耗时、
线程唤醒延迟、在途检查和线程 ID 的观测。原每秒检查周期、四秒过期
保护、真实检查异常退出、显示 DMA 停止／缓冲回收逻辑均不变。
已核对本地 system_hdmi.py 在 RuntimeWatch 类以外与正式文件完全一致。
正式 system_hdmi.py、media_player.py 和菜单缓存没有被覆盖。

扩展现有静态采样函数，检查撤销时先退出，再访问扫描计数器；不另建
第二套守卫或新的准入框架。复用原调度设置 SCHED_OTHER/Nice=5，不设置
实时优先级或绑核优化。临时诊断自恢复窗口为 150 秒，容纳 ARM 导入和
完整 30 秒扫描；并非给正式显示增加到期时间。

隔离目录：`/home/xilinx/gl-scan-20261008-5ee7a286`。沿用既有工具的目录
前缀，实际诊断日期为 2026-10-12。

目标为 Z15，加载既有
`/home/xilinx/tobii_z15/overlay/eye_wifi.bit`，恢复
`/home/xilinx/jupyter_notebooks/guardianloop_pynq/guardianloop_pynq.bit`。
没有创建新的 bitstream。准入检查核对 bit/HWH、原正式模型和恢复文件。

## 测试结果

修改前相关六项测试通过；扩展后的 14 项测试在本机与板端 Python 3.8
均通过，板端 2.152 秒。包括：守卫真实异常不被吞掉、四秒过期仍退出、
在途检查不能提前刷新已验证心跳，以及调度等待与检查耗时分离。
第一次读取本地源码用系统默认 GBK 编码失败，随后显式 UTF-8 读取完成
范围比对；没有在该失败时加载 PL。

30 秒实际扫描完成（30.00009 秒），无守卫或 VDMA 错误。硬件扫描计数
增加 1,818，约 60.600 Hz，VDMA 状态 0x11000；这是扫描计数，不是新
视频帧率，也不是光学频率实测。轮询最长间隔约 29.15 ms，因此部分扫描
未被逐帧观察，不能将轮询间隔当作屏幕每帧实际间隔。

运行守卫成功完成 26 次检查，最长约 170.00 ms；唤醒延迟最大约
0.933 ms，结束采样时最近有效检查年龄约 893.59 ms，无在途检查／错误。
静态固定像素，没有闪烁、音频、眼控 USB 打开或轮椅输出；Cyton 关闭，
采集服务未被停止／重启。

退出确认 display_halted、buffers_released、original_restored 均 true，
errors 为空。boot、采集／网页 PID、保护文件与开始前一致，PL 确认恢复
guardianloop_pynq.bit。独立恢复计时器在恢复确认后取消。

证据：`phone_video_upload/output/hdmi_guard_diagnostics_20261012/`。
含 launch、before、软件测试、guard-tests、observation-only-scope、scan-report、
after、unit-status 和 final-health。正式发布仍为
guardianloop-stream-status-repair-20261012。

## 结论边界与下一步

原先长时运行中的 Runtime guard heartbeat expired 本轮没有复现。
不能说根因已经修复，也不据此改长／删除原有保护。此次诊断没有覆盖
中央视频解码、多任务真实脑电或真实 SSVEP 刺激负载；短时静态通过不
替代这些检查。新增观测目前只在隔离候选中，并未正式部署。

下一步先开启 Cyton PC 模式、不佩戴，做完整 40 秒纯收包检查。
当前关机状态无法确定无线坏包／序号缺口来源。收包通过后可以推进
短时佩戴和四频＋中心休息，不因本轮未复现的静态问题无限追加防御
条件。实体轮椅仍禁用，先验证识别、停止和撤销旧命令。

后续：用户已开机并获准完成 40 秒纯收包，零坏字节／零序号缺口。
用户同时确认已佩戴并要求重新校准，已在恢复采集后主动重启基线。
见 [CYTON_RECEIVE_CHECK_20261012.md](CYTON_RECEIVE_CHECK_20261012.md)。
