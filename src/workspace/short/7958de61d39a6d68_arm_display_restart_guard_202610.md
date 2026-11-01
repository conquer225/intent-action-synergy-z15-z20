# ARM 后台计算与 HDMI 采集重启保护（2026-10-10）

## 本轮授权与范围

承接 ARM_PRIMARY_INSTALL_20261010.md 中失败并回退的正式接入。
用户本轮“允许”授权备份、修改 HDMI 持续保护、重新加载现有 eye_wifi.bit
恢复画面，然后重新接入后台主计算。以太网地址 192.168.2.99；不切换
手机热点。全程静音，不启动 SSVEP 闪烁，不操作实体轮椅，不改模型、
通道、量纲、质量门槛或 SD 启动镜像。用户控制的显示没有自动到期时间。

## 已确认原因和修复

显示 RuntimeWatch 调用 CoexistGuard.check_runtime，旧代码同时要求采集
始终 active 且 PID 不变。正常软件更新需要停止旧采集，因此触发
`Brain acquisition must already be running`，显示退出并自行恢复正式 PL。

只在统一 media_player 中显式启用 allow_acquisition_restart。独立旧眼控
会话默认仍严格要求进程不变。初次显示准入仍要求采集已运行、正式发布
完整、显示 bit/HWH 校验通过、全部脑任务为 ARM、固定八通道、无 DMA
keeper/gldma 冲突、无实体控制。停止/重启不再是关闭画面的充分理由。

采集短暂停止时仍检查当前 boot、自检任务和 PL 独立性；恢复进程须重新
检查命令、通道/模型配置，以及完整发布文件。只接受明确锁定的两个
发布清单 SHA（旧正式版和本轮经过既有板端检查的后台版），不接受任意
新发布。PID 和 start_ticks 一起构成采集身份，避免复用旧 PID。

BrainInputs 取得该身份；采集不可用时清除缓存和序号、撤销监测和方向。
重启后不得复用旧进程的缓存，跨身份变化的在途 HTTP 响应也会丢弃。
原数据时效、质量、SSVEP 页面/锁存证明和严重疲劳锁定规则保留。
没有通过跳过所有异常或伪造有效脑电维持界面。

显示持续保护之外的失败（例如 PL 归属冲突、非法配置、检查 IO 错误）仍
可能安全退出。此次修改不承诺硬件掉电或所有系统异常都不会影响显示。

## 软件检查与备份

修复私有目录：`/home/xilinx/gl-display-restart-20261010-f4M22a`。
修改目标仅 coexist_guard.py、media_player.py、统一运行目录的
guardianloop_system/live_inputs.py，以及 boot-pins.json。正式脑电代码
在这一阶段未变。逐文件 SHA 和模式保存于 guard-plan.json，原件于 backup。
安装异常自动恢复原件，拒绝覆盖不符合原/新指纹的后来修改。

首轮板端测试缺少私有目录中的 eye_entry.py，48 项里有 2 项导入失败；
未部署。补齐板上原有依赖后重跑，48 项全部通过，0.836 秒。这包含
停机撤销、旧序号拒绝、在途响应丢弃、严格初次准入、恢复发布检查及
DMA/PL 冲突负向测试。测试不会访问真实 USB 或加载 PL。

## 恢复 HDMI 与正式接入

重新加载现有显示工件：

- 板卡：当前 Z15，Zynq-7015；本轮没有创建 Vivado 工程或猜测引脚/约束。
- bit：`/home/xilinx/tobii_z15/overlay/eye_wifi.bit`
- bit SHA256：`8b52892466a1b4d025c5c693a951727ae6215e57ca3e5fa0dedaa2a1d510d50f`
- hwh SHA256：`5dcfe537c6793f5b18b47550f73078ab8d73500888e585037a707c8be1ebacef`
- 原恢复目标：正式目录的 guardianloop_pynq.bit。

新显示会话 play-a23ec084.service，PID 32491。中央播放已准备的小狗 SD
视频；state=playing，silent=true，direction=stop，stimulus_enabled=false，
physical_output_enabled=false。仅软件和扫描状态确认，未请求用户重新
目视验收。失败时现有回收路径先停止显示 DMA，再释放缓冲并恢复原 PL。

