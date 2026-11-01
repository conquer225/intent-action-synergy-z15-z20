# 我们意念合一

主线是用眼控、肌电和脑电分别控制灵巧手与倒立摆。眼控下保留表达、音频播放、视频浏览评分和音乐；MPU保留辅助入口。情绪、疲劳和运动想象结果只展示，SSVEP保留独立控制任务。视频图像处理不在当前主线。

用户提供的完整GuardianLoop工程包已在另一台电脑通过实物验收，S3/C3/灵巧手/倒立摆也保留此前验收记录。新增整合的本机软件、固件和FPGA构建记录见 [verification.md](report/verification.md)。设备当前不在本机，新版本的音频、真人输入和机械动作等待设备接回后验收。

## 三模式与按键

| 模式 | 页面和操作 |
| --- | --- |
| 眼控 | 首页“灵巧手／倒立摆／表达与媒体”。设备控制先注视“启用控制”，再选张开/闭合或倒立摆启停/左右短动作。表达保留“我想喝水”“我需要帮助”；视频可翻动、评分，音乐可播放、停止、切歌 |
| 肌电 | 原始ADC、RMS、按压状态和手开合。沿用已验收电极触发方式，按压事件不标成未经标定的肌肉分类，首版不做肌肉疲劳模型 |
| 脑电 | 显示原模型情绪与疲劳参考值、运动想象左右手候选；SSVEP进入独立的灵巧手/倒立摆控制页。参考结果不抢占页面或改变动作 |
| 辅助 | MPU移动控制倒立摆、信号过程和PS/PL对照；不作为第四主模式 |

PL_KEY0每按一次依次切换眼控→肌电→脑电→眼控，PL_KEY1全局停止。两个板载键位于H5/H6，接入AXI GPIO `0x41210000`，50ms消抖、按住只触发一次，上电按住先等待释放。无需另接按键。切模式和切控制页面先停止，新页面不会继承使能。

PS_KEY0在眼控模式保留连接、位置确认、重标定；采样校准进行中不另开工作进程。PS_KEY1保留取消校准、暂停/继续、退出视频，并先停止执行端。肌电模式PS_KEY0明确启用开合，先松开电极再按下。脑电模式PS_KEY0短按依次选择参考页、运动想象、SSVEP；在运动想象页长按0.8秒启动提示试次，按次序左手、右手、休息，按住不会重复。PS_KEY1终止试次。MPU通过辅助入口进入，静止时PS_KEY0置零，再按一次明确启用。

眼动仍使用原三点训练、快速检查、三区停留与换页阅读时间。校准失败、过期输入和断连不会重放动作。

## 电脑预览

在解压后的`intent_one`目录执行，Python需要Pillow、NumPy和中文字体；普通界面与板端显示使用同一Renderer。

```powershell
python -m intent_one preflight
python -m unittest discover -s tests -v
python -m intent_one preview
python -m intent_one run --simulate --control-dir ./simulation_log
```

静态页面位于`report/preview`。模拟窗口Tab切模式，ESC停止，Enter执行当前模式的确认动作，鼠标点击三区模拟一次眼控选择；终端支持`eye/emg/eeg`、`operate/process/technical/auxiliary`。调试快捷键1～6分别进入眼控手、眼控倒立摆、电极手、MPU倒立摆、SSVEP手、SSVEP倒立摆；e启用、s停止、z置零、q退出。模拟不会打开控制板或声音设备。无窗口检查可加`--headless --seconds 2`。

## Z15运行

沿用原已验收PYNQ/Linux SD环境、正式脑电模型和原生眼动程序。保留`BOOT.BIN`、设备树和原服务配置，新bit/HWH通过PYNQ独立装载。一次只运行一个显示/PL所有者，不开第二个Cyton串口读者。

1. 使用`config/network.example.json`建立本地私有配置，填与C3一致的密码。`python tools/c3_station.py config/network.local.json`只显示计划；在Z15本地终端加`sudo`和`--apply`切为C3热点。C3地址`.1`、S3`.2`、Z15`.3`。回滚使用原配置路径和`--rollback --apply`；脚本保存原配置与服务状态，改网络可能中断当前无线终端。
2. 确认原`guardianloop-cyton.service`已运行、本次启动自检通过且使用ARM后端，固定帽通道F3/F4/C3/C4/T7/T8/O1/O2。眼动根目录默认`/home/xilinx/tobii_z15`，需有原`is4-calibration`、`libtobii_display.so`和`captures`目录。不同已验收安装路径可用`--eye-root`指定。
3. 执行`sudo /usr/local/share/pynq-venv/bin/python3 -m intent_one preflight --board`，通过后执行同Python的`-m intent_one run`。PL按键即为模式切换与全局停止。
4. 先在执行端停止的条件下核对HDMI、眼动校准、脑电数据和遥测，后按 [ACCEPTANCE.md](ACCEPTANCE.md) 分项启用。SSVEP候选须同时满足显示计数、质量、连续性与两完整窗口门限；运动想象首版只显示。

默认媒体目录为`/home/xilinx/tobii_z15/media`，沿用原`playlist.json`的speech/music/videos素材。旧上传/竖版视频从`/home/xilinx/gl-media-20261007-314e8796/assets/*/cache`读取，评分沿用该目录`ratings.json`；可用`--media-dir`、`--prepared-media`、`--ratings`覆盖。旧播放状态文件可通过`--library-state`提供，其中playlist使用原id/name/cache结构。原素材、上传文件及历史评分不删除。

两条表达按原label匹配WAV。`--audio-device`可指定原ALSA设备；播放进程成功不等于扬声器可听到，缺素材、aplay或音频设备会显示原因。原包没有包含全部用户媒体素材时，继续使用原SD目录或指定原素材目录。

运动想象沿用原`/api/mi-cue`与冻结模型，trial始终`virtual_control=false`。原MI配置默认关闭时，先退出集成程序并停止执行端，运行`tools/prepare_mi.py`查看计划，在Z15加`sudo ... --apply`保存备份、开启原MI工作进程并重启采集服务；需重新等待脑电热身。`--rollback --apply`恢复原配置。不会修改模型或将实验结果晋升为正式准确率。

终端也可输入`monitor/mi/ssvep`选择脑电任务，`mi-left/mi-right/mi-rest`启动提示。试次只有在实际HDMI页面呈现后才发送presented确认；HTTP操作在有界工作线程内进行。页面租约默认原`/dev/shm/gl-media-20261007-314e8796-system-page.json`，用`--page-lease`匹配原服务的`GL_PAGE_POLICY_PATH`。

退出先停止控制与播放器、结束输入适配，确认DMA停止或完成PL重配置后释放缓冲区，并恢复原overlay。失败不自动重连或启用。

## 数据与构建

| 目录/接口 | 内容 |
| --- | --- |
| `intent_one` | 三模式、眼控媒体、原始采样、DMA、观察结果和日志 |
| `vendor` | 原算法、播放器、模型和有界视频缓存；保留来源与原门限 |
| `hardware` | 相对路径Vivado工程、信号核、显示刺激、PL键同步和测试台 |
| `firmware` | S3/C3/Nano/STM32源码快照、测试和Arduino依赖库，无私有Wi-Fi头文件 |
| `release` | 成对bit/HWH、独立XSA、已编译固件、SHA256清单 |
| `report` | 测试、编译、时序、CDC、复现记录和模拟页面 |
| `skills/intent-one-bringup` | 项目复用技能 |
| S3 TCP9000 / TCP9010 | 带ACK控制 / 单订阅者只读500Hz原始ADC、间隔、会话、序号与事件 |
| C3 UDP9001 / UDP9011 | 原STM桥接 / 只读200ms ADC、编码器与PWM遥测 |

STM32的平衡环仍在原1ms中断内，遥测从主循环非阻塞发送。过程页展示PS独立RMS与PL窗口统计；采样缺口撤销不完整窗口。ADC、编码器和PWM保留原单位，未标成力或角度。

`b`在停止条件下运行同一1000点合成输入的PS/PS＋PL对照，记录当前Z15耗时、CPU时间及数值误差到控制目录`benchmark.json`。当前交付没有板端性能数值或本轮真人准确率。

```powershell
python tools/verify.py
python tools/verify.py --firmware-tests --vcvars "实际的vcvars64.bat路径"
python tools/verify.py --rtl
python tools/vivado_tool.py --root "Vivado安装目录" vivado -mode batch -source hardware/create.tcl
python tools/build_firmware.py --arduino-cli "arduino-cli路径" --config "CLI配置文件" --keil "UV4.exe路径"
```

本机使用Vivado2023.1、ESP32 3.3.11、AVR1.8.6、ARMCC5.06。固件重建需按模板配置本地Wi-Fi；模板空密码构建用于验证源码可编译，不能连接热点。交付的现有二进制沿用本机已配置网络，属于内部交接文件。S3固定人工启用构建`MULTICONTROL_AUTO_START=0`。Nano姿态配置保持已验收值。

`tools/package.py`打包，`tools/clean_reproduce.py`从ZIP重新解压验证。来源与AI辅助记录集中在验证报告，公开提交前按原许可及私有配置范围整理。本轮没有烧录、提交、推送或发布。