新正式安装目录：`/home/xilinx/gl-calibration-install-20261010-d8sNJn`。
复用前一轮逐字节相同的六个合格源码与清单，不重新覆盖整个隔离目录。
继承 70 项板端短组全部通过及数值组 8 通过、1 跳过的证据；跳过不计通过。
新安装重新捕获当前网页/服务/显示 PID、start_ticks 和所有目标 SHA。
更新后的 boot-pins 同时保留本轮显示保护指纹。

正式版本 `guardianloop-fixed8-primary-async-20261010`，56 文件。
清单 SHA256：`38237fbb34b6a5d3399cb37df20270580e55fecf0dc8ef7d851678c5380ac105`。
新增后台主计算和遥测缓存；SEED 保持原异步/按页面调度；未推广 MI 分批
候选。安装 phase=committed，独立回退 timer 已停止。采集 PID 1865，
后台主计算 PID 1984，ARM、固定八通道、无 ESP32 输出，NRestarts=0。

RuntimeDirectoryPreserve=yes 在停止旧采集前生效，避免停止服务时删除
同一次开机的校准/佩戴目录。仍然执行 boot、佩戴、模型和滤波契约校验；
新佩戴和板卡重启不能盲目沿用旧基线。部署开始时并无完整校准文件，
不能声称恢复了当前不存在的已完成校准。

网页 PID 7994、统一网页 PID 9537、显示恢复看护 PID 10613 和显示
PID 32491 均保持原 start_ticks，没有因正式接入重启网页或显示。
实际 PL 始终为显示版，模型权重未改。正式 56 文件及所有 boot-pins
最终检查无不匹配。

## 观察与限制

安装旁路记录器保存 35 个样本、25.82 秒，覆盖采集暂停的 3 个样本。
其中 2 个已明确呈现 acquisition_available=false；轮询不是零延迟的。
暂停样本没有可信情绪/疲劳结果；全程方向停止、无闪烁/实体输出，
运行目录一直存在，显示会话/PID 不变且帧号继续增加。

该记录器在模型加载期间的一次 systemctl 查询达到 3 秒时限，退出为
failed/status=1，不能计为完整 60 秒通过。失败日志保留。随后只读
观察单独运行，查询时限改为 10 秒，不再重启任何正式服务。

补充只读观察正常完成：success / inactive / status=0，88 个样本、59.87
秒。采集持续 active / PID 1865，四个 UI/看护进程身份不变，画面一直
playing、帧号增加 600，无闪烁/实体输出/可信伪结果。所选 SD 视频缓存
本身为 10 fps、288×512、102 帧，因此此处约 10 个新帧/秒符合素材帧率，
不能用来判断 16 fps 视频或真实脑电负载下的吞吐。佩戴状态文件与安装
前备份逐字节相同；独立回退 timer inactive。wlan0 保持 FPGA 热点
192.168.50.1，没有切换手机热点。

当前 Cyton 无完整数据包，正式状态 WAITING_FOR_CYTON / valid=false /
calibration_current=0。本轮只能确认部署、恢复和停机隔离流程；真实收包、
佩戴后校准、完整脑电负载下视频最低帧率及四频/休息仍待实测。
multitask_16fps_qualified 继续为 false，不据此宣称准确率或流畅度达标。

恢复须按发布指纹核对，不能直接解包覆盖正式目录。先使用本轮正式安装
目录的受校验 rollback，恢复旧 ARM 和对应显示元数据；只有准备撤销
显示保护时，才在停止显示、完成 DMA 回收后恢复其四个目标。不得对
后续版本直接套用旧回退，也不得为了回退停止用户显示而不说明。

证据：`phone_video_upload/output/display_restart_guard_20261010/`。
恢复包和部署阶段不含原始脑电或用户视频；备份可能含佩戴状态，按私有
工程资料保存。独立回退 timer 只保护安装，不给用户显示设置到期时间。

恢复包已同时保存板端和本地：
`guardianloop-primary-display-recovery-20261010.tgz`，2,310,653 字节，
SHA256 `98526e8fcadf74443f5341a8c1120772e5eae3cdca8cf020272b1988fe2d51d8`。
本地下载 SHA 和包内各变化目标的原件/候选逐文件 SHA 均复核通过，
共 101 个归档条目。保留首次失败的恢复包，不覆盖旧证据。
